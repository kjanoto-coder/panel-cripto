import os
import requests
from datetime import datetime

# Configuración de los secretos de Telegram desde GitHub Actions
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
TOPIC_ID_GANADORAS = os.getenv('TOPIC_ID_GANADORAS')

EXCLUDE_TOKENS = ['UP', 'DOWN', 'BEAR', 'BULL', 'USDC', 'FDUSD', 'USDT', 'TUSD', 'DAI', 'BUSD', 'EUR', 'GBP', 'WBTC', 'AEUR', 'PAXG']

def obtener_datos_binance():
    try:
        # Usamos proxy seguro de allorigins para evitar el bloqueo 451 en GitHub Actions
        target_url = 'https://api.binance.com/api/v3/ticker/24hr'
        proxy_url = f'https://api.allorigins.win/raw?url={requests.utils.quote(target_url)}'
        
        response = requests.get(proxy_url, timeout=15)
        response.raise_for_status()
        data = response.json()
        
        mercado = []
        for t in data:
            if t['symbol'].endswith('USDT'):
                clean = t['symbol'].replace('USDT', '')
                if clean not in EXCLUDE_TOKENS:
                    mercado.append({
                        'ticker': clean,
                        'price': float(t['lastPrice']),
                        'change': float(t['priceChangePercent'])
                    })
        return mercado
    except Exception as e:
        print(f"Error al conectar con Binance via proxy: {e}")
        return []

def formatear_precio(precio):
    if precio < 0.0001:
        return f"${precio:.8f}"
    if precio < 1:
        return f"${precio:.5f}"
    if precio < 10:
        return f"${precio:.4f}"
    return f"${precio:,.2f}"

def generar_circulos(cambio):
    if cambio >= 35:
        return "🟢🟢🟢🟢🟢"
    elif cambio >= 25:
        return "🟢🟢🟢🟢⬜"
    elif cambio >= 15:
        return "🟢🟢🟢⬜⬜"
    elif cambio >= 8:
        return "🟢🟢⬜⬜⬜"
    else:
        return "🟢⬜⬜⬜⬜"

def enviar_telegram(mensaje):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Faltan las credenciales de Telegram en los secretos.")
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        'chat_id': TELEGRAM_CHAT_ID,
        'text': mensaje,
        'parse_mode': 'Markdown',
        'disable_web_page_preview': True
    }
    
    if TOPIC_ID_GANADORAS:
        payload['message_thread_id'] = int(TOPIC_ID_GANADORAS)

    try:
        res = requests.post(url, json=payload, timeout=10)
        if res.ok:
            print("Alerta exacta estilo reporte enviada con éxito a Telegram.")
        else:
            print(f"Error al enviar a Telegram: {res.text}")
    except Exception as e:
        print(f"Excepción al enviar mensaje: {e}")

def main():
    print("Ejecutando escaneo para Top 7 Ganadoras via Proxy...")
    mercado = obtener_datos_binance()
    
    if not mercado:
        print("No se pudieron obtener datos del mercado.")
        return

    ganadoras = sorted(mercado, key=lambda x: x['change'], reverse=True)[:7]
    fecha_actual = datetime.now().strftime('%Y-%m-%d')
    
    mensaje = f"🧠 **CENTRAL DE INTELIGENCIA DE MERCADO (1/5)**\n"
    mensaje += f"🚀 **1. TOP 7 GANADORAS (Detalle)**\n"
    mensaje += f"📅 *Fecha:* `{fecha_actual}`\n\n"
    
    for item in ganadoras:
        ticker = item['ticker']
        precio_fmt = formatear_precio(item['price'])
        circulos = generar_circulos(item['change'])
        cambio = item['change']
        
        link_resumen = f"https://es.tradingview.com/symbols/{ticker}USDT/"
        link_tradear = f"https://www.binance.com/es-AR/trade/{ticker}_USDT"
        
        mensaje += f"• **{ticker}** | `{precio_fmt}` | {circulos} | `+{cambio:.1f}%`\n"
        mensaje += f" ┗ 📊 [Resumen IA]({link_resumen}) | 🔶 [Tradear]({link_tradear})\n"
    
    enviar_telegram(mensaje)

if __name__ == "__main__":
    main()
