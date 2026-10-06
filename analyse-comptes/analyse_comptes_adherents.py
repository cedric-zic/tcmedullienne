#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Analyse des comptes adherents ADOC 2026-2027.

Croise 3 sources :
  - Inscription : gestion des adherents (inscriptions)     -> .ods
  - LiveXp      : export clients de l'application mobile    -> .csv
  - Fichier de suivi = fichier de synthese (.xlsx)
      * LU pour recuperer le suivi saisi (Compte cree, Adhesion validee,
        Email envoye, Credit, Commentaire)
      * REECRIT a chaque execution :
          - onglet "Suivi"        : 1 ligne par adherent inscrit (inscription),
                                    enrichi automatiquement du compte app
                                    (LiveXp), solde, inversion, homonymie ;
                                    les colonnes de suivi manuel sont
                                    preservees (migration depuis l'ancien
                                    Suivi a la 1re execution).
          - onglet "Annulation"  : inscriptions annulees (inscription, col. V).
          - onglets d'analyse    : compte sans abonnement ni credit,
                                    comptes pas a jour, inscrits sans
                                    compte app, homonymies.

Dependances : pandas, openpyxl, odfpy
  pip install pandas openpyxl odfpy
"""

import glob
import os
import re
import shutil
import unicodedata
from datetime import datetime

import pandas as pd

# =========================================================================
# PARAMETRES A ADAPTER
# =========================================================================

# Dossier de traitement racine (adapter a votre environnement).
DOSSIER_TRAVAIL = r"P:\2026-2027\Adhérents"

# Sous-dossier contenant l'extraction CSV de l'application (relatif au racine).
SOUS_DOSSIER_EXPORT = "Extraction_CSV_pour migration"

# Noms des fichiers (relatifs au dossier de traitement).
# Inscription (fichier gestion des adherents).
FICHIER_INSCRIPTIONS = "gestion_adherents_2026-2027_NEW.ods"
# LiveXp (export clients de l'application mobile).
FICHIER_EXPORT_APP   = "Export_clients_13092026145627.csv"

# Fichier de suivi = fichier de synthese (LU puis REECRIT).
# Il remplace l'ancien suivi (suivi_comptes_adherents_2026.ods).
FICHIER_SUIVI = "synthese_comptes_adherents_2026-2027.xlsx"
# Ancien suivi, utilise UNIQUEMENT pour la migration initiale
# (si FICHIER_SUIVI n'existe pas encore). Supprimable apres migration.
FICHIER_ANCIEN_SUIVI = "suivi_comptes_adherents_2026.ods"

# Rapport texte ecrit dans DOSSIER_TRAVAIL.

# Index des colonnes (0 = A, 1 = B, ...) - lus par position
# Inscription (fichier gestion des adherents)
F1_NOM      = 0   # A  NOM
F1_PRENOM   = 1   # B  PRENOM
F1_FORMULE  = 6   # G  FORMULE ADOC
F1_INSCRIPTION_VALIDEE = 21  # V  Inscription validee (Ok / Annule)
F1_PAIEMENT = 24  # Y  Paiement (Oui / Non / Partiel / Remboursement)

# LiveXp (fichier export application mobile)
F2_SOLDE    = 3   # D  CA_Solde
F2_NOM      = 5   # F  TA_Clients.Nom
F2_PRENOM   = 6   # G  prenom
F2_TYPE_CLIENT = 7  # H  Type_client (vide = compte non valide)

# Colonnes de suivi saisies manuellement (Suivi historique / onglet Suivi)
S_NOM      = 0   # A  Nom inscrit
S_PRENOM   = 1   # B  Prenom inscrit
S_COMPTE   = 2   # C  Compte cree
S_ADHESION = 3   # D  Adhesion validee
S_EMAIL    = 4   # E  Email envoye
S_CREDIT   = 5   # F  Credit
S_COMMENT  = 6   # G  Commentaire

# Ligne d'en-tete PAR FICHIER (0-indexee = numero de ligne Excel - 1).
F1_LIGNE_ENTETE = 6   # ligne 7 (legendes/totaux au-dessus)
F2_LIGNE_ENTETE = 0   # ligne 1
S_LIGNE_ENTETE = 2   # ligne 3 (totaux au-dessus) - ancien Suivi uniquement

# Separateur CSV force pour un fichier donne (None = detection auto).
F1_SEPARATEUR = ","
F2_SEPARATEUR = ";"
S_SEPARATEUR = ","

# Valeur consideree comme "renseigne/Oui" dans le suivi.
VALEUR_OUI = "Oui"
# Valeurs a ignorer (traitees comme "vide"). "Attente" ne doit JAMAIS
# etre considere comme un choix valide dans la solution finale.
VALEURS_VIDES = {"", "attente", "nan", "none", "na", "null"}

# Valeur indiquant un compte LiveXp non valide (Type_client vide).
VALEUR_INVALIDE = "Invalide"


# =========================================================================
# NORMALISATION DES NOMS / PRENOMS
# =========================================================================

def _strip_accents(text: str) -> str:
    """Retire les accents : decomposition NFD + suppression des combining marks."""
    return "".join(
        ch for ch in unicodedata.normalize("NFD", text)
        if unicodedata.category(ch) != "Mn"
    )


def normaliser(text) -> str:
    """
    Normalise un nom ou un prenom :
      - str + lower + strip
      - caracteres accentues remplaces par leur version sans accent
      - espaces remplaces par un tiret (-)  (noms composes / avec espace)
      - ponctuation parasite retiree (on garde lettres, chiffres, tiret)
    """
    if text is None:
        return ""
    s = str(text)
    s = _strip_accents(s)
    s = s.lower().strip()
    s = re.sub(r"\s+", "-", s)
    s = re.sub(r"[^a-z0-9-]", "", s)
    s = re.sub(r"-+", "-", s).strip("-")
    return s


# =========================================================================
# LECTURE DES FICHIERS
# =========================================================================

def _valeurs_colonnes(df: pd.DataFrame, indexs: list) -> list:
    return [df.iloc[:, i] for i in indexs]


def _detecter_separateur(chemin: str) -> str:
    with open(chemin, "rb") as f:
        echantillon = f.read(8192).decode("utf-8", errors="ignore")
    return ";" if echantillon.count(";") > echantillon.count(",") else ","


def _detecter_encodage(chemin: str) -> str:
    for enc in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            with open(chemin, "r", encoding=enc) as f:
                f.read(4096)
            return enc
        except (UnicodeDecodeError, LookupError):
            continue
    return "latin-1"


def _lire_table(chemin: str, ligne_entete, separateur=None) -> pd.DataFrame:
    """
    Lit un fichier .ods (engine=odf) ou .csv par position de colonnes.
    Renvoie un DataFrame SANS en-tete nomme (on lit ensuite par index).
    """
    ext = os.path.splitext(chemin)[1].lower()
    if ext == ".ods":
        return pd.read_excel(
            chemin, sheet_name=0, header=ligne_entete, engine="odf", dtype=str
        )
    sep = separateur if separateur is not None else _detecter_separateur(chemin)
    enc = _detecter_encodage(chemin)
    return pd.read_csv(
        chemin, header=ligne_entete, sep=sep, encoding=enc,
        dtype=str, skip_blank_lines=False, on_bad_lines="warn"
    )


def charger_inscriptions(chemin: str) -> pd.DataFrame:
    """Inscription : NOM, PRENOM, FORMULE ADOC, Inscription validee, Paiement."""
    df = _lire_table(chemin, F1_LIGNE_ENTETE, F1_SEPARATEUR)
    ncols = df.shape[1]
    idx = [F1_NOM, F1_PRENOM, F1_FORMULE]
    if ncols > F1_INSCRIPTION_VALIDEE:
        idx.append(F1_INSCRIPTION_VALIDEE)
    if ncols > F1_PAIEMENT:
        idx.append(F1_PAIEMENT)
    cols = _valeurs_colonnes(df, idx)
    out = pd.DataFrame({
        "NOM_f1":     cols[0].fillna("").astype(str),
        "PRENOM_f1":  cols[1].fillna("").astype(str),
        "FORMULE_f1": cols[2].fillna("").astype(str),
    })
    if len(cols) > 3:
        out["INSCRIPTION_VALIDEE_f1"] = cols[3].fillna("").astype(str)
    else:
        out["INSCRIPTION_VALIDEE_f1"] = ""
    if len(cols) > 4:
        out["PAIEMENT_f1"] = cols[4].fillna("").astype(str)
    else:
        out["PAIEMENT_f1"] = ""
    out["NOM_norm"]   = out["NOM_f1"].map(normaliser)
    out["PRENOM_norm"] = out["PRENOM_f1"].map(normaliser)
    out = out[(out["NOM_norm"] != "") | (out["PRENOM_norm"] != "")].reset_index(drop=True)
    return out


def charger_export_app(chemin: str) -> pd.DataFrame:
    """LiveXp : CA_Solde, TA_Clients.Nom, prenom, Type_client."""
    df = _lire_table(chemin, F2_LIGNE_ENTETE, F2_SEPARATEUR)
    ncols = df.shape[1]
    idx = [F2_NOM, F2_PRENOM, F2_SOLDE]
    if ncols > F2_TYPE_CLIENT:
        idx.append(F2_TYPE_CLIENT)
    cols = _valeurs_colonnes(df, idx)
    out = pd.DataFrame({
        "NOM_f2":     cols[0].fillna("").astype(str),
        "PRENOM_f2":  cols[1].fillna("").astype(str),
        "SOLDE_f2":   cols[2].fillna("").astype(str),
    })
    out["TYPE_CLIENT_f2"] = cols[3].fillna("").astype(str) if len(cols) > 3 else ""
    out["NOM_norm"]    = out["NOM_f2"].map(normaliser)
    out["PRENOM_norm"] = out["PRENOM_f2"].map(normaliser)
    out["SOLDE_num"] = pd.to_numeric(
        out["SOLDE_f2"].str.replace(",", ".").str.replace(" ", ""),
        errors="coerce"
    )
    # Un compte est considere valide si Type_client est renseigne.
    out["COMPTE_VALIDE"] = out["TYPE_CLIENT_f2"].str.strip() != ""
    out = out[(out["NOM_norm"] != "") | (out["PRENOM_norm"] != "")].reset_index(drop=True)
    return out


def charger_ancien_suivi(chemin: str) -> pd.DataFrame:
    """Ancien Suivi : suivi manuel (migration initiale)."""
    df = _lire_table(chemin, S_LIGNE_ENTETE, S_SEPARATEUR)
    ncols = df.shape[1]
    idx = [S_NOM, S_PRENOM, S_COMPTE, S_ADHESION, S_EMAIL, S_CREDIT]
    if ncols > S_COMMENT:
        idx.append(S_COMMENT)
    cols = _valeurs_colonnes(df, idx)
    out = pd.DataFrame({
        "NOM_s":      cols[0].fillna("").astype(str),
        "PRENOM_s":   cols[1].fillna("").astype(str),
        "COMPTE_s":   cols[2].fillna("").astype(str),
        "ADHESION_s": cols[3].fillna("").astype(str),
        "EMAIL_s":    cols[4].fillna("").astype(str),
        "CREDIT_s":   cols[5].fillna("").astype(str),
    })
    out["COMMENT_s"] = cols[6].fillna("").astype(str) if len(cols) > 6 else ""
    out["NOM_norm"]   = out["NOM_s"].map(normaliser)
    out["PRENOM_norm"] = out["PRENOM_s"].map(normaliser)
    out = out[(out["NOM_norm"] != "") | (out["PRENOM_norm"] != "")].reset_index(drop=True)
    return out


def charger_suivi_xlsx(chemin: str) -> pd.DataFrame:
    """Lit l'onglet 'Suivi' du fichier de synthese deja existant."""
    df = pd.read_excel(chemin, sheet_name="Suivi", engine="openpyxl", dtype=str)
    df = df.fillna("")
    out = pd.DataFrame({
        "NOM_s":      df.get("NOM", "").astype(str),
        "PRENOM_s":   df.get("PRENOM", "").astype(str),
        "COMPTE_s":   df.get("C - Compte cree", "").astype(str),
        "ADHESION_s": df.get("D - Adhesion validee", "").astype(str),
        "EMAIL_s":    df.get("E - Email envoye", "").astype(str),
        "CREDIT_s":   df.get("F - Credit octroye", "").astype(str),
        "COMMENT_s":  df.get("Commentaire", "").astype(str),
    })
    out["NOM_norm"]   = out["NOM_s"].map(normaliser)
    out["PRENOM_norm"] = out["PRENOM_s"].map(normaliser)
    out = out[(out["NOM_norm"] != "") | (out["PRENOM_norm"] != "")].reset_index(drop=True)
    return out


# =========================================================================
# UTILITAIRES DE CHAMPS "Oui"
# =========================================================================

def est_renseigne(valeur) -> bool:
    """Renvoie True si la cellule vaut 'Oui' (insensible casse/espaces)."""
    if valeur is None:
        return False
    s = str(valeur).strip().lower()
    return s == VALEUR_OUI.lower() and s not in VALEURS_VIDES


# =========================================================================
# CORRESPONDANCE FORMULE ADOC -> ABONNEMENT ATTENDU
# =========================================================================

def abonnement_attendu(formule: str) -> str:
    """
    'Tennis' seul         -> ABONNEMENT TENNIS ADHERENT
    'Padel' seul          -> ABONNEMENT PADEL ADHERENT
    'Tennis' + 'Padel'    -> ABONNEMENT TENNIS + PADEL
    'Adhesion seule'      -> (aucun)
    """
    if formule is None:
        return ""
    s = formule.lower()
    has_tennis = "tennis" in s
    has_padel = "padel" in s
    has_seule = "seule" in s
    if has_tennis and has_padel:
        return "ABONNEMENT TENNIS + PADEL"
    if has_tennis:
        return "ABONNEMENT TENNIS ADHERENT"
    if has_padel:
        return "ABONNEMENT PADEL ADHERENT"
    if has_seule or s.strip() == "":
        return ""
    return ""


def est_annulee(inscription_validee: str) -> bool:
    """Inscription annulee = colonne V de l'inscription contient 'Annule'."""
    if inscription_validee is None:
        return False
    s = str(inscription_validee).strip().lower()
    return "annul" in s


# =========================================================================
# CROISEMENT
# =========================================================================

def construire_index(df: pd.DataFrame) -> dict:
    """Index {(nom_norm, prenom_norm): [indices]}."""
    index = {}
    for i, row in df.iterrows():
        key = (row["NOM_norm"], row["PRENOM_norm"])
        index.setdefault(key, []).append(i)
    return index


def apparier(source, index_cible, detecter_inversion=False):
    """Renvoie liste d'indices cibles (liste vide si aucun), liste booleens inversion."""
    correspondances = []
    inversions = []
    for _, row in source.iterrows():
        key = (row["NOM_norm"], row["PRENOM_norm"])
        if key in index_cible and key[0] and key[1]:
            correspondances.append(index_cible[key])
            inversions.append(False)
            continue
        if detecter_inversion:
            key_inv = (row["PRENOM_norm"], row["NOM_norm"])
            if key_inv in index_cible and key_inv[0] and key_inv[1]:
                correspondances.append(index_cible[key_inv])
                inversions.append(True)
                continue
        correspondances.append([])
        inversions.append(False)
    return correspondances, inversions


# =========================================================================
# STATUT & MISE EN FORME
# =========================================================================

COLONNES_SUIVI = [
    "NOM", "PRENOM", "FORMULE ADOC", "Paiement", "Abonnement attendu",
    "Compte app (LiveXp)", "Solde app (indicatif)", "Inversion nom/prenom (LiveXp)",
    "C - Compte cree", "D - Adhesion validee", "E - Email envoye",
    "F - Credit octroye", "Commentaire", "Homonymie a verifier", "Statut",
]


def formater_statut(compte_app, suivi_present, compte_ok, adhesion_ok,
                    email_ok, credit_ok, annulee=False, ambig=False,
                    compte_valide=True):
    """Construit le libelle de statut affiche dans l'onglet Suivi."""
    if annulee:
        base = "ADHESION ANNULEE (inscription)"
        if compte_app:
            base += " - compte app encore present"
        return base
    if not compte_app:
        return "INSCRIT SANS COMPTE APP"
    if not compte_valide:
        statut = "COMPTE APP INVALIDE (Type_client vide)"
        if ambig:
            statut = "HOMONYMIE A VERIFIER - " + statut
        return statut
    if not suivi_present:
        return "COMPTE APP NON SUIVI (absent Suivi)"
    manquants = []
    if not compte_ok:
        manquants.append("C")
    if not adhesion_ok:
        manquants.append("D")
    if not email_ok:
        manquants.append("E")
    if not credit_ok:
        manquants.append("F")
    if manquants:
        statut = "COMPTE APP PAS A JOUR (champs: " + ",".join(manquants) + ")"
    else:
        statut = "OK"
    if ambig:
        statut = "HOMONYMIE A VERIFIER - " + statut
    return statut


def ajuster_largeurs(ws):
    """Ajuste la largeur de chaque colonne au contenu (en-tete + cellules)."""
    for col in ws.columns:
        lettre = col[0].column_letter
        longueur_max = 0
        for cell in col:
            val = "" if cell.value is None else str(cell.value)
            if len(val) > 60:
                val = val[:60]
            longueur_max = max(longueur_max, len(val))
        ws.column_dimensions[lettre].width = max(10, longueur_max + 2)
    ws.freeze_panes = "A2"


def sauvegarde_securise(chemin: str, dossier_old: str, nb_conservees: int = 5):
    """
    Copie le fichier de suivi existant avec un horodatage avant reecriture.
    Rotation : la sauvegarde la plus recente reste a cote du fichier ; les
    precedentes sont deplacees vers dossier_old, ou seules les nb_conservees
    dernieres sont conservees (les autres fichiers du dossier sont ignores).
    """
    if not os.path.exists(chemin):
        return
    base, ext = os.path.splitext(chemin)
    horodatage = datetime.now().strftime("%Y%m%d_%H%M%S")
    motif = f"{os.path.basename(base)}_sauvegarde_*{ext}"
    try:
        os.makedirs(dossier_old, exist_ok=True)
        for ancienne in glob.glob(os.path.join(os.path.dirname(chemin), motif)):
            shutil.move(ancienne, os.path.join(dossier_old, os.path.basename(ancienne)))
        cible = f"{base}_sauvegarde_{horodatage}{ext}"
        shutil.copy2(chemin, cible)
        print(f"[i] Sauvegarde precedente : {cible}")
        vieilles = sorted(glob.glob(os.path.join(dossier_old, motif)),
                          key=os.path.getmtime, reverse=True)
        for trop_vieille in vieilles[nb_conservees:]:
            os.remove(trop_vieille)
            print(f"[i] Vieille sauvegarde supprimee : {trop_vieille}")
    except Exception as e:
        print(f"[!] Sauvegarde impossible : {e}")


# =========================================================================
# MAIN
# =========================================================================

def main():
    import sys

    # --- Resolution des chemins complets depuis le dossier de travail ---
    os.makedirs(DOSSIER_TRAVAIL, exist_ok=True)
    chemin_inscriptions  = os.path.join(DOSSIER_TRAVAIL, FICHIER_INSCRIPTIONS)
    chemin_export        = os.path.join(DOSSIER_TRAVAIL, SOUS_DOSSIER_EXPORT, FICHIER_EXPORT_APP)
    chemin_suivi         = os.path.join(DOSSIER_TRAVAIL, FICHIER_SUIVI)
    chemin_ancien_suivi = os.path.join(DOSSIER_TRAVAIL, FICHIER_ANCIEN_SUIVI)

    # --- Chargement fichier 1 (inscriptions) ---------------------------
    try:
        df1 = charger_inscriptions(chemin_inscriptions)
    except FileNotFoundError:
        print(f"[!] Introuvable : {chemin_inscriptions}")
        sys.exit(1)

    # --- Chargement fichier 2 (export app) ------------------------------
    try:
        df2 = charger_export_app(chemin_export)
    except FileNotFoundError:
        print(f"[!] Introuvable : {chemin_export}")
        sys.exit(1)

    # --- Chargement du suivi (synthese existante OU ancien Suivi) -------
    suivi_source = "aucun"
    df_s = pd.DataFrame(columns=["NOM_s", "PRENOM_s", "COMPTE_s", "ADHESION_s",
                                  "EMAIL_s", "CREDIT_s", "COMMENT_s",
                                  "NOM_norm", "PRENOM_norm"])
    if os.path.exists(chemin_suivi):
        try:
            df_s = charger_suivi_xlsx(chemin_suivi)
            suivi_source = "synthese"
        except Exception as e:
            print(f"[!] Lecture {chemin_suivi} impossible : {e}")
            if os.path.exists(chemin_ancien_suivi):
                df_s = charger_ancien_suivi(chemin_ancien_suivi)
                suivi_source = "ancien_Suivi"
    elif os.path.exists(chemin_ancien_suivi):
        df_s = charger_ancien_suivi(chemin_ancien_suivi)
        suivi_source = "ancien_Suivi"

    # --- Index ----------------------------------------------------------
    idx2 = construire_index(df2)    # comptes app
    idx_s = construire_index(df_s)  # suivi existant

    # --- Appariement inscription -> LiveXp et inscription -> suivi ------
    corr1to2, inv1 = apparier(df1, idx2, detecter_inversion=True)
    corr1tos, _ = apparier(df1, idx_s, detecter_inversion=True)

    # --- Construction de l'onglet "Suivi" (1 ligne / adherent inscription) ---
    lignes_suivi = []
    lignes_annulation = []
    ambiguites = []
    for i1, row1 in df1.iterrows():
        c2 = corr1to2[i1]
        cs = corr1tos[i1]
        annulee = est_annulee(row1["INSCRIPTION_VALIDEE_f1"])
        nom_orig = row1["NOM_f1"]
        prenom_orig = row1["PRENOM_f1"]
        formule = row1["FORMULE_f1"]
        paiement = row1["PAIEMENT_f1"]
        abon_attendu = abonnement_attendu(formule)

        ambig_f2 = len(c2) > 1
        ambig_fs = len(cs) > 1

        if c2:
            row2 = df2.iloc[c2[0]]
            compte_app = True
            compte_valide = bool(row2["COMPTE_VALIDE"])
            solde = row2["SOLDE_f2"]
            inv_app = inv1[i1]
        else:
            compte_app = False
            compte_valide = True  # sans compte app, la notion d'invalide ne s'applique pas
            solde = ""
            inv_app = False

        if cs:
            row_s = df_s.iloc[cs[0]]
            suivi_present = True
            compte_s = row_s["COMPTE_s"]
            adhesion_s = row_s["ADHESION_s"]
            email_s = row_s["EMAIL_s"]
            credit_s = row_s["CREDIT_s"]
            comment_s = row_s["COMMENT_s"]
        else:
            suivi_present = False
            compte_s = ""
            adhesion_s = ""
            email_s = ""
            credit_s = ""
            comment_s = ""

        compte_ok = est_renseigne(compte_s)
        adhesion_ok = est_renseigne(adhesion_s)
        email_ok = est_renseigne(email_s)
        credit_ok = est_renseigne(credit_s)

        # Compte LiveXp invalide (Type_client vide) : force C = Invalide (ecrase
        # la saisie manuelle tant que le compte n'est pas valide dans l'app).
        if compte_app and not compte_valide:
            compte_s = VALEUR_INVALIDE
            compte_ok = False

        statut = formater_statut(
            compte_app, suivi_present, compte_ok, adhesion_ok, email_ok, credit_ok,
            annulee=annulee, ambig=(ambig_f2 or ambig_fs),
            compte_valide=compte_valide
        )

        ambig_label = ""
        if ambig_f2:
            ambig_label += f"LiveXp x{len(c2)}"
        if ambig_fs:
            ambig_label += (" + " if ambig_label else "") + f"suivi x{len(cs)}"

        if ambig_f2 or ambig_fs:
            ambiguites.append({
                "NOM (inscription)": nom_orig,
                "PRENOM (inscription)": prenom_orig,
                "Formule ADOC": formule,
                "Comptes app correspondants (LiveXp)": len(c2),
                "Lignes suivi correspondantes": len(cs),
                "Detail LiveXp": " | ".join(
                    f"{df2.iloc[j]['NOM_f2']} {df2.iloc[j]['PRENOM_f2']}" for j in c2
                ),
                "Detail suivi": " | ".join(
                    f"{df_s.iloc[j]['NOM_s']} {df_s.iloc[j]['PRENOM_s']}" for j in cs
                ),
            })

        ligne = {
            "NOM": nom_orig,
            "PRENOM": prenom_orig,
            "FORMULE ADOC": formule,
            "Paiement": paiement,
            "Abonnement attendu": abon_attendu,
            "Compte app (LiveXp)": "Oui" if compte_app else "",
            "Solde app (indicatif)": solde,
            "Inversion nom/prenom (LiveXp)": "Oui" if inv_app else "",
            "C - Compte cree": compte_s,
            "D - Adhesion validee": adhesion_s,
            "E - Email envoye": email_s,
            "F - Credit octroye": credit_s,
            "Commentaire": comment_s,
            "Homonymie a verifier": ambig_label,
            "Statut": statut,
        }
        if annulee:
            lignes_annulation.append(ligne)
        else:
            lignes_suivi.append(ligne)

    df_suivi = pd.DataFrame(lignes_suivi, columns=COLONNES_SUIVI).fillna("")
    df_annulation = pd.DataFrame(lignes_annulation, columns=COLONNES_SUIVI).fillna("")

    # --- Onglets d'analyse ----------------------------------------------

    # Compte SANS abonnement ET SANS credit octroye
    mask = (
        (df_suivi["Compte app (LiveXp)"] == "Oui")
        & (df_suivi["D - Adhesion validee"].apply(lambda v: not est_renseigne(v)))
        & (df_suivi["F - Credit octroye"].apply(lambda v: not est_renseigne(v)))
    )
    df_sans_abon_credit = df_suivi[mask][
        ["NOM", "PRENOM", "FORMULE ADOC", "Paiement", "Abonnement attendu",
         "C - Compte cree", "D - Adhesion validee", "E - Email envoye",
         "F - Credit octroye"]
    ].copy().fillna("")

    # Inscrits SANS compte app
    df_sans_compte = df_suivi[df_suivi["Compte app (LiveXp)"] != "Oui"][
        ["NOM", "PRENOM", "FORMULE ADOC", "Paiement", "Abonnement attendu", "Statut"]
    ].copy().fillna("")

    # Comptes app (LiveXp) non rattaches a une inscription
    idx1 = construire_index(df1)
    corr2to1, inv2 = apparier(df2, idx1, detecter_inversion=True)
    lignes_sans_insc = []
    for j, row2 in df2.iterrows():
        if not corr2to1[j]:
            lignes_sans_insc.append({
                "NOM (app)": row2["NOM_f2"],
                "PRENOM (app)": row2["PRENOM_f2"],
                "Solde (indicatif)": row2["SOLDE_f2"],
                "Nom/Prenom inverses": "Oui" if inv2[j] else "",
            })
    df_comptes_sans_inscription = pd.DataFrame(lignes_sans_insc).fillna("")

    # Comptes app pas a jour dans le suivi (rattaches a une inscription)
    corr2tos, _ = apparier(df2, idx_s, detecter_inversion=True)
    pas_a_jour = []
    for j, row2 in df2.iterrows():
        if not corr2to1[j]:
            continue  # non adherent, hors suivi
        if not bool(row2["COMPTE_VALIDE"]):
            continue  # compte invalide (Type_client vide) : a corriger dans l'app
        cs = corr2tos[j]
        if not cs:
            pas_a_jour.append({
                "NOM (app)": row2["NOM_f2"],
                "PRENOM (app)": row2["PRENOM_f2"],
                "Solde (indicatif)": row2["SOLDE_f2"],
                "Cas": "Absent du suivi",
                "Champs manquants": "C,D,E,F (tous)",
            })
        else:
            row_s = df_s.iloc[cs[0]]
            manquants = []
            if not est_renseigne(row_s["COMPTE_s"]):
                manquants.append("C")
            if not est_renseigne(row_s["ADHESION_s"]):
                manquants.append("D")
            if not est_renseigne(row_s["EMAIL_s"]):
                manquants.append("E")
            if not est_renseigne(row_s["CREDIT_s"]):
                manquants.append("F")
            if manquants:
                pas_a_jour.append({
                    "NOM (app)": row2["NOM_f2"],
                    "PRENOM (app)": row2["PRENOM_f2"],
                    "Solde (indicatif)": row2["SOLDE_f2"],
                    "Cas": "Present mais incomplet",
                    "Champs manquants": ",".join(manquants),
                })
    df_pas_a_jour = pd.DataFrame(pas_a_jour).fillna("")

    df_homonymies = pd.DataFrame(ambiguites).fillna("")

    # --- ECRITURE DU CLASSEUR -------------------------------------------
    os.makedirs(DOSSIER_TRAVAIL, exist_ok=True)
    out_xlsx = chemin_suivi
    sauvegarde_securise(out_xlsx, os.path.join(DOSSIER_TRAVAIL, "OLD_Docs"))

    feuilles = {
        "Suivi": df_suivi,
        "Annulation": df_annulation,
        "Compte_sans_abon_ni_credit": df_sans_abon_credit,
        "Comptes_pas_a_jour": df_pas_a_jour,
        "Inscrits_sans_compte_app": df_sans_compte,
        "Comptes_sans_inscription": df_comptes_sans_inscription,
        "Homonymies_a_verifier": df_homonymies,
    }
    with pd.ExcelWriter(out_xlsx, engine="openpyxl") as xw:
        for nom_feuille, df_feuille in feuilles.items():
            df_feuille.to_excel(xw, sheet_name=nom_feuille, index=False)
            ajuster_largeurs(xw.sheets[nom_feuille])

    # --- RAPPORT TEXTE --------------------------------------------------
    out_txt = os.path.join(DOSSIER_TRAVAIL, "rapport_analyse_comptes.txt")
    with open(out_txt, "w", encoding="utf-8") as f:
        f.write("RAPPORT D'ANALYSE DES COMPTES ADHERENTS 2026-2027\n")
        f.write("=" * 60 + "\n\n")

        f.write("1) Adherents AYANT un compte app mais SANS abonnement ET SANS credit octroye\n")
        f.write("-" * 60 + "\n")
        if df_sans_abon_credit.empty:
            f.write("   Aucun.\n")
        else:
            for _, r in df_sans_abon_credit.iterrows():
                f.write(f"   - {r['NOM']} {r['PRENOM']}  (formule: {r['FORMULE ADOC']}; "
                        f"abonnement attendu: {r['Abonnement attendu'] or 'aucun'})\n")
        f.write("\n")

        f.write("2) Personnes AYANT un compte app PAS A JOUR dans le suivi\n")
        f.write("-" * 60 + "\n")
        if df_pas_a_jour.empty:
            f.write("   Aucun.\n")
        else:
            for _, r in df_pas_a_jour.iterrows():
                f.write(f"   - {r['NOM (app)']} {r['PRENOM (app)']}  "
                        f"[{r['Cas']}] champs manquants: {r['Champs manquants']}\n")
        f.write("\n")

        f.write("3) Inscrits SANS compte dans l'application\n")
        f.write("-" * 60 + "\n")
        if df_sans_compte.empty:
            f.write("   Aucun.\n")
        else:
            for _, r in df_sans_compte.iterrows():
                f.write(f"   - {r['NOM']} {r['PRENOM']}  (formule: {r['FORMULE ADOC']})\n")
        f.write("\n")

        f.write("4) Comptes app non rattaches a une inscription (non-adherents / location)\n")
        f.write("-" * 60 + "\n")
        if df_comptes_sans_inscription.empty:
            f.write("   Aucun.\n")
        else:
            for _, r in df_comptes_sans_inscription.iterrows():
                inv = " [nom/prenom inverses]" if r["Nom/Prenom inverses"] == "Oui" else ""
                f.write(f"   - {r['NOM (app)']} {r['PRENOM (app)']}{inv}\n")
        f.write("\n")

        f.write("5) Homonymies / correspondances ambigues a verifier manuellement\n")
        f.write("-" * 60 + "\n")
        if df_homonymies.empty:
            f.write("   Aucune.\n")
        else:
            for _, r in df_homonymies.iterrows():
                f.write(
                    f"   - {r['NOM (inscription)']} {r['PRENOM (inscription)']}  "
                    f"(LiveXp: {r['Comptes app correspondants (LiveXp)']} ; "
                    f"suivi: {r['Lignes suivi correspondantes']})\n"
                )
                if str(r["Detail LiveXp"]):
                    f.write(f"       LiveXp -> {r['Detail LiveXp']}\n")
                if str(r["Detail suivi"]):
                    f.write(f"       suivi  -> {r['Detail suivi']}\n")
        f.write("\n")

        f.write("6) Adhesions annulees (inscription, colonne V)\n")
        f.write("-" * 60 + "\n")
        if df_annulation.empty:
            f.write("   Aucune.\n")
        else:
            for _, r in df_annulation.iterrows():
                f.write(f"   - {r['NOM']} {r['PRENOM']}  (formule: {r['FORMULE ADOC']}; "
                        f"statut: {r['Statut']})\n")
        f.write("\n")

        f.write("7) Synthese globale\n")
        f.write("-" * 60 + "\n")
        f.write(f"   Inscrits (inscription)         : {len(df1)}\n")
        f.write(f"     dont annulations             : {len(df_annulation)}\n")
        f.write(f"   Comptes app (LiveXp)          : {len(df2)}\n")
        f.write(f"   Lignes suivi (source)         : {len(df_s)} ({suivi_source})\n")
        f.write(f"   Adherents suivis (onglet Suivi): {len(df_suivi)}\n")
        f.write(f"   Comptes sans abonnement/credit: {len(df_sans_abon_credit)}\n")
        f.write(f"   Comptes pas a jour (suivi)    : {len(df_pas_a_jour)}\n")
        f.write(f"   Inscrits sans compte app     : {len(df_sans_compte)}\n")
        f.write(f"   Comptes sans inscription      : {len(df_comptes_sans_inscription)}\n")
        f.write(f"   Homonymies a verifier        : {len(df_homonymies)}\n")

    print(f"[OK] Classeur ecrit   : {out_xlsx}")
    print(f"[OK] Rapport ecrit    : {out_txt}")


if __name__ == "__main__":
    main()
