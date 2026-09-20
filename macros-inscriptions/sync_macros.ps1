# sync_macros.ps1 - Synchronise les macros Python LibreOffice avec le depot Git
# Le depot est la source de verite : on edite le fichier ICI, puis on deploie avec -Pull.
# Usage :
#   .\sync_macros.ps1 -Pull   # deploie macros\macros_inscriptions.py vers le profil LibreOffice
#   .\sync_macros.ps1 -Push   # (rare) recupere le fichier du profil LibreOffice vers le depot
param(
    [Parameter(Mandatory = $true, ParameterSetName = "Push")]
    [switch]$Push,
    [Parameter(Mandatory = $true, ParameterSetName = "Pull")]
    [switch]$Pull
)

$ErrorActionPreference = "Stop"

# --- Configuration ---
# Macros Python LibreOffice (niveau utilisateur) :
# %APPDATA%\LibreOffice\4\user\Scripts\python\  (un fichier .py par module)
$UserProfile = Join-Path $env:APPDATA "LibreOffice\4\user\Scripts\python"
$RepoDir     = "$PSScriptRoot\macros"

# Fichier de macros gere par ce depot.
$MacroFile  = "macros_inscriptions.py"

if ($Push) {
    $source = Join-Path $UserProfile $MacroFile
    $dest   = Join-Path $RepoDir $MacroFile
    $action = "PUSH (profil LibreOffice -> depot)"
} else {
    $source = Join-Path $RepoDir $MacroFile
    $dest   = Join-Path $UserProfile $MacroFile
    $action = "PULL (depot -> profil LibreOffice)"
}

Write-Host "=== sync_macros : $action ===" -ForegroundColor Cyan
Write-Host "Source      : $source"
Write-Host "Destination : $dest"
Write-Host ""

if (-not (Test-Path $source)) {
    Write-Host "ERREUR : le fichier source n'existe pas : $source" -ForegroundColor Red
    if ($Push) {
        Write-Host "Verifie le chemin du profil LibreOffice et le nom du fichier de macros"
        Write-Host "dans sync_macros.ps1 (`$UserProfile` / `$MacroFile`)."
    } else {
        Write-Host "Verifie que le depot contient bien macros\$MacroFile."
    }
    exit 1
}

New-Item -ItemType Directory -Force -Path (Split-Path $dest -Parent) | Out-Null

# Sauvegarde de secours avant un PULL (ecrasement du profil)
if ($Pull -and (Test-Path $dest)) {
    $backup = "$dest.bak"
    Copy-Item -Path $dest -Destination $backup -Force
    Write-Host "Sauvegarde de l'existant : $backup"
}

Copy-Item -Path $source -Destination $dest -Force
Write-Host ""
Write-Host "Termine : $dest" -ForegroundColor Green

# Apres un PULL : detecter d'anciens fichiers de macros qui coexisteraient
# dans le profil (sinon les macros apparaissent en double dans LibreOffice).
if ($Pull) {
    $autres = Get-ChildItem -Path $UserProfile -Filter *.py -File |
        Where-Object { $_.Name -ne $MacroFile }
    if ($autres) {
        Write-Host ""
        Write-Host "ATTENTION : d'autres fichiers de macros existent dans le profil :" -ForegroundColor Yellow
        foreach ($f in $autres) {
            Write-Host "  - $($_.FullName)"
            Write-Host "      Supprime-le s'il s'agit d'une ancienne version (ex. macros_libreoffice_python.py),"
            Write-Host "      sinon ses macros apparaitront en double dans LibreOffice."
        }
    }
    Write-Host ""
    Write-Host "Redemarre LibreOffice pour que les macros soient prises en compte."
}
