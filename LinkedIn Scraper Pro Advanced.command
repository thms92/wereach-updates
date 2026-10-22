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

# Adresse qui recoit les rapports. Doit rester identique a EMAIL_SUPPORT dans
# config.py — un test le verifie. Elle est dupliquee ici parce que le lanceur
# ne peut pas lire du Python quand c'est justement Python qui manque.
EMAIL_SUPPORT="thomas.laudet@wefiit.com"

# Encodage d'URL en shell pur, pour la meme raison. LC_ALL=C fait travailler
# octet par octet : les accents ressortent correctement en UTF-8 percent-encode.
urlencode() {
  local LC_ALL=C s="$1" i c
  for (( i=0; i<${#s}; i++ )); do
    c="${s:i:1}"
    case "$c" in
      [a-zA-Z0-9.~_-]) printf '%s' "$c" ;;
      # & 0xFF : sans ce masque, les octets hauts (accents) sortent avec
      # l'extension de signe, soit %FFFFFFFFFFFFFFC3 au lieu de %C3.
      *) printf '%%%02X' "$(( $(printf '%d' "'$c") & 0xFF ))" ;;
    esac
  done
}

diagnostic() {
  echo "We.Reach - rapport de probleme"
  echo ""
  echo "Version      : $(cat VERSION 2>/dev/null || echo inconnue)"
  echo "macOS        : $(sw_vers -productVersion 2>/dev/null || echo inconnu)"
  echo "Mac          : $(sysctl -n hw.model 2>/dev/null || echo inconnu)"
  echo "Python       : $("$HOME/Library/Application Support/We.Reach/python/bin/python3" --version 2>&1 || python3 --version 2>&1 || echo introuvable)"
  echo "Dossier      : $PWD"
  if command -v venv_ok >/dev/null 2>&1 && [ -n "${VENV:-}" ]; then
    echo "Environnement: $(venv_ok "$VENV" && echo sain || echo "absent ou casse")"
  fi
  echo "Date         : $(date '+%Y-%m-%d %H:%M')"
  echo ""
  echo "Probleme signale :"
  echo "$1"
  echo ""
  echo "Dernieres lignes du journal :"
  tail -n 12 scraper.log 2>/dev/null || echo "(journal introuvable)"
}

fail() {  # fenetre d'erreur, rapport pre-rempli, et garde le terminal ouvert
  local msg="$1" diag reponse
  diag="$(diagnostic "$msg")"
  printf '%s\n' "$diag" > "$HOME/Desktop/diagnostic-wereach.txt" 2>/dev/null

  reponse=$(osascript -e "display dialog \"$msg

Veux-tu envoyer un rapport ? Un mail s'ouvrira, deja redige : tu n'auras qu'a cliquer sur Envoyer.\" buttons {\"Non\", \"Envoyer un rapport\"} default button \"Envoyer un rapport\" with icon stop" 2>/dev/null)

  case "$reponse" in
    *"Envoyer un rapport"*)
      open "mailto:$EMAIL_SUPPORT?subject=$(urlencode "We.Reach - probleme au lancement")&body=$(urlencode "$diag")" 2>/dev/null
      ;;
  esac

  echo ""; echo "❌ $msg"; echo ""
  echo "Un diagnostic a ete enregistre sur ton Bureau : diagnostic-wereach.txt"
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

# L'environnement et Python vivent HORS du dossier de l'application (voir
# l'etape 2 pour la raison : iCloud).
SUPPORT="$HOME/Library/Application Support/We.Reach"
VENV="$SUPPORT/venv"
mkdir -p "$SUPPORT" 2>/dev/null

# 1) Python — version AUTONOME, rangee dans le dossier de We.Reach.
# L'installeur officiel (.pkg) exige le mot de passe d'un ADMINISTRATEUR : sur
# un Mac gere par l'entreprise, ou si la fenetre est fermee, l'installation
# echouait (cas reel, 2026-10-22). La version autonome (python-build-standalone,
# 15 Mo) se decompresse simplement : ni mot de passe, ni droits, rien dans le
# systeme. Elle ne sert qu'a creer l'environnement de l'outil (etape 2).
# 3.10 est le vrai plancher : utils/user_context.py et utils/app_auth.py
# annotent en `str | None`, syntaxe qui lève une TypeError à l'import sous 3.9.
PYVER="3.12.7"
PYBUILD="20241016"
installer_python() {
  local arch tmp
  PY="$SUPPORT/python/bin/python3"
  [ -x "$PY" ] && "$PY" -c 'import sys' >/dev/null 2>&1 && return 0
  case "$(uname -m)" in
    arm64) arch="aarch64" ;;
    *)     arch="x86_64" ;;
  esac
  echo "Installation de Python (15 Mo, sans mot de passe)..."
  tmp="$(mktemp -d)"
  curl -fsSL -o "$tmp/python.tgz" \
    "https://github.com/astral-sh/python-build-standalone/releases/download/${PYBUILD}/cpython-${PYVER}+${PYBUILD}-${arch}-apple-darwin-install_only.tar.gz" \
    || { rm -rf "$tmp"; fail "Telechargement de Python impossible (connexion internet ?). Relance le lanceur."; }
  rm -rf "$SUPPORT/python"
  tar xzf "$tmp/python.tgz" -C "$SUPPORT" || { rm -rf "$tmp"; fail "Python telecharge mais illisible. Relance le lanceur."; }
  rm -rf "$tmp"
  xattr -cr "$SUPPORT/python" 2>/dev/null || true
  "$PY" -c 'import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)' \
    || fail "Python installe mais inutilisable. Contacte Thomas."
  echo "Python installe."
}

# Double-cliquer le lanceur alors que l'outil tourne deja remplacait les
# fichiers sous le processus en cours : il rechargeait le nouveau
# app_advanced.py avec l'ancien config encore en memoire, d'ou un ImportError
# incomprehensible. Et la seconde instance, le port 8501 etant pris, se
# rabattait ailleurs — l'utilisateur continuait donc de voir l'ancienne
# version dans son navigateur.
arreter_instance_existante() {
  local motif="${1:-streamlit run app_advanced.py}" i
  pgrep -f "$motif" >/dev/null 2>&1 || return 0
  echo "We.Reach etait deja ouvert — fermeture de l'ancienne fenetre."
  pkill -f "$motif" 2>/dev/null
  for i in 1 2 3 4 5 6 7 8 9 10; do
    pgrep -f "$motif" >/dev/null 2>&1 || return 0
    sleep 0.5
  done
  pkill -9 -f "$motif" 2>/dev/null
  sleep 1
  return 0
}

arreter_instance_existante

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

if ! venv_ok "$VENV"; then
  if [ -d "$VENV" ]; then
    echo "Environnement Python inutilisable (frequent apres une mise a jour de macOS)."
    echo "Reconstruction automatique, patiente 2 a 3 minutes..."
    rm -rf "$VENV"   # emporte .setup_done : les dependances se reinstallent
  else
    echo "Premiere installation (2 a 5 minutes)..."
  fi
  installer_python
  "$PY" -m venv "$VENV" || fail "Impossible de creer l'environnement Python."
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
