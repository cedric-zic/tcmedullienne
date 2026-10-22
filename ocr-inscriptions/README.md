# ocr-inscriptions

Traitement automatisé des fiches d'inscription du TC La Medullienne : **OCR local**
des fiches numérisées (papier scanné, photo, PDF rempli sur ordinateur) + **rapprochement**
avec la liste des adhérents connus, en vue d'une **revue humaine** avant intégration
dans la feuille `gestion_adherents_2026-2027.ods`.

> **RGPD** : tout le traitement est **100 % local** (Tesseract installé sur le
> serveur, aucune API cloud, aucun envoi de données). Les 361 fiches d'entraînement
> et les données extraites ne quittent jamais le serveur Nextcloud / le poste du bureau.

## Architecture

```
Fiche numérisée (PDF scan / photo / PDF rempli)
        │
        ▼
pipeline_ocr.py ──► prétraitement (déskew, seuillage adaptatif)
        │           recalage gabarit ↔ scan (séparateurs du tableau)
        │           détection des cases cochées (analyse de pixels)
        │           OCR zoné Tesseract (fra) sur les champs texte
        │           (PDF avec couche texte → extraction directe, sans OCR image)
        ▼
    RésultatFiche (JSON) : champ → {valeur, confiance, type}
        │
        ▼
    ODS de revue (revue_inscriptions.ods)  ←  REVUE HUMAINE OBLIGATOIRE
        │   (colonne « Statut revue » : À vérifier / Validé)
        ▼
rapprochement.py ──► rapprochement flou avec les adhérents connus (réinscription,
        │           homonymes, nouvel adhérent) — comparaison possible avec
        │           l'extraction manuelle des coordonnées (mesure qualité OCR)
        ▼
    Intégration dans Liste_adherents → macros existantes → tampons (inchangé)
```

## Fichiers

| Fichier | Rôle |
|---|---|
| `gabarit_v12.json` | Coordonnées (points PDF, page A4) de toutes les zones de la fiche V12 : cases sexe, champs coordonnées adhérent/représentant, 14 lignes de formules, tableau disponibilités, cases paiement, marqueurs de recalage. |
| `traitement_image.py` | Prétraitement (déskew, seuillage), recalage, détection de cases, OCR zoné Tesseract, nettoyeurs (date, téléphone, email). |
| `pipeline_ocr.py` | Pipeline complet : lit une fiche → produit un résultat structuré + ODS de revue. |
| `rapprochement.py` | Rapprochement flou fiche ↔ adhérents connus (normalisation, Levenshtein, score pondéré). |
| `formulaire/` | Formulaire en ligne (Nextcloud Forms ou page statique) — en construction. |

## Installation (serveur Nextcloud Linux)

```bash
# Système
sudo apt install tesseract-ocr tesseract-ocr-fra

# Python
pip install pymupdf pillow numpy ezodf pytesseract
# ou, sans binaire système (tessdata à fournir) :
#   pip install tesserocr   +  TESSDATA_PREFIX=/chemin/tessdata

# OpenCV optionnel (meilleur seuillage) :
pip install opencv-python-headless
```

Vérifier :

```bash
tesseract --list-langs   # doit lister fra
python -c "import traitement_image as ti; ti.verifier_dependances()"
```

## Usage

```bash
# Une fiche unique
python pipeline_ocr.py --fichier "Inscription_2026_DUPONT_Jean.pdf"

# Un dossier de fiches (les 361 fiches d'entraînement, par ex.)
python pipeline_ocr.py --dossier /nextcloud/tclm/Fiches_a_traiter --sortie revue.ods --json

# Mode test : 5 premières fiches uniquement
python pipeline_ocr.py --dossier /nextcloud/tclm/Fiches_a_traiter --test

# Rapprochement avec l'extraction des coordonnées adhérents
python rapprochement.py --revue revue_inscriptions.json --adherents adherents.csv --sortie rapproche.ods
```

### Sorties

- `revue_inscriptions.ods` — **feuille de revue** : une ligne par fiche, tous les
  champs extraits, confiance globale, alertes, et deux colonnes laissées au bureau :
  `Statut revue` (À vérifier / Validé) et `Commentaire`.
- `revue_inscriptions.json` — détail complet par champ (valeur, confiance, ratios
  des cases) pour analyse et rapprochement.
- `logs/ocr_inscriptions_YYYYMMDD.log` — log horodaté (convention du dépôt).

## Principe de la revue humaine

L'OCR **ne valide jamais seul**. Chaque champ a un niveau de confiance :

- confiance ≥ 0,9 et pas d'alerte → proposition, le bureau valide d'un clic ;
- confiance < 0,7 ou alerte (0 ou plusieurs cases cochées, recalage faible,
  champ vide) → **à vérifier impérativement** (surligné dans l'ODS via la
  colonne Alertes).

Le bureau corrige dans l'ODS de revue, puis reporte dans `Liste_adherents`
(les macros et tampons existants prennent le relais inchangés).

## Calibrage sur les 361 fiches

Les seuils par défaut (`SEUIL_CASE_COCHEE`, `SEUIL_RELATIF`, `MARGE_BORD_CASE`
dans `traitement_image.py`) sont des valeurs de départ. Pour les calibrer :

```bash
# 1. Traiter les 361 fiches en mode test
python pipeline_ocr.py --dossier /chemin/361_fiches --sortie calibrage.ods --json

# 2. Comparer avec l'extraction manuelle (si fournie)
python rapprochement.py --revue calibrage.json --adherents extraction_manuelle.csv --sortie rapport_calibrage.ods

# 3. Ajuster les seuils dans traitement_image.py selon le taux d'alertes
```

Indicateurs à viser : taux de champs avec confiance ≥ 0,9 > 90 %, taux de
fausses alertes < 10 %. L'écriture manuscrite reste le point faible : les
champs douteux partent systématiquement en revue.

## Fiche V13 (saison prochaine)

Le gabarit est versionné (`gabarit_v12.json`). Pour la V13 :

1. Générer `gabarit_v13.json` à partir du nouveau modèle (mêmes étapes :
   extraction des séparateurs et zones depuis le PDF vierge) ;
2. Lancer avec `--gabarit gabarit_v13.json`.

Recommandations pour la V13 (à discutées avec le bureau) :

- **Disponibilités en matrice cases** (jour × tranche horaire prédéfinie) au
  lieu de saisie libre → détection de cases fiable à ~100 % et regroupement
  direct pour les professeurs ;
- **Cases carrées imprimées** explicites pour le sexe (aujourd'hui ce sont des
  cellules du tableau) ;
- **QR code avec token** sur la fiche → formulaire en ligne pré-rempli (zéro
  double saisie, la fiche papier reste le justificatif signé).

## Formulaire en ligne (Nextcloud)

Deux canaux, un même point d'arrivée (l'ODS de revue) :

| Canal | Qui remplit | Comment |
|---|---|---|
| Formulaire en ligne (adhérent) | L'adhérent | Nextcloud Forms (app Forms) ou page statique + script de collecte. Validation bureau obligatoire. |
| Formulaire en ligne (bureau) | Membre du bureau authentifié | Variante avec champs de validation/forçage (statut, formule corrigée, commentaire). |
| Fiche papier/PDF | Adhérent | Dépôt sur Nextcloud (upload appli mobile) → `pipeline_ocr.py`. |

> Les adhérents n'ont **pas** de compte Nextcloud : le formulaire public est un
> lien Nextcloud Forms (pas de compte requis) ou une page statique. Seuls les
> membres du bureau ont un compte Nextcloud (accès aux réponses + variante
> "bureau" du formulaire avec droits de validation).

Le script de collecte des réponses Forms (CSV Nextcloud) est à brancher sur le
même ODS de revue : `pipeline_ocr.py` sait aussi ingérer un CSV de réponses
(structure identique au JSON de sortie).

## Dépendances

```bash
pip install pymupdf pillow numpy ezodf pytesseract
# système : sudo apt install tesseract-ocr tesseract-ocr-fra
# optionnel : pip install opencv-python-headless
```

Python 3.10+ recommandé (convention du dépôt).

## Tests

```bash
# Tests unitaires (détection de cases, OCR zoné, nettoyeurs, rapprochement)
python -c "import traitement_image, rapprochement; print('modules OK')"

# Test de bout en bout sur une fiche synthétique générée depuis le modèle V12
python pipeline_ocr.py --fichier <fiche_test> --sortie /tmp/revue.ods --json
```

## Logs et sauvegardes

- Logs : `logs/ocr_inscriptions_YYYYMMDD.log` (exclu par `.gitignore`).
- Le pipeline est **en lecture seule** sur les fiches sources : il ne modifie
  jamais un PDF/image d'entrée.
- Convention du dépôt respectée : pas de secrets versionnés, pas de données
  réelles dans Git (`*.ods`, `*.csv` d'adhérents exclus).
