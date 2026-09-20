# sync_macros.ps1 - Synchronise les macros LibreOffice avec le depot Git
# Usage :
#   .\sync_macros.ps1 -Push   # copie les macros du profil LibreOffice vers le depot
#   .\sync_macros.ps1 -Pull   # restaure les macros du depot vers le profil LibreOffice
param(
    [Parameter(Mandatory = $true, ParameterSetName = "Push")]
    [switch]$Push,
    [Parameter(Mandatory = $true, ParameterSetName = "Pull")]
    [switch]$Pull
)

$ErrorActionPreference = "Stop"

# --- Configuration ---
# Profil LibreOffice (Basic) : macros stockees dans le dossier "basic" du profil utilisateur.
$UserProfile = Join-Path $env:APPDATA "LibreOffice\4\user\basic"
$RepoDir    = "$PSScriptRoot\profil-lo"
$ExcludeDirs = @("Standard")   # bibliotheque Standard : macros par defaut, hors scope

if ($Push) {
    $source = $UserProfile
    $dest   = $RepoDir
    $action = "PUSH (profil LibreOffice -> depot)"
} else {
    $source = $RepoDir
    $dest   = $UserProfile
    $action = "PULL (depot -> profil LibreOffice)"
}

Write-Host "=== sync_macros : $action ===" -ForegroundColor Cyan
Write-Host "Source : $source"
Write-Host "Destination : $dest"
Write-Host ""

if (-not (Test-Path $source)) {
    Write-Host "ERREUR : le dossier source n'existe pas : $source" -ForegroundColor Red
    Write-Host "Verifie la configuration (profil LibreOffice / dossier du depot)."
    exit 1
}

New-Item -ItemType Directory -Force -Path $dest | Out-Null

# Copie recursive en excluant les bibliotheques hors scope
Get-ChildItem -Path $source -Directory | Where-Object { $ExcludeDirs -notcontains $_.Name } | ForEach-Object {
    $target = Join-Path $dest $_.Name
    Write-Host "Copie : $($_.Name)"
    Copy-Item -Path $_.FullName -Destination $target -Recurse -Force
}

Write-Host ""
Write-Host "Termine. Fichiers concernes :" -ForegroundColor Green
Get-ChildItem -Path $dest -Recurse -File | ForEach-Object { Write-Host "  $($_.FullName.Substring($dest.Length + 1))" }
