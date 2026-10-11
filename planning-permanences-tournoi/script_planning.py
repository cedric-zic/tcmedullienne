# -*- coding: utf-8 -*-
"""
Génération du planning de permanences — Tournoi de tennis (17/10 -> 7/11)

Ce script :
  1. lit la feuille de disponibilités ("Feuil1") du classeur,
  2. résout l'affectation optimale des personnes aux créneaux :
       - au moins 1 personne par créneau (si possible),
       - jamais 2 créneaux le même jour pour une même personne,
       - jamais 2 jours consécutifs pour une même personne
         (élimine de fait le cas "créneau D le soir + créneau A le lendemain"),
       - au plus MAX_TOTAL (6) permanences par personne sur tout le tournoi,
       - au plus MAX_PAR_SEMAINE (4) permanences par personne et par semaine,
       - minimise le nombre de créneaux non couverts,
       - priorise les personnes ayant proposé le moins de disponibilités,
       - répartit la charge au maximum entre les personnes.
  3. ajoute (ou remplace) une feuille "PLANNING" dans le même classeur,
     avec une présentation en 3 blocs de 6 jours comme la feuille d'origine.

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
FEUILLE_PLANNING = "PLANNING"

SLOTS = ["9-13", "13-17", "17-21", "21-fin"]
LABELS_SLOTS = ["A 9h-13h", "B 13h-17h", "C 17h-21h", "D 21h-fin"]

# plafonds de charge par personne
MAX_TOTAL = 6        # permanences max sur la durée du tournoi
MAX_PAR_SEMAINE = 4  # permanences max par semaine (bloc de 6 jours + finale)

JOUR_RE = re.compile(r"^\S.*\d{1,2}/\d{1,2}")  # ex. "Sam 17/10"
SLOT_VALS = {"9-13", "13-17", "17-21", "21-fin"}


# ------------------------------------------------------------ LECTURE XLSX ---
def lire_dispos(fichier, feuille):
    """Retourne (jours, dispos).
    jours : liste de dict {label, nslots}
    dispos : dict (nom, jour, slot) -> valeur ('O', 'N', '> 18h', ...)
    """
    wb = load_workbook(fichier, data_only=True)
    ws = wb[feuille]
    rows = [
        [str(c).strip() if c is not None else "" for c in r]
        for r in ws.iter_rows(values_only=True)
    ]

    # lignes d'en-tête de jours : contiennent une date mais pas de libellé "9-13"
    day_rows = [
        i for i, r in enumerate(rows)
        if any(JOUR_RE.match(c) for c in r if c)
        and not any(c in SLOT_VALS for c in r if c)
    ]

    jours = []
    dispos = defaultdict(dict)  # nom -> {(jour, slot): valeur}
    day_index = -1
    for hr in day_rows:
        r = rows[hr]
        nom_row = rows[hr + 1]
        labels = [(j, c) for j, c in enumerate(r) if JOUR_RE.match(c)]
        block = []  # (idx, colonne_premier_slot, nb_slots, label, colonnes)
        for k, (j, c) in enumerate(labels):
            end = labels[k + 1][0] if k + 1 < len(labels) else len(r)
            day_index += 1
            if "FINALE" in c.upper():
                # cas particulier de la dernière feuille : créneaux A et B
                # positionnés dans 2 sous-colonnaires espacés (j et j+4)
                cols = [j, j + 4]
                nsl = 2
            else:
                span = nom_row[j:end]
                nsl = max(len([x for x in span if x in SLOT_VALS]), 1)
                cols = [j + s for s in range(nsl)]
            block.append((day_index, cols, nsl, c))
            jours.append({"label": c, "nslots": nsl})

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
            pr += 1
    return jours, dict(dispos)


def est_dispo(valeur):
    """'O' -> dispo complète ; '> 18h' / '> 14h' -> dispo partielle."""
    return valeur == "O" or valeur.startswith(">")


# ---------------------------------------------------------- OPTIMISATION ----
def resoudre(jours, dispos):
    """Affectation en 2 phases :
    phase 1 : minimiser les créneaux non couverts ;
    phase 2 : à couverture égale, équilibrer la charge (minimiser le max).
    Retourne (affectations, non_couverts, charge).
    """
    nD = len(jours)
    # personnes ayant répondu (au moins un O / N / >xx)
    noms = sorted(
        n for n, cells in dispos.items()
        if any(v in ("O", "N") or v.startswith(">") for v in cells.values())
    )
    # variables d'affectation
    idx = {}
    for n in noms:
        for (d, s), v in dispos.get(n, {}).items():
            if d < nD and s < jours[d]["nslots"] and est_dispo(v):
                idx[(n, d, s)] = len(idx)
    nA = len(idx)
    # variables de non-couverture y[d,s]
    yidx = {}
    for d in range(nD):
        for s in range(jours[d]["nslots"]):
            yidx[(d, s)] = nA + len(yidx)
    nY = len(yidx)
    nTot = nA + nY + 1  # +1 : variable de charge max (phase 2)
    zmax = nTot - 1

    # couverture par créneau
    cov = defaultdict(list)
    for (n, d, s) in idx:
        cov[(d, s)].append(n)

    A, lb, ub = [], [], []
    # 1 créneau = au moins 1 personne (ou variable d'écart)
    for key, yi in yidx.items():
        row = np.zeros(nTot)
        for n in cov.get(key, []):
            row[idx[(n, *key)]] = 1
        row[yi] = 1
        A.append(row); lb.append(1); ub.append(np.inf)
    # 1 seul créneau par personne et par jour
    perday = defaultdict(list)
    for (n, d, s), vi in idx.items():
        perday[(n, d)].append(vi)
    for vs in perday.values():
        row = np.zeros(nTot)
        for v in vs:
            row[v] = 1
        A.append(row); lb.append(-np.inf); ub.append(1)
    # jamais 2 jours consécutifs pour une même personne
    for n in noms:
        for d in range(nD - 1):
            v1 = [idx[(n, d, s)] for s in range(jours[d]["nslots"]) if (n, d, s) in idx]
            v2 = [idx[(n, d + 1, s)] for s in range(jours[d + 1]["nslots"]) if (n, d + 1, s) in idx]
            if v1 and v2:
                row = np.zeros(nTot)
                for v in v1 + v2:
                    row[v] = 1
                A.append(row); lb.append(-np.inf); ub.append(1)
    # charge d'une personne <= max global (phase 2)
    perpers = defaultdict(list)
    for (n, d, s), vi in idx.items():
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
    # (les blocs correspondent aux semaines affichées : jours 0-5, 6-11,
    # 12-17, puis 18-21 pour la semaine de la finale)
    persem = defaultdict(list)
    for (n, d, s), vi in idx.items():
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
    #      proportionnellement à son nombre total de disponibilités.
    #      À nombre de créneaux couverts égal, le solveur privilégie ainsi
    #      toujours les personnes qui ont proposé le moins de créneaux
    #      (celle qui n'en propose que 3 obtient ses 3 créneaux, même si
    #      5 personnes très disponibles sont aussi sur ces créneaux),
    #   3. équilibrer la charge (poids très faible sur la charge max).
    nb_dispo = defaultdict(int)
    for (n, d, s) in idx:
        nb_dispo[n] += 1

    c = np.zeros(nTot)
    for yi in yidx.values():
        c[yi] = 1000000.0
    for (n, d, s), vi in idx.items():
        c[vi] = float(nb_dispo[n])      # moins de dispos -> moins cher -> prioritaire
    c[zmax] = 0.001                      # équilibrage, très en dessous de la priorité

    res = milp(c=c, constraints=cons, integrality=integrality, bounds=bounds)
    if res.status != 0:
        raise RuntimeError(f"Solveur en échec : {res.message}")

    sol = np.round(res.x).astype(int)
    affect = defaultdict(dict)             # (jour, slot) -> [noms]
    charge = defaultdict(int)
    for (n, d, s), vi in idx.items():
        if sol[vi] == 1:
            affect[(d, s)][n] = True
            charge[n] += 1
    non_couverts = [k for k, yi in yidx.items() if sol[yi] == 1]
    return affect, non_couverts, dict(charge), noms


# ------------------------------------------------------------ ÉCRITURE ------
ENTETE_FILL = PatternFill("solid", fgColor="1F4E78")
ENTETE_FONT = Font(bold=True, color="FFFFFF", size=11)
JOUR_FILL = PatternFill("solid", fgColor="D9E1F2")
TROU_FONT = Font(bold=True, color="C00000")
PARTIEL_FONT = Font(italic=True)
BORD = Border(*[Side(style="thin")] * 4)
CENTRE = Alignment(horizontal="center", vertical="center")


def ecrire_planning(wb, jours, affect, non_couverts, charge, noms, dispos):
    if FEUILLE_PLANNING in wb.sheetnames:
        del wb[FEUILLE_PLANNING]
    ws = wb.create_sheet(FEUILLE_PLANNING)
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
        titre = f"Semaine {bi}" + (" (FINALE)" if jours[bloc[0]]["nslots"] < 4 else "")
        ws.cell(row=row, column=1, value=titre).font = Font(bold=True, size=12)
        row += 1
        # en-tête : label du jour sur la 1re colonne de chaque jour
        for c, di in enumerate(bloc):
            col = 2 + c * 4
            cell = ws.cell(row=row, column=col, value=jours[di]["label"])
            cell.fill, cell.font, cell.alignment, cell.border = (
                JOUR_FILL, Font(bold=True), CENTRE, BORD)
            for k in range(1, 4):
                ws.cell(row=row, column=col + k).border = BORD
                ws.cell(row=row, column=col + k).fill = JOUR_FILL
        row += 1
        # en-tête : libellés de créneau
        for c, di in enumerate(bloc):
            col = 2 + c * 4
            for s in range(jours[di]["nslots"]):
                cell = ws.cell(row=row, column=col + s, value=LABELS_SLOTS[s])
                cell.fill, cell.font, cell.alignment, cell.border = (
                    ENTETE_FILL, ENTETE_FONT, CENTRE, BORD)
        row += 1
        # affectations : une ligne par créneau
        for s in range(4):
            ws.cell(row=row, column=1, value=LABELS_SLOTS[s]).font = Font(bold=True)
            for c, di in enumerate(bloc):
                if s >= jours[di]["nslots"]:
                    continue
                col = 2 + c * 4 + s
                if (di, s) in affect:
                    noms_slot = list(affect[(di, s)])
                    txts = []
                    for n in noms_slot:
                        v = dispos.get(n, {}).get((di, s), "O")
                        txts.append(f"{n} ({v})" if v.startswith(">") else n)
                    cell = ws.cell(row=row, column=col, value="\n".join(txts))
                    cell.alignment, cell.border = CENTRE, BORD
                else:
                    cell = ws.cell(row=row, column=col, value="!! À POURVOIR")
                    cell.font, cell.alignment, cell.border = TROU_FONT, CENTRE, BORD
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
    # max de permanences par semaine (mêmes semaines que la limite du solveur)
    sem_par_pers = defaultdict(lambda: defaultdict(int))
    for (d, s), noms_slot in affect.items():
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
            value=", ".join(f"{jours[d]['label']} {LABELS_SLOTS[s]}" for d, s in non_couverts))

    # largeurs de colonnes
    ws.column_dimensions["A"].width = 16
    for c in range(2, 2 + 6 * 4):
        ws.column_dimensions[get_column_letter(c)].width = 13


# ------------------------------------------------------------------ MAIN ----
def main():
    jours, dispos = lire_dispos(FICHIER, FEUILLE_DISPO)
    total = sum(j["nslots"] for j in jours)
    print(f"{len(jours)} jours, {total} créneaux à couvrir.")

    affect, non_couverts, charge, noms = resoudre(jours, dispos)
    print(f"Personnes mobilisées : {len(charge)}")
    print(f"Créneaux couverts    : {total - len(non_couverts)}/{total}")
    print(f"Créneaux à pourvoir  : {len(non_couverts)}")
    for d, s in non_couverts:
        print(f"   - {jours[d]['label']}  {LABELS_SLOTS[s]}")

    wb = load_workbook(FICHIER)  # rechargé sans data_only pour préserver la feuille
    ecrire_planning(wb, jours, affect, non_couverts, charge, noms, dispos)
    wb.save(FICHIER)
    print(f"\nFeuille « {FEUILLE_PLANNING} » écrite dans {FICHIER}")


if __name__ == "__main__":
    main()
