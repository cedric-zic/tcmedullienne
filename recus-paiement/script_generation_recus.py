import locale
import hashlib
import hmac
from datetime import date, datetime
from docx import Document
from docx.shared import Inches, Cm, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
import os
import base64
import pandas as pd
from docx2pdf import convert

try:
    from cles_authenticite import calculer_cle
except ImportError:
    raise SystemExit(
        "❌ Fichier 'cles_authenticite.py' introuvable.\n"
        "Copiez 'cles_authenticite.py.example' en 'cles_authenticite.py' "
        "et renseignez les clés par saison.\n"
        "Ce fichier est exclu par le .gitignore : ne le commitez jamais."
    )


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


def main():
    work_dir = "P:/2026-2027/Adhérents/"
    fichier_source = "gestion_adherents_2026-2027.ods"
    template_facture = "Modele_doc/Modele_recu_paiement_2026.docx"
    export_dir = "Recu_paiements/"

    locale.setlocale(locale.LC_TIME, 'fr_FR.UTF-8')
    today = datetime.now()
    long_date = today.strftime("%A %d %B %Y")
    currentYear = date.today().year
    sportiveYear = str(currentYear) + "/" + str(currentYear + 1)
    date_recu = today.strftime("%Y%m%d")

    # Lire le fichier ODS en ignorant les lignes 1 à 7 (conserver l'en-tête)
    df = pd.read_excel(work_dir + fichier_source, engine="odf", skiprows=range(1, 8))

    # Filtrer les lignes où :
    # - Nom (Colonne A, index 0) n'est pas vide
    # - Demande de reçu (Colonne X, index 23) est EXACTEMENT "demandé"
    df_filtered = df[
        (df.iloc[:, 0].notna()) &  # Nom n'est pas NaN
        (df.iloc[:, 0] != "") &  # Nom n'est pas vide
        (df.iloc[:, 23].astype(str).str.strip() == "demandé")  # Demande de reçu est EXACTEMENT "demandé"
    ]

    print(f"Nombre total de lignes après filtrage initial : {len(df_filtered)}")

    # Afficher les lignes filtrées pour débogage
    print("\nLignes filtrées (Nom, Prénom, Demande de reçu, Montant) :")
    print(df_filtered[[df.columns[0], df.columns[1], df.columns[23], df.columns[25]]])

    # Parcourir uniquement les lignes filtrées
    for _, row in df_filtered.iterrows():
        nom = str(row.iloc[0]).strip()  # Colonne A (Nom)
        prenom = str(row.iloc[1]).strip()  # Colonne B (Prénom)
        montant = str(int(row.iloc[25]))  # Colonne Z (Montant)
        formule = row.iloc[6]  # Colonne G (Formule)

        # Vérifier que Montant est un nombre non nul AVANT de générer le document
        if str(montant).strip() == "0" or not str(montant).strip().replace('.', '', 1).isdigit():
            print(f"Ligne ignorée pour {prenom} {nom} : Montant invalide ({montant})")
            continue

        document = Document(work_dir + template_facture)
        style = document.styles['Normal']
        font = style.font
        font.name = 'Calibri'
        font.size = Pt(14)

        # Générer l'ID unique (HMAC sur nom, prénom, date, montant, saison, timestamp)
        timestamp = int(datetime.now().timestamp())
        unique_id = generer_id_authenticite(nom, prenom, date_recu, montant, sportiveYear, timestamp)

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

        # Ajouter le contenu au document
        document.add_paragraph(f"Nous confirmons que {prenom} {nom} est inscrit(e) au Tennis Club La Médullienne pour la saison tennistique {sportiveYear} avec la formule "
                              f"{formule}. La cotisation d'un montant total de {montant}€ a bien été acquittée. Celle-ci inclue: ")
        document.add_paragraph(f"    - l'adhésion au club")
        document.add_paragraph(f"    - la licence FFT multi-raquettes")
        document.add_paragraph(f"    - les cours avec un professeur diplômé, pour les enfants.")

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
        document.add_picture(work_dir + "/Modele_doc/signature_cedric.jpg")
        last_paragraph = document.paragraphs[-1]
        last_paragraph.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        # Ajouter l'ID unique
        p = document.add_paragraph(f"{unique_id}")
        p.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        for run in p.runs:
            run.font.size = Pt(6)
            run.font.color.rgb = RGBColor(201, 201, 201)

        # Nom du fichier Word
        filename_docx = f"TCLM_Recu_paiement_{nom}_{prenom}.docx"
        word_path = os.path.join(work_dir, export_dir, filename_docx)

        try:
            document.save(word_path)
            print(f"Reçu Word généré pour {prenom} {nom} avec ID : {unique_id}")

            # Convertir le fichier Word en PDF
            pdf_path = os.path.join(work_dir, export_dir, f"TCLM_Recu_paiement_{nom}_{prenom}.pdf")
            convert(word_path, pdf_path)
            print(f"Reçu PDF généré pour {prenom} {nom}")

        except PermissionError:
            print(f"Erreur : Impossible d'enregistrer le fichier {filename_docx}. Il est peut-être ouvert.")
        except Exception as e:
            print(f"Erreur lors de la conversion en PDF pour {prenom} {nom} : {e}")

if __name__ == "__main__":
    main()
