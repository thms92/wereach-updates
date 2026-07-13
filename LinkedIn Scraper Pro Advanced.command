#!/bin/bash
# ==========================================================================
#  We.Reach — Lanceur local macOS (double-clic)
#  Installe tout seul la 1re fois, puis lance l'appli dans le navigateur.
#  Utilise TON Chrome + TA connexion (ton IP) → LinkedIn ne bloque pas.
# ==========================================================================
cd "$(dirname "$0")"
clear
echo "======================================"
echo "        We.Reach — démarrage"
echo "======================================"
echo ""

fail() {  # affiche une vraie fenêtre d'erreur + garde le terminal ouvert
  osascript -e "display dialog \"$1\" buttons {\"OK\"} with icon stop" >/dev/null 2>&1
  echo ""; echo "❌ $1"; echo ""
  read -r -p "Appuie sur Entree pour fermer..."
  exit 1
}

# 0) Dossier accessible en écriture ? (sinon = lancé depuis le zip sans extraire)
if ! touch ".werite_test" 2>/dev/null; then
  fail "Extrais d'abord le dossier We.Reach (ex. sur le Bureau), puis double-clique le lanceur depuis ce dossier."
fi
rm -f ".werite_test"

# 1) Python 3 présent et assez récent (>= 3.9) ?
if ! command -v python3 &>/dev/null; then
  open "https://www.python.org/downloads/" 2>/dev/null
  fail "Python 3 n'est pas installe. Une page web vient de s'ouvrir : installe Python (bouton jaune), puis relance ce fichier."
fi
if ! python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3,9) else 1)' 2>/dev/null; then
  open "https://www.python.org/downloads/" 2>/dev/null
  fail "Ta version de Python est trop ancienne. Installe la derniere depuis python.org, puis relance."
fi

# 2) Environnement isolé (.venv) — créé une seule fois
if [ ! -d ".venv" ]; then
  echo "Premiere installation (2 a 5 minutes)..."
  python3 -m venv .venv || fail "Impossible de creer l'environnement Python (.venv). Reinstalle Python depuis python.org."
fi
# shellcheck disable=SC1091
source .venv/bin/activate || fail "Environnement Python illisible. Supprime le dossier .venv et relance."

# 3) Dépendances + navigateur Chromium (une seule fois, marqueur .setup_done)
if [ ! -f ".venv/.setup_done" ]; then
  echo "Installation des composants (patiente, c'est la seule fois)..."
  python -m pip install --upgrade pip >/dev/null 2>&1
  python -m pip install -r requirements.txt || fail "Erreur pendant l'installation des dependances (verifie ta connexion internet, puis relance)."
  echo "Installation du navigateur (Chromium)..."
  python -m playwright install chromium || fail "Erreur pendant l'installation du navigateur (connexion internet ?), puis relance."
  touch ".venv/.setup_done"
  echo "Installation terminee."
fi

# 4) Mode requis par LinkedIn : vrai Chrome VISIBLE, sans camouflage
export SCRAPER_HEADLESS=false
export SCRAPER_STEALTH=false

# 5) Lancement — ouvre le navigateur tout seul
echo ""
echo "Ouverture de We.Reach dans ton navigateur..."
echo "(Laisse cette fenetre noire ouverte pendant l'utilisation.)"
echo ""
( sleep 4; open "http://localhost:8501" >/dev/null 2>&1 ) &
python -m streamlit run app_advanced.py --server.headless=false || \
  fail "Erreur au lancement de We.Reach. Envoie une capture de cette fenetre a Thomas."
