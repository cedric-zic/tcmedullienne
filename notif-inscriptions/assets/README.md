# assets

Images utilisées par `script_envoi_email_inscription.py` (logo et tampons
appliqués sur les fiches PDF).

Chaque image est cherchée **d'abord dans ce dossier** selon l'ordre de priorité
défini dans le script (premier fichier trouvé = utilisé), puis à défaut sur les
chemins historiques du lecteur `P:`.

| Rôle | Fichiers dans `assets/` (ordre de priorité du script) |
|---|---|
| Logo du club (en-tête des emails) | `logo_tcmedullienne.png`, `logo_tcmedullienne_2026_transparent_160px.png` |
| Tampon « Annulé » | `tampon_Annule.png`, `tampon_Annule_transparent.png` |
| Tampon « Professeur » | `tampon_Professeur.png`, `tampon_Professeur_transparent.png` |

Avantages : chemins indépendants de la saison et du lecteur `P:` — le dépôt
devient autonome pour les images.
