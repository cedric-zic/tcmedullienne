#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Compresse les PDF d'un dossier ou d'un fichier (fiches d'inscription scannées,
reçus, etc.) en réduisant la résolution des images embarquées et en les
réencodant en JPEG. Le fichier reste un PDF valide et lisible.

Principe (identique aux outils type « PDF Gear ») : la quasi-totalité du poids
d'un PDF scanné vient de ses images. Chaque image est ré-échantillonnée vers
un DPI cible (150 par défaut, largement suffisant pour une fiche A4) puis
réencodée en JPEG (qualité 65 par défaut). Les images avec masque de
transparence (tampons, logos) et les PDF protégés ne sont pas modifiés.

Exemples :
    # Aperçu du gain, sans rien modifier
    python script_compacter_pdf.py "P:/2026-2027/Fiches" --test

    # Compression effective (remplace les fichiers, originaux perdus)
    python script_compacter_pdf.py "P:/2026-2027/Fiches"

    # Compression plus agressive
    python script_compacter_pdf.py fiche.pdf --dpi 120 --qualite 50
"""

import argparse
import io
import os
import sys
import tempfile
import time

import pymupdf
from PIL import Image

DPI_CIBLE_DEFAUT = 150
QUALITE_JPEG_DEFAUT = 65

def compresser_pdf(src, dst, dpi_cible=DPI_CIBLE_DEFAUT, qualite=QUALITE_JPEG_DEFAUT):
    """
    Compresse le PDF `src` vers `dst`.
    Retourne (nb_images_recompressees, taille_avant, taille_apres).
    """
    doc = pymupdf.open(src)
    traites = set()
    nb_images = 0
    try:
        for page in doc:
            for img_info in page.get_images(full=True):
                xref, smask = img_info[0], img_info[1]
                if xref in traites:
                    continue
                traites.add(xref)
                if smask > 0:
                    continue
                try:
                    pix = pymupdf.Pixmap(doc, xref)
                except Exception:
                    continue
                mode = {1: "L", 3: "RGB"}.get(pix.n)
                if mode is None or pix.colorspace is None:
                    continue
                rects = page.get_image_rects(xref)
                if not rects:
                    continue
                rect = max(rects, key=lambda r: r.width * r.height)
                dpi_actuel = pix.width / max(rect.width, 1) * 72
                if dpi_actuel <= dpi_cible:
                    continue
                ratio = dpi_cible / dpi_actuel
                new_w = max(1, round(pix.width * ratio))
                new_h = max(1, round(pix.height * ratio))
                img = Image.frombytes(mode, (pix.width, pix.height), pix.samples)
                img = img.resize((new_w, new_h), Image.LANCZOS)
                buf = io.BytesIO()
                img.save(buf, format="JPEG", quality=qualite, optimize=True)
                doc.update_stream(xref, buf.getvalue(), compress=0)
                doc.xref_set_key(xref, "Filter", "/DCTDecode")
                doc.xref_set_key(xref, "DecodeParms", "null")
                doc.xref_set_key(xref, "Width", str(new_w))
                doc.xref_set_key(xref, "Height", str(new_h))
                doc.xref_set_key(xref, "ColorSpace", "/DeviceRGB" if mode == "RGB" else "/DeviceGray")
                doc.xref_set_key(xref, "BitsPerComponent", "8")
                nb_images += 1
        doc.save(dst, garbage=4, deflate=True)
    finally:
        doc.close()
    return nb_images, os.path.getsize(src), os.path.getsize(dst)

def traiter_fichier(pdf_path, dpi_cible, qualite, test_mode=False):
    """
    Compresse un PDF : la version compressée remplace l'original uniquement
    si elle est réellement plus légère. En mode test, rien n'est modifié.
    Retourne (statut, taille_avant, taille_apres) ou ("erreur", 0, 0, message).
    """
    tmp_path = None
    try:
        fd, tmp_path = tempfile.mkstemp(suffix=".pdf", prefix="compact_")
        os.close(fd)
        _, avant, apres = compresser_pdf(pdf_path, tmp_path, dpi_cible, qualite)
        if apres >= avant * 0.98:
            return "inchangé", avant, avant
        if not test_mode:
            os.replace(tmp_path, pdf_path)
            tmp_path = None
        return "compresse", avant, apres
    except Exception as e:
        return "erreur", 0, 0, str(e)
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)

def main():
    parser = argparse.ArgumentParser(
        description="Compresse les PDF scannés (réduction du DPI des images + JPEG).",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("cible", help="Fichier PDF ou dossier à traiter (récursif pour un dossier)")
    parser.add_argument("--dpi", type=int, default=DPI_CIBLE_DEFAUT, help="DPI cible des images")
    parser.add_argument("--qualite", type=int, default=QUALITE_JPEG_DEFAUT, help="Qualité JPEG (1-95)")
    parser.add_argument("--test", action="store_true", help="Aperçu du gain sans modifier les fichiers")
    args = parser.parse_args()

    cible = args.cible
    if os.path.isfile(cible):
        fichiers = [cible]
    elif os.path.isdir(cible):
        fichiers = sorted(
            str(p) for p in __import__("pathlib").Path(cible).rglob("*.pdf")
        )
        if not fichiers:
            print(f"Aucun PDF trouvé dans {cible}")
            return 1
    else:
        print(f"Introuvable : {cible}")
        return 1

    print(f"{'Mode TEST (aucun fichier modifié)' if args.test else 'Mode compression effective'}")
    print(f"DPI cible : {args.dpi} | Qualité JPEG : {args.qualite}")
    print("-" * 78)

    total_avant = total_apres = 0
    nb_compresses = nb_inchanges = nb_erreurs = 0
    t0 = time.time()
    for pdf in fichiers:
        resultat = traiter_fichier(pdf, args.dpi, args.qualite, args.test)
        statut, avant, apres = resultat[0], resultat[1], resultat[2]
        erreur = resultat[3] if len(resultat) > 3 else None
        nom = os.path.basename(pdf)
        if statut == "compresse":  # and apres < avant * 0.98 garanti par traiter_fichier
            nb_compresses += 1
            total_avant += avant
            total_apres += apres
            gain = (1 - apres / avant) * 100 if avant else 0
            print(f"✅ {nom} : {avant/1e6:.2f} Mo → {apres/1e6:.2f} Mo (-{gain:.0f}%)")
        elif statut == "inchangé":
            nb_inchanges += 1
            total_avant += avant
            total_apres += apres
            print(f"⏭️  {nom} : déjà léger ({avant/1e6:.2f} Mo), inchangé")
        else:
            nb_erreurs += 1
            print(f"❌ {nom} : {erreur}")

    print("-" * 78)
    duree = time.time() - t0
    if total_avant:
        print(
            f"{nb_compresses} compressés | {nb_inchanges} inchangés | {nb_erreurs} erreurs — "
            f"{total_avant/1e6:.1f} Mo → {total_apres/1e6:.1f} Mo "
            f"(-{(1 - total_apres/total_avant)*100:.0f} %) en {duree:.1f} s"
        )
    else:
        print(f"Aucune modification. {nb_erreurs} erreur(s).")
    return 0 if nb_erreurs == 0 else 1

if __name__ == "__main__":
    sys.exit(main())
