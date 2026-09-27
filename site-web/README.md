# site-web

Site web de présentation du TC La Médullienne : pages d'accueil, Tennis,
Padel et Contact, plus des pages d'administration pour gérer sponsors et
événements sans toucher au code. Le club est présenté sur ses deux sites,
Avensan et Castelnau de Médoc.

Aucune build, aucun framework : HTML/CSS/JS purs. Les pages d'administration
nécessitent PHP (sur YunoHost : l'activer dans la configuration de My Webapp).

## Pages

| Fichier | Contenu |
|---|---|
| `index.html` | Accueil : présentation du club, carrousel d'événements, horaires, carte des deux sites, sponsors |
| `tennis.html` | Page Tennis |
| `padel.html` | Page Padel |
| `contact.html` | Formulaire de contact + coordonnées complètes |
| `footer.html` | Fragment de pied de page inclus dans les autres pages |

## Fichiers

| Fichier | Rôle |
|---|---|
| `styles.css` | Styles du site et des pages d'administration (Montserrat / Open Sans via Google Fonts) |
| `script.js` | Carte Leaflet, carrousel et sponsors chargés depuis les JSON, menu mobile, formulaire, email obfusqué |
| `images/logo.png` | Logo du club |

### Pages d'administration (nécessitent PHP)

| Fichier | Rôle |
|---|---|
| `admin-lib.php` | Bibliothèque partagée : authentification, lecture/écriture JSON, upload d'images |
| `admin-sponsors.php` | Gestion des sponsors : liste avec miniatures, ajout, modification, suppression |
| `admin-evenements.php` | Gestion des événements du carrousel : liste, ajout, modification, suppression |

## Gestion du contenu (sponsors et événements)

Le contenu n'est **pas** codé dans les fichiers du site : il vit dans deux
fichiers JSON lus au chargement des pages :

- `sponsors.json` — liste des sponsors (nom, URL, image), affichés en
  rotation sur l'accueil et la page contact
- `evenements.json` — liste des événements (titre, image), affichés dans le
  carrousel de l'accueil

Ces fichiers, le fichier de mot de passe et les dossiers
`images/sponsors/` et `images/evenements/` sont **exclus du dépôt Git** :
ils sont créés et modifiés uniquement sur le serveur via les pages
d'administration.

### Utilisation

1. Ouvrir `admin-sponsors.php` ou `admin-evenements.php` dans le navigateur
2. Saisir le mot de passe (fichier `admin-mot-de-passe.php`, voir ci-dessous)
3. Ajouter / modifier / supprimer ; la liste existante est affichée avec
   miniatures et positions, et les changements sont visibles immédiatement
   sur le site

### Configuration obligatoire : `admin-mot-de-passe.php`

Les deux pages d'administration sont protégées par un mot de passe stocké
dans `admin-mot-de-passe.php`, à créer à la racine du site **sur le serveur
uniquement**. Ce fichier est exclu par le `.gitignore` et ne doit jamais
être commité.

Modèle :

```php
<?php
return 'votre mot de passe';
```

### Déploiement et mises à jour du site

Les données étant séparées du code, une mise à jour du site ne doit jamais
les écraser :

```bash
rsync -rv --delete \
  --exclude='.git' \
  --exclude='sponsors.json' \
  --exclude='evenements.json' \
  --exclude='admin-mot-de-passe.php' \
  --exclude='images/sponsors/' \
  --exclude='images/evenements/' \
  site-web/ serveur:/var/www/my_webapp/www/
```

Sur YunoHost (My Webapp) : activer PHP dans la configuration de l'app ;
les pages d'administration sont alors servies telles quelles. La limite
d'upload nginx par défaut (1 Mo) est inférieure aux 5 Mo autorisés par les
pages d'administration : la relever via le fichier SSI ci-dessous
(`client_max_body_size`).

## Inclusion du footer (SSI)

`index.html`, `tennis.html` et `padel.html` chargent le pied de page via :

```html
<!--#include virtual="footer.html" -->
```

C'est une inclusion **Server Side Include** : elle ne fonctionne que servie
par un serveur HTTP avec SSI activé (ex. nginx avec `ssi on;`), pas en
ouvrant le fichier directement depuis le disque. `contact.html` a son
footer en dur pour cette raison.

### Activation sur YunoHost (nginx)

Ne pas éditer `my_webapp.conf` (régénéré à chaque upgrade ou changement de
configuration de l'app) : le dossier `my_webapp.d/` est l'emplacement
prévu par l'app pour les personnalisations persistantes — son contenu est
inclus par le template nginx officiel et conservé lors des upgrades.

```bash
cat > /etc/nginx/conf.d/www.tcmedullienne.local.d/my_webapp.d/ssi.conf <<'EOF'
ssi on;
client_max_body_size 10M;
EOF

systemctl reload nginx
```

- `ssi on;` active l'inclusion du footer (s'applique à tout le site servi
  à la racine) ;
- `client_max_body_size 10M;` relève la limite d'upload nginx (1 Mo par
  défaut) au-dessus des 5 Mo acceptés par les pages d'administration.

Après un `yunohost app change-url` ou une reconfiguration de l'app, ces
fichiers personnalisés sont conservés (contrairement à `my_webapp.conf`).

## Dépendances externes

- **Leaflet 1.9.4** (carte OpenStreetMap) — chargé via CDN sur `index.html`
- **Google Fonts** (Montserrat, Open Sans) — chargées via CDN sur toutes
  les pages

Le site fonctionne hors ligne, mais sans carte ni polices.

## Publication

Ouverture locale (footer SSI non résolu, sauf pour `contact.html` ; pages
d'administration non fonctionnelles sans PHP) :

```bash
cd site-web && python -m http.server 8000
```

## Formulaire de contact

Attention : le formulaire (`contact.html`) est actuellement purement
décoratif — l'action est vide et l'envoi affiche seulement une alerte côté
navigateur. Aucun email n'est réellement transmis. À brancher sur un
service d'envoi (ex. le script du dossier `notif-inscriptions` ou un
service type Formspree) avant la mise en production.

## Sponsors et événements

Tant que `sponsors.json` est absent ou vide, la section sponsors est
masquée sur les pages publiques. Tant que `evenements.json` est absent ou
vide, le carrousel affiche les slides présents dans `index.html`
(placeholders à remplacer par de vraies photos via l'administration).
