# planning-permanences-tournoi

Génération automatique du tableau de permanences pour le tournoi d'automne de
tennis (samedi 17/10 → samedi 7/11, journée finale incluse) : le script lit
les disponibilités saisies dans le classeur Excel, calcule l'affectation
optimale des personnes aux créneaux et ajoute une feuille `PLANNING` mise en
forme dans le même classeur.

## Usage

```bash
python script_planning.py
```

- Le classeur cible est défini en tête de script (`FICHIER`) :
  `P:/2026-2027/Bureau/Championnats - Tournois/TOURNOI AUTOMNE PERMANENCES_fusion.xlsx`.
- Fermer le fichier dans Excel avant l'exécution (sinon échec à l'enregistrement).
- La feuille `PLANNING` est **entièrement supprimée puis recréée** à chaque
  exécution : toujours modifier les disponibilités dans `Feuil1`, jamais dans
  `PLANNING`.
- Les créneaux non couverts sont listés dans la console et en bas de la
  feuille, marqués « !! À POURVOIR » en rouge dans la grille.

## Créneaux et règles d'affectation

Créneaux : A 9h-13h · B 13h-17h · C 17h-21h · D 21h-fin (la finale du 7/11
n'a que A et B).

Règles appliquées par le solveur (HiGHS) :

- au moins 1 personne par créneau quand les disponibilités le permettent ;
- jamais 2 créneaux le même jour pour une même personne ;
- jamais 2 jours consécutifs (élimine de fait le cas D le soir + A le lendemain) ;
- priorité aux personnes ayant proposé le moins de disponibilités : celles qui
  n'offrent que 3 créneaux les obtiennent même si des personnes bien plus
  disponibles sont aussi sur ces créneaux ;
- en dernier recours, équilibrage de la charge entre les personnes.

## Réglages

| Paramètre | Défaut | Rôle |
|---|---|---|
| `FICHIER` | `P:/2026-2027/Bureau/Championnats - Tournois/…` | Chemin du classeur des permanences |
| `FEUILLE_DISPO` | `Feuil1` | Feuille des disponibilités |
| `FEUILLE_PLANNING` | `PLANNING` | Nom de la feuille générée |
| `MAX_TOTAL` | 6 | Permanences max par personne sur tout le tournoi |
| `MAX_PAR_SEMAINE` | 4 | Permanences max par personne et par semaine |

## Saisie des disponibilités

Dans `Feuil1` : `O` = disponible, `N` = non disponible, `> 18h` / `> 14h` =
disponibilité partielle (arrivée tardive, signalée entre parenthèses dans le
planning). Les personnes sans aucune réponse sont ignorées.

## Feuille générée

- 3 blocs de 6 jours + le bloc de la finale, comme la feuille d'origine ;
- entêtes de journées alignés à gauche ;
- récapitulatif « Charge par personne » : total (alerte rouge à `MAX_TOTAL`)
  et max par semaine (alerte rouge à `MAX_PAR_SEMAINE`) ;
- liste des créneaux non couverts.

## Dépendances

```bash
pip install openpyxl scipy
```

- `openpyxl` — lecture du classeur et écritriture de la feuille `PLANNING`.
- `scipy` — solveur MILP (HiGHS) pour l'affectation optimale.
