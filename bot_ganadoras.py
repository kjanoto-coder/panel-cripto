import os
import csv
import requests
from datetime import datetime, timezone, timedelta

TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
TOPIC_ID_GANADORAS = os.getenv('TOPIC_ID_GANADORAS')

HISTORIAL_CSV = "historico_alertas.csv"

def registrar_en_csv(ticker, precio_actual, rendimiento):
    tz_arg = timezone(timedelta(hours=-3))
    ahora = datetime.now(tz_arg).strftime('%Y-%m-%d %H:%M:%S')
    
    existe = os.path.exists(HISTORIAL_CSV)
    try:
        with open(HISTORIAL_CSV, mode='a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            if not existe:
                writer.writerow(['fecha_hora', 'ticker', 'precio', 'rendimiento'])
            writer.writerow([ahora, ticker, precio_actual, rendimiento])
    except Exception as e:
        print(f"⚠️ Error al guardar en CSV: {e}")

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
            print("✅ Mensaje enviado a Telegram con éxito.")
        else:
            print(f"❌ Error de Telegram ({response.status_code}): {response.text}")
    except Exception as e:
        print(f"❌ Excepción conectando a Telegram: {e}")

def obtener_datos_binance():
    # Espejos oficiales para evitar bloqueos geográficos en GitHub Actions
    urls = [
        "https://data-api.binance.vision/api/v3/ticker/24hr",
        "https://api1.binance.com/api/v3/ticker/24hr",
        "https://api.binance.com/api/v3/ticker/24hr"
    ]
    for url in urls:
        try:
            res = requests.get(url, timeout=15)
            if res.status_code == 200:
                return res.json()
        except Exception:
            continue
    return []

def generar_bolillas(rendimiento):
    if rendimiento >= 50:
        return "🟢🟢🟢🟢🟢"
    elif rendimiento >= 30:
        return "🟢🟢🟢🟢⬜"
    elif rendimiento >= 15:
        return "🟢🟢🟢⬜⬜"
    elif rendimiento >= 8:
        return "🟢🟢⬜⬜⬜"
    else:
        return "🟢⬜⬜⬜⬜"

def main():
    data = obtener_datos_binance()
    if not data:
        print("❌ Error crítico: Binance no devolvió datos.")
        return

    ganadoras = []
    for t in data:
        sym = t.get('symbol', '')
        # Tomamos exclusivamente los pares contra USDT que publica Binance de forma oficial
        if sym.endswith('USDT') and not any(sub in sym for sub in ['UP', 'DOWN', 'BULL', 'BEAR']):
            ticker = sym.replace('USDT', '')
            try:
                precio_actual = float(t.get('lastPrice', 0))
                cambio_24h = float(t.get('priceChangePercent', 0))
                volumen_usdt = float(t.get('quoteVolume', 0))
            except ValueError:
                continue
            
            # Filtro estricto para asegurar que sean monedas con movimiento real y volumen considerable
            if cambio_24h > 0 and volumen_usdt >= 100000:
                ganadoras.append({
                    "ticker": ticker,
                    "precio": precio_actual,
                    "rendimiento": cambio_24h
                })

    if not ganadoras:
        print("⚠️ No hay suficientes ganadoras para mostrar.")
        return

    # Ordenar exactamente de mayor a menor rendimiento (Top 7 oficial idéntico a Binance)
    ganadoras_ordenadas = sorted(ganadoras, key=lambda x: x['rendimiento'], reverse=True)

    tz_arg = timezone(timedelta(hours=-3))
    fecha_hoy = datetime.now(tz_arg).strftime('%Y-%m-%d')

    mensaje = f"🧠 **CENTRAL DE INTELIGENCIA DE MERCADO (1/5)**\n"
    mensaje += f"🚀 **1. TOP 7 GANADORAS (Detalle)**\n"
    mensaje += f"📅 Fecha: `{fecha_hoy}`\n\n"

    for g in ganadoras_ordenadas[:7]:
        precio_str = f"${g['precio']:.5f}" if g['precio'] < 1.0 else f"${g['precio']:.2f}"
        bolillas = generar_bolillas(g['rendimiento'])
        
        # Guardamos en el archivo CSV la información oficial exacta para que el reporte diario la consuma sin alteraciones
        registrar_en_csv(g['ticker'], g['precio'], g['rendimiento'])

        mensaje += f"• **{g['ticker']}** | Precio: `{precio_str}` | `+{g['rendimiento']:.2f}%`\n"
        mensaje += f"{bolillas}\n"
        mensaje += f"┗ 📊 [Resumen IA](https://t.me/) | 🔶 Tradear\n\n"

    enviar_telegram(mensaje)

if __name__ == "__main__":
    main()
