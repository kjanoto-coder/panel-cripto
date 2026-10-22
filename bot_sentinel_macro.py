import os
import json
import requests
import datetime
import pandas as pd
import yfinance as yf
import matplotlib.pyplot as plt
import squarify
from bs4 import BeautifulSoup
import xml.etree.ElementTree as ET
from google import genai

# ---------------------------------------------------------
# CONFIGURACIÓN DE CREDENCIALES Y RUTAS
# ---------------------------------------------------------
TELEGRAM_BOT_TOKEN = (os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("TELEGRAM_TOKEN") or "").strip()
TELEGRAM_CHAT_ID = (os.getenv("TELEGRAM_CHAT_ID") or os.getenv("CHAT_ID") or "").strip()
MESSAGE_THREAD_ID = (os.getenv("TOPIC_ID_SENTINEL_MACRO") or os.getenv("TELEGRAM_MESSAGE_THREAD_ID") or "").strip()
GEMINI_API_KEY = (os.getenv("GEMINI_API_KEY") or "").strip()

ESTADO_PREVIO_FILE = "datos_sentinel_macro.json"
HISTORIAL_NOTICIAS_FILE = "historial_noticias.json"
DATABASE_ECOSISTEMA_FILE = "database_ecosistema.json"

# Enlace de tu Planilla de Google Sheets (Auditor Ecosistema Cripto)
GOOGLE_SHEET_URL = "https://docs.google.com/spreadsheets/d/1qMAWNGK7dMay12wDQ9x3hZiZwE9klzdtWuoReGE1pg/edit"

# ---------------------------------------------------------
# MEMORIA Y COMPARATIVA DE GIROS
# ---------------------------------------------------------
def cargar_estado_previo():
    if os.path.exists(ESTADO_PREVIO_FILE):
        try:
            with open(ESTADO_PREVIO_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def guardar_estado_actual(datos_ws, datos_cripto):
    estado = {
        "timestamp": datetime.datetime.now().isoformat(),
        "wall_street": datos_ws,
        "cripto": datos_cripto
    }
    try:
        with open(ESTADO_PREVIO_FILE, "w", encoding="utf-8") as f:
            json.dump(estado, f, indent=4)
    except Exception as e:
        print("Error guardando estado previo: " + str(e))

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
# 1. MAPA DE CALOR DE S&P 500 (WALL STREET)
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
    labels = [row['ticker'] + "\n" + str(row['var']) + "%" for _, row in df.iterrows()]
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
# 2. MAPA DE CALOR DE CRIPTO (BINANCE)
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
    labels = [row['ticker'] + "\n" + str(row['var']) + "%" for _, row in df.iterrows()]
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
# 3. EXTRAER NOTICIAS EN VIVO Y CONFIGURAR ENLACE DE TRADINGVIEW
# ---------------------------------------------------------
def limpiar_html(texto):
    return texto.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").strip()

def cargar_historial_noticias():
    if os.path.exists(HISTORIAL_NOTICIAS_FILE):
        try:
