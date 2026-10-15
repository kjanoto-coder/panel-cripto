import os
import json
import requests
import ccxt
import pandas as pd

# ---------------------------------------------------------
# CONFIGURACIÓN DE CREDENCIALES (Alineado con tus secretos)
# ---------------------------------------------------------
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("CHAT_ID")
MESSAGE_THREAD_ID = os.getenv("TOPIC_ID_PRE_EXPLOSION")

# URL de tu web desplegada en Netlify (Reemplaza con tu dominio real de Netlify si es necesario)
NETLIFY_BASE_URL = "https://tu-motor-pre-explosion.netlify.app"

# ---------------------------------------------------------
# 1 Y 2. ESCÁNER DE VOLUMEN Y ANOMALÍAS (BINANCE)
# ---------------------------------------------------------
print("🚀 Iniciando escaneo de Criptos Pre-Explosión...")

exchange = ccxt.binance({'enableRateLimit': True})
tickers = exchange.fetch_tickers()

candidatas_pre_explosion = []

for symbol, data in tickers.items():
    # Filtrar solo pares USDT
    if not symbol.endswith('/USDT'):
        continue
        
    price_change_24h = data['percentage'] if data['percentage'] is not None else 0
    vol_24h = data['quoteVolume'] if data['quoteVolume'] is not None else 0
    
    # Filtro 1: El precio aún no explotó (entre 0% y +5.0%) y tiene volumen mínimo
    if 0 <= price_change_24h <= 5.0 and vol_24h > 100000:
        try:
            # Obtener velas de 1 hora
            ohlcv = exchange.fetch_ohlcv(symbol, timeframe='1h', limit=24)
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            
            vol_actual_1h = df['volume'].iloc[-1]
            promedio_vol_24h = df['volume'].mean()
            
            # Filtro 2: El volumen de la última hora es al menos 2.5 veces el promedio
            if promedio_vol_24h > 0 and vol_actual_1h >= (promedio_vol_24h * 2.5):
                ratio_volumen = round(vol_actual_1h / promedio_vol_24h, 2)
                ticker_limpio = symbol.split('/')[0] # ej: "GNS" de "GNS/USDT"
                
                # Cálculo de Score preliminar
                score = round(ratio_volumen * (5.1 - price_change_24h), 2)
                
                candidatas_pre_explosion.append({
                    'symbol': symbol,
                    'ticker': ticker_limpio,
                    'price_change': round(price_change_24h, 2),
                    'ratio_volumen': ratio_volumen,
                    'score': score
                })
        except Exception as e:
            continue

# Ordenar por Score y tomar el TOP 7
top_7_candidatas = sorted(candidatas_pre_explosion, key=lambda x: x['score'], reverse=True)[:7]

# ---------------------------------------------------------
# 3. PARTE 3: CONSTRUCCIÓN DEL MENSAJE Y BOTONES EN TELEGRAM
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
        
        # URL dinámica pasando la moneda elegida como parámetro hacia Netlify
        url_dinamica = f"{NETLIFY_BASE_URL}/?coin={coin['ticker']}"
        
        # Botón para la botonera de Telegram
        inline_keyboard.append([
            {"text": f"🔍 Analizar ${coin['ticker']} en Netlify", "url": url_dinamica}
        ])

    # Enviar reporte a Telegram con botones interactivos y al tema específico
    if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
        url_api = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {
            'chat_id': TELEGRAM_CHAT_ID,
            'text': mensaje_telegram,
            'parse_mode': 'Markdown',
            'reply_markup': json.dumps({'inline_keyboard': inline_keyboard})
        }
        
        # Incluir el ID del tema (Topic ID) configurado en GitHub Secrets
        if MESSAGE_THREAD_ID:
            payload['message_thread_id'] = int(MESSAGE_THREAD_ID)
            
        res = requests.post(url_api, json=payload)
        print("✅ Reporte de Pre-Explosión enviado al tema de Telegram.")

# ---------------------------------------------------------
# 4. PARTE 4: EXPORTACIÓN DE ESTRUCTURA JSON PARA EL TRADER IA
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

# Guardar los datos procesados en un archivo JSON local que la IA podrá consultar
with open("datos_pre_explosion_ia.json", "w") as f:
    json.dump(estructura_ia, f, indent=4)

print("💾 Archivo 'datos_pre_explosion_ia.json' generado exitosamente para el Trader IA.")
