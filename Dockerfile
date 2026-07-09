FROM python:3.11-slim

# Dépendances système : Playwright/Chromium + Xvfb (écran virtuel pour lancer
# Chrome en mode VISIBLE côté serveur, requis car LinkedIn sert une version
# dégradée aux navigateurs headless) + tzdata (heure locale).
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget curl gnupg ca-certificates tzdata \
    xvfb xauth \
    libnss3 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 \
    libxkbcommon0 libxcomposite1 libxdamage1 libxfixes3 libxrandr2 \
    libgbm1 libasound2 libpango-1.0-0 libcairo2 libx11-xcb1 libxcb1 \
    libxext6 libxss1 fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Chromium (complet, capable de tourner en mode visible sous Xvfb)
RUN playwright install chromium
RUN playwright install-deps chromium

COPY . .

# Navigateur VISIBLE + pas de camouflage (indispensable pour les invitations)
# + fuseau horaire France.
ENV SCRAPER_HEADLESS=false \
    SCRAPER_STEALTH=false \
    TZ=Europe/Paris \
    PYTHONUNBUFFERED=1

EXPOSE 8501

HEALTHCHECK --interval=30s --timeout=10s --start-period=40s \
  CMD curl -f http://localhost:8501/_stcore/health || exit 1

# Lancer Streamlit SOUS un écran virtuel Xvfb (Chrome s'ouvre "visible" dedans).
CMD xvfb-run -a --server-args="-screen 0 1920x1080x24" \
    streamlit run app_advanced.py \
    --server.port=8501 --server.address=0.0.0.0 \
    --server.headless=true --server.enableCORS=false \
    --browser.gatherUsageStats=false
