import os
import requests

TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
TOPIC_ID_GANADORAS = os.getenv('TOPIC_ID_GANADORAS')

# Lista negra estricta para matchear exactamente con Binance (incluyendo KDA)
EXCLUDE_TOKENS = ['CREAM', 'KDA', 'CLV', 'UP', 'DOWN', 'BEAR', 'BULL', 'USDC', 'FDUSD', 'USDT', 'TUSD', 'DAI', 'BUSD', 'EUR', 'GBP', 'WBTC', 'AEUR', 'PAXG']

def obtener_datos_binance():
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'application/json'
    }
    urls = [
        'https://api.binance.com/api/v3/ticker/24hr',
        'https://data-api.binance.vision/api/v3/ticker/24hr'
    ]
    for url in urls:
        try:
            response = requests.get(url, headers=headers, timeout=15)
            if response.status_code == 200:
                data = response.json()
                mercado = []
                for t in data:
                    if t['symbol'].endswith('USDT'):
                        clean = t['symbol'].replace('USDT', '')
                        change = float(t['priceChangePercent'])
                        price = float(t['lastPrice'])
                        
                        # Filtramos la lista negra y solo tomamos las que están en positivo
                        if clean not in EXCLUDE_TOKENS and change > 0:
                            base_price = price / (1 + (change / 100))
                            mercado.append({
                                'ticker': clean,
                                'price': price,
                                'base_price': base_price,
                                'change': change
                            })
                if mercado:
                    return mercado
        except Exception:
            continue
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
        requests.post(url, json=payload, timeout=10)
    except Exception:
        pass

def main():
    mercado = obtener_datos_binance()
    if not mercado:
        return

    # Ordenar estrictamente de mayor a menor según el % real directo de Binance y tomar el Top 7
    ganadoras = sorted(mercado, key=lambda x: x['change'], reverse=True)[:7]
    
    from datetime import datetime, timezone, timedelta
    tz_arg = timezone(timedelta(hours=-3))
    fecha_actual = datetime.now(tz_arg).strftime('%Y-%m-%d')
    
    mensaje = f"🧠 **CENTRAL DE INTELIGENCIA DE MERCADO (1/5)**\n"
    mensaje += f"🚀 **1. TOP 7 GANADORAS (Detalle)**\n"
    mensaje += f"📅 *Fecha:* `{fecha_actual}`\n\n"
    
    for item in ganadoras:
        ticker = item['ticker']
        precio_fmt = formatear_precio(item['price'])
        base_fmt = formatear_precio(item['base_price'])
        circulos = generar_circulos(item['change'])
        cambio = item['change']
        
        link_resumen = f"https://es.tradingview.com/symbols/{ticker}USDT/"
        link_tradear = f"https://www.binance.com/es-AR/trade/{ticker}_USDT"
        
        mensaje += f"• **{ticker}** | Base: `{base_fmt}` ➔ `{precio_fmt}` | `+{cambio:.2f}%`\n"
        mensaje += f"   {circulos}\n"
        mensaje += f" ┗ 📊 [Resumen IA]({link_resumen}) | 🔶 [Tradear]({link_tradear})\n\n"
    
    enviar_telegram(mensaje)

if __name__ == "__main__":
    main()
