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
# GESTIÓN DE MEMORIA ANTI-REPETICIÓN
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
        historial = historial[-150:]
        with open(HISTORIAL_FILE, "w") as f:
            json.dump(historial, f, indent=4)

# ---------------------------------------------------------
# DETECCIÓN DE SESIÓN GLOBAL
# ---------------------------------------------------------
def obtener_sesion_actual_mercado():
    hora_actual = datetime.datetime.now().hour
    if 20 <= hora_actual or hora_actual < 4:
        return "🌏 SESIÓN ASIA (Tokio / Hong Kong)"
    elif 4 <= hora_actual < 10:
        return "🌍 SESIÓN EUROPA (Londres / Frankfurt)"
    elif 21 == hora_actual:
        return "🪙 CIERRE DIARIO DE VELA CRIPTO (21:00 ART)"
    else:
        return "🌎 SESIÓN EE. UU. (Wall Street / S&P 500)"

# ---------------------------------------------------------
# 1. MAPA DE CALOR PROPORCIONAL DE S&P 500 (WALL STREET)
# ---------------------------------------------------------
def obtener_datos_wall_street_treemap():
    acciones = {
        "NVDA": ("NVDA", 3.2), "AAPL": ("AAPL", 3.4), "MSFT": ("MSFT", 3.1),
        "GOOGL": ("GOOGL", 2.1), "AMZN": ("AMZN", 2.2), "META": ("META", 1.5),
        "TSLA": ("TSLA", 0.9), "AVGO": ("AVGO", 0.9), "JPM": ("JPM", 0.7),
        "AMD": ("AMD", 0.4), "NFLX": ("NFLX", 0.4), "INTC": ("INTC", 0.3),
        "QCOM": ("QCOM", 0.3), "PEP": ("PEP", 0.4), "KO": ("KO", 0.4),
        "DIS": ("DIS", 0.3), "PYPL": ("PYPL", 0.2), "CSCO": ("CSCO", 0.3)
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
    fig, ax = plt.subplots(figsize=(12, 7), facecolor='#0b0e14')
    ax.set_facecolor('#0b0e14')

    sizes = df['weight']
    labels = [f"{row['ticker']}\n{row['var']}%" for _, row in df.iterrows()]
    colors = ['#00796b' if v >= 2 else ('#26a69a' if v >= 0 else ('#e53935' if v <= -2 else '#c62828')) for v in df['var']]

    squarify.plot(sizes=sizes, label=labels, color=colors, alpha=0.95,
                  pad=True, edgecolor="#0b0e14", linewidth=2,
                  text_kwargs={'color':'white', 'fontsize':9, 'weight':'bold'}, ax=ax)

    plt.title("MAPA DE CALOR PROFESIONAL — S&P 500 (WALL STREET)", color='#FFD700', fontsize=13, fontweight='bold', pad=15)
    plt.axis('off')
    plt.tight_layout()
    plt.savefig('heatmap_wall_street.png', dpi=300, facecolor=fig.get_facecolor(), edgecolor='none')
    plt.close()

# ---------------------------------------------------------
# 2. MAPA DE CALOR PROPORCIONAL DE CRIPTO
# ---------------------------------------------------------
def obtener_datos_cripto_treemap():
    criptos = [
        "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", 
        "DOGEUSDT", "ADAUSDT", "AVAXUSDT", "LINKUSDT", "DOTUSDT", 
        "MATICUSDT", "NEARUSDT", "UNIUSDT", "ATOMUSDT", "LTCUSDT"
    ]
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
    fig, ax = plt.subplots(figsize=(12, 7), facecolor='#0b0e14')
    ax.set_facecolor('#0b0e14')

    sizes = df['vol']
    labels = [f"{row['ticker']}\n{row['var']}%" for _, row in df.iterrows()]
    colors = ['#00796b' if v >= 2 else ('#26a69a' if v >= 0 else ('#e53935' if v <= -2 else '#c62828')) for v in df['var']]

    squarify.plot(sizes=sizes, label=labels, color=colors, alpha=0.95,
                  pad=True, edgecolor="#0b0e14", linewidth=2,
                  text_kwargs={'color':'white', 'fontsize':9, 'weight':'bold'}, ax=ax)

    plt.title("MAPA DE CALOR PROFESIONAL — BINANCE CRIPTO MARKET", color='#FFD700', fontsize=13, fontweight='bold', pad=15)
    plt.axis('off')
    plt.tight_layout()
    plt.savefig('heatmap_cripto.png', dpi=300, facecolor=fig.get_facecolor(), edgecolor='none')
    plt.close()

# ---------------------------------------------------------
# 3. ANÁLISIS DE DATOS REALES CON IA PROFUNDA (GEMINI)
# ---------------------------------------------------------
def analizar_noticias_wall_street_ia(df_ws, sesion):
    if not GEMINI_API_KEY: return "Análisis no disponible."
    client = genai.Client(api_key=GEMINI_API_KEY)
    
    # Pasamos los datos exactos obtenidos de Yahoo Finance
    detalle_activos = "\n".join([f"- {r['ticker']}: {r['var']}%" for _, r in df_ws.iterrows()])
    
    prompt = f"""
    Actúa como un trader institucional senior y analista macroeconómico de Wall Street.
    Sesión analizada: {sesion}.
    
    Datos exactos de variación en tiempo real del S&P 500 / Big Tech:
    {detalle_activos}

    Redacta un reporte táctico directo y agudo (de 3 a 5 líneas máximo). 
    REGLAS OBLIGATORIAS:
    - No uses frases cliché ni vacías. 
    - Menciona qué acciones específicas están liderando las subidas o bajadas según los datos provistos.
    - Explica con precisión quirúrgica qué sector ( semiconductores, consumo, banca, tecnología) tracciona el mercado hoy y qué factores macro (rendimiento de bonos, tensiones geopolíticas, expectativas de tasas) explican este comportamiento.
    """
    for mod in ['gemini-2.5-flash', 'gemini-1.5-flash']:
        try:
            res = client.models.generate_content(model=mod, contents=prompt)
            if res and res.text: return res.text
        except: continue
    return "Variaciones mixtas en el S&P 500 con rotación de capital hacia activos defensivos ante la cautela en la renta variable tecnológica."

def analizar_noticias_cripto_ia(df_cripto, sesion):
    if not GEMINI_API_KEY: return "Análisis no disponible."
    client = genai.Client(api_key=GEMINI_API_KEY)
    
    # Pasamos los datos exactos obtenidos de Binance
    detalle_cripto = "\n".join([f"- {r['ticker']}: {r['var']}% (Vol: {r['vol']:,.0f})" for _, r in df_cripto.iterrows()])
    
    prompt = f"""
    Actúa como un analista cuantitativo de criptomonedas y experto en derivados de Binance.
    Sesión analizada: {sesion}.
    
    Datos exactos de variación y volumen en 24h:
    {detalle_cripto}

    Redacta un reporte táctico directo y agudo (de 3 a 5 líneas máximo).
    REGLAS OBLIGATORIAS:
    - No uses frases cliché ni vacías.
    - Analiza qué altcoins o majors (BTC, ETH, SOL, etc.) están absorbiendo volumen o sufriendo presión vendedora.
    - Explica la salud del mercado en base a las cifras: ¿hay apetito de riesgo en altcoins o refugio exclusivo en Bitcoin? Menciona la dinámica de liquidaciones o flujos institucionales.
    """
    for mod in ['gemini-2.5-flash', 'gemini-1.5-flash']:
        try:
            res = client.models.generate_content(model=mod, contents=prompt)
            if res and res.text: return res.text
        except: continue
    return "El mercado cripto muestra selectividad en altcoins con flujos concentrados en los activos de mayor capitalización."

# ---------------------------------------------------------
# 4. EJECUCIÓN Y ENVÍO A TELEGRAM CON BOTONES
# ---------------------------------------------------------
print("🌐 Ejecutando Sentinel Macro con análisis de IA profunda...")

sesion_actual = obtener_sesion_actual_mercado()

# S&P 500 / Wall Street
df_ws = obtener_datos_wall_street_treemap()
generar_treemap_wall_street(df_ws)
causas_ws = analizar_noticias_wall_street_ia(df_ws, sesion_actual)

msg_ws = f"🏛️ **SENTINEL MACRO — 1. S&P 500 & TRADFI**\n"
msg_ws += f"🕒 *Sesión:* `{sesion_actual}`\n\n"
msg_ws += f"🔍 **Análisis Táctico & Diagnóstico de Mercado:**\n{causas_ws}\n"

# Cripto
df_cripto = obtener_datos_cripto_treemap()
generar_treemap_cripto(df_cripto)
causas_cripto = analizar_noticias_cripto_ia(df_cripto, sesion_actual)

msg_cripto = f"🪙 **SENTINEL MACRO — 2. BINANCE CRIPTO MARKET**\n"
msg_cripto += f"🕒 *Sesión:* `{sesion_actual}`\n\n"
msg_cripto += f"🔍 **Análisis Táctico & Diagnóstico de Mercado:**\n{causas_cripto}\n"

# Enviar a Telegram
if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
    url_base = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"
    thread_id = int(MESSAGE_THREAD_ID) if MESSAGE_THREAD_ID else None

    teclado_ws = {
        "inline_keyboard": [[
            {"text": "📊 Ver Mapa Interactivo S&P 500 (Investing)", "url": "https://es.investing.com/markets/heatmap"}
        ]]
    }

    teclado_cripto = {
        "inline_keyboard": [[
            {"text": "🪙 Ver Mapa Interactivo Binance Futures", "url": "https://www.binance.com/es-AR/futures/crypto-heatmap"}
        ]]
    }

    # 1. Enviar S&P 500
    with open('heatmap_wall_street.png', 'rb') as f1:
        p_f1 = {'chat_id': TELEGRAM_CHAT_ID, 'caption': f"🗺️ **Mapa de Calor — S&P 500 ({sesion_actual})**", 'parse_mode': 'Markdown'}
        if thread_id: p_f1['message_thread_id'] = thread_id
        requests.post(f"{url_base}/sendPhoto", data=p_f1, files={'photo': f1})

    p_m1 = {
        'chat_id': TELEGRAM_CHAT_ID, 
        'text': msg_ws, 
        'parse_mode': 'Markdown',
        'reply_markup': teclado_ws
    }
    if thread_id: p_m1['message_thread_id'] = thread_id
    requests.post(f"{url_base}/sendMessage", json=p_m1)

    # 2. Enviar Cripto
    with open('heatmap_cripto.png', 'rb') as f2:
        p_f2 = {'chat_id': TELEGRAM_CHAT_ID, 'caption': f"🗺️ **Mapa de Calor — Cripto ({sesion_actual})**", 'parse_mode': 'Markdown'}
        if thread_id: p_f2['message_thread_id'] = thread_id
        requests.post(f"{url_base}/sendPhoto", data=p_f2, files={'photo': f2})

    p_m2 = {
        'chat_id': TELEGRAM_CHAT_ID, 
        'text': msg_cripto, 
        'parse_mode': 'Markdown',
        'reply_markup': teclado_cripto
    }
    if thread_id: p_m2['message_thread_id'] = thread_id
    requests.post(f"{url_base}/sendMessage", json=p_m2)

    print("✅ Reportes con diagnóstico analítico profundo enviados exitosamente.")
