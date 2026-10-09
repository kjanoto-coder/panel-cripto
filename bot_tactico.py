import os
import re
import time
import requests
from datetime import datetime
from google import genai
from PIL import Image, ImageDraw, ImageFont

# Variables de entorno de GitHub Secrets
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.getenv("CHAT_ID", "").strip()
TELEGRAM_TOPIC_ID = os.getenv("TOPIC_ID_TACTICO", "").strip()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()

def configurar_ia():
    if not GEMINI_API_KEY:
        raise ValueError("Falta la clave GEMINI_API_KEY en los secretos de GitHub.")
    return genai.Client(api_key=GEMINI_API_KEY)

def obtener_mercado_binance():
    protocolo = "https"
    dominio = "data-api.binance.vision"
    url = f"{protocolo}://{dominio}/api/v3/ticker/24hr"
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

def filtrar_candidatos_bajo_valor(tickers):
    usdt_pairs = [
        t for t in tickers 
        if t['symbol'].endswith('USDT') and not any(x in t['symbol'] for x in ['UP', 'DOWN', 'BULL', 'BEAR'])
    ]
    tokens_bajo_valor = [t for t in usdt_pairs if float(t['lastPrice']) < 1.0]
    top_volumen = sorted(tokens_bajo_valor, key=lambda x: float(x['quoteVolume']), reverse=True)[:25]
    return top_volumen

def analizar_oportunidades_con_ia(client, mercado_resumen):
    prompt = f"""
    Actúa como un trader cuantitativo especializado en altcoins de baja capitalización.
    Aquí tienes el escaneo en tiempo real del Top 25 de criptomonedas (< $1 USD) en Binance Spot:
    
    {mercado_resumen}
    
    Selecciona las **3 o 4 mejores opciones** con mayor impulso técnico y ordénalas según su proyección.
    
    Genera un informe sintético para Telegram usando únicamente etiquetas HTML de Telegram (<b>texto</b>):
    
    - Resumen general del movimiento de hoy en 2 oraciones.
    - Para cada moneda seleccionada, incluye:
      • 🪙 <b>Símbolo:</b> [TICKER]
      • 💲 <b>Precio:</b> [Precio]
      • 🧠 <b>Veredicto IA:</b> [Breve justificación cuantitativa]
    """
    
    candidatos_dinamicos = []
    try:
        for m in client.models.list():
            nombre = getattr(m, 'name', str(m)).replace('models/', '')
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
                    return response.text
            except Exception:
                time.sleep(2)

    raise Exception("No se pudo obtener respuesta de la IA.")

def generar_imagen_infografia(seleccionados):
    """
    Genera una infografía estilo tarjeta gráfica (800x800) con las monedas
    ordenadas de menor a mayor porcentaje de cambio 24h.
    """
    # Ordenar estrictamente de menor a mayor porcentaje para la gráfica
    items_ordenados = sorted(seleccionados, key=lambda x: x['cambio'])
    
    width, height = 800, 800
    img = Image.new('RGB', (width, height), color='#0B131E')
    draw = ImageDraw.Draw(img)

    # Rejilla sutil de fondo
    grid_color = '#132235'
    for x in range(0, width, 40):
        draw.line([(x, 0), (x, height)], fill=grid_color, width=1)
    for y in range(0, height, 40):
        draw.line([(0, y), (width, y)], fill=grid_color, width=1)

    # Fuentes integradas por defecto
    try:
        font_title = ImageFont.truetype("DejaVuSans-Bold.ttf", 38)
        font_sub = ImageFont.truetype("DejaVuSans.ttf", 20)
        font_val = ImageFont.truetype("DejaVuSans-Bold.ttf", 24)
        font_symbol = ImageFont.truetype("DejaVuSans-Bold.ttf", 20)
        font_footer = ImageFont.truetype("DejaVuSans.ttf", 16)
    except Exception:
        font_title = ImageFont.load_default()
        font_sub = ImageFont.load_default()
        font_val = ImageFont.load_default()
        font_symbol = ImageFont.load_default()
        font_footer = ImageFont.load_default()

    # Título principal y fecha
    draw.text((50, 45), "Narrativa de Caza", fill="#FFC82C", font=font_title)
    draw.text((50, 95), "ALTCOINS SUB-$1 USD", fill="#38BDF8", font=font_title)
    fecha_str = f"📅 {datetime.now().strftime('%Y-%m-%d')}"
    draw.text((50, 150), fecha_str, fill="#94A3B8", font=font_sub)

    # Parámetros para dibujar las barras
    num_items = len(items_ordenados)
    chart_bottom = 680
    max_bar_height = 320
    
    # Calcular ancho dinámico según cantidad de elementos
    available_width = width - 100
    bar_width = min(110, int(available_width / (num_items * 1.6)))
    spacing = int((available_width - (num_items * bar_width)) / (num_items + 1))

    # Obtener valores máximos y mínimos para escalar barras
    min_val = max(0.1, min([x['cambio'] for x in items_ordenados]))
    max_val = max([x['cambio'] for x in items_ordenados])

    x_start = 50 + spacing
    for item in items_ordenados:
        pct = item['cambio']
        simbolo = item['simbolo']

        # Normalizar altura de barra de menor a mayor
        rel_height = (pct / max_val) if max_val > 0 else 0.5
        bar_h = int(max_bar_height * max(0.2, rel_height))
        
        y_top = chart_bottom - bar_h
        x_left = x_start
        x_right = x_start + bar_width

        # Dibujar barra con tono cian/verde
        draw.rounded_rectangle([x_left, y_top, x_right, chart_bottom], radius=10, fill="#10B981")

        # Texto del Símbolo dentro de la barra
        draw.text((x_left + (bar_width // 2) - 18, chart_bottom - 45), simbolo[:4], fill="#0F172A", font=font_symbol)

        # Badge circular superior para el porcentaje
        badge_y = y_top - 55
        badge_center = x_left + (bar_width // 2)
        draw.ellipse([badge_center - 32, badge_y - 32, badge_center + 32, badge_y + 32], fill="#0B131E", outline="#34D399", width=3)
        draw.text((badge_center - 18, badge_y - 10), simbolo[:2], fill="#FFFFFF", font=font_symbol)

        # Porcentaje sobre el badge
        val_str = f"+{pct:.1f}%" if pct >= 0 else f"{pct:.1f}%"
        draw.text((badge_center - 30, badge_y - 65), val_str, fill="#34D399", font=font_val)

        x_start += bar_width + spacing

    # Pie de foto informativo
    footer_text = "Cazador Táctico • Filtro por Volumen 24h & Momentum Spot"
    draw.text((50, 735), footer_text, fill="#64748B", font=font_footer)

    path_output = "infografia_tactica.png"
    img.save(path_output)
    return path_output

def enviar_a_telegram_con_foto_y_botones(path_imagen, analisis_ia, seleccionados):
    token_limpio = re.sub(r'[^a-zA-Z0-9:\-_]', '', TELEGRAM_BOT_TOKEN)
    chat_id_limpio = re.sub(r'[^0-9\-]', '', TELEGRAM_CHAT_ID)
    topic_id_limpio = re.sub(r'[^0-9]', '', TELEGRAM_TOPIC_ID)
    
    protocolo = "https"
    dominio = "api.telegram.org"
    url = f"{protocolo}://{dominio}/bot{token_limpio}/sendPhoto"

    # Construir botones interactivos (Inline Keyboard) debajo de la imagen
    inline_keyboard = []
    
    # Botones individuales de acceso rápido a Binance para cada moneda destacada
    for item in seleccionados[:4]:
        sim = item['simbolo']
        link_binance = item['url']
        inline_keyboard.append([
            {"text": f"🚀 Trade {sim} en Binance", "url": link_binance}
        ])

    payload_data = {
        "chat_id": chat_id_limpio,
        "caption": f"🎯 <b>CAZADOR TÁCTICO - ANÁLISIS DE MERCADO</b>\n\n{analisis_ia}",
        "parse_mode": "HTML",
        "reply_markup": re.sub(r'\s+', '', str(inline_keyboard).replace("'", '"'))
    }

    # Estructura del Inline Keyboard compatible con la API de Telegram
    keyboard_structure = {
        "inline_keyboard": inline_keyboard
    }

    data = {
        "chat_id": chat_id_limpio,
        "caption": f"🎯 <b>CAZADOR TÁCTICO - RADAR DE OPORTUNIDADES</b>\n\n{analisis_ia}",
        "parse_mode": "HTML",
        "reply_markup": requests.compat.json.dumps(keyboard_structure)
    }

    if topic_id_limpio:
        data["message_thread_id"] = int(topic_id_limpio)

    with open(path_imagen, 'rb') as photo_file:
        files = {'photo': photo_file}
        response = requests.post(url, data=data, files=files)

    if response.status_code != 200:
        print(f"Error al enviar imagen a Telegram ({response.text}). Reintentando en texto plano...")
        # Fallback de seguridad en caso de error
        url_text = f"{protocolo}://{dominio}/bot{token_limpio}/sendMessage"
        data_text = {
            "chat_id": chat_id_limpio,
            "text": f"🎯 <b>CAZADOR TÁCTICO</b>\n\n{analisis_ia}",
            "parse_mode": "HTML",
            "disable_web_page_preview": True
        }
        if topic_id_limpio:
            data_text["message_thread_id"] = int(topic_id_limpio)
        requests.post(url_text, json=data_text)
    else:
        print("¡Infografía y botones interactivos publicados con éxito en Telegram!")

if __name__ == "__main__":
    print("Iniciando Cazador Táctico con Infografía Dinámica...")
    client = configurar_ia()
    
    tickers = obtener_mercado_binance()
    if tickers:
        candidatos = filtrar_candidatos_bajo_valor(tickers)
        
        # Tomar el top para el análisis y la imagen
        datos_formateados = []
        resumen_texto_ia = []
        
        for item in candidatos:
            sim = item['symbol'].replace('USDT', '')
            precio = float(item['lastPrice'])
            cambio = float(item['priceChangePercent'])
            volumen = float(item['quoteVolume'])
            binance_url = f"https://www.binance.com/es/trade/{sim}_USDT?type=spot"
            
            objeto_moneda = {
                'simbolo': sim,
                'precio': precio,
                'cambio': cambio,
                'volumen': volumen,
                'url': binance_url
            }
            datos_formateados.append(objeto_moneda)
            resumen_texto_ia.append(
                f"Moneda: {sim} | Precio: {formatear_precio(precio)} | Cambio 24h: {cambio:+.2f}% | Vol USDT: {volumen:,.0f}"
            )
        
        # 1. Obtener análisis resumido con la IA
        analisis_ia = analizar_oportunidades_con_ia(client, "\n".join(resumen_texto_ia[:15]))
        
        # 2. Seleccionar de 3 a 5 monedas destacadas
        monedas_destacadas = sorted(datos_formateados, key=lambda x: x['volumen'], reverse=True)[:4]
        
        # 3. Generar la imagen infográfica (barras ordenadas de menor a mayor)
        path_imagen = generar_imagen_infografia(monedas_destacadas)
        
        # 4. Enviar a Telegram con la foto y los botones interactivos
        enviar_a_telegram_con_foto_y_botones(path_imagen, analisis_ia, monedas_destacadas)
    else:
        print("No se pudieron obtener datos del mercado.")
