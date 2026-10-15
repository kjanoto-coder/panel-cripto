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

# Por ahora dejamos esta variable lista; más tarde le asignamos el nuevo proyecto de Netlify
NETLIFY_BASE_URL = "https://tu-nuevo-motor-pre-explosion.netlify.app"

# ---------------------------------------------------------
# FUNCIONES AUXILIARES DE FORMATO VISUAL
# ---------------------------------------------------------
def obtener_barras_fuerza(ratio_volumen):
    """Genera 5 bloques de color según el nivel de disparo de volumen 1H"""
    if ratio_volumen >= 5.0:
        return "🟢🟢🟢🟢🟢"
    elif ratio_volumen >= 4.0:
        return "🟢🟢🟢🟢⚪"
    elif ratio_volumen >= 3.0:
        return "🟢🟢🟢⚪⚪"
    else:
        return "🟢🟢⚪⚪⚪"

def formatear_precio(precio):
    """Formatea precios pequeños o grandes limpiamente"""
    if precio < 0.01:
        return f"${precio:.6f}"
    elif precio < 1.0:
        return f"${precio:.4f}"
    else:
        return f"${precio:.2f}"

# ---------------------------------------------------------
# 1 Y 2. ESCÁNER DE VOLUMEN (BINANCE SPOT GLOBAL)
# ---------------------------------------------------------
print("🚀 Iniciando escaneo de Criptos Pre-Explosión...")

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

tickers = exchange.fetch_tickers()

candidatas_pre_explosion = []

for symbol, data in tickers.items():
    if not symbol.endswith('/USDT'):
        continue
        
    price_change_24h = data['percentage'] if data['percentage'] is not None else 0
    vol_24h = data['quoteVolume'] if data['quoteVolume'] is not None else 0
    last_price = data['last'] if data['last'] is not None else 0
    
    # Filtro: Monedas con variación entre 0% y +5.0% que aún no despegaron y volumen aceptable
    if 0 <= price_change_24h <= 5.0 and vol_24h > 100000 and last_price > 0:
        try:
            ohlcv = exchange.fetch_ohlcv(symbol, timeframe='1h', limit=24)
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            
            vol_actual_1h = df['volume'].iloc[-1]
            promedio_vol_24h = df['volume'].mean()
            
            if promedio_vol_24h > 0 and vol_actual_1h >= (promedio_vol_24h * 2.5):
                ratio_volumen = round(vol_actual_1h / promedio_vol_24h, 2)
                ticker_limpio = symbol.split('/')[0]
                
                score = round(ratio_volumen * (5.1 - price_change_24h), 2)
                
                candidatas_pre_explosion.append({
                    'symbol': symbol,
                    'ticker': ticker_limpio,
                    'price': last_price,
                    'price_change': round(price_change_24h, 2),
                    'ratio_volumen': ratio_volumen,
                    'score': score
                })
        except Exception:
            continue

top_7_candidatas = sorted(candidatas_pre_explosion, key=lambda x: x['score'], reverse=True)[:7]

# ---------------------------------------------------------
# 3. CONSTRUCCIÓN DEL MENSAJE ESTÉTICO (TIPO CANAL PRINCIPAL)
# ---------------------------------------------------------
if top_7_candidatas:
    mensaje_telegram = "🧠 **CENTRAL DE INTELIGENCIA DE MERCADO**\n"
    mensaje_telegram += "🚀 **TOP 7 PRE-EXPLOSIÓN (Detección Temprana)**\n\n"
    
    for coin in top_7_candidatas:
        precio_fmt = formatear_precio(coin['price'])
        barras = obtener_barras_fuerza(coin['ratio_volumen'])
        
        # Enlace 1: Resumen IA (Hacia Netlify)
        url_netlify = f"{NETLIFY_BASE_URL}/?coin={coin['ticker']}"
        
        # Enlace 2: Tradear (Hacia Binance Spot público directo)
        url_binance = f"https://www.binance.com/es/trade/{coin['ticker']}_USDT?type=spot"
        
        mensaje_telegram += (
            f"• **{coin['ticker']}** | `{precio_fmt}` | {barras} | `+{coin['price_change']}%`\n"
            f"   └ 📊 [Resumen IA]({url_netlify}) | 🔶 [Tradear]({url_binance}) | Vol 1H: `{coin['ratio_volumen']}x`\n\n"
        )

    # Enviar payload a Telegram (sin la botonera gigante de abajo para mantenerlo limpio)
    if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
        url_api = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {
            'chat_id': TELEGRAM_CHAT_ID,
            'text': mensaje_telegram,
            'parse_mode': 'Markdown',
            'disable_web_page_preview': True
        }
        
        if MESSAGE_THREAD_ID:
            payload['message_thread_id'] = int(MESSAGE_THREAD_ID)
            
        res = requests.post(url_api, json=payload)
        print("✅ Reporte con formato limpio y enlaces enviado a Telegram.")

# ---------------------------------------------------------
# 4. ESTRUCTURA JSON PARA TRADER IA
# ---------------------------------------------------------
estructura_ia = {
    "timestamp": pd.Timestamp.now().isoformat(),
    "bot_origen": "Criptos Pre-Explosión",
    "top_candidatas": [
        {
            "token": item['ticker'],
            "precio": item['price'],
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

print("💾 Archivo JSON generado exitosamente.")
