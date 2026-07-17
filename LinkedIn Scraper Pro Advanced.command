#!/bin/bash
# ==========================================================================
#  We.Reach — Lanceur local macOS (double-clic)
#  Installe tout seul (Python si besoin + composants + navigateur) la 1re fois,
#  puis lance l'appli dans le navigateur. Utilise TON Chrome + TA connexion
#  (ton IP) → LinkedIn ne bloque pas.
# ==========================================================================
cd "$(dirname "$0")"
clear
echo "======================================"
echo "        We.Reach — démarrage"
echo "======================================"
echo ""

fail() {  # fenêtre d'erreur + garde le terminal ouvert
  osascript -e "display dialog \"$1\" buttons {\"OK\"} with icon stop" >/dev/null 2>&1
  echo ""; echo "❌ $1"; echo ""
  read -r -p "Appuie sur Entree pour fermer..."
  exit 1
}

# 0) Dossier accessible en écriture ? (sinon = lancé sans extraire le zip)
if ! touch ".werite_test" 2>/dev/null; then
  fail "Extrais d'abord le dossier We.Reach (ex. sur le Bureau), puis double-clique le lanceur depuis ce dossier."
fi
rm -f ".werite_test"

# 1) Python 3 (>= 3.9) — sinon INSTALLATION AUTOMATIQUE
PYVER="3.12.7"
PKG_URL="https://www.python.org/ftp/python/${PYVER}/python-${PYVER}-macos11.pkg"
python_ok() { command -v python3 &>/dev/null && python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3,9) else 1)' 2>/dev/null; }

if ! python_ok; then
  echo "Python n'est pas installe — installation automatique."
  echo "(macOS va te demander le mot de passe de ta session, c'est normal.)"
  osascript -e 'display notification "Installation de Python en cours..." with title "We.Reach"' >/dev/null 2>&1
  curl -fsSL -o /tmp/wereach-python.pkg "$PKG_URL" \
    || { open "https://www.python.org/downloads/" 2>/dev/null; fail "Telechargement de Python impossible (connexion internet ?). Installe-le depuis la page ouverte, puis relance."; }
  osascript -e 'do shell script "installer -pkg /tmp/wereach-python.pkg -target /" with administrator privileges' \
    || { open "https://www.python.org/downloads/" 2>/dev/null; fail "Installation automatique de Python echouee (droits admin ?). Installe-le depuis la page ouverte, puis relance."; }
  rm -f /tmp/wereach-python.pkg
  export PATH="/usr/local/bin:/Library/Frameworks/Python.framework/Versions/Current/bin:$PATH"
  hash -r
  python_ok || fail "Python installe mais introuvable. Redemarre le Mac et relance, ou contacte Thomas."
  echo "Python installe avec succes."
fi

# 2) Environnement isolé (.venv) — créé une seule fois
if [ ! -d ".venv" ]; then
  echo "Premiere installation (2 a 5 minutes)..."
  python3 -m venv .venv || fail "Impossible de creer l'environnement Python (.venv)."
fi
# shellcheck disable=SC1091
source .venv/bin/activate || fail "Environnement Python illisible. Supprime le dossier .venv et relance."

# 3) Dépendances + navigateur Chromium (une seule fois, marqueur .setup_done)
if [ ! -f ".venv/.setup_done" ]; then
  echo "Installation des composants (patiente, c'est la seule fois)..."
  python -m pip install --upgrade pip >/dev/null 2>&1
  python -m pip install -r requirements.txt || fail "Erreur d'installation des dependances (connexion internet ?), puis relance."
  echo "Installation du navigateur (Chromium)..."
  python -m playwright install chromium || fail "Erreur d'installation du navigateur (connexion internet ?), puis relance."
  touch ".venv/.setup_done"
  echo "Installation terminee."
fi

# 4) Mode requis par LinkedIn : vrai Chrome VISIBLE, sans camouflage
export SCRAPER_HEADLESS=false
export SCRAPER_STEALTH=false

# 5) Streamlit demande un email au tout premier lancement et ATTEND une saisie
#    (le serveur ne demarre jamais tant qu'on ne repond pas). On desactive ce
#    message une fois pour toutes sur ce Mac.
mkdir -p "$HOME/.streamlit"
if [ ! -f "$HOME/.streamlit/credentials.toml" ]; then
  printf '[general]\nemail = ""\n' > "$HOME/.streamlit/credentials.toml"
fi

# 6) Lancement — c'est nous qui ouvrons le navigateur (headless=true evite a la
#    fois le message de bienvenue et un second onglet ouvert par Streamlit).
echo ""
echo "Ouverture de We.Reach dans ton navigateur..."
echo "(Laisse cette fenetre noire ouverte pendant l'utilisation.)"
echo ""
( sleep 4; open "http://localhost:8501" >/dev/null 2>&1 ) &
python -m streamlit run app_advanced.py --server.headless=true \
  || fail "Erreur au lancement de We.Reach. Envoie une capture de cette fenetre a Thomas."
