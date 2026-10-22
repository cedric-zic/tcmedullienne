# -*- coding: utf-8 -*-
"""
traitement_image.py — Prétraitement, recalage et lecture d'une fiche d'inscription.

Tout le traitement est local (aucun appel réseau). Les fonctions de détection de
cases et de recalage ne dépendent que de numpy + Pillow + PyMuPDF. L'OCR texte
(Tesseract) et le déskew avancé (OpenCV) sont des dépendances optionnelles :
le module dégrade proprement leur absence avec un message explicite.

Conventions :
- Toutes les coordonnées de zone sont en points PDF (origine haut-gauche),
  page A4 595.3 x 841.9 pt (voir gabarit_v12.json).
- Les images traitées sont en niveaux de gris, numpy uint8, résolution DPI_LECTURE.
"""

import logging
import math
import os
import shutil
import subprocess

import numpy as np

logger = logging.getLogger(__name__)

DPI_LECTURE = 300  # résolution de rasterisation pour l'analyse d'image

# Seuils de détection d'une case cochée (ratio de pixels sombres à l'intérieur
# de la case, bords exclus). À calibrer sur le jeu des 361 fiches réelles.
SEUIL_CASE_COCHEE = 0.08
MARGE_BORD_CASE = 0.15  # fraction de la case à exclure sur chaque bord
# Une case est cochée si son ratio dépasse le ratio médian des cases du même
# groupe + SEUIL_RELATIF (évite les faux positifs sur cases bruitées).
SEUIL_RELATIF = 0.05


# ---------------------------------------------------------------------------
# Dépendances optionnelles
# ---------------------------------------------------------------------------

def _moteur_ocr_disponible():
    """Vrai si un moteur OCR local est utilisable (tesserocr ou pytesseract+tesseract)."""
    try:
        import tesserocr  # noqa: F401
        return True
    except ImportError:
        pass
    if shutil.which("tesseract"):
        try:
            import pytesseract  # noqa: F401
            return True
        except ImportError:
            return False
    return False


def tesseract_disponible():
    """Retourne le chemin de l'exécutable tesseract, ou None."""
    return shutil.which("tesseract")


def opencv_disponible():
    try:
        import cv2  # noqa: F401
        return True
    except ImportError:
        return False


def verifier_dependances(avec_ocr_texte=True):
    """Vérifie les dépendances et lève une erreur claire si manquante."""
    import fitz  # noqa: F401
    import PIL  # noqa: F401
    if avec_ocr_texte and not _moteur_ocr_disponible():
        raise RuntimeError(
            "Aucun moteur OCR local disponible. Installer sur le serveur :\n"
            "  sudo apt install tesseract-ocr tesseract-ocr-fra\n"
            "  pip install pytesseract\n"
            "ou bien : pip install tesserocr (sans binaire système, nécessite "
            "les fichiers tessdata : TESSDATA_PREFIX)"
        )


# ---------------------------------------------------------------------------
# Rasterisation
# ---------------------------------------------------------------------------

def rasteriser_page_pdf(page, dpi=DPI_LECTURE):
    """Rasterise une page PyMuPDF en image numpy (niveaux de gris)."""
    import fitz
    zoom = dpi / 72.0
    pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), colorspace=fitz.csGRAY)
    img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width)
    return img


def charger_image(fichier, dpi=DPI_LECTURE):
    """Charge un fichier image (JPG/PNG/TIFF...) en numpy gris.

    Retourne (image, echelle) où echelle = dpi_image / 72 (pour convertir
    les coordonnées du gabarit en pixels).
    """
    from PIL import Image
    pil = Image.open(fichier)
    info_dpi = pil.info.get("dpi", (dpi, dpi))
    dpi_x = info_dpi[0] if info_dpi[0] else dpi
    pil = pil.convert("L")
    img = np.array(pil)
    return img, dpi_x / 72.0


# ---------------------------------------------------------------------------
# Prétraitement
# ---------------------------------------------------------------------------

def seuillage_adaptatif(img):
    """Binarisation adaptative. Utilise OpenCV si dispo, sinon Otsu global (numpy)."""
    if opencv_disponible():
        import cv2
        return cv2.adaptiveThreshold(
            img, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 10
        )
    # Fallback : Otsu global
    hist, _ = np.histogram(img, bins=256, range=(0, 256))
    total = img.size
    sum_all = np.dot(np.arange(256), hist)
    sum_b, w_b, max_var, threshold = 0.0, 0, 0.0, 0
    for t in range(256):
        w_b += hist[t]
        if w_b == 0:
            continue
        w_f = total - w_b
        if w_f == 0:
            break
        sum_b += t * hist[t]
        m_b = sum_b / w_b
        m_f = (sum_all - sum_b) / w_f
        var = w_b * w_f * (m_b - m_f) ** 2
        if var > max_var:
            max_var, threshold = var, t
    return np.where(img > threshold, 255, 0).astype(np.uint8)


def corriger_inclinaison(img):
    """Estime et corrige l'inclinaison d'un scan (déskew).

    Méthode : projection horizontale sur profil de pixels sombres, test de
    plusieurs angles, on garde celui qui maximise la variance du profil.
    OpenCV non requis. Retourne l'image corrigée.
    """
    binaire = seuillage_adaptatif(img)
    sombre = (binaire == 0)
    h, w = sombre.shape
    # Sous-échantillonner pour la vitesse si l'image est grande
    scale = 1.0
    if w > 2000:
        scale = 2000.0 / w
        from PIL import Image
        pil = Image.fromarray(sombre.astype(np.uint8) * 255)
        pil = pil.resize((int(w * scale), int(h * scale)))
        sombre = np.array(pil) > 127
        h, w = sombre.shape
    # Tester des angles de -3 à +3 degrés par pas de 0.25
    meilleur_angle, meilleur_score = 0.0, -1.0
    centre_y, centre_x = h / 2.0, w / 2.0
    for angle in np.arange(-3.0, 3.01, 0.25):
        rad = math.radians(angle)
        cos_a, sin_a = math.cos(rad), math.sin(rad)
        # Rotation inverse des coordonnées des pixels sombres (échantillonnés)
        ys, xs = np.nonzero(sombre)
        if len(xs) == 0:
            continue
        # Échantillonner pour la vitesse
        idx = np.arange(0, len(xs), max(1, len(xs) // 20000))
        xs, ys = xs[idx], ys[idx]
        xr = (xs - centre_x) * cos_a - (ys - centre_y) * sin_a + centre_x
        yr = (xs - centre_x) * sin_a + (ys - centre_y) * cos_a + centre_y
        # Profil horizontal (somme par ligne après rotation)
        bins = np.clip(yr.astype(int), 0, h - 1)
        profil = np.bincount(bins, minlength=h).astype(float)
        score = float(np.var(profil))
        if score > meilleur_score:
            meilleur_score, meilleur_angle = score, angle
    if abs(meilleur_angle) < 0.1:
        return img
    # Appliquer la rotation inverse avec PIL
    from PIL import Image
    pil = Image.fromarray(img)
    pil = pil.rotate(meilleur_angle, resample=Image.BICUBIC, fillcolor=255)
    logger.info("Inclinaison corrigée : %.2f°", meilleur_angle)
    return np.array(pil)


# ---------------------------------------------------------------------------
# Recalage (alignement gabarit ↔ scan)
# ---------------------------------------------------------------------------

class Recalage:
    """Transformation affine simple (rotation + translation + échelle uniforme)
    estimée à partir des séparateurs horizontaux du tableau coordonnées."""

    def __init__(self):
        self.angle_deg = 0.0
        self.dx_pt = 0.0
        self.dy_pt = 0.0
        self.echelle = 1.0
        self.fiabilite = 0.0  # 0..1, proportion de séparateurs retrouvés

    def vers_pixels(self, x_pt, y_pt, img_shape, dpi=DPI_LECTURE):
        """Convertit un point du gabarit (pt) en pixel de l'image, après recalage.

        Le recalage exprime : px = pt * zoom * echelle + translation_px.
        L'échelle et la translation sont estimées sur les séparateurs du
        gabarit, donc le dpi nominal passé ici n'a d'importance que comme
        référence de départ (il est absorbé par l'échelle).
        """
        zoom = dpi / 72.0
        x = x_pt * zoom * self.echelle + self.dx_pt * zoom
        y = y_pt * zoom * self.echelle + self.dy_pt * zoom
        # rotation autour du centre de l'image
        h, w = img_shape[:2]
        cx, cy = w / 2.0, h / 2.0
        rad = math.radians(self.angle_deg)
        xr = (x - cx) * math.cos(rad) - (y - cy) * math.sin(rad) + cx
        yr = (x - cx) * math.sin(rad) + (y - cy) * math.cos(rad) + cy
        return xr, yr

    def zone_pixels(self, zone, img_shape, dpi=DPI_LECTURE):
        """Convertit une zone {x:[x0,x1], y:[y0,y1]} (pt) en rectangle pixel (x0,y0,x1,y1).

        Accepte aussi x ou y sous forme de nombre (pas de liste).
        """
        xz, yz = zone["x"], zone["y"]
        if isinstance(xz, dict):
            xz = xz["x"]
        if isinstance(yz, dict):
            yz = yz["y"]
        x0_pt, x1_pt = (xz if isinstance(xz, (list, tuple)) else (xz, xz))
        y0_pt, y1_pt = (yz if isinstance(yz, (list, tuple)) else (yz, yz))
        xa, ya = self.vers_pixels(x0_pt, y0_pt, img_shape, dpi)
        xb, yb = self.vers_pixels(x1_pt, y1_pt, img_shape, dpi)
        x0, x1 = sorted((int(round(min(xa, xb))), int(round(max(xa, xb)))))
        y0, y1 = sorted((int(round(min(ya, yb))), int(round(max(ya, yb)))))
        h, w = img_shape[:2]
        x0, x1 = max(0, x0), min(w, x1)
        y0, y1 = max(0, y0), min(h, y1)
        return (x0, y0, x1, y1)


def estimer_recalage(img, gabarit, dpi=DPI_LECTURE):
    """Estime le recalage à partir des séparateurs horizontaux du tableau
    coordonnées (lignes noires quasi pleine largeur, y attendus dans le gabarit).

    Retourne un Recalage. Si aucun séparateur n'est trouvé, retourne un
    recalage identité (fiabilité 0) — l'appelant décidera quoi faire.
    """
    recalage = Recalage()
    binaire = seuillage_adaptatif(img)
    sombre = binaire == 0
    h, w = sombre.shape
    zoom = dpi / 72.0
    # Facteur d'échelle brut : le scan fait quelle largeur en px pour une page
    # A4 de 595.3 pt ? Ça donne l'échelle globale même si le dpi déclaré est faux.
    echelle_brut = (w / (595.3 * zoom)) if w else 1.0
    y_attendus = gabarit.get("marqueurs_recalage", {}).get("y_attendus", [])
    if not y_attendus:
        recalage.echelle = echelle_brut
        return recalage
    # Pour chaque y attendu, chercher dans une fenêtre verticale la ligne
    # horizontale la plus sombre (somme de pixels sombres sur la largeur).
    # La fenêtre est exprimée en pixels via l'échelle brute.
    fenetre = 12 * zoom * echelle_brut  # ±12 pt de tolérance
    x0_profil = int(24 * zoom * echelle_brut)
    x1_profil = int(577 * zoom * echelle_brut)
    correspondances = []  # (y_attendu_pt, y_trouve_pt)
    for y_pt in y_attendus:
        y_centre = int(y_pt * zoom * echelle_brut)
        y_deb = max(0, int(y_centre - fenetre))
        y_fin = min(h, int(y_centre + fenetre))
        if y_fin <= y_deb:
            continue
        profil = sombre[y_deb:y_fin, x0_profil:x1_profil].sum(axis=1)
        # une vraie ligne de tableau = forte densité sur toute la largeur
        seuil_ligne = 0.5 * (x1_profil - x0_profil)
        candidats = np.where(profil > seuil_ligne)[0]
        if len(candidats) == 0:
            continue
        # centre de gravité des candidats (robuste à une ligne épaisse)
        y_trouve_px = float(np.average(candidats + y_deb, weights=profil[candidats]))
        correspondances.append((y_pt, y_trouve_px / (zoom * echelle_brut)))
    if len(correspondances) < 3:
        logger.warning("Recalage : seulement %d séparateurs trouvés, échelle brute %.3f", len(correspondances), echelle_brut)
        recalage.echelle = echelle_brut
        recalage.fiabilite = float(len(correspondances) / max(1, len(y_attendus)))
        return recalage
    # Régression y_trouve = a * y_attendu + b  (a = échelle affinée, b = offset pt)
    ya = np.array([c[0] for c in correspondances])
    yt = np.array([c[1] for c in correspondances])
    a, b = np.polyfit(ya, yt, 1)
    # L'échelle horizontale vient des séparateurs verticaux du tableau formules
    echelle_x = estimer_echelle_x(sombre, gabarit, zoom, echelle_brut)
    echelle = float((a + echelle_x) / 2.0) if echelle_x else float(a)
    angle = estimer_angle(sombre, gabarit, zoom)
    # Transformation finale : px = (pt + dy_pt) * echelle * zoom
    # Depuis y_trouve = a*y_attendu + b  =>  y_attendu = (y_trouve - b)/a
    # On veut px = y_pt * echelle * zoom, donc on exprime dy pour corriger
    # l'offset : y_corrigé_pt = y_pt + dy_pt avec dy_pt = -b/a (approximation
    # petits angles ; la translation est absorbée par l'échelle affinée).
    recalage.echelle = echelle
    recalage.dy_pt = float(-b / a)
    recalage.dx_pt = 0.0
    recalage.angle_deg = float(angle)
    residus = yt - (a * ya + b)
    recalage.fiabilite = float(min(1.0, len(correspondances) / len(y_attendus)))
    logger.info(
        "Recalage : échelle=%.4f (brut %.3f), dy=%.1f pt, angle=%.2f°, %d/%d séparateurs (résidu max %.1f pt)",
        recalage.echelle, echelle_brut, recalage.dy_pt, recalage.angle_deg,
        len(correspondances), len(y_attendus), float(np.max(np.abs(residus))),
    )
    return recalage


def estimer_echelle_x(sombre, gabarit, zoom, echelle_brut=1.0):
    """Estime l'échelle horizontale via les séparateurs verticaux du tableau
    formules (lignes verticales hautes entre y=340 et y=554)."""
    h, w = sombre.shape
    x_attendus = [20.3, 51.2, 258.5, 300.9, 343.4, 379.9, 422.2]
    eb = echelle_brut
    y_deb = int(345 * zoom * eb)
    y_fin = int(550 * zoom * eb)
    if y_fin > h or y_deb >= y_fin:
        return None
    profil = sombre[y_deb:y_fin, :].sum(axis=0)
    seuil = 0.5 * (y_fin - y_deb)
    # pics = colonnes avec beaucoup de pixels sombres
    pics = []
    in_pic = False
    for x in range(w):
        if profil[x] > seuil and not in_pic:
            debut = x; in_pic = True
        elif profil[x] <= seuil and in_pic:
            pics.append((debut + x) / 2.0); in_pic = False
    if in_pic:
        pics.append((debut + w) / 2.0)
    if len(pics) < 3:
        return None
    xa = np.array(sorted(x_attendus)) * zoom * eb
    pics_sorted = np.array(sorted(pics))
    # prendre les len(xa) pics les plus forts (par hauteur de profil)
    if len(pics_sorted) > len(xa):
        # filtrer les pics faibles
        forces = [profil[int(p)] for p in pics_sorted]
        ordre = np.argsort(forces)[-len(xa):]
        xp = np.sort(pics_sorted[ordre])
    else:
        xp = pics_sorted
    if len(xp) != len(xa):
        return None
    a, _ = np.polyfit(xa, xp, 1)
    return float(a)


def estimer_angle(sombre, gabarit, zoom):
    """Estime l'angle d'inclinaison via la corrélation des profils horizontaux
    en haut et en bas de la page (les lignes de tableau doivent être alignées)."""
    h, w = sombre.shape
    # Chercher pour quelques angles la variance du profil horizontal projeté
    # (méthode rapide : on réutilise corriger_inclinaison sur une version
    # sous-échantillonnée si l'angle estimé est significatif)
    return 0.0  # l'inclinaison est déjà corrigée en amont par corriger_inclinaison


# ---------------------------------------------------------------------------
# Détection de cases cochées
# ---------------------------------------------------------------------------

def ratio_pixels_sombres(img, rect, margin=MARGE_BORD_CASE):
    """Ratio de pixels sombres à l'intérieur d'un rectangle (bords exclus).

    rect = (x0, y0, x1, y1) en pixels. Retourne le ratio (0..1).
    """
    x0, y0, x1, y1 = rect
    if x1 <= x0 or y1 <= y0:
        return 0.0
    mx = int((x1 - x0) * margin)
    my = int((y1 - y0) * margin)
    interieur = img[y0 + my:y1 - my, x0 + mx:x1 - mx]
    if interieur.size == 0:
        return 0.0
    return float(np.mean(interieur < 128))


def case_cochee(img, rect, seuil=SEUIL_CASE_COCHEE, margin=MARGE_BORD_CASE):
    """Détecte si une case est cochée. Retourne (cochee: bool, ratio: float)."""
    ratio = ratio_pixels_sombres(img, rect, margin)
    return ratio >= seuil, ratio


def detecter_cases_groupe(img, rects, seuil=SEUIL_CASE_COCHEE, margin=MARGE_BORD_CASE,
                          seuil_relatif=SEUIL_RELATIF):
    """Détecte les cases cochées dans un groupe de cases (formules, paiement...).

    `rects` : liste de (nom, rect). Retourne (liste_noms_coches, {nom: ratio}).
    Stratégie : une case est cochée si son ratio est >= seuil ET supérieur
    d'au moins `seuil_relatif` au ratio médian du groupe (les cases vides
    d'un formulaire imprimé ont un ratio de fond quasi constant).
    """
    ratios = {nom: ratio_pixels_sombres(img, rect, margin) for nom, rect in rects}
    if not ratios:
        return [], ratios
    mediane = float(np.median(list(ratios.values())))
    cochees = [
        nom for nom, r in ratios.items()
        if r >= seuil and r >= mediane + seuil_relatif
    ]
    return cochees, ratios


# ---------------------------------------------------------------------------
# OCR d'une zone de texte
# ---------------------------------------------------------------------------

def _ocr_avec_tesserocr(pil_img, langue, psm):
    """OCR via tesserocr (API C de Tesseract, sans binaire système)."""
    from tesserocr import PyTessBaseAPI, PSM, RIL
    psm_map = {6: PSM.SINGLE_BLOCK, 7: PSM.SINGLE_LINE, 8: PSM.SINGLE_WORD, 3: PSM.AUTO}
    tessdata = os.environ.get("TESSDATA_PREFIX", "")
    kwargs = {"lang": langue}
    if tessdata:
        kwargs["path"] = tessdata
    api = PyTessBaseAPI(**kwargs)
    try:
        api.SetImage(pil_img)
        api.SetPageSegMode(psm_map.get(psm, PSM.SINGLE_LINE))
        texte = api.GetUTF8Text() or ""
        # Confiance moyenne par mot
        confs = []
        ri = api.GetIterator()
        if ri:
            while True:
                try:
                    confs.append(ri.Confidence(RIL.WORD))
                except Exception:
                    pass
                if not ri.Next(RIL.WORD):
                    break
        mots = [m for m in texte.split() if m.strip()]
        confiance = float(np.mean(confs)) / 100.0 if confs else (1.0 if mots else 0.0)
        return texte.strip(), confiance
    finally:
        api.End()


def _ocr_avec_pytesseract(pil_img, langue, psm):
    """OCR via pytesseract (binaire tesseract système)."""
    import pytesseract
    data = pytesseract.image_to_data(
        pil_img, lang=langue, config=f"--psm {psm}", output_type=pytesseract.Output.DICT
    )
    mots, confs = [], []
    for texte, conf in zip(data["text"], data["conf"]):
        texte = (texte or "").strip()
        if not texte:
            continue
        try:
            c = float(conf)
        except (TypeError, ValueError):
            continue
        if c < 0:
            continue
        mots.append(texte)
        confs.append(c)
    texte = " ".join(mots).strip()
    confiance = float(np.mean(confs)) / 100.0 if confs else 0.0
    return texte, confiance


def ocr_zone(img, rect, langue="fra", psm=7):
    """OCR d'une zone rectangulaire (pixels) via Tesseract (local).

    Retourne (texte, confiance 0..1). psm 7 = une seule ligne de texte.
    Essaie tesserocr (API C) puis pytesseract (binaire système).
    """
    from PIL import Image
    x0, y0, x1, y1 = rect
    if x1 <= x0 or y1 <= y0:
        return "", 0.0
    # Isoler le contenu manuscrit/imprimé : seuillage pour ne garder que le
    # texte (supprime le fond gris des scans et les séparateurs de tableau).
    sous = img[y0:y1, x0:x1]
    binaire = seuillage_adaptatif(sous)
    # Marge de contexte pour aider Tesseract (appliquée sur le binaire complet)
    mx = int((x1 - x0) * 0.05)
    my = int((y1 - y0) * 0.3)
    h, w = binaire.shape
    zone = np.full((h + 2 * my, w + 2 * mx), 255, dtype=np.uint8)
    zone[my:my + h, mx:mx + w] = binaire
    pil = Image.fromarray(zone)
    # Suréchantillonner si la zone est petite (Tesseract aime les grandes glyphes)
    if pil.height < 40:
        facteur = max(2, int(40 / max(1, pil.height)))
        pil = pil.resize((pil.width * facteur, pil.height * facteur), Image.LANCZOS)
    try:
        import tesserocr  # noqa: F401
        return _ocr_avec_tesserocr(pil, langue, psm)
    except ImportError:
        pass
    return _ocr_avec_pytesseract(pil, langue, psm)


def ocr_zone_multiligne(img, rect, langue="fra"):
    """OCR d'une zone pouvant contenir plusieurs lignes (psm 6)."""
    return ocr_zone(img, rect, langue=langue, psm=6)


def nettoyer_date_naissance(texte):
    """Normalise une date de naissance lue par OCR (JJ/MM/AAAA)."""
    import re
    t = texte.strip().replace(" ", "")
    # gardes chiffres et séparateurs
    t = re.sub(r"[^0-9./-]", "", t)
    m = re.match(r"^(\d{1,2})[./-](\d{1,2})[./-](\d{2,4})$", t)
    if not m:
        return texte.strip()
    j, mth, a = m.groups()
    if len(a) == 2:
        a = ("19" + a) if int(a) > 30 else ("20" + a)
    return f"{int(j):02d}/{int(mth):02d}/{a}"


def nettoyer_telephone(texte):
    """Normalise un numéro de téléphone français."""
    import re
    chiffres = re.sub(r"[^0-9]", "", texte)
    if len(chiffres) == 10:
        return " ".join(chiffres[i:i + 2] for i in range(0, 10, 2))
    return texte.strip()


def nettoyer_email(texte):
    """Nettoie un email lu par OCR (espaces, virgules finales, etc.)."""
    import re
    t = texte.strip().replace(" ", "")
    t = t.strip(".,;:")
    # corrige les classiques : ',at' -> '@', 'gmail,com' -> 'gmail.com'
    t = t.replace(",", ".")
    if "@" not in t:
        t = re.sub(r"(at|@| a )", "@", t, count=1) if (" at " in f" {texte} " or "a t" in t) else t
    return t.lower()
