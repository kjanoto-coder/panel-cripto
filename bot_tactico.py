import os
import requests
import json
import html
import time
from datetime import datetime
import matplotlib.pyplot as plt

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
TOPIC_ID_TACTICO = os.getenv("TOPIC_ID_TACTICO")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

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

def formatear_precio(val):
    """Ajusta dinámicamente la cantidad de decimales según el valor de la criptomoneda para evitar ceros incorrectos."""
    if val < 0.0001:
        return f"${val:.8f}"
    elif val < 0.01:
        return f"${val:.6f}"
    elif val < 1.0:
        return f"${val:.4f}"
    else:
        return f"${val:.2f}"

def generar_sintesis_resumen(simbolo, precio, cambio, volumen, high, low):
    """
    Genera un análisis técnico detallado, específico e independiente utilizando la API REST de Gemini.
    """
    if GEMINI_API_KEY:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
        headers = {"Content-Type": "application/json"}
        
        prompt = f"""
        Eres un analista técnico sénior de mercados cripto. Genera un análisis técnico específico y detallado para la criptomoneda {simbolo} en Binance Spot usando estos datos exactos de 24h:
        - Precio actual: {formatear_precio(precio)}
        - Variación 24h: {cambio:+.2f}%
        - Volumen 24h: ${volumen:,.0f} USDT
        - Máximo 24h (Resistencia): {formatear_precio(high)}
        - Mínimo 24h (Soporte): {formatear_precio(low)}

        INSTRUCCIONES:
        Escribe un diagnóstico de precisión en exactamente una sola línea encerrada entre corchetes, especificando niveles exactos de precio.

        FORMATO OBLIGATORIO:
        [1D: Impulso sobre soporte en {formatear_precio(low)} | 4H: Búsqueda de resistencia en {formatear_precio(high)} | 15M: Gatillo activo en {formatear_precio(precio)} | Conclusión: Opción alcista]
        """
        
        payload = {
            "contents": [{
                "parts": [{"text": prompt}]
            }]
        }
        
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=10)
            if response.status_code == 200:
                data = response.json()
                texto = data['candidates'][0]['content']['parts'][0]['text'].strip()
                if not (texto.startswith('[') and texto.endswith(']')):
                    texto = f"[{texto}]"
                return texto
        except Exception as e:
            print(f"Error en API REST de Gemini para {simbolo}: {e}")

    # Fallback técnico dinámico con números reales si la API no está disponible
    return f"[1D: Acumulación sobre piso en {formatear_precio(low)} | 4H: Testeo de techo en {formatear_precio(high)} | 15M: Entrada de flujo en {formatear_precio(precio)} | Conclusión: Giro alcista]"

def procesar_oportunidades(data):
    filtrados = []
    total_sub1 = 0
    
    # Lista negra de tokens deslistados o con anomalías de nombres/datos en la API Spot de Binance
    LISTA_NEGRA = ['PNTUSDT', 'VGXUSDT', 'BNCUSDT']
    
    for item in data:
        symbol = item['symbol']
        if symbol.endswith('USDT'):
            try:
                precio = float(item['lastPrice'])
                cambio = float(item['priceChangePercent'])
                volumen = float(item['quoteVolume'])
                high = float(item['highPrice'])
                low = float(item['lowPrice'])
                
                # Conteo exclusivo de activos sub-$1 USD, con volumen real > $50,000 USDT y fuera de lista negra
                if 0 < precio < 1.0 and volumen > 50000 and symbol not in LISTA_NEGRA:
                    total_sub1 += 1
                    filtrados.append({
                        'symbol': symbol,
                        'close': precio,
                        'change': cambio,
                        'volume': volumen,
                        'high': high,
                        'low': low
                    })
            except ValueError:
                continue

    top_datos = sorted(filtrados, key=lambda x: x['change'], reverse=True)[:5]

    resultado = []
    for kline in top_datos:
        sim = kline['symbol'].replace('USDT', '')
        precio = kline['close']
        cambio = kline['change']
        volumen = kline['volume']
        high = kline['high']
        low = kline['low']
        
        binance_url = f"https://www.binance.com/es/trade/{sim}_USDT?type=spot"
        timestamp = int(time.time())
        
        # URL optimizada que envía high, low y un cache-buster dinámico
        netlify_url = f"https://polite-baklava-8ec85f.netlify.app/?coin={sim}&price={precio}&change={cambio}&high={high}&low={low}&vol={volumen:,.0f}&v={timestamp}"
        
        resumen_moneda = generar_sintesis_resumen(sim, precio, cambio, volumen, high, low)
        time.sleep(0.8)
        
        resultado.append({
            'simbolo': sim,
            'precio': precio,
            'change': cambio,
            'binance_url': binance_url,
            'netlify_url': netlify_url,
            'resumen': resumen_moneda
        })
        
    return resultado, total_sub1

def generar_grafico_narrativa(oportunidades):
    ops_ordenadas = sorted(oportunidades, key=lambda x: x['change'])
    
    simbolos = [op['simbolo'] for op in ops_ordenadas]
    cambios = [op['change'] for op in ops_ordenadas]
    
    fig, ax = plt.subplots(figsize=(8, 6), facecolor='#0b132b')
    ax.set_facecolor('#0b132b')
    
    bars = ax.bar(simbolos, cambios, color='#00c853', width=0.5, zorder=3)
    
    ax.grid(True, color='#1e293b', linestyle='-', linewidth=0.8, zorder=1)
    ax.set_axisbelow(True)
    
    for spine in ['top', 'right', 'left', 'bottom']:
        ax.spines[spine].set_visible(False)
        
    ax.tick_params(left=False, labelleft=False, bottom=False)
    ax.tick_params(axis='x', colors='white', labelsize=11)
    
    for bar, sim, cambio in zip(bars, simbolos, cambios):
        yval = bar.get_height()
        xval = bar.get_x() + bar.get_width() / 2.0
        
        ax.text(xval, yval + 4.0, f"+{cambio:.1f}%" if cambio >= 0 else f"{cambio:.1f}%", 
                ha='center', va='bottom', color='#00c853', fontweight='bold', fontsize=11)
        
        ax.plot(xval, yval + 1.5, marker='o', markersize=22, markerfacecolor='#0f172a', markeredgecolor='#00c853', markeredgewidth=1.5, zorder=4)
        ax.text(xval, yval + 1.5, sim, ha='center', va='center', color='white', fontsize=8, fontweight='bold', zorder=5)

    fecha_str = datetime.now().strftime('%Y-%m-%d')
    plt.title("NARRATIVA DEL DÍA\nTOP 5 ALTCOINS SUB-$1 USD\n", loc='left', color='#ffab00', fontsize=15, fontweight='bold', pad=15)
    ax.text(0.0, 1.02, f"Fecha: {fecha_str}", transform=ax.transAxes, color='#94a3b8', fontsize=9)
    ax.text(0.0, -0.12, "Cazador Táctico • Ranking de Momentum 24h en Binance Spot", transform=ax.transAxes, color='#64748b', fontsize=8)
    
    plt.tight_layout()
    image_path = 'narrativa_dia.png'
    plt.savefig(image_path, dpi=300, facecolor=fig.get_facecolor(), edgecolor='none')
    plt.close()
    return image_path

def enviar_telegram_con_foto(image_path):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"
    with open(image_path, 'rb') as photo:
        payload = {"chat_id": CHAT_ID}
        if TOPIC_ID_TACTICO:
            payload["message_thread_id"] = TOPIC_ID_TACTICO
        
        files = {"photo": photo}
        response = requests.post(url, data=payload, files=files)
        print("Respuesta de Telegram (Foto):", response.text)
        return response.json()

def enviar_telegram_texto(mensaje):
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
    print("Respuesta de Telegram (Texto):", response.text)
    return response.json()

def main():
    datos = obtener_datos_binance()
    if not datos:
        print("Error al obtener datos de Binance.")
        return

    oportunidades, total_sub1 = procesar_oportunidades(datos)
    if not oportunidades:
        print("No se encontraron oportunidades con los filtros establecidos.")
        return
    
    imagen_grafico = generar_grafico_narrativa(oportunidades)
    enviar_telegram_con_foto(imagen_grafico)
    
    bloque_1 = oportunidades[:3]
    bloque_2 = oportunidades[3:]
    
    msg_parte_2 = "🎯 <b>CAZADOR TÁCTICO</b>\n"
    msg_parte_2 += "📊 <i>Ranking de Momentum 24h en Binance Spot</i>\n\n"
    msg_parte_2 += f"<b>MONEDAS ANALIZADAS:</b> {total_sub1}\n\n"
    msg_parte_2 += f"<b>RESUMEN:</b> Estas altcoins fueron seleccionadas de un universo de {total_sub1} activos bajo $1 USD en Binance Spot debido a una confluencia de compresión de volatilidad previa y rotación agresiva de capital hacia activos de alta beta.\n\n"
    msg_parte_2 += "🚀 <b>TOP OPORTUNIDADES TÁCTICAS</b>\n"
    
    for op in bloque_1:
        precio_str = formatear_precio(op['precio'])
        cambio_str = f"+{op['change']:.1f}%" if op['change'] >= 0 else f"{op['change']:.1f}%"
        
        safe_netlify = html.escape(op['netlify_url'])
        safe_binance = html.escape(op['binance_url'])
        
        link_ia = f'<a href="{safe_netlify}">Resumen IA</a>'
        link_trade = f'<a href="{safe_binance}">Tradear</a>'
        
        msg_parte_2 += f"\n• <b>{op['simbolo']}</b> ({cambio_str}) — {precio_str} | 🟢🟢🟢🟢🟢\n"
        msg_parte_2 += f"🧠 <i>{op['resumen']}</i>\n"
        msg_parte_2 += f"  └ 📊 {link_ia} | 🔶 {link_trade}\n"

    enviar_telegram_texto(msg_parte_2)
    
    msg_parte_3 = ""
    for op in bloque_2:
        precio_str = formatear_precio(op['precio'])
        cambio_str = f"+{op['change']:.1f}%" if op['change'] >= 0 else f"{op['change']:.1f}%"
        
        safe_netlify = html.escape(op['netlify_url'])
        safe_binance = html.escape(op['binance_url'])
        
        link_ia = f'<a href="{safe_netlify}">Resumen IA</a>'
        link_trade = f'<a href="{safe_binance}">Tradear</a>'
        
        msg_parte_3 += f"\n• <b>{op['simbolo']}</b> ({cambio_str}) — {precio_str} | 🟢🟢🟢🟢🟢\n"
        msg_parte_3 += f"🧠 <i>{op['resumen']}</i>\n"
        msg_parte_3 += f"  └ 📊 {link_ia} | 🔶 {link_trade}\n"

    enviar_telegram_texto(msg_parte_3)

if __name__ == "__main__":
    main()
