<#
.SYNOPSIS
  Prépare, en local, ce qu'il faut envoyer sur le serveur pour déployer une application Hakili Lab.

.DESCRIPTION
  1. Compile le frontend (npm run build) du projet indiqué.
  2. Crée deploy\out\<App>-backend.tar.gz : le dossier backend\ (sans venv, .env, caches, journaux,
     tests) + le frontend compilé, rangé dans frontend_dist\ (servi par le backend, voir main.py).
  3. Avec -AvecSecrets : crée aussi deploy\out\<App>.container.env à partir de backend\.env du projet
     (clé Anthropic, DATABASE_URL, VECTOR_TABLE_NAME, modèle) + APP_ENV=production et un JWT_SECRET
     neuf. Aucune valeur secrète n'est affichée. À n'utiliser que pour le PREMIER déploiement :
     changer le JWT_SECRET déconnecte tous les élèves.

  Le dossier deploy\out\ est ignoré par git. Supprimez le fichier .container.env une fois envoyé.

.EXAMPLE
  # Chimie (depuis le dossier chatbot-chimie-burkina)
  .\deploy\preparer_archive.ps1 -App chatchimie -AvecSecrets

.EXAMPLE
  # Physique (même script, autre projet)
  .\deploy\preparer_archive.ps1 -App chatphysique -Projet ..\chatbot-physique-burkina -AvecSecrets
#>
param(
  [Parameter(Mandatory = $true)][ValidatePattern('^[a-z0-9_-]+$')][string]$App,
  [string]$Projet = (Join-Path $PSScriptRoot '..'),
  [switch]$AvecSecrets
)
$ErrorActionPreference = 'Stop'

$Projet = (Resolve-Path $Projet).Path
$backend = Join-Path $Projet 'backend'
$frontend = Join-Path $Projet 'frontend'
$out = Join-Path $PSScriptRoot 'out'
foreach ($p in @($backend, $frontend, (Join-Path $backend 'Dockerfile'))) {
  if (-not (Test-Path $p)) { throw "Introuvable : $p (le paramètre -Projet pointe-t-il vers la racine d'une application ?)" }
}
New-Item -ItemType Directory -Force $out | Out-Null
if (Test-Path (Join-Path $backend 'frontend_dist')) {
  throw "Un ancien build est présent dans $backend\frontend_dist : supprimez ce dossier (il entrerait en conflit avec le frontend compilé)."
}

Write-Host "== Compilation du frontend de $Projet"
Push-Location $frontend
# npm/vite écrivent des avertissements sur stderr (taille des fichiers JS...) : sous PowerShell 5.1,
# en mode Stop, ils seraient pris pour des erreurs. Seul le code de retour fait foi ici.
$ErrorActionPreference = 'Continue'
try {
  if (-not (Test-Path 'node_modules')) { npm install --no-audit --no-fund 2>&1 | ForEach-Object { "$_" } | Out-Host }
  npm run build 2>&1 | ForEach-Object { "$_" } | Out-Host
  if ($LASTEXITCODE -ne 0) { throw "npm run build a échoué" }
} finally { Pop-Location; $ErrorActionPreference = 'Stop' }
if (-not (Test-Path (Join-Path $frontend 'dist\index.html'))) { throw "frontend\dist\index.html absent après la compilation" }

$archive = Join-Path $out "$App-backend.tar.gz"
Write-Host "== Création de $archive"
# Le frontend compilé doit arriver dans frontend_dist\ (servi par le backend, voir main.py). Le tar
# de Windows ne sait pas renommer à la volée (pas d'option -s) : copie dans un dossier temporaire
# portant ce nom, plutôt que dans le dossier backend du projet.
$tar = Join-Path $env:SystemRoot 'System32\tar.exe'
$staging = Join-Path ([System.IO.Path]::GetTempPath()) "hakili-deploy-$App"
if (Test-Path $staging) { Remove-Item -Recurse -Force $staging }
New-Item -ItemType Directory -Force $staging | Out-Null
Copy-Item -Recurse (Join-Path $frontend 'dist') (Join-Path $staging 'frontend_dist')
try {
  & $tar -czf $archive `
    --exclude 'venv' --exclude '.env' --exclude 'hf_cache' --exclude '__pycache__' --exclude '*.pyc' `
    --exclude '*.log' --exclude 'tests' --exclude '.pytest_cache' `
    --exclude '.jwt_secret' --exclude 'app.db' `
    -C $backend . `
    -C $staging frontend_dist
  if ($LASTEXITCODE -ne 0) { throw "tar a échoué" }
} finally { Remove-Item -Recurse -Force $staging }

$listing = & $tar -tzf $archive
foreach ($attendu in @('./Dockerfile', './main.py', 'frontend_dist/index.html')) {
  if ($listing -notcontains $attendu) { throw "Archive incomplète : $attendu absent" }
}
$interdits = $listing | Where-Object { $_ -match '(^|/)(\.env|\.jwt_secret|app\.db)$' -or $_ -match '(^|/)(venv|hf_cache)/' }
if ($interdits) { throw "L'archive contient des fichiers qui ne doivent pas partir : $($interdits -join ', ')" }
$pdfs = ($listing | Where-Object { $_ -match '^\./data/documents/.+\.pdf$' }).Count
$taille = [Math]::Round((Get-Item $archive).Length / 1MB, 1)
Write-Host "[OK] Archive : $taille Mo, $($listing.Count) entrées, $pdfs PDF de cours"

if ($AvecSecrets) {
  $envLocal = Join-Path $backend '.env'
  if (-not (Test-Path $envLocal)) { throw "Introuvable : $envLocal" }
  $vals = @{}
  foreach ($ligne in Get-Content $envLocal -Encoding UTF8) {
    if ($ligne -match '^\s*([A-Z_]+)\s*=\s*(.*?)\s*$') { $vals[$Matches[1]] = $Matches[2] }
  }
  $cle = $vals['ANTHROPIC_API_KEY']
  if (-not $cle) { $cle = $env:ANTHROPIC_API_KEY; $sourceCle = 'variable Windows ANTHROPIC_API_KEY' } else { $sourceCle = 'backend\.env' }
  if (-not $cle) { throw "Aucune clé Anthropic : ni dans $envLocal, ni dans la variable Windows ANTHROPIC_API_KEY" }
  if (-not $vals['DATABASE_URL']) { throw "DATABASE_URL vide dans $envLocal" }
  if (-not $vals['VECTOR_TABLE_NAME']) { throw "VECTOR_TABLE_NAME vide dans $envLocal" }
  $octets = New-Object byte[] 48
  [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($octets)
  $jwt = [Convert]::ToBase64String($octets).TrimEnd('=').Replace('+', '-').Replace('/', '_')
  $modele = if ($vals['ANTHROPIC_MODEL']) { $vals['ANTHROPIC_MODEL'] } else { 'claude-sonnet-5' }
  $contenu = @(
    "# Généré par preparer_archive.ps1 le $(Get-Date -Format 'yyyy-MM-dd HH:mm') pour $App — NE JAMAIS COMMITER"
    "ANTHROPIC_API_KEY=$cle"
    "ANTHROPIC_MODEL=$modele"
    "DATABASE_URL=$($vals['DATABASE_URL'])"
    "VECTOR_TABLE_NAME=$($vals['VECTOR_TABLE_NAME'])"
    "APP_ENV=production"
    "JWT_SECRET=$jwt"
    "JWT_EXPIRE_DAYS=7"
    "HISTORY_MAX_TURNS=6"
  )
  $fichierEnv = Join-Path $out "$App.container.env"
  # LF + UTF-8 sans BOM : lu par docker --env-file sur Linux.
  [System.IO.File]::WriteAllText($fichierEnv, (($contenu -join "`n") + "`n"), (New-Object System.Text.UTF8Encoding $false))
  Write-Host "[OK] $fichierEnv créé (clé Anthropic prise dans : $sourceCle ; table : $($vals['VECTOR_TABLE_NAME'])). Valeurs non affichées."
  Write-Host "     Envoyez-le sur le serveur sous le nom container.env, puis supprimez-le d'ici."
}
