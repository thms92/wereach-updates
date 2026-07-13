#!/bin/bash
# ==========================================================================
#  We.Reach — Lanceur local macOS (double-clic)
#  Fait tout, tout seul : installe l'environnement la 1re fois, puis lance
#  l'appli dans ton navigateur. Utilise TON Chrome + TA connexion (ton IP),
#  donc LinkedIn ne bloque pas (contrairement au mode serveur).
# ==========================================================================
cd "$(dirname "$0")"
clear
echo "======================================"
echo "        We.Reach — démarrage"
echo "======================================"
echo ""

# 1) Python 3 présent ?
if ! command -v python3 &>/dev/null; then
  osascript -e 'display dialog "Python 3 nest pas installe.

Installe-le depuis https://www.python.org/downloads/ (bouton jaune Download),
puis double-clique a nouveau sur ce fichier." buttons {"OK"} with icon stop' >/dev/null 2>&1
  open "https://www.python.org/downloads/"
  exit 1
fi

# 2) Environnement isolé (.venv) — créé une seule fois
if [ ! -d ".venv" ]; then
  echo "Premiere installation en cours (2 a 5 minutes)..."
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate

# 3) Dépendances + navigateur Chromium (une seule fois, marqueur .setup_done)
if [ ! -f ".venv/.setup_done" ]; then
  echo "Installation des composants (patiente, c'est la seule fois)..."
  python -m pip install --upgrade pip >/dev/null 2>&1
  python -m pip install -r requirements.txt || {
    osascript -e 'display dialog "Erreur pendant linstallation des dependances." buttons {"OK"} with icon stop' >/dev/null 2>&1
    exit 1
  }
  echo "Installation du navigateur (Chromium)..."
  python -m playwright install chromium
  touch ".venv/.setup_done"
  echo "Installation terminee."
fi

# 4) Mode requis par LinkedIn : vrai Chrome VISIBLE, sans camouflage
#    (indispensable pour que les boutons d'invitation apparaissent).
export SCRAPER_HEADLESS=false
export SCRAPER_STEALTH=false

# 5) Lancement — Streamlit ouvre automatiquement le navigateur
echo ""
echo "Ouverture de We.Reach dans ton navigateur..."
echo "(Laisse cette fenetre noire ouverte pendant l'utilisation.)"
echo ""
python -m streamlit run app_advanced.py

# Si erreur au lancement
if [ $? -ne 0 ]; then
  osascript -e 'display dialog "Erreur au lancement de We.Reach. Reessaie, ou contacte Thomas." buttons {"OK"} with icon stop' >/dev/null 2>&1
fi
