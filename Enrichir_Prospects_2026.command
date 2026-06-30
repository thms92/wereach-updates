#!/bin/bash

# Enrichissement Prospects 2026 - Data & IA
# Double-cliquez pour lancer l'enrichissement LinkedIn

# Aller dans le dossier du script (nécessaire pour trouver linkedin_cookies.json)
cd "$(dirname "$0")"

INPUT="$HOME/Downloads/Base de donnée Prospect 2026 - Data & IA(Feuil1).csv"
OUTPUT="$(dirname "$0")/Base_enrichie_Prospects_2026.csv"

# Vérifier que le fichier source existe
if [ ! -f "$INPUT" ]; then
    osascript -e 'display dialog "Fichier source introuvable :\n'"$INPUT"'\n\nVérifiez que le fichier est bien dans votre dossier Téléchargements." buttons {"OK"} with icon stop'
    exit 1
fi

osascript -e 'display notification "Démarrage de l'\''enrichissement LinkedIn..." with title "Enrichissement Prospects 2026"'

echo "========================================"
echo "  Enrichissement Prospects 2026"
echo "========================================"
echo "  Source  : $INPUT"
echo "  Sortie  : $OUTPUT"
echo "========================================"
echo ""

# Vérifier les dépendances
export PATH="$HOME/.local/bin:$PATH"
for module in playwright pandas; do
    if ! python3 -c "import $module" &> /dev/null 2>&1; then
        echo "Installation de $module..."
        python3 -m pip install --break-system-packages $module
    fi
done

# Vérifier que Playwright Chromium est installé
if ! python3 -m playwright install --dry-run chromium &> /dev/null 2>&1; then
    echo "Installation de Chromium pour Playwright..."
    python3 -m playwright install chromium
fi

# Lancer l'enrichissement
python3 enrich_linkedin.py \
    --input "$INPUT" \
    --output "$OUTPUT"

STATUS=$?

if [ $STATUS -eq 0 ]; then
    osascript -e 'display notification "Enrichissement terminé ! Fichier sauvegardé dans le dossier scrapping." with title "✅ Enrichissement Prospects 2026"'
    echo ""
    echo "✅ Fichier enrichi sauvegardé : $OUTPUT"
    # Ouvrir le dossier dans le Finder
    open -R "$OUTPUT"
else
    osascript -e 'display dialog "Une erreur est survenue pendant l'\''enrichissement.\nConsultez le terminal pour les détails." buttons {"OK"} with icon stop'
fi
