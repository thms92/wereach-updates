#!/bin/bash

# Enrichissement Excel Profils - Fonction & Société depuis LinkedIn
# Double-cliquez pour lancer l'enrichissement

# Aller dans le dossier du script
cd "$(dirname "$0")"

echo "========================================"
echo "  Enrichissement Excel Profils LinkedIn"
echo "========================================"
echo ""

# Vérifier les dépendances Python
export PATH="$HOME/.local/bin:$PATH"

for module in playwright pandas openpyxl; do
    if ! python3 -c "import $module" &> /dev/null 2>&1; then
        echo "📦 Installation de $module..."
        python3 -m pip install --break-system-packages $module
    fi
done

# Vérifier que Playwright Chromium est installé
if ! python3 -m playwright install --dry-run chromium &> /dev/null 2>&1; then
    echo "🌐 Installation de Chromium pour Playwright..."
    python3 -m playwright install chromium
fi

# Vérifier que linkedin_cookies.json existe
if [ ! -f "linkedin_cookies.json" ]; then
    osascript -e 'display dialog "Fichier linkedin_cookies.json introuvable.\n\nLancez dabord lapplication principale LinkedIn Scraper Pro pour vous connecter à LinkedIn, puis relancez." buttons {"OK"} with icon stop'
    exit 1
fi

# Chercher un fichier Excel dans le dossier (hors _enrichi)
EXCEL_FILE=$(python3 -c "
import glob, os
files = glob.glob('*.xlsx')
files = [f for f in files if '_enrichi' not in f.lower()]
print(files[0] if files else '')
" 2>/dev/null)

if [ -z "$EXCEL_FILE" ]; then
    osascript -e 'display dialog "Aucun fichier Excel (.xlsx) trouvé dans le dossier.\n\nCopiez votre fichier Excel (avec les prénoms, noms et URLs LinkedIn) dans ce dossier puis relancez." buttons {"OK"} with icon stop'
    exit 1
fi

OUTPUT_FILE="${EXCEL_FILE%.*}_enrichi.xlsx"

echo "  Fichier source  : $EXCEL_FILE"
echo "  Fichier sortie  : $OUTPUT_FILE"
echo ""

osascript -e "display notification \"Démarrage de l'enrichissement de $EXCEL_FILE...\" with title \"Enrichissement Excel LinkedIn\""

# Lancer l'enrichissement
python3 enrich_excel.py --input "$EXCEL_FILE" --output "$OUTPUT_FILE"

STATUS=$?

if [ $STATUS -eq 0 ]; then
    osascript -e "display notification \"Enrichissement terminé ! Fichier : $OUTPUT_FILE\" with title \"✅ Enrichissement Excel LinkedIn\""
    echo ""
    echo "✅ Fichier enrichi sauvegardé : $OUTPUT_FILE"
    # Ouvrir le dossier dans le Finder
    open -R "$OUTPUT_FILE"
else
    osascript -e 'display dialog "Une erreur est survenue pendant lenrichissement.\nConsultez le terminal pour les détails." buttons {"OK"} with icon stop'
fi
