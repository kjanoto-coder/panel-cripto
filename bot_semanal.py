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
    hoy = datetime.now(tz_arg)
    
    acumulado_semana = {}
    
    # Recorrer los últimos 7 días (de lunes a domingo) buscando los archivos de resumen diario
    for i in range(1, 8):
        dia = hoy - timedelta(days=i)
        fecha_str = dia.strftime('%Y-%m-%d')
        archivo = f'resumen_final_{fecha_str}.json'
        
        if os.path.exists(archivo):
            try:
                with open(archivo, 'r', encoding='utf-8') as f:
                    contenido = json.load(f)
                    for item in contenido.get('ranking', []):
                        ticker = item['ticker']
                        # Si la moneda ya apareció en otro día de la semana, conservamos la que tenga mayor porcentaje
                        if ticker not in acumulado_semana or item['change'] > acumulado_semana[ticker]['change']:
                            acumulado_semana[ticker] = item
            except Exception:
                pass

    if not acumulado_semana:
        print("No hay registros suficientes para armar el resumen semanal.")
        return

    # Ordenar estrictamente de mayor a menor porcentaje acumulado de toda la semana
    ranking_semanal = sorted(list(acumulado_semana.values()), key=lambda x: x['change'], reverse=True)
    
    # Construir mensaje idéntico al reporte diario pero a escala semanal
    mensaje = f"🧠 **CENTRAL DE INTELIGENCIA DE MERCADO**\n"
    mensaje += f"🏆 **RESUMEN SEMANAL GLOBAL DE GANADORAS** 📈\n"
    mensaje += f"📅 *Consolidado de la semana (Lunes a Domingo)*\n\n"
    mensaje += "` N° |   NOMBRE   |      $ BASE ➔ ACTUAL      | % SUBIDA `\n"
    mensaje += "`--------------------------------------------------`\n"
    
    for idx, item in enumerate(ranking_semanal, 1):
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
