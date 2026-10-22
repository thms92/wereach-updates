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
GH_REPO="wereach-updates"
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
       setup_vps.sh create_package.sh make_package.sh make_package_windows.sh publish_update.sh \
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

# macOS marque tout fichier venu d'internet (com.apple.quarantine) et exige
# une autorisation manuelle au premier lancement. Quand l'utilisateur clique
# "Ouvrir quand meme", le systeme enregistre une derogation mais LAISSE la
# marque. Une mise a jour de macOS peut revoquer cette derogation : la marque
# est toujours la, et le blocage revient sans raison apparente. On efface la
# marque de tout le dossier des le premier demarrage reussi — il n'y a alors
# plus rien a evaluer, jamais.
xattr -cr "\$PWD" 2>/dev/null || true

APP="\$PWD/app"
GH_OWNER="$GH_OWNER"
GH_REPO="$GH_REPO"
GH_BRANCH="$GH_BRANCH"

echo "======================================"
echo "        We.Reach — démarrage"
echo "======================================"

# Double-cliquer le lanceur alors que l'outil tourne deja remplacait les
# fichiers sous le processus en cours : il rechargeait le nouveau
# app_advanced.py avec l'ancien config encore en memoire, d'ou un ImportError
# incomprehensible. Et la seconde instance, le port 8501 etant pris, se
# rabattait ailleurs — l'utilisateur continuait donc de voir l'ancienne
# version dans son navigateur.
arreter_instance_existante() {
  local motif="\${1:-streamlit run app_advanced.py}" i
  pgrep -f "\$motif" >/dev/null 2>&1 || return 0
  echo "We.Reach etait deja ouvert — fermeture de l'ancienne fenetre."
  pkill -f "\$motif" 2>/dev/null
  for i in 1 2 3 4 5 6 7 8 9 10; do
    pgrep -f "\$motif" >/dev/null 2>&1 || return 0
    sleep 0.5
  done
  pkill -9 -f "\$motif" 2>/dev/null
  sleep 1
  return 0
}

arreter_instance_existante

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
==========================================================
  We.Reach - Installation (Mac)
  5 minutes, UNE SEULE FOIS. Suis les etapes DANS L'ORDRE.
==========================================================

ETAPE 1 - Sortir le dossier du zip
----------------------------------
Si un ancien dossier "We.Reach" est deja dans Telechargements, mets-le
d'abord a la corbeille (sinon le nouveau s'appellera "We.Reach 2").
Double-clic sur le zip -> un dossier "We.Reach" apparait.
LAISSE-LE DANS TELECHARGEMENTS (ne le deplace pas pour l'instant).


ETAPE 2 - Autoriser We.Reach (une seule fois, 1 minute, sans Terminal)
----------------------------------------------------------------------
macOS bloque tout fichier venu d'internet qui ne vient pas de l'App
Store. La premiere fois, il faut l'autoriser :

  a. Ouvre le dossier We.Reach et double-clic sur
        1 - Lancer We.Reach.command
     -> une alerte "Apple n'a pas pu verifier..." apparait.
     Clique "Termine".  (JAMAIS "Placer dans la corbeille".)

  b. Ouvre  Reglages Systeme  (pomme en haut a gauche > Reglages
     Systeme), puis  Confidentialite et securite  dans la colonne de
     gauche.

  c. Descends tout en bas de la page. Tu vois :
        "1 - Lancer We.Reach.command" a ete bloque...
     Clique  "Ouvrir quand meme" , puis saisis le mot de passe de ta
     session Mac.

  d. Double-clic a nouveau sur "1 - Lancer We.Reach.command"
     -> clique "Ouvrir". C'est parti (ETAPE 3).


ETAPE 3 - Laisser faire (2 a 5 min, automatique)
------------------------------------------------
Une fenetre noire s'ouvre et installe TOUT toute seule : Python si
besoin (macOS peut redemander le mot de passe de ta session, c'est
normal), les composants et le navigateur. Ne ferme rien.
We.Reach s'ouvre ensuite dans ton navigateur.

  >> Garde la fenetre noire OUVERTE pendant que tu utilises l'outil
     (tu peux la reduire dans le Dock). <<


SI TU NE TROUVES PAS "Ouvrir quand meme" (secours, 1 ligne)
----------------------------------------------------------
  1. Cmd + Espace, tape  Terminal  puis Entree.
  2. Copie cette ligne en entier, colle-la (Cmd + V), puis Entree :

        xattr -cr ~/Downloads/We.Reach

  3. Rien ne s'affiche = reussi. Double-clic sur le lanceur (ETAPE 3).


==========================================================
ENSUITE - TOUT EST AUTOMATIQUE
==========================================================
- Au quotidien : double-clic sur "1 - Lancer We.Reach.command".
  L'outil s'ouvre dans un onglet de ton navigateur, que tu peux garder
  ouvert toute la journee (favori : http://localhost:8501).
- Si tu fermes la fenetre noire ou redemarres le Mac : relance le meme
  fichier.
- Mises a jour : automatiques a chaque lancement. Tu ne recevras JAMAIS
  de nouveau zip, et tu n'auras JAMAIS a refaire l'ETAPE 2.
- Ta version s'affiche en bas de la barre de gauche ("We.Reach X.Y.Z").
- Au premier lancement, We.Reach te demande ton prenom et ton nom. A
  chaque ouverture, il signale a Thomas ton nom, ta version et l'heure :
  rien d'autre (ni contacts, ni recherches, ni session LinkedIn).
- Session LinkedIn : l'outil t'explique comment la recuperer (page
  Recherche). Elle est personnelle : ne la partage jamais.

UN SOUCI ?
----------
- En cas d'erreur, une fenetre propose d'envoyer un rapport a Thomas, et
  un fichier diagnostic-wereach.txt est depose sur ton Bureau.
- Sinon, envoie une photo de la fenetre noire a Thomas.

(Le dossier "app" contient le programme : n'y touche pas.)
==========================================================
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
