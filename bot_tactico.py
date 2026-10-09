import os
import re
import time
import requests
from google import genai

# Captura y limpieza de variables de entorno
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.getenv("CHAT_ID", "").strip()
TELEGRAM_TOPIC_ID = os.getenv("TOPIC_ID_TACTICO", "").strip()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()

def configurar_ia():
    if not GEMINI_API_KEY:
        raise ValueError("Falta la clave GEMINI_API_KEY en los secretos de GitHub.")
    return genai.Client(api_key=GEMINI_API_KEY)

def obtener_mercado_binance():
    url = "https://data-api.binance.vision/api/v3/ticker/24hr"
    try:
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"Error al conectar con Binance: {e}")
        return None

def formatear_precio(precio):
    """Ajusta los decimales dinámicamente para coincidir con la interfaz de Binance."""
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
    # 1. Filtrar pares USDT válidos (excluyendo tokens apalancados)
    usdt_pairs = [
        t for t in tickers 
        if t['symbol'].endswith('USDT') and not any(x in t['symbol'] for x in ['UP', 'DOWN', 'BULL', 'BEAR'])
    ]
    
    # 2. FILTRO ESTRICTO: Únicamente monedas con precio menor a $1.00 USD
    tokens_bajo_valor = [
        t for t in usdt_pairs if float(t['lastPrice']) < 1.0
    ]
    
    # 3. Ordenar por volumen y tomar el Top 25 dinámico
    top_volumen = sorted(tokens_bajo_valor, key=lambda x: float(x['quoteVolume']), reverse=True)[:25]
    return top_volumen

def analizar_oportunidades_con_ia(client, mercado_resumen):
    prompt = f"""
    Actúa como un trader cuantitativo implacable especializado en altcoins de baja capitalización y memecoins de alto rendimiento.
    Aquí tienes el escaneo en tiempo real del Top 25 de criptomonedas de **bajo valor (menores a $1 USD)** en Binance Spot con su enlace oficial de trading:
    
    {mercado_resumen}
    
    Tu objetivo es seleccionar estrictamente las **2 o 3 mejores opciones** que muestren un patrón claro de acumulación o rebote inminente en el corto plazo.
    
    Estructura la alerta para Telegram usando ÚNICAMENTE formato HTML de Telegram (utiliza <b>texto</b> para negritas y <a href="URL">Texto</a> para enlaces):
    
    - 🪙 <b>Símbolo:</b> [Nombre y Símbolo]
    - 💲 <b>Precio:</b> [Precio actual]
    - 📈 <b>Cambio 24h y Volumen:</b> [Variación % y Volumen USDT]
    - 🧠 <b>Veredicto de la IA:</b> [Explicación técnica del porqué destaca hoy]
    - 🚀 <b>Trade Directo:</b> <a href="[URL_BINANCE]">Abrir en Binance</a>
    
    REGLAS ESTRICTAS:
    1. NO uses bloques de código tipo markdown (```html). Devuelve únicamente texto plano formateado con HTML directo.
    2. Incluye siempre la línea de "Trade Directo" con el enlace exacto a Binance proporcionado en la lista.
    3. No utilices asteriscos (**) para negritas. Usa únicamente etiquetas HTML <b>...</b>.
    """
    
    # Modelo oficial indicado por la API de Google
    modelos = ['gemini-2.8-flash', 'gemini-2.5-flash']
    
    for modelo in modelos:
        print(f"Probando modelo IA: {modelo}...")
        for intento in range(1, 3):
            try:
                response = client.models.generate_content(
                    model=modelo,
                    contents=prompt,
                )
                if response and response.text:
                    print(f"¡Análisis de mercado generado con éxito usando {modelo}!")
                    return response.text
            except Exception as e:
                print(f"Aviso con modelo {modelo} (Intento {intento}/2): {e}")
                time.sleep(5)
            
    raise Exception("No se pudo obtener respuesta de la IA. Verifica que tu GEMINI_API_KEY en GitHub Secrets sea válida y esté activa.")

def enviar_a_telegram(mensaje, total_analizadas):
    token_limpio = re.sub(r'[^a-zA-Z0-9:\-_]', '', TELEGRAM_BOT_TOKEN)
    chat_id_limpio = re.sub(r'[^0-9\-]', '', TELEGRAM_CHAT_ID)
    topic_id_limpio = re.sub(r'[^0-9]', '', TELEGRAM_TOPIC_ID)
    
    url = f"[https://api.telegram.org/bot](https://api.telegram.org/bot){token_limpio}/sendMessage"
    
    mensaje_limpio = (
        mensaje.replace("```html", "")
        .replace("```", "")
        .replace("**", "")
        .strip()
    )
    
    encabezado = (
        "🎯 <b>CAZADOR TÁCTICO (ALTCOINS SUB-$1)</b>\n"
        "🏢 <b>Mercado:</b> Binance Spot (USDT)\n"
        f"🔍 <b>Universo analizado:</b> Top {total_analizadas} monedas (< $1.00 USD) por volumen 24h\n"
        "-----------------------------------------\n\n"
    )
    
    texto_final = f"{encabezado}{mensaje_limpio}"
    
    payload = {
        "chat_id": chat_id_limpio,
        "text": texto_final,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }
    
    if topic_id_limpio:
        try:
            payload["message_thread_id"] = int(topic_id_limpio)
        except ValueError:
            payload["message_thread_id"] = topic_id_limpio
            
    response = requests.post(url, json=payload)
    
    if response.status_code != 200:
        print(f"Aviso de formato en Telegram ({response.text}). Reintentando envío en texto plano...")
        payload.pop("parse_mode", None)
        payload["text"] = texto_final.replace("<b>", "").replace("</b>", "").replace("<i>", "").replace("</i>", "")
        response = requests.post(url, json=payload)
        if response.status_code != 200:
            raise Exception(f"Error al enviar a Telegram: {response.text}")
            
    print("¡Alerta enviada con éxito al tema de Telegram!")

if __name__ == "__main__":
    print("Iniciando Cazador Táctico de Bajo Valor...")
    client = configurar_ia()
    
    tickers = obtener_mercado_binance()
    if tickers:
        candidatos = filtrar_candidatos_bajo_valor(tickers)
        
        resumen_datos = []
        for item in candidatos:
            sim = item['symbol'].replace('USDT', '')
            precio = float(item['lastPrice'])
            cambio = float(item['priceChangePercent'])
            volumen = float(item['quoteVolume'])
            binance_url = f"[https://www.binance.com/es/trade/](https://www.binance.com/es/trade/){sim}_USDT?type=spot"
            
            resumen_datos.append(
                f"Moneda: {sim} | Precio: {formatear_precio(precio)} | Cambio 24h: {cambio:+.2f}% | Vol USDT: {volumen:,.0f} | URL Binance: {binance_url}"
            )
        
        analisis_ia = analizar_oportunidades_con_ia(client, "\n".join(resumen_datos))
        enviar_a_telegram(analisis_ia, len(candidatos))
    else:
        print("No se pudieron obtener datos del mercado.")
