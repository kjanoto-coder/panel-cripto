import os
import json
import requests
import ccxt
import pandas as pd
import matplotlib.pyplot as plt
from google import genai

# ---------------------------------------------------------
# CONFIGURACIÓN DE CREDENCIALES
# ---------------------------------------------------------
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("CHAT_ID")
MESSAGE_THREAD_ID = os.getenv("TOPIC_ID_PRE_EXPLOSION")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

NETLIFY_BASE_URL = "https://tu-nuevo-motor-pre-explosion.netlify.app"

# ---------------------------------------------------------
# FUNCIONES AUXILIARES
# ---------------------------------------------------------
def obtener_barras_fuerza(ratio_volumen):
    if ratio_volumen >= 5.0:
        return "🟢🟢🟢🟢🟢"
    elif ratio_volumen >= 4.0:
        return "🟢🟢🟢🟢⚪"
    elif ratio_volumen >= 3.0:
        return "🟢🟢🟢⚪⚪"
    else:
        return "🟢🟢⚪⚪⚪"

def formatear_precio(precio):
    if precio < 0.01:
        return f"${precio:.6f}"
    elif precio < 1.0:
        return f"${precio:.4f}"
    else:
        return f"${precio:.2f}"

def generar_grafico_barras(candidatas):
    """Genera una imagen con el gráfico de barras del Top 7 ordenado de menor a mayor"""
    # Ordenar de menor a mayor para el gráfico
    candidatas_ordenadas = sorted(candidatas, key=lambda x: x['score'])
    tickers = [c['ticker'] for c in candidatas_ordenadas]
    scores = [c['score'] for c in candidatas_ordenadas]
    
    plt.figure(figsize=(8, 4))
    plt.style.use('dark_background')
    
    bars = plt.bar(tickers, scores, color='#00E676')
    plt.title('TOP 7 PRE-EXPLOSIÓN — Score de Acumulación (Volumen 1H)', fontsize=12, color='white', pad=15)
    plt.xlabel('Criptomoneda', fontsize=10, color='gray')
    plt.ylabel('Score', fontsize=10, color='gray')
    plt.grid(axis='y', linestyle='--', alpha=0.3)
    
    # Añadir los valores encima de las barras
    for bar in bars:
        yval = bar.get_height()
        plt.text(bar.get_x() + bar.get_width()/2.0, yval + 0.2, f"{yval:.1f}", ha='center', va='bottom', color='white', fontsize=9)
        
    plt.tight_layout()
    plt.savefig('grafico_pre_explosion.png', dpi=200)
    plt.close()

def generar_resumen_ia(candidatas):
    """Usa Gemini para redactar el análisis experto del Top 7"""
    if not GEMINI_API_KEY:
        return "⚠️ *Análisis de IA no disponible (Falta configurar GEMINI_API_KEY)*"
        
    client = genai.Client(api_key=GEMINI_API_KEY)
    
    lista_texto = "\n".join([f"- {c['ticker']}: Precio: {c['price']}, Var 24h: {c['price_change']}%, Vol 1H: {c['ratio_volumen']}x, Score: {c['score']}" for c in candidatas])
    
    prompt = f"""
    Actúa como un trader cuantitativo experto en criptomonedas. 
    He detectado mediante un escáner de anomalías de volumen en Binance las siguientes 7 criptomonedas en fase de pre-explosión (acumulación silenciosa sin ruptura de precio aún):
    
    {lista_texto}
    
    Redacta un análisis ejecutivo breve (máximo 4 líneas) en español que cumpla con:
    1. Explique brevemente por qué estas monedas muestran acumulación de volumen y potencial de ruptura.
    2. Identifique claramente CUÁL de las 7 (la de mayor score o métricas más sólidas) tiene la mayor probabilidad de romper al alza primero.
    Sé directo, profesional y claro.
    """
    try:
        response = client.models.generate_content(model='gemini-2.5-flash', contents=prompt)
        return response.text
    except Exception as e:
        return f"No se pudo generar el resumen de IA: {e}"

# ---------------------------------------------------------
# ESCÁNER DE VOLUMEN (BINANCE SPOT)
# ---------------------------------------------------------
print("🚀 Iniciando escaneo de Criptos Pre-Explosión...")

exchange = ccxt.binance({
    'enableRateLimit': True,
    'options': {'defaultType': 'spot', 'fetchMarkets': ['spot']},
    'urls': {'api': {'public': 'https://data-api.binance.vision/api/v3', 'spot': 'https://data-api.binance.vision/api/v3'}}
})

tickers = exchange.fetch_tickers()
total_pares_analizados = len(tickers)

candidatas_pre_explosion = []

for symbol, data in tickers.items():
    if not symbol.endswith('/USDT'):
        continue
        
    price_change_24h = data['percentage'] if data['percentage'] is not None else 0
    vol_24h = data['quoteVolume'] if data['quoteVolume'] is not None else 0
    last_price = data['last'] if data['last'] is not None else 0
    
    if 0 <= price_change_24h <= 5.0 and vol_24h > 100000 and last_price > 0:
        try:
            ohlcv = exchange.fetch_ohlcv(symbol, timeframe='1h', limit=24)
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            
            vol_actual_1h = df['volume'].iloc[-1]
            promedio_vol_24h = df['volume'].mean()
            
            if promedio_vol_24h > 0 and vol_actual_1h >= (promedio_vol_24h * 2.5):
                ratio_volumen = round(vol_actual_1h / promedio_vol_24h, 2)
                ticker_limpio = symbol.split('/')[0]
                score = round(ratio_volumen * (5.1 - price_change_24h), 2)
                
                candidatas_pre_explosion.append({
                    'symbol': symbol,
                    'ticker': ticker_limpio,
                    'price': last_price,
                    'price_change': round(price_change_24h, 2),
                    'ratio_volumen': ratio_volumen,
                    'score': score
                })
        except Exception:
            continue

# Tomar el Top 7 y ordenarlos de mayor a menor score para la lista de texto
top_7_candidatas = sorted(candidatas_pre_explosion, key=lambda x: x['score'], reverse=True)[:7]

if top_7_candidatas:
    # Generar gráfico de barras
    generar_grafico_barras(top_7_candidatas)
    
    # Generar resumen de IA
    resumen_ia = generar_resumen_ia(top_7_candidatas)
    
    # Construcción del mensaje
    mensaje_telegram = "🧠 **CENTRAL DE INTELIGENCIA DE MERCADO**\n"
    mensaje_telegram += f"🚀 **TOP 7 PRE-EXPLOSIÓN (Detección Temprana)**\n"
    mensaje_telegram += f"🔍 *Pares analizados en Binance:* `{total_pares_analizados}`\n\n"
    
    mensaje_telegram += f"💡 **Análisis y Proyección (IA):**\n{resumen_ia}\n\n"
    mensaje_telegram += "─────────────────────────\n"
    
    for coin in top_7_candidatas:
        precio_fmt = formatear_precio(coin['price'])
        barras = obtener_barras_fuerza(coin['ratio_volumen'])
        url_netlify = f"{NETLIFY_BASE_URL}/?coin={coin['ticker']}"
        url_binance = f"https://www.binance.com/es/trade/{coin['ticker']}_USDT?type=spot"
        
        mensaje_telegram += (
            f"• **{coin['ticker']}** | `{precio_fmt}` | {barras} | `+{coin['price_change']}%`\n"
            f"   └ 📊 [Resumen IA]({url_netlify}) | 🔶 [Tradear]({url_binance}) | Vol 1H: `{coin['ratio_volumen']}x` | Score: `{coin['score']}`\n\n"
        )

    # Enviar Imagen del Gráfico Primero
    if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
        url_foto = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
        with open('grafico_pre_explosion.png', 'rb') as foto:
            payload_foto = {
                'chat_id': TELEGRAM_CHAT_ID,
                'caption': "📊 **Gráfico Comparativo — Score de Acumulación Pre-Explosión**",
                'parse_mode': 'Markdown'
            }
            if MESSAGE_THREAD_ID:
                payload_foto['message_thread_id'] = int(MESSAGE_THREAD_ID)
            requests.post(url_foto, data=payload_foto, files={'photo': foto})

        # Enviar Mensaje de Texto con el Listado y el Análisis de IA
        url_msg = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload_msg = {
            'chat_id': TELEGRAM_CHAT_ID,
            'text': mensaje_telegram,
            'parse_mode': 'Markdown',
            'disable_web_page_preview': True
        }
        if MESSAGE_THREAD_ID:
            payload_msg['message_thread_id'] = int(MESSAGE_THREAD_ID)
        requests.post(url_msg, json=payload_msg)
        
        print("✅ Reporte completo con gráfico y análisis IA enviado a Telegram.")

# Exportar JSON para IA
estructura_ia = {
    "timestamp": pd.Timestamp.now().isoformat(),
    "bot_origen": "Criptos Pre-Explosión",
    "total_analizados": total_pares_analizados,
    "top_candidatas": top_7_candidatas
}
with open("datos_pre_explosion_ia.json", "w") as f:
    json.dump(estructura_ia, f, indent=4)
