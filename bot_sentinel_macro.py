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
ESTADO_PREVIO_FILE = "datos_sentinel_macro.json"

# ---------------------------------------------------------
# MEMORIA Y COMPARATIVA DE GIROS (DE ROJO A VERDE O VICEVERSA)
# ---------------------------------------------------------
def cargar_estado_previo():
    if os.path.exists(ESTADO_PREVIO_FILE):
        try:
            with open(ESTADO_PREVIO_FILE, "r") as f:
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
    with open(ESTADO_PREVIO_FILE, "w") as f:
        json.dump(estado, f, indent=4)

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
# 1. MAPA DE CALOR PROFESIONAL DE S&P 500 (WALL STREET)
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
# 2. MAPA DE CALOR PROFESIONAL DE CRIPTO (BINANCE)
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
# 3. GENERACIÓN DE DIAGNÓSTICO Y ALERTA (CONSERVANDO FORMATO EXACTO)
# ---------------------------------------------------------
def analizar_wall_street_ia(df_ws, sesion, estado_previo):
    if not GEMINI_API_KEY: 
        return "📊 Diagnóstico: Renta variable operando con volatilidad moderada.\n🚨 Alerta: Mantener cautela en posiciones apalancadas."
    
    client = genai.Client(api_key=GEMINI_API_KEY)
    
    detalle_actual = {r['ticker']: r['var'] for _, r in df_ws.iterrows()}
    prev_ws = estado_previo.get("wall_street", {})
    
    giros = []
    for t, val_act in detalle_actual.items():
        val_prev = prev_ws.get(t, val_act)
        if val_prev < 0 and val_act > 0:
            giros.append(f"{t} cambió de rojo ({val_prev}%) a verde (+{val_act}%)")
        elif val_prev > 0 and val_act < 0:
            giros.append(f"{t} cambió de verde (+{val_prev}%) a rojo ({val_act}%)")

    texto_giros = ", ".join(giros) if giros else "Sin cambios drásticos respecto al reporte anterior."
    datos_txt = ", ".join([f"{r['ticker']}: {r['var']}%" for _, r in df_ws.iterrows()])

    prompt = f"""
    Actúa como un estratega macroeconómico de Wall Street.
    Sesión: {sesion}.
    Variaciones del S&P 500: {datos_txt}.
    Giros recientes detectados: {texto_giros}.

    MANTÉN EXACTAMENTE ESTE FORMATO DE DOS LÍNEAS DIRECTAS:
    📊 Diagnóstico: [Explica en 1 o 2 frases cortas cómo transcurrió el día desde la apertura y qué sector impulsa la sesión]
    🚨 Alerta: [Proporciona un aviso claro de si el mercado apunta a SUBIR o BAJAR en los próximos días y si hubo giro de rojo a verde o viceversa]
    """
    for mod in ['gemini-2.5-flash', 'gemini-1.5-flash']:
        try:
            res = client.models.generate_content(model=mod, contents=prompt)
            if res and res.text: return res.text.strip()
        except: continue
    return "📊 Diagnóstico: Renta variable operando con volatilidad moderada.\n🚨 Alerta: Mantener cautela en posiciones apalancadas."

def analizar_cripto_ia(df_cripto, sesion, estado_previo):
    if not GEMINI_API_KEY: 
        return "📊 Diagnóstico: Mercado buscando estabilización.\n🚨 Alerta: Monitoreando flujos de liquidez."
    
    client = genai.Client(api_key=GEMINI_API_KEY)
    
    detalle_actual = {r['ticker']: r['var'] for _, r in df_cripto.iterrows()}
    prev_cripto = estado_previo.get("cripto", {})
    
    giros = []
    for t, val_act in detalle_actual.items():
        val_prev = prev_cripto.get(t, val_act)
        if val_prev < 0 and val_act > 0:
            giros.append(f"{t} giró de ROJO ({val_prev}%) a VERDE (+{val_act}%)")
        elif val_prev > 0 and val_act < 0:
            giros.append(f"{t} giró de VERDE (+{val_prev}%) a ROJO ({val_act}%)")

    texto_giros = ", ".join(giros) if giros else "Sin giros drásticos en los últimos minutos."
    datos_txt = ", ".join([f"{r['ticker']}: {r['var']}%" for _, r in df_cripto.iterrows()])

    prompt = f"""
    Actúa como un analista cuantitativo de criptomonedas.
    Sesión: {sesion}.
    Estado de Binance: {datos_txt}.
    Giros de polaridad detectados: {texto_giros}.

    MANTÉN EXACTAMENTE ESTE FORMATO DE DOS LÍNEAS DIRECTAS:
    📊 Diagnóstico: [Explica en 1 o 2 frases cortas la evolución de la vela diaria desde el inicio y qué monedas absorben volumen]
    🚨 Alerta: [Da una alerta clara sobre la dirección proyectada para los próximos días (Alcista/Bajista) destacando giros de rojo a verde]
    """
    for mod in ['gemini-2.5-flash', 'gemini-1.5-flash']:
        try:
            res = client.models.generate_content(model=mod, contents=prompt)
            if res and res.text: return res.text.strip()
        except: continue
    return "📊 Diagnóstico: Mercado buscando estabilización.\n🚨 Alerta: Monitoreando flujos de liquidez."

# ---------------------------------------------------------
# 4. EJECUCIÓN Y ENVÍO A TELEGRAM (CONFORMATO IDÉNTICO)
# ---------------------------------------------------------
print("🌐 Ejecutando Sentinel Macro...")

sesion_actual = obtener_sesion_actual_mercado()
estado_previo = cargar_estado_previo()

# --- 1. S&P 500 / WALL STREET ---
df_ws = obtener_datos_wall_street_treemap()
generar_treemap_wall_street(df_ws)
causas_ws = analizar_wall_street_ia(df_ws, sesion_actual, estado_previo)

msg_ws = f"🏛️ **SENTINEL MACRO — 1. S&P 500 & TRADFI**\n"
msg_ws += f"🕒 **Sesión:** 🌎 `{sesion_actual}`\n\n"
msg_ws += f"{causas_ws}\n"

# --- 2. CRIPTO / BINANCE ---
df_cripto = obtener_datos_cripto_treemap()
generar_treemap_cripto(df_cripto)
causas_cripto = analizar_cripto_ia(df_cripto, sesion_actual, estado_previo)

msg_cripto = f"🪙 **SENTINEL MACRO — 2. BINANCE CRIPTO MARKET**\n"
msg_cripto += f"🕒 **Sesión:** 🌎 `{sesion_actual}`\n\n"
msg_cripto += f"{causas_cripto}\n"

# Guardar estado para la comparativa histórica del siguiente ciclo
dict_ws_save = {r['ticker']: r['var'] for _, r in df_ws.iterrows()}
dict_cripto_save = {r['ticker']: r['var'] for _, r in df_cripto.iterrows()}
guardar_estado_actual(dict_ws_save, dict_cripto_save)

# --- ENVÍO A TELEGRAM ---
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

    print("✅ Mensajes enviados manteniendo exactamente el diseño actual.")
