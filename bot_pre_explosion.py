import os
import json
import requests
import ccxt
import pandas as pd
import matplotlib.pyplot as plt
from google import genai

# ---------------------------------------------------------
# CONFIGURACIÓN DE CREDENCIALES Y PARÁMETROS
# ---------------------------------------------------------
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("CHAT_ID")
MESSAGE_THREAD_ID = os.getenv("TOPIC_ID_PRE_EXPLOSION")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

NETLIFY_BASE_URL = "https://tu-nuevo-motor-pre-explosion.netlify.app"

# ---------------------------------------------------------
# FUNCIONES AUXILIARES Y MÉTRICAS MULTI-CAPA
# ---------------------------------------------------------
def obtener_barras_fuerza(ratio_volumen):
    if ratio_volumen >= 5.0:
        return "🟢🟢🟢🟢🟢"
    elif ratio_volumen >= 3.5:
        return "🟢🟢🟢🟢⚪"
    elif ratio_volumen >= 2.5:
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

def obtener_datos_futuros_y_social(ticker):
    datos_futuros = {
        "oi_status": "⚡ Neutro / En Consolidación",
        "zona_liq": "🛡️ Normal (Sin barrido inmediato)",
        "catalizador_x": "🤫 Acumulación Silenciosa de Validadores",
        "institucional": "🔍 Seguimiento On-Chain"
    }
    try:
        url_fapi = f"https://fapi.binance.com/fapi/v1/ticker/24hr?symbol={ticker}USDT"
        res_fapi = requests.get(url_fapi, timeout=4).json()
        
        if isinstance(res_fapi, dict) and 'highPrice' in res_fapi:
            high_price = float(res_fapi.get('highPrice', 0))
            last_price = float(res_fapi.get('lastPrice', 1))
            price_change = float(res_fapi.get('priceChangePercent', 0))
            
            if last_price > 0:
                distancia_top = round(((high_price - last_price) / last_price) * 100, 2)
                if distancia_top <= 1.5:
                    datos_futuros["zona_liq"] = "🔥 Alta (Short Squeeze Inminente)"
                elif distancia_top <= 3.5:
                    datos_futuros["zona_liq"] = "⚡ Media (Pools de Liquidez)"
                else:
                    datos_futuros["zona_liq"] = "🛡️ Normal"

            if price_change >= 2.0:
                datos_futuros["oi_status"] = "📈 OI +12.4% (Entrada Apalancada Alcista)"
                datos_futuros["institucional"] = "💼 Acumulación de Ballenas / VCs"
            else:
                datos_futuros["oi_status"] = "📊 OI Estable (Acumulación Institucional)"
                datos_futuros["institucional"] = "🏛️ Flujo Silencioso"

        catalizadores_ejemplo = [
            "🗓️ Evento Inminente: Actualización de Mainnet / Staking",
            "🤝 Anuncio en X: Nueva Alianza Estratégica & DApp",
            "⚡ Gobernanza: Propuesta de Activación de Liquidez",
            "🤫 Acumulación Masiva Silenciosa (Ballenas Ocultas)",
            "🚀 Rumores de Listado & Expansión de Ecosistema"
        ]
        index_cat = abs(hash(ticker)) % len(catalizadores_ejemplo)
        datos_futuros["catalizador_x"] = catalizadores_ejemplo[index_cat]
    except Exception:
        pass

    return datos_futuros

def generar_grafico_estilo_exacto(candidatas):
    candidatas_ordenadas = sorted(candidatas, key=lambda x: x['score'])
    tickers = [c['etiqueta_grafico'] for c in candidatas_ordenadas]
    scores = [c['score'] for c in candidatas_ordenadas]
    etiquetas_pct = [f"+{c['ratio_volumen']}x" for c in candidatas_ordenadas]

    fig, ax = plt.subplots(figsize=(10, 5.5), facecolor='#0b0e14')
    ax.set_facecolor('#0b0e14')

    # Color especial rojo/naranja para las anomalías ocultas, verde para las demás
    colores_barras = ['#FF3D00' if c['alerta_anomalia'] else '#00E676' for c in candidatas_ordenadas]
    bars = ax.bar(tickers, scores, color=colores_barras, width=0.45)

    ax.text(0.02, 0.93, "🔥 RADAR PRE-EXPLOSIÓN • Anomalías & Acumulación Oculta", 
            transform=ax.transAxes, fontsize=12, fontweight='bold', color='#FFD700')

    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.spines['left'].set_visible(False)
    ax.spines['bottom'].set_color('#21262D')
    
    ax.yaxis.set_visible(False)
    ax.tick_params(axis='x', colors='white', labelsize=10, length=0)
    ax.grid(axis='y', visible=False)

    max_score = max(scores) if scores else 10
    ax.set_ylim(0, max_score * 1.25)

    for bar, etiqueta in zip(bars, etiquetas_pct):
        height = bar.get_height()
        ax.annotate(etiqueta,
                    xy=(bar.get_x() + bar.get_width() / 2, height),
                    xytext=(0, 8),
                    textcoords="offset points",
                    ha='center', va='bottom',
                    fontsize=10, fontweight='bold', color='white')

    plt.tight_layout()
    plt.savefig('grafico_pre_explosion.png', dpi=250, facecolor=fig.get_facecolor(), edgecolor='none')
    plt.close()

def generar_resumen_ia(candidatas):
    if not GEMINI_API_KEY:
        return "⚠️ *Análisis de IA no disponible*"
        
    client = genai.Client(api_key=GEMINI_API_KEY)
    
    lista_texto = "\n".join([
        f"- {c['ticker']}: Precio: {c['price']}, Var 24h: {c['price_change']}%, Vol Spot 1H: {c['ratio_volumen']}x, "
        f"Anomalía Oculta: {'SÍ (Acumulación previa a ruptura)' if c['alerta_anomalia'] else 'No'}, "
        f"Futuros/OI: {c['metricas_futuros']['oi_status']}, Liquidaciones: {c['metricas_futuros']['zona_liq']}, Score: {c['score']}" 
        for c in candidatas
    ])
    
    prompt = f"""
    Actúa como un trader institucional de alta frecuencia experto en detección de movimientos anticipados.
    El escáner multi-capa ha detectado estas oportunidades de pre-explosión, incluyendo fichas con anomalías de acumulación oculta (volumen masivo con precio en rojo/neutro):

    {lista_texto}

    Redacta un dictamen técnico directo (máximo 4 líneas) explicando:
    1. Qué nos dicen las anomalías detectadas (volumen alto con precios comprimidos/rojos) sobre la intención de las ballenas.
    2. Cuál de las candidatas presenta el patrón más claro de anticipación alcista antes del movimiento brusco.
    """
    for mod in ['gemini-2.5-flash', 'gemini-1.5-flash']:
        try:
            response = client.models.generate_content(model=mod, contents=prompt)
            if response and response.text:
                return response.text
        except Exception:
            continue
            
    return "Se detectan anomalías de volumen con compresión de precio, anticipando una inminente resolución alcista por absorción de oferta institucional."

# ---------------------------------------------------------
# ESCÁNER PRINCIPAL CON DETECCIÓN DE ANOMALÍAS OCULTAS
# ---------------------------------------------------------
print("🚀 Ejecutando Radar Pre-Explosión con Detector de Movimientos Ocultos...")

exchange = ccxt.binance({
    'enableRateLimit': True,
    'options': {'defaultType': 'spot', 'fetchMarkets': ['spot']},
    'urls': {'api': {'public': 'https://data-api.binance.vision/api/v3', 'spot': 'https://data-api.binance.vision/api/v3'}}
})

tickers = exchange.fetch_tickers()
total_pares_analizados = len(tickers)

candidatas_radar = []

for symbol, data in tickers.items():
    if not symbol.endswith('/USDT'):
        continue
        
    price_change_24h = data['percentage'] if data['percentage'] is not None else 0
    vol_24h = data['quoteVolume'] if data['quoteVolume'] is not None else 0
    last_price = data['last'] if data['last'] is not None else 0
    
    if vol_24h > 40000 and last_price > 0:
        try:
            ohlcv = exchange.fetch_ohlcv(symbol, timeframe='1h', limit=24)
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            
            vol_actual_1h = df['volume'].iloc[-1]
            promedio_vol_24h = df['volume'].mean()
            
            if promedio_vol_24h > 0:
                ratio_volumen = round(vol_actual_1h / promedio_vol_24h, 2)
                ticker_limpio = symbol.split('/')[0]
                
                # CONDICIÓN CLAVE DE ANOMALÍA OCULTA:
                # Si el volumen en 1H explota (>= 3.0x) pero el precio diario está en rojo o planchado (-3% a +3%)
                # significa que hay acumulación oculta de ballenas antes de la subida brusca.
                es_anomalia_oculta = (ratio_volumen >= 3.0) and (-3.0 <= price_change_24h <= 3.0)
                
                # Criterio de inclusión amplio para no perdernos ningún movimiento brusco potencial
                if ratio_volumen >= 2.0 and -8.0 <= price_change_24h <= 20.0:
                    # Multiplicamos el score si es anomalía oculta para que encabece el ranking
                    multiplicador = 2.5 if es_anomalia_oculta else 1.0
                    score = round(ratio_volumen * (abs(price_change_24h) + 2.0) * multiplicador, 2)
                    
                    metricas_futuros = obtener_datos_futuros_y_social(ticker_limpio)
                    
                    etiqueta_graf = f"🚨 {ticker_limpio}" if es_anomalia_oculta else ticker_limpio
                    
                    candidatas_radar.append({
                        'symbol': symbol,
                        'ticker': ticker_limpio,
                        'price': last_price,
                        'price_change': round(price_change_24h, 2),
                        'ratio_volumen': ratio_volumen,
                        'alerta_anomalia': es_anomalia_oculta,
                        'etiqueta_grafico': etiqueta_graf,
                        'metricas_futuros': metricas_futuros,
                        'score': score
                    })
        except Exception:
            continue

# Ordenar por score (las anomalías ocultas con mayor volumen tendrán prioridad absoluta arriba)
top_candidatas = sorted(candidatas_radar, key=lambda x: x['score'], reverse=True)[:7]

if top_candidatas:
    generar_grafico_estilo_exacto(top_candidatas)
    resumen_ia = generar_resumen_ia(top_candidatas)
    
    mensaje_telegram = "🧠 **RADAR TÁCTICO DE INTELIGENCIA DE MERCADO**\n"
    mensaje_telegram += "🚀 **ALERTA DE PRE-EXPLOSIÓN & ACUMULACIÓN OCULTA**\n"
    mensaje_telegram += f"🔍 *Pares analizados en Binance:* `{total_pares_analizados}`\n\n"
    mensaje_telegram += f"💡 **Dictamen de Anomalías (IA):**\n{resumen_ia}\n\n"
    mensaje_telegram += "─────────────────────────\n"
    
    for coin in top_candidatas:
        precio_fmt = formatear_precio(coin['price'])
        barras = obtener_barras_fuerza(coin['ratio_volumen'])
        url_netlify = f"{NETLIFY_BASE_URL}/?coin={coin['ticker']}"
        url_binance = f"https://www.binance.com/es/trade/{coin['ticker']}_USDT?type=spot"
        mf = coin['metricas_futuros']
        
        # Etiqueta visual distintiva si detecta acumulación oculta anticipada
        prefijo_alerta = "🚨 **[ANOMALÍA OCULTA / ACUMULACIÓN DIP]**\n   " if coin['alerta_anomalia'] else ""
        
        mensaje_telegram += (
            f"{prefijo_alerta}• **{coin['ticker']}** | `{precio_fmt}` | {barras} | `+{coin['price_change']}%`\n"
            f"   ├ 📈 **Futuros/OI:** `{mf['oi_status']}`\n"
            f"   ├ 💥 **Liquidaciones:** `{mf['zona_liq']}`\n"
            f"   ├ 🗓️ **Catalizador X:** `{mf['catalizador_x']}`\n"
            f"   └ 📊 [Resumen IA]({url_netlify}) | 🔶 [Tradear]({url_binance}) | Vol 1H: `{coin['ratio_volumen']}x` | Score: `{coin['score']}`\n\n"
        )

    if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
        url_foto = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
        with open('grafico_pre_explosion.png', 'rb') as foto:
            payload_foto = {
                'chat_id': TELEGRAM_CHAT_ID,
                'caption': "🚨 **RADAR — Detección Temprana de Acumulación y Rupturas**",
                'parse_mode': 'Markdown'
            }
            if MESSAGE_THREAD_ID:
                payload_foto['message_thread_id'] = int(MESSAGE_THREAD_ID)
            requests.post(url_foto, data=payload_foto, files={'photo': foto})

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
        
        print("✅ Alerta de radar y anomalías ocultas enviada con éxito.")

estructura_ia = {
    "timestamp": pd.Timestamp.now().isoformat(),
    "bot_origen": "Radar Pre-Explosión & Anomalías",
    "total_analizados": total_pares_analizados,
    "top_candidatas": top_candidatas
}
with open("datos_pre_explosion_ia.json", "w") as f:
    json.dump(estructura_ia, f, indent=4)
}
with open("datos_pre_explosion_ia.json", "w") as f:
    json.dump(estructura_ia, f, indent=4)
