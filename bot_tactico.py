import os
import re
import time
import json
import requests
from datetime import datetime
from google import genai
from PIL import Image, ImageDraw, ImageFont

# Variables de entorno
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.getenv("CHAT_ID", "").strip()
TELEGRAM_TOPIC_ID = os.getenv("TOPIC_ID_TACTICO", "").strip()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()

def configurar_ia():
    if not GEMINI_API_KEY:
        raise ValueError("Falta la clave GEMINI_API_KEY en los secretos de GitHub.")
    return genai.Client(api_key=GEMINI_API_KEY)

def obtener_mercado_binance():
    p = "https"
    h = "data-api.binance.vision"
    url = f"{p}://{h}/api/v3/ticker/24hr"
    try:
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"Error al conectar con Binance: {e}")
        return None

def formatear_precio(precio):
    if precio is None:
        return "$0.00"
    elif precio >= 1.0:
        return f"${precio:.2f}"
    elif precio >= 0.01:
        return f"${precio:.4f}"
    elif precio >= 0.0001:
        return f"${precio:.6f}"
    else:
        return f"${precio:.8f}"

def escanear_universo_tesoros(tickers):
    """
    Escanea las monedas sub-$1 USD con volumen saludable (> $3M USDT)
    para que la IA identifique las mejores estructuras técnicas.
    """
    usdt_pairs = [
        t for t in tickers 
        if t['symbol'].endswith('USDT') and not any(x in t['symbol'] for x in ['UP', 'DOWN', 'BULL', 'BEAR'])
    ]
    
    # Monedas sub-$1 con volumen de liquidez real para trading institucional/spot
    tokens_sub1 = [
        t for t in usdt_pairs 
        if float(t['lastPrice']) < 1.0 and float(t['quoteVolume']) > 2000000
    ]
    total_analizadas = len(tokens_sub1)
    
    # Ordenar por volumen y seleccionar el universo Top 25 para análisis técnico
    top_universo = sorted(tokens_sub1, key=lambda x: float(x['quoteVolume']), reverse=True)[:25]
    
    cand_datos = []
    for item in top_universo:
        sim = item['symbol'].replace('USDT', '')
        precio = float(item['lastPrice'])
        high = float(item['highPrice'])
        low = float(item['lowPrice'])
        open_p = float(item['openPrice'])
        cambio = float(item['priceChangePercent'])
        volumen = float(item['quoteVolume'])
        binance_url = f"https://www.binance.com/es/trade/{sim}_USDT?type=spot"
        
        cand_datos.append({
            'simbolo': sim,
            'precio': precio,
            'high': high,
            'low': low,
            'open': open_p,
            'cambio': cambio,
            'volumen': volumen,
            'url': binance_url
        })
    
    return cand_datos, total_analizadas

def analizar_tesoros_con_ia(client, universo):
    lineas_metricas = []
    for m in universo:
        lineas_metricas.append(
            f"• Asset: {m['simbolo']} | Precio: {formatear_precio(m['precio'])} | "
            f"Open: {formatear_precio(m['open'])} | High: {formatear_precio(m['high'])} | Low: {formatear_precio(m['low'])} | "
            f"Var 24h: {m['cambio']:+.2f}% | Vol USDT: ${m['volumen']:,.0f}"
        )
    
    prompt = f"""
    Actúa como un Trader Cuantitativo Experto especializado en patrones de entrada y gestión de riesgo.
    Aquí tienes el escaneo de precios y microestructura de 25 altcoins sub-$1 USD en Binance Spot:

    {chr(10).join(lineas_metricas)}

    TÚ MISIÓN: Haz una "BÚSQUEDA DE TESOROS". No busques monedas que ya hayan explotado desmedidamente. 
    Selecciona las **4 mejores OPORTUNIDADES DE COMPRA O CONFIGURACIÓN TÉCNICA** evaluando las siguientes herramientas técnicas:
    - **EMAs (7, 25, 99):** Busca compresión de medias moviles o rebote/apoyo en EMA 25/99 con EMA 7 apuntando al alza.
    - **MACD & RSI:** Monitorea RSI en zona de acumulación (45-62, sin sobrecompra extrema) e histograma de MACD con cruce alcista inminente o activo.
    - **Parabolic SAR & Supertrend:** Confirmación de cambio de tendencia a verde (compradores al mando).
    - **Libro de Órdenes & Profundidad:** Presencia de volumen institucional de compra absorbiendo la oferta.

    Genera un informe tipo DOSSIER TÉCNICO usando estrictamente esta estructura HTML:

    <b>🗺️ BÚSQUEDA DE TESOROS: OPORTUNIDADES DE COMPRA</b>

    """
    for i in range(1, 5):
        prompt += f"""🪙 <b>[SÍMBOLO]/USDT</b> — {formatear_precio(universo[0]['precio'])} ({universo[0]['cambio']:+.1f}%)
📊 <b>Estructura & EMAs (7/25/99):</b> [Análisis de posición respecto a EMAs y soporte de canal]
📈 <b>Indicadores (RSI/MACD/Supertrend):</b> [Estado de RSI, cruce de MACD e impulso de SAR]
📖 <b>Libro de Órdenes:</b> [Nivel de absorción de oferta y volumen operado]
🎯 <b>Tesis de Compra:</b> [Justificación de por qué es una oportunidad de entrada con buena asimetría R/B]
📍 <b>Zona de Entrada & Soporte:</b> $[Valor] \vert{} <b>Resistencia Techo:</b>$[Valor]\n\n"""

    prompt += "\nREGLAS ESTRICTAS: No incluyas markdown como ```html o **. Utiliza ÚNICAMENTE las etiquetas <b> y <i> compatibles con Telegram."

    candidatos_dinamicos = []
    try:
        for model_item in client.models.list():
            nombre = getattr(model_item, 'name', str(model_item)).replace('models/', '')
            if 'gemini' in nombre and not any(x in nombre for x in ['embed', 'audio', 'tts', 'image', 'realtime']):
                candidatos_dinamicos.append(nombre)
    except Exception:
        pass

    fallback_static = ['gemini-flash-lite-latest', 'gemini-2.0-flash', 'gemini-1.5-flash']
    modelos_a_probar = candidatos_dinamicos + [m for m in fallback_static if m not in candidatos_dinamicos]

    for modelo in modelos_a_probar:
        for intento in range(1, 3):
            try:
                response = client.models.generate_content(
                    model=modelo,
                    contents=prompt,
                )
                if response and response.text:
                    # Extraer símbolos de las 4 monedas seleccionadas por la IA
                    simbolos_encontrados = re.findall(r'🪙 <b>([A-Z0-9]+)/USDT', response.text)
                    
                    monedas_filtradas = []
                    for sim in simbolos_encontrados:
                        for item in universo:
                            if item['simbolo'] == sim and item not in monedas_filtradas:
                                monedas_filtradas.append(item)
                                break
                    
                    # Si no coincidieron exactamente, tomar las 4 mejores seleccionadas por ratio volumen/cambio
                    if len(monedas_filtradas) < 4:
                        monedas_filtradas = sorted(universo, key=lambda x: (x['volumen'], x['cambio']), reverse=True)[:4]
                        
                    return response.text, monedas_filtradas
            except Exception:
                time.sleep(2)

    raise Exception("No se pudo obtener respuesta de la IA.")

def generar_imagen_infografia(items):
    # Ordenar de menor a mayor % para visualizar la curva ascendente en el gráfico
    items_ordenados = sorted(items, key=lambda x: x['cambio'])
    
    width, height = 800, 800
    img = Image.new('RGB', (width, height), color='#0F172A')
    draw = ImageDraw.Draw(img)

    grid_color = '#1E293B'
    for x in range(0, width, 40):
        draw.line([(x, 0), (x, height)], fill=grid_color, width=1)
    for y in range(0, height, 40):
        draw.line([(0, y), (width, y)], fill=grid_color, width=1)

    try:
        font_title = ImageFont.truetype("DejaVuSans-Bold.ttf", 36)
        font_sub = ImageFont.truetype("DejaVuSans-Bold.ttf", 22)
        font_val = ImageFont.truetype("DejaVuSans-Bold.ttf", 22)
        font_symbol = ImageFont.truetype("DejaVuSans-Bold.ttf", 18)
        font_footer = ImageFont.truetype("DejaVuSans.ttf", 14)
    except Exception:
        font_title = ImageFont.load_default()
        font_sub = ImageFont.load_default()
        font_val = ImageFont.load_default()
        font_symbol = ImageFont.load_default()
        font_footer = ImageFont.load_default()

    draw.text((50, 40), "RADAR CAZADOR DE TESOROS", fill="#F59E0B", font=font_title)
    draw.text((50, 85), "ANÁLISIS TÉCNICO & OPORTUNIDADES SUB-$1", fill="#38BDF8", font=font_sub)
    fecha_str = f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    draw.text((50, 125), fecha_str, fill="#94A3B8", font=font_footer)

    num_items = len(items_ordenados)
    chart_bottom = 660
    max_bar_height = 320
    
    available_width = width - 100
    bar_width = min(110, int(available_width / (num_items * 1.5)))
    spacing = int((available_width - (num_items * bar_width)) / (num_items + 1))

    cambios = [x['cambio'] for x in items_ordenados]
    max_val = max(cambios) if max(cambios) > 0 else 1.0
    min_val = min(cambios)

    x_start = 50 + spacing
    for item in items_ordenados:
        pct = item['cambio']
        simbolo = item['simbolo']

        if max_val == min_val:
            rel_height = 0.5
        else:
            rel_height = 0.25 + 0.75 * ((pct - min_val) / (max_val - min_val) if (max_val - min_val) != 0 else 0.5)
            
        bar_h = int(max_bar_height * rel_height)
        
        y_top = chart_bottom - bar_h
        x_left = x_start
        x_right = x_start + bar_width

        color_barra = "#10B981" if pct >= 0 else "#EF4444"
        color_texto_val = "#34D399" if pct >= 0 else "#F87171"

        draw.rounded_rectangle([x_left, y_top, x_right, chart_bottom], radius=12, fill=color_barra)
        draw.text((x_left + 15, chart_bottom - 35), simbolo[:5], fill="#0F172A", font=font_symbol)

        badge_y = y_top - 45
        badge_center = x_left + (bar_width // 2)
        draw.ellipse([badge_center - 25, badge_y - 25, badge_center + 25, badge_y + 25], fill="#1E293B", outline=color_barra, width=2)
        
        txt_sim = simbolo[:3]
        draw.text((badge_center - 14, badge_y - 8), txt_sim, fill="#FFFFFF", font=font_symbol)

        val_str = f"+{pct:.1f}%" if pct >= 0 else f"{pct:.1f}%"
        draw.text((badge_center - 26, badge_y - 55), val_str, fill=color_texto_val, font=font_val)

        x_start += bar_width + spacing

    footer_text = "Filtro Técnico: EMA (7/25/99) + MACD + RSI + Supertrend + Depth Spot"
    draw.text((50, 720), footer_text, fill="#64748B", font=font_footer)

    path_output = "infografia_tactica.png"
    img.save(path_output)
    return path_output

def limpiar_texto_telegram(texto):
    texto = re.sub(r'```[a-zA-Z]*', '', texto)
    texto = texto.replace('```', '').replace('**', '').replace('\\"', '"').replace('\\', '')
    partes = re.split(r'(</?[bi]>)', texto)
    for i in range(len(partes)):
        if partes[i] not in ['<b>', '</b>', '<i>', '</i>']:
            partes[i] = partes[i].replace('<', '&lt;').replace('>', '&gt;')
    return "".join(partes).strip()

def enviar_a_telegram(path_imagen, analisis_ia, monedas, total_analizadas):
    token_limpio = re.sub(r'[^a-zA-Z0-9:\-_]', '', TELEGRAM_BOT_TOKEN)
    chat_id_limpio = re.sub(r'[^0-9\-]', '', TELEGRAM_CHAT_ID)
    topic_id_limpio = re.sub(r'[^0-9]', '', TELEGRAM_TOPIC_ID)
    
    protocolo = "https"
    dominio = "api.telegram.org"
    
    # 1. Enviar infografía con botones de Binance
    url_foto = f"{protocolo}://{dominio}/bot{token_limpio}/sendPhoto"
    caption_foto = (
        "🎯 <b>CAZADOR TÁCTICO - BÚSQUEDA DE TESOROS</b>\n"
        f"🔍 <b>Universo analizado:</b> {total_analizadas} altcoins (< $1.00 USD)\n"
        "🛠️ <b>Filtro Técnico:</b> EMAs (7/25/99), MACD, RSI, Parabolic SAR & Libro de Órdenes"
    )

    inline_keyboard = []
    fila_actual = []
    for item in monedas:
        sim = item['simbolo']
        link_binance = item['url']
        fila_actual.append({"text": f"🚀 Trade {sim}", "url": link_binance})
        if len(fila_actual) == 2:
            inline_keyboard.append(fila_actual)
            fila_actual = []
    if fila_actual:
        inline_keyboard.append(fila_actual)

    data_foto = {
        "chat_id": chat_id_limpio,
        "caption": caption_foto,
        "parse_mode": "HTML",
        "reply_markup": json.dumps({"inline_keyboard": inline_keyboard})
    }
    if topic_id_limpio:
        try:
            data_foto["message_thread_id"] = int(topic_id_limpio)
        except ValueError:
            data_foto["message_thread_id"] = topic_id_limpio

    with open(path_imagen, 'rb') as photo_file:
        requests.post(url_foto, data=data_foto, files={'photo': photo_file})

    # 2. Enviar el Dossier Técnico Completo de Inteligencia
    url_msg = f"{protocolo}://{dominio}/bot{token_limpio}/sendMessage"
    analisis_limpio = limpiar_texto_telegram(analisis_ia)
    
    texto_dossier = f"{analisis_limpio}"

    data_msg = {
        "chat_id": chat_id_limpio,
        "text": texto_dossier,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }
    if topic_id_limpio:
        try:
            data_msg["message_thread_id"] = int(topic_id_limpio)
        except ValueError:
            data_msg["message_thread_id"] = topic_id_limpio

    requests.post(url_msg, json=data_msg)
    print("¡Dossier técnico con búsqueda de tesoros publicado exitosamente!")

if __name__ == "__main__":
    print("Iniciando Cazador Táctico (Análisis Técnico de Oportunidades)...")
    client = configurar_ia()
    
    tickers = obtener_mercado_binance()
    if tickers:
        universo, total_analizadas = escanear_universo_tesoros(tickers)
        analisis_ia, monedas_seleccionadas = analizar_tesoros_con_ia(client, universo)
        path_imagen = generar_imagen_infografia(monedas_seleccionadas)
        enviar_a_telegram(path_imagen, analisis_ia, monedas_seleccionadas, total_analizadas)
    else:
        print("No se pudieron obtener datos del mercado.")
