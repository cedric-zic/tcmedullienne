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
        page = doc[0]
        # Si le PDF a une couche texte (fiche remplie sur ordinateur), on
        # l'utilise directement : c'est plus fiable que l'OCR image.
        couche_texte = page.get_text().strip()
        if len(couche_texte) > 200:
            logger.info("%s : PDF avec couche texte détectée, extraction directe", os.path.basename(fichier))
            return traiter_pdf_texte(fichier, doc, gabarit, resultat)
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

    # --- Recalage gabarit ↔ scan ---
    recalage = ti.estimer_recalage(img, gabarit, dpi)
    if recalage.fiabilite < 0.3:
        resultat.ajouter_alerte(
            f"Recalage faible (fiabilité {recalage.fiabilite:.0%}) — fiche à vérifier visuellement"
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
    lignes_y = formules["lignes_y"]
    choix_x = formules["choix_x"]
    rects = []
    for i, formule in enumerate(formules["formules"]):
        zone = {"x": choix_x, "y": [lignes_y[i], lignes_y[i + 1]]}
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
    "Moyen paiement", "Confiance globale", "Alertes", "Statut revue", "Commentaire",
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
