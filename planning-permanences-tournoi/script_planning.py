# -*- coding: utf-8 -*-
"""
Génération du planning de permanences — Tournoi de tennis (17/10 -> 7/11)

Ce script :
  1. lit la feuille de disponibilités ("Feuil1") du classeur,
  2. résout l'affectation optimale des personnes aux créneaux :
       - au moins 1 personne par créneau (si possible),
       - jamais 2 créneaux le même jour pour une même personne,
       - jamais 2 jours consécutifs pour une même personne, SAUF si la
         colonne "2 jours consécutifs" est cochée (O) pour elle ; l'enchaine-
         ment D (21h-fin) + A (9h-13h) le lendemain reste interdit sauf si
         la colonne "Soir+Matin" est aussi cochée (facultatif, 2 colonnes
         placées juste après le NOM dans Feuil1),
       - au plus MAX_TOTAL (6) permanences par personne sur tout le tournoi,
       - au plus MAX_PAR_SEMAINE (4) permanences par personne et par semaine,
       - minimise le nombre de créneaux non couverts,
       - priorise les personnes ayant proposé le moins de disponibilités,
       - répartit la charge au maximum entre les personnes.
  3. écrit DEUX feuilles de planning dans le même classeur :
       - "planning 1 site"  : site principal (A 9-13, B 13-17, C 17-21, D 21-fin)
       - "planning 2 sites" : site principal + second site sur les créneaux
         du soir uniquement (C 17-21 et D 21-fin).
     Les deux plannings sont résolus indépendamment : une personne peut donc
     apparaître sur des créneaux différents dans chaque feuille.
  4. présentation en 3 blocs de 6 jours + le bloc finale, comme la feuille
     d'origine.

Dépendances : openpyxl, scipy (pip install openpyxl scipy)
"""

import re
from collections import defaultdict

import numpy as np
from openpyxl import load_workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from scipy.optimize import Bounds, LinearConstraint, milp

# ----------------------------------------------------------------- CONFIG ---
FICHIER = r"P:/2026-2027/Bureau/Championnats - Tournois/TOURNOI AUTOMNE PERMANENCES_fusion.xlsx"
FEUILLE_DISPO = "Feuil1"
FEUILLE_1_SITE = "planning 1 site"
FEUILLE_2_SITES = "planning 2 sites"

SLOTS = ["9-13", "13-17", "17-21", "21-fin"]
LABELS_SLOTS = ["A 9h-13h", "B 13h-17h", "C 17h-21h", "D 21h-fin"]

# plafonds de charge par personne
MAX_TOTAL = 6        # permanences max sur la durée du tournoi
MAX_PAR_SEMAINE = 4  # permanences max par semaine (bloc de 6 jours + finale)

JOUR_RE = re.compile(r"^\S.*\d{1,2}/\d{1,2}")  # ex. "Sam 17/10"
SLOT_VALS = {"9-13", "13-17", "17-21", "21-fin"}

# site 2 : créneaux du soir uniquement (indices 2=C et 3=D)
SLOTS_SITE2 = (2, 3)


# ------------------------------------------------------------ LECTURE XLSX ---
def _sans_accent(s):
    return (s.replace("é", "e").replace("è", "e").replace("ê", "e")
             .replace("à", "a").replace("ç", "c").lower())


def lire_dispos(fichier, feuille):
    """Retourne (jours, dispos, options).
    jours   : liste de dict {label, nslots}
    dispos  : dict nom -> {(jour, slot) -> valeur}
    options : dict nom -> {"consecutifs": bool, "soir_matin": bool}
              lu dans 2 colonnes placées juste après le NOM (facultatif) :
              - "2 jours consecutifs" : O = peut faire 2 jours de suite
              - "Soir+Matin"          : O = peut enchainer D puis A le
                lendemain (implique l'autorisation des 2 jours de suite)
    """
    wb = load_workbook(fichier, data_only=True)
    ws = wb[feuille]
    rows = [
        [str(c).strip() if c is not None else "" for c in r]
        for r in ws.iter_rows(values_only=True)
    ]

    day_rows = [
        i for i, r in enumerate(rows)
        if any(JOUR_RE.match(c) for c in r if c)
        and not any(c in SLOT_VALS for c in r if c)
    ]

    jours = []
    dispos = defaultdict(dict)
    options = defaultdict(dict)          # nom -> {"consecutifs": bool, "soir_matin": bool}
    opt_consec_col, opt_da_col = None, None   # colonnes des 2 options
    day_index = -1
    for hr in day_rows:
        r = rows[hr]
        nom_row = rows[hr + 1]
        labels = [(j, c) for j, c in enumerate(r) if JOUR_RE.match(c)]
        block = []
        for k, (j, c) in enumerate(labels):
            end = labels[k + 1][0] if k + 1 < len(labels) else len(r)
            day_index += 1
            if "FINALE" in c.upper():
                nsl, cols = 2, [j, j + 4]
            else:
                span = nom_row[j:end]
                nsl = max(len([x for x in span if x in SLOT_VALS]), 1)
                cols = [j + s for s in range(nsl)]
            block.append((day_index, cols, nsl, c))
            jours.append({"label": c, "nslots": nsl})

        # détection des colonnes d'options (juste après le NOM, avant le
        # premier jour) : les intitulés peuvent être sur la ligne des jours
        # (au-dessus de NOM) ou sur la ligne NOM elle-même
        if opt_consec_col is None and labels:
            first_day_col = labels[0][0]
            for entete_row in (r, nom_row):
                for col in range(1, first_day_col):
                    h = _sans_accent(entete_row[col] if col < len(entete_row) else "")
                    if "cons" in h:
                        opt_consec_col = col
                    elif "soir" in h or "matin" in h:
                        opt_da_col = col

        pr = hr + 2
        while pr < len(rows) and rows[pr] and rows[pr][0] and rows[pr][0] != "NOM":
            nom = rows[pr][0]
            if JOUR_RE.match(nom):
                pr += 1
                continue
            for (di, cols, nsl, lab) in block:
                for s, col in enumerate(cols):
                    v = rows[pr][col] if col < len(rows[pr]) else ""
                    if v:
                        dispos[nom][(di, s)] = v
            # colonnes d'options individuelles (facultatives)
            if opt_consec_col is not None or opt_da_col is not None:
                v1 = rows[pr][opt_consec_col] if (opt_consec_col is not None
                        and opt_consec_col < len(rows[pr])) else ""
                v2 = rows[pr][opt_da_col] if (opt_da_col is not None
                        and opt_da_col < len(rows[pr])) else ""
                consec = str(v1).strip().upper() == "O"
                da = str(v2).strip().upper() == "O"
                options[nom] = {"consecutifs": consec, "soir_matin": da}
            pr += 1
    return jours, dict(dispos), dict(options)


def est_dispo(valeur):
    """'O' -> dispo complète ; '> 18h' / '> 14h' -> dispo partielle."""
    return valeur == "O" or valeur.startswith(">")


# ---------------------------------------------------------- OPTIMISATION ----
def creneaux_scenario(jours, avec_site2):
    """Liste des créneaux du scénario : tuples (jour, slot, site).
    site = 1 (principal) ou 2 (second site, soirées uniquement).
    """
    out = []
    for d, j in enumerate(jours):
        for s in range(j["nslots"]):
            out.append((d, s, 1))
            if avec_site2 and s in SLOTS_SITE2:
                out.append((d, s, 2))
    return out


def resoudre(jours, dispos, avec_site2, options=None):
    """Résout l'affectation pour un scénario (site 2 inclus ou non).
    Retourne (affectations, non_couverts, charge).
    """
    creneaux = creneaux_scenario(jours, avec_site2)
    nD = len(jours)

    noms = sorted(
        n for n, cells in dispos.items()
        if any(v in ("O", "N") or v.startswith(">") for v in cells.values())
    )
    # variables d'affectation : une personne peut tenir le même créneau horaire
    # sur le site 1 ou le site 2 (sa dispo horaire s'applique aux deux)
    idx = {}
    for n in noms:
        for (d, s, site) in creneaux:
            v = dispos.get(n, {}).get((d, s), "")
            if d < nD and s < jours[d]["nslots"] and est_dispo(v):
                idx[(n, d, s, site)] = len(idx)
    nA = len(idx)

    yidx = {c: nA + i for i, c in enumerate(creneaux)}
    nTot = nA + len(yidx) + 1
    zmax = nTot - 1

    cov = defaultdict(list)
    for (n, d, s, site), vi in idx.items():
        cov[(d, s, site)].append((n, vi))

    A, lb, ub = [], [], []
    # 1 créneau (site donné) = au moins 1 personne (ou variable d'écart)
    for (d, s, site), yi in yidx.items():
        row = np.zeros(nTot)
        for n, vi in cov.get((d, s, site), []):
            row[vi] = 1
        row[yi] = 1
        A.append(row); lb.append(1); ub.append(np.inf)
    # 1 seul créneau par personne et par jour (tous sites confondus)
    perday = defaultdict(list)
    for (n, d, s, site), vi in idx.items():
        perday[(n, d)].append(vi)
    for vs in perday.values():
        row = np.zeros(nTot)
        for v in vs:
            row[v] = 1
        A.append(row); lb.append(-np.inf); ub.append(1)
    # jours consécutifs : règle par personne (tous sites confondus)
    #   - par défaut : jamais 2 jours de suite ;
    #   - option "2 jours consecutifs" : autorisé, SAUF l'enchainement
    #     D (21h-fin) le soir + A (9h-13h) le lendemain, interdit sauf si
    #     l'option "Soir+Matin" est aussi cochée pour cette personne.
    options = options or {}
    for n in noms:
        opt = options.get(n, {})
        consec = opt.get("consecutifs", False)
        da_ok = opt.get("soir_matin", False)
        for d in range(nD - 1):
            v1 = [vi for (nn, dd, s, site), vi in idx.items()
                  if nn == n and dd == d]
            v2 = [vi for (nn, dd, s, site), vi in idx.items()
                  if nn == n and dd == d + 1]
            if not (v1 and v2):
                continue
            if not consec:
                # contrainte stricte : au plus 1 créneau sur les 2 jours
                row = np.zeros(nTot)
                for v in v1 + v2:
                    row[v] = 1
                A.append(row); lb.append(-np.inf); ub.append(1)
            elif not da_ok:
                # 2 jours de suite autorisés, mais jamais D puis A
                vd = [vi for (nn, dd, s, site), vi in idx.items()
                      if nn == n and dd == d and s == jours[d]["nslots"] - 1]
                va = [vi for (nn, dd, s, site), vi in idx.items()
                      if nn == n and dd == d + 1 and s == 0]
                if vd and va:
                    row = np.zeros(nTot)
                    for v in vd + va:
                        row[v] = 1
                    A.append(row); lb.append(-np.inf); ub.append(1)
    # charge <= max global (équilibrage, phase suivante)
    perpers = defaultdict(list)
    for (n, d, s, site), vi in idx.items():
        perpers[n].append(vi)
    for vs in perpers.values():
        row = np.zeros(nTot)
        for v in vs:
            row[v] = 1
        row[zmax] = -1
        A.append(row); lb.append(-np.inf); ub.append(0)
    # plafond global : au plus MAX_TOTAL permanences sur tout le tournoi
    for vs in perpers.values():
        row = np.zeros(nTot)
        for v in vs:
            row[v] = 1
        A.append(row); lb.append(-np.inf); ub.append(MAX_TOTAL)
    # plafond hebdomadaire : au plus MAX_PAR_SEMAINE par bloc de 6 jours
    persem = defaultdict(list)
    for (n, d, s, site), vi in idx.items():
        persem[(n, min(d // 6, 3))].append(vi)
    for vs in persem.values():
        row = np.zeros(nTot)
        for v in vs:
            row[v] = 1
        A.append(row); lb.append(-np.inf); ub.append(MAX_PAR_SEMAINE)

    cons = LinearConstraint(np.array(A), lb, ub)
    integrality = np.ones(nTot)
    bounds = Bounds(np.zeros(nTot), np.ones(nTot))
    bounds.lb[zmax] = 0.0
    bounds.ub[zmax] = np.inf

    # objectif, par ordre de priorité décroissante :
    #   1. minimiser les créneaux non couverts (poids écrasant),
    #   2. PRIO AUX PETITES DISPOS : affecter une personne coûte
    #      proportionnellement à son nombre total de disponibilités,
    #   3. PRÉFÉRENCE SITE 1 : petit surcoût pour chaque affectation sur le
    #      site 2 — si une seule personne est disponible sur un créneau,
    #      elle est donc placée sur le site 1 en priorité (le site 2 n'est
    #      rempli que par des personnes supplémentaires),
    #   4. équilibrer la charge (poids très faible).
    nb_dispo = defaultdict(int)
    for (n, d, s), v in [(k, v) for k, v in
                         ((kk, dispos.get(kk[0], {}).get((kk[1], kk[2]), ""))
                          for kk in [(n, d, s) for (n, d, s, site) in idx])]:
        if est_dispo(v):
            nb_dispo[n] += 1

    c = np.zeros(nTot)
    # poids des trous : un trou sur un créneau A/B en semaine (jours ouvrés)
    # est moins grave (vous l'avez indiqué) -> pénalité réduite, le solveur
    # déplace donc les trous vers ces créneaux quand c'est possible.
    for (d, s, site), yi in yidx.items():
        we = jours[d]["label"].strip().lower()[:3] in ("sam", "dim")
        grave = (not we) and s in (0, 1)
        c[yi] = 200000.0 if grave else 1000000.0
    for (n, d, s, site), vi in idx.items():
        c[vi] = float(nb_dispo[n]) + (0.0005 if site == 2 else 0.0)
    c[zmax] = 0.00001

    res = milp(c=c, constraints=cons, integrality=integrality, bounds=bounds)
    if res.status != 0:
        raise RuntimeError(f"Solveur en échec : {res.message}")

    sol = np.round(res.x).astype(int)
    affect = defaultdict(list)              # (jour, slot, site) -> [noms]
    charge = defaultdict(int)
    for (n, d, s, site), vi in idx.items():
        if sol[vi] == 1:
            affect[(d, s, site)].append(n)
            charge[n] += 1
    non_couverts = [k for k, yi in yidx.items() if sol[yi] == 1]
    return affect, non_couverts, dict(charge), noms


# ------------------------------------------------------------ ÉCRITURE ------
ENTETE_FILL = PatternFill("solid", fgColor="1F4E78")
ENTETE_FONT = Font(bold=True, color="FFFFFF", size=11)
JOUR_FILL = PatternFill("solid", fgColor="D9E1F2")
SITE2_FILL = PatternFill("solid", fgColor="FFF2CC")
TROU_FONT = Font(bold=True, color="C00000")
BORD = Border(*[Side(style="thin")] * 4)
CENTRE = Alignment(horizontal="center", vertical="center")
GAUCHE = Alignment(horizontal="left", vertical="center", indent=1)


def lignes_scenario(avec_site2, nslots):
    """Lignes d'un bloc : liste (slot, site, libellé de ligne).
    Site 1 : une ligne par créneau horaire. Site 2 : ligne insérée
    JUSTE EN DESSOUS du créneau horaire correspondant (C site 2 sous C,
    D site 2 sous D), pour ne pas élargir le planning vers la droite.
    """
    lignes = []
    for s in range(nslots):
        lignes.append((s, 1, LABELS_SLOTS[s]))
        if avec_site2 and s in SLOTS_SITE2:
            lignes.append((s, 2, f"{LABELS_SLOTS[s]} (site 2)"))
    return lignes


def ecrire_planning(wb, nom_feuille, jours, affect, non_couverts, charge,
                    dispos, avec_site2):
    if nom_feuille in wb.sheetnames:
        del wb[nom_feuille]
    ws = wb.create_sheet(nom_feuille)
    ws.sheet_view.showGridLines = False

    # découpage en blocs de 6 jours (comme la feuille d'origine) + finale
    blocs = []
    d = 0
    while d < len(jours) and jours[d]["nslots"] == 4:
        blocs.append(list(range(d, min(d + 6, len(jours)))))
        d += 6
    if d < len(jours):
        blocs.append(list(range(d, len(jours))))  # bloc finale

    row = 1
    for bi, bloc in enumerate(blocs, start=1):
        titre = f"Semaine {bi}" + (" (FINALE)" if any(jours[di]["nslots"] < 4 for di in bloc) else "")
        ws.cell(row=row, column=1, value=titre).font = Font(bold=True, size=12)
        row += 1

        # ligne 1 : labels des jours (alignés à gauche), 4 colonnes par jour
        for c, di in enumerate(bloc):
            col = 2 + c * 4
            cell = ws.cell(row=row, column=col, value=jours[di]["label"])
            cell.fill, cell.font, cell.border = (JOUR_FILL, Font(bold=True), BORD)
            cell.alignment = GAUCHE
            for k in range(1, jours[di]["nslots"]):
                cc = ws.cell(row=row, column=col + k)
                cc.fill, cc.border = JOUR_FILL, BORD
        row += 1

        # ligne 2 : libellés de créneaux (une colonne par créneau horaire)
        for c, di in enumerate(bloc):
            for s in range(jours[di]["nslots"]):
                cell = ws.cell(row=row, column=2 + c * 4 + s, value=LABELS_SLOTS[s])
                cell.fill, cell.font, cell.alignment, cell.border = (
                    ENTETE_FILL, ENTETE_FONT, CENTRE, BORD)
        row += 1

        # lignes d'affectation : une ligne par (créneau, site).
        # Les lignes du site 2 sont ajoutées sous celles du site 1.
        lignes = lignes_scenario(avec_site2, jours[bloc[0]]["nslots"])
        for (s, site, lab) in lignes:
            cell = ws.cell(row=row, column=1, value=lab)
            cell.font = Font(bold=True, italic=(site == 2))
            for c, di in enumerate(bloc):
                if s >= jours[di]["nslots"]:
                    continue
                col = 2 + c * 4 + s
                if (di, s, site) in affect:
                    txts = []
                    for n in affect[(di, s, site)]:
                        v = dispos.get(n, {}).get((di, s), "O")
                        txts.append(f"{n} ({v})" if v.startswith(">") else n)
                    cell2 = ws.cell(row=row, column=col, value="\n".join(txts))
                    cell2.alignment, cell2.border = CENTRE, BORD
                    if site == 2:
                        cell2.fill = SITE2_FILL
                else:
                    cell2 = ws.cell(row=row, column=col, value="!! À POURVOIR")
                    cell2.font, cell2.alignment, cell2.border = TROU_FONT, CENTRE, BORD
                    if site == 2:
                        cell2.fill = SITE2_FILL
            row += 1
        row += 1  # ligne vide entre les blocs

    # récapitulatif des charges (avec entête des plafonds configurés)
    ws.cell(row=row, column=1,
            value="Charge par personne (créneaux tenus) :").font = Font(bold=True)
    row += 1
    tete = ws.cell(row=row, column=1, value="NOM")
    tete.font = Font(bold=True, color="FFFFFF")
    tete.fill = ENTETE_FILL
    tete.alignment = CENTRE
    tete.border = BORD
    for col, txt in ((2, f"Total (max {MAX_TOTAL})"),
                     (3, f"Sem (max {MAX_PAR_SEMAINE})")):
        c2 = ws.cell(row=row, column=col, value=txt)
        c2.font = Font(bold=True, color="FFFFFF")
        c2.fill = ENTETE_FILL
        c2.alignment = CENTRE
        c2.border = BORD
    row += 1
    sem_par_pers = defaultdict(lambda: defaultdict(int))
    for (d, s, site), noms_slot in affect.items():
        for n in noms_slot:
            sem_par_pers[n][min(d // 6, 3)] += 1
    for n in sorted(charge, key=lambda x: (-charge[x], x)):
        ws.cell(row=row, column=1, value=n).border = BORD
        ct = ws.cell(row=row, column=2, value=charge[n])
        ct.alignment, ct.border = CENTRE, BORD
        if charge[n] >= MAX_TOTAL:
            ct.font = Font(bold=True, color="C00000")
        maxi = max(sem_par_pers[n].values()) if sem_par_pers[n] else 0
        cs = ws.cell(row=row, column=3, value=maxi)
        cs.alignment, cs.border = CENTRE, BORD
        if maxi >= MAX_PAR_SEMAINE:
            cs.font = Font(bold=True, color="C00000")
        row += 1
    ws.cell(row=row, column=1, value="Créneaux non couverts :").font = Font(bold=True)
    ws.cell(row=row, column=2, value=len(non_couverts)).font = TROU_FONT
    ws.cell(row=row + 1, column=1,
            value=", ".join(
                f"{jours[d]['label']} {LABELS_SLOTS[s]}" + (f" [site {site}]" if site == 2 else "")
                for d, s, site in non_couverts))

    # largeurs de colonnes
    ws.column_dimensions["A"].width = 16
    ncol_max = 2 + 6 * 4
    for c in range(2, ncol_max):
        ws.column_dimensions[get_column_letter(c)].width = 13


# ------------------------------------------------------------------ MAIN ----
def main():
    jours, dispos, options = lire_dispos(FICHIER, FEUILLE_DISPO)
    nb_consec = sum(1 for o in options.values() if o.get("consecutifs"))
    nb_da = sum(1 for o in options.values() if o.get("soir_matin"))
    if options:
        print(f"Options individuelles : {nb_consec} personne(s) autorisée(s) "
              f"en 2 jours consécutifs, {nb_da} en enchained Soir+Matin.")
    else:
        print("Pas de colonnes d'options détectées (2 jours consecutifs / "
              "Soir+Matin) : contraintes strictes pour tout le monde.")
    total = sum(j["nslots"] for j in jours)
    print(f"{len(jours)} jours, {total} créneaux (1 site), "
          f"{total + 2 * sum(1 for j in jours if j['nslots'] == 4)} (2 sites).")

    wb = load_workbook(FICHIER)  # sans data_only pour préserver la feuille

    for nom_feuille, avec_site2 in ((FEUILLE_1_SITE, False), (FEUILLE_2_SITES, True)):
        affect, non_couverts, charge, noms = resoudre(jours, dispos, avec_site2, options)
        nb = len(creneaux_scenario(jours, avec_site2))
        site_txt = "2 sites" if avec_site2 else "1 site"
        print(f"\n--- Planning {site_txt} ---")
        print(f"Personnes mobilisées : {len(charge)}")
        print(f"Créneaux couverts    : {nb - len(non_couverts)}/{nb}")
        print(f"Créneaux à pourvoir  : {len(non_couverts)}")
        for d, s, site in non_couverts:
            print(f"   - {jours[d]['label']}  {LABELS_SLOTS[s]}"
                  + (f" [site {site}]" if site == 2 else ""))
        ecrire_planning(wb, nom_feuille, jours, affect, non_couverts,
                        charge, dispos, avec_site2)
        print(f"Feuille « {nom_feuille} » écrite")

    try:
        wb.save(FICHIER)
    except PermissionError:
        print("\n*** ERREUR : le classeur n'a pas pu être enregistré. ***")
        print("    Il est probablement encore ouvert dans Excel (ou verrouillé")
        print("    par un autre programme / une synchronisation OneDrive).")
        print("    Fermez complètement Excel puis relancez le script.")
        raise SystemExit(1)

    # vérification : relire le classeur et confirmer que les 2 feuilles y sont
    from openpyxl import load_workbook as _lw
    wb_verif = _lw(FICHIER, read_only=True)
    manquantes = [f for f in (FEUILLE_1_SITE, FEUILLE_2_SITES)
                  if f not in wb_verif.sheetnames]
    wb_verif.close()
    if manquantes:
        print(f"\n*** ALERTE : feuilles absentes après enregistrement : {manquantes}")
        print("    Le fichier a probablement été réécrit après la sauvegarde")
        print("    (Excel ouvert, synchronisation OneDrive/lecteur réseau...).")
        raise SystemExit(1)
    print(f"\nClasseur enregistré et vérifié : {FICHIER}")
    print(f"Feuilles : {', '.join(wb.sheetnames)}")


if __name__ == "__main__":
    main()
