#!/bin/bash
# ==========================================================================
#  Génère un package propre We.Reach.zip pour distribution aux utilisateurs.
#
#  Résultat (ce que voit la personne en ouvrant le dossier) :
#     We.Reach/
#       0 - LIRE-MOI.txt
#       1 - Lancer We.Reach.command      <- elle double-clique ça
#       app/                              <- tout le code, rangé, hors de vue
#
#  Le lanceur top-level est un "bootstrap" : à chaque ouverture il vérifie
#  sur GitHub s'il existe une version plus récente, la télécharge et remplace
#  le code de app/ (en préservant .venv, data/, config/, logs/), puis lance
#  l'app. => quand tu publies (bash publish_update.sh), tout le monde est à
#  jour au prochain lancement, sans rien renvoyer.
# ==========================================================================
set -e
cd "$(dirname "$0")"

# --- Source des mises à jour (dépôt GitHub public) ------------------------
GH_OWNER="thms92"
GH_REPO="wereach"
GH_BRANCH="main"
# --------------------------------------------------------------------------

STAGE="/tmp/wereach_pkg"
OUT="${1:-$HOME/Downloads/We.Reach.zip}"

rm -rf "$STAGE"
mkdir -p "$STAGE/We.Reach/app"

echo "1) Copie du code source (propre) dans app/…"
git archive HEAD | tar -x -C "$STAGE/We.Reach/app"

echo "2) Ménage : on retire du sous-dossier tout ce qui ne sert pas à l'utilisateur…"
cd "$STAGE/We.Reach/app"
rm -rf tests docs
rm -f  "Diagnostic Cookie LinkedIn.command" Enrichir_*.command \
       start.command stop.command start.bat stop.bat *.bat \
       start_advanced.sh start_app.sh launch_app.sh install.sh install_mac.sh \
       setup_vps.sh create_package.sh make_package.sh publish_update.sh \
       Dockerfile docker-compose.yml deploy_oracle.sh \
       README.md requirements-dev.txt "LIRE-MOI (installation).txt" \
       Base_enrichie_Prospects_2026.csv.progress.json 2>/dev/null || true
cd - >/dev/null

echo "3) Lanceur-bootstrap (auto-update) au niveau supérieur…"
# NB : le vrai runner reste dans app/ (LinkedIn Scraper Pro Advanced.command)
#      et EST mis à jour par le tarball. Le bootstrap ci-dessous, lui, est
#      stable : il ne fait que "vérifier maj -> remplacer app/ -> lancer".
BOOT="$STAGE/We.Reach/1 - Lancer We.Reach.command"
cat > "$BOOT" <<BOOTSTRAP
#!/bin/bash
# We.Reach — lanceur (bootstrap auto-update). Ne pas modifier.
cd "\$(dirname "\$0")"
APP="\$PWD/app"
GH_OWNER="$GH_OWNER"
GH_REPO="$GH_REPO"
GH_BRANCH="$GH_BRANCH"

echo "======================================"
echo "        We.Reach — démarrage"
echo "======================================"

# --- Vérification de mise à jour (silencieuse si hors-ligne) --------------
REMOTE=\$(curl -fsSL --max-time 8 "https://raw.githubusercontent.com/\$GH_OWNER/\$GH_REPO/\$GH_BRANCH/VERSION" 2>/dev/null | tr -d '[:space:]')
LOCAL=\$(tr -d '[:space:]' < "\$APP/VERSION" 2>/dev/null)
if [ -n "\$REMOTE" ] && [ "\$REMOTE" != "\$LOCAL" ]; then
  echo "Mise à jour disponible (\$LOCAL -> \$REMOTE), installation…"
  TMP=\$(mktemp -d)
  if curl -fsSL --max-time 90 "https://github.com/\$GH_OWNER/\$GH_REPO/archive/refs/heads/\$GH_BRANCH.tar.gz" -o "\$TMP/u.tgz" 2>/dev/null \\
     && tar xzf "\$TMP/u.tgz" -C "\$TMP" 2>/dev/null; then
    SRC=\$(find "\$TMP" -maxdepth 1 -type d -name "\$GH_REPO-*" | head -1)
    if [ -n "\$SRC" ] && [ -f "\$SRC/VERSION" ]; then
      OLD_REQ=\$(md5 -q "\$APP/requirements.txt" 2>/dev/null)
      rsync -a --delete \\
        --exclude '.venv' --exclude 'data' --exclude 'config' \\
        --exclude 'logs' --exclude '.werite_test' \\
        "\$SRC"/ "\$APP"/ 2>/dev/null
      NEW_REQ=\$(md5 -q "\$APP/requirements.txt" 2>/dev/null)
      # dépendances changées -> forcer la réinstallation au prochain setup
      [ "\$OLD_REQ" != "\$NEW_REQ" ] && rm -f "\$APP/.venv/.setup_done"
      echo "Mise à jour installée (v\$REMOTE)."
    else
      echo "(mise à jour illisible, on garde la version actuelle)"
    fi
  else
    echo "(mise à jour indisponible, on garde la version actuelle)"
  fi
  rm -rf "\$TMP"
fi

# --- Lancement du runner (dans app/) --------------------------------------
exec "\$APP/LinkedIn Scraper Pro Advanced.command"
BOOTSTRAP
chmod +x "$BOOT"

echo "4) LIRE-MOI au niveau supérieur…"
cat > "$STAGE/We.Reach/0 - LIRE-MOI.txt" <<'TXT'
========================================================
  We.Reach — Installation (Mac)
========================================================

Tu n'as RIEN à installer à la main. Deux clics et c'est parti :

1) CLIC DROIT sur  " 1 - Lancer We.Reach.command "  ->  Ouvrir  ->  Ouvrir
   (macOS le demande une seule fois car le fichier vient d'internet — normal.)

2) La 1re fois, une fenêtre noire installe TOUT automatiquement (2 à 5 min) :
   - Python si besoin (macOS te demandera ton mot de passe de session — normal),
   - les composants + le navigateur.
   Laisse faire, ne ferme rien. Ton navigateur s'ouvre ensuite sur We.Reach.

   >> Garde la fenêtre noire OUVERTE pendant que tu utilises l'outil. <<

--------------------------------------------------------
MISES À JOUR — automatiques
- À chaque ouverture, We.Reach vérifie s'il existe une version plus récente
  et l'installe tout seul (quelques secondes). Tu n'as rien à refaire.
- La version installée est affichée en bas de la barre de gauche (We.Reach vX.Y.Z).

--------------------------------------------------------
UTILISER
- Récupère ton cookie LinkedIn (li_at) : voir l'encadré "Comment récupérer
  mon cookie" dans l'app (page Recherche). Colle-le -> Enregistrer.
- Limite volontaire : 20 invitations / jour (protège ton compte).
- Pour relancer un autre jour : re-double-clique le même fichier (instantané).
- Un souci ? Envoie une capture de la fenêtre noire à Thomas.

(Le dossier "app" contient le programme — n'y touche pas.)
========================================================
TXT

echo "5) Création du zip…"
rm -f "$OUT"
cd "$STAGE"
zip -r -q -X "$OUT" "We.Reach" -x "*.DS_Store"
cd - >/dev/null

echo ""
if [ "$GH_OWNER" = "__GH_OWNER__" ]; then
  echo "⚠️  GH_OWNER/GH_REPO non configurés dans make_package.sh — auto-update inactif."
fi
echo "✅ Package prêt : $OUT"
echo "   Contenu visible par l'utilisateur :"
unzip -l "$OUT" | awk '{print $4}' | grep -E "^We.Reach/[^/]*$" | sed 's#^#   #'
