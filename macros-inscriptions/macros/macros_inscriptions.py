import unicodedata
import uno
# from datetime import datetime


def normaliser_chaine(chaine):
    """
    Normalise une chaîne en :
    1. Supprimant les accents.
    2. Convertissant en minuscules.
    3. Supprimant les espaces superflus.
    """
    if not chaine:
        return ""

    # Supprimer les accents (ex: "é" → "e")
    chaine_sans_accents = unicodedata.normalize('NFKD', chaine)
    chaine_sans_accents = ''.join([c for c in chaine_sans_accents if not unicodedata.combining(c)])

    # Convertir en minuscules et supprimer les espaces superflus
    return chaine_sans_accents.strip().lower()


def copier_donnees_filtrees_vers_groupes(*args):
    # Récupérer le document actuel
    doc = XSCRIPTCONTEXT.getDocument()
    controller = doc.getCurrentController()
    controller.suspend(True)  # Désactive les mises à jour d'écran

    # Récupérer les feuilles
    feuille_source = doc.Sheets.getByName("Liste_adherents")
    feuille_dest = doc.Sheets.getByName("Groupes")
    # log_sheet = doc.Sheets.getByName("Logs")

    max_lignes = 1999
    # start_time = datetime.now()

    # --- 1. NETTOYAGE DES COLONNES A, B, C, D (indices 0 à 3) DANS "Groupes" ---
    last_used_row = 0
    # Trouver la dernière ligne utilisée dans la colonne A de "Groupes"
    while (last_used_row < max_lignes and
           feuille_dest.getCellByPosition(0, last_used_row + 1).getString() != ""):
        last_used_row += 1

    # Nettoyer les colonnes A à D (0 à 3) pour les lignes 1 à last_used_row
    if last_used_row > 0:
        for j in range(4):  # Colonnes 0 à 3
            for i in range(1, last_used_row + 1):  # Lignes 1 à last_used_row
                feuille_dest.getCellByPosition(j, i).setString("")

    # --- 2. TROUVER LA DERNIÈRE LIGNE DANS "Liste_adherents" (colonne A) ---
    last_row = 7
    while (last_row < max_lignes and
           feuille_source.getCellByPosition(0, last_row + 1).getString() != ""):
        last_row += 1

    # --- 3. COPIE DES DONNÉES FILTRÉES ---
    dest_row = 2
    # lignes_copiees = 0

    for i in range(7, last_row + 1):
        nom = feuille_source.getCellByPosition(0, i).getString()
        if not nom:  # Si la cellule est vide, on sort
            break

        prenom = feuille_source.getCellByPosition(1, i).getString()
        abonnement = feuille_source.getCellByPosition(6, i).getString()
        telephone = feuille_source.getCellByPosition(5, i).getString()
        statut = feuille_source.getCellByPosition(21, i).getString() # Colonne V Inscription validée (colonne 22 index 21)

        # # Filtrer les abonnements non souhaités
        # if ("Loisir" not in abonnement and
        #     "Adhésion seule" not in abonnement and
        #     "Padel illimité" not in abonnement and
        #     statut in ["Ok", "En cours"] and
        #     statut != ""):
        abonnement_lower = abonnement.lower()
        statut_condition = (statut in ["Ok", "En cours"]) and (statut != "")

        if not (("loisir" in abonnement_lower) or
                ("adhésion seule" == abonnement_lower) or
                ("padel illimité" == abonnement_lower)) and \
        statut_condition:

            nom_prenom = (nom + "-" + prenom).upper()

            # Écrire dans "Groupes"
            feuille_dest.getCellByPosition(0, dest_row).setString(nom_prenom)  # Nom-Prenom (A)
            feuille_dest.getCellByPosition(1, dest_row).setString(abonnement)   # Formule (B)
            feuille_dest.getCellByPosition(3, dest_row).setString(telephone)   # Téléphone (D)

            dest_row += 1
            # lignes_copiees += 1

    # # --- 4. ÉCRIRE LE TEMPS TOTAL DANS LA FEUILLE "Logs" ---
    # total_time = (datetime.now() - start_time).total_seconds()
    # log_sheet.getCellByPosition(0, 1).setString(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))  # Date
    # log_sheet.getCellByPosition(1, 1).setString(f"{total_time:.3f}")  # Temps écoulé

    controller.suspend(False)  # Réactive les mises à jour d'écran


def MiseEnFormeAdherentsEnregistresNonPresents(*args):
    doc = XSCRIPTCONTEXT.getDocument()
    controller = doc.getCurrentController()
    controller.suspend(True)  # Désactive les mises à jour visuelles

    # Récupérer les feuilles
    feuille_adherents = doc.Sheets.getByName("Liste_adherents")
    feuille_enregistres = doc.Sheets.getByName("adherents_enregistres")
    # log_sheet = doc.Sheets.getByName("Logs")

    # start_time = datetime.now()

    # --- 1. Créer un ensemble des paires (Nom, Prénom) normalisées de "Liste_adherents" ---
    adherents_present_set = set()
    last_row_adherents = 7  # Lignes commencent à 7 (index 6)
    while last_row_adherents < 1007 and feuille_adherents.getCellByPosition(0, last_row_adherents).getString() != "":
        nom = feuille_adherents.getCellByPosition(0, last_row_adherents).getString().strip()
        prenom = feuille_adherents.getCellByPosition(1, last_row_adherents).getString().strip()

        # Normaliser les chaînes (sans accents, en minuscules)
        nom_normalise = normaliser_chaine(nom)
        prenom_normalise = normaliser_chaine(prenom)

        if nom_normalise and prenom_normalise:
            adherents_present_set.add((nom_normalise, prenom_normalise))
        last_row_adherents += 1

    # --- 2. Réinitialiser les couleurs de "adherents_enregistres" (optionnel) ---
    last_row_enregistres = 0
    while last_row_enregistres < 1007 and feuille_enregistres.getCellByPosition(1, last_row_enregistres).getString() != "":
        feuille_enregistres.getCellByPosition(1, last_row_enregistres).setPropertyValue("CellBackColor", 0xFFFFFF)  # Blanc
        feuille_enregistres.getCellByPosition(2, last_row_enregistres).setPropertyValue("CellBackColor", 0xFFFFFF)  # Blanc
        last_row_enregistres += 1

    # --- 3. Parcourir "adherents_enregistres" et colorer les absents ---
    last_row_enregistres = 0
    while last_row_enregistres < 1007 and feuille_enregistres.getCellByPosition(1, last_row_enregistres).getString() != "":
        nom = feuille_enregistres.getCellByPosition(1, last_row_enregistres).getString().strip()  # Colonne B (Nom)
        prenom = feuille_enregistres.getCellByPosition(2, last_row_enregistres).getString().strip()  # Colonne C (Prénom)

        # Normaliser les chaînes
        nom_normalise = normaliser_chaine(nom)
        prenom_normalise = normaliser_chaine(prenom)

        if nom_normalise and prenom_normalise:
            if (nom_normalise, prenom_normalise) not in adherents_present_set:
                # Colorer en rouge pâle
                feuille_enregistres.getCellByPosition(1, last_row_enregistres).setPropertyValue("CellBackColor", 0xFFCCCC)  # Nom (B)
                feuille_enregistres.getCellByPosition(2, last_row_enregistres).setPropertyValue("CellBackColor", 0xFFCCCC)  # Prénom (C)

        last_row_enregistres += 1

    # # --- 4. Écrire les logs ---
    # end_time = datetime.now()
    # duration = (end_time - start_time).total_seconds()
    # log_sheet.getCellByPosition(0, 55).setString(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    # log_sheet.getCellByPosition(3, 55).setString(f"Mise à jour des adhérents manquants : {duration:.3f} secondes")

    controller.suspend(False)  # Réactive les mises à jour visuelles


def AppliquerMiseEnFormeEtCompterOccurrences(*args):
    doc = XSCRIPTCONTEXT.getDocument()
    controller = doc.getCurrentController()
    controller.suspend(True)  # Désactive les mises à jour visuelles

    feuille = doc.Sheets.getByName("Groupes")
    # log_sheet = doc.Sheets.getByName("Logs")

    # Colonnes à inclure (indices 0-based)
    colonnes_inclues = [7,8,9,10, 12,13,14,15, 17,18,19,20, 22,23,24,25, 27,28,29,30, 32,33,34,35 ]
    colonnes_exclues = [6, 11, 16, 21, 26, 31]
    # Colonnes pour les bordures (6 à 34 inclus)
    colonnes_bordure = list(range(6, 36))

    # start_time = datetime.now()

    # --- 1. Trouver la dernière ligne dans "Groupes" (colonne A) ---
    last_row_groupes = feuille.Rows.Count - 1
    if last_row_groupes > 1999:
        last_row_groupes = 1999
    while last_row_groupes > 0 and feuille.getCellByPosition(0, last_row_groupes).getString() == "":
        last_row_groupes -= 1

    # --- 2. Pré-charger les noms valides (colonne A, lignes 1 à last_row_groupes) ---
    noms_valides = set()
    for k in range(2, last_row_groupes + 1):
        nom = feuille.getCellByPosition(0, k).getString()
        if nom:
            noms_valides.add(nom)

    # --- 3. Identifier les noms invalides et les marquer en rouge ---
    for j in range(2, 70):  # Lignes 1 à 70
        for i in colonnes_inclues:
            cell = feuille.getCellByPosition(i, j)
            nom = cell.getString()
            if nom and nom not in noms_valides:
                cell.setPropertyValue("CellBackColor", 0xffcccc)  # Rouge clair pour les noms invalides

    # --- 4. Compter les occurrences des noms valides ---
    comptes_noms = {}
    for j in range(2, 70):
        for i in colonnes_inclues:
            nom = feuille.getCellByPosition(i, j).getString()
            if nom and nom in noms_valides:  # On ne compte que les noms valides
                if nom in comptes_noms:
                    comptes_noms[nom] += 1
                else:
                    comptes_noms[nom] = 1

    # --- 5. Appliquer les couleurs en fonction des comptes (uniquement pour les noms valides) ---
    for j in range(2, 70):
        for i in colonnes_inclues:
            cell = feuille.getCellByPosition(i, j)
            nom = cell.getString()
            if nom and nom in noms_valides:  # On ignore les noms invalides (déjà en rouge)
                count = comptes_noms.get(nom, 0)
                if count == 0:
                    cell.setPropertyValue("CellBackColor", 0xFFFFFF)  # Blanc
                elif count == 1:
                    cell.setPropertyValue("CellBackColor", 0x90EE90)  # Vert clair
                elif count == 2:
                    cell.setPropertyValue("CellBackColor", 0x228B22)  # Vert foncé
                elif count == 3:
                    cell.setPropertyValue("CellBackColor", 0xE8A202)  # Jaune
                elif count == 4:
                    cell.setPropertyValue("CellBackColor", 0xB697F6)  # Violet clair
                elif count >= 5:
                    cell.setPropertyValue("CellBackColor", 0x8A2BDE)  # Violet foncé
            else:
                if nom:  # Nom présent mais invalide (ex: faute de frappe)
                    cell.setPropertyValue("CellBackColor", 0xFFCCCC)  # Rouge clair
                else:    # Cellule vide
                    cell.setPropertyValue("CellBackColor", 0xFFFFFF)  # Blanc

    # --- 6. Écrire les résultats dans la colonne C et appliquer les couleurs ---
    for i in range(2, last_row_groupes + 1):
        nom = feuille.getCellByPosition(0, i).getString()
        if nom:
            count = comptes_noms.get(nom, 0)
            # Écrire le compte dans la colonne C (index 2)
            feuille.getCellByPosition(2, i).setString(str(count))
            # Appliquer la couleur à la colonne C et A
            if nom not in noms_valides:
                color = 0xffcccc  # Rouge clair pour les noms invalides
            else:
                if count == 0:
                    color = 0xFFFFFF  # Blanc
                elif count == 1:
                    color = 0x90EE90  # Vert clair
                elif count == 2:
                    color = 0x228B22  # Vert foncé
                elif count == 3:
                    color = 0xE8A202  # Jaune
                elif count == 4:
                    color = 0xB697F6  # Violet clair
                else:  # count >= 5
                    color = 0x8A2BDE  # Violet foncé

            feuille.getCellByPosition(2, i).setPropertyValue("CellBackColor", color)
            feuille.getCellByPosition(0, i).setPropertyValue("CellBackColor", color)

    # --- 7. Appliquer les bordures ---
    border = uno.createUnoStruct("com.sun.star.table.BorderLine2")
    border.OuterLineWidth = 1
    border.Color = 0x000000  # Noir
    border.LineStyle = 0  # Continu

    for j in range(2, 70):
        for i in colonnes_bordure:
            cell = feuille.getCellByPosition(i, j)
            cell.setPropertyValue("TopBorder", border)
            cell.setPropertyValue("BottomBorder", border)
            cell.setPropertyValue("LeftBorder", border)
            cell.setPropertyValue("RightBorder", border)

    # # --- 8. Écrire les logs ---
    # end_time = datetime.now()
    # duration = (end_time - start_time).total_seconds()

    # log_sheet.getCellByPosition(0, 2).setString(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))  # Log pour la mise en forme
    # log_sheet.getCellByPosition(2, 2).setString(f"{duration:.3f}")

    controller.suspend(False)  # Réactive les mises à jour visuelles


def AppliquerMiseEnFormeConditionnelle_Montants_ListeAdherents(*args):
    doc = XSCRIPTCONTEXT.getDocument()
    controller = doc.getCurrentController()
    controller.suspend(True)  # Désactive les mises à jour visuelles
    # Definition des constantes de colonne (Nom et index-0)
    INDEX_FAMILLE = 3 # Colonne D - Famille = 3
    INDEX_FICHE_VALIDEE = 15 # Colonne P (Fiche validée)
    INDEX_PREINSCRIPTION = 16 # Colonne Q (Pré-inscription ADOC)
    INDEX_FICHE_NUMERISEE = 18 # Colonne S (Fiche numérisée)
    INDEX_INSCRIPTION_VALIDEE = 21 # Colonne V (Inscription validée ADOC)
    INDEX_LICENCE_GENEREE = 22 # Colonne W (Licence générée ADOC)
    INDEX_DEMANDE_RECU = 23 # Colonne X (Demande reçu)
    INDEX_PAIEMENT = 24 # Colonne Y (Paiement)

    INDEX_MONTANT_CLUB = 25 # Colonne Z - Montant Club
    INDEX_RESTE_DU = 26 # Colonne AA - Reste dû
    INDEX_MOYEN_PAIEMENT = 27 # colonne AB - Moyen paiement

    INDEX_NOUVEAU_ADHERENT = 60  # Colonne BI (61ème colonne, index 60)

    feuille = doc.Sheets.getByName("Liste_adherents")
    # log_sheet = doc.Sheets.getByName("Logs")

    # start_time = datetime.now()

    # --- 1. Trouver la dernière ligne avec des données dans la colonne A ---
    last_row = 7
    while last_row < 1007 and feuille.getCellByPosition(0, last_row + 1).getString() != "":
        last_row += 1

    # --- 2. MISE EN FORME DE Z8:Z[lastRow] (vert clair si > 0) Colonne Montant club ---
    for i in range(7, last_row + 1):
        cell_montant_club = feuille.getCellByPosition(INDEX_MONTANT_CLUB, i)
        try:
            montant = float(cell_montant_club.getValue())
            if montant > 0:
                cell_montant_club.setPropertyValue("CellBackColor", 0x90EE90)  # Vert clair (style "Correct")
            else:
                cell_montant_club.setPropertyValue("CellBackColor", 0xFFFFFF)  # Blanc (style "Default")
        except ValueError:
            cell_montant_club.setPropertyValue("CellBackColor", 0xFFFFFF)  # Blanc si non numérique

    # --- 3. MISE EN FORME DE AA8:AA[lastRow] (selon conditions) colonne Reste dû ---
    for i in range(7, last_row + 1):
        cell_montant_club = feuille.getCellByPosition(INDEX_MONTANT_CLUB, i)
        cell_reste_du = feuille.getCellByPosition(INDEX_RESTE_DU, i)
        try:
            montant_total = float(cell_montant_club.getValue())
            reste_du = float(cell_reste_du.getValue())

            if reste_du == 0:
                cell_reste_du.setPropertyValue("CellBackColor", 0x90EE90)  # Vert clair (style "Correct")
            elif reste_du > 0:
                cell_reste_du.setPropertyValue("CellBackColor", 0xffffcc)  # Gris clair (style "Neutre")
            elif reste_du < 0:
                if (montant_total + reste_du) == 0:
                    cell_reste_du.setPropertyValue("CellBackColor", 0xffcccc)  # Rouge clair (style "Incorrect")
                else:
                    cell_reste_du.setPropertyValue("CellBackColor", 0xffffcc)  # Gris clair (style "Neutre")
        except ValueError:
            cell_reste_du.setPropertyValue("CellBackColor", 0xFFFFFF)  # Blanc si erreur

    # --- 3.5. MISE EN FORME ET CALCUL DU STATUT DE PAIEMENT (COLONNE Y, INDEX 24) ---
    for i in range(7, last_row + 1):
        cell_montant_club = feuille.getCellByPosition(INDEX_MONTANT_CLUB, i)  # Colonne Z (25)
        cell_reste_du = feuille.getCellByPosition(INDEX_RESTE_DU, i)          # Colonne AA (26)
        cell_paiement = feuille.getCellByPosition(INDEX_PAIEMENT, i)          # Colonne Y (24)

        if cell_montant_club.getString() != "":
            try:
                montant_club = cell_montant_club.getValue()
                reste_du = cell_reste_du.getValue()

                # Logique validée avec tes exemples
                if reste_du == 0:
                    statut_paiement = "Oui"  # Paiement complet (ex: 175 / 0,00 €)
                elif reste_du > 0:
                    statut_paiement = "Remboursement"  # Trop payé (ex: 120 / 30,00 €)
                elif reste_du < 0:
                    if (montant_club + reste_du) == 0:
                        statut_paiement = "Non"  # Aucun paiement (ex: 120 / -120,00 €)
                    else:
                        statut_paiement = "Partiel"  # Paiement partiel (ex: 175 / -25,00 €)

                # Écrire le statut dans la colonne Y
                cell_paiement.setString(statut_paiement)

                # Appliquer une couleur selon le statut
                if statut_paiement == "Oui":
                    cell_paiement.setPropertyValue("CellBackColor", 0x90EE90)  # Vert clair
                elif statut_paiement == "Non":
                    cell_paiement.setPropertyValue("CellBackColor", 0xffcccc)  # Rouge clair
                elif statut_paiement == "Partiel":
                    cell_paiement.setPropertyValue("CellBackColor", 0xffffcc)  # Or
                elif statut_paiement == "Remboursement":
                    cell_paiement.setPropertyValue("CellBackColor", 0xD3D3D3)  # Gris clair

            except:
                cell_paiement.setString("Erreur")
                cell_paiement.setPropertyValue("CellBackColor", 0xFFFFFF)  # Blanc
        else:
            cell_paiement.setString("")
            cell_paiement.setPropertyValue("CellBackColor", 0xFFFFFF)  # Blanc

    # --- 4. MISE EN FORME CONDITIONNELLE POUR LA COLONNE D (si valeur apparaît ≥ 3 fois) Colonne Famille 3---
    # Compter les occurrences de chaque valeur dans la colonne D (lignes 7 à 1007)
    compte_colonne_famille = {}
    for i in range(7, 1008):  # Lignes 8 à 1008 (indices 7 à 1007)
        if feuille.getCellByPosition(0, i).getString() != "":  # Si la colonne A n'est pas vide
            valeur_famille = feuille.getCellByPosition(INDEX_FAMILLE, i).getString()
            if valeur_famille:
                if valeur_famille in compte_colonne_famille:
                    compte_colonne_famille[valeur_famille] += 1
                else:
                    compte_colonne_famille[valeur_famille] = 1

    # Appliquer le style "Correct" (vert clair) si la valeur apparaît ≥ 3 fois
    for i in range(7, 1008):
        if feuille.getCellByPosition(0, i).getString() != "":
            valeur_famille = feuille.getCellByPosition(INDEX_FAMILLE, i).getString()
            if valeur_famille and compte_colonne_famille.get(valeur_famille, 0) >= 3:
                feuille.getCellByPosition(INDEX_FAMILLE, i).setPropertyValue("CellBackColor", 0x90EE90)  # Vert clair

    # --- 5. MISE EN FORME DES COLONNES P, Q, S, U, V (selon conditions) ---
    # Définir les colonnes et leurs conditions
    colonnes_et_conditions = [
        (INDEX_FICHE_VALIDEE, {"Ok": 0x90EE90, "En cours": 0xffcccc, "Annulé": 0xffffcc}),  # Colonne P (Fiche validée)
        (INDEX_PREINSCRIPTION, {"Ok": 0x90EE90, "En cours": 0xffcccc, "Annulé": 0xffffcc}),  # Colonne Q (Pré-inscription)
        (INDEX_FICHE_NUMERISEE, {"Oui": 0x90EE90, "Oui - Prof": 0x90EE90, "Non": 0xffcccc}),  # Colonne S (Fiche numérisée)
        (INDEX_INSCRIPTION_VALIDEE, {"Ok": 0x90EE90, "En cours": 0xffcccc, "Annulé": 0xffffcc}),  # Colonne V (Inscription validée)
        (INDEX_LICENCE_GENEREE, {"Ok": 0x90EE90, "En cours": 0xffcccc, "Annulé": 0xffffcc}),  # Colonne X (Licence générée)
        (INDEX_DEMANDE_RECU, {"traité": 0x90EE90, "encours": 0xffcccc, "demandé": 0xffffcc}),  # Colonne X (Demande reçu)
        (INDEX_MOYEN_PAIEMENT, {"CB": 0x90EE90, "Chèque": 0x90EE90, "Espèce": 0x90EE90, "Virement": 0x90EE90}),  # Colonne AB (Moyen paiement)
    ]

    for colonne, conditions in colonnes_et_conditions:
        for i in range(7, last_row + 1):
            cell = feuille.getCellByPosition(colonne, i)
            valeur = cell.getString()
            if valeur in conditions:
                cell.setPropertyValue("CellBackColor", conditions[valeur])
            else:
                cell.setPropertyValue("CellBackColor", 0xFFFFFF)  # Blanc (style "Default")

    # --- NOUVELLE SECTION : MISE EN FORME POUR LES NOUVEAUX ADHÉRENTS (COLONNE BI = 1) ---
    # Debug : Vérifier que l'index 60 correspond à BI
    # col_name = feuille.getCellByPosition(INDEX_NOUVEAU_ADHERENT, 0).getCellAddress().Column
    # log_sheet.getCellByPosition(0, 45).setString(f"Index 60 = colonne {col_name} (BI=62)")

    # Debug : Vérifier le format de BI pour la ligne 66
    # cell_bi_66 = feuille.getCellByPosition(INDEX_NOUVEAU_ADHERENT, 65)
    # log_sheet.getCellByPosition(0, 46).setString(f"Ligne 66, BI : Type={type(cell_bi_66.getValue())}, Valeur={cell_bi_66.getValue()}")

    # Debug : Lister les adhérents avec BI=1
    # log_row = 50
    # log_sheet.getCellByPosition(0, log_row).setString("Adhérents avec BI=1 :")
    # log_row += 1

    # nombre_nouveaux_adherents = 0
    for i in range(7, last_row + 1):
        cell_nouveau_adherent = feuille.getCellByPosition(INDEX_NOUVEAU_ADHERENT, i)
        valeur_str = cell_nouveau_adherent.getString().strip()
        valeur_num = cell_nouveau_adherent.getValue()

        # nom = feuille.getCellByPosition(0, i).getString()
        # prenom = feuille.getCellByPosition(1, i).getString()

        if (valeur_str == "1" or valeur_num == 1 or valeur_num == 1.0):
            # log_sheet.getCellByPosition(0, log_row).setString(f"Ligne {i+1} : {nom} {prenom} (BI={valeur_str or valeur_num})")
            # log_row += 1

            # Colorer les colonnes A et B en vert
            feuille.getCellByPosition(0, i).setPropertyValue("CellBackColor", 0x90EE90)
            feuille.getCellByPosition(1, i).setPropertyValue("CellBackColor", 0x90EE90)
            # nombre_nouveaux_adherents += 1

    # log_sheet.getCellByPosition(0, 16).setString(f"Nombre de nouveaux adhérents : {nombre_nouveaux_adherents}")
    # --- 6. ÉCRIRE LE TEMPS TOTAL DANS LA FEUILLE LOGS ---
    # end_time = datetime.now()
    # duration = (end_time - start_time).total_seconds()

    # log_sheet.getCellByPosition(0, 4).setString(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    # log_sheet.getCellByPosition(3, 4).setString(f"{duration:.3f}")

    controller.suspend(False)  # Réactive les mises à jour visuelles


def AppliquerMiseEnForme_PlageMensuelle_ListeAdherents(*args):
    doc = XSCRIPTCONTEXT.getDocument()
    controller = doc.getCurrentController()
    controller.suspend(True)  # Désactive les mises à jour visuelles

    feuille = doc.Sheets.getByName("Liste_adherents")
    # log_sheet = doc.Sheets.getByName("Logs")

    # start_time = datetime.now()

    # --- 1. Trouver la dernière ligne avec des données dans la colonne A ---
    last_row = 7
    while last_row < 1007 and feuille.getCellByPosition(0, last_row + 1).getString() != "":
        last_row += 1

    # --- 2. Traiter chaque colonne de 29 à 58 (plage mensuelle) ---
    for j in range(29, 58):  # Colonnes 29 à 58 (inclus)
        for i in range(7, last_row + 1):
            cell = feuille.getCellByPosition(j, i)
            cell_value = cell.getString()
            if cell_value != "":
                # Cellule non vide → colorer en vert clair
                cell.setPropertyValue("CellBackColor", 0x90EE90)
            else:
                # Cellule vide → laisser en blanc (ou forcer le blanc si nécessaire)
                cell.setPropertyValue("CellBackColor", 0xFFFFFF)

    # --- 3. Écrire les logs ---
    # end_time = datetime.now()
    # duration = (end_time - start_time).total_seconds()

    # log_sheet.getCellByPosition(0, 5).setString(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    # log_sheet.getCellByPosition(4, 5).setString(f"{duration:.3f}")

    controller.suspend(False)  # Réactive les mises à jour visuelles


def VerifierDoublonsNomPrenom(*args):
    """
    Vérifie les doublons dans les colonnes A (Nom) et B (Prénom) de la feuille Liste_adherents.
    - Détecte les doublons et les signale.
    - Colorie en rouge les doublons.
    - Réinitialise en blanc les cellules si le doublon est supprimé ou corrigé.
    """
    doc = XSCRIPTCONTEXT.getDocument()
    feuille = doc.Sheets.getByName("Liste_adherents")

    # Trouver la dernière ligne avec des données dans la colonne A
    last_row = 7
    while last_row < 1007 and feuille.getCellByPosition(0, last_row + 1).getString() != "":
        last_row += 1

    # Dictionnaire pour stocker les paires Nom+Prénom et leurs lignes
    noms_prenoms = {}
    doublons = set()  # Stocker les indices des lignes en doublon

    # Parcourir les lignes pour détecter les doublons
    for i in range(7, last_row + 1):
        nom = feuille.getCellByPosition(0, i).getString().strip()  # Colonne A (Nom)
        prenom = feuille.getCellByPosition(1, i).getString().strip()  # Colonne B (Prénom)

        if nom and prenom:  # Ignorer les lignes vides
            cle = f"{nom}|{prenom}"  # Clé unique pour la paire Nom+Prénom
            if cle in noms_prenoms:
                # Doublon détecté : ajouter les deux lignes au set des doublons
                doublons.add(noms_prenoms[cle])
                doublons.add(i)
            else:
                noms_prenoms[cle] = i  # Stocker l'index de la ligne

    # Réinitialiser TOUTES les cellules des colonnes A et B en blanc
    for i in range(7, last_row + 1):
        feuille.getCellByPosition(0, i).setPropertyValue("CellBackColor", 0xFFFFFF)  # Blanc
        feuille.getCellByPosition(1, i).setPropertyValue("CellBackColor", 0xFFFFFF)  # Blanc

    # Colorer UNIQUEMENT les doublons actuels en rouge
    for ligne in doublons:
        # Vérifier que la ligne existe toujours (au cas où elle aurait été supprimée)
        if ligne <= last_row:
            feuille.getCellByPosition(0, ligne).setPropertyValue("CellBackColor", 0xFF6464)  # Rouge clair
            feuille.getCellByPosition(1, ligne).setPropertyValue("CellBackColor", 0xFF6464)  # Rouge clair


# ===== MACROS DE GROUPE =====
def MiseEnForme_Groupes(*args):
    # copier_donnees_filtrees_vers_groupes()
    AppliquerMiseEnFormeEtCompterOccurrences()

def MiseAJour_Groupes(*args):
    copier_donnees_filtrees_vers_groupes()

def MiseEnForme_ListeAdherents(*args):
    VerifierDoublonsNomPrenom()
    AppliquerMiseEnFormeConditionnelle_Montants_ListeAdherents()
    AppliquerMiseEnForme_PlageMensuelle_ListeAdherents()
    MiseEnFormeAdherentsEnregistresNonPresents()

def MiseAJourComplete(*args):
    copier_donnees_filtrees_vers_groupes()
    MiseEnForme_ListeAdherents()
    MiseEnForme_Groupes()
