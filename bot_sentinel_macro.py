import os
import json
import requests
import datetime
import pandas as pd
import yfinance as yf
import matplotlib.pyplot as plt
import squarify
from google import genai

# ---------------------------------------------------------
# CONFIGURACIÓN DE CREDENCIALES Y RUTAS
# ---------------------------------------------------------
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("CHAT_ID")
MESSAGE_THREAD_ID = os.getenv("TOPIC_ID_SENTINEL_MACRO")  # Topic 2489 (Sentimiento Mercado)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

HISTORIAL_FILE = "historial_noticias.json"

# ---------------------------------------------------------
# GESTIÓN DE MEMORIA ANTI-REPETICIÓN DE NOTICIAS
# ---------------------------------------------------------
def cargar_historial():
    if os.path.exists(HISTORIAL_FILE):
        try:
            with open(HISTORIAL_FILE, "r") as f:
                return json.load(f)
        except Exception:
            return []
    return []

def guardar_noticia_en_historial(texto):
    historial = cargar_historial()
    if texto not in historial:
        historial.append(texto)
        # Mantener solo las últimas 150 entradas
        historial = historial[-150:]
        with open(HISTORIAL_FILE, "w") as f:
            json.dump(historial, f, indent=4)

def filtrar_noticias_nuevas(texto_analisis):
    """Compara y evita duplicar fragmentos ya analizados en ejecuciones previas"""
    historial = cargar_historial()
    for item in historial:
        if item in texto_analisis:
            return False
    guardar_noticia_en_historial(texto_analisis)
    return True

# ---------------------------------------------------------
# DETECCIÓN DE SESIÓN GLOBAL (ASIA, EUROPA, EE.UU., CIERRE CRIPTO)
# ---------------------------------------------------------
def obtener_sesion_actual_mercado():
    hora_actual = datetime.datetime.now().hour
    # Hora Argentina (ART)
    if 20 <= hora_actual or hora_actual < 4:
        return "🌏 SESIÓN ASIA (Tokio / Hong Kong) & Nocturno Cripto"
    elif 4 <= hora_actual < 10:
        return "🌍 SESIÓN EUROPA (Londres / Frankfurt)"
    elif 21 == hora_actual:
        return "🪙 CIERRE DIARIO DE VELA CRIPTO (21:00 ART)"
    else:
        return "🌎 SESIÓN EE. UU. (Wall Street / Nueva York)"

# ---------------------------------------------------------
# 1. MAPA DE CALOR PROPORCIONAL DE WALL STREET (TRADFI)
# ---------------------------------------------------------
def obtener_datos_wall_street_treemap():
    acciones = {
        "NVDA": ("NVDA", 3.0), "AAPL": ("AAPL", 3.3), "MSFT": ("MSFT", 3.1),
        "GOOGL": ("GOOGL", 2.1), "AMZN": ("AMZN", 2.2), "META": ("META", 1.4),
        "TSLA": ("TSLA", 0.8), "AVGO": ("AVGO", 0.8), "JPM": ("JPM", 0.6),
        "AMD": ("AMD", 0.3)
    }
    datos = []
    for label, (ticker_str, mcap_weight) in acciones.items():
        try:
            t = yf.Ticker(ticker_str)
            hist = t.history(period="2d")
            if len(hist) >= 2:
                p_act = hist['Close'].iloc[-1]
                p_prev = hist['Close'].iloc[-2]
                var = round(((p_act - p_prev) / p_prev) * 100, 2)
            else:
                var = 0.0
        except Exception:
            var = 0.0
        datos.append({"ticker": label, "weight": mcap_weight, "var": var})
    return pd.DataFrame(datos)

def generar_treemap_wall_street(df):
    fig, ax = plt.subplots(figsize=(10, 6), facecolor='#0b0e14')
    ax.set_facecolor('#0b0e14')

    sizes = df['weight']
    labels = [f"{row['ticker']}\n{row['var']}%" for _, row in df.iterrows()]
    colors = ['#26a69a' if v >= 0 else '#ef5350' for v in df['var']]

    squarify.plot(sizes=sizes, label=labels, color=colors, alpha=0.9,
                  text_kwargs={'color':'white', 'fontsize':10, 'weight':'bold'}, ax=ax)

    plt.title("MAPA DE CALOR — WALL STREET & BIG TECH", color='#FFD700', fontsize=12, fontweight='bold', pad=12)
    plt.axis('off')
    plt.tight_layout()
    plt.savefig('heatmap_wall_street.png', dpi=250, facecolor=fig.get_facecolor(), edgecolor='none')
    plt.close()

# ---------------------------------------------------------
# 2. MAPA DE CALOR PROPORCIONAL DE CRIPTO (BINANCE)
# ---------------------------------------------------------
def obtener_datos_cripto_treemap():
    criptos = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "DOGEUSDT", "ADAUSDT", "AVAXUSDT"]
    datos = []
    try:
        res = requests.get("https://data-api.binance.vision/api/v3/ticker/24hr", timeout=5).json()
        dict_res = {item['symbol']: item for item in res}
        
        for symbol in criptos:
            if symbol in dict_res:
                item = dict_res[symbol]
                ticker_clean = symbol.replace("USDT", "")
                vol = float(item['quoteVolume'])
                var = round(float(item['priceChangePercent']), 2)
                datos.append({"ticker": ticker_clean, "vol": vol, "var": var})
    except Exception:
        pass
        
    if not datos:
        datos = [{"ticker": "BTC", "vol": 100, "var": -1.5}, {"ticker": "ETH", "vol": 60, "var": -2.8}]
        
    return pd.DataFrame(datos)

def generar_treemap_cripto(df):
    fig, ax = plt.subplots(figsize=(10, 6), facecolor='#0b0e14')
    ax.set_facecolor('#0b0e14')

    sizes = df['vol']
    labels = [f"{row['ticker']}USDT\n{row['var']}%" for _, row in df.iterrows()]
    colors = ['#26a69a' if v >= 0 else '#ef5350' for v in df['var']]

    squarify.plot(sizes=sizes, label=labels, color=colors, alpha=0.9,
                  text_kwargs={'color':'white', 'fontsize':11, 'weight':'bold'}, ax=ax)

    plt.title("MAPA DE CALOR — BINANCE CRIPTO MARKET", color='#FFD700', fontsize=12, fontweight='bold', pad=12)
    plt.axis('off')
    plt.tight_layout()
    plt.savefig('heatmap_cripto.png', dpi=250, facecolor=fig.get_facecolor(), edgecolor='none')
    plt.close()

# ---------------------------------------------------------
# 3. ANÁLISIS DE NOTICIAS Y CAUSAS CON IA (GEMINI)
# ---------------------------------------------------------
def analizar_noticias_wall_street_ia(df_ws, sesion):
    if not GEMINI_API_KEY: return "Análisis no disponible."
    client = genai.Client(api_key=GEMINI_API_KEY)
    
    resumen_mercado = ", ".join([f"{r['ticker']}: {r['var']}%" for _, r in df_ws.iterrows()])
    
    prompt = f"""
    Actúa como un estratega macroeconómico global.
    Sesión actual: {sesion}.
    Variaciones del mercado bursátil: {resumen_mercado}.

    Redacta un reporte técnico de última hora (máximo 4 líneas) explicando:
    1. Por qué el mapa de calor muestra ese comportamiento (factores geopolíticos, tecnológicas, tasas de la Fed).
    2. Noticias recientes frescas que expliquen el movimiento actual de la sesión.
    """
    for mod in ['gemini-2.5-flash', 'gemini-1.5-flash']:
        try:
            res = client.models.generate_content(model=mod, contents=prompt)
            if res and res.text: return res.text
        except: continue
    return "Mercados evaluando la liquidez institucional y los informes macroeconómicos recientes."

def analizar_noticias_cripto_ia(df_cripto, sesion):
    if not GEMINI_API_KEY: return "Análisis no disponible."
    client = genai.Client(api_key=GEMINI_API_KEY)
    
    resumen_cripto = ", ".join([f"{r['ticker']}: {r['var']}%" for _, r in df_cripto.iterrows()])
    
    prompt = f"""
    Actúa como un analista cuantitativo de criptomonedas.
    Sesión actual: {sesion}.
    Variaciones en Binance: {resumen_cripto}.

    Redacta un reporte técnico de última hora (máximo 4 líneas) explicando:
    1. Por qué el mercado cripto se mueve en esa dirección (flujos en ETFs, liquidaciones en derivados o narrativas en redes sociales).
    2. Novedades y catalizadores recientes que impactan el volumen actual.
    """
    for mod in ['gemini-2.5-flash', 'gemini-1.5-flash']:
        try:
            res = client.models.generate_content(model=mod, contents=prompt)
            if res and res.text: return res.text
        except: continue
    return "El mercado cripto mantiene flujos condicionados por la apertura global y la actividad en derivados."

# ---------------------------------------------------------
# 4. EJECUCIÓN Y ENVÍO A TELEGRAM
# ---------------------------------------------------------
print("🌐 Ejecutando Sentinel Macro con sincronización de sesiones...")

sesion_actual = obtener_sesion_actual_mercado()

# --- 1. WALL STREET ---
df_ws = obtener_datos_wall_street_treemap()
generar_treemap_wall_street(df_ws)
causas_ws = analizar_noticias_wall_street_ia(df_ws, sesion_actual)

msg_ws = f"🏛️ **SENTINEL MACRO — 1. WALL STREET & TRADFI**\n"
msg_ws += f"🕒 *Sesión:* `{sesion_actual}`\n\n"
msg_ws += f"🔍 **¿Qué está pasando y por qué? (Noticias & Análisis):**\n{causas_ws}\n"

# --- 2. CRIPTO ---
df_cripto = obtener_datos_cripto_treemap()
generar_treemap_cripto(df_cripto)
causas_cripto = analizar_noticias_cripto_ia(df_cripto, sesion_actual)

msg_cripto = f"🪙 **SENTINEL MACRO — 2. BINANCE CRIPTO MARKET**\n"
msg_cripto += f"🕒 *Sesión:* `{sesion_actual}`\n\n"
msg_cripto += f"🔍 **¿Qué está pasando y por qué? (Noticias & Mercado):**\n{causas_cripto}\n"

# Envío a Telegram (Topic 2489)
if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
    url_base = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"
    thread_id = int(MESSAGE_THREAD_ID) if MESSAGE_THREAD_ID else None

    # Enviar Wall Street
    with open('heatmap_wall_street.png', 'rb') as f1:
        p_f1 = {'chat_id': TELEGRAM_CHAT_ID, 'caption': f"🗺️ **Mapa de Calor — Wall Street ({sesion_actual})**", 'parse_mode': 'Markdown'}
        if thread_id: p_f1['message_thread_id'] = thread_id
        requests.post(f"{url_base}/sendPhoto", data=p_f1, files={'photo': f1})

    p_m1 = {'chat_id': TELEGRAM_CHAT_ID, 'text': msg_ws, 'parse_mode': 'Markdown'}
    if thread_id: p_m1['message_thread_id'] = thread_id
    requests.post(f"{url_base}/sendMessage", json=p_m1)

    # Enviar Cripto
    with open('heatmap_cripto.png', 'rb') as f2:
        p_f2 = {'chat_id': TELEGRAM_CHAT_ID, 'caption': f"🗺️ **Mapa de Calor — Cripto ({sesion_actual})**", 'parse_mode': 'Markdown'}
        if thread_id: p_f2['message_thread_id'] = thread_id
        requests.post(f"{url_base}/sendPhoto", data=p_f2, files={'photo': f2})

    p_m2 = {'chat_id': TELEGRAM_CHAT_ID, 'text': msg_cripto, 'parse_mode': 'Markdown'}
    if thread_id: p_m2['message_thread_id'] = thread_id
    requests.post(f"{url_base}/sendMessage", json=p_m2)

    print("✅ Reportes con mapas de calor y control de sesiones enviados exitosamente.")
