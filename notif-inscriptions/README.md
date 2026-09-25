# notif-inscriptions

Envoi des emails d'inscription aux adhérents du TC La Médullienne pour la saison
2026/2027, à partir d'une feuille de calcul `.ods`.

Gère trois flux :
- **Adhérents normaux** — confirmation d'inscription + relance si paiement
  partiel ou non réglé après un mois. Un tampon « Payé » est appliqué sur la
  fiche PDF lorsque l'email confirmant un paiement complet est envoyé.
- **Professeurs** — application d'un tampon « Professeur » sur la fiche PDF.
- **Annulations** — application d'un tampon « Annulé » + email d'annulation.

## Usage

```bash
# Mode test : génère un PDF par adhérent, n'envoie rien
python script_envoi_email_inscription.py --test

# Envoi réel
python script_envoi_email_inscription.py
```

## Configuration obligatoire : `secrets_local.py`

Ce script lit les identifiants SMTP dans `secrets_local.py`, à créer à côté du
script. Ce fichier est exclu par le `.gitignore` et **ne doit jamais être
committé**.

### Modèle

```python
# secrets_local.py — NE JAMAIS COMMITTER
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
SMTP_USER = "ton.adresse@gmail.com"
SMTP_PASSWORD = "mot de passe d'application Gmail"
```

Le script importe ces 4 variables automatiquement. Sans le fichier, il s'arrête
avec un message d'erreur explicite.

### Obtenir le mot de passe d'application Gmail

1. Activer la 2FA sur le compte Google.
2. `https://myaccount.google.com/apppasswords` → créer un mot de passe
   d'application « Mail ».
3. Le coller dans `SMTP_PASSWORD` (avec les espaces tels quels).

## Images : dossier `assets/`

Le logo et les tampons sont cherchés **d'abord dans `assets/`** (à côté du
script), puis à défaut sur les chemins historiques du lecteur `P:`.
Fichiers utilisés par le script :

- `logo_tcmedullienne_2026_transparent_160px.png`
- `tampon_Annule_transparent.png`
- `tampon_Paye_transparent.png`
- `tampon_Professeur_transparent.png`

## Fichiers attendus sur le poste (chemins configurés dans le script)
 | Constante | Rôle | Chemin attendu |
 |---|---|---|
 | `SOURCE_FILE` | Feuille `.ods` des adhérents | `P:/2026-2027/Adhérents/...ods` |
 | `ATTACHMENTS_DIR` | Fiches d'inscription PDF | `P:/2026-2027/Adhérents/Fiches_inscriptions` |
 | `LOGO_PATH` | Logo du club (PNG transparent) | `assets/logo_tcmedullienne_2026_transparent_160px.png`, sinon `P:/2025-2026/.../logo_...png` |
 | `TAMPON_ANNULE_PATH` | Tampon « Annulé » (PNG) | `assets/tampon_Annule_transparent.png`, sinon `P:/.../tampon_Annulé_transparent.png` |
 | `TAMPON_PROF_PATH` | Tampon « Professeur » (PNG) | `assets/tampon_Professeur_transparent.png`, sinon `P:/.../tampon_Professeur_transparent.png` |
| `TAMPON_PAYE_PATH` | Tampon « Payé » (PNG) | `assets/tampon_Paye_transparent.png`, sinon `P:/.../tampon_Paye_transparent.png` |

Le lecteur `P:` correspond à un montage pCloud local. Adapte les chemins si tu
changes de machine.

## Cadence d'envoi

Pour éviter les pics vers Gmail/free/outlook :

- `BATCH_SIZE = 1` — un email à la fois.
- `INTER_EMAIL_DELAY = 45` — 45 s entre chaque envoi (succès ou échec).
- `LIMIT_PER_DAY = 20` — arrêt automatique après 20 tentatives.

Réglage dans le script. À adapter selon ta limite Gmail réelle.

## Dépendances

```bash
pip install ezodf pymupdf pillow weasyprint
```

- `ezodf` — lecture/écriture du `.ods`.
- `pymupdf` — application des tampons sur les PDF.
- `pillow` — rotation/redimensionnement des images de tampon.
- `weasyprint` — génération du PDF en mode test.

## Logs

Fichiers dans `logs/envoi_emails_YYYYMMDD.log`, créés automatiquement à la
racine d'exécution.

## Mode test

`--test` génère un PDF du corps HTML pour chaque adhérent dans `ATTACHMENTS_DIR`
sans rien envoyer, sans modifier le `.ods`. Idéal pour valider le rendu HTML/PDF
et les montants avant un envoi réel.

## Détails techniques notables

- **Structure MIME** — `multipart/mixed` (racine) → `multipart/related` (corps
  HTML) + pièces jointes au niveau `mixed`. Conforme aux clients mail larges.
- **Logo** — embarqué en data-URI base64 dans le HTML (pas de `cid:logo` ni
  `MIMEImage`).
- **CSS inline** — pas de `display:flex` (remplacé par tables), largeur fluide
  `max-width:600px`. Compatibilité Gmail mobile maximale.
- **Compteur `total_sent`** — incrémenté même en cas d'échec SMTP, pour garder
  un compteur monotone dans les logs (`13/15` puis `14/15`) et borner la boucle.
  Un échec écrit le statut « Erreur » et sera retenté au prochain lancement.
- **Montant restant** — convention : « Reste dû » stocké négatif dans le `.ods`
  quand il reste à payer. La négation dans le code le normalise pour l'affichage.
