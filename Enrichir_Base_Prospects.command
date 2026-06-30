#!/bin/bash

# Enrichissement Base_enrichie_Prospects_2026
# Remplit les colonnes Fonction et Société depuis LinkedIn
# Double-cliquez pour lancer

cd "$(dirname "$0")"

INPUT="$(dirname "$0")/Base_enrichie_Prospects_2026.csv"
OUTPUT="$(dirname "$0")/Base_enrichie_Prospects_2026.csv"

echo "========================================"
echo "  Enrichissement Base Prospects 2026"
echo "========================================"
echo "  Fichier : Base_enrichie_Prospects_2026.csv"
echo "========================================"
echo ""

# Vérifier que le fichier source existe
if [ ! -f "$INPUT" ]; then
    osascript -e 'display dialog "Fichier Base_enrichie_Prospects_2026.csv introuvable dans le dossier scrapping." buttons {"OK"} with icon stop'
    exit 1
fi

# Vérifier les cookies LinkedIn
if [ ! -f "linkedin_cookies.json" ]; then
    osascript -e 'display dialog "Fichier linkedin_cookies.json introuvable.\n\nLancez dabord lapplication principale LinkedIn Scraper Pro pour vous connecter à LinkedIn." buttons {"OK"} with icon stop'
    exit 1
fi

# Vérifier les dépendances
export PATH="$HOME/.local/bin:$PATH"
for module in playwright pandas; do
    if ! python3 -c "import $module" &> /dev/null 2>&1; then
        echo "📦 Installation de $module..."
        python3 -m pip install --break-system-packages $module
    fi
done

if ! python3 -m playwright install --dry-run chromium &> /dev/null 2>&1; then
    echo "🌐 Installation de Chromium pour Playwright..."
    python3 -m playwright install chromium
fi

osascript -e 'display notification "Démarrage de lenrichissement Fonction & Société..." with title "Enrichissement Base Prospects 2026"'

# Compter les profils à enrichir avant
TOTAL=$(python3 -c "
import pandas as pd
df = pd.read_csv('Base_enrichie_Prospects_2026.csv', sep=';', encoding='utf-8-sig')
def is_empty(v):
    if pd.isna(v): return True
    return str(v).strip() in ('', '\n', '\r\n')
mask = (df['Fonction'].apply(is_empty) | df['Société - Nom'].apply(is_empty)) & df['URL LK'].notna()
print(mask.sum())
" 2>/dev/null)

echo "  📋 $TOTAL profils à enrichir"
echo ""

# Lancer l'enrichissement (mise à jour en place)
python3 enrich_linkedin.py \
    --input "$INPUT" \
    --output "$OUTPUT"

STATUS=$?

if [ $STATUS -eq 0 ]; then
    osascript -e 'display notification "Enrichissement terminé ! Base_enrichie_Prospects_2026.csv mis à jour." with title "✅ Enrichissement Base Prospects 2026"'
    echo ""
    echo "✅ Fichier mis à jour : $OUTPUT"
    open -R "$OUTPUT"
else
    osascript -e 'display dialog "Une erreur est survenue.\nConsultez le terminal pour les détails." buttons {"OK"} with icon stop'
fi
