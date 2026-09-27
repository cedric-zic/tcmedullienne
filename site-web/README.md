# site-web

Site web statique de présentation du TC La M\u00e9dullienne : pages d'accueil,
Tennis, Padel et Contact. Le club est pr\u00e9sent\u00e9 sur ses deux sites, Avensan
et Castelnau de M\u00e9doc.

Aucune build, aucun framework : HTML/CSS/JS purs, servables tels quels.

## Pages

| Fichier | Contenu |
|---|---|
| `index.html` | Accueil : pr\u00e9sentation du club, carrousel d'\u00e9v\u00e9nements, horaires, carte des deux sites |
| `tennis.html` | Page Tennis |
| `padel.html` | Page Padel |
| `contact.html` | Formulaire de contact + coordonn\u00e9es compl\u00e8tes |
| `footer.html` | Fragment de pied de page inclus dans les autres pages |

## Fichiers

| Fichier | R\u00f4le |
|---|---|
| `styles.css` | Styles du site (Montserrat / Open Sans via Google Fonts) |
| `script.js` | Carte Leaflet, carrousel, rotation des sponsors, menu mobile, formulaire, email obfusqu\u00e9 |
| `images/logo.png` | Logo du club |

## Inclusion du footer (SSI)

`index.html`, `tennis.html` et `padel.html` chargent le pied de page via :

```html
<!--#include virtual="footer.html" -->
```

C'est une inclusion **Server Side Include** : elle ne fonctionne que servie
par un serveur HTTP avec SSI activ\u00e9 (Apache avec `mod_include`), pas en
ouvrant le fichier directement depuis le disque. `contact.html` a son footer
en dur pour cette raison.

## D\u00e9pendances externes

- **Leaflet 1.9.4** (carte OpenStreetMap) \u2014 charg\u00e9 via CDN sur `index.html`
- **Google Fonts** (Montserrat, Open Sans) \u2014 charg\u00e9es via CDN sur toutes
  les pages

Le site fonctionne hors ligne, mais sans carte ni polices.

## Publication

Ouverture locale (footer SSI non r\u00e9solu, sauf pour `contact.html`) :

```bash
cd site-web && python -m http.server 8000
```

En production, d\u00e9ployer le dossier tel quel sur un h\u00e9bergement avec SSI
activ\u00e9 (ex. Apache : `Options Includes`, fichiers `.shtml` ou `XBitHack`).

## Formulaire de contact

Attention : le formulaire (`contact.html`) est actuellement purement
d\u00e9coratif \u2014 l'action est vide et l'envoi affiche seulement une alerte
c\u00f4t\u00e9 navigateur. Aucun email n'est r\u00e9ellement transmis. \u00c0 brancher sur un
service d'envoi (ex. le script du dossier `notif-inscriptions` ou un
service type Formspree) avant la mise en production.

## Sponsors

La rotation des sponsors (`script.js`) utilise actuellement des logos SVG
de placeholder et des URL `*.example.com` \u00e0 remplacer par les vrais
partenaires.
