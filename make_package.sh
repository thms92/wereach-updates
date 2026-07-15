#!/bin/bash
# ==========================================================================
#  Génère un package propre We.Reach.zip pour distribution aux utilisateurs.
#  Résultat (ce que voit la personne en ouvrant le dossier) :
#     We.Reach/
#       0 - LIRE-MOI.txt
#       1 - Lancer We.Reach.command      <- elle double-clique ça
#       app/                              <- tout le code, rangé, hors de vue
# ==========================================================================
set -e
cd "$(dirname "$0")"

STAGE="/tmp/wereach_pkg"
OUT="${1:-$HOME/Downloads/We.Reach.zip}"

rm -rf "$STAGE"
mkdir -p "$STAGE/We.Reach/app"

echo "1) Copie du code source (propre) dans app/…"
git archive HEAD | tar -x -C "$STAGE/We.Reach/app"

echo "2) Ménage : on retire du sous-dossier tout ce qui ne sert pas à l'utilisateur…"
cd "$STAGE/We.Reach/app"
# Fichiers/dossiers inutiles pour un utilisateur final (dev, docker, doublons)
rm -rf tests docs
rm -f  "Diagnostic Cookie LinkedIn.command" Enrichir_*.command \
       start.command stop.command start.bat stop.bat *.bat \
       start_advanced.sh start_app.sh launch_app.sh install.sh install_mac.sh \
       setup_vps.sh create_package.sh make_package.sh \
       Dockerfile docker-compose.yml deploy_oracle.sh \
       README.md requirements-dev.txt "LIRE-MOI (installation).txt" \
       Base_enrichie_Prospects_2026.csv.progress.json 2>/dev/null || true
cd - >/dev/null

echo "3) Lanceur clair au niveau supérieur…"
# On réutilise le vrai lanceur (dans app/) mais on ajuste le 'cd' pour qu'il
# pointe vers app/ ; puis on le place au top-level avec un nom explicite.
sed 's#cd "$(dirname "$0")"#cd "$(dirname "$0")/app"#' \
    "$STAGE/We.Reach/app/LinkedIn Scraper Pro Advanced.command" \
    > "$STAGE/We.Reach/1 - Lancer We.Reach.command"
chmod +x "$STAGE/We.Reach/1 - Lancer We.Reach.command"
# On enlève le lanceur d'origine du sous-dossier (évite le doublon visible)
rm -f "$STAGE/We.Reach/app/LinkedIn Scraper Pro Advanced.command"

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
# -x pour exclure les .DS_Store éventuels
zip -r -q -X "$OUT" "We.Reach" -x "*.DS_Store"
cd - >/dev/null

echo ""
echo "✅ Package prêt : $OUT"
echo "   Contenu visible par l'utilisateur :"
unzip -l "$OUT" | awk '{print $4}' | grep -E "^We.Reach/[^/]*$" | sed 's#^#   #'
