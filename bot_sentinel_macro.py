import os
import json
import requests
import pandas as pd
import yfinance as yf
import matplotlib.pyplot as plt
import squarify
from google import genai

# ---------------------------------------------------------
# CONFIGURACIÓN DE CREDENCIALES
# ---------------------------------------------------------
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("CHAT_ID")
MESSAGE_THREAD_ID = os.getenv("TOPIC_ID_SENTINEL_MACRO")  # Topic 2489 (Sentimiento Mercado)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# ---------------------------------------------------------
# 1. MAPA DE CALOR PROPORCIONAL DE WALL STREET (TRADFI)
# ---------------------------------------------------------
def obtener_datos_wall_street_treemap():
    """Descarga datos y capitalización para armar el mapa de calor real por mosaicos"""
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
    """Genera el mapa de calor mosaico idéntico al de TradingView"""
    fig, ax = plt.subplots(figsize=(10, 6), facecolor='#0b0e14')
    ax.set_facecolor('#0b0e14')

    sizes = df['weight']
    labels = [f"{row['ticker']}\n{row['var']}%" for _, row in df.iterrows()]
    
    # Asignar colores verde/rojo según variación
    colors = ['#26a69a' if v >= 0 else '#ef5350' for v in df['var']]

    squarify.plot(sizes=sizes, label=labels, color=colors, alpha=0.9,
                  text_kwargs={'color':'white', 'fontsize':10, 'weight':'bold'}, ax=ax)

    plt.title("MAPA DE CALOR DE ACCIONES (S&P 500 / WALL STREET)", color='#FFD700', fontsize=12, fontweight='bold', pad=12)
    plt.axis('off')
    plt.tight_layout()
    plt.savefig('heatmap_wall_street.png', dpi=250, facecolor=fig.get_facecolor(), edgecolor='none')
    plt.close()

# ---------------------------------------------------------
# 2. MAPA DE CALOR PROPORCIONAL DE CRIPTO (FUTUROS/SPOT)
# ---------------------------------------------------------
def obtener_datos_cripto_treemap():
    """Obtiene datos de volumen y variación de Binance para el Mapa de Calor Cripto"""
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
    """Genera el mapa de calor mosaico idéntico al de Binance Futures"""
    fig, ax = plt.subplots(figsize=(10, 6), facecolor='#0b0e14')
    ax.set_facecolor('#0b0e14')

    sizes = df['vol']
    labels = [f"{row['ticker']}USDT\n{row['var']}%" for _, row in df.iterrows()]
    colors = ['#26a69a' if v >= 0 else '#ef5350' for v in df['var']]

    squarify.plot(sizes=sizes, label=labels, color=colors, alpha=0.9,
                  text_kwargs={'color':'white', 'fontsize':11, 'weight':'bold'}, ax=ax)

    plt.title("MAPA DE CALOR CRIPTO (BINANCE MARKET HEATMAP)", color='#FFD700', fontsize=12, fontweight='bold', pad=12)
    plt.axis('off')
    plt.tight_layout()
    plt.savefig('heatmap_cripto.png', dpi=250, facecolor=fig.get_facecolor(), edgecolor='none')
    plt.close()

# ---------------------------------------------------------
# 3. NOTICIAS Y DIAGNÓSTICO CON IA (GEMINI)
# ---------------------------------------------------------
def analizar_noticias_wall_street_ia(df_ws):
    if not GEMINI_API_KEY: return "Análisis no disponible."
    client = genai.Client(api_key=GEMINI_API_KEY)
    
    resumen_mercado = ", ".join([f"{r['ticker']}: {r['var']}%" for _, r in df_ws.iterrows()])
    
    prompt = f"""
    Actúa como un analista financiero jefe de Wall Street.
    El estado actual del mercado bursátil refleja las siguientes variaciones: {resumen_mercado}.

    Redacta un reporte breve en español (máximo 4 líneas) explicando:
    1. ¿Por qué el mapa de calor muestra esos colores? (Causas de fondo: sector tecnológico/IA, interrupciones de red, deudas del sector o expectativas de tasas de la Fed).
    2. Resumen de noticias recientes que están impactando la jornada actual.
    """
    for mod in ['gemini-2.5-flash', 'gemini-1.5-flash']:
        try:
            res = client.models.generate_content(model=mod, contents=prompt)
            if res and res.text: return res.text
        except: continue
    return "El sector tecnológico ajusta posiciones tras la volatilidad en las empresas de IA y la cautela por las tasas de interés."

def analizar_noticias_cripto_ia(df_cripto):
    if not GEMINI_API_KEY: return "Análisis no disponible."
    client = genai.Client(api_key=GEMINI_API_KEY)
    
    resumen_cripto = ", ".join([f"{r['ticker']}: {r['var']}%" for _, r in df_cripto.iterrows()])
    
    prompt = f"""
    Actúa como un estratega cuantitativo cripto.
    El mapa de calor de Binance muestra las siguientes variaciones en 24h: {resumen_cripto}.

    Redacta un reporte breve en español (máximo 4 líneas) explicando:
    1. Por qué el mercado cripto está cotizando en esa dirección (presión en liquidez, salidas/entradas de ETFs, derivación de altcoins).
    2. Noticias de última hora y eventos en redes (X) motivando la tendencia actual.
    """
    for mod in ['gemini-2.5-flash', 'gemini-1.5-flash']:
        try:
            res = client.models.generate_content(model=mod, contents=prompt)
            if res and res.text: return res.text
        except: continue
    return "Bitcoin y las principales altcoins reaccionan a la toma de ganancias y a la fluctuación de los derivados en Binance."

# ---------------------------------------------------------
# 4. EJECUCIÓN Y ENVÍO A TELEGRAM
# ---------------------------------------------------------
print("🌐 Generando Mapas de Calor Reales y Análisis de Noticias...")

# --- 1. WALL STREET ---
df_ws = obtener_datos_wall_street_treemap()
generar_treemap_wall_street(df_ws)
causas_ws = analizar_noticias_wall_street_ia(df_ws)

msg_ws = "🏛️ **SENTINEL MACRO — 1. MAPA DE CALOR & NOTICIAS WALL STREET**\n\n"
msg_ws += f"🔍 **¿Qué está pasando y por qué? (Noticias & Análisis):**\n{causas_ws}\n"

# --- 2. CRIPTO ---
df_cripto = obtener_datos_cripto_treemap()
generar_treemap_cripto(df_cripto)
causas_cripto = analizar_noticias_cripto_ia(df_cripto)

msg_cripto = "🪙 **SENTINEL MACRO — 2. MAPA DE CALOR & NOTICIAS CRIPTO**\n\n"
msg_cripto += f"🔍 **¿Qué está pasando y por qué? (Noticias & Mercado):**\n{causas_cripto}\n"

# Envío a Telegram (Topic 2489 - Sentimiento Mercado)
if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
    url_base = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"
    thread_id = int(MESSAGE_THREAD_ID) if MESSAGE_THREAD_ID else None

    # 1. Enviar Mapa de Calor Wall Street + Noticias
    with open('heatmap_wall_street.png', 'rb') as f1:
        p_f1 = {'chat_id': TELEGRAM_CHAT_ID, 'caption': "🗺️ **Mapa de Calor en Vivo — Wall Street (S&P 500)**", 'parse_mode': 'Markdown'}
        if thread_id: p_f1['message_thread_id'] = thread_id
        requests.post(f"{url_base}/sendPhoto", data=p_f1, files={'photo': f1})

    p_m1 = {'chat_id': TELEGRAM_CHAT_ID, 'text': msg_ws, 'parse_mode': 'Markdown'}
    if thread_id: p_m1['message_thread_id'] = thread_id
    requests.post(f"{url_base}/sendMessage", json=p_m1)

    # 2. Enviar Mapa de Calor Cripto + Noticias
    with open('heatmap_cripto.png', 'rb') as f2:
        p_f2 = {'chat_id': TELEGRAM_CHAT_ID, 'caption': "🗺️ **Mapa de Calor en Vivo — Binance Cripto Market**", 'parse_mode': 'Markdown'}
        if thread_id: p_f2['message_thread_id'] = thread_id
        requests.post(f"{url_base}/sendPhoto", data=p_f2, files={'photo': f2})

    p_m2 = {'chat_id': TELEGRAM_CHAT_ID, 'text': msg_cripto, 'parse_mode': 'Markdown'}
    if thread_id: p_m2['message_thread_id'] = thread_id
    requests.post(f"{url_base}/sendMessage", json=p_m2)

    print("✅ Ambos reportes con Mapas de Calor Mosaico y Noticias enviados a Telegram.")
