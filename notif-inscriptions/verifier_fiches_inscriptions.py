import argparse
import difflib
import logging
import os
import re
import sys
import unicodedata

import ezodf

SOURCE_FILE = r"P:/2026-2027/Adhérents/gestion_adherents_2026-2027.ods"
ATTACHMENTS_DIR = r"P:/2026-2027/Adhérents/Fiches_inscriptions"
PREFIX_FICHE = "Inscription_2026"
MAX_ADHERENTS = 500
RAPPORT_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "rapport_verification_fiches_{horodatage}.txt",
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


# --- FONCTIONS DE NORMALISATION (identiques à script_envoi_email_inscription.py) ---

def remove_accents(input_str):
    if not input_str:
        return ""
    nfkd_form = unicodedata.normalize("NFKD", str(input_str))
    return "".join([c for c in nfkd_form if not unicodedata.combining(c)])


def normalize_name(nom, prenom, prefix=PREFIX_FICHE):
    nom = nom.strip()
    nom = remove_accents(nom)
    nom = nom.replace(" ", "-").upper()
    prenom = prenom.strip()
    prenom = remove_accents(prenom)
    prenom_parts = prenom.split()
    prenom_normalized = "-".join([part.capitalize() for part in prenom_parts])
    return f"{prefix}_{nom}_{prenom_normalized}.pdf"


def cle_normale(nom, prenom):
    """Clé de comparaison insensible à la casse, accents et séparateurs."""
    def canon(s):
        s = remove_accents(str(s)).lower()
        s = re.sub(r"[\s'\-]+", " ", s).strip()
        return s
    return f"{canon(nom)}|{canon(prenom)}"


# --- LECTURE DE L'ODS (même logique de détection que le script d'envoi) ---

def lire_adherents(ods_file):
    wb = ezodf.opendoc(ods_file)
    ws = wb.sheets["Liste_adherents"]

    nom_pos = None
    for row in range(10):
        for col in range(50):
            cell_val = ws[col, row].value
            if cell_val is not None and str(cell_val).strip() == "NOM":
                nom_pos = (col, row)
                break
        if nom_pos:
            break
    if not nom_pos:
        raise ValueError("❌ En-tête 'NOM' introuvable dans 'Liste_adherents'")

    col_nom, row_nom = nom_pos
    is_transposed = False
    if col_nom + 1 < 50 and str(ws[col_nom + 1, row_nom].value or "").strip() == "PRENOM":
        logger.info("📊 Structure détectée : NORMALE (lignes = adhérents)")
    elif str(ws[col_nom, row_nom + 1].value or "").strip() == "PRENOM":
        logger.info("📊 Structure détectée : TRANSPOSÉE (colonnes = adhérents)")
        is_transposed = True
    else:
        raise ValueError("❌ Structure non reconnue (PRENOM pas à côté de NOM)")

    prenoms_col = col_nom + 1 if not is_transposed else col_nom
    prenoms_row = row_nom if not is_transposed else row_nom + 1

    adherents = []
    if not is_transposed:
        for row in range(row_nom + 1, MAX_ADHERENTS):
            nom = ws[col_nom, row].value
            prenom = ws[prenoms_col, row].value
            if nom is None or str(nom).strip() == "":
                break
            adherents.append(
                (str(nom).strip(), str(prenom).strip() if prenom else "", row + 1)
            )
    else:
        for col in range(col_nom + 1, MAX_ADHERENTS):
            nom = ws[col, row_nom].value
            prenom = ws[col, prenoms_row].value
            if nom is None or str(nom).strip() == "":
                break
            adherents.append(
                (str(nom).strip(), str(prenom).strip() if prenom else "", col + 1)
            )

    logger.info(f"✅ {len(adherents)} adhérents lus dans l'ODS")
    return adherents


# --- LECTURE DES FICHES PDF DU DOSSIER ---

def parse_nom_fichier(filename):
    """Extrait (nom, prenom) d'un nom de fichier normalisé, sinon None."""
    base = os.path.splitext(filename)[0]
    reste = re.sub(rf"^{re.escape(PREFIX_FICHE)}_", "", base, flags=re.IGNORECASE)
    if "_" in reste:
        nom, prenom = reste.split("_", 1)
    elif "-" in reste:
        nom, prenom = reste.split("-", 1)
    else:
        return None
    return nom, prenom


def lire_fiches(directory):
    fiches = []
    for filename in sorted(os.listdir(directory)):
        if not filename.lower().endswith(".pdf"):
            continue
        fiches.append(filename)
    return fiches


# --- VÉRIFICATION ---

def verifier(adherents, fiches):
    fiches_par_cle = {}
    fiches_non_parsees = []
    for f in fiches:
        parsed = parse_nom_fichier(f)
        if parsed is None:
            fiches_non_parsees.append(f)
            continue
        fiches_par_cle.setdefault(cle_normale(*parsed), []).append(f)

    adherents_par_cle = {}
    for nom, prenom, ligne in adherents:
        adherents_par_cle.setdefault(cle_normale(nom, prenom), []).append((nom, prenom, ligne))

    # 1. Adhérents de l'ODS sans fiche correspondante
    sans_fiche = []
    correspondances_approx = []
    noms_fiches_cles = list(fiches_par_cle.keys())
    for nom, prenom, ligne in adherents:
        cle = cle_normale(nom, prenom)
        attendu = normalize_name(nom, prenom)
        if cle in fiches_par_cle:
            continue
        # Recherche approximative : nom seul, ou inversion nom/prénom
        a_nom, a_prenom = cle.split("|")
        candidats = []
        for f_cle, fichiers in fiches_par_cle.items():
            f_nom, f_prenom = f_cle.split("|")
            inversion = f_nom == a_prenom and f_prenom == a_nom
            prenom_proche = (
                f_nom == a_nom
                and difflib.SequenceMatcher(None, f_prenom, a_prenom).ratio() >= 0.6
            )
            if inversion or prenom_proche:
                candidats.extend(fichiers)
        if candidats:
            correspondances_approx.append((nom, prenom, ligne, attendu, candidats))
        else:
            sans_fiche.append((nom, prenom, ligne, attendu))

    # 2. Fiches PDF sans ligne correspondante dans l'ODS
    fiches_sans_adherent = []
    for cle, fichiers in fiches_par_cle.items():
        if cle not in adherents_par_cle:
            fiches_sans_adherent.append(fichiers)

    return {
        "sans_fiche": sans_fiche,
        "correspondances_approx": correspondances_approx,
        "fiches_sans_adherent": fiches_sans_adherent,
        "fiches_non_parsees": fiches_non_parsees,
    }


def afficher_rapport(resultats, adherents, fiches, sortie):
    w = sortie.write
    w("=" * 70 + "\n")
    w("VÉRIFICATION FICHES D'INSCRIPTION vs ODS ADHÉRENTS\n")
    w("=" * 70 + "\n")
    w(f"Adhérents dans l'ODS      : {len(adherents)}\n")
    w(f"Fiches PDF dans le dossier : {len(fiches)}\n\n")

    w(f"--- Adhérents SANS fiche PDF ({len(resultats['sans_fiche'])}) ---\n")
    if resultats["sans_fiche"]:
        for nom, prenom, ligne, attendu in resultats["sans_fiche"]:
            w(f"  ❌ Ligne {ligne} : {nom} {prenom} — attendu : {attendu}\n")
    else:
        w("  ✅ Aucun — tous les adhérents ont leur fiche\n")
    w("\n")

    w(f"--- Correspondances approximatives à vérifier ({len(resultats['correspondances_approx'])}) ---\n")
    if resultats["correspondances_approx"]:
        for nom, prenom, ligne, attendu, candidats in resultats["correspondances_approx"]:
            w(f"  ⚠️ Ligne {ligne} : {nom} {prenom} — attendu : {attendu}\n")
            for c in candidats:
                w(f"      → fiche proche trouvée : {c}\n")
    else:
        w("  ✅ Aucune ambiguïté\n")
    w("\n")

    w(f"--- Fiches PDF SANS adhérent dans l'ODS ({len(resultats['fiches_sans_adherent'])}) ---\n")
    if resultats["fiches_sans_adherent"]:
        for fichiers in resultats["fiches_sans_adherent"]:
            for f in fichiers:
                w(f"  ❌ {f}\n")
    else:
        w("  ✅ Aucune — toutes les fiches correspondent à un adhérent\n")
    w("\n")

    w(f"--- Fiches au nommage non reconnu ({len(resultats['fiches_non_parsees'])}) ---\n")
    if resultats["fiches_non_parsees"]:
        for f in resultats["fiches_non_parsees"]:
            w(f"  ⚠️ {f}\n")
    else:
        w("  ✅ Toutes les fiches respectent le nommage normalisé\n")


def main():
    parser = argparse.ArgumentParser(
        description="Vérifier la complétude de l'ODS des adhérents par rapport aux fiches d'inscription PDF."
    )
    parser.add_argument("--ods", default=SOURCE_FILE, help="Chemin du fichier .ods des adhérents.")
    parser.add_argument("--fiches", default=ATTACHMENTS_DIR, help="Dossier des fiches d'inscription PDF.")
    args = parser.parse_args()

    if not os.path.exists(args.ods):
        raise SystemExit(f"❌ Fichier ODS introuvable : {args.ods}")
    if not os.path.isdir(args.fiches):
        raise SystemExit(f"❌ Dossier des fiches introuvable : {args.fiches}")

    logger.info(f"📖 Lecture de l'ODS : {args.ods}")
    adherents = lire_adherents(args.ods)
    fiches = lire_fiches(args.fiches)
    logger.info(f"📁 {len(fiches)} fiches PDF trouvées dans {args.fiches}")

    resultats = verifier(adherents, fiches)

    horodatage = __import__("datetime").datetime.now().strftime("%Y%m%d_%H%M%S")
    rapport_path = RAPPORT_FILE.format(horodatage=horodatage)
    with open(rapport_path, "w", encoding="utf-8") as sortie:
        afficher_rapport(resultats, adherents, fiches, sortie)
    with open(rapport_path, encoding="utf-8") as sortie:
        print(sortie.read())
    print(f"📄 Rapport écrit : {rapport_path}")

    if resultats["sans_fiche"] or resultats["fiches_sans_adherent"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
