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

def seleccionar_top5_oportunidades(tickers):
    usdt_pairs = [
        t for t in tickers 
        if t['symbol'].endswith('USDT') and not any(x in t['symbol'] for x in ['UP', 'DOWN', 'BULL', 'BEAR'])
    ]
    tokens_bajo_valor = [t for t in usdt_pairs if float(t['lastPrice']) < 1.0]
    total_analizadas = len(tokens_bajo_valor)
    
    top_liquidez = sorted(tokens_bajo_valor, key=lambda x: float(x['quoteVolume']), reverse=True)[:35]
    top_5_ganadoras = sorted(top_liquidez, key=lambda x: float(x['priceChangePercent']), reverse=True)[:5]
    
    resultado = []
    for item in top_5_ganadoras:
        sim = item['symbol'].replace('USDT', '')
        precio = float(item['lastPrice'])
        cambio = float(item['priceChangePercent'])
        volumen = float(item['quoteVolume'])
        
        binance_url = f"https://www.binance.com/es/trade/{sim}_USDT?type=spot"
        netlify_url = f"https://gregarious-frangollo-0346c5.netlify.app/?coin={sim}&price={precio}&change={cambio}"
        
        resultado.append({
            'simbolo': sim,
            'precio': precio,
            'cambio': cambio,
            'volumen': volumen,
            'binance_url': binance_url,
            'netlify_url': netlify_url
        })
    
    # Ordenar de menor a mayor % para el gráfico infográfico de barras
    resultado_grafico = sorted(resultado, key=lambda x: x['cambio'])
    return resultado_grafico, total_analizadas

def analizar_top5_con_ia(client, monedas, total_analizadas):
    lista_texto = []
    for m in monedas:
        lista_texto.append(
            f"- {m['simbolo']} (Precio: {formatear_precio(m['precio'])}, Cambio: {m['cambio']:+.2f}%, Vol USDT: ${m['volumen']:,.0f})"
        )
    
    prompt = (
        f"Actúa como un Trader Cuantitativo Senior.\n"
        f"Se escanearon un total de {total_analizadas} altcoins sub-$1 USD en Binance Spot.\n"
        f"Tras filtrar por liquidez y rendimiento en 24h, estas son las 5 ganadoras seleccionadas:\n"
        f"{chr(10).join(lista_texto)}\n\n"
        "Devuelve la respuesta estrictamente en este formato de texto plano:\n"
        f"RESUMEN: [Explica claramente por qué se seleccionaron estas 5 de entre las {total_analizadas} monedas analizadas, detallando la narrativa de mercado o el criterio cuantitativo que las destaca y por qué no son al azar]\n"
        f"1. {monedas[0]['simbolo']}: [Frase corta de análisis técnico]\n"
        f"2. {monedas[1]['simbolo']}: [Frase corta de análisis técnico]\n"
        f"3. {monedas[2]['simbolo']}: [Frase corta de análisis técnico]\n"
        f"4. {monedas[3]['simbolo']}: [Frase corta de análisis técnico]\n"
        f"5. {monedas[4]['simbolo']}: [Frase corta de análisis técnico]\n"
    )

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

    grid_color = '#1E293B'
    for x in range(0, width, 40):
        draw.line([(x, 0), (x, height)], fill=grid_color, width=1)
    for y in range(0, height, 40):
        draw.line([(0, y), (width, y)], fill=grid_color, width=1)

    try:
        font_title = ImageFont.truetype("DejaVuSans-Bold.ttf", 36)
        font_sub = ImageFont.truetype("DejaVuSans-Bold.ttf", 22)
        font_val = ImageFont.truetype("DejaVuSans-Bold.ttf", 20)
        font_symbol = ImageFont.truetype("DejaVuSans-Bold.ttf", 16)
        font_footer = ImageFont.truetype("DejaVuSans.ttf", 14)
    except Exception:
        font_title = ImageFont.load_default()
        font_sub = ImageFont.load_default()
        font_val = ImageFont.load_default()
        font_symbol = ImageFont.load_default()
        font_footer = ImageFont.load_default()

    draw.text((50, 40), "NARRATIVA DEL DÍA", fill="#F59E0B", font=font_title)
    draw.text((50, 85), "TOP 5 ALTCOINS SUB-$1 USD", fill="#38BDF8", font=font_sub)
    fecha_str = f"📅 {datetime.now().strftime('%Y-%m-%d')}"
    draw.text((50, 125), fecha_str, fill="#94A3B8", font=font_footer)

    num_items = len(items_ordenados)
    chart_bottom = 660
    max_bar_height = 320
    
    available_width = width - 100
    bar_width = min(95, int(available_width / (num_items * 1.4)))
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

        draw.rounded_rectangle([x_left, y_top, x_right, chart_bottom], radius=10, fill=color_barra)
        draw.text((x_left + 8, chart_bottom - 32), simbolo[:5], fill="#0F172A", font=font_symbol)

        badge_y = y_top - 45
        badge_center = x_left + (bar_width // 2)
        draw.ellipse([badge_center - 25, badge_y - 25, badge_center + 25, badge_y + 25], fill="#1E293B", outline=color_barra, width=2)
        
        txt_sim = simbolo[:3]
        draw.text((badge_center - 14, badge_y - 8), txt_sim, fill="#FFFFFF", font=font_symbol)

        val_str = f"+{pct:.1f}%" if pct >= 0 else f"{pct:.1f}%"
        draw.text((badge_center - 26, badge_y - 55), val_str, fill=color_texto_val, font=font_val)

        x_start += bar_width + spacing

    footer_text = "Cazador Táctico • Ranking de Momentum 24h en Binance Spot"
    draw.text((50, 720), footer_text, fill="#64748B", font=font_footer)

    path_output = "infografia_tactica.png"
    img.save(path_output)
    return path_output

def enviar_a_telegram(path_imagen, texto_ia, monedas, total_analizadas):
    token_limpio = re.sub(r'[^a-zA-Z0-9:\-_]', '', TELEGRAM_BOT_TOKEN)
    chat_id_limpio = re.sub(r'[^0-9\-]', '', TELEGRAM_CHAT_ID)
    topic_id_limpio = re.sub(r'[^0-9]', '', TELEGRAM_TOPIC_ID)
    
    protocolo = "https"
    dominio = "api.telegram.org"
    
    # 1. Enviar la imagen sola con título limpio
    url_foto = f"{protocolo}://{dominio}/bot{token_limpio}/sendPhoto"
    data_foto = {
        "chat_id": chat_id_limpio,
        "caption": "🎯 <b>CAZADOR TÁCTICO</b>\n📊 <i>Ranking de Momentum 24h en Binance Spot</i>",
        "parse_mode": "HTML"
    }
    if topic_id_limpio:
        try:
            data_foto["message_thread_id"] = int(topic_id_limpio)
        except ValueError:
            data_foto["message_thread_id"] = topic_id_limpio

    with open(path_imagen, 'rb') as photo_file:
        requests.post(url_foto, data=data_foto, files={'photo': photo_file})

    # 2. Extraer resumen cuantitativo y análisis por moneda
    resumen_global = f"Selección optimizada de las mejores oportunidades tras filtrar {total_analizadas} activos por volumen y aceleración de momentum."
    match_resumen = re.search(r'RESUMEN:\s*(.*)', texto_ia)
    if match_resumen:
        resumen_global = match_resumen.group(1).strip()
    
    analisis_dict = {}
    for m in monedas:
        sim = m['simbolo']
        match_moneda = re.search(rf'(?:\d+\.|\-)?\s*{sim}:\s*(.*)', texto_ia, re.IGNORECASE)
        if match_moneda:
            analisis_dict[sim] = match_moneda.group(1).strip()
        else:
            analisis_dict[sim] = "Ruptura limpia con expansión de volumen y acumulación en intradiario."

    bloques_monedas = []
    for m in monedas:
        sim = m['simbolo']
        frase = analisis_dict.get(sim, "Impulso alcista sostenido con volumen favorable.")
        
        bloque = (
            f"• <b>{sim}</b> ({m['cambio']:+.1f}%) — {formatear_precio(m['precio'])} | 🟢🟢🟢🟢🟢\n"
            f"🧠 <i>{frase}</i>\n"
            f"└ 📊 <a href=\"{m['netlify_url']}\">Resumen IA</a> | 🔶 <a href=\"{m['binance_url']}\">Tradear</a>"
        )
        bloques_monedas.append(bloque)

    texto_detallado = (
        f"<b>MONEDAS ANALIZADAS:</b> {total_analizadas}\n\n"
        f"<b>RESUMEN:</b> {resumen_global}\n\n" +
        "\n\n".join(bloques_monedas)
    )

    # 3. Enviar mensaje detallado con enlaces interactivos funcionales
    url_msg = f"{protocolo}://{dominio}/bot{token_limpio}/sendMessage"
    data_msg = {
        "chat_id": chat_id_limpio,
        "text": texto_detallado,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }
    if topic_id_limpio:
        try:
            data_msg["message_thread_id"] = int(topic_id_limpio)
        except ValueError:
            data_msg["message_thread_id"] = topic_id_limpio

    requests.post(url_msg, json=data_msg)
    print("¡Publicación enviada con éxito!")

if __name__ == "__main__":
    print("Iniciando Cazador Táctico...")
    client = configurar_ia()
    
    tickers = obtener_mercado_binance()
    if tickers:
        monedas_grafico, total_analizadas = seleccionar_top5_oportunidades(tickers)
        texto_ia = analizar_top5_con_ia(client, monedas_grafico, total_analizadas)
        path_imagen = generar_imagen_infografia(monedas_grafico)
        enviar_a_telegram(path_imagen, texto_ia, monedas_grafico, total_analizadas)
    else:
        print("No se pudieron obtener datos del mercado.")
