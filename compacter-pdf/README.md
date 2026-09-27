# compacter-pdf

Compression des PDF scannés (fiches d'inscription, reçus) : réduction de la
résolution des images embarquées + réencodage JPEG. Le fichier reste un PDF
valide et lisible ; les tampons et images à transparence ne sont pas altérés.

Équivalent en Python des outils type « PDF Gear » : la quasi-totalité du poids
d'un PDF scanné vient de ses images (souvent scannées à 300 dpi alors que
150 dpi suffisent pour une fiche A4 lisible à l'écran et à l'impression courante).

## Usage

```bash
# Aperçu du gain, sans rien modifier
python script_compacter_pdf.py "P:/2026-2027/Adhérents/Fiches_inscriptions" --test

# Compression effective (remplace les fichiers)
python script_compacter_pdf.py "P:/2026-2027/Adhérents/Fiches_inscriptions"

# Un seul fichier, réglages plus agressifs
python script_compacter_pdf.py fiche.pdf --dpi 120 --qualite 50
```

## Réglages

| Paramètre | Défaut | Rôle |
|---|---|---|
| `--dpi` | 150 | Résolution cible des images (une image déjà à 150 dpi ou moins n'est pas retouchée) |
| `--qualite` | 65 | Qualité JPEG (1–95) |
| `--test` | — | Simule et affiche le gain sans modifier les fichiers |

## Comportement

- Un PDF dont la version compressée ne serait pas plus légère (à 2 % près)
  reste inchangé — la compression est donc idempotente.
- Les images avec masque de transparence (tampons « Payé », logos) sont
  conservées telles quelles.
- Les PDF protégés ou corrompus sont signalés en erreur, la suite du lot
  continue.
- Garde-fou : en cas d'échec de compression d'un fichier, l'original est
  conservé.

## Dépendances

```bash
pip install pymupdf pillow
```

- `pymupdf` — manipulation du PDF et remplacement des flux images.
- `pillow` — ré-échantillonnage et réencodage JPEG.

## Lien avec `notif-inscriptions`

L'envoi des emails (`notif-inscriptions/script_envoi_email_inscription.py`)
compresse automatiquement la pièce jointe au-dessus de 1 Mo via le même
mécanisme, sur une **copie temporaire** — les fiches originales du lecteur
`P:` ne sont jamais modifiées par l'envoi. Ce dossier sert au traitement par
lot de tout un dossier de PDF (archivage, gain de place durable).
