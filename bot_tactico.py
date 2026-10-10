import os
import requests
import json
from datetime import datetime

# Configuración de variables de entorno y Telegram
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
TOPIC_ID_TACTICO = os.getenv("TOPIC_ID_TACTICO")

def obtener_datos_binance():
    url = "https://data-api.binance.vision/api/v3/ticker/24hr"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            return response.json()
        else:
            print(f"Error HTTP de Binance: {response.status_code}")
    except Exception as e:
        print(f"Excepción al conectar con Binance: {e}")
    return []

def seleccionar_top5_oportunidades(data):
    filtrados = []
    for item in data:
        symbol = item['symbol']
        if symbol.endswith('USDT'):
            try:
                precio = float(item['lastPrice'])
                cambio = float(item['priceChangePercent'])
                volumen = float(item['quoteVolume'])
                
                if precio < 1.0:
                    filtrados.append({
                        'symbol': symbol,
                        'close': precio,
                        'change': cambio,
                        'volume': volumen
                    })
            except ValueError:
                continue

    top_datos = sorted(filtrados, key=lambda x: x['change'], reverse=True)[:7]

    resultado = []
    for kline in top_datos:
        sim = kline['symbol'].replace('USDT', '')
        precio = kline['close']
        cambio = kline['change']
        volumen = kline['volume']
        
        binance_url = f"https://www.binance.com/es/trade/{sim}_USDT?type=spot"
        netlify_url = f"https://polite-baklava-8ec85f.netlify.app/?coin={sim}&price={precio}&change={cambio}"
        
        resultado.append({
            'simbolo': sim,
            'precio': precio,
            'change': cambio,
            'volumen': volumen,
            'binance_url': binance_url,
            'netlify_url': netlify_url
        })
        
    return resultado

def enviar_telegram(mensaje):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": mensaje,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }
    if TOPIC_ID_TACTICO:
        payload["message_thread_id"] = TOPIC_ID_TACTICO

    response = requests.post(url, json=payload)
    print("Respuesta de Telegram:", response.text)
    return response.json()

def main():
    datos = obtener_datos_binance()
    if not datos:
        print("Error al obtener datos de Binance.")
        return

    oportunidades = seleccionar_top5_oportunidades(datos)
    if not oportunidades:
        print("No se encontraron oportunidades con los filtros establecidos.")
        return
    
    # Construcción del mensaje con HTML perfectamente escapado para Telegram
    mensaje = "🧠 <b>CENTRAL DE INTELIGENCIA DE MERCADO (Cazador Táctico)</b>\n"
    mensaje += "📊 <i>Monitoreo Cuantitativo: Activos Spot < $1 USD</i>\n"
    mensaje += "⚡ <b>Estado: Automatización Activa (Cada 15m)</b>\n\n"
    mensaje += "🚀 <b>TOP OPORTUNIDADES TÁCTICAS</b>\n"
    
    for op in oportunidades:
        precio_str = f"${op['precio']:.4f}" if op['precio'] < 1 else f"${op['precio']:.2f}"
        cambio_str = f"+{op['change']:.1f}%" if op['change'] >= 0 else f"{op['change']:.1f}%"
        
        # Uso estricto de comillas dobles escapadas para el atributo href de Telegram
        link_ia = f"<a href=\"{op['netlify_url']}\">Resumen IA</a>"
        link_trade = f"<a href=\"{op['binance_url']}\">Tradear</a>"
        
        mensaje += f"• <b>{op['simbolo']}</b> | {precio_str} | 🟢🟢🟢🟢🟢 |\n"
        mensaje += f"  └ 📊 {link_ia} | 🔶 {link_trade} ({cambio_str})\n"

    enviar_telegram(mensaje)

if __name__ == "__main__":
    main()
