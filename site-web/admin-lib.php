<?php
// admin-lib.php — bibliothèque partagée des pages d'administration
// (authentification, lecture/écriture JSON, gestion des images).

declare(strict_types=1);

// --------------------------------------------------------------------------
// Configuration locale
//
// Le mot de passe des pages d'administration se trouve dans
// `admin-mot-de-passe.php`, A COTER DE CE FICHIER, SUR LE SERVEUR SEULEMENT.
// Ce fichier est exclu par le .gitignore racine et ne doit jamais être commité.
//
// Modele du fichier attendu :
//   <?php
//   return 'votre mot de passe';
//
// Tant que ce fichier est absent, les pages d'administration refusent
// l'accès avec un message explicite.
// --------------------------------------------------------------------------

define('DOSSIER_RACINE', __DIR__);
define('FICHIER_MOT_DE_PASSE', DOSSIER_RACINE . '/admin-mot-de-passe.php');
define('TAILLE_IMAGE_MAX', 5 * 1024 * 1024); // 5 Mo
define('EXTENSIONS_AUTORISEES', ['jpg', 'jpeg', 'png', 'gif', 'webp', 'svg']);

// --------------------------------------------------------------------------
// Authentification
// --------------------------------------------------------------------------

function mot_de_passe_admin(): ?string
{
    if (!is_file(FICHIER_MOT_DE_PASSE)) {
        return null;
    }
    $mot_de_passe = (require FICHIER_MOT_DE_PASSE);
    return is_string($mot_de_passe) && $mot_de_passe !== '' ? $mot_de_passe : null;
}

function tenter_connexion(string $mot_de_passe_saisi): bool
{
    $mot_de_passe = mot_de_passe_admin();
    if ($mot_de_passe !== null && hash_equals($mot_de_passe, $mot_de_passe_saisi)) {
        $_SESSION['admin_authentifie'] = true;
        return true;
    }
    return false;
}

function deconnexion_admin(): void
{
    $_SESSION = [];
    if (ini_get('session.use_cookies')) {
        $params = session_get_cookie_params();
        setcookie(session_name(), '', time() - 42000, $params['path'], $params['domain'], $params['secure'], $params['httponly']);
    }
    session_destroy();
}

// --------------------------------------------------------------------------
// Lecture / écriture des fichiers JSON
// --------------------------------------------------------------------------

function lire_json(string $chemin): array
{
    if (!is_file($chemin)) {
        return [];
    }
    $contenu = file_get_contents($chemin);
    $donnees = json_decode($contenu ?: '[]', true);
    return is_array($donnees) ? $donnees : [];
}

function ecrire_json(string $chemin, array $donnees): bool
{
    $json = json_encode($donnees, JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE);
    if ($json === false) {
        return false;
    }
    $temporaire = $chemin . '.tmp';
    if (file_put_contents($temporaire, $json) === false) {
        return false;
    }
    return rename($temporaire, $chemin);
}

// --------------------------------------------------------------------------
// Gestion des images
// --------------------------------------------------------------------------

function nettoyer_nom_fichier(string $nom): string
{
    $nom = mb_strtolower(basename($nom));
    $nom = preg_replace('/[^a-z0-9._-]+/', '-', $nom);
    $nom = trim($nom, '-.');
    return $nom !== '' ? $nom : 'image';
}

function extension_fichier(string $nom): string
{
    return mb_strtolower(pathinfo($nom, PATHINFO_EXTENSION));
}

/**
 * Valide et déplace une image uploadée ($_FILES[...]).
 * Retourne ['succes' => true, 'fichier' => nom_final] ou ['succes' => false, 'erreur' => message].
 * Aucun déplacement si $nom_prefere fourni et libre (sinon suffixe numérique).
 */
function enregistrer_image(array $fichier, string $dossier_images, ?string $nom_prefere = null): array
{
    if (($fichier['error'] ?? UPLOAD_ERR_NO_FILE) === UPLOAD_ERR_NO_FILE) {
        return ['succes' => false, 'erreur' => 'Aucune image fournie.'];
    }
    if ($fichier['error'] !== UPLOAD_ERR_OK) {
        return ['succes' => false, 'erreur' => "Erreur lors de l'envoi de l'image (code " . $fichier['error'] . ")."];
    }
    if ($fichier['size'] > TAILLE_IMAGE_MAX) {
        return ['succes' => false, 'erreur' => "L'image dépasse la taille maximale de 5 Mo."];
    }

    $extension = extension_fichier($fichier['name']);
    if (!in_array($extension, EXTENSIONS_AUTORISEES, true)) {
        return ['succes' => false, 'erreur' => "Extension non autorisée. Formats acceptés : " . implode(', ', EXTENSIONS_AUTORISEES) . '.'];
    }

    if (!is_dir($dossier_images)) {
        if (!mkdir($dossier_images, 0755, true)) {
            return ['succes' => false, 'erreur' => "Impossible de créer le dossier d'images."];
        }
    }

    $base = $nom_prefere !== null ? nettoyer_nom_fichier($nom_prefere) : nettoyer_nom_fichier($fichier['name']);
    $final = $base . '.' . $extension;
    $compteur = 1;
    while (is_file($dossier_images . '/' . $final)) {
        $final = $base . '-' . $compteur . '.' . $extension;
        $compteur++;
    }

    if (!move_uploaded_file($fichier['tmp_name'], $dossier_images . '/' . $final)) {
        return ['succes' => false, 'erreur' => "Impossible d'enregistrer l'image sur le serveur."];
    }
    return ['succes' => true, 'fichier' => $final];
}

function supprimer_image(string $dossier_images, string $nom_fichier): void
{
    $nom_fichier = basename($nom_fichier);
    if ($nom_fichier !== '' && is_file($dossier_images . '/' . $nom_fichier)) {
        unlink($dossier_images . '/' . $nom_fichier);
    }
}

// --------------------------------------------------------------------------
// Aides d'affichage
// --------------------------------------------------------------------------

function echapper(?string $texte): string
{
    return htmlspecialchars((string)$texte, ENT_QUOTES, 'UTF-8');
}
