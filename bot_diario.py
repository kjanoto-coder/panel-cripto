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
    # Al ejecutarse a las 00:00, procesamos el día que acaba de concluir (ayer)
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

    # Ordenar estrictamente de mayor a menor porcentaje acumulado del día
    ranking = sorted(monedas, key=lambda x: x['change'], reverse=True)
    
    # Guardar archivo consolidado oficial para que luego el Bot 3 (Semanal) lo lea
    archivo_semanal_registro = f'resumen_final_{fecha_ayer}.json'
    with open(archivo_semanal_registro, 'w', encoding='utf-8') as f:
        json.dump({'fecha': fecha_ayer, 'ranking': ranking}, f, ensure_ascii=False, indent=4)

    # Construir mensaje estilo tabla limpia idéntica al Excel pero con precio base y actual
    mensaje = f"🧠 **CENTRAL DE INTELIGENCIA DE MERCADO**\n"
    mensaje += f"📊 **RESUMEN DIARIO DE GANADORAS** 🚀\n"
    mensaje += f"📅 *Fecha:* `{fecha_ayer}`\n\n"
    mensaje += "` N° |   NOMBRE   |      $ BASE ➔ ACTUAL      | % SUBIDA `\n"
    mensaje += "`--------------------------------------------------`\n"
    
    for idx, item in enumerate(ranking, 1):
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
