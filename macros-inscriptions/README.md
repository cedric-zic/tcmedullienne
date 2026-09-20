# macros-inscriptions

Macros **Python** LibreOffice de la feuille d'adhérents `gestion_adherents_2026-2027.ods`.
Le fichier `.ods` lui-même n'est **pas versionné** (données réelles, exclu par le `.gitignore`) — seules les macros le sont.

## Organisation

| Contenu | Rôle |
|---|---|
| `sync_macros.ps1` | Synchronisation profil LibreOffice ↔ dépôt Git |
| `macros/macros_inscriptions.py` | Fichier de macros versionné (copie conforme du fichier dans le profil LibreOffice) |

## Synchronisation des macros

Les macros Python LibreOffice sont stockées dans le profil utilisateur :
`%APPDATA%\LibreOffice\4\user\Scripts\python\` (un fichier `.py` par module).

⚠️ Le nom du fichier versionné (`macros/macros_inscriptions.py`) doit correspondre
au nom du fichier réellement présent dans le profil LibreOffice. Si ton fichier
s'appelle autrement, ajuste `$MacroFile` dans `sync_macros.ps1`.

### Récupérer les macros dans le dépôt (après une modif dans LibreOffice)

```powershell
cd macros-inscriptions
.\sync_macros.ps1 -Push
git add macros/
git commit -m "Mise a jour des macros"
git push
```

### Restaurer les macros sur un poste (nouvelle machine, réinstallation)

```powershell
cd macros-inscriptions
.\sync_macros.ps1 -Pull
```

puis redémarrer LibreOffice. Le `-Pull` crée automatiquement une sauvegarde
`.bak` du fichier existant avant de l'écraser.

## Documentation des macros

Exécutables depuis **Outils → Macros → Macros Python → Mes macros → macros_inscriptions**
(ou via l'organisateur de macros), document actif requis.

### Macros de groupe (les seules à lancer directement)

| Macro | Rôle |
|---|---|
| `MiseAJourComplete` | Tout-en-un : copie des données → mise en forme `Liste_adherents` → mise en forme `Groupes`. Le point d'entrée normal. |
| `MiseAJour_Groupes` | Recopie uniquement les adhérents filtrés vers la feuille `Groupes`. |
| `MiseEnForme_Groupes` | Recolore/compte les occurrences dans `Groupes` (sans recopier). |
| `MiseEnForme_ListeAdherents` | Toute la mise en forme de `Liste_adherents` (doublons, statuts, paiements, plage mensuelle, absents). |

### Macros individuelles

| Macro | Feuille | Rôle |
|---|---|---|
| `copier_donnees_filtrees_vers_groupes` | `Liste_adherents` → `Groupes` | Vide les colonnes A-D de `Groupes`, puis recopie `NOM-Prénom`, abonnement et téléphone des adhérents **hors** formules Loisir / Adhésion seule / Padel illimité, dont le statut d'inscription (col. V) est « Ok » ou « En cours ». |
| `MiseEnFormeAdherentsEnregistresNonPresents` | `adherents_enregistres` | Colore en rouge pâle les adhérents de la feuille `adherents_enregistres` absents de `Liste_adherents` (comparaison normalisée : sans accents, minuscules). |
| `AppliquerMiseEnFormeEtCompterOccurrences` | `Groupes` | Compte les inscriptions de chaque adhérent dans les plages de créneaux, colore selon le nombre d'occurrences (vert 1, vert foncé 2, jaune 3, violet 4+, rouge = nom inconnu/faute de frappe), écrit le compte en colonne C, applique des bordures. |
| `AppliquerMiseEnFormeConditionnelle_Montants_ListeAdherents` | `Liste_adherents` | Mise en forme des colonnes de suivi : Montant club (Z), Reste dû (AA), **calcul du statut de paiement (Y : Oui/Non/Partiel/Remboursement)**, Famille (D, vert si ≥ 3 membres), statuts Ok/En cours/Annulé (P, Q, S, V, W, X), moyen de paiement (AB), nouveaux adhérents (BI=1 → colonnes A/B en vert). |
| `AppliquerMiseEnForme_PlageMensuelle_ListeAdherents` | `Liste_adherents` | Colore en vert clair toute cellule renseignée dans la plage mensuelle (colonnes 29-58). |
| `VerifierDoublonsNomPrenom` | `Liste_adherents` | Détecte les doublons Nom+Prénom et colore les lignes concernées en rouge. Réinitialise en blanc au préalable (un doublon corrigé redevient blanc). |

### Convention des colonnes clés (feuille `Liste_adherents`)

| Colonne | Contenu |
|---|---|
| A/B | Nom / Prénom (données dès la ligne 8, index 7) |
| D | Famille |
| P | Fiche validée |
| Q | Pré-inscription ADOC |
| S | Fiche numérisée |
| V | Inscription validée ADOC |
| W | Licence générée |
| X | Demande reçu |
| Y | Paiement (calculé par la macro) |
| Z / AA | Montant club / Reste dû (négatif = il reste à payer) |
| AB | Moyen paiement |
| BI | Nouvel adhérent (1) |

### Notes techniques

- Les macros utilisent `XSCRIPTCONTEXT` (fourni par LibreOffice) et `uno` : elles ne
  peuvent s'exécuter que **dans** LibreOffice, pas en script Python autonome.
- La mise à jour d'écran est suspendue pendant l'exécution (`controller.suspend`) pour la vitesse.
- Les colonnes exclues des comptes d'occurrences correspondent aux créneaux non comptabilisés (ex. moniteurs).
- Le fichier de macros ne lit/écrit que le document ouvert ; aucune donnée n'est envoyée ailleurs.
