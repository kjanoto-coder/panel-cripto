import os
import json
import requests
import ccxt
import pandas as pd

# ---------------------------------------------------------
# CONFIGURACIÓN DE CREDENCIALES
# ---------------------------------------------------------
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("CHAT_ID")
MESSAGE_THREAD_ID = os.getenv("TOPIC_ID_PRE_EXPLOSION")

NETLIFY_BASE_URL = "https://tu-motor-pre-explosion.netlify.app"

# ---------------------------------------------------------
# 1 Y 2. ESCÁNER DE VOLUMEN (BINANCE SPOT GLOBAL)
# ---------------------------------------------------------
print("🚀 Iniciando escaneo de Criptos Pre-Explosión...")

# Se configura únicamente el mercado 'spot' y se desactiva 'swap/future' para evitar la API bloqueada fapi.binance.com
exchange = ccxt.binance({
    'enableRateLimit': True,
    'options': {
        'defaultType': 'spot',
        'fetchMarkets': ['spot']
    },
    'urls': {
        'api': {
            'public': 'https://data-api.binance.vision/api/v3',
            'spot': 'https://data-api.binance.vision/api/v3'
        }
    }
})

# Cargar solo mercados spot
tickers = exchange.fetch_tickers()

candidatas_pre_explosion = []

for symbol, data in tickers.items():
    # Filtrar únicamente pares USDT
    if not symbol.endswith('/USDT'):
        continue
        
    price_change_24h = data['percentage'] if data['percentage'] is not None else 0
    vol_24h = data['quoteVolume'] if data['quoteVolume'] is not None else 0
    
    # Filtro 1: Monedas con variación entre 0% y +5.0% y volumen mínimo representativo
    if 0 <= price_change_24h <= 5.0 and vol_24h > 100000:
        try:
            ohlcv = exchange.fetch_ohlcv(symbol, timeframe='1h', limit=24)
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            
            vol_actual_1h = df['volume'].iloc[-1]
            promedio_vol_24h = df['volume'].mean()
            
            # Filtro 2: El volumen de la última hora es al menos 2.5 veces el promedio de 24H
            if promedio_vol_24h > 0 and vol_actual_1h >= (promedio_vol_24h * 2.5):
                ratio_volumen = round(vol_actual_1h / promedio_vol_24h, 2)
                ticker_limpio = symbol.split('/')[0]
                
                score = round(ratio_volumen * (5.1 - price_change_24h), 2)
                
                candidatas_pre_explosion.append({
                    'symbol': symbol,
                    'ticker': ticker_limpio,
                    'price_change': round(price_change_24h, 2),
                    'ratio_volumen': ratio_volumen,
                    'score': score
                })
        except Exception:
            continue

top_7_candidatas = sorted(candidatas_pre_explosion, key=lambda x: x['score'], reverse=True)[:7]

# ---------------------------------------------------------
# 3. PARTE 3: ENVÍO A TELEGRAM
# ---------------------------------------------------------
if top_7_candidatas:
    mensaje_telegram = "🚀 **TOP 7 CRIPTOS PRE-EXPLOSIÓN (Detección Temprana)**\n\n"
    mensaje_telegram += "Monedas con acumulación silenciosa de volumen 1H que aún no se dispararon:\n\n"
    
    inline_keyboard = []
    
    for idx, coin in enumerate(top_7_candidatas, 1):
        mensaje_telegram += (
            f"**{idx}. {coin['ticker']}** | Var 24h: `{coin['price_change']}%` | "
            f"Vol 1H: `{coin['ratio_volumen']}x` | Score: `{coin['score']}`\n"
        )
        
        url_dinamica = f"{NETLIFY_BASE_URL}/?coin={coin['ticker']}"
        inline_keyboard.append([
            {"text": f"🔍 Analizar ${coin['ticker']} en Netlify", "url": url_dinamica}
        ])

    if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
        url_api = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {
            'chat_id': TELEGRAM_CHAT_ID,
            'text': mensaje_telegram,
            'parse_mode': 'Markdown',
            'reply_markup': json.dumps({'inline_keyboard': inline_keyboard})
        }
        
        if MESSAGE_THREAD_ID:
            payload['message_thread_id'] = int(MESSAGE_THREAD_ID)
            
        res = requests.post(url_api, json=payload)
        print("✅ Reporte de Pre-Explosión enviado a Telegram.")

# ---------------------------------------------------------
# 4. PARTE 4: ESTRUCTURA JSON PARA TRADER IA
# ---------------------------------------------------------
estructura_ia = {
    "timestamp": pd.Timestamp.now().isoformat(),
    "bot_origen": "Criptos Pre-Explosión",
    "top_candidatas": [
        {
            "token": item['ticker'],
            "score_acumulacion": item['score'],
            "variacion_24h": item['price_change'],
            "volumen_anomalo_1h": f"{item['ratio_volumen']}x",
            "estado_ia": "LISTO_PARA_ENTRY"
        }
        for item in top_7_candidatas
    ]
}

with open("datos_pre_explosion_ia.json", "w") as f:
    json.dump(estructura_ia, f, indent=4)

print("💾 Archivo 'datos_pre_explosion_ia.json' generado exitosamente.")
