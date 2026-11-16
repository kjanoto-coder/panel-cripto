import os
import csv
import requests
from datetime import datetime, timezone, timedelta

TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
TOPIC_ID_GANADORAS = os.getenv('TOPIC_ID_GANADORAS')

HISTORIAL_CSV = "historico_alertas.csv"

print("🔍 Iniciando Bot de Monedas Ganadoras (Ciclo de 5 min)...")

def registrar_en_csv(ticker, precio, rendimiento):
    tz_arg = timezone(timedelta(hours=-3))
    ahora = datetime.now(tz_arg).strftime('%Y-%m-%d %H:%M:%S')
    
    existe = os.path.exists(HISTORIAL_CSV)
    try:
        with open(HISTORIAL_CSV, mode='a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            if not existe:
                writer.writerow(['fecha_hora', 'ticker', 'precio', 'rendimiento'])
            writer.writerow([ahora, ticker, precio, rendimiento])
    except Exception as e:
        print(f"⚠️ Error al guardar en el CSV histórico: {e}")

def enviar_telegram(mensaje):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("❌ Faltan credenciales de Telegram.")
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
        response = requests.post(url, json=payload, timeout=15)
        if response.status_code == 200:
            print("✅ Alerta enviada a Telegram con éxito.")
        else:
            print(f"❌ Error de Telegram ({response.status_code}): {response.text}")
    except Exception as e:
        print(f"❌ Excepción conectando a Telegram: {e}")

def obtener_datos_binance():
    urls = [
        "https://api.binance.com/api/v3/ticker/24hr",
        "https://data-api.binance.vision/api/v3/ticker/24hr"
    ]
    for url in urls:
        try:
            res = requests.get(url, timeout=15)
            if res.status_code == 200:
                return res.json()
        except Exception:
            continue
    return []

def main():
    data = obtener_datos_binance()
    if not data:
        print("❌ No se pudieron obtener datos de Binance.")
        return

    ganadoras_encontradas = []

    for t in data:
        sym = t.get('symbol', '')
        if sym.endswith('USDT'):
            ticker = sym.replace('USDT', '')
            precio_actual = float(t.get('lastPrice', 0))
            cambio_24h = float(t.get('priceChangePercent', 0))
            
            # Filtro de ganadoras (ej: monedas con rendimiento positivo destacado, ajusta el umbral si es necesario)
            if cambio_24h >= 5.0:
                precio_base = precio_actual / (1 + (cambio_24h / 100))
                ganadoras_encontradas.append({
                    "ticker": ticker,
                    "precio": precio_actual,
                    "rendimiento": cambio_24h
                })
                # Guardamos de inmediato en el archivo compartido para el reporte diario
                registrar_en_csv(ticker, precio_actual, cambio_24h)

    if not ganadoras_encontradas:
        print("ℹ️ No hay suficientes ganadoras en este ciclo para reportar.")
        return

    # Ordenar de mayor a menor rendimiento para el mensaje en vivo
    ganadoras_ordenadas = sorted(ganadoras_encontradas, key=lambda x: x['rendimiento'], reverse=True)

    tz_arg = timezone(timedelta(hours=-3))
    fecha_hora_actual = datetime.now(tz_arg).strftime('%Y-%m-%d %H:%M')

    mensaje = f"💰 **MONEDAS GANADORAS (EN VIVO)**\n"
    mensaje += f"⏱ *Hora:* `{fecha_hora_actual}`\n\n"

    for g in ganadoras_ordenadas[:7]: # Top 7 en vivo por ejemplo
        precio_str = f"${g['precio']:.4f}" if g['precio'] < 1.0 else f"${g['precio']:.2f}"
        mensaje += f"• **{g['ticker']}** | Valor: `{precio_str}` | 🚀 `+{g['rendimiento']:.2f}%`\n"

    enviar_telegram(mensaje)

if __name__ == "__main__":
    main()
