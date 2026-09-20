# recus-paiement

Génération des reçus de paiement de cotisation à partir de la feuille d'adhérents
`gestion_adherents_2026-2027.ods`, et vérification de leur authenticité.

## Scripts

| Script | Rôle |
|---|---|
| `script_generation_recus.py` | Génère les reçus (Word → PDF) pour les adhérents avec « Demande de reçu » = « demandé » (col. X), avec un ID d'authenticité |
| `script_verification_recu.py` | Vérifie l'ID d'authenticité d'un reçu (nom, prénom, date, clé) |
| `cles_authenticite.py.example` | Template de la clé locale — à copier en `cles_authenticite.py` |

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

### Générer les reçus

```bash
python script_generation_recus.py
```

Filtre les adhérents dont la colonne X « Demande de reçu » vaut « demandé »,
génère `TCLM_Recu_paiement_<Nom>_<Prenom>.docx` + `.pdf` dans
`P:/2026-2027/Adhérents/Recu_paiements/`, à partir du template
`Modele_doc/Modele_recu_paiement_2026.docx`.

Après envoi du reçu, penser à passer la colonne X à « traité » pour ne pas
regénérer le même reçu.

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
