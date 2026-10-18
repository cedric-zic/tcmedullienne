# -*- coding: utf-8 -*-
"""
Export du planning de permanences vers Nextcloud Deck — Tournoi de tennis
(17/10 -> 7/11)

Ce script :
  1. relit le classeur Excel des disponibilités (même fichier que
     script_planning.py) et résout le planning 1 site (même solveur),
  2. crée un tableau Nextcloud Deck :
       - un board « Permanences Tournoi d'automne »,
       - une colonne (stack) par jour, dans l'ordre chronologique,
       - une carte par créneau (A 9h-13h, B 13h-17h, C 17h-21h, D 21h-fin)
         avec le(s) permanencier(s) dans la description + date d'échéance,
       - un label coloré par type de créneau (mêmes couleurs que la page
         post-its : jaune / vert / corail / bleu),
  3. si un compte Nextcloud correspond à un permanencier (dictionnaire
     EQUIPE ci-dessous), l'assigne à sa carte en plus de la description.

Prérequis :
  - pip install openpyxl scipy requests
  - un « mot de passe d'application » Nextcloud :
      Paramètres -> Sécurité -> Mots de passe d'application -> créer.

Utilisation :
  python export_deck.py            # crée/mets à jour le board
  python export_deck.py --dry-run  # simule sans rien créer

Le board existant de même titre est supprimé puis recréé à chaque exécution
(pour relancer proprement après une mise à jour des disponibilités).
"""

import sys
import json
import datetime as dt

# ------------------------- À RENSEIGNER ------------------------------
NEXTCLOUD_URL = "https://cloud.mondomaine.fr"   # racine du Nextcloud
NC_USER       = "cedric"                        # identifiant Nextcloud
NC_TOKEN      = ""                              # mot de passe d'application

# facultatif : nom exact dans Feuil1 -> identifiant du compte Nextcloud.
# Laisser vide pour ne rien assigner (les noms restent dans la description).
EQUIPE = {
    # "Cédric":   "cedric",
    # "Philippe": "philippe",
}
# ----------------------------------------------------------------------

FICHIER = r"P:/2026-2027/Bureau/Championnats - Tournois/TOURNOI AUTOMNE PERMANENCES_fusion.xlsx"
FEUILLE_DISPO = "Feuil1"
BOARD_TITRE = "Permanences Tournoi d'automne"

SLOT_LIBELLES = ["A · 9h-13h", "B · 13h-17h", "C · 17h-21h", "D · 21h-fin"]
SLOT_COULEURS = ["ffe8a3", "bde3a5", "ffd0c2", "c9d7f5"]   # idem page post-its

ANNEE = 2026    # année des libellés « Sam 17/10 »


# ---------------------------------------------------------------- solveur
def resoudre_planning():
    """Réutilise le solveur de script_planning.py (même dossier)."""
    import script_planning as sp
    sp.FICHIER = FICHIER
    jours, dispos, options = sp.lire_dispos(FICHIER, FEUILLE_DISPO)
    affect, non_couverts, charge, noms = sp.resoudre(jours, dispos,
                                                    avec_site2=False,
                                                    options=options)
    return jours, affect, non_couverts


def date_du_label(label):
    """« Sam 17/10 » -> date(2026, 10, 17)."""
    import re
    m = re.search(r"(\d{1,2})/(\d{1,2})", label)
    return dt.date(ANNEE, int(m.group(2)), int(m.group(1))) if m else None


# ---------------------------------------------------------------- API Deck
class Deck:
    def __init__(self, base, user, token, dry_run=False):
        self.base = base.rstrip("/") + "/index.php/apps/deck/api/v1"
        self.dry = dry_run
        self._log = []
        if dry_run:
            self.s = None
            return
        import requests                       # requis seulement hors --dry-run
        self.s = requests.Session()
        self.s.auth = (user, token)
        self.s.headers.update({"OCS-APIRequest": "true",
                               "Accept": "application/json",
                               "Content-Type": "application/json"})

    def _req(self, meth, path, payload=None, tolerated=()):
        if self.dry:
            self._log.append((meth, path, payload))
            return {"id": len(self._log)}
        r = getattr(self.s, meth)(f"{self.base}{path}",
                                   data=json.dumps(payload or {}))
        if r.status_code >= 500 or (r.status_code >= 400
                                    and r.status_code not in tolerated):
            r.raise_for_status()
        return r.json() if r.text and r.status_code < 400 else {}

    def post(self, path, payload=None):
        return self._req("post", path, payload)

    def put(self, path, payload=None):
        return self._req("put", path, payload, tolerated=(400, 404))

    def verifier_connexion(self):
        if self.dry:
            return
        r = self.s.get(self.base + "/boards")
        if r.status_code in (401, 403):
            raise SystemExit("*** Erreur d'authentification Nextcloud : vérifiez "
                             "NC_USER / NC_TOKEN (mot de passe d'application).")
        if r.status_code == 404:
            raise SystemExit("*** API Deck introuvable : vérifiez NEXTCLOUD_URL "
                             "et que l'app Deck est installée/activée.")
        r.raise_for_status()

    def supprimer_boards_existants(self, titre):
        if self.dry:
            return
        r = self.s.get(self.base + "/boards")
        r.raise_for_status()
        for b in r.json():
            if b.get("title") == titre:
                self.s.delete(f"{self.base}/boards/{b['id']}")
                print(f"Ancien board supprimé (id {b['id']})")


# ---------------------------------------------------------------- main
def main():
    dry = "--dry-run" in sys.argv
    if not NC_TOKEN and not dry:
        raise SystemExit("*** Renseignez NC_TOKEN (mot de passe d'application "
                         "Nextcloud) en tête de script, ou lancez avec --dry-run.")

    print("Calcul du planning 1 site…")
    jours, affect, non_couverts = resoudre_planning()
    nb = sum(j["nslots"] for j in jours)
    print(f"  {len(jours)} jours, {nb} créneaux, "
          f"{nb - len(non_couverts)}/{nb} couverts.")

    deck = Deck(NEXTCLOUD_URL, NC_USER, NC_TOKEN, dry_run=dry)
    if not dry:
        deck.verifier_connexion()
        deck.supprimer_boards_existants(BOARD_TITRE)

    # 1. board
    board = deck.post("/boards", {"title": BOARD_TITRE, "color": "f4b400"})
    bid = board["id"]

    # 2. labels par type de créneau
    label_ids = {}
    for s, lib in enumerate(SLOT_LIBELLES):
        lab = deck.post(f"/boards/{bid}/labels",
                        {"title": lib, "color": SLOT_COULEURS[s]})
        label_ids[s] = lab.get("id")

    # 3. une colonne par jour, une carte par créneau
    nb_cartes, nb_assign = 0, 0
    for d, j in enumerate(jours):
        stack = deck.post(f"/boards/{bid}/stacks",
                          {"title": j["label"].strip(), "order": d})
        sid = stack["id"]
        ddate = date_du_label(j["label"])
        for s in range(j["nslots"]):
            noms = affect.get((d, s, 1), [])
            desc = "\n".join("• " + n for n in noms) if noms else "!! À POURVOIR"
            due = (dt.datetime(ddate.year, ddate.month, ddate.day, 12)
                   .strftime("%Y-%m-%dT%H:%M:%S+00:00")) if ddate else None
            card = deck.post(
                f"/boards/{bid}/stacks/{sid}/cards",
                {"title": SLOT_LIBELLES[s], "description": desc,
                 "labels": [label_ids[s]], "duedate": due, "order": s})
            nb_cartes += 1
            for n in noms:
                uid = EQUIPE.get(n)
                if uid and not dry:
                    deck.put(f"/boards/{bid}/stacks/{sid}/cards/{card['id']}"
                             "/assignUser", {"userId": uid})
                    nb_assign += 1

    print(f"Board « {BOARD_TITRE} » : {len(jours)} colonnes, {nb_cartes} cartes "
          f"{'simulées (--dry-run)' if dry else 'créées dans Deck'}, "
          f"{nb_assign} assignation(s).")

    if non_couverts:
        print("Créneaux non couverts (cartes « À POURVOIR ») :")
        for (d, s, site) in non_couverts:
            print(f"   - {jours[d]['label']}  {SLOT_LIBELLES[s]}")

    if dry:
        print(f"\n[dry-run] {len(deck._log)} appels API seraient effectués, "
              "par exemple :")
        for m, p, pay in deck._log[:8]:
            print(f"   {m} {p}  {json.dumps(pay, ensure_ascii=False)[:70]}")
        if len(deck._log) > 8:
            print(f"   … (+{len(deck._log) - 8} autres)")


if __name__ == "__main__":
    main()
