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

# macOS marque tout fichier venu d'internet (com.apple.quarantine) et exige
# une autorisation manuelle au premier lancement. Quand l'utilisateur clique
# "Ouvrir quand meme", le systeme enregistre une derogation mais LAISSE la
# marque. Une mise a jour de macOS peut revoquer cette derogation : la marque
# est toujours la, et le blocage revient sans raison apparente. On efface la
# marque de tout le dossier des le premier demarrage reussi — il n'y a alors
# plus rien a evaluer, jamais.
xattr -cr "$PWD/.." 2>/dev/null || true

# 1) Python 3 (>= 3.10) — sinon INSTALLATION AUTOMATIQUE
# 3.10 est le vrai plancher : utils/user_context.py et utils/app_auth.py
# annotent en `str | None`, syntaxe qui lève une TypeError à l'import sous 3.9.
PYVER="3.12.7"
PKG_URL="https://www.python.org/ftp/python/${PYVER}/python-${PYVER}-macos11.pkg"
python_ok() { command -v python3 &>/dev/null && python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)' 2>/dev/null; }

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

# 2) Environnement isolé (.venv) — reconstruit des qu'il est inutilisable
# Tester l'existence du dossier ne suffit pas : une mise a jour de macOS le
# laisse en place mais rend son interpreteur introuvable. Le lanceur sautait
# alors la reconstruction, sautait aussi l'installation (le marqueur
# .setup_done etant la), et echouait plus loin sur "python: command not
# found" — sans autre issue qu'une reinstallation complete.
# find_spec verifie l'interpreteur ET les paquets sans les importer : 0,02 s.
venv_ok() {
  local v="${1:-.venv}"
  [ -x "$v/bin/python" ] && "$v/bin/python" -c \
    'import importlib.util as u; raise SystemExit(0 if u.find_spec("streamlit") and u.find_spec("playwright") else 1)' \
    >/dev/null 2>&1
}

# L'environnement vit HORS du dossier de l'application. Pose sur le Bureau,
# ce dossier est synchronise par iCloud (reglage par defaut de macOS), qui
# decharge des fichiers pour gagner de la place et casse les milliers de liens
# du venv. Seul Telechargements y echappait, d'ou un outil qui ne demarrait
# qu'a cet endroit. Application Support n'est jamais synchronise : le dossier
# de l'app devient deplacable n'importe ou.
SUPPORT="$HOME/Library/Application Support/We.Reach"
VENV="$SUPPORT/venv"
mkdir -p "$SUPPORT" 2>/dev/null

if ! venv_ok "$VENV"; then
  if [ -d "$VENV" ]; then
    echo "Environnement Python inutilisable (frequent apres une mise a jour de macOS)."
    echo "Reconstruction automatique, patiente 2 a 3 minutes..."
    rm -rf "$VENV"   # emporte .setup_done : les dependances se reinstallent
  else
    echo "Premiere installation (2 a 5 minutes)..."
  fi
  python3 -m venv "$VENV" || fail "Impossible de creer l'environnement Python."
fi
# shellcheck disable=SC1091
source "$VENV/bin/activate" || fail "Environnement Python illisible. Contacte Thomas."


# 3) Dépendances + navigateur Chromium (une seule fois, marqueur .setup_done)
if [ ! -f "$VENV/.setup_done" ]; then
  echo "Installation des composants (patiente, c'est la seule fois)..."
  python -m pip install --upgrade pip >/dev/null 2>&1
  python -m pip install -r requirements.txt || fail "Erreur d'installation des dependances (connexion internet ?), puis relance."
  echo "Installation du navigateur (Chromium)..."
  python -m playwright install chromium || fail "Erreur d'installation du navigateur (connexion internet ?), puis relance."
  touch "$VENV/.setup_done"
  echo "Installation terminee."
fi

# Ancien environnement reste dans le dossier de l'app : plusieurs centaines de
# Mo, et c'est precisement lui qu'iCloud n'arrive pas a suivre. On ne le retire
# qu'une fois le nouveau confirme fonctionnel.
if [ -d ".venv" ] && venv_ok "$VENV"; then
  echo "Nettoyage de l'ancien environnement..."
  rm -rf ".venv"
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
