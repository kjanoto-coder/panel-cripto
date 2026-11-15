import os
import json
import requests
from datetime import datetime, timezone, timedelta

TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
TOPIC_ID_GANADORAS = os.getenv('TOPIC_ID_GANADORAS')

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

def formatear_precio(precio):
    if precio < 0.0001:
        return f"${precio:.8f}"
    if precio < 1:
        return f"${precio:.5f}"
    if precio < 10:
        return f"${precio:.4f}"
    return f"${precio:,.2f}"

def main():
    tz_arg = timezone(timedelta(hours=-3))
    ayer = datetime.now(tz_arg) - timedelta(days=1)
    fecha_ayer = ayer.strftime('%Y-%m-%d')
    json_diario = f'datos_ganadoras_{fecha_ayer}.json'
    
    if not os.path.exists(json_diario):
        print(f"No hay registros para la fecha {fecha_ayer}")
        return

    try:
        with open(json_diario, 'r', encoding='utf-8') as f:
            data = json.load(f)
            monedas = list(data.get('monedas', {}).values())
    except Exception as e:
        print(f"Error leyendo el archivo diario: {e}")
        return

    # Ordenar de mayor a menor porcentaje acumulado del día
    ranking = sorted(monedas, key=lambda x: x['change'], reverse=True)
    
    # Guardar archivo consolidado oficial para la semana
    archivo_semanal_registro = f'resumen_final_{fecha_ayer}.json'
    with open(archivo_semanal_registro, 'w', encoding='utf-8') as f:
        json.dump({'fecha': fecha_ayer, 'ranking': ranking}, f, ensure_ascii=False, indent=4)

    # Construir mensaje diario detallado incluyendo Precio Base ➔ Precio Actual
    mensaje = f"🧠 **CENTRAL DE INTELIGENCIA DE MERCADO**\n"
    mensaje += f"📊 **RESUMEN DIARIO DE GANADORAS** 🚀\n"
    mensaje += f"📅 *Fecha:* `{fecha_ayer}`\n\n"
    
    for idx, item in enumerate(ranking, 1):
        ticker = item['ticker']
        # Si ya viene calculado el precio base del bot de 15m lo usamos, sino lo calculamos matemáticamente
        precio_act = item['price']
        cambio = item['change']
        base_price = item.get('base_price', precio_act / (1 + (cambio / 100)))
        
        base_fmt = formatear_precio(base_price)
        precio_fmt = formatear_precio(precio_act)
        
        link_resumen = f"https://es.tradingview.com/symbols/{ticker}USDT/"
        link_tradear = f"https://www.binance.com/es-AR/trade/{ticker}_USDT"
        
        mensaje += f"`{idx}.` **{ticker}** | Base: `{base_fmt}` ➔ `{precio_fmt}` | `+{cambio:.1f}%`\n"
        mensaje += f" ┗ 📊 [Resumen IA]({link_resumen}) | 🔶 [Tradear]({link_tradear})\n\n"
        
    enviar_telegram(mensaje)

if __name__ == "__main__":
    main()
