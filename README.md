# TC La Médullienne — Outils d'administration

Scripts d'administration du Tennis Club La Médullienne : envoi des emails
d'inscription, gestion des macros de la feuille d'adhérents, génération et
vérification des reçus de paiement, et site web statique.

## Organisation
   Dossier | Rôle | État |
 |---|---|---|
 | `notif-inscriptions/` | Envoi des emails de confirmation/relance/annulation d'inscription | Actif |
 | `macros-inscriptions/` | Gestion des macros du fichier `.ods` des adhérents | Actif |
 | `recus-paiement/` | Génération des reçus + vérification d'authenticité | Actif |
 | `site-web/` | Site web statique du club | À venir |

Chaque dossier a son propre `README.md` décrivant l'usage, les dépendances et
la configuration.

## Configuration locale obligatoire

Certains scripts lisent des paramètres sensibles (identifiants SMTP, clé
d'authenticité des reçus) dans des fichiers **locaux, jamais versionnés** :

- `notif-inscriptions/secrets_local.py` — identifiants SMTP
- `recus-paiement/cles_authenticite.py` — clé unique des reçus

Ces fichiers sont exclus par le `.gitignore` à la racine. Un script ne démarre
pas sans son fichier local correspondant ; un message d'erreur indique quoi créer.

Voir le `README.md` de chaque dossier pour le modèle du fichier attendu.

## Dépendances communes

Python 3.10+ recommandé. Dépendances listées par script dans son README.

## Licence

Usage interne au Tennis Club La Médullienne. Code non destiné à être redistribué.
