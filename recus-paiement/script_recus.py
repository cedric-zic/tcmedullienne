import ezodf
import hashlib
import hmac
import locale
import logging
import os
import shutil
import smtplib
import sys
from datetime import date, datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from email.utils import formataddr
from docx import Document
from docx.shared import Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH

try:
    from cles_authenticite import calculer_cle
except ImportError:
    raise SystemExit(
        "❌ Fichier 'cles_authenticite.py' introuvable.\n"
        "Copiez 'cles_authenticite.py.example' en 'cles_authenticite.py' "
        "et renseignez les clés par saison.\n"
        "Ce fichier est exclu par le .gitignore : ne le commitez jamais."
    )

try:
    from secrets_local import (
        SMTP_SERVER,
        SMTP_PORT,
        SMTP_USER,
        SMTP_PASSWORD,
    )
except ImportError:
    raise SystemExit(
        "❌ Fichier 'secrets_local.py' introuvable.\n"
        "Créez-le à côté du script avec :\n"
        "  SMTP_SERVER = \"smtp.gmail.com\"\n"
        "  SMTP_PORT = 587\n"
        "  SMTP_USER = \"...\"\n"
        "  SMTP_PASSWORD = \"...\"\n"
        "Et ajoutez 'secrets_local.py' dans .gitignore."
    )

# --- CONFIGURATION ---
WORK_DIR = "P:/2026-2027/Adhérents/"
FICHIER_SOURCE = "gestion_adherents_2026-2027.ods"
TEMPLATE_FACTURE = "Modele_doc/Modele_recu_paiement_2026.docx"
EXPORT_DIR = "Recu_paiements/"
SIGNATURE_IMG = "Modele_doc/signature_cedric.jpg"

# Colonnes de la feuille Liste_adherents (index 0-based, données ligne 8)
COL_NOM = 0          # A
COL_PRENOM = 1        # B
COL_FORMULE = 6       # G
COL_EMAIL = 3         # D
COL_DEMANDE_RECU = 23  # X : demandé / encours / traité
COL_MONTANT = 25      # Z
HEADER_ROW = 7        # ligne des en-têtes (index 0-based)
DATA_START_ROW = 7    # première ligne de données (index 0-based)

INTER_EMAIL_DELAY = 45  # secondes entre chaque envoi
LIMIT_PER_DAY = 15       # limite d'envois par lancement
STATUT_DEMANDE = "demandé"
STATUT_ENCOURS = "encours"
STATUT_TRAITE = "traité"

# --- LOGS ---
LOG_DIR = "logs"
LOG_FILE = os.path.join(LOG_DIR, f"envoi_recus_{datetime.now().strftime('%Y%m%d')}.log")
os.makedirs(LOG_DIR, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE, encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# --- MODELE DE MAIL ---
SUJET_MAIL = "TC La Médullienne - Votre reçu de paiement saison {saison}"

CORPS_MAIL = (
    "Bonjour {prenom},\n"
    "\n"
    "Vous trouverez en pièce jointe votre reçu de paiement pour la saison {saison}. "
    "Cet envoi fait suite à votre demande.\n"
    "{contenu_formule}"
    "\n"
    "Si vous avez besoin d'un complément ou d'une correction, n'hésitez pas à nous "
    "répondre, nous restons à votre disposition.\n"
    "\n"
    "Bien sportivement,\n"
    "Cédric Meschin\n"
    "Secrétaire - TC La Médullienne"
)

# Feuille de correspondance formule -> elements de contenu (phase 2).
# Structure (proposition A) : une ligne par formule,
#   colonne A = nom de la formule (identique a la colonne G de Liste_adherents),
#   colonnes B, C, D, E, F = elements inclus dans la cotisation (2 a 5 par formule).
# Le mail insere : "Cette cotisation inclut : <elem1>, <elem2> et <elem3>."
# Formule absente de la feuille -> paragraphe omis (mail generique phase 1).
FEUILLE_TEXTES_FORMULES = "Textes_formules"
TEXTE_INTRO_CONTENU = "Cette cotisation inclut : "


def generer_id_authenticite(nom, prenom, date_recu, montant, saison, timestamp):
    """
    Génère l'ID d'authenticité d'un reçu.

    Format : AAAAMMJJ.TTTTTTTTTT.<signature>
    - AAAAMMJJ : date du reçu
    - TTTTTTTTTT : timestamp de génération
    - signature : HMAC-SHA256 tronqué, calculé sur
      nom|prénom|date|montant|saison|timestamp avec la clé locale
      de la saison correspondante.
      Toute modification d'un seul caractère (ID, nom, prénom, date,
      montant ou saison) invalide la signature.
    """
    cle = calculer_cle(saison)
    message = f"{nom.upper()}|{prenom.upper()}|{date_recu}|{montant}|{saison}|{timestamp}".encode()
    signature = hmac.new(cle, message, hashlib.sha256).hexdigest()[:16]
    return f"{date_recu}.{timestamp}.{signature}"


def ods_path():
    return os.path.join(WORK_DIR, FICHIER_SOURCE)


def sauvegarde_ods():
    """Copie de sécurité de l'ODS avant modification (une par jour)."""
    src = ods_path()
    horodatage = datetime.now().strftime("%Y%m%d")
    dst = os.path.join(WORK_DIR, f"sauvegarde_{FICHIER_SOURCE}.{horodatage}.bak")
    if not os.path.exists(dst):
        shutil.copy2(src, dst)
        logger.info(f"Sauvegarde de sécurité créée : {dst}")
    else:
        logger.info(f"Sauvegarde du jour déjà présente : {dst}")


def maj_statut_recu(ligne, statut):
    """
    Met à jour la colonne X de la ligne donnée (index 0-based de la feuille,
    en-têtes ligne 8 => DATA_START_ROW) dans l'ODS, via ezodf
    (préserve la mise en forme du fichier).
    """
    doc = ezodf.opendoc(ods_path())
    feuille = doc.sheets[0]  # Liste_adherents est la première feuille
    cellule = feuille[COL_DEMANDE_RECU, ligne]
    cellule.set_value(statut)
    doc.save()
    logger.info(f"Ligne {ligne + 1} : statut demande reçu -> {statut}")


def lire_lignes_ods():
    """
    Retourne la liste des adhérents pertinents de l'ODS :
    (ligne_ods, nom, prenom, formule, email, statut_recu, montant)
    où ligne_ods est l'index de ligne ezodf (0-based) pour réécriture.
    """
    doc = ezodf.opendoc(ods_path())
    feuille = doc.sheets[0]
    resultats = []
    for idx in range(DATA_START_ROW, feuille.nrows()):
        nom = str(feuille[COL_NOM, idx].value or "").strip()
        if not nom:
            continue
        prenom = str(feuille[COL_PRENOM, idx].value or "").strip()
        formule = str(feuille[COL_FORMULE, idx].value or "").strip()
        email = str(feuille[COL_EMAIL, idx].value or "").strip()
        statut = str(feuille[COL_DEMANDE_RECU, idx].value or "").strip().lower()
        montant = feuille[COL_MONTANT, idx].value
        try:
            montant = int(round(float(montant))) if montant not in (None, "") else 0
        except (TypeError, ValueError):
            montant = 0
        resultats.append((idx, nom, prenom, formule, email, statut, montant))
    return resultats


def generer_recus(mode_test=False):
    """Génère les PDF pour les adhérents X='demandé' puis passe X à 'encours'."""
    locale.setlocale(locale.LC_TIME, 'fr_FR.UTF-8')
    today = datetime.now()
    long_date = today.strftime("%A %d %B %Y")
    currentYear = date.today().year
    sportiveYear = f"{currentYear}/{currentYear + 1}"
    date_recu = today.strftime("%Y%m%d")

    lignes = lire_lignes_ods()
    a_generer = [l for l in lignes if l[5] == STATUT_DEMANDE and l[6] > 0]

    if not a_generer:
        print("Aucun reçu à générer (aucune ligne avec 'demandé' et montant valide).")
        return

    print(f"\n{len(a_generer)} reçu(s) à générer :\n")
    print(f"{'Nom':<20} {'Prénom':<15} {'Montant':<8}")
    print("-" * 45)
    for (_, nom, prenom, _, _, _, montant) in a_generer:
        print(f"{nom:<20} {prenom:<15} {montant}€")
    print()

    if not mode_test:
        reponse = input("Générer ces reçus (PDF) ? (O/n) : ").strip().lower()
        if reponse == "n":
            print("Génération annulée.")
            return
        sauvegarde_ods()

    for (idx, nom, prenom, formule, email, _, montant) in a_generer:
        document = Document(os.path.join(WORK_DIR, TEMPLATE_FACTURE))
        style = document.styles['Normal']
        font = style.font
        font.name = 'Calibri'
        font.size = Pt(14)

        timestamp = int(datetime.now().timestamp())
        unique_id = generer_id_authenticite(nom, prenom, date_recu, str(montant), sportiveYear, timestamp)

        document.add_paragraph("")
        document.add_paragraph("")
        document.add_paragraph("")
        document.add_paragraph("")

        p = document.add_paragraph("Castelnau de médoc le {}.".format(long_date))
        last_paragraph = document.paragraphs[-1]
        last_paragraph.alignment = WD_ALIGN_PARAGRAPH.RIGHT

        document.add_paragraph("")
        document.add_paragraph("Reçu pour paiement de cotisation saison sportive {}".format(sportiveYear), style='TOC Heading')
        document.add_paragraph("")
        document.add_paragraph("")
        document.add_paragraph("")

        document.add_paragraph(f"Nous confirmons que {prenom} {nom} est inscrit(e) au Tennis Club La Médullienne pour la saison tennistique {sportiveYear} avec la formule "
                              f"{formule}. La cotisation d'un montant total de {montant}€ a bien été acquittée. Celle-ci inclue: ")
        document.add_paragraph("    - l'adhésion au club")
        document.add_paragraph("    - la licence FFT multi-raquettes")
        document.add_paragraph("    - la réservation gratuite des terrains en illimité")
        document.add_paragraph("    - les cours avec un professeur diplômé, pour les enfants.")

        document.add_paragraph("")
        document.add_paragraph("Fait pour valoir ce que de droit.")
        document.add_paragraph("")
        document.add_paragraph("")

        last_paragraph = document.paragraphs[-1]
        last_paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER

        p = document.add_paragraph("Le secrétaire", style='Caption')
        p.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        p = document.add_paragraph("Cédric Meschin", style='Caption')
        p.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        document.add_picture(os.path.join(WORK_DIR, SIGNATURE_IMG))
        last_paragraph = document.paragraphs[-1]
        last_paragraph.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        p = document.add_paragraph(f"ID d'authentification: {unique_id}")
        p.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        for run in p.runs:
            run.font.size = Pt(6)
            run.font.color.rgb = RGBColor(201, 201, 201)

        filename_docx = f"TCLM_Recu_paiement_{nom}_{prenom}.docx"
        word_path = os.path.join(WORK_DIR, EXPORT_DIR, filename_docx)

        try:
            document.save(word_path)
            print(f"Reçu Word généré pour {prenom} {nom} avec ID : {unique_id}")

            if not mode_test:
                from docx2pdf import convert
                pdf_path = os.path.join(WORK_DIR, EXPORT_DIR, f"TCLM_Recu_paiement_{nom}_{prenom}.pdf")
                convert(word_path, pdf_path)
                print(f"Reçu PDF généré pour {prenom} {nom}")
                maj_statut_recu(idx, STATUT_ENCOURS)
        except PermissionError:
            print(f"Erreur : Impossible d'enregistrer {filename_docx}. Il est peut-être ouvert.")
        except Exception as e:
            print(f"Erreur pour {prenom} {nom} : {e}")


def charger_textes_formules():
    """
    Charge la feuille Textes_formules de l'ODS.

    Retourne {formule: [elements...]} ou un dict vide si la feuille
    n'existe pas encore (mail generique).
    """
    doc = ezodf.opendoc(ods_path())
    noms_feuilles = [s.name for s in doc.sheets]
    if FEUILLE_TEXTES_FORMULES not in noms_feuilles:
        logger.info(f"Feuille '{FEUILLE_TEXTES_FORMULES}' absente : contenu par formule desactive.")
        return {}
    feuille = doc.sheets[FEUILLE_TEXTES_FORMULES]
    correspondance = {}
    # Ignorer une eventuelle ligne d'en-tetes (ligne 1)
    premiere_ligne = 1 if feuille.nrows() > 1 else 0
    for idx in range(premiere_ligne, feuille.nrows()):
        try:
            formule = str(feuille[0, idx].value or "").strip()
        except IndexError:
            break  # fin reelle de la feuille (lignes non ecrites)
        if not formule:
            continue
        elements = []
        for col in range(1, 6):  # colonnes B a F : jusqu'a 5 elements
            try:
                element = str(feuille[col, idx].value or "").strip()
            except IndexError:
                break
            if element:
                elements.append(element)
        if elements:
            correspondance[formule] = elements
    logger.info(f"{len(correspondance)} formule(s) chargees depuis '{FEUILLE_TEXTES_FORMULES}'.")
    return correspondance


def formater_contenu_formule(elements):
    """Formate la liste d'elements en phrase pour le mail."""
    if not elements:
        return ""
    if len(elements) == 1:
        liste = elements[0]
    elif len(elements) == 2:
        liste = f"{elements[0]} et {elements[1]}"
    else:
        liste = ", ".join(elements[:-1]) + f" et {elements[-1]}"
    return f"\n{TEXTE_INTRO_CONTENU}{liste}.\n"


def construire_mail(nom, prenom, saison, elements_formule=None):
    """Construit le mail (sujet + corps) pour un adhérent."""
    sujet = SUJET_MAIL.format(saison=saison)
    contenu_formule = formater_contenu_formule(elements_formule or [])
    corps = CORPS_MAIL.format(prenom=prenom, nom=nom, saison=saison,
                              contenu_formule=contenu_formule)
    return sujet, corps


def envoyer_mail(to_email, sujet, corps, pdf_path):
    """Envoie le mail avec le reçu en pièce jointe."""
    msg = MIMEMultipart()
    msg['From'] = formataddr(("TC La Médullienne", SMTP_USER))
    msg['To'] = to_email
    msg['Subject'] = sujet
    msg.attach(MIMEText(corps, 'plain', 'utf-8'))

    with open(pdf_path, 'rb') as f:
        piece = MIMEApplication(f.read(), _subtype='pdf')
    piece.add_header('Content-Disposition', 'attachment',
                     filename=os.path.basename(pdf_path))
    msg.attach(piece)

    with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
        server.starttls()
        server.login(SMTP_USER, SMTP_PASSWORD)
        server.send_message(msg)


def envoyer_recus(mode_test=False):
    """Envoie les PDF des reçus X='encours' puis passe X à 'traité'."""
    import time
    currentYear = date.today().year
    sportiveYear = f"{currentYear}/{currentYear + 1}"
    textes_formules = charger_textes_formules()

    lignes = lire_lignes_ods()
    a_envoyer = [l for l in lignes if l[5] == STATUT_ENCOURS]

    if not a_envoyer:
        print("Aucun reçu en attente d'envoi (aucune ligne avec 'encours').")
        return

    # Vérifier les PDF existants
    complets = []
    for ligne in a_envoyer:
        (idx, nom, prenom, _, email, _, montant) = ligne
        pdf_path = os.path.join(WORK_DIR, EXPORT_DIR, f"TCLM_Recu_paiement_{nom}_{prenom}.pdf")
        if not os.path.exists(pdf_path):
            print(f"⚠️  PDF introuvable pour {prenom} {nom} : {pdf_path}")
            print("    (le reçu reste 'encours', il sera proposé au prochain lancement)")
            continue
        if not email or "@" not in email:
            print(f"⚠️  Email manquant ou invalide pour {prenom} {nom} ({email!r})")
            print("    (le reçu reste 'encours', complétez la colonne D)")
            continue
        complets.append((ligne, pdf_path))

    if not complets:
        print("\nAucun reçu envoyable (PDF manquant ou email invalide).")
        return

    print(f"\n{len(complets)} reçu(s) prêt(s) à l'envoi :\n")
    print(f"{'Nom':<20} {'Prénom':<15} {'Montant':<8} {'Email':<30}")
    print("-" * 75)
    for ((_, nom, prenom, _, email, _, montant), _) in complets:
        print(f"{nom:<20} {prenom:<15} {montant:<8} {email:<30}")
    print()

    if mode_test:
        print("Mode test : aucun envoi, aucune modification de l'ODS.")
        exemple_formule = complets[0][0][3]
        elements = textes_formules.get(exemple_formule, [])
        sujet, corps = construire_mail("DUPONT", "Jean", sportiveYear, elements)
        print(f"\n--- Aperçu du mail (formule : {exemple_formule}) ---")
        print(f"Sujet : {sujet}\n")
        print(corps)
        return

    # Confirmation : T (tous) ou U (unitaire)
    mode = ""
    while mode not in ("t", "u"):
        mode = input("Envoyer [T]ous ou [U]nitaire (O/N pour chaque reçu) ? ").strip().lower()

    selection = []
    if mode == "t":
        reponse = input(f"Envoyer les {len(complets)} reçu(s) ? (O/n) : ").strip().lower()
        if reponse == "n":
            print("Envoi annulé.")
            return
        selection = complets
    else:
        for (ligne, pdf_path) in complets:
            (_, nom, prenom, _, email, _, montant) = ligne
            reponse = input(f"Envoyer le reçu de {prenom} {nom} ({montant}€) à {email} ? (O/n) : ").strip().lower()
            if reponse != "n":
                selection.append((ligne, pdf_path))

    if not selection:
        print("Aucun envoi sélectionné.")
        return

    sauvegarde_ods()
    print()
    total = len(selection)
    for position, (ligne, pdf_path) in enumerate(selection, 1):
        (idx, nom, prenom, formule, email, _, montant) = ligne
        elements = textes_formules.get(formule, [])
        sujet, corps = construire_mail(nom, prenom, sportiveYear, elements)
        try:
            envoyer_mail(email, sujet, corps, pdf_path)
            maj_statut_recu(idx, STATUT_TRAITE)
            logger.info(f"[{position}/{total}] Reçu envoyé à {prenom} {nom} ({email}) - statut 'traité'")
            print(f"[{position}/{total}] ✅ Reçu envoyé à {prenom} {nom} ({email})")
        except Exception as e:
            logger.error(f"[{position}/{total}] Échec envoi {prenom} {nom} : {e}")
            print(f"[{position}/{total}] ❌ Échec pour {prenom} {nom} : {e}")
        if position < total:
            time.sleep(INTER_EMAIL_DELAY)

    print(f"\nTerminé : voir {LOG_FILE}")


def main():
    print("=== TC La Médullienne — Reçus de paiement ===\n")
    print("  1. Générer les reçus (colonne X 'demandé' -> PDF, statut 'encours')")
    print("  2. Envoyer les reçus (colonne X 'encours' -> mail + PJ, statut 'traité')")
    print("  3. Quitter\n")

    choix = ""
    while choix not in ("1", "2", "3"):
        choix = input("Votre choix : ").strip()

    mode_test = "--test" in sys.argv
    if choix == "1":
        generer_recus(mode_test=mode_test)
    elif choix == "2":
        envoyer_recus(mode_test=mode_test)
    else:
        print("Au revoir.")


if __name__ == "__main__":
    main()
