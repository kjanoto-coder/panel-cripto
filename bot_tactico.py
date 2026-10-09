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

def seleccionar_top4_oportunidades(tickers):
    # 1. Filtrar pares USDT (< $1.00 USD)
    usdt_pairs = [
        t for t in tickers 
        if t['symbol'].endswith('USDT') and not any(x in t['symbol'] for x in ['UP', 'DOWN', 'BULL', 'BEAR'])
    ]
    tokens_bajo_valor = [t for t in usdt_pairs if float(t['lastPrice']) < 1.0]
    
    # 2. Filtrar por volumen alto de liquidez (Top 15 por volumen)
    top_liquidez = sorted(tokens_bajo_valor, key=lambda x: float(x['quoteVolume']), reverse=True)[:15]
    
    # 3. De esas 15, tomar las 4 con mayor ganancia % en 24h
    top_4_ganadoras = sorted(top_liquidez, key=lambda x: float(x['priceChangePercent']), reverse=True)[:4]
    
    resultado = []
    for item in top_4_ganadoras:
        sim = item['symbol'].replace('USDT', '')
        precio = float(item['lastPrice'])
        cambio = float(item['priceChangePercent'])
        volumen = float(item['quoteVolume'])
        binance_url = f"https://www.binance.com/es/trade/{sim}_USDT?type=spot"
        
        resultado.append({
            'simbolo': sim,
            'precio': precio,
            'cambio': cambio,
            'volumen': volumen,
            'url': binance_url
        })
    
    # 4. Ordenar de menor a mayor % para la barra del gráfico
    resultado_ordenado = sorted(resultado, key=lambda x: x['cambio'])
    return resultado_ordenado

def analizar_monedas_exactas_con_ia(client, monedas):
    lista_texto = []
    for m in monedas:
        lista_texto.append(
            f"Moneda: {m['simbolo']} | Precio: {formatear_precio(m['precio'])} | Cambio 24h: {m['cambio']:+.2f}% | Vol USDT: {m['volumen']:,.0f}"
        )
    
    prompt = f"""
    Eres un analista cuantitativo de criptomonedas.
    Analiza ÚNICAMENTE estas 4 monedas seleccionadas de bajo valor (< $1 USD):

    {chr(10).join(lista_texto)}

    Genera un informe SÚPER CONCISO y LIMPIO para Telegram.
    Sigue ESTRICTAMENTE este formato sin añadir introducciones ni textos largos:

    <b>RESUMEN:</b> [1 sola frase corta sobre la tendencia general de la sesión]

    """
    for m in monedas:
        prompt += f"""• <b>{m['simbolo']}</b> ({m['cambio']:+.1f}%) — {formatear_precio(m['precio'])}
🧠 <i>[1 sola frase corta de veredicto técnico]</i>\n\n"""

    prompt += "\nReglas: No uses bloques markdown. Usa únicamente etiquetas <b> y <i> de HTML. Sé muy directo y breve."

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
                    return response.text
            except Exception:
                time.sleep(2)

    raise Exception("No se pudo obtener respuesta de la IA.")

def generar_imagen_infografia(items_ordenados):
    width, height = 800, 800
    img = Image.new('RGB', (width, height), color='#0F172A')
    draw = ImageDraw.Draw(img)

    # Rejilla
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

    # Encabezado
    draw.text((50, 40), "NARRATIVA DEL DÍA", fill="#F59E0B", font=font_title)
    draw.text((50, 85), "ALTCOINS SUB-$1 USD", fill="#38BDF8", font=font_sub)
    fecha_str = f"📅 {datetime.now().strftime('%Y-%m-%d')}"
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

        # Barra
        draw.rounded_rectangle([x_left, y_top, x_right, chart_bottom], radius=12, fill=color_barra)

        # Texto del símbolo abajo en la barra
        draw.text((x_left + 15, chart_bottom - 35), simbolo[:5], fill="#0F172A", font=font_symbol)

        # Badge circular superior
        badge_y = y_top - 45
        badge_center = x_left + (bar_width // 2)
        draw.ellipse([badge_center - 25, badge_y - 25, badge_center + 25, badge_y + 25], fill="#1E293B", outline=color_barra, width=2)
        
        txt_sim = simbolo[:3]
        draw.text((badge_center - 14, badge_y - 8), txt_sim, fill="#FFFFFF", font=font_symbol)

        # Porcentaje sobre el badge
        val_str = f"+{pct:.1f}%" if pct >= 0 else f"{pct:.1f}%"
        draw.text((badge_center - 26, badge_y - 55), val_str, fill=color_texto_val, font=font_val)

        x_start += bar_width + spacing

    footer_text = "Cazador Táctico • Ranking de Momentum 24h en Binance Spot"
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

def enviar_a_telegram_con_foto_y_botones(path_imagen, analisis_ia, monedas):
    token_limpio = re.sub(r'[^a-zA-Z0-9:\-_]', '', TELEGRAM_BOT_TOKEN)
    chat_id_limpio = re.sub(r'[^0-9\-]', '', TELEGRAM_CHAT_ID)
    topic_id_limpio = re.sub(r'[^0-9]', '', TELEGRAM_TOPIC_ID)
    
    protocolo = "https"
    dominio = "api.telegram.org"
    url = f"{protocolo}://{dominio}/bot{token_limpio}/sendPhoto"

    analisis_limpio = limpiar_texto_telegram(analisis_ia)
    caption_texto = f"🎯 <b>CAZADOR TÁCTICO</b>\n\n{analisis_limpio}"

    if len(caption_texto) > 1000:
        caption_texto = caption_texto[:995] + "..."

    # Botones ordenados de 2 en 2 por fila
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

    keyboard_structure = {
        "inline_keyboard": inline_keyboard
    }

    data = {
        "chat_id": chat_id_limpio,
        "caption": caption_texto,
        "parse_mode": "HTML",
        "reply_markup": json.dumps(keyboard_structure)
    }

    if topic_id_limpio:
        try:
            data["message_thread_id"] = int(topic_id_limpio)
        except ValueError:
            data["message_thread_id"] = topic_id_limpio

    with open(path_imagen, 'rb') as photo_file:
        files = {'photo': photo_file}
        response = requests.post(url, data=data, files=files)

    if response.status_code != 200:
        print(f"Error al enviar foto: {response.text}")
        data.pop("parse_mode", None)
        data["caption"] = caption_texto.replace("<b>", "").replace("</b>", "").replace("<i>", "").replace("</i>", "")
        with open(path_imagen, 'rb') as photo_file:
            files = {'photo': photo_file}
            requests.post(url, data=data, files=files)
    else:
        print("¡Infografía sincronizada enviada a Telegram con éxito!")

if __name__ == "__main__":
    print("Iniciando Cazador Táctico (100% Sincronizado)...")
    client = configurar_ia()
    
    tickers = obtener_mercado_binance()
    if tickers:
        monedas_seleccionadas = seleccionar_top4_oportunidades(tickers)
        analisis_ia = analizar_monedas_exactas_con_ia(client, monedas_seleccionadas)
        path_imagen = generar_imagen_infografia(monedas_seleccionadas)
        enviar_a_telegram_con_foto_y_botones(path_imagen, analisis_ia, monedas_seleccionadas)
    else:
        print("No se pudieron obtener datos del mercado.")
