# -*- coding: utf-8 -*-
"""
rapprochement.py — Rapproche une fiche OCRisée avec la liste des adhérents
connus (réinscriptions) et l'extraction de coordonnées fournie par le bureau.

Le rapprochement est flou (nom/prénom/date de naissance) et ne JAMAIS ne
modifie les données : il propose des correspondances avec un score, à valider
par le bureau. Utilisé pour :
- détecter une réinscription (pré-remplir, ne lire que Nom/Prénom/Date/Email) ;
- signaler les homonymes ;
- comparer le traitement OCR avec l'extraction manuelle (mesure de qualité).

Usage :
    python rapprochement.py --revue revue_inscriptions.ods --adherents adherents.csv --sortie rapproche.ods
"""

import argparse
import csv
import json
import logging
import os
import re
import unicodedata
from datetime import datetime

logger = logging.getLogger("rapprochement")


def normaliser(texte):
    """Normalise un nom/prénom : sans accents, minuscules, sans ponctuation."""
    if not texte:
        return ""
    t = unicodedata.normalize("NFD", str(texte))
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    t = re.sub(r"[^a-zA-Z0-9 ]", " ", t.lower())
    return " ".join(t.split())


def distance_levenshtein(a, b):
    """Distance de Levenshtein entre deux chaînes normalisées."""
    if a == b:
        return 0
    if not a or not b:
        return max(len(a), len(b))
    precedent = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        courant = [i]
        for j, cb in enumerate(b, 1):
            courant.append(min(
                precedent[j] + 1,        # suppression
                courant[j - 1] + 1,      # insertion
                precedent[j - 1] + (ca != cb),  # substitution
            ))
        precedent = courant
    return precedent[-1]


def similarite(a, b):
    """Similarité 0..1 entre deux chaînes (1 - distance normalisée)."""
    a, b = normaliser(a), normaliser(b)
    if not a or not b:
        return 0.0
    d = distance_levenshtein(a, b)
    return 1.0 - d / max(len(a), len(b))


def normaliser_date(texte):
    """Normalise une date en JJ/MM/AAAA. Retourne '' si illisible."""
    if not texte:
        return ""
    t = re.sub(r"[^0-9]", "", str(texte))
    if len(t) == 8:
        # Essayer JJMMYYYY puis MMAAJJ etc.
        return f"{t[0:2]}/{t[2:4]}/{t[4:8]}"
    return str(texte).strip()


def score_correspondance(fiche, adherent):
    """Score de correspondance 0..1 entre une fiche OCR et un adhérent connu.

    Pondération : nom 0.4, prénom 0.4, date de naissance 0.2.
    """
    s_nom = similarite(fiche.get("nom", ""), adherent.get("nom", ""))
    s_prenom = similarite(fiche.get("prenom", ""), adherent.get("prenom", ""))
    d_fiche = normaliser_date(fiche.get("date_naissance", ""))
    d_adh = normaliser_date(adherent.get("date_naissance", ""))
    s_date = 1.0 if (d_fiche and d_adh and d_fiche == d_adh) else 0.0
    return 0.4 * s_nom + 0.4 * s_prenom + 0.2 * s_date


def charger_adherents_csv(chemin):
    """Charge un CSV d'adhérents. Colonnes attendues (flexible) :
    nom, prenom, date_naissance (ou naissance, ddn), email, telephone.
    """
    adherents = []
    with open(chemin, encoding="utf-8-sig", newline="") as f:
        lecteur = csv.DictReader(f)
        # Normaliser les noms de colonnes
        for ligne in lecteur:
            ligne_norm = {normaliser(k): v for k, v in ligne.items() if k}
            adherents.append({
                "nom": ligne_norm.get("nom", "") or ligne_norm.get("name", ""),
                "prenom": ligne_norm.get("prenom", "") or ligne_norm.get("prénom", ""),
                "date_naissance": (ligne_norm.get("date de naissance", "")
                                   or ligne_norm.get("naissance", "")
                                   or ligne_norm.get("ddn", "")),
                "email": ligne_norm.get("email", "") or ligne_norm.get("e-mail", ""),
                "telephone": ligne_norm.get("telephone", "") or ligne_norm.get("téléphone", ""),
            })
    return adherents


def rapprocher(fiche_champs, adherents, seuil=0.75):
    """Retourne les meilleures correspondances pour une fiche.

    Retourne une liste de dicts {adherent, score} triée par score décroissant,
    filtrée au-dessus du seuil.
    """
    fiche = {k: v.get("valeur", "") for k, v in fiche_champs.items()}
    scores = []
    for adh in adherents:
        s = score_correspondance(fiche, adh)
        if s >= seuil:
            scores.append({"adherent": adh, "score": round(s, 3)})
    scores.sort(key=lambda x: x["score"], reverse=True)
    return scores


def main():
    parser = argparse.ArgumentParser(description="Rapprochement fiches OCR / adhérents connus")
    parser.add_argument("--revue", required=True, help="ODS ou JSON de revue généré par pipeline_ocr")
    parser.add_argument("--adherents", required=True, help="CSV d'extraction des coordonnées adhérents")
    parser.add_argument("--sortie", default="rapprochement.ods", help="Fichier de sortie")
    parser.add_argument("--seuil", type=float, default=0.75, help="Seuil de correspondance (défaut 0.75)")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    # Charger les fiches traitées
    ext = os.path.splitext(args.revue)[1].lower()
    if ext == ".json":
        with open(args.revue, encoding="utf-8") as f:
            fiches = json.load(f)
    else:
        # ODS : lire la feuille de revue
        import ezodf
        doc = ezodf.opendoc(args.revue)
        sheet = doc.sheets[0]
        rows = list(sheet.rows())
        headers = [c.value for c in rows[0]]
        fiches = []
        for row in rows[1:]:
            valeurs = [c.value for c in row]
            champs = {}
            for h, v in zip(headers, valeurs):
                champs[normaliser(h)] = {"valeur": v or ""}
            fiches.append({"fichier": valeurs[0], "champs": champs})

    adherents = charger_adherents_csv(args.adherents)
    logger.info("%d fiches à rapprocher, %d adhérents connus", len(fiches), len(adherents))

    resultats = []
    for fiche in fiches:
        correspondances = rapprocher(fiche["champs"], adherents, args.seuil)
        resultats.append({
            "fichier": fiche.get("fichier", ""),
            "correspondances": correspondances,
            "statut": (
                "Réinscription probable" if len(correspondances) == 1 and correspondances[0]["score"] > 0.9
                else "Homonyme — vérifier" if len(correspondances) > 1
                else "Nouvel adhérent" if not correspondances
                else "Correspondance faible"
            ),
        })
        logger.info("  %s -> %s", fiche.get("fichier", "?"), resultats[-1]["statut"])

    # Export JSON (intermédiaire) + ODS de synthèse
    with open(os.path.splitext(args.sortie)[0] + ".json", "w", encoding="utf-8") as f:
        json.dump(resultats, f, ensure_ascii=False, indent=2, default=str)

    import ezodf
    doc = ezodf.newdoc(doctype="ods", filename=args.sortie)
    cols = ["Fichier", "Nom OCR", "Prénom OCR", "Statut", "Meilleure correspondance", "Score", "Nom connu", "Prénom connu"]
    sheet = ezodf.Sheet("Rapprochement", size=(len(resultats) + 1, len(cols)))
    doc.sheets += sheet
    for j, c in enumerate(cols):
        sheet[0, j].set_value(c)
    for i, r in enumerate(resultats, 1):
        ch = r.get("correspondances", [])
        meilleure = ch[0] if ch else None
        nom_ocr = fiche.get("champs", {}).get("nom", {}).get("valeur", "") if False else ""
        ligne = [
            r["fichier"],
            "",  # nom OCR — à compléter depuis la revue si besoin
            "",
            r["statut"],
            f"{meilleure['adherent']['nom']} {meilleure['adherent']['prenom']}" if meilleure else "",
            meilleure["score"] if meilleure else "",
            meilleure["adherent"]["nom"] if meilleure else "",
            meilleure["adherent"]["prenom"] if meilleure else "",
        ]
        for j, v in enumerate(ligne):
            sheet[i, j].set_value(str(v))
    doc.save()
    logger.info("Rapport de rapprochement : %s", args.sortie)


if __name__ == "__main__":
    main()
