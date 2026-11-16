import os
import json
import requests
from datetime import datetime, timezone, timedelta

TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
TOPIC_ID_GANADORAS = os.getenv('TOPIC_ID_GANADORAS')

print("🔍 Iniciando ejecución de bot_ganadoras.py...")

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
            print("✅ Reporte enviado a Telegram con éxito.")
        else:
            print(f"❌ Error de Telegram API ({response.status_code}): {response.text}")
    except Exception as e:
        print(f"❌ Excepción al conectar con Telegram: {e}")

def obtener_precios_binance():
    try:
        res = requests.get("https://api.binance.com/api/v3/ticker/24hr", timeout=15)
        if res.status_code == 200:
            return res.json()
    except Exception:
        pass
    return []

def main():
    archivo_datos = "datos_pre_explosion_ia.json"
    registros = []

    # Intentar leer del archivo si existe y no está vacío
    if os.path.exists(archivo_datos) and os.path.getsize(archivo_datos) > 0:
        try:
            with open(archivo_datos, 'r', encoding='utf-8') as f:
                contenido = json.load(f)
                if isinstance(contenido, dict):
                    registros = contenido.get("top_candidatas", [])
                elif isinstance(contenido, list):
                    registros = contenido
        except Exception as e:
            print(f"⚠️ No se pudo leer el JSON local, consultando Binance directamente: {e}")

    # Si no hay registros en el archivo, respaldamos consultando Binance directamente para no fallar
    ganadoras = []
    if registros:
        for item in registros:
            ticker = item.get('ticker', item.get('symbol', ''))
            precio_base = float(item.get('price', 0))
            precio_actual = float(item.get('precio_actual', precio_base))
            if precio_base > 0:
                rend = ((precio_actual - precio_base) / precio_base) * 100
                ganadoras.append({"ticker": ticker, "base": precio_base, "rendimiento": rend})
    else:
        print("⚠️ El archivo JSON estaba vacío o sin candidatas. Tomando datos 24h de Binance...")
        data_binance = obtener_precios_binance()
        for t in data_binance:
            sym = t.get('symbol', '')
            if sym.endswith('USDT'):
                ticker = sym.replace('USDT', '')
                precio_actual = float(t.get('lastPrice', 0))
                cambio_24h = float(t.get('priceChangePercent', 0))
                if cambio_24h > 0:
                    precio_base = precio_actual / (1 + (cambio_24h / 100))
                    ganadoras.append({"ticker": ticker, "base": precio_base, "rendimiento": cambio_24h})

    if not ganadoras:
        print("❌ No hay datos de ganadoras para mostrar.")
        return

    # Ordenar de mayor a menor rendimiento
    ganadoras_ordenadas = sorted(ganadoras, key=lambda x: x['rendimiento'], reverse=True)

    tz_arg = timezone(timedelta(hours=-3))
    fecha_hoy = datetime.now(tz_arg).strftime('%Y-%m-%d')

    mensaje = f"🏆 **REPORTE DIARIO DE MONEDAS GANADORAS**\n"
    mensaje += f"📅 *Fecha:* `{fecha_hoy}`\n\n"

    for idx, g in enumerate(ganadoras_ordenadas[:10], 1):
        base_str = f"${g['base']:.2f}" if g['base'] >= 1.0 else f"${g['base']:.4f}"
        mensaje += f"{idx}. **{g['ticker']}** | Base: `{base_str}` | 🚀 `+{g['rendimiento']:.2f}%`\n"

    enviar_telegram(mensaje)

if __name__ == "__main__":
    main()
