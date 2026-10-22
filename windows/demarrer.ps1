# ==========================================================================
#  We.Reach - lanceur Windows (appele par "1 - Lancer We.Reach.bat")
#
#  Equivalent du lanceur Mac (LinkedIn Scraper Pro Advanced.command) :
#    1. met a jour le dossier app\ depuis GitHub si une version plus recente
#       existe (contacts et reglages vivent ailleurs : rien n'est perdu) ;
#    2. installe Python si besoin (pour l'utilisateur seul, sans droits admin),
#       les composants et le navigateur, une seule fois ;
#    3. lance l'outil et ouvre le navigateur.
#
#  Ce fichier vit dans app\ : il est lui-meme mis a jour avec l'outil, ce qui
#  permet de corriger le lanceur sans renvoyer de zip. PowerShell lit le
#  script en entier au demarrage : le remplacer pendant qu'il tourne est sans
#  effet sur l'execution en cours.
#
#  Texte en ASCII seulement : Windows PowerShell 5.1 lit un .ps1 sans BOM
#  dans l'encodage local, et les accents s'afficheraient mal.
# ==========================================================================
$ErrorActionPreference = "Continue"
$ProgressPreference = "SilentlyContinue"   # Invoke-WebRequest 10x plus rapide
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$APP = Split-Path -Parent $PSScriptRoot          # ...\We.Reach\app
Set-Location $APP

# Doit rester identique a EMAIL_SUPPORT dans config.py (un test le verifie).
$EMAIL_SUPPORT = "thomas.laudet@wefiit.com"
$GH = "thms92/wereach-updates"
$PYVER = "3.12.7"
$SUPPORT = Join-Path $env:LOCALAPPDATA "We.Reach"
$VENV = Join-Path $SUPPORT "venv"
$PY_VENV = Join-Path $VENV "Scripts\python.exe"
New-Item -ItemType Directory -Force -Path $SUPPORT | Out-Null

Write-Host "======================================"
Write-Host "        We.Reach - demarrage"
Write-Host "======================================"
Write-Host ""

function Diagnostic($msg) {
    $version = (Get-Content (Join-Path $APP "VERSION") -ErrorAction SilentlyContinue) -join ""
    $os = (Get-CimInstance Win32_OperatingSystem -ErrorAction SilentlyContinue).Caption
    $journal = (Get-Content (Join-Path $APP "scraper.log") -Tail 12 -ErrorAction SilentlyContinue) -join "`n"
    return @"
We.Reach - rapport de probleme

Version      : $version
Windows      : $os
Dossier      : $APP
Date         : $(Get-Date -Format "yyyy-MM-dd HH:mm")

Probleme signale :
$msg

Dernieres lignes du journal :
$journal
"@
}

function Echec($msg) {
    $diag = Diagnostic $msg
    $bureau = [Environment]::GetFolderPath("Desktop")
    Set-Content -Path (Join-Path $bureau "diagnostic-wereach.txt") -Value $diag -ErrorAction SilentlyContinue
    try {
        Add-Type -AssemblyName System.Windows.Forms
        $r = [System.Windows.Forms.MessageBox]::Show(
            "$msg`n`nVeux-tu envoyer un rapport ? Un mail s'ouvrira, deja redige : tu n'auras qu'a cliquer sur Envoyer.",
            "We.Reach", "YesNo", "Error")
        if ($r -eq "Yes") {
            $sujet = [uri]::EscapeDataString("We.Reach - probleme au lancement (Windows)")
            $corps = [uri]::EscapeDataString($diag)
            Start-Process "mailto:$EMAIL_SUPPORT`?subject=$sujet&body=$corps"
        }
    } catch {}
    Write-Host ""
    Write-Host "ERREUR : $msg" -ForegroundColor Red
    Write-Host "Un diagnostic a ete enregistre sur ton Bureau : diagnostic-wereach.txt"
    Read-Host "Appuie sur Entree pour fermer"
    exit 1
}

# 0) Dossier accessible en ecriture ? (sinon : lance depuis le zip non extrait)
try { [IO.File]::WriteAllText((Join-Path $APP ".werite_test"), "x"); Remove-Item (Join-Path $APP ".werite_test") }
catch { Echec "Extrais d'abord le dossier We.Reach (clic droit sur le zip > Extraire tout), puis double-clique le lanceur depuis ce dossier." }

# Fermer une instance deja ouverte : sinon on remplacerait les fichiers sous
# le processus en cours, et la nouvelle instance prendrait un autre port.
$anciens = Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -like "*streamlit run app_advanced.py*" }
if ($anciens) {
    Write-Host "We.Reach etait deja ouvert - fermeture de l'ancienne fenetre."
    $anciens | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
    Start-Sleep -Seconds 2
}

# Windows marque tout fichier venu d'internet et le bloque ensuite ("Windows a
# protege votre ordinateur"). On efface la marque de tout le dossier des le
# premier demarrage reussi, comme xattr -cr sur Mac.
Get-ChildItem (Split-Path -Parent $APP) -Recurse -File -ErrorAction SilentlyContinue |
    Unblock-File -ErrorAction SilentlyContinue

# 1) Mise a jour (silencieuse si hors ligne). Une seule fois par demarrage :
#    GitHub peut annoncer la nouvelle version avant que son archive soit a
#    jour (cache), et le lanceur se relancerait alors sans fin.
if ($env:WEREACH_MAJ_FAITE -eq "1") { $distante = "" } else { try {
    $distante = (Invoke-WebRequest -UseBasicParsing -TimeoutSec 8 `
        "https://raw.githubusercontent.com/$GH/main/VERSION").Content.Trim()
} catch { $distante = "" } }
$locale = ((Get-Content (Join-Path $APP "VERSION") -ErrorAction SilentlyContinue) -join "").Trim()
if ($distante -and $distante -ne $locale) {
    Write-Host "Mise a jour disponible ($locale -> $distante), installation..."
    $tmp = Join-Path $env:TEMP ("wereach-maj-" + [guid]::NewGuid())
    try {
        New-Item -ItemType Directory -Force -Path $tmp | Out-Null
        Invoke-WebRequest -UseBasicParsing -TimeoutSec 120 `
            "https://github.com/$GH/archive/refs/heads/main.zip" -OutFile (Join-Path $tmp "u.zip")
        Expand-Archive -Path (Join-Path $tmp "u.zip") -DestinationPath $tmp -Force
        $src = Get-ChildItem $tmp -Directory | Where-Object { $_.Name -like "wereach-updates-*" } | Select-Object -First 1
        if ($src -and (Test-Path (Join-Path $src.FullName "VERSION"))) {
            # /MIR : copie conforme ; les donnees vivent dans %LOCALAPPDATA%,
            # les dossiers exclus ne sont la que par prudence.
            robocopy $src.FullName $APP /MIR /XD .venv data config logs /NFL /NDL /NJH /NJS /NP | Out-Null
            Write-Host "Mise a jour installee (v$distante)."
            # Relancer le lanceur a jour : c'est lui qui doit installer la suite.
            Remove-Item $tmp -Recurse -Force -ErrorAction SilentlyContinue
            $env:WEREACH_MAJ_FAITE = "1"
            & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $APP "windows\demarrer.ps1")
            exit $LASTEXITCODE
        } else {
            Write-Host "(mise a jour illisible, on garde la version actuelle)"
        }
    } catch {
        Write-Host "(mise a jour indisponible, on garde la version actuelle)"
    }
    Remove-Item $tmp -Recurse -Force -ErrorAction SilentlyContinue
}

# 2) Python >= 3.10, sinon installation pour l'utilisateur seul
function Trouver-Python {
    $candidats = @(
        (Join-Path $env:LOCALAPPDATA "Programs\Python\Python312\python.exe"),
        (Join-Path $env:LOCALAPPDATA "Programs\Python\Python313\python.exe"),
        (Join-Path $env:LOCALAPPDATA "Programs\Python\Python311\python.exe"),
        (Join-Path $env:LOCALAPPDATA "Programs\Python\Python310\python.exe")
    )
    foreach ($c in $candidats) { if (Test-Path $c) { return $c } }
    # "python" peut n'etre que le raccourci du Microsoft Store : on verifie
    # qu'il repond vraiment avant de le retenir.
    foreach ($nom in @("py", "python")) {
        $cmd = Get-Command $nom -ErrorAction SilentlyContinue
        if ($cmd -and $cmd.Source -notlike "*WindowsApps*") {
            $args3 = if ($nom -eq "py") { @("-3", "-c") } else { @("-c") }
            $chemin = & $cmd.Source @args3 "import sys; print(sys.executable) if sys.version_info >= (3,10) else None" 2>$null
            if ($LASTEXITCODE -eq 0 -and $chemin) { return ($chemin | Select-Object -First 1).Trim() }
        }
    }
    return $null
}

$PY = Trouver-Python
if (-not $PY) {
    Write-Host "Python n'est pas installe - installation automatique (2 minutes)..."
    $exe = Join-Path $env:TEMP "wereach-python.exe"
    try {
        Invoke-WebRequest -UseBasicParsing -TimeoutSec 300 `
            "https://www.python.org/ftp/python/$PYVER/python-$PYVER-amd64.exe" -OutFile $exe
    } catch {
        Start-Process "https://www.python.org/downloads/"
        Echec "Telechargement de Python impossible (connexion internet ?). Installe-le depuis la page ouverte, puis relance."
    }
    $p = Start-Process $exe -ArgumentList "/quiet InstallAllUsers=0 PrependPath=1 Include_launcher=0 Include_test=0" -Wait -PassThru
    Remove-Item $exe -ErrorAction SilentlyContinue
    $PY = Trouver-Python
    if (-not $PY) {
        Start-Process "https://www.python.org/downloads/"
        Echec "Installation automatique de Python echouee (code $($p.ExitCode)). Installe-le depuis la page ouverte, puis relance."
    }
    Write-Host "Python installe avec succes."
}

# 3) Environnement isole, hors du dossier de l'app (OneDrive peut synchroniser
#    le Bureau et casser les milliers de fichiers d'un environnement Python).
function Venv-Ok {
    if (-not (Test-Path $PY_VENV)) { return $false }
    & $PY_VENV -c "import importlib.util as u; raise SystemExit(0 if u.find_spec('streamlit') and u.find_spec('playwright') else 1)" 2>$null
    return ($LASTEXITCODE -eq 0)
}
if (-not (Test-Path $PY_VENV)) {
    Write-Host "Premiere installation (2 a 5 minutes)..."
    & $PY -m venv $VENV
    if (-not (Test-Path $PY_VENV)) { Echec "Impossible de creer l'environnement Python." }
}

# 4) Composants et navigateur : a la premiere installation, et des que la
#    liste des composants change (empreinte de requirements.txt).
$empreinte = (Get-FileHash (Join-Path $APP "requirements.txt") -Algorithm MD5).Hash
$marqueur = Join-Path $VENV ".setup_done"
$installee = (Get-Content $marqueur -ErrorAction SilentlyContinue) -join ""
if ($installee -ne $empreinte -or -not (Venv-Ok)) {
    Write-Host "Installation des composants (patiente, c'est la seule fois)..."
    & $PY_VENV -m pip install --upgrade pip *> $null
    & $PY_VENV -m pip install -r (Join-Path $APP "requirements.txt")
    if ($LASTEXITCODE -ne 0) { Echec "Erreur d'installation des composants (connexion internet ?). Relance le lanceur." }
    Write-Host "Installation du navigateur (Chromium)..."
    & $PY_VENV -m playwright install chromium
    if ($LASTEXITCODE -ne 0) { Echec "Erreur d'installation du navigateur (connexion internet ?). Relance le lanceur." }
    Set-Content -Path $marqueur -Value $empreinte
    Write-Host "Installation terminee."
}

# 5) Mode requis par LinkedIn : vrai navigateur visible, sans camouflage
$env:SCRAPER_HEADLESS = "false"
$env:SCRAPER_STEALTH = "false"
$env:PYTHONIOENCODING = "utf-8"

# Streamlit demande un email au tout premier lancement et attend une saisie :
# on desactive cette question une fois pour toutes.
$cred = Join-Path $env:USERPROFILE ".streamlit\credentials.toml"
if (-not (Test-Path $cred)) {
    New-Item -ItemType Directory -Force -Path (Split-Path $cred) | Out-Null
    Set-Content -Path $cred -Value "[general]`nemail = `"`""
}

# 6) Lancement : c'est nous qui ouvrons le navigateur, une fois le serveur pret.
Write-Host ""
Write-Host "Ouverture de We.Reach dans ton navigateur..."
Write-Host "(Laisse cette fenetre ouverte pendant l'utilisation.)"
Write-Host ""
Start-Process powershell -WindowStyle Hidden -ArgumentList '-NoProfile -Command "Start-Sleep -Seconds 5; Start-Process http://localhost:8501"' 
& $PY_VENV -m streamlit run app_advanced.py --server.headless=true
if ($LASTEXITCODE -ne 0) { Echec "Erreur au lancement de We.Reach. Envoie une capture de cette fenetre a Thomas." }
