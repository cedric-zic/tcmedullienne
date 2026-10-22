# -*- coding: utf-8 -*-
"""
pipeline_ocr.py — Traite une fiche d'inscription numérisée (PDF scanné, photo,
PDF rempli sur ordinateur) et produit un dictionnaire structuré + un niveau de
confiance par champ.

Usage :
    python pipeline_ocr.py --fichier "Inscription_2026_DUPONT_Jean.pdf"
    python pipeline_ocr.py --dossier /chemin/Fiches_inscriptions --sortie revue.ods
    python pipeline_ocr.py --dossier /chemin/Fiches --test  # 5 premières fiches

Le pipeline ne valide JAMAIS seul : chaque champ est annoté d'une confiance et
le résultat est destiné à la revue humaine (export ODS de revue).
"""

import argparse
import json
import logging
import os
import sys
from datetime import datetime

import numpy as np

import traitement_image as ti

logger = logging.getLogger("pipeline_ocr")

DOSSIER_COURANT = os.path.dirname(os.path.abspath(__file__))
GABARIT_DEFAUT = os.path.join(DOSSIER_COURANT, "gabarit_v12.json")

LOG_DIR = os.path.join(DOSSIER_COURANT, "logs")
LOG_FILE = os.path.join(LOG_DIR, f"ocr_inscriptions_{datetime.now().strftime('%Y%m%d')}.log")

FORMULES_PAR_ID = {}  # rempli au chargement du gabarit


def configurer_logging():
    os.makedirs(LOG_DIR, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[
            logging.FileHandler(LOG_FILE, encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )


def charger_gabarit(chemin=GABARIT_DEFAUT):
    with open(chemin, encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Lecture d'une fiche
# ---------------------------------------------------------------------------

class ResultatFiche:
    """Résultat structuré de l'OCR d'une fiche."""

    def __init__(self, fichier):
        self.fichier = fichier
        self.champs = {}        # nom_champ -> {"valeur":..., "confiance":..., "type":...}
        self.alertes = []       # champs à revue humaine
        self.erreurs = []

    def set(self, champ, valeur, confiance, type_champ="texte"):
        self.champs[champ] = {"valeur": valeur, "confiance": round(confiance, 3), "type": type_champ}
        if confiance < 0.7 and valeur:
            self.alertes.append(champ)

    def ajouter_alerte(self, message):
        self.alertes.append(message)

    def score_global(self):
        """Confiance moyenne des champs texte lus (0..1)."""
        confs = [c["confiance"] for c in self.champs.values() if c["type"] == "texte" and c["valeur"]]
        return float(np.mean(confs)) if confs else 0.0

    def en_dict(self):
        return {
            "fichier": self.fichier,
            "date_traitement": datetime.now().isoformat(timespec="seconds"),
            "champs": self.champs,
            "alertes": self.alertes,
            "erreurs": self.erreurs,
            "score_global": round(self.score_global(), 3),
        }


def _lire_cases(img, recalage, cases_dict, y_range, dpi, resultat, prefix):
    """Lit un groupe de cases à cocher avec détection relative (médiane du groupe).

    `cases_dict` : {nom: [x0, x1]} ou {nom: {"x": [x0, x1]}}.
    `y_range` : [y0, y1]. Retourne la liste des cases cochées.
    """
    rects = []
    for nom, xr in cases_dict.items():
        if isinstance(xr, dict):
            xr = xr["x"]
        zone = {"x": xr, "y": list(y_range)}
        rects.append((nom, recalage.zone_pixels(zone, img.shape, dpi)))
    cochees, ratios = ti.detecter_cases_groupe(img, rects)
    ratios = {nom: round(r, 3) for nom, r in ratios.items()}
    resultat.set(f"{prefix}_brut", ", ".join(cochees), 1.0 if len(cochees) == 1 else 0.3, type_champ="case")
    resultat.champs[f"{prefix}_brut"]["ratios"] = ratios
    if len(cochees) == 1:
        resultat.set(prefix, cochees[0], 0.95, type_champ="case")
    elif len(cochees) == 0:
        resultat.set(prefix, "", 0.0, type_champ="case")
        resultat.ajouter_alerte(f"{prefix} : aucune case cochée détectée")
    else:
        resultat.set(prefix, " + ".join(cochees), 0.4, type_champ="case")
        resultat.ajouter_alerte(f"{prefix} : {len(cochees)} cases cochées ({cochees}) — vérifier")
    return cochees


def _lire_texte(img, recalage, zone, dpi, resultat, champ, psm=7, nettoyeur=None):
    rect = recalage.zone_pixels(zone, img.shape, dpi)
    texte, conf = ti.ocr_zone(img, rect, psm=psm)
    if nettoyeur:
        texte = nettoyeur(texte)
    resultat.set(champ, texte, conf)
    return texte


def traiter_fiche(fichier, gabarit, dpi=ti.DPI_LECTURE):
    """Traite une fiche complète. Retourne un ResultatFiche."""
    ti.verifier_dependances(avec_ocr_texte=True)
    resultat = ResultatFiche(fichier)
    ext = os.path.splitext(fichier)[1].lower()

    # --- Chargement de l'image de la page 1 ---
    if ext == ".pdf":
        import fitz
        doc = fitz.open(fichier)
        if doc.page_count < 1:
            resultat.erreurs.append("PDF vide")
            return resultat
        # Détection du type de PDF :
        # 1. PDF rempli sur ordinateur (couche texte + éventuelles annotations) ;
        # 2. PDF = scan pleine page (1 image embarquée couvrant toute la page) ;
        # 3. PDF = assemblage de morceaux de scan (plusieurs images, souvent
        #    tournées 90°, basse résolution) + éventuellement couche texte bureau.
        page = doc[0]
        couche_texte = page.get_text().strip()
        images = page.get_images(full=True)
        image_principale = None
        for img_info in images:
            pix = fitz.Pixmap(doc, img_info[0])
            if pix.width > 400 and pix.height > 400:
                image_principale = img_info
            pix = None
        # Vérifier si l'image couvre (approximativement) toute la page
        couvre_page = False
        if image_principale:
            rects = page.get_image_rects(image_principale[0])
            for r in rects:
                if r.width > 0.8 * page.rect.width and r.height > 0.8 * page.rect.height:
                    couvre_page = True
        # Seuil de couche texte : un PDF rempli sur ordinateur a des MILLIERS
        # de caractères (tout le texte imprimé + les réponses). 200 caractères,
        # c'est typiquement une couche 'bureau' ajoutée sur un scan.
        if len(couche_texte) > 1000 and not couvre_page:
            logger.info("%s : PDF avec couche texte détectée, extraction directe", os.path.basename(fichier))
            return traiter_pdf_texte(fichier, doc, gabarit, resultat)
        if len(couche_texte) > 50:
            # Extraire les données bureau de la couche texte (paiement, chèques...)
            resultat = extraire_couche_bureau(couche_texte, resultat)
        if doc.page_count > 1:
            resultat.ajouter_alerte(
                f"PDF multi-pages ({doc.page_count}) : pages suivantes ignorées "
                "(probablement chèques / preuves de paiement scannés en complément)"
            )
        # Sélection de la page FICHE : la première page contenant l'en-tête
        # "Tennis Club La Médullienne" (OCR rapide de l'en-tête). Par défaut,
        # la page 0. Les pages suivantes sont des chèques / preuves de paiement.
        page = _selectionner_page_fiche(doc)
        img = ti.rasteriser_page_pdf(page, dpi)
    elif ext in (".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".webp"):
        from PIL import Image
        with Image.open(fichier) as pil:
            info = pil.info.get("dpi")
        img, _ = ti.charger_image(fichier, dpi)
        # Le dpi déclaré d'une photo/scan est souvent faux (96, 72...). On estime
        # le dpi réel par recalage : la largeur de page A4 doit faire ~595.3 pt.
        # Le recalage estimera l'échelle ; on se contente ici de passer le dpi
        # nominal de lecture, l'échelle sera corrigée par estimer_recalage.
        dpi = dpi  # conservé ; l'échelle du recalage absorbe l'écart
    else:
        resultat.erreurs.append(f"Extension non supportée : {ext}")
        return resultat

    # --- Prétraitement ---
    img = ti.corriger_inclinaison(img)

    # --- Upsampling si le scan est basse résolution (< 200 dpi effectif) ---
    # Les scans à 110 dpi (photos) doivent être upsamplés pour que Tesseract
    # puisse lire le manuscrit. Facteur x3 => ~330 dpi.
    zoom_lu = dpi / 72.0
    largeur_pt_estimee = img.shape[1] / zoom_lu
    dpi_effectif = img.shape[1] / (595.3 / 72.0)
    if dpi_effectif < 200:
        facteur = int(round(300 / max(1, dpi_effectif)))
        if facteur > 1:
            from PIL import Image
            img = np.array(Image.fromarray(img).resize(
                (img.shape[1] * facteur, img.shape[0] * facteur), Image.LANCZOS))
            dpi = int(dpi * facteur)
            logger.info("Upsampling x%d (%.0f dpi -> %d dpi)", facteur, dpi_effectif, dpi)

    # --- Recalage gabarit ↔ scan ---
    recalage = ti.estimer_recalage(img, gabarit, dpi)
    if recalage.fiabilite < 0.3:
        resultat.ajouter_alerte(
            f"Recalage faible (fiabilité {recalage.fiabilite:.0%}) — fiche à vérifier visuellement"
        )
    elif recalage.fiabilite < 0.7:
        resultat.ajouter_alerte(
            f"Recalage incertain (fiabilité {recalage.fiabilite:.0%}, résidus élevés) "
            "— photo déformée, vérifier tous les champs"
        )

    # --- Sexe ---
    sexe_adh = gabarit["sexe_adherent"]
    _lire_cases(img, recalage, sexe_adh["cases"], sexe_adh["ligne_y"], dpi, resultat, "sexe_adherent")
    sexe_rep = gabarit["sexe_representant"]
    if any(True for _ in [0]):  # représentant : ne lire que si la zone contient de l'écriture
        pass
    # On lit toujours le sexe représentant ; s'il est vide, les cases seront vides.
    _lire_cases(img, recalage, sexe_rep["cases"], sexe_rep["ligne_y"], dpi, resultat, "sexe_representant")

    # --- Coordonnées adhérent ---
    # Marge verticale à exclure (les séparateurs horizontaux du tableau
    # coordonnées sont dans les zones ; on les rogne pour ne pas polluer l'OCR).
    ROGNE_SEPARATEUR_PT = 2.5

    def zone_saisie(z, x_defaut):
        y = z["y"]
        return {"x": z.get("x", x_defaut), "y": [y[0] + ROGNE_SEPARATEUR_PT, y[1] - ROGNE_SEPARATEUR_PT]}

    coord_adh = gabarit["coordonnes_adherent"]
    x_saisie = coord_adh["x_saisie"]
    champs_adh = coord_adh["champs"]
    mapping = [
        ("nom", "nom", None, 7),
        ("prenom", "prenom", None, 7),
        ("date_naissance", "date_naissance", ti.nettoyer_date_naissance, 7),
        ("adresse", "adresse", None, 6),
        ("code_postal", "code_postal", None, 7),
        ("ville", "ville", None, 7),
        ("telephone", "telephone", ti.nettoyer_telephone, 7),
        ("email", "email", ti.nettoyer_email, 7),
        ("nationalite", "nationalite", None, 7),
        ("famille", "famille", None, 7),
    ]
    for champ_gab, champ_out, nettoyeur, psm in mapping:
        _lire_texte(img, recalage, zone_saisie(champs_adh[champ_gab], x_saisie),
                    dpi, resultat, champ_out, psm=psm, nettoyeur=nettoyeur)

    # Rattachement famille : case O/N (une croix dans la zone [255-285])
    z_ratt = champs_adh["rattachement_famille_ON"]
    rect_ratt = recalage.zone_pixels(zone_saisie(z_ratt, x_saisie), img.shape, dpi)
    cochee_ratt, ratio_ratt = ti.case_cochee(img, rect_ratt)
    resultat.set("rattachement_famille", "O" if cochee_ratt else "N",
                 0.9 if cochee_ratt else 0.7, type_champ="case")
    resultat.champs["rattachement_famille"]["ratio"] = round(ratio_ratt, 3)

    # --- Coordonnées représentant légal ---
    coord_rep = gabarit["coordonnes_representant"]
    x_saisie_rep = coord_rep["x_saisie"]
    champs_rep = coord_rep["champs"]
    for champ_gab, psm in [
        ("nom", 7), ("prenom", 7), ("date_naissance", 7), ("adresse", 6),
        ("code_postal", 7), ("ville", 7), ("telephone", 7), ("email", 7), ("nationalite", 7),
    ]:
        nettoyeur = ti.nettoyer_date_naissance if champ_gab == "date_naissance" else (
            ti.nettoyer_telephone if champ_gab == "telephone" else (
                ti.nettoyer_email if champ_gab == "email" else None))
        _lire_texte(img, recalage, zone_saisie(champs_rep[champ_gab], x_saisie_rep),
                    dpi, resultat, f"rep_{champ_gab}", psm=psm, nettoyeur=nettoyeur)

    # --- Formule (14 cases, une seule cochée) ---
    formules = gabarit["formules"]
    bornes_y = formules.get("bornes_y", formules["lignes_y"])
    choix_x = formules["choix_x"]
    rects = []
    for i, formule in enumerate(formules["formules"]):
        zone = {"x": choix_x, "y": [bornes_y[i], bornes_y[i + 1]]}
        rects.append((formule["id"], recalage.zone_pixels(zone, img.shape, dpi)))
    cochees, ratios = ti.detecter_cases_groupe(img, rects)
    ratios = {nom: round(r, 3) for nom, r in ratios.items()}
    resultat.champs["formule_brut"] = {
        "valeur": ", ".join(cochees), "confiance": 1.0 if len(cochees) == 1 else 0.3,
        "type": "case", "ratios": ratios,
    }
    if len(cochees) == 1:
        formule = next(f for f in formules["formules"] if f["id"] == cochees[0])
        resultat.set("formule", formule["nom"], 0.95, type_champ="case")
        resultat.set("formule_id", formule["id"], 0.95, type_champ="case")
        resultat.set("montant_total", formule["total"], 1.0, type_champ="montant")
    elif len(cochees) == 0:
        resultat.set("formule", "", 0.0, type_champ="case")
        resultat.ajouter_alerte("formule : aucune case cochée détectée")
    else:
        resultat.set("formule", " + ".join(cochees), 0.4, type_champ="case")
        resultat.ajouter_alerte(f"formule : {len(cochees)} cases cochées — vérifier")

    # --- Disponibilités (saisie libre, 6 jours × 2 colonnes) ---
    dispo = gabarit["disponibilites"]
    lignes_d = dispo["lignes_y"]
    for i, jour in enumerate(dispo["jours"]):
        y = [lignes_d[i] + ROGNE_SEPARATEUR_PT, lignes_d[i + 1] - ROGNE_SEPARATEUR_PT]
        ordre, _ = ti.ocr_zone(img, recalage.zone_pixels({"x": dispo["x_ordre"], "y": y}, img.shape, dpi), psm=7)
        dispo_txt, conf_d = ti.ocr_zone(img, recalage.zone_pixels({"x": dispo["x_disponibilites"], "y": y}, img.shape, dpi), psm=6)
        resultat.set(f"dispo_{jour.lower()}_ordre", ordre.strip(), 0.8 if ordre.strip() else 1.0)
        resultat.set(f"dispo_{jour.lower()}", dispo_txt, conf_d)

    # --- Moyen de paiement ---
    paie = gabarit["paiement"]
    _lire_cases(img, recalage, paie["cases"], paie["y"], dpi, resultat, "moyen_paiement")

    return resultat


def extraire_couche_bureau(texte, resultat):
    """Extrait les informations de la couche texte 'bureau' d'un PDF
    (paiement, chèques, tampons) quand la fiche elle-même est un scan.

    Reconnaît : montant total, nombre de chèques, montant par chèque,
    numéros de chèque, date de reçu, nom du club sur les chèques.
    """
    import re
    lignes = [l.strip() for l in texte.splitlines() if l.strip()]
    texte_complet = " ".join(lignes)
    # Montant total (ex: '175')
    m = re.search(r"(?<![\d.])(\d{2,4})(?![\d.])\s*(?:€|EUR)?\s*(?:$|Reçu)", texte_complet)
    # Chercher plus spécifiquement: un nombre isolé suivi de 'Reçu le'
    m_recu = re.search(r"(\d{2,4})\s*\n?\s*Reçu le (\d{2}/\d{2}/\d{4})", texte)
    if m_recu:
        resultat.set("bureau_montant_total", m_recu.group(1), 0.9, type_champ="bureau")
        resultat.set("bureau_date_recu", m_recu.group(2), 0.9, type_champ="bureau")
    # Chèques: 'N chèques de X€YY'
    m_cheques = re.search(r"(\d+)\s*chèques?\s*de\s*(\d+)\s*€\s*(\d{2})", texte_complet)
    if m_cheques:
        resultat.set("bureau_nb_cheques", m_cheques.group(1), 0.9, type_champ="bureau")
        montant = f"{m_cheques.group(2)}.{m_cheques.group(3)}"
        resultat.set("bureau_montant_cheque", montant, 0.9, type_champ="bureau")
        resultat.set("moyen_paiement", "Chèque", 0.9, type_champ="case")
    # Numéros de chèque (séquence de 7 chiffres)
    numeros = re.findall(r"\b(\d{7})\b", texte_complet)
    if numeros:
        resultat.set("bureau_numeros_cheques", ", ".join(numeros), 0.8, type_champ="bureau")
    # Nom du club sur les chèques (ligne répétée)
    clubs = re.findall(r"(CMSO\s*/\s*[A-Z\-]+)", texte_complet)
    if clubs:
        resultat.set("bureau_club_cheque", clubs[0], 0.8, type_champ="bureau")
    return resultat


MARQUEUR_FICHE = "tennis club la medullienne"


def _selectionner_page_fiche(doc):
    """Sélectionne la page contenant la fiche d'inscription.

    Règle : la première page dont l'en-tête contient "Tennis Club La
    Médullienne" (vérifié par OCR rapide de la zone d'en-tête, ou par la
    couche texte si présente). Par défaut : page 0.

    Les pages suivantes d'un PDF multi-pages sont ignorées : ce sont
    typiquement des chèques / preuves de paiement scannés en complément.
    """
    import fitz
    for pno in range(min(doc.page_count, 10)):
        page = doc[pno]
        # 1. Couche texte native (PDF rempli sur ordinateur)
        texte = page.get_text()[:500].lower()
        if MARQUEUR_FICHE in texte:
            if pno != 0:
                logger.info("Page fiche détectée en position %d (marqueur en-tête)", pno)
            return page
        # 2. Scan : OCR rapide de la zone d'en-tête (y 0-80 pt)
        try:
            clip = fitz.Rect(0, 0, page.rect.width, 80)
            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), clip=clip)
            import numpy as np
            from PIL import Image
            import io as _io
            img = np.array(Image.open(_io.BytesIO(pix.tobytes("png"))).convert("L"))
            texte_ocr, _ = ti.ocr_zone(img, (0, 0, img.shape[1], img.shape[0]), psm=6)
            if MARQUEUR_FICHE in texte_ocr.lower():
                if pno != 0:
                    logger.info("Page fiche détectée en position %d (OCR en-tête)", pno)
                return page
        except Exception:
            pass
    return doc[0]


def traiter_pdf_texte(fichier, doc, gabarit, resultat):
    """Extraction directe des champs d'un PDF rempli sur ordinateur
    (couche texte native, positions connues). Plus fiable que l'OCR image.

    On récupère les mots avec leurs positions et on les affecte aux zones
    du gabarit.
    """
    import fitz
    page = doc[0]
    mots = page.get_text("words")  # x0, y0, x1, y1, texte, ...

    intitules = {
        "nom", "prénom", "prenom", "date", "naissance", "adresse", "code", "postal",
        "ville", "téléphone", "telephone", "tel", "email", "e-mail", "nationalité",
        "nationalite", "famille", "homme", "femme", "jours", "ordre", "disponibilités",
        "disponibilites", "choix", "lundi", "mardi", "mercredi", "jeudi", "vendredi",
        "samedi", "demande", "rattachement", "ancien", "club", "licence",
    }

    def mots_dans_zone(zone, exclure_intitules=False):
        x0, y0 = zone["x"][0], zone["y"][0]
        x1, y1 = zone["x"][1], zone["y"][1]
        trouves = [m for m in mots if m[0] >= x0 - 2 and m[2] <= x1 + 2 and m[1] >= y0 - 2 and m[3] <= y1 + 2]
        if exclure_intitules:
            trouves = [m for m in trouves if m[4].strip("* :.,").lower() not in intitules]
        trouves.sort(key=lambda m: (round(m[1]), m[0]))
        return " ".join(m[4] for m in trouves)

    coord_adh = gabarit["coordonnes_adherent"]
    x_saisie = coord_adh["x_saisie"]
    champs_adh = coord_adh["champs"]
    mapping = [
        ("nom", "nom", None), ("prenom", "prenom", None),
        ("date_naissance", "date_naissance", ti.nettoyer_date_naissance),
        ("adresse", "adresse", None), ("code_postal", "code_postal", None),
        ("ville", "ville", None), ("telephone", "telephone", ti.nettoyer_telephone),
        ("email", "email", ti.nettoyer_email), ("nationalite", "nationalite", None),
        ("famille", "famille", None), ("rattachement_famille_ON", "rattachement_famille", None),
    ]
    for champ_gab, champ_out, nettoyeur in mapping:
        z = champs_adh[champ_gab]
        zone = {"x": z.get("x", x_saisie), "y": z["y"]}
        texte = mots_dans_zone(zone, exclure_intitules=(champ_gab not in ("nom", "prenom", "famille")))
        if nettoyeur:
            texte = nettoyeur(texte)
        resultat.set(champ_out, texte, 1.0 if texte else 0.0)

    coord_rep = gabarit["coordonnes_representant"]
    for champ_gab in ["nom", "prenom", "date_naissance", "adresse", "code_postal", "ville", "telephone", "email", "nationalite"]:
        z = coord_rep["champs"][champ_gab]
        zone = {"x": z.get("x", coord_rep["x_saisie"]), "y": z["y"]}
        texte = mots_dans_zone(zone, exclure_intitules=(champ_gab not in ("nom", "prenom")))
        resultat.set(f"rep_{champ_gab}", texte, 1.0 if texte else 0.0)

    # Disponibilités
    dispo = gabarit["disponibilites"]
    lignes_d = dispo["lignes_y"]
    for i, jour in enumerate(dispo["jours"]):
        y = [lignes_d[i], lignes_d[i + 1]]
        ordre = mots_dans_zone({"x": dispo["x_ordre"], "y": y}, exclure_intitules=True)
        dispo_txt = mots_dans_zone({"x": dispo["x_disponibilites"], "y": y}, exclure_intitules=True)
        resultat.set(f"dispo_{jour.lower()}_ordre", ordre, 1.0 if ordre else 0.0)
        resultat.set(f"dispo_{jour.lower()}", dispo_txt, 1.0 if dispo_txt else 0.0)

    # Note : formule et cases à cocher ne sont pas dans la couche texte d'un
    # PDF rempli via formulaire — à compléter selon le remplissage réel.
    resultat.ajouter_alerte("PDF texte : formule et paiement à vérifier (non extraits de la couche texte)")
    return resultat


# ---------------------------------------------------------------------------
# Export ODS de revue
# ---------------------------------------------------------------------------

COLONNES_REVUE = [
    "Fichier", "Nom", "Prénom", "Date naissance", "Sexe", "Téléphone", "Email",
    "Adresse", "Code postal", "Ville", "Nationalité", "Famille",
    "Rep. Nom", "Rep. Prénom", "Rep. Téléphone", "Rep. Email",
    "Formule", "Montant total (€)",
    "Dispo Lundi", "Dispo Mardi", "Dispo Mercredi", "Dispo Jeudi", "Dispo Vendredi", "Dispo Samedi",
    "Moyen paiement", "Montant bureau", "Date reçu", "N° chèques",
    "Confiance globale", "Alertes", "Statut revue", "Commentaire",
]


def exporter_revue_ods(resultats, chemin_sortie):
    """Écrit un ODS de revue : une ligne par fiche, champs extraits + confiance +
    colonne 'Statut revue' (À vérifier / Validé) laissée au bureau."""
    import ezodf
    doc = ezodf.newdoc(doctype="ods", filename=chemin_sortie)
    # ezodf: size=(lignes, colonnes) et sheet[ligne, colonne]
    sheet = ezodf.Sheet("Revue_inscriptions", size=(len(resultats) + 1, len(COLONNES_REVUE)))
    doc.sheets += sheet
    for j, col in enumerate(COLONNES_REVUE):
        sheet[0, j].set_value(col)
    for i, res in enumerate(resultats, start=1):
        c = res.champs

        def val(champ):
            return c.get(champ, {}).get("valeur", "")

        ligne = [
            os.path.basename(res.fichier), val("nom"), val("prenom"), val("date_naissance"),
            val("sexe_adherent"), val("telephone"), val("email"), val("adresse"),
            val("code_postal"), val("ville"), val("nationalite"), val("famille"),
            val("rep_nom"), val("rep_prenom"), val("rep_telephone"), val("rep_email"),
            val("formule"), val("montant_total"),
            val("dispo_lundi"), val("dispo_mardi"), val("dispo_mercredi"),
            val("dispo_jeudi"), val("dispo_vendredi"), val("dispo_samedi"),
            val("moyen_paiement"),
            val("bureau_montant_total"), val("bureau_date_recu"), val("bureau_numeros_cheques"),
            f"{res.score_global():.0%}",
            "; ".join(res.alertes) if res.alertes else "",
            "À vérifier" if res.alertes else "",
            "",
        ]
        for j, v in enumerate(ligne):
            sheet[i, j].set_value(str(v) if v is not None else "")
    doc.save()
    logger.info("ODS de revue écrit : %s (%d fiches)", chemin_sortie, len(resultats))


def exporter_json(resultats, chemin_sortie):
    with open(chemin_sortie, "w", encoding="utf-8") as f:
        json.dump([r.en_dict() for r in resultats], f, ensure_ascii=False, indent=2)
    logger.info("JSON écrit : %s", chemin_sortie)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def lister_fiches(dossier):
    exts = (".pdf", ".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".webp")
    fichiers = []
    for f in sorted(os.listdir(dossier)):
        if f.lower().endswith(exts) and not f.startswith("."):
            fichiers.append(os.path.join(dossier, f))
    return fichiers


def main():
    parser = argparse.ArgumentParser(description="OCR des fiches d'inscription TCLM")
    parser.add_argument("--fichier", help="Une fiche unique (PDF ou image)")
    parser.add_argument("--dossier", help="Dossier de fiches à traiter")
    parser.add_argument("--gabarit", default=GABARIT_DEFAUT, help="Gabarit de zones (JSON)")
    parser.add_argument("--sortie", default="revue_inscriptions.ods", help="Fichier ODS de sortie")
    parser.add_argument("--json", action="store_true", help="Exporter aussi un JSON détaillé")
    parser.add_argument("--test", action="store_true", help="Ne traiter que les 5 premières fiches")
    parser.add_argument("--seuil-confiance", type=float, default=0.7,
                        help="Seuil de confiance pour alerte (défaut 0.7)")
    args = parser.parse_args()

    configurer_logging()
    gabarit = charger_gabarit(args.gabarit)

    if args.fichier:
        fichiers = [args.fichier]
    elif args.dossier:
        fichiers = lister_fiches(args.dossier)
        if args.test:
            fichiers = fichiers[:5]
    else:
        parser.error("--fichier ou --dossier requis")

    if not fichiers:
        logger.error("Aucune fiche trouvée")
        sys.exit(1)

    logger.info("Traitement de %d fiche(s)", len(fichiers))
    resultats = []
    for i, f in enumerate(fichiers, 1):
        logger.info("[%d/%d] %s", i, len(fichiers), os.path.basename(f))
        try:
            res = traiter_fiche(f, gabarit)
        except Exception as e:  # noqa: BLE001 — on continue sur les autres fiches
            logger.exception("Erreur sur %s", f)
            res = ResultatFiche(f)
            res.erreurs.append(str(e))
            res.ajouter_alerte(f"ERREUR traitement : {e}")
        resultats.append(res)
        logger.info("  -> score %.0f%%, %d alerte(s)", res.score_global() * 100, len(res.alertes))

    exporter_revue_ods(resultats, args.sortie)
    if args.json:
        exporter_json(resultats, os.path.splitext(args.sortie)[0] + ".json")

    # Synthèse
    nb_alertes = sum(1 for r in resultats if r.alertes)
    nb_erreurs = sum(1 for r in resultats if r.erreurs)
    logger.info("=== Synthèse : %d fiches, %d avec alertes, %d en erreur ===",
                len(resultats), nb_alertes, nb_erreurs)
    for r in resultats:
        if r.alertes:
            logger.info("  %s : %s", os.path.basename(r.fichier), "; ".join(r.alertes))


if __name__ == "__main__":
    main()
