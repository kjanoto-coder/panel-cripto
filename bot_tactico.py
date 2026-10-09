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

def analizar_top5_con_ia(client, monedas):
    lista_texto = []
    for m in monedas:
        lista_texto.append(
            f"• Símbolo: {m['simbolo']} | Precio: {formatear_precio(m['precio'])} | Cambio: {m['cambio']:+.2f}%"
        )
    
    prompt = (
        "Actúa como un Trader Cuantitativo Senior.\n"
        "A continuación tienes los datos exactos de las 5 altcoins seleccionadas:\n\n"
        f"{chr(10).join(lista_texto)}\n\n"
        "Genera una respuesta utilizando ESTRICTAMENTE este formato HTML (sin usar etiquetas <a> escritas, solo texto plano en la última línea):\n\n"
        "<b>RESUMEN:</b> [1 sola frase corta sobre el comportamiento global del mercado]\n\n"
    )
    
    for m in monedas:
        prompt += (
            f"• <b>{m['simbolo']}</b> ({m['cambio']:+.1f}%) — {formatear_precio(m['precio'])} | 🟢🟢🟢🟢🟢\n"
            f"🧠 <i>[1 frase corta de análisis técnico fundamentando el movimiento de {m['simbolo']}]</i>\n"
            f"└ 📊 [RESUMEN_IA_{m['simbolo']}] | 🔶 [TRADEAR_{m['simbolo']}]\n\n"
        )

    prompt += "REGLA: Mantén exactamente las marcas [RESUMEN_IA_...] y [TRADEAR_...]."

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

        badge_y = y_top - 40
        badge_center = x_left + (bar_width // 2)
        draw.ellipse([badge_center - 22, badge_y - 22, badge_center + 22, badge_y + 22], fill="#1E293B", outline=color_barra, width=2)
        
        txt_sim = simbolo[:3]
        draw.text((badge_center - 12, badge_y - 7), txt_sim, fill="#FFFFFF", font=font_symbol)

        val_str = f"+{pct:.1f}%" if pct >= 0 else f"{pct:.1f}%"
        draw.text((badge_center - 24, badge_y - 50), val_str, fill=color_texto_val, font=font_val)

        x_start += bar_width + spacing

    footer_text = "Cazador Táctico • Ranking de Momentum 24h en Binance Spot"
    draw.text((50, 720), footer_text, fill="#64748B", font=font_footer)

    path_output = "infografia_tactica.png"
    img.save(path_output)
    return path_output

def ensamblar_texto_final(texto_ia, monedas):
    texto = re.sub(r'```[a-zA-Z]*', '', texto_ia)
    texto = texto.replace('```', '').replace('**', '').replace('\\"', '"').replace('\\', '')
    
    # Reemplazar de forma limpia y segura las marcas por etiquetas HTML de enlaces reales
    for m in monedas:
        tag_ia = f"[RESUMEN_IA_{m['simbolo']}]"
        enlace_ia = f'<a href="{m["netlify_url"]}">Resumen IA</a>'
        texto = texto.replace(tag_ia, enlace_ia)
        
        tag_trade = f"[TRADEAR_{m['simbolo']}]"
        enlace_trade = f'<a href="{m["binance_url"]}">Tradear</a>'
        texto = texto.replace(tag_trade, enlace_trade)

    lineas = texto.split('\n')
    lineas_reparadas = []
    for l in lineas:
        if l.count('<i>') > l.count('</i>'):
            l += '</i>'
        lineas_reparadas.append(l)
    
    return "\n".join(lineas_reparadas).strip()

def enviar_a_telegram(path_imagen, analisis_ia, monedas, total_analizadas):
    token_limpio = re.sub(r'[^a-zA-Z0-9:\-_]', '', TELEGRAM_BOT_TOKEN)
    chat_id_limpio = re.sub(r'[^0-9\-]', '', TELEGRAM_CHAT_ID)
    topic_id_limpio = re.sub(r'[^0-9]', '', TELEGRAM_TOPIC_ID)
    
    protocolo = "https"
    dominio = "api.telegram.org"
    url_foto = f"{protocolo}://{dominio}/bot{token_limpio}/sendPhoto"
    
    analisis_limpio = ensamblar_texto_final(analisis_ia, monedas)
    
    caption_completo = (
        "🎯 <b>CAZADOR TÁCTICO</b>\n"
        f"<b>MONEDAS ANALIZADAS:</b> {total_analizadas}\n\n"
        f"{analisis_limpio}"
    )
    
    if len(caption_completo) > 1000:
        caption_completo = caption_completo[:995] + "..."

    data_foto = {
        "chat_id": chat_id_limpio,
        "caption": caption_completo,
        "parse_mode": "HTML"
    }
    if topic_id_limpio:
        try:
            data_foto["message_thread_id"] = int(topic_id_limpio)
        except ValueError:
            data_foto["message_thread_id"] = topic_id_limpio

    with open(path_imagen, 'rb') as photo_file:
        res = requests.post(url_foto, data=data_foto, files={'photo': photo_file})
        if res.status_code != 200:
            print(f"Error en envío con HTML: {res.text}")
            data_foto.pop("parse_mode", None)
            data_foto["caption"] = re.sub(r'<[^>]+>', '', caption_completo)
            with open(path_imagen, 'rb') as photo_file2:
                requests.post(url_foto, data=data_foto, files={'photo': photo_file2})

    print("¡Publicación enviada perfectamente a Telegram!")

if __name__ == "__main__":
    print("Iniciando Cazador Táctico (Top 5 con enlaces seguros)...")
    client = configurar_ia()
    
    tickers = obtener_mercado_binance()
    if tickers:
        monedas_grafico, total_analizadas = seleccionar_top5_oportunidades(tickers)
        analisis_ia = analizar_top5_con_ia(client, monedas_grafico)
        path_imagen = generar_imagen_infografia(monedas_grafico)
        enviar_a_telegram(path_imagen, analisis_ia, monedas_grafico, total_analizadas)
    else:
        print("No se pudieron obtener datos del mercado.")
