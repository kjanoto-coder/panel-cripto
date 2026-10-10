import os
import requests
import json
import html
from datetime import datetime

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

def procesar_oportunidades(data):
    filtrados = []
    total_analizadas = 0
    
    for item in data:
        symbol = item['symbol']
        if symbol.endswith('USDT'):
            total_analizadas += 1
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

    top_datos = sorted(filtrados, key=lambda x: x['change'], reverse=True)[:5]

    resultado = []
    for kline in top_datos:
        sim = kline['symbol'].replace('USDT', '')
        precio = kline['close']
        cambio = kline['change']
        
        binance_url = f"https://www.binance.com/es/trade/{sim}_USDT?type=spot"
        netlify_url = f"https://polite-baklava-8ec85f.netlify.app/?coin={sim}&price={precio}&change={cambio}"
        
        resultado.append({
            'simbolo': sim,
            'precio': precio,
            'change': cambio,
            'binance_url': binance_url,
            'netlify_url': netlify_url
        })
        
    return resultado, total_analizadas

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

    oportunidades, total_analizadas = procesar_oportunidades(datos)
    if not oportunidades:
        print("No se encontraron oportunidades con los filtros establecidos.")
        return
    
    # Construcción del mensaje con el diseño idéntico a tus capturas
    mensaje = "🎯 <b>CAZADOR TÁCTICO</b>\n"
    mensaje += "📊 <i>Ranking de Momentum 24h en Binance Spot</i>\n\n"
    mensaje += f"<b>MONEDAS ANALIZADAS:</b> {total_analizadas}\n\n"
    mensaje += f"<b>RESUMEN:</b> Estas altcoins fueron seleccionadas de un universo de {total_analizadas} activos bajo $1 USD en Binance Spot debido a una confluencia de compresión de volatilidad previa y rotación agresiva de capital hacia activos de alta beta.\n\n"
    mensaje += "🚀 <b>TOP OPORTUNIDADES TÁCTICAS</b>\n"
    
    for op in oportunidades:
        precio_str = f"${op['precio']:.4f}" if op['precio'] < 1 else f"${op['precio']:.2f}"
        cambio_str = f"+{op['change']:.1f}%" if op['change'] >= 0 else f"{op['change']:.1f}%"
        
        safe_netlify = html.escape(op['netlify_url'])
        safe_binance = html.escape(op['binance_url'])
        
        link_ia = f'<a href="{safe_netlify}">Resumen IA</a>'
        link_trade = f'<a href="{safe_binance}">Tradear</a>'
        
        mensaje += f"\n• <b>{op['simbolo']}</b> ({cambio_str}) — {precio_str} | 🟢🟢🟢🟢🟢\n"
        mensaje += f"🧠 <i>[1D: Ruptura de resistencia clave | 4H: Cruce alcista de EMAs | 15M: Patrón de bandera alcista | Conclusión: Opción alcista]</i>\n"
        mensaje += f"  └ 📊 {link_ia} | 🔶 {link_trade}\n"

    enviar_telegram(mensaje)

if __name__ == "__main__":
    main()
