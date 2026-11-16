import os
import csv
import requests
from datetime import datetime, timezone, timedelta

TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
TOPIC_ID_GANADORAS = os.getenv('TOPIC_ID_GANADORAS')

HISTORIAL_CSV = "historico_alertas.csv"

def registrar_en_csv(ticker, precio_base, precio_actual, rendimiento):
    tz_arg = timezone(timedelta(hours=-3))
    ahora = datetime.now(tz_arg).strftime('%Y-%m-%d %H:%M:%S')
    
    existe = os.path.exists(HISTORIAL_CSV)
    try:
        with open(HISTORIAL_CSV, mode='a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            if not existe:
                writer.writerow(['fecha_hora', 'ticker', 'precio_base', 'precio_actual', 'rendimiento'])
            writer.writerow([ahora, ticker, precio_base, precio_actual, rendimiento])
    except Exception as e:
        print(f"⚠️ Error al guardar en CSV: {e}")

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
        try:
            payload['message_thread_id'] = int(TOPIC_ID_GANADORAS)
        except ValueError:
            pass
            
    try:
        requests.post(url, json=payload, timeout=15)
    except Exception as e:
        print(f"Error Telegram: {e}")

def obtener_datos_binance():
    try:
        res = requests.get("https://api.binance.com/api/v3/ticker/24hr", timeout=15)
        if res.status_code == 200:
            return res.json()
    except Exception:
        pass
    return []

def main():
    data = obtener_datos_binance()
    if not data:
        return

    ganadoras = []
    for t in data:
        sym = t.get('symbol', '')
        if sym.endswith('USDT'):
            ticker = sym.replace('USDT', '')
            precio_actual = float(t.get('lastPrice', 0))
            cambio_24h = float(t.get('priceChangePercent', 0))
            
            # Filtro de ganadoras destacadas
            if cambio_24h >= 5.0:
                precio_base = precio_actual / (1 + (cambio_24h / 100))
                ganadoras.append({
                    "ticker": ticker,
                    "base": precio_base,
                    "actual": precio_actual,
                    "rendimiento": cambio_24h
                })
                # Registramos en el CSV histórico para el reporte diario de las 00:00
                registrar_en_csv(ticker, precio_base, precio_actual, cambio_24h)

    if not ganadoras:
        return

    # Ordenar de mayor a menor rendimiento
    ganadoras_ordenadas = sorted(ganadoras, key=lambda x: x['rendimiento'], reverse=True)

    # Reconstrucción exacta del diseño original que pediste
    mensaje = ""
    for g in ganadoras_ordenadas[:7]: # Top 7
        base_str = f"${g['base']:.5f}" if g['base'] < 1.0 else f"${g['base']:.2f}"
        actual_str = f"${g['actual']:.5f}" if g['actual'] < 1.0 else f"${g['actual']:.2f}"
        
        mensaje += f"• **{g['ticker']}** | Base: `{base_str}` ➔ `{actual_str}` | `+{g['rendimiento']:.2f}%`\n"

    if mensaje:
        enviar_telegram(mensaje)

if __name__ == "__main__":
    main()
