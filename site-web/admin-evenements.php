<?php
// admin-evenements.php — gestion des événements du site (ajout,
// modification, suppression) via un simple navigateur. Protégé par mot de
// passe (voir admin-lib.php pour la configuration).

declare(strict_types=1);

require_once __DIR__ . '/admin-lib.php';

define('FICHIER_EVENEMENTS', DOSSIER_RACINE . '/evenements.json');
define('DOSSIER_IMAGES_EVENEMENTS', DOSSIER_RACINE . '/images/evenements');
define('URL_IMAGES_EVENEMENTS', 'images/evenements');

session_start();
$mot_de_passe_attendu = mot_de_passe_admin();

if ($mot_de_passe_attendu === null) {
    http_response_code(500);
    exit('Configuration manquante : créez le fichier .admin-mot-de-passe.php dans le dossier parent de la racine web (voir site-web/README.md).');
}

$message_erreur = '';
$message_succes = '';

if (($_SERVER['REQUEST_METHOD'] ?? 'GET') === 'POST') {
    $action = $_POST['action'] ?? '';

    if ($action === 'connexion') {
        if (tenter_connexion((string)($_POST['mot_de_passe'] ?? ''))) {
            $_SESSION['admin_authentifie'] = true;
        } else {
            $message_erreur = 'Mot de passe incorrect.';
        }
    } elseif (($_SESSION['admin_authentifie'] ?? false) === true) {
        $evenements = array_values(lire_json(FICHIER_EVENEMENTS));

        if ($action === 'deconnexion') {
            deconnexion_admin();
        } elseif ($action === 'ajouter') {
            $titre = trim((string)($_POST['titre'] ?? ''));
            if ($titre === '') {
                $message_erreur = 'Le titre de l\'événement est obligatoire.';
            } else {
                $image = $_FILES['image'] ?? null;
                $nouveau = null;
                if ($image && ($image['error'] ?? UPLOAD_ERR_NO_FILE) !== UPLOAD_ERR_NO_FILE) {
                    $resultat = enregistrer_image($image, DOSSIER_IMAGES_EVENEMENTS);
                    if (!$resultat['succes']) {
                        $message_erreur = $resultat['erreur'];
                    } else {
                        $nouveau = ['titre' => $titre, 'image' => URL_IMAGES_EVENEMENTS . '/' . $resultat['fichier']];
                    }
                }
                if ($nouveau !== null) {
                    $position = (int)($_POST['position'] ?? 0);
                    $position = max(1, min($position, count($evenements) + 1));
                    array_splice($evenements, $position - 1, 0, [$nouveau]);
                    if (ecrire_json(FICHIER_EVENEMENTS, $evenements)) {
                        $message_succes = sprintf('Événement « %s » ajouté (position %d).', $titre, $position);
                    } else {
                        $message_erreur = "Impossible d'écrire evenements.json (vérifiez les droits sur le serveur).";
                    }
                }
            }
        } elseif ($action === 'modifier') {
            $index = (int)($_POST['index'] ?? -1);
            $titre = trim((string)($_POST['titre'] ?? ''));
            if ($titre === '') {
                $message_erreur = 'Le titre de l\'événement est obligatoire.';
            } elseif (!isset($evenements[$index])) {
                $message_erreur = 'Événement introuvable.';
            } else {
                $evenements[$index]['titre'] = $titre;
                $image = $_FILES['image'] ?? null;
                if ($image && ($image['error'] ?? UPLOAD_ERR_NO_FILE) !== UPLOAD_ERR_NO_FILE) {
                    $resultat = enregistrer_image($image, DOSSIER_IMAGES_EVENEMENTS);
                    if (!$resultat['succes']) {
                        $message_erreur = $resultat['erreur'];
                    } else {
                        if (!empty($evenements[$index]['image']) && str_starts_with((string)$evenements[$index]['image'], URL_IMAGES_EVENEMENTS . '/')) {
                            supprimer_image(DOSSIER_IMAGES_EVENEMENTS, basename((string)$evenements[$index]['image']));
                        }
                        $evenements[$index]['image'] = URL_IMAGES_EVENEMENTS . '/' . $resultat['fichier'];
                    }
                }
                if ($message_erreur === '') {
                    $position = (int)($_POST['position'] ?? $index + 1);
                    $position = max(1, min($position, count($evenements)));
                    if ($position - 1 !== $index) {
                        $deplace = array_splice($evenements, $index, 1);
                        array_splice($evenements, $position - 1, 0, $deplace);
                    }
                    if (ecrire_json(FICHIER_EVENEMENTS, $evenements)) {
                        $message_succes = sprintf('Événement « %s » mis à jour.', $titre);
                    } else {
                        $message_erreur = "Impossible d'écrire evenements.json (vérifiez les droits sur le serveur).";
                    }
                }
            }
        } elseif ($action === 'supprimer') {
            $index = (int)($_POST['index'] ?? -1);
            if (!isset($evenements[$index])) {
                $message_erreur = 'Événement introuvable.';
            } else {
                $titre = (string)($evenements[$index]['titre'] ?? '');
                if (!empty($evenements[$index]['image']) && str_starts_with((string)$evenements[$index]['image'], URL_IMAGES_EVENEMENTS . '/')) {
                    supprimer_image(DOSSIER_IMAGES_EVENEMENTS, basename((string)$evenements[$index]['image']));
                }
                array_splice($evenements, $index, 1);
                if (ecrire_json(FICHIER_EVENEMENTS, array_values($evenements))) {
                    $message_succes = sprintf('Événement « %s » supprimé.', $titre);
                } else {
                    $message_erreur = "Impossible d'écrire evenements.json (vérifiez les droits sur le serveur).";
                }
            }
        }
    }
}

$est_authentifie = ($_SESSION['admin_authentifie'] ?? false) === true;
$evenements = $est_authentifie ? array_values(lire_json(FICHIER_EVENEMENTS)) : [];
?>
<!doctype html>
<html lang="fr">
<head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Admin - Événements</title>
    <link href="https://fonts.googleapis.com/css2?family=Montserrat:wght@400;600;700&family=Open+Sans:wght@400;600&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="styles.css" />
</head>
<body>
    <main class="admin-main">
        <h1 class="section-title">Gestion des événements</h1>

        <?php if (!$est_authentifie): ?>
        <form method="post" class="admin-login">
            <input type="hidden" name="action" value="connexion" />
            <div class="form-group">
                <label for="mot_de_passe">Mot de passe</label>
                <input type="password" id="mot_de_passe" name="mot_de_passe" required autofocus />
            </div>
            <button type="submit" class="submit-btn">Se connecter</button>
        </form>

        <?php else: ?>
            <?php if ($message_succes !== ''): ?>
                <p class="admin-message admin-succes"><?= echapper($message_succes) ?></p>
            <?php endif; ?>
            <?php if ($message_erreur !== ''): ?>
                <p class="admin-message admin-erreur"><?= echapper($message_erreur) ?></p>
            <?php endif; ?>

            <h2>Événements actuels</h2>
            <?php if (count($evenements) === 0): ?>
                <p class="admin-vide">Aucun événement pour le moment. Ajoutez le premier ci-dessous.</p>
            <?php else: ?>
            <div class="admin-liste">
                <?php foreach ($evenements as $index => $evenement): ?>
                <div class="admin-item">
                    <img class="admin-miniature" src="<?= echapper((string)($evenement['image'] ?? '')) ?>" alt="<?= echapper((string)($evenement['titre'] ?? '')) ?>" />
                    <form method="post" class="admin-item-form" enctype="multipart/form-data">
                        <input type="hidden" name="action" value="modifier" />
                        <input type="hidden" name="index" value="<?= $index ?>" />
                        <div class="form-group">
                            <label>Titre</label>
                            <input type="text" name="titre" value="<?= echapper((string)($evenement['titre'] ?? '')) ?>" required />
                        </div>
                        <div class="form-group">
                            <label>Position</label>
                            <input type="number" name="position" min="1" max="<?= count($evenements) ?>" value="<?= $index + 1 ?>" />
                        </div>
                        <div class="form-group">
                            <label>Remplacer l'image (optionnel)</label>
                            <input type="file" name="image" accept=".jpg,.jpeg,.png,.gif,.webp,.svg" />
                        </div>
                        <button type="submit" class="submit-btn">Enregistrer</button>
                    </form>
                    <form method="post" class="admin-item-suppression" onsubmit="return confirm('Supprimer définitivement « <?= echapper((string)($evenement['titre'] ?? '')) ?> » ?');">
                        <input type="hidden" name="action" value="supprimer" />
                        <input type="hidden" name="index" value="<?= $index ?>" />
                        <button type="submit" class="admin-btn-supprimer">Supprimer</button>
                    </form>
                </div>
                <?php endforeach; ?>
            </div>
            <?php endif; ?>

            <h2>Ajouter un événement</h2>
            <form method="post" class="admin-form" enctype="multipart/form-data">
                <input type="hidden" name="action" value="ajouter" />
                <div class="form-group">
                    <label for="titre">Titre de l'événement *</label>
                    <input type="text" id="titre" name="titre" required />
                </div>
                <div class="form-group">
                    <label for="image">Image *</label>
                    <input type="file" id="image" name="image" accept=".jpg,.jpeg,.png,.gif,.webp,.svg" required />
                </div>
                <div class="form-group">
                    <label for="position">Position dans le carrousel</label>
                    <input type="number" id="position" name="position" min="1" max="<?= count($evenements) + 1 ?>" value="<?= count($evenements) + 1 ?>" />
                </div>
                <button type="submit" class="submit-btn">Ajouter l'événement</button>
            </form>

            <form method="post" class="admin-deconnexion">
                <input type="hidden" name="action" value="deconnexion" />
                <button type="submit" class="admin-btn-secondaire">Se déconnecter</button>
            </form>
        <?php endif; ?>
    </main>
</body>
</html>
