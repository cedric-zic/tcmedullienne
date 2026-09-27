<?php
// admin-sponsors.php — gestion des sponsors du site (ajout, modification,
// suppression) via un simple navigateur. Protégé par mot de passe
// (voir admin-lib.php pour la configuration).

declare(strict_types=1);

require_once __DIR__ . '/admin-lib.php';

define('FICHIER_SPONSORS', DOSSIER_RACINE . '/sponsors.json');
define('DOSSIER_IMAGES_SPONSORS', DOSSIER_RACINE . '/images/sponsors');
define('URL_IMAGES_SPONSORS', 'images/sponsors');

session_start();
$mot_de_passe_attendu = mot_de_passe_admin();

if ($mot_de_passe_attendu === null) {
    http_response_code(500);
    exit('Configuration manquante : créez le fichier admin-mot-de-passe.php à côté de cette page (voir site-web/README.md).');
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
        $sponsors = lire_json(FICHIER_SPONSORS);
        $sponsors = array_values($sponsors);

        if ($action === 'deconnexion') {
            deconnexion_admin();
        } elseif ($action === 'ajouter') {
            $nom = trim((string)($_POST['nom'] ?? ''));
            $url = trim((string)($_POST['url'] ?? ''));
            if ($nom === '') {
                $message_erreur = 'Le nom du sponsor est obligatoire.';
            } else {
                $image = $_FILES['image'] ?? null;
                $nouveau = null;
                if ($image && ($image['error'] ?? UPLOAD_ERR_NO_FILE) !== UPLOAD_ERR_NO_FILE) {
                    $resultat = enregistrer_image($image, DOSSIER_IMAGES_SPONSORS);
                    if (!$resultat['succes']) {
                        $message_erreur = $resultat['erreur'];
                    } else {
                        $nouveau = ['nom' => $nom, 'url' => $url, 'image' => URL_IMAGES_SPONSORS . '/' . $resultat['fichier']];
                    }
                }
                if ($nouveau !== null) {
                    $position = (int)($_POST['position'] ?? 0);
                    $position = max(1, min($position, count($sponsors) + 1));
                    array_splice($sponsors, $position - 1, 0, [$nouveau]);
                    if (ecrire_json(FICHIER_SPONSORS, $sponsors)) {
                        $message_succes = sprintf('Sponsor « %s » ajouté (position %d).', $nom, $position);
                    } else {
                        $message_erreur = "Impossible d'écrire sponsors.json (vérifiez les droits sur le serveur).";
                    }
                }
            }
        } elseif ($action === 'modifier') {
            $index = (int)($_POST['index'] ?? -1);
            $nom = trim((string)($_POST['nom'] ?? ''));
            if ($nom === '') {
                $message_erreur = 'Le nom du sponsor est obligatoire.';
            } elseif (!isset($sponsors[$index])) {
                $message_erreur = 'Sponsor introuvable.';
            } else {
                $sponsors[$index]['nom'] = $nom;
                $sponsors[$index]['url'] = trim((string)($_POST['url'] ?? ''));
                $image = $_FILES['image'] ?? null;
                if ($image && ($image['error'] ?? UPLOAD_ERR_NO_FILE) !== UPLOAD_ERR_NO_FILE) {
                    $resultat = enregistrer_image($image, DOSSIER_IMAGES_SPONSORS);
                    if (!$resultat['succes']) {
                        $message_erreur = $resultat['erreur'];
                    } else {
                        if (!empty($sponsors[$index]['image']) && str_starts_with((string)$sponsors[$index]['image'], URL_IMAGES_SPONSORS . '/')) {
                            supprimer_image(DOSSIER_IMAGES_SPONSORS, basename((string)$sponsors[$index]['image']));
                        }
                        $sponsors[$index]['image'] = URL_IMAGES_SPONSORS . '/' . $resultat['fichier'];
                    }
                }
                if ($message_erreur === '') {
                    $position = (int)($_POST['position'] ?? $index + 1);
                    $position = max(1, min($position, count($sponsors)));
                    if ($position - 1 !== $index) {
                        $deplace = array_splice($sponsors, $index, 1);
                        array_splice($sponsors, $position - 1, 0, $deplace);
                    }
                    if (ecrire_json(FICHIER_SPONSORS, $sponsors)) {
                        $message_succes = sprintf('Sponsor « %s » mis à jour.', $nom);
                    } else {
                        $message_erreur = "Impossible d'écrire sponsors.json (vérifiez les droits sur le serveur).";
                    }
                }
            }
        } elseif ($action === 'supprimer') {
            $index = (int)($_POST['index'] ?? -1);
            if (!isset($sponsors[$index])) {
                $message_erreur = 'Sponsor introuvable.';
            } else {
                $nom = (string)($sponsors[$index]['nom'] ?? '');
                if (!empty($sponsors[$index]['image']) && str_starts_with((string)$sponsors[$index]['image'], URL_IMAGES_SPONSORS . '/')) {
                    supprimer_image(DOSSIER_IMAGES_SPONSORS, basename((string)$sponsors[$index]['image']));
                }
                array_splice($sponsors, $index, 1);
                if (ecrire_json(FICHIER_SPONSORS, array_values($sponsors))) {
                    $message_succes = sprintf('Sponsor « %s » supprimé.', $nom);
                } else {
                    $message_erreur = "Impossible d'écrire sponsors.json (vérifiez les droits sur le serveur).";
                }
            }
        }
    }
}

$est_authentifie = ($_SESSION['admin_authentifie'] ?? false) === true;
$sponsors = $est_authentifie ? array_values(lire_json(FICHIER_SPONSORS)) : [];
?>
<!doctype html>
<html lang="fr">
<head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Admin - Sponsors</title>
    <link href="https://fonts.googleapis.com/css2?family=Montserrat:wght@400;600;700&family=Open+Sans:wght@400;600&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="styles.css" />
</head>
<body>
    <main class="admin-main">
        <h1 class="section-title">Gestion des sponsors</h1>

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

            <h2>Sponsors actuels</h2>
            <?php if (count($sponsors) === 0): ?>
                <p class="admin-vide">Aucun sponsor pour le moment. Ajoutez le premier ci-dessous.</p>
            <?php else: ?>
            <div class="admin-liste">
                <?php foreach ($sponsors as $index => $sponsor): ?>
                <div class="admin-item">
                    <img class="admin-miniature" src="<?= echapper((string)($sponsor['image'] ?? '')) ?>" alt="<?= echapper((string)($sponsor['nom'] ?? '')) ?>" />
                    <form method="post" class="admin-item-form" enctype="multipart/form-data">
                        <input type="hidden" name="action" value="modifier" />
                        <input type="hidden" name="index" value="<?= $index ?>" />
                        <div class="form-group">
                            <label>Nom</label>
                            <input type="text" name="nom" value="<?= echapper((string)($sponsor['nom'] ?? '')) ?>" required />
                        </div>
                        <div class="form-group">
                            <label>Site web</label>
                            <input type="url" name="url" value="<?= echapper((string)($sponsor['url'] ?? '')) ?>" placeholder="https://..." />
                        </div>
                        <div class="form-group">
                            <label>Position</label>
                            <input type="number" name="position" min="1" max="<?= count($sponsors) ?>" value="<?= $index + 1 ?>" />
                        </div>
                        <div class="form-group">
                            <label>Remplacer l'image (optionnel)</label>
                            <input type="file" name="image" accept=".jpg,.jpeg,.png,.gif,.webp,.svg" />
                        </div>
                        <button type="submit" class="submit-btn">Enregistrer</button>
                    </form>
                    <form method="post" class="admin-item-suppression" onsubmit="return confirm('Supprimer définitivement « <?= echapper((string)($sponsor['nom'] ?? '')) ?> » ?');">
                        <input type="hidden" name="action" value="supprimer" />
                        <input type="hidden" name="index" value="<?= $index ?>" />
                        <button type="submit" class="admin-btn-supprimer">Supprimer</button>
                    </form>
                </div>
                <?php endforeach; ?>
            </div>
            <?php endif; ?>

            <h2>Ajouter un sponsor</h2>
            <form method="post" class="admin-form" enctype="multipart/form-data">
                <input type="hidden" name="action" value="ajouter" />
                <div class="form-group">
                    <label for="nom">Nom du sponsor *</label>
                    <input type="text" id="nom" name="nom" required />
                </div>
                <div class="form-group">
                    <label for="url">Site web du sponsor</label>
                    <input type="url" id="url" name="url" placeholder="https://..." />
                </div>
                <div class="form-group">
                    <label for="image">Image (logo) *</label>
                    <input type="file" id="image" name="image" accept=".jpg,.jpeg,.png,.gif,.webp,.svg" required />
                </div>
                <div class="form-group">
                    <label for="position">Position dans la liste</label>
                    <input type="number" id="position" name="position" min="1" max="<?= count($sponsors) + 1 ?>" value="<?= count($sponsors) + 1 ?>" />
                </div>
                <button type="submit" class="submit-btn">Ajouter le sponsor</button>
            </form>

            <form method="post" class="admin-deconnexion">
                <input type="hidden" name="action" value="deconnexion" />
                <button type="submit" class="admin-btn-secondaire">Se déconnecter</button>
            </form>
        <?php endif; ?>
    </main>
</body>
</html>
