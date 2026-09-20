# assets

Images utilisées par `script_envoi_email_inscription.py` (logo et tampons
appliqués sur les fiches PDF).

Le script cherche chaque image **d'abord dans ce dossier**, puis retombe sur
les chemins historiques du lecteur `P:` si elle n'y est pas.

| Rôle | Nom principal attendu | Nom alternatif accepté |
|---|---|---|
| Logo du club (PNG transparent, en-tête des emails) | `logo_tcmedullienne.png` | `logo_tcmedullienne_2026_transparent_160px.png` |
| Tampon « Annulé » (PNG transparent) | `tampon_annule.png` | `tampon_Annulé_transparent.png` |
| Tampon « Professeur » (PNG transparent) | `tampon_professeur.png` | `tampon_Professeur_transparent.png` |

Avantages : chemins indépendants de la saison et du lecteur `P:` — le dépôt
devient autonome pour les images.
