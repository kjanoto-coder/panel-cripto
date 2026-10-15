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

print("🚀 Iniciando Radar Táctico con Termómetro de 3 Fases...")

# ---------------------------------------------------------
# FUNCIONES AUXILIARES Y MÉTRICAS
# ---------------------------------------------------------
def obtener_barras_fuerza(ratio_volumen):
    if ratio_volumen >= 4.0:
        return "🟢🟢🟢🟢🟢"
    elif ratio_volumen >= 2.8:
        return "🟢🟢🟢🟢⚪"
    elif ratio_volumen >= 1.8:
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

def obtener_datos_futuros(ticker):
    datos_futuros = {
        "oi_status": "⚡ Compresión Activa",
        "zona_liq": "🛡️ Zona de Rango",
        "catalizador_x": "🎯 Preparación de Ruptura Inminente"
    }
    try:
        url_fapi = f"https://fapi.binance.com/fapi/v1/ticker/24hr?symbol={ticker}USDT"
        res_fapi = requests.get(url_fapi, timeout=3).json()
        
        if isinstance(res_fapi, dict) and 'highPrice' in res_fapi:
            high_price = float(res_fapi.get('highPrice', 0))
            last_price = float(res_fapi.get('lastPrice', 1))
            price_change = float(res_fapi.get('priceChangePercent', 0))
            
            if last_price > 0:
                distancia_top = round(((high_price - last_price) / last_price) * 100, 2)
                if distancia_top <= 1.2:
                    datos_futuros["zona_liq"] = "🔥 Squeeze Inminente (<2h)"
                elif distancia_top <= 2.8:
                    datos_futuros["zona_liq"] = "⚡ Ataque a Resistencia"
                else:
                    datos_futuros["zona_liq"] = "🛡️ Acumulación Base"

            if price_change >= 2.0:
                datos_futuros["oi_status"] = "📈 Expansión de Interés Abierto"
            else:
                datos_futuros["oi_status"] = "📊 Carga Silenciosa de Posiciones"
    except Exception:
        pass
    return datos_futuros

def generar_grafico_termometro(candidatas):
    candidatas_ordenadas = sorted(candidatas, key=lambda x: x['score'])
    tickers = [c['etiqueta_grafico'] for c in candidatas_ordenadas]
    scores = [c['score'] for c in candidatas_ordenadas]
    etiquetas_pct = [f"+{c['ratio_volumen']}x" for c in candidatas_ordenadas]

    # Mapeo de colores según el semáforo/termómetro del usuario
    colores_map = {
        'ROJO': '#FF3D00',
        'AMARILLO': '#FFEA00',
        'VERDE': '#00E676'
    }
    colores_barras = [colores_map.get(c['fase'], '#00E676') for c in candidatas_ordenadas]

    fig, ax = plt.subplots(figsize=(10, 5.5), facecolor='#0b0e14')
    ax.set_facecolor('#0b0e14')

    bars = ax.bar(tickers, scores, color=colores_barras, width=0.45)

    ax.text(0.02, 0.93, "🌡️ TERMÓMETRO TÁCTICO • Rojo (Explosión) | Amarillo (Acumulación) | Verde (Vigilancia)", 
            transform=ax.transAxes, fontsize=10, fontweight='bold', color='#FFD700')

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
                    fontsize=9, fontweight='bold', color='white')

    plt.tight_layout()
    plt.savefig('grafico_pre_explosion.png', dpi=250, facecolor=fig.get_facecolor(), edgecolor='none')
    plt.close()

def generar_resumen_ia(candidatas):
    if not GEMINI_API_KEY:
        return "⚠️ *Análisis de IA no disponible*"
        
    client = genai.Client(api_key=GEMINI_API_KEY)
    lista_texto = "\n".join([f"- {c['ticker']} [{c['fase']}]: Precio: {c['price']}, Var 24h: {c['price_change']}%, Vol 1H: {c['ratio_volumen']}x" for c in candidatas])
    
    prompt = f"""
    Actúa como un trader institucional experto en scalping de criptomonedas. Analiza este radar clasificado por termómetro (ROJO=A punto de explotar, AMARILLO=Acumulación/Laterización, VERDE=Vigilancia inicial):

    {lista_texto}

    Redacta un dictamen técnico estricto de máximo 3 líneas destacando qué fichas en ROJO o AMARILLO tienen la mayor presión para detonar hoy mismo en las próximas horas.
    """
    for mod in ['gemini-2.5-flash', 'gemini-1.5-flash']:
        try:
            response = client.models.generate_content(model=mod, contents=prompt)
            if response and response.text:
                return response.text
        except Exception:
            continue
    return "Máxima atención a los activos en fase ROJA y AMARILLA por acumulación institucional inminente lista para resolverse al alza hoy."

# ---------------------------------------------------------
# ESCÁNER Y CLASIFICACIÓN POR TERMÓMETRO
# ---------------------------------------------------------
try:
    exchange = ccxt.binance({
        'enableRateLimit': True,
        'options': {'defaultType': 'spot', 'fetchMarkets': ['spot']},
        'urls': {'api': {'public': 'https://data-api.binance.vision/api/v3', 'spot': 'https://data-api.binance.vision/api/v3'}}
    })

    tickers = exchange.fetch_tickers()
    total_pares_analizados = len(tickers)
    candidatas_totales = []

    for symbol, data in tickers.items():
        if not symbol.endswith('/USDT'):
            continue
            
        price_change_24h = data['percentage'] if data['percentage'] is not None else 0
        vol_24h = data['quoteVolume'] if data['quoteVolume'] is not None else 0
        last_price = data['last'] if data['last'] is not None else 0
        
        if vol_24h > 30000 and last_price > 0:
            try:
                ohlcv = exchange.fetch_ohlcv(symbol, timeframe='1h', limit=12)
                df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
                
                vol_actual_1h = df['volume'].iloc[-1]
                promedio_vol_24h = df['volume'].mean()
                
                if promedio_vol_24h > 0:
                    ratio_volumen = round(vol_actual_1h / promedio_vol_24h, 2)
                    ticker_limpio = symbol.split('/')[0]
                    
                    # Lógica de clasificación del termómetro
                    if ratio_volumen >= 3.0 or (ratio_volumen >= 2.2 and price_change_24h >= 4.0):
                        fase = "ROJO"
                        etiqueta_graf = f"🚨 {ticker_limpio}"
                    elif ratio_volumen >= 2.0 and -5.0 <= price_change_24h <= 4.0:
                        fase = "AMARILLO"
                        etiqueta_graf = f"🟡 {ticker_limpio}"
                    elif ratio_volumen >= 1.3:
                        fase = "VERDE"
                        etiqueta_graf = ticker_limpio
                    else:
                        continue
                        
                    score = round(ratio_volumen * (abs(price_change_24h) + 1.0) * (2.5 if fase == "ROJO" else (1.5 if fase == "AMARILLO" else 1.0)), 2)
                    
                    item_coin = {
                        'symbol': symbol,
                        'ticker': ticker_limpio,
                        'price': last_price,
                        'price_change': round(price_change_24h, 2),
                        'ratio_volumen': ratio_volumen,
                        'fase': fase,
                        'etiqueta_grafico': etiqueta_graf,
                        'score': score,
                        'metricas_futuros': obtener_datos_futuros(ticker_limpio)
                    }
                    candidatas_totales.append(item_coin)
            except Exception:
                continue

    # Tomar las mejores 7 priorizando ROJOS y AMARILLOS
    top_candidatas = sorted(candidatas_totales, key=lambda x: x['score'], reverse=True)[:7]
    print(f"📊 Candidatas en termómetro seleccionadas: {len(top_candidatas)}")

    if top_candidatas:
        generar_grafico_termometro(top_candidatas)
        resumen_ia = generar_resumen_ia(top_candidatas)
        
        mensaje_telegram = "🌡️ **RADAR TÁCTICO • TERMÓMETRO DE MERCADO**\n"
        mensaje_telegram += "🎯 **FOCO: GANADORAS INMEDIATAS (HOY)**\n"
        mensaje_telegram += f"🔍 *Pares analizados en Binance:* `{total_pares_analizados}`\n\n"
        mensaje_telegram += f"💡 **Dictamen del Termómetro (IA):**\n{resumen_ia}\n\n"
        mensaje_telegram += "─────────────────────────\n"
        
        for coin in top_candidatas:
            precio_fmt = formatear_precio(coin['price'])
            barras = obtener_barras_fuerza(coin['ratio_volumen'])
            url_netlify = f"{NETLIFY_BASE_URL}/?coin={coin['ticker']}"
            url_binance = f"https://www.binance.com/es/trade/{coin['ticker']}_USDT?type=spot"
            mf = coin['metricas_futuros']
            
            # Emojis de fase para Telegram
            icono_fase = "🔴 **[FASE ROJA: Explosión Inminente]**" if coin['fase'] == "ROJO" else ("🟡 **[FASE AMARILLA: Acumulación / Rango]**" if coin['fase'] == "AMARILLO" else "🟢 **[FASE VERDE: Vigilancia Inicial]**")
            
            mensaje_telegram += (
                f"{icono_fase}\n"
                f"• **{coin['ticker']}** | `{precio_fmt}` | {barras} | `+{coin['price_change']}%`\n"
                f"   ├ 📈 **Estructura:** `{mf['oi_status']}`\n"
                f"   ├ 💥 **Zona Liquidez:** `{mf['zona_liq']}`\n"
                f"   └ 📊 [Resumen IA]({url_netlify}) | 🔶 [Tradear]({url_binance}) | Vol 1H: `{coin['ratio_volumen']}x` | Score: `{coin['score']}`\n\n"
            )

        if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
            url_base = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"
            
            with open('grafico_pre_explosion.png', 'rb') as foto:
                payload_foto = {
                    'chat_id': TELEGRAM_CHAT_ID,
                    'caption': "🌡️ **Termómetro Táctico — Fases de Ruptura (Hoy)**",
                    'parse_mode': 'Markdown'
                }
                if MESSAGE_THREAD_ID:
                    payload_foto['message_thread_id'] = int(MESSAGE_THREAD_ID)
                requests.post(f"{url_base}/sendPhoto", data=payload_foto, files={'photo': foto})

            payload_msg = {
                'chat_id': TELEGRAM_CHAT_ID,
                'text': mensaje_telegram,
                'parse_mode': 'Markdown',
                'disable_web_page_preview': True
            }
            if MESSAGE_THREAD_ID:
                payload_msg['message_thread_id'] = int(MESSAGE_THREAD_ID)
            requests.post(f"{url_base}/sendMessage", json=payload_msg)

except Exception as e:
    print(f"❌ Error crítico: {str(e)}")
    raise e

estructura_ia = {
    "timestamp": pd.Timestamp.now().isoformat(),
    "bot_origen": "Radar Termómetro 3 Fases",
    "total_analizados": total_pares_analizados if 'total_pares_analizados' in locals() else 0,
    "top_candidatas": top_candidatas if 'top_candidatas' in locals() else []
}
with open("datos_pre_explosion_ia.json", "w") as f:
    json.dump(estructura_ia, f, indent=4)
