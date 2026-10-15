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

def obtener_calor_del_mercado():
    """Consulta el índice de Miedo y Codicia (Fear & Greed) y evalúa el sentimiento institucional"""
    calor = {
        "score_fg": 50,
        "sentimiento_fg": "Neutral",
        "apuesta_mercado": "Equilibrio / Espera de Catalizador"
    }
    try:
        # API pública de Alternative.me para el Crypto Fear & Greed Index
        url_fg = "https://api.alternative.me/fng/?limit=1"
        res = requests.get(url_fg, timeout=5).json()
        if "data" in res and len(res["data"]) > 0:
            score = int(res["data"][0]["value"])
            clasificacion = res["data"][0]["value_classification"]
            calor["score_fg"] = score
            calor["sentimiento_fg"] = clasificacion
            
            # Interpretar las apuestas de la masa según el índice
            if score <= 25:
                calor["apuesta_mercado"] = "🐻 Pánico Extremo (Oportunidad de Acumulación en Suelo)"
            elif score <= 45:
                calor["apuesta_mercado"] = "⚠️ Miedo / Cautela Moderada"
            elif score <= 55:
                calor["apuesta_mercado"] = "⚖️ Zona Neutral / Indecisión del Mercado"
            elif score <= 75:
                calor["apuesta_mercado"] = "🐂 Codicia / Optimismo Creciente"
            else:
                calor["apuesta_mercado"] = "🚨 Euforia Extrema (Alto Riesgo de Corrección)"
    except Exception:
        pass
        
    return calor

# ---------------------------------------------------------
# INTERPRETACIÓN CON IA (GEMINI)
# ---------------------------------------------------------
def evaluar_clima_mercado_ia(ws, cripto, calor):
    """Genera un diagnóstico macro global y de sentimiento sobre la postura de inversión"""
    if not GEMINI_API_KEY:
        return "⚠️ *Análisis macro de IA no disponible (Falta GEMINI_API_KEY)*"
        
    client = genai.Client(api_key=GEMINI_API_KEY)
    
    prompt = f"""
    Actúa como un estratega macroeconómico global y CIO de un fondo cuantitativo.
    Analiza el estado actual del mercado financiero global y el "calor del mercado" con los siguientes datos:

    MERCADOS TRADICIONALES (WALL STREET & MACRO):
    - S&P 500 (SPX): {ws['SPX']['precio']} ({ws['SPX']['var_pct']}%)
    - Nasdaq (NDX): {ws['NDX']['precio']} ({ws['NDX']['var_pct']}%)
    - Índice de Miedo VIX: {ws['VIX']['precio']} ({ws['VIX']['var_pct']}%)
    - Dólar Global (DXY): {ws['DXY']['precio']} ({ws['DXY']['var_pct']}%)

    MERCADO CRIPTO MACRO:
    - Bitcoin (BTC): ${cripto['BTC']['precio']} ({cripto['BTC']['var_pct']}%)
    - Ethereum (ETH): ${cripto['ETH']['precio']} ({cripto['ETH']['var_pct']}%)

    CALOR DEL MERCADO & SENTIMIENTO (FEAR & GREED):
    - Score: {calor['score_fg']}/100 ({calor['sentimiento_fg']})
    - Postura de apuestas de la masa: {calor['apuesta_mercado']}

    Redacta un diagnóstico conciso en español (máximo 4 líneas) respondiendo:
    1. ¿Cómo contrasta el apetito por riesgo macroeconómico con el "calor del mercado" actual (sentimiento de masas)?
    2. ¿Indica sobreventa (suelo potencial) o sobrecompra (riesgo de reversión)?
    3. Recomendación operativa breve para anticiparse al movimiento de las próximas horas.
    """
    
    for mod in ['gemini-2.5-flash', 'gemini-1.5-flash']:
        try:
            response = client.models.generate_content(model=mod, contents=prompt)
            if response and response.text:
                return response.text
        except Exception:
            continue
            
    return "El sentimiento de mercado muestra divergencia con Wall Street. Se recomienda operar con cautela estricta y validar soportes clave antes de posicionarse."

# ---------------------------------------------------------
# ESCANEO Y PUBLICACIÓN
# ---------------------------------------------------------
print("🌐 Consultando mercados, Wall Street y el Calor del Mercado...")

datos_ws = obtener_datos_wall_street()
datos_cripto = obtener_datos_cripto_macro()
calor_mercado = obtener_calor_del_mercado()

# Estado general del VIX
vix_val = datos_ws['VIX']['precio']
if vix_val >= 25:
    estado_vix = "🚨 ALTO MIEDO EN WALL STREET"
elif vix_val >= 18:
    estado_vix = "⚠️ VOLATILIDAD MODERADA"
else:
    estado_vix = "🟢 CALMA EN LOS MERCADOS"

diagnostico_ia = evaluar_clima_mercado_ia(datos_ws, datos_cripto, calor_mercado)

# Mensaje para Telegram
mensaje = "🏛️ **ALERTAS DE MERCADO GLOBAL — SENTINEL MACRO**\n"
mensaje += f"ESTADO GENERAL: `{estado_vix}` (VIX: `{vix_val}`)\n\n"

mensaje += "🔥 **Calor del Mercado & Sentimiento (Fear & Greed):**\n"
mensaje += f"• Índice: `{calor_mercado['score_fg']}/100` ({calor_mercado['sentimiento_fg']})\n"
mensaje += f"• Apuesta de la Masa: `{calor_mercado['apuesta_mercado']}`\n\n"

mensaje += "💡 **Diagnóstico Global (IA):**\n"
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
        print("✅ Alerta de Mercado Global con Calor del Mercado enviada al topic 'Sentimiento Mercado'.")
    else:
        print(f"[-] Error enviando a Telegram: {res_tg.json()}")

# Guardar estructura JSON para el Trader Autónomo de IA
estructura_macro = {
    "timestamp": pd.Timestamp.now().isoformat(),
    "wall_street": datos_ws,
    "cripto_macro": datos_cripto,
    "calor_mercado": calor_mercado,
    "diagnostico_ia": diagnostico_ia
}
with open("datos_sentinel_macro.json", "w") as f:
    json.dump(estructura_macro, f, indent=4)
