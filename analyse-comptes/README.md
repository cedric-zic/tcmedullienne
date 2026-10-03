# analyse-comptes

Analyse et croisement des comptes adhérents ADOC 2026-2027 : rapproche le
fichier `gestion_adherents_2026-2027.ods` (inscriptions), l'export CSV des
clients LiveXp (application mobile) et le fichier de synthèse de suivi.

Le fichier `.ods`, l'export CSV et le fichier de synthèse ne sont **pas
versionnés** (données réelles) — seul le script l'est.

## Rôle

Croise 3 sources :

- **Inscription** : `gestion_adherents_2026-2027.ods` (NOM, PRENOM, FORMULE ADOC,
  Inscription validée col. V, Paiement col. Y).
- **LiveXp** : export clients de l'application mobile (`.csv`) — solde,
  nom/prénom, `Type_client` (vide = compte non valide).
- **Suivi** : `synthese_comptes_adherents_2026-2027.xlsx` — LU pour récupérer
  la saisie manuelle (Compte créé, Adhésion validée, Email envoyé, Crédit,
  Commentaire), puis **REÉCRIT** à chaque exécution.

À chaque exécution, le script régénère l'onglet `Suivi` (1 ligne par adhérent
inscrit, enrichi du compte app, solde, inversion, homonymie, paiement) et les
onglets d'analyse :

| Onglet | Contenu |
|---|---|
| `Suivi` | Suivi consolidé, colonnes manuelles préservées |
| `Annulation` | Inscriptions annulées (col. V) |
| `Compte_sans_abon_ni_credit` | Compte app sans adhésion validée ni crédit |
| `Comptes_pas_a_jour` | Comptes valides dont le suivi est incomplet (invalides exclus) |
| `Inscrits_sans_compte_app` | Inscrits sans compte dans l'application |
| `Comptes_sans_inscription` | Comptes app non rattachés à une inscription |
| `Homonymies_a_verifier` | Correspondances ambiguës (plusieurs matchs) |

Un rapport texte `rapport_analyse_comptes.txt` est également écrit.

## Utilisation

Adapter les constantes en tête du script (dossier de travail, noms de
fichiers, index de colonnes si le `.ods` évolue), puis :

```bash
python analyse_comptes_adherents.py
```

Une sauvegarde horodatée du fichier de synthèse est créée avant chaque
réécriture (`*_sauvegarde_YYYYMMJJ_HHMMSS.xlsx`).

## Dépendances

Python 3.10+ recommandé.

```bash
pip install pandas openpyxl odfpy
```

## Points d'attention

- Un compte LiveXp avec `Type_client` vide est traité comme **invalide** :
  `C - Compte cree` est forcé à `Invalide`, le statut dédié
  `COMPTE APP INVALIDE (Type_client vide)` est appliqué, et le compte est
  exclu de `Comptes_pas_a_jour`.
- Les colonnes de suivi manuel sont relues par **nom de colonne** de l'onglet
  `Suivi` : elles survivent à la réécriture, même si de nouvelles colonnes
  sont insérées (ex. `Paiement`, col. D).
- Au premier lancement (ou si le fichier de synthèse est absent), la saisie
  est migrée depuis l'ancien `suivi_comptes_adherents_2026.ods`.
