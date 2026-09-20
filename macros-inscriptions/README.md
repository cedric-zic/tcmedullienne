# macros-inscriptions

Macros LibreOffice Basic de la feuille d'adhérents `gestion_adherents_2026-2027.ods`.
Le fichier `.ods` lui-même n'est **pas versionné** (données réelles, exclu par le `.gitignore`) — seules les macros le sont.

## Organisation

| Contenu | Rôle |
|---|---|
| `sync_macros.ps1` | Synchronisation profil LibreOffice ↔ dépôt Git |
| `profil-lo/` | Copie versionnée des bibliothèques Basic (`*.bas`, `*.xba`, `script.xlb`...) |

## Synchronisation des macros

Les macros Basic sont stockées dans le profil utilisateur LibreOffice :
`%APPDATA%\LibreOffice\4\user\basic\` (une bibliothèque = un sous-dossier).

### Récupérer les macros dans le dépôt (après une modif dans LibreOffice)

```powershell
cd macros-inscriptions
.\sync_macros.ps1 -Push
git add profil-lo/
git commit -m "Mise a jour des macros"
git push
```

### Restaurer les macros sur un poste (nouvelle machine, réinstallation)

```powershell
cd macros-inscriptions
.\sync_macros.ps1 -Pull
```

puis redémarrer LibreOffice.

### Notes

- La bibliothèque `Standard` (macros par défaut de LibreOffice) est exclue de la synchronisation.
- Adapter `$ExcludeDirs` dans `sync_macros.ps1` si ta bibliothèque de macros s'appelle autrement.
- Fermer LibreOffice avant un `-Pull` pour éviter tout conflit d'écriture.

## Documentation des macros

> **À compléter** — la documentation détaillée (nom des macros, rôles, déclencheurs,
> effets sur la feuille) sera ajoutée ici à partir du contenu du fichier Basic.

## Fichier concerné

- `P:/2026-2027/Adhérents/gestion_adherents_2026-2027.ods` — feuille des adhérents,
  même fichier source que `notif-inscriptions/` (lignes 7-8, colonnes P/T/U).
