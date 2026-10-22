#!/bin/bash
# ==========================================================================
#  Génère We.Reach-Windows.zip pour un collègue sous Windows.
#
#  Résultat (ce que voit la personne en ouvrant le dossier) :
#     We.Reach/
#       0 - LIRE-MOI.txt
#       1 - Lancer We.Reach.bat           <- elle double-clique ça
#       app/                              <- tout le code, rangé, hors de vue
#
#  Le .bat ne fait qu'appeler app\windows\demarrer.ps1, qui gère la mise à
#  jour, l'installation et le lancement. Ce script étant dans app\, il est
#  mis à jour avec l'outil : le lanceur Windows se corrige par simple
#  publication, sans renvoyer de zip.
# ==========================================================================
set -e
cd "$(dirname "$0")"

STAGE="/tmp/wereach_pkg_windows"
OUT="${1:-$HOME/Downloads/We.Reach-Windows.zip}"

rm -rf "$STAGE"
mkdir -p "$STAGE/We.Reach/app"

echo "1) Copie du code source (propre) dans app/…"
git archive HEAD | tar -x -C "$STAGE/We.Reach/app"

echo "2) Ménage : on retire tout ce qui ne sert pas à l'utilisateur…"
cd "$STAGE/We.Reach/app"
rm -rf tests docs
rm -f  *.command *.bat *.sh Dockerfile docker-compose.yml \
       README.md requirements-dev.txt "LIRE-MOI (installation).txt" \
       Base_enrichie_Prospects_2026.csv.progress.json 2>/dev/null || true
cd - >/dev/null

# Les fichiers lus par cmd.exe et le Bloc-notes veulent des fins de ligne
# Windows (CRLF) : un .bat en LF peut mal interpréter ses lignes.
crlf() { python3 -c 'import sys; p=sys.argv[1]; d=open(p,"rb").read().replace(b"\r\n",b"\n"); open(p,"wb").write(d.replace(b"\n",b"\r\n"))' "$1"; }

echo "3) Lanceur…"
BAT="$STAGE/We.Reach/1 - Lancer We.Reach.bat"
cat > "$BAT" <<'BAT'
@echo off
REM We.Reach - lanceur Windows. Ne pas modifier : tout se passe dans
REM app\windows\demarrer.ps1, mis a jour automatiquement avec l'outil.
cd /d "%~dp0"
title We.Reach
if not exist "app\windows\demarrer.ps1" (
  echo Le dossier "app" est introuvable.
  echo Extrais d'abord le zip : clic droit sur We.Reach-Windows.zip, puis "Extraire tout".
  pause
  exit /b 1
)
powershell -NoProfile -ExecutionPolicy Bypass -File "app\windows\demarrer.ps1"
if errorlevel 1 pause
BAT
crlf "$BAT"
crlf "$STAGE/We.Reach/app/windows/demarrer.ps1"

echo "4) LIRE-MOI…"
LIRE="$STAGE/We.Reach/0 - LIRE-MOI.txt"
cat > "$LIRE" <<'TXT'
==========================================================
  We.Reach - Installation (Windows)
  ~5 minutes, UNE SEULE FOIS. Rien a installer a la main.
==========================================================

----------------------------------------------------------
ETAPE 1 - Extraire le dossier du zip
----------------------------------------------------------
Clic droit sur We.Reach-Windows.zip > "Extraire tout..." > Extraire.
Tu obtiens un dossier "We.Reach". Mets-le ou tu veux (ex. Documents).

  >> Ne lance PAS le fichier depuis l'interieur du zip sans l'extraire :
     ca ne fonctionnera pas. <<

----------------------------------------------------------
ETAPE 2 - Lancer (et autoriser une seule fois)
----------------------------------------------------------
Double-clic sur "1 - Lancer We.Reach.bat".

Windows peut afficher un ecran bleu "Windows a protege votre ordinateur".
C'est normal pour tout programme telecharge qui ne vient pas du Store :
  1. Clique sur "Informations complementaires"
  2. Puis sur "Executer quand meme"

  >> A faire UNE SEULE FOIS. Plus jamais ensuite, mises a jour comprises. <<

----------------------------------------------------------
ETAPE 3 - Laisser faire (2 a 5 min, automatique)
----------------------------------------------------------
Une fenetre noire installe TOUT toute seule :
  - Python si tu ne l'as pas (pour ton compte seulement, sans mot de
    passe administrateur),
  - les composants + le navigateur.
Laisse faire, ne ferme rien.
Ton navigateur s'ouvre ensuite sur We.Reach (adresse : http://localhost:8501).

  >> Garde la fenetre noire OUVERTE pendant que tu utilises l'outil
     (tu peux la reduire dans la barre des taches). <<

----------------------------------------------------------
MISES A JOUR - automatiques, rien a faire
----------------------------------------------------------
A chaque ouverture, We.Reach se met a jour tout seul si une nouvelle
version existe (quelques secondes).
- Tu ne recevras JAMAIS de nouveau zip a reinstaller.
- Ta version est affichee en bas de la barre de gauche : "We.Reach X.Y.Z".
- Au premier lancement, We.Reach te demande ton prenom et ton nom. A chaque
  ouverture, il signale a Thomas ton nom, ta version et l'heure : rien
  d'autre (ni contacts, ni recherches, ni session LinkedIn).

----------------------------------------------------------
AU QUOTIDIEN
----------------------------------------------------------
- Double-clic sur "1 - Lancer We.Reach.bat" : l'outil s'ouvre dans un
  onglet de ton navigateur. Tu peux garder cet onglet ouvert toute la
  journee (ajoute http://localhost:8501 a tes favoris).
- Si tu fermes la fenetre noire, ou apres un redemarrage du PC, relance
  simplement "1 - Lancer We.Reach.bat".
- Session LinkedIn : l'outil t'explique comment la recuperer (page
  Recherche). Ne la partage jamais.

----------------------------------------------------------
UN SOUCI ?
----------------------------------------------------------
- En cas d'erreur, une fenetre propose d'envoyer un rapport a Thomas, et
  un fichier diagnostic-wereach.txt est depose sur ton Bureau.
- Sinon, envoie une photo de la fenetre noire a Thomas.

(Le dossier "app" contient le programme - n'y touche pas.)
==========================================================
TXT
crlf "$LIRE"

echo "5) Création du zip…"
rm -f "$OUT"
cd "$STAGE"
zip -r -q -X "$OUT" "We.Reach" -x "*.DS_Store"
cd - >/dev/null

echo "✅ Package Windows prêt : $OUT"
unzip -l "$OUT" | awk '{print $4}' | grep -E "^We.Reach/[^/]*$" | sed 's#^#   #'
