# recus-paiement

Génération, envoi et vérification des reçus de paiement de cotisation, à partir
de la feuille d'adhérents `gestion_adherents_2026-2027.ods`.

## Scripts

| Script | Rôle |
|---|---|
| `script_recus.py` | Script unique : **[1] Générer** les reçus (col. X « demandé » → PDF, statut « encours ») puis **[2] Envoyer** (col. X « encours » → mail + PJ, statut « traité ») |
| `script_verification_recu.py` | Vérifie l'ID d'authenticité d'un reçu (nom, prénom, date, montant, saison, clé) |
| `cles_authenticite.py.example` | Template des clés par saison — à copier en `cles_authenticite.py` |

## Workflow automatisé

```
1. script_recus.py -> option 1
   Filtre colonne X = « demandé », génère les PDF,
   passe X à « encours » (sauvegarde ODS automatique avant modification)

2. CONTRÔLE HUMAIN
   Vérification des PDF générés dans Recu_paiements/,
   ajustements manuels si besoin (ré-exporter le PDF après modif du .docx)

3. script_recus.py -> option 2
   Liste des « encours » avec PDF présent et email valide,
   confirmation T (tous) ou U (O/N par reçu),
   envoi du mail avec le reçu en pièce jointe,
   passage de X à « traité » après chaque envoi réussi
```

Statuts de la colonne X « Demande reçu » : `demandé` → `encours` → `traité`.

- PDF manquant ou email invalide → le reçu reste « encours », il sera
  reproposé au prochain lancement (aucun envoi).
- Échec d'envoi SMTP → le statut reste « encours », retenté au prochain lancement.
- Mode `--test` : aucune génération/envoi, aucune modification de l'ODS ;
  l'option 2 affiche un aperçu du mail.
- Cadence : 45 s entre chaque envoi (à adapter via `INTER_EMAIL_DELAY`).
- Logs : `logs/envoi_recus_YYYYMMDD.log`.

## Modèle de mail (phase 1 — générique)

Sujet : `TC La Médullienne - Votre reçu de paiement saison {saison}`

> Bonjour {prenom},
>
> Vous trouverez en pièce jointe votre reçu de paiement pour la saison {saison}.
> Cet envoi fait suite à votre demande.
>
> Si vous avez besoin d'un complément ou d'une correction, n'hésitez pas à nous
> répondre, nous restons à votre disposition.
>
> Bien sportivement,
> Cédric Meschin — Secrétaire - TC La Médullienne

Texte brut, PDF en pièce jointe. Les constantes `SUJET_MAIL` et `CORPS_MAIL`
sont modifiables en tête de `script_recus.py`.

## Configuration obligatoire (fichiers locaux, jamais committés)

- `cles_authenticite.py` — clés HMAC par saison (voir section dédiée plus bas)
- `secrets_local.py` — identifiants SMTP :
  ```python
  SMTP_SERVER = "smtp.gmail.com"
  SMTP_PORT = 587
  SMTP_USER = "ton.adresse@gmail.com"
  SMTP_PASSWORD = "mot de passe d'application Gmail"
  ```
  (même format que `notif-inscriptions/secrets_local.py`)

## Contenu dynamique par formule (phase 2 — implémenté)

Une feuille dédiée de l'ODS, **`Textes_formules`**, associe chaque formule
à 2 à 5 éléments de contenu insérés dans le mail. Structure (une ligne par
formule, un élément par colonne) :

| | A (Formule) | B (Élément 1) | C (Élément 2) | D (Élément 3) | E | F |
|---|---|---|---|---|---|---|
| 1 | Formule | Élément 1 | Élément 2 | Élément 3 | Élément 4 | Élément 5 |
| 2 | Jeune compétition | l'adhésion au club | la licence FFT | les cours avec un professeur diplômé | | |
| 3 | Adulte loisir | l'adhésion au club | l'accès aux créneaux libres | | | |
| 4 | Adulte illimité | l'adhésion au club | l'accès illimité aux créneaux | la licence FFT | | |

Règles :
- le nom de la formule (colonne A) doit être **identique** à la colonne G de
  `Liste_adherents` ;
- la ligne 1 (en-têtes) est ignorée automatiquement ;
- de 1 à 5 éléments, colonnes B à F — les colonnes vides sont ignorées ;
- le mail insère : « Cette cotisation inclut : X, Y et Z. » (grammaire
  française : « et » avant le dernier élément) ;
- **formule absente de la feuille** → le paragraphe est omis, le mail reste
  celui de la phase 1 (générique) ;
- **feuille absente de l'ODS** → idem, tout le monde reçoit le mail générique
  (le script logge l'information).

L'ajout d'une formule ou d'un élément se fait donc directement dans
LibreOffice, sans toucher au code.

Le texte d'introduction est modifiable via la constante `TEXTE_INTRO_CONTENU`
de `script_recus.py`.

## ID d'authenticité — principe

Chaque reçu porte un ID au format :

```
AAAAMMJJ.TTTTTTTTTT.<signature-hex-16>
```

- `AAAAMMJJ` : date du reçu (identique à la date affichée sur le document)
- `TTTTTTTTTT` : timestamp de génération
- `signature` : HMAC-SHA256 de `NOM|PRÉNOM|AAAAMMJJ|MONTANT|SAISON|TTTTTTTTTT`
  avec la clé secrète du club, tronqué à 16 caractères hexadécimaux

**Propriété clé :** la validation utilise `hmac.compare_digest` (comparaison
temps constant). Si un seul caractère change — dans l'ID, le nom, le prénom,
la date, le montant ou la saison saisis — la signature ne correspond plus et
le reçu est déclaré invalide. Contrairement à l'ancien système (timestamp
chiffré AES-ECB), il n'existe plus de cas où un ID altéré passe la vérification.

Le montant et la saison sportive sont inclus dans la signature : un reçu dont
le montant ou la saison affichée serait modifié (ex. réutiliser un reçu de la
saison précédente pour l'année suivante) est détecté automatiquement.

La clé de signature est **publique par opposition** : connaître l'algorithme
ne permet rien, seule la clé secrète permet de forger un ID valide.

## Configuration obligatoire : `cles_authenticite.py`

Les clés sont gérées **une par saison sportive**, dans `cles_authenticite.py`,
à créer à côté des scripts :

```bash
cp cles_authenticite.py.example cles_authenticite.py
# puis éditer et renseigner CLES_PAR_SAISON
```

```python
CLES_PAR_SAISON = {
    "2026/2027": "clé-secrète-longue-et-aléatoire",
    # "2027/2028": "nouvelle-clé-à-chaque-saison",
}
```

Ce fichier est exclu par le `.gitignore` et **ne doit jamais être committé**.

Puisqu'une clé est associée à chaque saison et que la saison est signée dans
l'ID, la rotation de clé est naturelle : changer de clé pour la saison
suivante n'invalide pas les reçus des saisons précédentes, qui restent
vérifiables avec leur clé d'origine. **Conservez ce fichier d'une saison sur
l'autre** (en lieu sûr, hors Git) : c'est lui qui permet de revérifier les
anciens reçus.

La génération s'arrête avec un message explicite si aucune clé n'est définie
pour la saison en cours.

La vérification, elle, demande la clé de la saison en saisie masquée
(`getpass`) : elle fonctionne sur n'importe quel poste, sans fichier local.

## Usage

### Utilisation

```bash
python script_recus.py           # menu interactif : 1. Générer / 2. Envoyer
python script_recus.py --test    # mode aperçu (aucun envoi, aucune écriture ODS)
```

Génère `TCLM_Recu_paiement_<Nom>_<Prenom>.docx` + `.pdf` dans
`P:/2026-2027/Adhérents/Recu_paiements/`, à partir du template
`Modele_doc/Modele_recu_paiement_2026.docx`.

### Vérifier un reçu

```bash
python script_verification_recu.py 20260920.1758371234.a1b2c3d4e5f60789
```

Le script demande : nom, prénom, date du reçu (JJMMAAAA ou AAAAMMJJ),
montant, saison sportive et la clé (saisie masquée). Répond ✅ original ou
❌ invalide.

## Dépendances

```bash
pip install pandas odfpy python-docx docx2pdf pycryptodome
```

- `pandas` + `odfpy` — lecture du `.ods`
- `python-docx` — génération du Word
- `docx2pdf` — conversion PDF (nécessite Microsoft Word ou LibreOffice installé)
- `pycryptodome` — **requis uniquement par l'ancienne version** du script ;
  la version HMAC n'en dépend plus

## Fichiers attendus sur le poste

| Fichier | Chemin |
|---|---|
| Feuille adhérents | `P:/2026-2027/Adhérents/gestion_adherents_2026-2027.ods` |
| Template reçu | `P:/2026-2027/Adhérents/Modele_doc/Modele_recu_paiement_2026.docx` |
| Signature | `P:/2026-2027/Adhérents/Modele_doc/signature_cedric.jpg` |
| Export | `P:/2026-2027/Adhérents/Recu_paiements/` |
