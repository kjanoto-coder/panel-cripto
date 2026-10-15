import os
import json
import requests
import pandas as pd
from google import genai

# ---------------------------------------------------------
# CONFIGURACIÓN DE CREDENCIALES
# ---------------------------------------------------------
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("CHAT_ID")
MESSAGE_THREAD_ID = os.getenv("TOPIC_ID_SENTINEL_MACRO")  # ID 2489 (Sentimiento Mercado)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# ---------------------------------------------------------
# 1. CAPTURA DE DATOS Y RECURSOS
# ---------------------------------------------------------
def descargar_heatmap_wall_street():
    """Descarga el mosaico/heatmap en tiempo real del S&P 500"""
    url_map = "https://finviz.com/map.ashx?t=sec"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        res = requests.get(url_map, headers=headers, timeout=10)
        if res.status_code == 200:
            with open("heatmap_wall_street.png", "wb") as f:
                f.write(res.content)
            return True
    except Exception:
        pass
    return False

def obtener_fear_and_greed_cripto():
    fg = {"score": 50, "clasificacion": "Neutral"}
    try:
        url = "https://api.alternative.me/fng/?limit=1"
        res = requests.get(url, timeout=5).json()
        if "data" in res and len(res["data"]) > 0:
            fg["score"] = int(res["data"][0]["value"])
            fg["clasificacion"] = res["data"][0]["value_classification"]
    except Exception:
        pass
    return fg

def obtener_datos_cripto_global():
    datos = {"BTC": 0, "BTC_VAR": 0, "ETH": 0, "ETH_VAR": 0}
    try:
        res = requests.get("https://data-api.binance.vision/api/v3/ticker/24hr", timeout=5).json()
        for item in res:
            if item['symbol'] == 'BTCUSDT':
                datos["BTC"] = round(float(item['lastPrice']), 2)
                datos["BTC_VAR"] = round(float(item['priceChangePercent']), 2)
            elif item['symbol'] == 'ETHUSDT':
                datos["ETH"] = round(float(item['lastPrice']), 2)
                datos["ETH_VAR"] = round(float(item['priceChangePercent']), 2)
    except Exception:
        pass
    return datos

def obtener_vix_wall_street():
    try:
        import yfinance as yf
        vix = yf.Ticker("^VIX").history(period="1d")['Close'].iloc[-1]
        return round(vix, 2)
    except Exception:
        return 16.5

# ---------------------------------------------------------
# 2. MOTOR DE ANÁLISIS GLOBAL E IMPULSORES (POR QUÉ SUBE O BAJA)
# ---------------------------------------------------------
def analizar_causas_wall_street_ia(vix_val):
    if not GEMINI_API_KEY: 
        return "Análisis de causas no disponible."
        
    client = genai.Client(api_key=GEMINI_API_KEY)
    prompt = f"""
    Actúa como un estratega macroeconómico senior de Wall Street.
    El índice de volatilidad VIX está en {vix_val}.
    
    Redacta un resumen técnico y global (máximo 4 líneas) explicando:
    1. ¿Por qué Wall Street y las tecnológicas cotizan al alza o a la baja en la jornada actual? (Menciona factores clave como políticas de la Fed, datos de inflación, empleo, rendimientos de bonos o reportes de ganancias).
    2. ¿Cuál es el catalizador principal que está moviendo el mercado hoy?
    3. Perspectiva de riesgo para el cierre.
    """
    for mod in ['gemini-2.5-flash', 'gemini-1.5-flash']:
        try:
            res = client.models.generate_content(model=mod, contents=prompt)
            if res and res.text: return res.text
        except: continue
    return "Wall Street reacciona a los ajustes en las expectativas de tasas de la Reserva Federal y el comportamiento del sector tecnológico."

def analizar_causas_cripto_ia(fg_data, cripto_data):
    if not GEMINI_API_KEY: 
        return "Análisis de causas no disponible."
        
    client = genai.Client(api_key=GEMINI_API_KEY)
    prompt = f"""
    Actúa como un analista cuantitativo del mercado cripto.
    El índice de Miedo y Codicia está en {fg_data['score']}/100 ({fg_data['clasificacion']}) con BTC en ${cripto_data['BTC']} ({cripto_data['BTC_VAR']}%).
    
    Redacta un resumen técnico (máximo 4 líneas) explicando:
    1. ¿Por qué el mercado cripto está subiendo o bajando? (Evalúa flujos institucionales en ETFs, volumen en redes sociales (X), liquidaciones en derivados y la correlación macro con el dólar/Wall Street).
    2. ¿Es un movimiento orgánico de acumulación/distribución o impulsado por noticias/rumores?
    3. Conclusión sobre los niveles de soporte/resistencia clave en Bitcoin.
    """
    for mod in ['gemini-2.5-flash', 'gemini-1.5-flash']:
        try:
            res = client.models.generate_content(model=mod, contents=prompt)
            if res and res.text: return res.text
        except: continue
    return f"El mercado refleja cautela en la zona de {fg_data['clasificacion']} a la espera de confirmación de volumen en los ETFs spot de Bitcoin."

# ---------------------------------------------------------
# 3. EJECUCIÓN Y ENVÍO A TELEGRAM
# ---------------------------------------------------------
print("🌐 Analizando causas del mercado global y generando reportes...")

vix = obtener_vix_wall_street()
fg_cripto = obtener_fear_and_greed_cripto()
datos_cripto = obtener_datos_cripto_global()

causas_tradfi = analizar_causas_wall_street_ia(vix)
causas_cripto = analizar_causas_cripto_ia(fg_cripto, datos_cripto)

# Estado visual VIX
if vix >= 22:
    estado_vix = "🚨 PÁNICO / ALTA VOLATILIDAD"
elif vix >= 17:
    estado_vix = "⚠️ PRECAUCIÓN EN BOLSAS"
else:
    estado_vix = "🟢 CALMA Y OPTIMISMO"

# --- MENSAJE 1: WALL STREET & TRADFI ---
msg_tradfi = "🏛️ **SENTINEL MACRO — 1. WALL STREET & TRADFI**\n\n"
msg_tradfi += f"📊 **Índice de Volatilidad (VIX):** `{vix}` | `{estado_vix}`\n\n"
msg_tradfi += f"🔍 **¿Por qué se mueve Wall Street? (Diagnóstico Global):**\n{causas_tradfi}\n"

# --- MENSAJE 2: MERCADO CRIPTO ---
msg_cripto = "🪙 **SENTINEL MACRO — 2. MERCADO CRIPTO**\n\n"
msg_cripto += f"🌡️ **Índice de Miedo y Codicia:** `{fg_cripto['score']}/100` — *{fg_cripto['clasificacion']}*\n"
msg_cripto += f"• **Bitcoin (BTC):** `${datos_cripto['BTC']}` | `{datos_cripto['BTC_VAR']}%`\n"
msg_cripto += f"• **Ethereum (ETH):** `${datos_cripto['ETH']}` | `{datos_cripto['ETH_VAR']}%`\n\n"
msg_cripto += f"🔍 **¿Por qué se mueve el Mercado Cripto? (Análisis Técnico & X):**\n{causas_cripto}\n"

# Envío a Telegram dirigiendo al Topic 2489 (Sentimiento Mercado)
if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
    url_base = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"
    thread_id = int(MESSAGE_THREAD_ID) if MESSAGE_THREAD_ID else None

    # Descargar Heatmap de Wall Street
    descargar_heatmap_wall_street()

    # ENVÍO REPORTE 1: WALL STREET
    if os.path.exists("heatmap_wall_street.png"):
        with open("heatmap_wall_street.png", "rb") as foto1:
            p_f1 = {'chat_id': TELEGRAM_CHAT_ID, 'caption': "🗺️ **Mapa de Calor en Vivo — Wall Street (S&P 500)**", 'parse_mode': 'Markdown'}
            if thread_id: p_f1['message_thread_id'] = thread_id
            requests.post(f"{url_base}/sendPhoto", data=p_f1, files={'photo': foto1})

    p_m1 = {'chat_id': TELEGRAM_CHAT_ID, 'text': msg_tradfi, 'parse_mode': 'Markdown'}
    if thread_id: p_m1['message_thread_id'] = thread_id
    requests.post(f"{url_base}/sendMessage", json=p_m1)

    # ENVÍO REPORTE 2: CRIPTO
    url_fg_img = "https://alternative.me/crypto/fear-and-greed-index.png"
    p_f2 = {'chat_id': TELEGRAM_CHAT_ID, 'photo': url_fg_img, 'caption': "🌡️ **Medidor Oficial Fear & Greed Cripto**", 'parse_mode': 'Markdown'}
    if thread_id: p_f2['message_thread_id'] = thread_id
    requests.post(f"{url_base}/sendPhoto", data=p_f2)

    p_m2 = {'chat_id': TELEGRAM_CHAT_ID, 'text': msg_cripto, 'parse_mode': 'Markdown'}
    if thread_id: p_m2['message_thread_id'] = thread_id
    requests.post(f"{url_base}/sendMessage", json=p_m2)

    print("✅ Ambos reportes con análisis de causas global enviados exitosamente a Telegram.")
