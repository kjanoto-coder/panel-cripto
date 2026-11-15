import os
import json
import requests
from datetime import datetime, timezone, timedelta

TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
TOPIC_ID_GANADORAS = os.getenv('TOPIC_ID_GANADORAS')

EXCLUDE_TOKENS = ['CREAM', 'UP', 'DOWN', 'BEAR', 'BULL', 'USDC', 'FDUSD', 'USDT', 'TUSD', 'DAI', 'BUSD', 'EUR', 'GBP', 'WBTC', 'AEUR', 'PAXG']

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
    # Zona horaria local (Argentina UTC-3)
    tz_arg = timezone(timedelta(hours=-3))
    ahora = datetime.now(tz_arg)
    hoy_str = ahora.strftime('%Y-%m-%d')
    json_file = f'datos_ganadoras_{hoy_str}.json'
    
    # Cargar acumulado del día actual (desde las 00:00 hs)
    datos_acumulados = {'fecha': hoy_str, 'monedas': {}}
    if os.path.exists(json_file):
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                contenido = json.load(f)
                if contenido.get('fecha') == hoy_str:
                    datos_acumulados = contenido
        except Exception:
            pass

    # Obtener datos actuales de Binance
    mercado = obtener_datos_binance()
    if not mercado:
        return

    # Incorporar y actualizar el récord máximo de cada moneda durante el día sin duplicados
    for item in mercado:
        ticker = item['ticker']
        if ticker not in datos_acumulados['monedas'] or item['change'] > datos_acumulados['monedas'][ticker]['change']:
            datos_acumulados['monedas'][ticker] = item

    # Guardar el JSON del día actualizado en el repositorio
    try:
        with open(json_file, 'w', encoding='utf-8') as f:
            json.dump(datos_acumulados, f, ensure_ascii=False, indent=4)
    except Exception:
        pass

    # Ordenar estrictamente de mayor a menor porcentaje acumulado
    ranking_dia = sorted(list(datos_acumulados['monedas'].values()), key=lambda x: x['change'], reverse=True)

    # Guardar también el respaldo para el resumen semanal del domingo
    archivo_semanal = f'resumen_final_{hoy_str}.json'
    with open(archivo_semanal, 'w', encoding='utf-8') as f:
        json.dump({'fecha': hoy_str, 'ranking': ranking_dia}, f, ensure_ascii=False, indent=4)

    # Construir el mensaje en formato tabla limpia con Precio Base -> Actual
    mensaje = f"🧠 **CENTRAL DE INTELIGENCIA DE MERCADO**\n"
    mensaje += f"🚀 **GANADORAS ACUMULADAS DEL DÍA**\n"
    mensaje += f"📅 *Fecha:* `{hoy_str}` (Actualizado en vivo c/15m)\n\n"
    mensaje += "` N° |   NOMBRE   |      $ BASE ➔ ACTUAL      | % SUBIDA `\n"
    mensaje += "`--------------------------------------------------`\n"
    
    for idx, item in enumerate(ranking_dia, 1):
        ticker = item['ticker'].ljust(8)[:8]
        precio_act = item['price']
        cambio = item['change']
        base_price = item.get('base_price', precio_act / (1 + (cambio / 100)))
        
        base_fmt = formatear_precio(base_price)
        precio_fmt = formatear_precio(precio_act)
        rango_precio = f"{base_fmt} ➔ {precio_fmt}".ljust(21)[:21]
        porcentaje = f"+{cambio:.1f}%".ljust(7)[:7]
        
        mensaje += f"`{idx:2d} | {ticker} | {rango_precio} | {porcentaje}`\n"

    enviar_telegram(mensaje)

if __name__ == "__main__":
    main()
