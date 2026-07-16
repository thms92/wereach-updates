#!/bin/bash
# ==========================================================================
#  publish_update.sh — publie une mise à jour à TOUS les utilisateurs.
#
#  Usage :
#     bash publish_update.sh 1.0.1 "fix: message d'explication"
#     bash publish_update.sh patch  "fix: ..."     # bump auto du dernier chiffre
#
#  Ce que ça fait :
#   1) écrit la nouvelle version dans VERSION
#   2) commit toutes tes modifs
#   3) pousse sur la branche 'main' du dépôt GitHub public
#  => chaque personne reçoit la mise à jour à son prochain lancement.
# ==========================================================================
set -e
cd "$(dirname "$0")"

BRANCH="main"

if [ -z "$1" ]; then
  echo "Usage : bash publish_update.sh <version|patch|minor|major> \"message\""
  echo "Version actuelle : $(cat VERSION 2>/dev/null || echo '?')"
  exit 1
fi

CUR=$(cat VERSION 2>/dev/null | tr -d '[:space:]')
[ -z "$CUR" ] && CUR="0.0.0"

case "$1" in
  patch|minor|major)
    IFS='.' read -r MA MI PA <<< "$CUR"
    MA=${MA:-0}; MI=${MI:-0}; PA=${PA:-0}
    case "$1" in
      patch) PA=$((PA+1)) ;;
      minor) MI=$((MI+1)); PA=0 ;;
      major) MA=$((MA+1)); MI=0; PA=0 ;;
    esac
    NEW="$MA.$MI.$PA"
    ;;
  *)
    NEW="$1"
    ;;
esac

MSG="${2:-release: v$NEW}"

echo "Version : $CUR  ->  $NEW"
printf '%s\n' "$NEW" > VERSION

git add -A
if git diff --cached --quiet; then
  echo "Aucune modification à publier."
  exit 0
fi
git commit -q -m "$MSG (v$NEW)"

echo "Publication sur GitHub (branche $BRANCH)…"
git push -q origin "HEAD:$BRANCH"

echo ""
echo "✅ Publié : v$NEW"
echo "   Tout le monde l'aura au prochain lancement de We.Reach."
