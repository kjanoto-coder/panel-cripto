import os
import json
import requests
import yfinance as yf
import pandas as pd
from google import genai

# ---------------------------------------------------------
# CONFIGURACIÓN DE CREDENCIALES
# ---------------------------------------------------------
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("CHAT_ID")
# Tomamos el ID del topic específico para Sentimiento Mercado (2489)
MESSAGE_THREAD_ID = os.getenv("TOPIC_ID_SENTINEL_MACRO")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# ---------------------------------------------------------
# RASTREO DE MERCADOS TRADICIONALES (WALL STREET & MACRO)
# ---------------------------------------------------------
def obtener_datos_wall_street():
    """Descarga cotizaciones e índices clave de Yahoo Finance"""
    tickers_macro = {
        "SPX": "^GSPC",    # S&P 500
        "NDX": "^IXIC",    # Nasdaq 100
        "VIX": "^VIX",     # Índice de Volatilidad / Miedo
        "DXY": "DX-Y.NYB", # Índice del Dólar Estadounidense
        "US10Y": "^TNX",   # Rendimiento del Bono a 10 años EE.UU.
        "GOLD": "GC=F"     # Oro
    }
    
    resultados = {}
    
    for nombre, sym in tickers_macro.items():
        try:
            ticker = yf.Ticker(sym)
            hist = ticker.history(period="2d")
            if len(hist) >= 2:
                precio_actual = hist['Close'].iloc[-1]
                precio_previo = hist['Close'].iloc[-2]
                var_pct = round(((precio_actual - precio_previo) / precio_previo) * 100, 2)
                resultados[nombre] = {"precio": round(precio_actual, 2), "var_pct": var_pct}
            else:
                resultados[nombre] = {"precio": 0, "var_pct": 0}
        except Exception:
            resultados[nombre] = {"precio": 0, "var_pct": 0}
            
    return resultados

def obtener_datos_cripto_macro():
    """Descarga datos macro de Bitcoin y Ethereum"""
    resultados = {}
    try:
        url = "https://data-api.binance.vision/api/v3/ticker/24hr"
        res = requests.get(url, timeout=5).json()
        
        for item in res:
            if item['symbol'] == 'BTCUSDT':
                resultados['BTC'] = {
                    "precio": round(float(item['lastPrice']), 2),
                    "var_pct": round(float(item['priceChangePercent']), 2)
                }
            elif item['symbol'] == 'ETHUSDT':
                resultados['ETH'] = {
                    "precio": round(float(item['lastPrice']), 2),
                    "var_pct": round(float(item['priceChangePercent']), 2)
                }
    except Exception:
        resultados['BTC'] = {"precio": 0, "var_pct": 0}
        resultados['ETH'] = {"precio": 0, "var_pct": 0}
        
    return resultados

# ---------------------------------------------------------
# INTERPRETACIÓN CON IA (GEMINI)
# ---------------------------------------------------------
def evaluar_clima_mercado_ia(ws, cripto):
    """Genera un diagnóstico macro global sobre la postura de inversión (Risk-On vs Risk-Off)"""
    if not GEMINI_API_KEY:
        return "⚠️ *Análisis macro de IA no disponible (Falta GEMINI_API_KEY)*"
        
    client = genai.Client(api_key=GEMINI_API_KEY)
    
    prompt = f"""
    Actúa como un estratega macroeconómico global y CIO de un fondo de cobertura (Hedge Fund).
    Analiza el estado actual del mercado financiero global con los siguientes datos:

    MERCADOS TRADICIONALES (WALL STREET & MACRO):
    - S&P 500 (SPX): {ws['SPX']['precio']} ({ws['SPX']['var_pct']}%)
    - Nasdaq (NDX): {ws['NDX']['precio']} ({ws['NDX']['var_pct']}%)
    - Índice de Miedo VIX: {ws['VIX']['precio']} ({ws['VIX']['var_pct']}%)
    - Dólar Global (DXY): {ws['DXY']['precio']} ({ws['DXY']['var_pct']}%)
    - Rendimiento Bonos 10 Años (US10Y): {ws['US10Y']['precio']}% ({ws['US10Y']['var_pct']}%)
    - Oro: ${ws['GOLD']['precio']} ({ws['GOLD']['var_pct']}%)

    MERCADO CRIPTO MACRO:
    - Bitcoin (BTC): ${cripto['BTC']['precio']} ({cripto['BTC']['var_pct']}%)
    - Ethereum (ETH): ${cripto['ETH']['precio']} ({cripto['ETH']['var_pct']}%)

    Redacta un diagnóstico conciso en español (máximo 4 líneas) respondiendo:
    1. ¿El clima global es **Risk-On** (Apetito por Riesgo) o **Risk-Off** (Pánico/Refugio)? Justifica usando VIX y DXY.
    2. ¿Cómo impacta el comportamiento de Wall Street sobre Bitcoin y las Altcoins en las próximas horas?
    3. Conclusión con una recomendación operativa breve (ej. Aumentar liquidez, Operar rupturas con cautela, Búsqueda de coberturas).
    """
    
    for mod in ['gemini-2.5-flash', 'gemini-1.5-flash']:
        try:
            response = client.models.generate_content(model=mod, contents=prompt)
            if response and response.text:
                return response.text
        except Exception:
            continue
            
    return "El mercado opera bajo prudencia. Monitorear la correlación entre el DXY y Bitcoin antes de aperturar nuevas operaciones de riesgo."

# ---------------------------------------------------------
# ESCANEO Y PUBLICACIÓN
# ---------------------------------------------------------
print("🌐 Consultando mercados de Wall Street y Cripto...")

datos_ws = obtener_datos_wall_street()
datos_cripto = obtener_datos_cripto_macro()

# Estado general del VIX
vix_val = datos_ws['VIX']['precio']
if vix_val >= 25:
    estado_vix = "🚨 ALTO MIEDO EN WALL STREET"
elif vix_val >= 18:
    estado_vix = "⚠️ VOLATILIDAD MODERADA"
else:
    estado_vix = "🟢 CALMA EN LOS MERCADOS"

diagnostico_ia = evaluar_clima_mercado_ia(datos_ws, datos_cripto)

# Mensaje para Telegram
mensaje = "🏛️ **ALERTAS DE MERCADO GLOBAL — SENTINEL MACRO**\n"
mensaje += f"ESTADO GENERAL: `{estado_vix}` (VIX: `{vix_val}`)\n\n"

mensaje += "💡 **Diagnóstico Macro Global (IA):**\n"
mensaje += f"{diagnostico_ia}\n\n"

mensaje += "─────────────────────────\n"
mensaje += "📈 **MERCADOS TRADICIONALES (WALL STREET)**\n"
mensaje += f"• **S&P 500 (SPX):** `{datos_ws['SPX']['precio']}` | `{datos_ws['SPX']['var_pct']}%`\n"
mensaje += f"• **Nasdaq (NDX):** `{datos_ws['NDX']['precio']}` | `{datos_ws['NDX']['var_pct']}%`\n"
mensaje += f"• **Índice Dólar (DXY):** `{datos_ws['DXY']['precio']}` | `{datos_ws['DXY']['var_pct']}%`\n"
mensaje += f"• **Bonos US 10Y:** `{datos_ws['US10Y']['precio']}%` | `{datos_ws['US10Y']['var_pct']}%`\n"
mensaje += f"• **Oro:** `${datos_ws['GOLD']['precio']}` | `{datos_ws['GOLD']['var_pct']}%`\n\n"

mensaje += "🪙 **MERCADO CRIPTO MACRO**\n"
mensaje += f"• **Bitcoin (BTC):** `${datos_cripto['BTC']['precio']}` | `{datos_cripto['BTC']['var_pct']}%`\n"
mensaje += f"• **Ethereum (ETH):** `${datos_cripto['ETH']['precio']}` | `{datos_cripto['ETH']['var_pct']}%`\n"

# Enviar a Telegram dirigiendo al topic específico (Sentimiento Mercado / 2489)
if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
    url_msg = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload_msg = {
        'chat_id': TELEGRAM_CHAT_ID,
        'text': mensaje,
        'parse_mode': 'Markdown',
        'disable_web_page_preview': True
    }
    if MESSAGE_THREAD_ID:
        payload_msg['message_thread_id'] = int(MESSAGE_THREAD_ID)
        
    res_tg = requests.post(url_msg, json=payload_msg)
    if res_tg.json().get("ok"):
        print("✅ Alerta de Mercado Global enviada exitosamente al topic 'Sentimiento Mercado'.")
    else:
        print(f"[-] Error enviando a Telegram: {res_tg.json()}")

# Guardar estructura JSON para el Trader Autónomo de IA
estructura_macro = {
    "timestamp": pd.Timestamp.now().isoformat(),
    "wall_street": datos_ws,
    "cripto_macro": datos_cripto,
    "diagnostico_ia": diagnostico_ia
}
with open("datos_sentinel_macro.json", "w") as f:
    json.dump(estructura_macro, f, indent=4)
