import os
import re
import json
import time
import requests
import datetime
import pandas as pd
import yfinance as yf
import matplotlib.pyplot as plt
import squarify
from bs4 import BeautifulSoup
from google import genai

# ---------------------------------------------------------
# CONFIGURACIÓN DE CREDENCIALES, ZONA HORARIA Y RUTAS
# ---------------------------------------------------------
TZ_ART = datetime.timezone(datetime.timedelta(hours=-3))

TELEGRAM_BOT_TOKEN = (os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("TELEGRAM_TOKEN") or "").strip()
TELEGRAM_CHAT_ID = (os.getenv("TELEGRAM_CHAT_ID") or os.getenv("CHAT_ID") or "").strip()
MESSAGE_THREAD_ID = (os.getenv("TOPIC_ID_SENTINEL_MACRO") or os.getenv("TELEGRAM_MESSAGE_THREAD_ID") or "").strip()
GEMINI_API_KEY = (os.getenv("GEMINI_API_KEY") or "").strip()

ESTADO_PREVIO_FILE = "datos_sentinel_macro.json"
HISTORIAL_NOTICIAS_FILE = "historial_noticias.json"
DATABASE_ECOSISTEMA_FILE = "database_ecosistema.json"

GOOGLE_SHEET_URL = "https://docs.google.com/spreadsheets/d/1qMAWNGK7dMaY12wDQ9x3h3iZwJE9klzdtWuoReGE1pg/edit?usp=sharing"
INTERVALO_REPORTE_COMPLETO_MIN = 26  # Garantiza envío puntual en los bloques de 30 min

# ---------------------------------------------------------
# MEMORIA PERSISTENTE Y DETECCIÓN DE GIROS (VERDE <-> ROJO)
# ---------------------------------------------------------
def ahora_art():
    return datetime.datetime.now(TZ_ART)

def cargar_estado_previo():
    if os.path.exists(ESTADO_PREVIO_FILE):
        try:
            with open(ESTADO_PREVIO_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def guardar_estado_actual(datos_ws, datos_cripto, sesgo_ws, sesgo_cripto, ultimo_reporte_iso):
    estado = {
        "timestamp": ahora_art().isoformat(),
        "ultimo_reporte_completo": ultimo_reporte_iso,
        "sesgo_ws": sesgo_ws,
        "sesgo_cripto": sesgo_cripto,
        "wall_street": datos_ws,
        "cripto": datos_cripto
    }
    try:
        with open(ESTADO_PREVIO_FILE, "w", encoding="utf-8") as f:
            json.dump(estado, f, indent=4)
    except Exception as e:
        print("Error guardando estado previo: " + str(e))

def obtener_sesion_actual_mercado():
    hora_actual = ahora_art().hour
    if hora_actual == 21:
        return "🪙 CIERRE DIARIO DE VELA CRIPTO (21:00 ART)"
    elif 20 <= hora_actual or hora_actual < 4:
        return "🌏 SESIÓN ASIA (Tokio / Hong Kong)"
    elif 4 <= hora_actual < 10:
        return "🌍 SESIÓN EUROPA (Londres / Frankfurt)"
    else:
        return "🌎 SESIÓN EE. UU. (Wall Street / S&P 500)"

def evaluar_giro_mercado(df_ws, df_cripto, estado_previo):
    peso_total_ws = df_ws['weight'].sum() or 1
    prom_ws = round((df_ws['var'] * df_ws['weight']).sum() / peso_total_ws, 2)
    sesgo_ws_act = "VERDE" if prom_ws >= 0 else "ROJO"

    vol_total_cr = df_cripto['vol'].sum() or 1
    prom_cr = round((df_cripto['var'] * df_cripto['vol']).sum() / vol_total_cr, 2)
    sesgo_cr_act = "VERDE" if prom_cr >= 0 else "ROJO"

    sesgo_ws_prev = estado_previo.get("sesgo_ws")
    sesgo_cr_prev = estado_previo.get("sesgo_cripto")
    prev_cr_dict = estado_previo.get("cripto", {})
    prev_ws_dict = estado_previo.get("wall_street", {})

    alertas_giro = []

    if sesgo_cr_prev and sesgo_cr_prev != sesgo_cr_act:
        icono = "🟢🚀" if sesgo_cr_act == "VERDE" else "🔴⚠️"
        alertas_giro.append(
            f"{icono} <b>MERCADO CRIPTO GIRÓ DE {sesgo_cr_prev} A {sesgo_cr_act}</b> (Índice ponderado: <b>{prom_cr:+.2f}%</b>)"
        )

    if sesgo_ws_prev and sesgo_ws_prev != sesgo_ws_act:
        icono = "🟢📈" if sesgo_ws_act == "VERDE" else "🔴📉"
        alertas_giro.append(
            f"{icono} <b>WALL STREET (S&P 500) GIRÓ DE {sesgo_ws_prev} A {sesgo_ws_act}</b> (Índice: <b>{prom_ws:+.2f}%</b>)"
        )

    lideres_cr = ["BTC", "ETH", "SOL", "BNB", "XRP"]
    for _, r in df_cripto.iterrows():
        t = r['ticker']
        v_act = r['var']
        if t in lideres_cr and t in prev_cr_dict:
            v_prev = prev_cr_dict[t]
            if v_prev < 0 and v_act >= 0.3:
                alertas_giro.append(f"🟢 <b>{t}</b> cruzó a VERDE: {v_prev:+.2f}% ➔ <b>{v_act:+.2f}%</b>")
            elif v_prev > 0 and v_act <= -0.3:
                alertas_giro.append(f"🔴 <b>{t}</b> cruzó a ROJO: {v_prev:+.2f}% ➔ <b>{v_act:+.2f}%</b>")
            elif abs(v_act - v_prev) >= 2.0:
                alertas_giro.append(f"⚡ <b>{t}</b> movimiento brusco: {v_prev:+.2f}% ➔ <b>{v_act:+.2f}%</b>")

    for _, r in df_ws.iterrows():
        t = r['ticker']
        v_act = r['var']
        if t in ["NVDA", "AAPL", "MSFT", "TSLA"] and t in prev_ws_dict:
            v_prev = prev_ws_dict[t]
            if v_prev < 0 and v_act >= 0.3:
                alertas_giro.append(f"🟢 <b>{t}</b> (WS) cruzó a VERDE: {v_prev:+.2f}% ➔ <b>{v_act:+.2f}%</b>")
            elif v_prev > 0 and v_act <= -0.3:
                alertas_giro.append(f"🔴 <b>{t}</b> (WS) cruzó a ROJO: {v_prev:+.2f}% ➔ <b>{v_act:+.2f}%</b>")

    return alertas_giro, sesgo_ws_act, sesgo_cr_act, prom_ws, prom_cr

# ---------------------------------------------------------
# 1. MAPA DE CALOR DE S&P 500 (WALL STREET)
# ---------------------------------------------------------
def obtener_datos_wall_street_treemap():
    acciones = {
        "NVDA": 3.2, "AAPL": 3.4, "MSFT": 3.1, "GOOGL": 2.1, "AMZN": 2.2,
        "META": 1.5, "TSLA": 0.9, "AVGO": 0.9, "JPM": 0.7, "AMD": 0.4,
        "NFLX": 0.4, "INTC": 0.3, "QCOM": 0.3, "PEP": 0.4, "KO": 0.4,
        "DIS": 0.3, "PYPL": 0.2, "CSCO": 0.3
    }
    tickers = list(acciones.keys())
    datos = []
    hist_bulk = None

    try:
        hist_bulk = yf.download(tickers, period="5d", interval="1d", progress=False, threads=True)
    except Exception as e:
        print(f"⚠️ Descarga masiva yfinance falló, usando modo individual: {e}")

    for label, mcap_weight in acciones.items():
        var = 0.0
        try:
            if hist_bulk is not None and not hist_bulk.empty and 'Close' in hist_bulk:
                serie = hist_bulk['Close'][label].dropna()
                if len(serie) >= 2:
                    p_act = float(serie.iloc[-1])
                    p_prev = float(serie.iloc[-2])
                    var = round(((p_act - p_prev) / p_prev) * 100, 2)
            else:
                hist = yf.Ticker(label).history(period="5d")
                if len(hist) >= 2:
                    p_act = float(hist['Close'].iloc[-1])
                    p_prev = float(hist['Close'].iloc[-2])
                    var = round(((p_act - p_prev) / p_prev) * 100, 2)
        except Exception:
            var = 0.0
        datos.append({"ticker": label, "weight": mcap_weight, "var": var})
    return pd.DataFrame(datos)

def generar_treemap_wall_street(df):
    fig, ax = plt.subplots(figsize=(12, 7), facecolor='#0b0e14')
    ax.set_facecolor('#0b0e14')

    sizes = df['weight']
    labels = [f"{row['ticker']}\n{row['var']:+.2f}%" for _, row in df.iterrows()]
    colors = ['#00796b' if v >= 2 else ('#26a69a' if v >= 0 else ('#e53935' if v <= -2 else '#c62828')) for v in df['var']]

    squarify.plot(sizes=sizes, label=labels, color=colors, alpha=0.95,
                  pad=True, edgecolor="#0b0e14", linewidth=2,
                  text_kwargs={'color': 'white', 'fontsize': 9, 'weight': 'bold'}, ax=ax)

    plt.title("MAPA DE CALOR PROFESIONAL — S&P 500 (WALL STREET)", color='#FFD700', fontsize=13, fontweight='bold', pad=15)
    plt.axis('off')
    plt.tight_layout()
    plt.savefig('heatmap_wall_street.png', dpi=300, facecolor=fig.get_facecolor(), edgecolor='none')
    plt.close()

# ---------------------------------------------------------
# 2. MAPA DE CALOR DE CRIPTO (BINANCE MULTI-ENDPOINT)
# ---------------------------------------------------------
def obtener_datos_cripto_treemap():
    criptos = [
        "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT",
        "DOGEUSDT", "ADAUSDT", "AVAXUSDT", "LINKUSDT", "DOTUSDT",
        "POLUSDT", "NEARUSDT", "UNIUSDT", "ATOMUSDT", "LTCUSDT"
    ]
    endpoints = [
        "https://data-api.binance.vision/api/v3/ticker/24hr",
        "https://api.binance.com/api/v3/ticker/24hr",
        "https://api1.binance.com/api/v3/ticker/24hr",
        "https://api3.binance.com/api/v3/ticker/24hr"
    ]
    datos = []
    res_json = None

    for url in endpoints:
        try:
            r = requests.get(url, timeout=8)
            if r.status_code == 200:
                res_json = r.json()
                break
        except Exception as e:
            print(f"⚠️ Falló endpoint Binance {url}: {e}")

    if res_json:
        dict_res = {item['symbol']: item for item in res_json if 'symbol' in item}
        for symbol in criptos:
            if symbol in dict_res:
                item = dict_res[symbol]
                ticker_clean = symbol.replace("USDT", "")
                vol = float(item['quoteVolume'])
                var = round(
