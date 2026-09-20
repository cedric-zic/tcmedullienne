import argparse
import base64
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from email.header import Header
from email.utils import formataddr
import ezodf
from ezodf import Cell  # Ajoute cette ligne
from fpdf import FPDF
#from email.mime.image import MIMEImage
import getpass  # ajout pour la demande de mot de passe
import io               # Pour gérer les flux de bytes
import logging
import os
import pandas as pd
from pathlib import Path
from PIL import Image   # Pour rotater/redimensionner les images
import pymupdf          # Pour manipuler les PDF
import re
import smtplib
import tempfile
import time
import unicodedata
import uuid
from weasyprint import HTML

logging.getLogger('weasyprint').setLevel(logging.ERROR)  # ✅ Désactive INFO et WARNING
logging.getLogger("pymupdf").setLevel(logging.CRITICAL)  # Désactive les logs MuPDF

# # --- CONFIGURATION POUR GMAIL ---
# SMTP_SERVER = "smtp.gmail.com"
# SMTP_PORT = 587
# SMTP_USER = "cedric.tclm@gmail.com"
# # SMTP_PASSWORD = getpass.getpass("Entrez votre mot de passe GMail (le mot de passe ne s'affichera pas) : ")  # Demande le mot de passe (masqué)
# SMTP_PASSWORD = "ytlm akig wpnq wmsd "
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

SOURCE_FILE = r"P:/2026-2027/Adhérents/gestion_adherents_2026-2027.ods"
ATTACHMENTS_DIR = r"P:/2026-2027/Adhérents/Fiches_inscriptions"
LOGO_PATH = r"P:/2025-2026/Bureau/Documents divers/logo_tcmedullienne_2026_transparent_160px.png"  # Remplacez par votre chemin

# --- NOUVELLES CONSTANTES POUR LES TAMPONS ---
TAMPON_ANNULE_PATH = r"P:/2026-2027/Bureau/Modèles documents/Logos/tampon_Annulé_transparent.png"
TAMPON_PROF_PATH = r"P:/2026-2027/Bureau/Modèles documents/Logos/tampon_Professeur_transparent.png"

BATCH_SIZE = 1
LIMIT_PER_DAY = 15  # adaptez à votre limite réelle (15-20)
INTER_EMAIL_DELAY = 45   # secondes entre chaque email (envoi lissé, pas de pics)
SUBJECT = "TC La Medullienne - Inscription {prenom} {nom} - Saison 2026/2027"
EMAIL_SENT_COLUMN = 20  # Colonne T (20ème colonne)
DATE_ENVOI_COLUMN = 21 # Colonne U
FICHE_VALIDEE_COLUMN = 16  # Colonne P (16ème colonne)
HEADER_ROW = 7  # Ligne des en-têtes (ligne 7)
DATA_START_ROW = 8  # Ligne de début des données (ligne 8)
MAX_ADHERENTS = 1000 # nombre maximum de lignes à traiter dans le fichier (fonction Read_calc principalement)

# --- CONFIGURATION DES LOGS ---
LOG_DIR = "logs"
LOG_FILE = os.path.join(LOG_DIR, f"envoi_emails_{datetime.now().strftime('%Y%m%d')}.log")
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

# --- VÉRIFIER L'ACCÈS AU LECTEUR P: ---
try:
    if not os.path.exists("P:\\"):
        raise FileNotFoundError("Le lecteur P: (pCloud) n'est pas accessible.")
    if not os.path.exists(SOURCE_FILE):
        raise FileNotFoundError(f"Le fichier calc {SOURCE_FILE} est introuvable.")
    if not os.path.isdir(ATTACHMENTS_DIR):
        raise NotADirectoryError(f"Le dossier {ATTACHMENTS_DIR} est introuvable.")
    if not os.path.exists(TAMPON_ANNULE_PATH):
        raise FileNotFoundError(f"Le tampon d'annulation {TAMPON_ANNULE_PATH} est introuvable.")
    if not os.path.exists(TAMPON_PROF_PATH):
        raise FileNotFoundError(f"Le tampon professeur {TAMPON_PROF_PATH} est introuvable.")
    logger.info("✅ Accès au lecteur P: et aux fichiers validé.")
except Exception as e:
    logger.error(f"❌ Erreur d'accès aux fichiers : {e}")
    raise

# --- FONCTION POUR AJOUTER UN TAMPON SUR UN PDF ---
def ajouter_tampon_au_pdf(
    pdf_path: str,
    image_path: str,
    position_percent: tuple = (0.33, 0.70),
    rotation: float = 0,
    max_size: tuple = (200, 200),
    page_index: int = 0,
    output_path: str = None
):
    """
    Version corrigée de votre fonction originale.
    Évite les conflits en sauvegardant d'abord dans un fichier temporaire.
    """
    # Créer un fichier temporaire pour éviter les conflits
    temp_dir = tempfile.mkdtemp()
    temp_pdf_path = os.path.join(temp_dir, os.path.basename(pdf_path))

    try:
        # Copier le PDF original dans le fichier temporaire
        with open(pdf_path, "rb") as src, open(temp_pdf_path, "wb") as dst:
            dst.write(src.read())

        # Traiter le fichier temporaire
        doc = pymupdf.open(temp_pdf_path)
        page = doc[page_index]
        img = Image.open(image_path)

        if rotation != 0:
            img = img.rotate(rotation, expand=True, resample=Image.BICUBIC)
        if max_size:
            img.thumbnail(max_size, Image.BICUBIC)

        x = position_percent[0] * page.rect.width
        y = position_percent[1] * page.rect.height
        img_rect = pymupdf.Rect(x, y, x + img.width, y + img.height)

        img_byte_arr = io.BytesIO()
        img.save(img_byte_arr, format='PNG')
        img_byte_arr.seek(0)
        page.insert_image(img_rect, stream=img_byte_arr)

        # Sauvegarder dans un nouveau fichier temporaire
        output_temp_path = os.path.join(temp_dir, "output.pdf")
        doc.save(output_temp_path)
        doc.close()

        # Remplacer le fichier original par le nouveau
        with open(output_temp_path, "rb") as src, open(pdf_path, "wb") as dst:
            dst.write(src.read())

    finally:
        # Nettoyer les fichiers temporaires
        for f in [temp_pdf_path, output_temp_path] if 'output_temp_path' in locals() else [temp_pdf_path]:
            if os.path.exists(f):
                try:
                    os.remove(f)
                except:
                    pass
        if os.path.exists(temp_dir):
            try:
                os.rmdir(temp_dir)
            except:
                pass

# --- FONCTIONS DE NORMALISATION ---
def remove_accents(input_str):
    if not input_str:
        return ""
    nfkd_form = unicodedata.normalize('NFKD', str(input_str))
    return ''.join([c for c in nfkd_form if not unicodedata.combining(c)])

def normalize_name(nom, prenom, prefix="Inscription_2026"):
    nom = nom.strip()
    nom = remove_accents(nom)
    nom = nom.replace(" ", "-").upper()
    prenom = prenom.strip()
    prenom = remove_accents(prenom)
    prenom_parts = prenom.split()
    prenom_normalized = "-".join([part.capitalize() for part in prenom_parts])
    return f"{prefix}_{nom}_{prenom_normalized}.pdf"

def find_attachment(nom, prenom, directory):
    expected_filename = normalize_name(nom, prenom)
    expected_path = os.path.join(directory, expected_filename)
    if os.path.exists(expected_path):
        logger.info(f"📎 Pièce jointe trouvée : {expected_filename}")
        return expected_path
    for filename in os.listdir(directory):
        if expected_filename.lower() in filename.lower():
            logger.warning(f"⚠️ Pièce jointe trouvée avec un nom différent : {filename}")
            return os.path.join(directory, filename)
    logger.warning(f"⚠️ Aucune pièce jointe pour {nom} {prenom} (recherché : {expected_filename})")
    return None

def est_transposee_ezodf(sheet, ligne_en_tetes=7):
    """Vérifie si une feuille ezodf est transposée (NOM en colonne)."""
    try:
        for col in range(10):
            val = sheet[col, ligne_en_tetes - 1].value
            if val is not None and str(val).strip() == "NOM":
                if col + 1 < 10 and sheet[col + 1, ligne_en_tetes - 1].value == "PRENOM":
                    return False  # Structure NORMALE (lignes = adhérents)
                elif ligne_en_tetes < 10 and sheet[col, ligne_en_tetes].value == "PRENOM":
                    return True   # Structure TRANSPOSEE (colonnes = adhérents)
        return False
    except:
        return False


def is_after_october_first():
    """Vérifie si la date du jour est après le 1er octobre."""
    today = datetime.now()
    return today.month > 10 or (today.month == 10 and today.day >= 1)


def is_older_than_one_month(date_str):
    """Vérifie si une date (str) a plus d'un mois."""
    if not date_str or str(date_str).strip() == "":
        return True  # Pas de date = considérer comme ancien
    try:
        # Essayer les formats courants
        for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
            try:
                date_obj = datetime.strptime(str(date_str).strip(), fmt)
                return (datetime.now() - date_obj) > timedelta(days=30)
            except ValueError:
                continue
        return True  # Format inconnu
    except Exception:
        return True

def get_logo_base64():
    """Retourne le logo sous forme de data URI base64."""
    try:
        with open(LOGO_PATH, "rb") as img_file:
            logo_data = img_file.read()
            logo_base64 = base64.b64encode(logo_data).decode('utf-8')
            return f"data:image/png;base64,{logo_base64}"
    except Exception as e:
        logger.error(f"❌ Impossible de lire le logo: {e}")
        return ""  # Retourne une chaîne vide si le logo est introuvable

# --- FONCTION POUR GÉNÉRER LE CORPS DE L'EMAIL D'ANNULATION ---
def generate_html_annulation_body(adherent):
    formule = adherent.get("FORMULE ADOC", "Non spécifiée")

    # ✅ Utilisation du logo en base64
    logo_data_uri = get_logo_base64()  # Appel de la fonction

    return f"""
    <!DOCTYPE html>
    <html lang="fr">
    <head>
        <meta http-equiv="Content-Type" content="text/html; charset=utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <meta name="x-apple-disable-message-reformatting">
        <title>Annulation de votre adhésion 2026</title>
    </head>
    <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Arial, sans-serif; line-height: 1.4; color: #333; width: 100%; max-width: 600px; margin: 0 auto; padding: 20px; background: #f9f9f9; font-size: 14px;">
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:600px; margin:0 auto;">
            <tr>
                <td style="background: #e74c3c; color: white; padding: 20px; text-align: center; border-radius: 5px 5px 0 0;">
                    <table role="presentation" align="center" cellpadding="0" cellspacing="0">
                        <tr>
                            <td style="background: white; padding: 5px; border-radius: 5px; box-shadow: 0 1px 3px rgba(0,0,0,0.2);">
                                <img src="{logo_data_uri}" alt="Logo TC La Médullienne" style="max-height: 60px; display: block; border:0;">
                            </td>
                            <td style="padding-left: 15px; vertical-align: middle;">
                                <h1 style="margin: 0; font-size: 20px;">Annulation de votre adhésion 2026</h1>
                            </td>
                        </tr>
                    </table>
                </td>
            </tr>
            <tr>
                <td style="background: white; padding: 20px; border-radius: 0 0 5px 5px; box-shadow: 0 2px 5px rgba(0,0,0,0.1);">
                    <p style="margin:0 0 10px 0;">Bonjour <strong>{adherent['PRENOM']} {adherent['NOM']}</strong>,</p>
                    <p style="margin:0 0 10px 0;">Nous vous confirmons que l'annulation de votre inscription pour la saison 2026/2027 a bien été prise en compte.</p>
                    <h2 style="color: #2c3e50; border-bottom: 2px solid #e74c3c; padding-bottom: 5px; margin: 20px 0 10px 0; font-size:16px;">📋 Détails de l'annulation</h2>
                    <p style="margin:0 0 10px 0;"><strong>Formule initialement souscrite :</strong> {formule}</p>
                    <p style="margin:15px 0 0 0;">N'hésitez pas à nous contacter pour toute question.</p>
                </td>
            </tr>
            <tr>
                <td style="margin-top: 20px; text-align: center; font-size: 12px; color: #7f8c8d; padding: 20px;">
                    <p style="margin:0;">Cordialement,<br>Cédric Meschin<br>Secrétaire TC La Médullienne.</p>
                </td>
            </tr>
        </table>
    </body>
    </html>
    """

# --- FONCTION POUR GÉNÉRER LE CORPS DE L'EMAIL (AVEC CONVERSION DES VALEURS NUMÉRIQUES) ---
def generate_html_email_body(adherent, attachment_found=False):
    formule = adherent.get("FORMULE ADOC", "Non spécifiée")

    # ✅ Utilisation du logo en base64
    logo_data_uri = get_logo_base64()  # Appel de la fonction
    # Conversion explicite des valeurs numériques en float
    prix_club = float(adherent.get("Prix Club", 0) or 0)
    reduc = float(adherent.get("Réduc", 1) or 1)
    tarif_professeur = float(adherent.get("Prix Profs", 0) or 0)
    montant_club = float(adherent.get("Montant club", 0) or 0)
    montant_restant = -round(float(adherent.get("Reste dû", 0) or 0),2)
    montant_paye = montant_club - montant_restant
    print("Montant payé {} = Montant Club {} - Montant restant {}".format(montant_paye, montant_club, montant_restant))
    moyen_paiement = adherent.get("Moyen paiement", "Non spécifié")

    tarif_applicable = prix_club + tarif_professeur
    tarif_details = []

    message_paiement_professeur = ""
    tarif_details.append(f"Tarif Club : {prix_club:.2f} €")
    if reduc != 1:  # famille d'au moins 3 personnes
        tarif_details.append(f"Réduction -20% (famille) : Oui")
        tarif_details.append(f"Tarif réduit (famille) sur prix Club: {montant_club:.2f} €")
    if tarif_professeur > 0:
        tarif_details.append(f"Tarif professeur : {tarif_professeur:.2f} € - Paiement directement au professeur.")
        message_paiement_professeur = """
        <p style="color: #e74c3c; font-weight: bold; font-size: 16px;">
            ⚠️ Rappel : Le règlement des cours adultes se fait directement auprès des professeurs.
        </p>
        """
    tarif_applicable = montant_club + tarif_professeur

    if montant_restant > 0:
        message_paiement = f"""
        <p style="color: #e74c3c; font-weight: bold; font-size: 16px;">
            ⚠️ Rappel : Il reste un solde de <strong>{montant_restant:.2f} €</strong> à régler au club.
        </p>
        """
        message_solde = f"""
        <tr><th>Montant restant dû</th><td><span class="highlight">{montant_restant:.2f} €</span></td></tr>
        """
    elif montant_restant == 0:
        message_paiement = """
        <p style="color: #2ecc71; font-weight: bold; font-size: 16px;">
            ✅ Merci pour votre paiement complet !
        </p>
        """
        message_solde = f"""
        <tr><th>Montant restant dû</th><td><span class="highlight">{abs(montant_restant):.2f} €</span></td></tr>
        """
    else:  # montant_restant < 0 (trop payé)
        message_paiement = f"""
        <p style="color: #3498db; font-weight: bold; font-size: 16px;">
            ℹ️ Vous avez trop payé de <strong>{-montant_restant:.2f} €</strong>. Nous vous recontacterons pour le remboursement.
        </p>
        """
        message_solde = f"""
        <tr><th>Montant trop versé</th><td><span class="highlight">{abs(montant_restant):.2f} €</span></td></tr>
        """

    attachment_message = """
    <p style="color: #3498db; font-weight: bold;">
        📎 Votre <strong>fiche d'inscription</strong> est jointe à cet email.
    </p>
    """ if attachment_found else """
    <p style="color: #e74c3c; font-style: italic;">
        ⚠️ Aucune fiche d'inscription n'a été trouvée pour votre dossier.
    </p>
    """

    return f"""
    <!DOCTYPE html>
    <html lang="fr">
    <head>
        <meta http-equiv="Content-Type" content="text/html; charset=utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <meta name="x-apple-disable-message-reformatting">
        <title>Votre adhésion 2026</title>
    </head>
    <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Arial, sans-serif; line-height: 1.4; color: #333; width: 100%; max-width: 600px; margin: 0 auto; padding: 20px; background: #f9f9f9; font-size: 14px;">
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:600px; margin:0 auto;">
            <tr>
                <td style="background: #3498db; color: white; padding: 20px; text-align: center; border-radius: 5px 5px 0 0;">
                    <table role="presentation" align="center" cellpadding="0" cellspacing="0">
                        <tr>
                            <td style="background: white; padding: 5px; border-radius: 5px; box-shadow: 0 1px 3px rgba(0,0,0,0.2);">
                                <img src="{logo_data_uri}" alt="Logo TC La Médullienne" style="max-height: 60px; display: block; border:0;">
                            </td>
                            <td style="padding-left: 15px; vertical-align: middle;">
                                <h1 style="margin: 0; font-size: 20px;">Votre adhésion 2026</h1>
                            </td>
                        </tr>
                    </table>
                </td>
            </tr>
            <tr>
                <td style="background: white; padding: 20px; border-radius: 0 0 5px 5px; box-shadow: 0 2px 5px rgba(0,0,0,0.1);">
                    <p style="margin:0 0 10px 0;">Bonjour <strong>{adherent['PRENOM']} {adherent['NOM']}</strong>,</p>
                    <p style="margin:0 0 10px 0;">Nous vous confirmons la prise en compte de votre inscription pour la nouvelle saison 2026/2027.</p>
                    {attachment_message}
                    <h2 style="color: #2c3e50; border-bottom: 2px solid #3498db; padding-bottom: 5px; margin: 20px 0 10px 0; font-size:16px;">📋 Détails de votre adhésion</h2>
                    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border-collapse: collapse; margin: 10px 0;">
                        <tr><th style="padding: 8px; text-align: left; border-bottom: 1px solid #ddd; font-size: 12px; background: #f2f2f2;">Formule</th><td style="padding: 8px; text-align: left; border-bottom: 1px solid #ddd; font-size: 12px;">{formule}</td></tr>
                        <tr>
                            <th style="padding: 8px; text-align: left; border-bottom: 1px solid #ddd; font-size: 12px; background: #f2f2f2; vertical-align: top;">Tarif appliqué</th>
                            <td style="padding: 8px; text-align: left; border-bottom: 1px solid #ddd; font-size: 12px;">
                                <ul style="margin:0; padding-left:20px;">
                                    {''.join([f'<li style="margin-bottom:5px;">{d}</li>' for d in tarif_details])}
                                </ul>
                                <p style="margin:5px 0 0 0;"><strong>→ Total : {tarif_applicable:.2f} €</strong></p>
                            </td>
                        </tr>
                    </table>
                    <h2 style="color: #2c3e50; border-bottom: 2px solid #3498db; padding-bottom: 5px; margin: 20px 0 10px 0; font-size:16px;">💳 Paiement au club</h2>
                    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border-collapse: collapse; margin: 10px 0;">
                        <tr><th style="padding: 8px; text-align: left; border-bottom: 1px solid #ddd; font-size: 12px; background: #f2f2f2;">Montant total</th><td style="padding: 8px; text-align: left; border-bottom: 1px solid #ddd; font-size: 12px; font-weight: bold; color: #3498db;">{montant_club:.2f} €</td></tr>
                        <tr><th style="padding: 8px; text-align: left; border-bottom: 1px solid #ddd; font-size: 12px; background: #f2f2f2;">Montant payé</th><td style="padding: 8px; text-align: left; border-bottom: 1px solid #ddd; font-size: 12px; font-weight: bold; color: #3498db;">{montant_paye:.2f} €</td></tr>
                        {message_solde.replace('<tr>', '<tr>').replace('<th>', '<th style="padding: 8px; text-align: left; border-bottom: 1px solid #ddd; font-size: 12px; background: #f2f2f2;">').replace('<td>', '<td style="padding: 8px; text-align: left; border-bottom: 1px solid #ddd; font-size: 12px;">')}
                        <tr><th style="padding: 8px; text-align: left; border-bottom: 1px solid #ddd; font-size: 12px; background: #f2f2f2;">Moyen de paiement</th><td style="padding: 8px; text-align: left; border-bottom: 1px solid #ddd; font-size: 12px;">{moyen_paiement}</td></tr>
                    </table>
                    {message_paiement_professeur}
                    {message_paiement}
                    <p style="margin:15px 0 0 0;">N'hésitez pas à nous contacter pour toute question.</p>
                </td>
            </tr>
            <tr>
                <td style="margin-top: 20px; text-align: center; font-size: 12px; color: #7f8c8d; padding: 20px;">
                    <p style="margin:0;">Cordialement,<br>Cédric Meschin<br>Secrétaire TC La Médullienne.</p>
                </td>
            </tr>
        </table>
    </body>
    </html>
    """

# --- FONCTION POUR METTRE À JOUR LE FICHIER calc POUR LES ANNULATIONS ---
def update_calc_annulation_status(ods_file, row_index, is_transposed=False, date_envoi=None, test_mode=False):
    """Met à jour les champs liés à l'annulation dans le fichier ODS."""
    if test_mode:  # ✅ Ajout de cette ligne
        return

    try:
        wb = ezodf.opendoc(ods_file)
        ws = wb.sheets["Liste_adherents"]
        
        # Colonnes à mettre à jour (en 0-based pour ezodf)
        fiche_validee_col = FICHE_VALIDEE_COLUMN - 1  # Colonne P (16ème colonne)
        pre_inscription_col = 17 - 1  # Colonne Q (17ème)
        email_envoye_col = EMAIL_SENT_COLUMN - 1  # Colonne T (20ème colonne)
        inscription_validee_col = 22 - 1  # Colonne V (22ème)
        licence_generee_col = 23 - 1  # Colonne W (23ème)
        paiement_col = 25 - 1  # Colonne Y (25ème)
        date_envoi_col = DATE_ENVOI_COLUMN - 1  # Colonne U (21ème colonne)
        
        if is_transposed:
            # Structure transposée : adhérents en COLONNES
            ws[row_index + DATA_START_ROW - 1, fiche_validee_col] = Cell("Annulé")
            ws[row_index + DATA_START_ROW - 1, pre_inscription_col] = Cell("Annulé")
            ws[row_index + DATA_START_ROW - 1, email_envoye_col] = Cell("Annulé")
            ws[row_index + DATA_START_ROW - 1, inscription_validee_col] = Cell("Annulé")
            ws[row_index + DATA_START_ROW - 1, licence_generee_col] = Cell("Annulé")
            ws[row_index + DATA_START_ROW - 1, paiement_col] = Cell("Annulé")
            if date_envoi:
                ws[row_index + DATA_START_ROW - 1, date_envoi_col] = Cell(date_envoi)
        else:
            # Structure normale : adhérents en LIGNES
            ws[fiche_validee_col, row_index + DATA_START_ROW - 1] = Cell("Annulé")
            ws[pre_inscription_col, row_index + DATA_START_ROW - 1] = Cell("Annulé")
            ws[email_envoye_col, row_index + DATA_START_ROW - 1] = Cell("Annulé")
            ws[inscription_validee_col, row_index + DATA_START_ROW - 1] = Cell("Annulé")
            ws[licence_generee_col, row_index + DATA_START_ROW - 1] = Cell("Annulé")
            ws[paiement_col, row_index + DATA_START_ROW - 1] = Cell("Annulé")
            if date_envoi:
                ws[date_envoi_col, row_index + DATA_START_ROW - 1] = Cell(date_envoi)
        
        wb.save()
        logger.info(f"📝 Mise à jour ODS pour annulation : ligne {row_index + DATA_START_ROW} | Date={date_envoi}")
    except Exception as e:
        logger.error(f"❌ Erreur mise à jour ODS pour annulation : {str(e)}")

# --- FONCTION POUR METTRE À JOUR LE FICHIER calc (AVEC WIN32COM) ---
def update_calc_status(ods_file, row_index, status, test_mode=False, is_transposed=False, date_envoi=None):
    if test_mode:
        return
    try:
        wb = ezodf.opendoc(ods_file)
        ws = wb.sheets["Liste_adherents"]
        if is_transposed:
            # Structure transposée : adhérents en COLONNES
            ws[row_index + DATA_START_ROW - 1, EMAIL_SENT_COLUMN - 1] = Cell(status)
            if date_envoi:
                ws[row_index + DATA_START_ROW - 1, DATE_ENVOI_COLUMN - 1] = Cell(date_envoi)
        else:
            # Structure normale : adhérents en LIGNES
            ws[EMAIL_SENT_COLUMN - 1, row_index + DATA_START_ROW - 1] = Cell(status)
            if date_envoi:
                ws[DATE_ENVOI_COLUMN - 1, row_index + DATA_START_ROW - 1] = Cell(date_envoi)
        wb.save()
        logger.info(f"📝 Mise à jour ODS : {'colonne' if is_transposed else 'ligne'} {row_index + DATA_START_ROW} | Statut={status} | Date={date_envoi}")
    except Exception as e:
        logger.error(f"❌ Erreur mise à jour ODS : {str(e)}")

# --- FONCTION POUR METTRE À JOUR LE CHAMP "Fiche numérisée" ---
def update_fiche_numerisee_status(ods_file, row_index, status, test_mode=False, is_transposed=False):
    """Met à jour le champ 'Fiche numérisée' dans le fichier ODS."""
    if test_mode:
        return
    try:
        wb = ezodf.opendoc(ods_file)
        ws = wb.sheets["Liste_adherents"]
        fiche_numerisee_col = 19 - 1  # Colonne S (19ème)
        
        if is_transposed:
            ws[row_index + DATA_START_ROW - 1, fiche_numerisee_col] = Cell(status)
        else:
            ws[fiche_numerisee_col, row_index + DATA_START_ROW - 1] = Cell(status)
        
        wb.save()
        logger.info(f"📝 Mise à jour ODS : Fiche numérisée = {status} pour {'colonne' if is_transposed else 'ligne'} {row_index + DATA_START_ROW}")
    except Exception as e:
        logger.error(f"❌ Erreur mise à jour ODS pour 'Fiche numérisée' : {str(e)}")

# # --- FONCTION POUR GÉNÉRER UN PDF ---
# def generate_pdf(content, pdf_filename, output_dir=None):
#     # WeasyPrint gère UTF-8 et les emojis (📎, ✅, ⚠️, €, etc.) sans modification
#     pdf_path = os.path.join(output_dir, pdf_filename) if output_dir else pdf_filename
#     HTML(string=content).write_pdf(pdf_path)
#     return pdf_path
def generate_pdf(content, pdf_filename, output_dir=None):
    """
    Génère un PDF à partir du HTML, en remplaçant le chemin du logo par son contenu binaire.
    """
    # ✅ Remplacer le chemin du logo par une version base64 intégrée (pour les PDFs)
    if 'cid:logo' in content:
        try:
            with open(LOGO_PATH, "rb") as img_file:
                logo_data = img_file.read()
                logo_base64 = base64.b64encode(logo_data).decode('utf-8')
                # Remplacer cid:logo par une balise img avec le logo en base64
                content = content.replace(
                    '<img src="cid:logo"',
                    f'<img src="data:image/png;base64,{logo_base64}"'
                )
        except Exception as e:
            logger.warning(f"⚠️ Impossible d'intégrer le logo dans le PDF: {e}")

    pdf_path = os.path.join(output_dir, pdf_filename) if output_dir else pdf_filename
    HTML(string=content).write_pdf(pdf_path)
    return pdf_path

# --- FONCTION D'ENVOI D'EMAIL ---
def send_email(to_email, subject, html_body, attachment_path=None, test_mode=False, logo_path=None, adherent=None):
    nom = str(adherent.get("NOM", "") if adherent else "").strip()
    prenom = str(adherent.get("PRENOM", "") if adherent else "").strip()
    pdf_filename = normalize_name(nom, prenom, prefix="Votre_adhesion_2026")

    if test_mode:
        pdf_path = generate_pdf(html_body, pdf_filename, ATTACHMENTS_DIR)
        logger.info(f"📄 PDF généré pour {to_email} : {pdf_path}")
        return True

    # ✅ Racine : multipart/mixed (corps HTML + pièces jointes)
    msg = MIMEMultipart('mixed')

    # Encodage des en-têtes
    msg["From"] = formataddr(("Cédric Meschin - TC La Médullienne", SMTP_USER))
    msg["To"] = to_email
    msg["Subject"] = Header(subject, 'utf-8')
    msg["Date"] = datetime.now().strftime("%a, %d %b %Y %H:%M:%S %z")
    msg["Reply-To"] = SMTP_USER
    msg["Message-ID"] = f"<{uuid.uuid4()}@gmail.com>"
    msg["X-Mailer"] = "script_envoi_email_inscription_v9.py/1.0"
    # Return-Path retiré : Gmail le positionne correctement lui-même,
    # le forcer manuellement peut créer une incohérence pénalisée par free/outlook.

    # ✅ Section multipart/related (HTML + images inline)
    # Le logo est déjà embarqué en data-URI base64 dans le HTML (get_logo_base64),
    # donc pas besoin de mécanisme cid:logo ni de MIMEImage.
    related = MIMEMultipart('related')
    related.attach(MIMEText(html_body, 'html', 'utf-8'))
    msg.attach(related)

    # ✅ Pièce jointe (fiche d'inscription) — au niveau du mixed, hors du related
    attachment_name = "aucune"
    if attachment_path and os.path.exists(attachment_path):
        attachment_name = os.path.basename(attachment_path)
        with open(attachment_path, "rb") as attachment:
            part = MIMEBase("application", "octet-stream")
            part.set_payload(attachment.read())
        encoders.encode_base64(part)
        part.add_header("Content-Disposition", f"attachment; filename={attachment_name}")
        msg.attach(part)

    try:
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT, timeout=60) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.send_message(msg)
        return True
    except Exception as e:
        logger.error(f"❌ Échec pour {to_email} | Erreur : {str(e)}")
        return False

# --- FONCTION POUR LECTURE DES DONNÉES ---
def read_calc_data(ods_file):
    try:
        wb = ezodf.opendoc(ods_file)
        ws = wb.sheets["Liste_adherents"]

        # 🔍 Étape 1 : Trouver "NOM" (10 lignes × 50 colonnes)
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
            raise ValueError("❌ En-tête 'NOM' introuvable")

        col_nom, row_nom = nom_pos
        logger.info(f"✅ 'NOM' trouvé en colonne {col_nom + 1}, ligne {row_nom + 1}")

        # 🔍 Étape 2 : Détection UNIQUE de la structure
        is_transposed = False
        if col_nom + 1 < 50 and ws[col_nom + 1, row_nom].value == "PRENOM":
            logger.info("📊 Structure détectée : NORMALE (lignes = adhérents)")
        elif row_nom + 1 < 10 and ws[col_nom, row_nom + 1].value == "PRENOM":
            logger.info("📊 Structure détectée : TRANSPOSEE (colonnes = adhérents)")
            is_transposed = True
        else:
            raise ValueError("❌ Structure non reconnue")

        # 🔍 Étape 3 : Lecture des données (selon la structure)
        headers = []
        data = []

        if not is_transposed:
            # Structure NORMALE : en-têtes en ligne, données en lignes
            for col in range(50):
                val = ws[col, row_nom].value
                if val is None or str(val).strip() == "":
                    break
                headers.append(str(val).strip())

            for row in range(row_nom + 1, MAX_ADHERENTS):
                nom = ws[0, row].value
                if nom is None or str(nom).strip() == "":
                    break
                adherent = {}
                for j, header in enumerate(headers):
                    adherent[header] = str(ws[j, row].value).strip() if ws[j, row].value is not None else ""
                data.append(adherent)

        else:
            # Structure TRANSPOSEE : en-têtes en colonne, données en colonnes
            for row in range(row_nom, row_nom + 50):
                val = ws[col_nom, row].value
                if val is None or str(val).strip() == "":
                    break
                headers.append(str(val).strip())

            for col in range(col_nom + 1, MAX_ADHERENTS):
                nom = ws[col, row_nom].value
                if nom is None or str(nom).strip() == "":
                    break
                adherent = {}
                for j, header in enumerate(headers):
                    adherent[header] = str(ws[col, row_nom + j].value).strip() if ws[col, row_nom + j].value is not None else ""
                data.append(adherent)

        logger.info(f"✅ En-têtes lus : {headers}")
        logger.info(f"✅ Données lues : {len(data)} adhérents")
        return data, headers, is_transposed

    except Exception as e:
        logger.error(f"❌ Erreur lecture ODS : {str(e)}", exc_info=True)
        return [], [], False

# --- FONCTION PRINCIPALE (MODIFIÉE POUR RÉESSAYER LES ERREURS) ---
def main():
    parser = argparse.ArgumentParser(description="Envoyer des emails de confirmation d'adhésion.")
    parser.add_argument("--test", action="store_true", help="Mode test: génère un PDF au lieu d'envoyer un email.")
    args = parser.parse_args()

    try:
        adherents, headers, is_transposed = read_calc_data(SOURCE_FILE)
        logger.info(f"🔍 Structure finale : {'TRANSPOSEE' if is_transposed else 'NORMALE'}")
        
        required_columns = [
            "NOM", "PRENOM", "Email", "FORMULE ADOC", "Prix Club",
            "Réduc", "Prix Profs", "Prix Total hors remise", "Montant club",
            "Reste dû", "Moyen paiement", "Fiche numérisée", "Paiement", "Date envoie", "Fiche Validée"
        ]
        missing_columns = [col for col in required_columns if col not in headers]
        if missing_columns:
            raise ValueError(f"Colonnes manquantes : {missing_columns}")

        # Filtrer uniquement les lignes où NOM est non vide
        adherents = [a for a in adherents if a.get("NOM") and str(a["NOM"]).strip() != ""]

        wb = ezodf.opendoc(SOURCE_FILE)
        ws = wb.sheets["Liste_adherents"]

        # --- ÉTAPE 1: TRAITER LES PROFESSEURS (ajout du tampon) ---
        logger.info("🔹 Début du traitement des professeurs...")
        for row_index, adherent in enumerate(adherents):
            formule_adoc = adherent.get("FORMULE ADOC", "")
            fiche_numerisee = adherent.get("Fiche numérisée", "")
            
            if "Prof" in formule_adoc and fiche_numerisee != "Oui - Prof":
                nom = adherent.get("NOM", "")
                prenom = adherent.get("PRENOM", "")
                attachment_path = find_attachment(nom, prenom, ATTACHMENTS_DIR)
                
                if attachment_path:
                    try:
                        # Appliquer le tampon PROF
                        ajouter_tampon_au_pdf(
                            pdf_path=attachment_path,
                            image_path=TAMPON_PROF_PATH,
                            position_percent=(0.33, 0.70),
                            rotation=0,
                            output_path=attachment_path
                        )
                        logger.info(f"🖌️ Tampon PROF ajouté à la fiche de {prenom} {nom}")
                        
                        # Mettre à jour le champ "Fiche numérisée"
                        update_fiche_numerisee_status(
                            SOURCE_FILE, row_index, "Oui - Prof", args.test, is_transposed
                        )
                        adherent["Fiche numérisée"] = "Oui - Prof"
                        
                    except Exception as e:
                        logger.error(f"❌ Erreur lors de l'ajout du tampon PROF pour {prenom} {nom}: {str(e)}")
                else:
                    logger.warning(f"⚠️ Fiche non trouvée pour le professeur {prenom} {nom}")

        # --- ÉTAPE 2: TRAITER LES ANNULATIONS (flux séparé) ---
        logger.info("🔹 Début du traitement des annulations...")
        adherents_annules = []
        for row_index, adherent in enumerate(adherents):
            fiche_validee = adherent.get("Fiche Validée", "")
            email_envoye = adherent.get("Email envoyé", "")
            
            if fiche_validee == "Annulé" and email_envoye != "Annulé":
                adherents_annules.append((row_index, adherent))
        
        for row_index, adherent in adherents_annules:
            nom = adherent.get("NOM", "")
            prenom = adherent.get("PRENOM", "")
            email = adherent.get("Email", "")
            
            if not nom or not prenom or not email:
                logger.warning(f"⚠️ Ligne annulée ignorée (NOM/PRENOM/Email manquant) : {adherent}")
                continue
            
            attachment_path = find_attachment(nom, prenom, ATTACHMENTS_DIR)
            if not attachment_path:
                logger.error(f"❌ Fiche non trouvée pour l'annulation de {prenom} {nom}")
                continue
            
            try:
                # Appliquer le tampon ANNULÉ
                ajouter_tampon_au_pdf(
                    pdf_path=attachment_path,
                    image_path=TAMPON_ANNULE_PATH,
                    position_percent=(0.33, 0.30),
                    rotation=45,
                    output_path=attachment_path
                )
                logger.info(f"🖌️ Tampon ANNULÉ ajouté à la fiche de {prenom} {nom}")
                
                # Envoyer l'email d'annulation
                subject = SUBJECT.format(prenom=prenom, nom=nom) + " - Annulé"
                html_body = generate_html_annulation_body(adherent)
                
                if send_email(
                    email, subject, html_body, 
                    attachment_path, args.test, 
                    logo_path=LOGO_PATH, adherent=adherent
                ):
                    today = datetime.now().strftime("%d/%m/%Y")
                    update_calc_annulation_status(SOURCE_FILE, row_index, is_transposed, today, test_mode=args.test)
                    logger.info(f"✅ Email d'annulation {'simulé' if args.test else 'envoyé'} à {email}")
                    time.sleep(INTER_EMAIL_DELAY)
                else:
                    logger.error(f"❌ Échec de l'envoi de l'email d'annulation pour {email}")
                    time.sleep(INTER_EMAIL_DELAY)
                    
            except Exception as e:
                logger.error(f"❌ Erreur critique pour l'annulation de {prenom} {nom}: {str(e)}")

        # --- ÉTAPE 3: TRAITER LES ADHÉRENTS NORMAUX (logique existante) ---
        logger.info("🔹 Début du traitement des adhérents normaux...")
        adherents_to_process = []
        for i, adherent in enumerate(adherents):
            fiche_validee = adherent.get("Fiche Validée", "")
            if fiche_validee == "Annulé":
                continue  # Exclure les annulés
            
            try:
                if is_transposed:
                    status = ws[i + DATA_START_ROW - 1, EMAIL_SENT_COLUMN - 1].value
                    date_envoi = ws[i + DATA_START_ROW - 1, DATE_ENVOI_COLUMN - 1].value
                else:
                    status = ws[EMAIL_SENT_COLUMN - 1, i + DATA_START_ROW - 1].value
                    date_envoi = ws[DATE_ENVOI_COLUMN - 1, i + DATA_START_ROW - 1].value

                envoyer_email = False
                is_relance = False
                paiement = str(adherent.get("Paiement", "Non")).strip()
                status = str(status).strip() if status else ""

                # Cas 1: Paiement COMPLET → Envoyer email de confirmation SI statut ≠ "Oui"
                if paiement in ["Oui", "Remboursement"]:
                    if status != "Oui":
                        envoyer_email = True
                        is_relance = False

                # Cas 2: Paiement PARTIEL/NON → Envoyer email de relance SI :
                elif paiement == "Partiel":
                    if status in ["", "Erreur"]:
                        envoyer_email = True
                        is_relance = False
                    elif (status == "Relancer" and date_envoi and is_older_than_one_month(date_envoi) and is_after_october_first()):
                        envoyer_email = True
                        is_relance = True
                elif paiement == "Non":
                    if status in ["", "Erreur"]:
                        envoyer_email = True
                        is_relance = False
                    elif (status == "Relancer" and date_envoi and is_older_than_one_month(date_envoi)):
                        envoyer_email = True
                        is_relance = True

                if envoyer_email:
                    adherents_to_process.append((i, adherent, is_relance))
                    logger.info(f"📌 À traiter: {adherent.get('NOM', '')} {adherent.get('PRENOM', '')} | Relance: {is_relance} | Paiement: {paiement} | Statut: {status} | Date: {date_envoi}")

            except IndexError as e:
                logger.warning(f"⚠️ Cellule hors limites pour l'adhérent {i}: {str(e)}")
                adherents_to_process.append((i, adherent, False))

        # logger.info(f"📊 {len(adherents_to_process)} adhérents à traiter (hors annulations).")
        total_to_process = len(adherents_to_process)
        logger.info(f"📊 {total_to_process} adhérents à traiter hors annulations (limite journalière: {LIMIT_PER_DAY}).")

        total_sent = 0
        for i in range(0, len(adherents_to_process), BATCH_SIZE):
            batch = adherents_to_process[i:i + BATCH_SIZE]

            # Calculer les emails restants avant la limite
            remaining = LIMIT_PER_DAY - total_sent
            if remaining <= 0:
                logger.info(f"⏳ Limite journalière de {LIMIT_PER_DAY} emails atteinte. Arrêt.")
                break

            # Réduire le batch si nécessaire
            batch = batch[:remaining]

            logger.info(f"📤 Envoi du lot {i//BATCH_SIZE + 1} ({len(batch)} emails)...")
            for row_index, adherent, is_relance in batch:
                nom = adherent.get("NOM", "")
                prenom = adherent.get("PRENOM", "")
                email = adherent.get("Email", "")
                fiche = adherent.get("Fiche numérisée", "")
                paiement = adherent.get("Paiement", "Non")
                
                # Adaptation du sujet
                subject = SUBJECT.format(prenom=prenom, nom=nom)
                if is_relance:
                    subject += " - Relance"
                
                if row_index == 57:
                    logger.warning(f"🔍 Adhérent 57 : {adherent}")
                
                # Vérifier que NOM, PRENOM et Email ne sont pas vides
                if not nom or not prenom:
                    logger.warning(f"⚠️ Ligne ignorée (NOM ou PRENOM manquant) : NOM={nom}, PRENOM={prenom}, Email={email}")
                    update_calc_status(SOURCE_FILE, row_index, "Erreur", args.test, is_transposed)
                    continue

                if not email:
                    logger.warning(f"⚠️ Ligne ignorée (Email manquant) : NOM={nom}, PRENOM={prenom}")
                    update_calc_status(SOURCE_FILE, row_index, "Erreur", args.test, is_transposed)
                    continue

                if not fiche:
                    logger.warning(f"⚠️ Ligne ignorée (Fiche manquante) : NOM={nom}, PRENOM={prenom}")
                    update_calc_status(SOURCE_FILE, row_index, "Erreur", args.test, is_transposed)
                    continue

                attachment_path = find_attachment(nom, prenom, ATTACHMENTS_DIR)
                attachment_found = attachment_path is not None
                if attachment_found:
                    html_body = generate_html_email_body(adherent, attachment_found)
                else:
                    update_calc_status(SOURCE_FILE, row_index, "Erreur", args.test, is_transposed)
                    logger.error(f"❌ Pièce jointe de {prenom} {nom} non trouvée pour {email} (fiche numérisée: {fiche}). Envoi email annulé.")
                    continue

                try:
                    if send_email(email, subject, html_body, attachment_path, args.test, logo_path=LOGO_PATH, adherent=adherent):
                        today = datetime.now().strftime("%d/%m/%Y")
                        statut = "Relancer" if paiement in ["Partiel", "Non"] else "Oui"
                        update_calc_status(SOURCE_FILE, row_index, statut, args.test, is_transposed, today)
                        total_sent += 1
                        # ✅ Décompte: X/Y (où Y = min(total_to_process, LIMIT_PER_DAY))
                        max_to_send = min(total_to_process, LIMIT_PER_DAY)
                        logger.info(f"✅ Email {total_sent}/{max_to_send} {'simulé' if args.test else 'envoyé'} à {email}")
                        logger.info(f"⏳ Pause de {INTER_EMAIL_DELAY} secondes avant le prochain email...")
                        time.sleep(INTER_EMAIL_DELAY)
                    else:
                        today = datetime.now().strftime("%d/%m/%Y")
                        update_calc_status(SOURCE_FILE, row_index, "Erreur", args.test, is_transposed, today)
                        logger.error(f"❌ Échec de l'envoi pour {email} (problème SMTP)")
                        total_sent += 1
                        logger.info(f"❌ Email {total_sent}/{LIMIT_PER_DAY} {'simulé' if args.test else ' non envoyé'} à {email}")
                        logger.info(f"⏳ Pause de {INTER_EMAIL_DELAY} secondes avant le prochain email...")
                        time.sleep(INTER_EMAIL_DELAY)
                except Exception as e:
                    update_calc_status(SOURCE_FILE, row_index, "Erreur", args.test, is_transposed)
                    logger.error(f"❌ Erreur critique pour {email} : {str(e)}")

            logger.info("⏳ Emails envoyés....")

            if i + BATCH_SIZE < len(adherents_to_process) and total_sent < LIMIT_PER_DAY:
                if args.test:
                    continue
                # Pas de pause supplémentaire : la pause inter-email (INTER_EMAIL_DELAY) suffit
                # pour lisser la cadence vers free/outlook.
        
        logger.info("🎉 Tous les emails ont été traités.")
    except Exception as e:
        logger.error(f"❌ Erreur critique dans le script : {str(e)}", exc_info=True)

if __name__ == "__main__":
    main()