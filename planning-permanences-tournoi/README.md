# planning-permanences-tournoi

Génération automatique du tableau de permanences pour le tournoi d'automne de
tennis (samedi 17/10 → samedi 7/11, journée finale inclue) : le script lit
les disponibilités saisies dans le classeur Excel, calcule l'affectation
optimale des personnes aux créneaux et écrit deux feuilles de planning dans
le même classeur :

- **planning 1 site** : site principal (A 9h-13h, B 13h-17h, C 17h-21h, D 21h-fin) ;
- **planning 2 sites** : site principal + second site sur les créneaux du
  soir uniquement (C 17h-21h et D 21h-fin).

Les deux plannings sont résolus indépendamment à partir des mêmes
disponibilités : les plafonds (6 total, 4/semaine) s'appliquent séparément
à chaque planning.

## Usage

```bash
python script_planning.py
```

- Le classeur cible est défini en tête de script (`FICHIER`) :
  `P:/2026-2027/Bureau/Championnats - Tournois/TOURNOI AUTOMNE PERMANENCES_fusion.xlsx`.
- Fermer le fichier dans Excel avant l'exécution (sinon échec à l'enregistrement).
- Les feuilles de planning sont **entièrement supprimées puis recréées** à
  chaque exécution : toujours modifier les disponibilités dans `Feuil1`,
  jamais dans les plannings.
- Les créneaux non couverts sont listés dans la console et en bas de chaque
  feuille, marqués « !! À POURVOIR » en rouge dans la grille.
- Sur la feuille « planning 2 sites », les colonnes du second site (créneaux
  du soir) sont sur fond jaune.

## Créneaux et règles d'affectation

Créneaux : A 9h-13h · B 13h-17h · C 17h-21h · D 21h-fin (la finale du 7/11
n'a que A et B ; le second site n'existe pas sur la finale).

Règles appliquées par le solveur (HiGHS), pour chaque planning :

- au moins 1 personne par créneau quand les disponibilités le permettent ;
- jamais 2 créneaux le même jour pour une même personne (tous sites confondus) ;
- jamais 2 jours consécutifs (élimine de fait le cas D le soir + A le lendemain) ;
- au plus `MAX_TOTAL` (6) permanences par personne sur tout le tournoi ;
- au plus `MAX_PAR_SEMAINE` (4) permanences par personne et par semaine ;
- priorité aux personnes ayant proposé le moins de disponibilités ;
- en dernier recours, équilibrage de la charge entre les personnes.

## Réglages

| Paramètre | Défaut | Rôle |
|---|---|---|
| `FICHIER` | `P:/2026-2027/Bureau/Championnats - Tournois/…` | Chemin du classeur des permanences |
| `FEUILLE_DISPO` | `Feuil1` | Feuille des disponibilités |
| `FEUILLE_1_SITE` | `planning 1 site` | Nom de la feuille planning 1 site |
| `FEUILLE_2_SITES` | `planning 2 sites` | Nom de la feuille planning 2 sites |
| `SLOTS_SITE2` | `(2, 3)` | Créneaux du second site (C et D) |
| `MAX_TOTAL` | 6 | Permanences max par personne sur tout le tournoi |
| `MAX_PAR_SEMAINE` | 4 | Permanences max par personne et par semaine |

## Saisie des disponibilités

Dans `Feuil1` : `O` = disponible, `N` = non disponible, `> 18h` / `> 14h` =
disponibilité partielle (arrivée tardive, signalée entre parenthèses dans le
planning). Les personnes sans aucune réponse sont ignorées. La même
disponibilité horaire vaut pour les deux sites.

## Feuilles générées

- 3 blocs de 6 jours + le bloc de la finale, comme la feuille d'origine ;
- entêtes de journées alignés à gauche ;
- récapitulatif « Charge par personne » : total (alerte rouge à `MAX_TOTAL`)
  et max par semaine (alerte rouge à `MAX_PAR_SEMAINE`) ;
- liste des créneaux non couverts (mention `[site 2]` pour le second site).

## Dépendances

```bash
pip install openpyxl scipy
```

- `openpyxl` — lecture du classeur et écriture des feuilles de planning.
- `scipy` — solveur MILP (HiGHS) pour l'affectation optimale.
