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

def generar_grafico_estilo_exacto(candidatas):
    """Genera un gráfico idéntico al estilo de las ganadoras (barras verticales, fondo oscuro, texto y porcentajes)"""
    # Ordenar de menor a mayor score para que las barras crezcan de izquierda a derecha
    candidatas_ordenadas = sorted(candidatas, key=lambda x: x['score'])
    tickers = [c['ticker'] for c in candidatas_ordenadas]
    scores = [c['score'] for c in candidatas_ordenadas]
    # Usaremos el ratio de volumen o score como valor visual superior, ej: "+4.5x" o el score
    etiquetas_pct = [f"+{c['ratio_volumen']}x" for c in candidatas_ordenadas]

    # Configuración de la figura con el fondo oscuro exacto
    fig, ax = plt.subplots(figsize=(10, 5.5), facecolor='#0b0e14')
    ax.set_facecolor('#0b0e14')

    # Dibujar barras verdes verticales
    bars = ax.bar(tickers, scores, color='#00E676', width=0.45)

    # Título superior idéntico al estilo de tu imagen de referencia
    ax.text(0.02, 0.93, "🔥 TOP 7 PRE-EXPLOSIÓN • Ranking de Acumulación 1H", 
            transform=ax.transAxes, fontsize=12, fontweight='bold', color='#FFD700')

    # Ocultar bordes innecesarios para dejar un aspecto limpio y profesional
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.spines['left'].set_visible(False)
    ax.spines['bottom'].set_color('#21262D')
    
    # Eje Y invisible para centrar la atención en las barras
    ax.yaxis.set_visible(False)
    
    # Personalizar etiquetas del eje X (nombre de la moneda abajo)
    ax.tick_params(axis='x', colors='white', labelsize=11, length=0)
    ax.grid(axis='y', visible=False)

    # Ajustar límites para dar espacio arriba a los porcentajes
    max_score = max(scores) if scores else 10
    ax.set_ylim(0, max_score * 1.25)

    # Añadir los porcentajes flotantes arriba de cada barra con estilo limpio
    for bar, etiqueta in zip(bars, etiquetas_pct):
        height = bar.get_height()
        ax.annotate(etiqueta,
                    xy=(bar.get_x() + bar.get_width() / 2, height),
                    xytext=(0, 8),
                    textcoords="offset points",
                    ha='center', va='bottom',
                    fontsize=10, fontweight='bold', color='#00E676')

    plt.tight_layout()
    plt.savefig('grafico_pre_explosion.png', dpi=250, facecolor=fig.get_facecolor(), edgecolor='none')
    plt.close()

def generar_resumen_ia(candidatas):
    """Genera el resumen analítico utilizando el modelo Gemini actualizado"""
    if not GEMINI_API_KEY:
        return "⚠️ *Análisis de IA no disponible (Falta configurar GEMINI_API_KEY)*"
        
    client = genai.Client(api_key=GEMINI_API_KEY)
    
    lista_texto = "\n".join([f"- {c['ticker']}: Precio: {c['price']}, Var 24h: {c['price_change']}%, Vol 1H: {c['ratio_volumen']}x, Score: {c['score']}" for c in candidatas])
    
    prompt = f"""
    Actúa como un analista cuantitativo de criptomonedas.
    He detectado mediante un escáner en Binance las siguientes 7 criptomonedas en fase de pre-explosión (acumulación silenciosa):

    {lista_texto}

    Redacta un análisis breve (máximo 3-4 líneas) en español respondiendo:
    1. Por qué estas monedas muestran acumulación anómala de volumen en 1H sin disparar su precio.
    2. Cuál de las 7 (indica el ticker) tiene la mayor probabilidad técnica de despegue inmediato basándose en su score.
    Sé conciso y claro.
    """
    
    for mod in ['gemini-2.5-flash', 'gemini-1.5-flash']:
        try:
            response = client.models.generate_content(model=mod, contents=prompt)
            if response and response.text:
                return response.text
        except Exception:
            continue
            
    top_coin = candidatas[0]['ticker']
    return f"Las candidatas seleccionadas muestran un incremento anómalo de volumen comprador en la última hora sin ruptura de precio aún. La criptomoneda **{top_coin}** lidera el ranking con el mayor volumen relativo y score de acumulación, siendo la principal candidata para una ruptura al alza."

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

top_7_candidatas = sorted(candidatas_pre_explosion, key=lambda x: x['score'], reverse=True)[:7]

if top_7_candidatas:
    # 1. Generar gráfico con el diseño exacto de barras verticales y nombres abajo
    generar_grafico_estilo_exacto(top_7_candidatas)
    
    # 2. Generar análisis de IA
    resumen_ia = generar_resumen_ia(top_7_candidatas)
    
    # 3. Construcción del texto para Telegram
    mensaje_telegram = "🧠 **CENTRAL DE INTELIGENCIA DE MERCADO**\n"
    mensaje_telegram += "🚀 **TOP 7 PRE-EXPLOSIÓN (Detección Temprana)**\n"
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

    # 4. Enviar Imagen del Gráfico Primero
    if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
        url_foto = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
        with open('grafico_pre_explosion.png', 'rb') as foto:
            payload_foto = {
                'chat_id': TELEGRAM_CHAT_ID,
                'caption': "📊 **TOP 7 PRE-EXPLOSIÓN — Ranking de Acumulación**",
                'parse_mode': 'Markdown'
            }
            if MESSAGE_THREAD_ID:
                payload_foto['message_thread_id'] = int(MESSAGE_THREAD_ID)
            requests.post(url_foto, data=payload_foto, files={'photo': foto})

        # 5. Enviar Texto con el Desglose y Análisis de IA
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
        
        print("✅ Reporte completo con gráfico idéntico enviado a Telegram.")

# Exportar JSON para IA
estructura_ia = {
    "timestamp": pd.Timestamp.now().isoformat(),
    "bot_origen": "Criptos Pre-Explosión",
    "total_analizados": total_pares_analizados,
    "top_candidatas": top_7_candidatas
}
with open("datos_pre_explosion_ia.json", "w") as f:
    json.dump(estructura_ia, f, indent=4)
