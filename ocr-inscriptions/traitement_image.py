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


def detecter_lignes(sombre, axe=0, seuil_frac=0.4, min_px=5):
    """Détecte les lignes horizontales (axe=0) ou verticales (axe=1) d'un
    binaire. Retourne les positions (pixels) des centres de lignes."""
    if axe == 0:  # horizontales
        profil = sombre.sum(axis=1)
        seuil = seuil_frac * sombre.shape[1]
    else:  # verticales
        profil = sombre.sum(axis=0)
        seuil = seuil_frac * sombre.shape[0]
    candidats = np.where(profil > seuil)[0]
    groupes = []
    if len(candidats):
        debut = candidats[0]
        prec = candidats[0]
        for y in candidats[1:]:
            if y - prec > min_px:
                groupes.append((debut + prec) / 2.0)
                debut = y
            prec = y
        groupes.append((debut + prec) / 2.0)
    return np.array(groupes)


def detecter_lignes_dans_zone(sombre, x0, x1, seuil_frac=0.4, min_px=5):
    """Détecte les lignes horizontales dans une zone verticale [x0, x1]."""
    profil = sombre[:, x0:x1].sum(axis=1)
    seuil = seuil_frac * (x1 - x0)
    candidats = np.where(profil > seuil)[0]
    groupes = []
    if len(candidats):
        debut = candidats[0]
        prec = candidats[0]
        for y in candidats[1:]:
            if y - prec > min_px:
                groupes.append((debut + prec) / 2.0)
                debut = y
            prec = y
        groupes.append((debut + prec) / 2.0)
    return np.array(groupes)


def appariements_lignes(lignes_detectees_pt, y_attendus_pt, fenetre_pt=30):
    """Associe les lignes détectées aux lignes attendues (plus proche voisin
    dans une fenêtre). Retourne [(y_attendu, y_trouve), ...]."""
    correspondances = []
    for y_att in y_attendus_pt:
        if len(lignes_detectees_pt) == 0:
            break
        distances = np.abs(lignes_detectees_pt - y_att)
        idx = int(np.argmin(distances))
        if distances[idx] < fenetre_pt:
            correspondances.append((float(y_att), float(lignes_detectees_pt[idx])))
    return correspondances


def estimer_homographie(sombre, gabarit, zoom, echelle_brut=1.0):
    """Estime une homographie (correction de perspective) à partir des
    séparateurs du tableau coordonnées.

    Repère les 4 coins du tableau coordonnées (intersections des séparateurs
    horizontaux extrêmes et verticaux extrêmes) dans le scan, et calcule la
    transformation perspective qui les ramène aux coordonnées du gabarit.

    Retourne (matrice 3x3, qualité 0..1) ou (None, 0) si échec.
    """
    if not opencv_disponible():
        return None, 0.0
    import cv2
    h, w = sombre.shape
    eb = echelle_brut
    # Zone du tableau coordonnées dans le gabarit
    x0g, x1g = 23.6, 577.0
    y0g, y1g = 94.9, 313.3
    # Lignes horizontales attendues (séparateurs du tableau coord)
    y_attendus = gabarit.get("marqueurs_recalage", {}).get("y_attendus", [])
    if len(y_attendus) < 5:
        return None, 0.0
    # Détecter les lignes horizontales dans le scan (zone centrale)
    x0_px = int(0.05 * w)
    x1_px = int(0.95 * w)
    lignes_px = detecter_lignes_dans_zone(sombre, x0_px, x1_px, seuil_frac=0.3)
    lignes_pt = lignes_px / (zoom * eb)
    # Appariement
    corresp = appariements_lignes(lignes_pt, y_attendus, fenetre_pt=40)
    if len(corresp) < 5:
        return None, 0.0
    # Coins horizontaux: première et dernière ligne appariées
    y_top_att, y_top_scan = corresp[0]
    y_bot_att, y_bot_scan = corresp[-1]
    # Détecter les séparateurs verticaux du tableau coordonnées dans la
    # bande verticale correspondant au tableau
    y_top_px = int(y_top_scan * zoom * eb)
    y_bot_px = int(y_bot_scan * zoom * eb)
    if y_bot_px <= y_top_px or y_bot_px > h:
        return None, 0.0
    # Séparateurs verticaux attendus: x=23.6 (gauche tableau), 87.9, 310.7, 368.0, 577.0 (droite)
    x_attendus = [23.6, 577.0]  # bords du tableau
    profil_x = sombre[y_top_px:y_bot_px, :].sum(axis=0)
    seuil_x = 0.3 * (y_bot_px - y_top_px)
    cols_px = np.where(profil_x > seuil_x)[0]
    # Grouper
    groupes_x = []
    if len(cols_px):
        debut = cols_px[0]; prec = cols_px[0]
        for x in cols_px[1:]:
            if x - prec > 5:
                groupes_x.append((debut + prec) / 2.0)
                debut = x
            prec = x
        groupes_x.append((debut + prec) / 2.0)
    if len(groupes_x) < 2:
        return None, 0.0
    # Prendre le séparateur le plus à gauche et le plus à droite (bords du tableau)
    x_gauche_px = groupes_x[0]
    x_droite_px = groupes_x[-1]
    # 4 coins du scan (en pixels)
    src = np.float32([
        [x_gauche_px, y_top_px],
        [x_droite_px, y_top_px],
        [x_gauche_px, y_bot_px],
        [x_droite_px, y_bot_px],
    ])
    # 4 coins du gabarit (en pixels à la même échelle que le scan)
    dst = np.float32([
        [x0g * zoom * eb, y0g * zoom * eb],
        [x1g * zoom * eb, y0g * zoom * eb],
        [x0g * zoom * eb, y1g * zoom * eb],
        [x1g * zoom * eb, y1g * zoom * eb],
    ])
    # Vérifier que les coins scan forment bien un quadrilatère (pas dégénéré)
    if (x_droite_px - x_gauche_px) < 50 or (y_bot_px - y_top_px) < 50:
        return None, 0.0
    M = cv2.getPerspectiveTransform(src, dst)
    # Qualité: nombre de correspondances / nombre attendu, pénalisé si peu
    qualite = min(1.0, len(corresp) / len(y_attendus))
    logger.info("Homographie estimée : %d/%d séparateurs, coins scan (%.0f,%.0f)-(%.0f,%.0f)",
                len(corresp), len(y_attendus), x_gauche_px, y_top_px, x_droite_px, y_bot_px)
    return M, qualite


def corriger_perspective(img, M):
    """Applique une homographie à une image (correction de perspective).

    La matrice M transforme les coordonnées du gabarit (pt * zoom) vers le scan.
    On veut l'inverse : on génère l'image corrigée en mappant chaque pixel du
    gabarit vers le scan via M (warpPerspective avec WARP_INVERSE_MAP).
    """
    if not opencv_disponible():
        return img
    import cv2
    h, w = img.shape[:2]
    # Taille de sortie : le gabarit en pixels à la même échelle
    # On garde les dimensions de l'image d'entrée (le scan couvre au moins le tableau)
    return cv2.warpPerspective(img, M, (w, h), flags=cv2.INTER_CUBIC,
                               borderMode=cv2.BORDER_CONSTANT, borderValue=255)


def estimer_recalage(img, gabarit, dpi=DPI_LECTURE):
    """Estime le recalage à partir des séparateurs horizontaux du tableau
    coordonnées (lignes noires quasi pleine largeur, y attendus dans le gabarit).

    Deux stratégies, essayées dans l'ordre :
    1. **Détection globale + appariement** : détecte toutes les lignes
       horizontales du scan, les apparie aux y attendus (fenêtre ±40 pt),
       puis régression affine. Robuste aux scans décalés/zoomés.
    2. Si < 5 appariements : retour à l'échelle brute (le scan est trop
       dégradé ou trop décalé pour un recalage fiable).

    Retourne un Recalage. La fiabilité reflète le nombre d'appariements.
    """
    recalage = Recalage()
    binaire = seuillage_adaptatif(img)
    sombre = binaire == 0
    h, w = sombre.shape
    zoom = dpi / 72.0
    # Facteur d'échelle brut : largeur du scan en px pour une page A4 (595.3 pt)
    echelle_brut = (w / (595.3 * zoom)) if w else 1.0
    y_attendus = gabarit.get("marqueurs_recalage", {}).get("y_attendus", [])
    if not y_attendus:
        recalage.echelle = echelle_brut
        return recalage
    # Stratégie 1 : détection globale + appariement
    x0_px = int(0.05 * w)
    x1_px = int(0.95 * w)
    lignes_px = detecter_lignes_dans_zone(sombre, x0_px, x1_px, seuil_frac=0.3)
    lignes_pt = lignes_px / (zoom * echelle_brut)
    corresp = appariements_lignes(lignes_pt, y_attendus, fenetre_pt=40)
    if len(corresp) < 5:
        logger.warning("Recalage : seulement %d séparateurs appariés, échelle brute %.3f", len(corresp), echelle_brut)
        recalage.echelle = echelle_brut
        recalage.fiabilite = float(len(corresp) / max(1, len(y_attendus)))
        return recalage
    # Régression affine y_trouve = a * y_attendu + b
    ya = np.array([c[0] for c in corresp])
    yt = np.array([c[1] for c in corresp])
    a, b = np.polyfit(ya, yt, 1)
    # Échelle horizontale via les séparateurs verticaux du tableau formules
    echelle_x = estimer_echelle_x(sombre, gabarit, zoom, echelle_brut)
    echelle = float((a + echelle_x) / 2.0) if echelle_x else float(a)
    recalage.echelle = echelle
    recalage.dy_pt = float(-b / a)
    recalage.dx_pt = 0.0
    recalage.angle_deg = 0.0
    residus = yt - (a * ya + b)
    residu_max = float(np.max(np.abs(residus)))
    recalage.fiabilite = float(min(1.0, len(corresp) / len(y_attendus)))
    # Pénaliser la fiabilité si les résidus sont grands (photo déformée)
    if residu_max > 5:
        recalage.fiabilite *= max(0.3, 1.0 - (residu_max - 5) / 20)
    logger.info(
        "Recalage : échelle=%.4f (brut %.3f), dy=%.1f pt, %d/%d séparateurs (résidu max %.1f pt)",
        recalage.echelle, echelle_brut, recalage.dy_pt,
        len(corresp), len(y_attendus), residu_max,
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
