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

print("🚀 Ejecutando Radar con Espejos Anti-Bloqueo (Spot + Futuros)...")

# ---------------------------------------------------------
# FUNCIONES AUXILIARES Y MÉTRICAS MULTI-CAPA
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

def analizar_multi_temporalidad_y_liquidaciones(exchange_spot, symbol, ticker):
    metricas = {
        "oi_status": "⚡ Compresión de Rango",
        "zona_liq": "🛡️ Zonas Estables",
        "catalizador_x": "🔥 Tracción y Hype en Redes Sociales",
        "confluencia_tf": "⏳ Alineación 1H/4H en Curso"
    }
    try:
        ohlcv_4h = exchange_spot.fetch_ohlcv(symbol, timeframe='4h', limit=6)
        df_4h = pd.DataFrame(ohlcv_4h, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        
        ohlcv_1d = exchange_spot.fetch_ohlcv(symbol, timeframe='1d', limit=3)
        df_1d = pd.DataFrame(ohlcv_1d, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        
        vol_4h_reciente = df_4h['volume'].iloc[-1]
        media_4h = df_4h['volume'].mean()
        tendencia_1d_alcista = df_1d['close'].iloc[-1] > df_1d['open'].iloc[-1]
        
        if media_4h > 0 and (vol_4h_reciente / media_4h) >= 1.5 and tendencia_1d_alcista:
            metricas["confluencia_tf"] = "🚀 Confluencia Total (1H + 4H + 1D Alcista)"
        elif tendencia_1d_alcista:
            metricas["confluencia_tf"] = "⚡ Estructura 1D Favorable"
        else:
            metricas["confluencia_tf"] = "💤 Acumulación en Soporte"

        url_fapi = f"https://fapi.binance.vision/fapi/v1/ticker/24hr?symbol={ticker}USDT"
        res_fapi = requests.get(url_fapi, timeout=3).json()
        
        if isinstance(res_fapi, dict) and 'highPrice' in res_fapi:
            high_price = float(res_fapi.get('highPrice', 0))
            last_price = float(res_fapi.get('lastPrice', 1))
            
            if last_price > 0:
                distancia_top = round(((high_price - last_price) / last_price) * 100, 2)
                if distancia_top <= 1.5:
                    metricas["zona_liq"] = "🔥 Clúster de Shorts listo para Liquidación (<1.5%)"
                else:
                    metricas["zona_liq"] = "🛡️ Limpieza previa a impulso"
    except Exception:
        pass
    return metricas

def generar_grafico_termometro(candidatas):
    candidatas_ordenadas = sorted(candidatas, key=lambda x: x['score'])
    tickers = [c['etiqueta_grafico'] for c in candidatas_ordenadas]
    scores = [c['score'] for c in candidatas_ordenadas]
    etiquetas_pct = [f"+{c['ratio_volumen']}x" for c in candidatas_ordenadas]

    colores_map = {
        'ROJO': '#FF3D00',     # Explosión inminente
        'AMARILLO': '#FFD600', # Acumulación en rango
        'VERDE': '#00E676'     # Vigilancia inicial
    }
    colores_barras = [colores_map.get(c['fase'], '#00E676') for c in candidatas_ordenadas]

    fig, ax = plt.subplots(figsize=(10, 5.5), facecolor='#0b0e14')
    ax.set_facecolor('#0b0e14')

    bars = ax.bar(tickers, scores, color=colores_barras, width=0.45)

    ax.text(0.02, 0.93, "🌡️ TERMÓMETRO TÁCTICO • Rojo (Explosión) | Amarillo (Acumulación) | Verde (Vigilancia)", 
            transform=ax.transAxes, fontsize=9.5, fontweight='bold', color='#FFD700')

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
    lista_texto = "\n".join([
        f"- {c['ticker']} [{c['fase']}]: Precio: {c['price']}, Var 24h: {c['price_change']}%, Vol 1H: {c['ratio_volumen']}x" 
        for c in candidatas
    ])
    
    prompt = f"""
    Actúa como un trader institucional especialista en anticipación de criptomonedas ganadoras. Analiza estas candidatas clasificadas por termómetro (ROJO=Explosión inminente, AMARILLO=Acumulación silenciosa, VERDE=Vigilancia):

    {lista_texto}

    Escribe un dictamen contundente y directo de máximo 4 líneas. 
    Señala cuál de estas monedas tiene la mayor probabilidad de convertirse en la ganadora explosiva de las próximas horas basándote en su compresión y volumen.
    """
    for mod in ['gemini-2.5-flash', 'gemini-1.5-flash']:
        try:
            response = client.models.generate_content(model=mod, contents=prompt)
            if response and response.text:
                return response.text
        except Exception:
            continue
    return "Máxima atención a los activos en fase Roja y Amarilla: la acumulación silenciosa detectada anticipa el próximo movimiento explosivo del día."

# ---------------------------------------------------------
# ESCÁNER DUAL BALANCEADO (CON ESPEJOS PÚBLICOS `.vision`)
# ---------------------------------------------------------
try:
    exchange_spot = ccxt.binance({
        'enableRateLimit': True,
        'options': {'defaultType': 'spot', 'fetchMarkets': ['spot']},
        'urls': {'api': {'public': 'https://data-api.binance.vision/api/v3', 'spot': 'https://data-api.binance.vision/api/v3'}}
    })
    
    exchange_future = ccxt.binance({
        'enableRateLimit': True,
        'options': {'defaultType': 'future'},
        'urls': {
            'api': {
                'public': 'https://fapi.binance.vision/fapi/v1',
                'fapiPublic': 'https://fapi.binance.vision/fapi/v1'
            }
        }
    })

    tickers_spot = exchange_spot.fetch_tickers()
    tickers_future = exchange_future.fetch_tickers()
    total_pares_analizados = len(tickers_spot) + len(tickers_future)

    candidatas_rojas = []
    candidatas_amarillas = []
    candidatas_verdes = []
    procesados = set()

    fuentes_mercado = [
        (tickers_spot, exchange_spot, "SPOT"),
        (tickers_future, exchange_spot, "FUTUROS")
    ]

    for tickers_dict, ex_ref, tipo_mercado in fuentes_mercado:
        for symbol, data in tickers_dict.items():
            if not symbol.endswith('/USDT'):
                continue
            ticker_limpio = symbol.split('/')[0]
            if ticker_limpio in procesados:
                continue
            
            price_change_24h = data['percentage'] if data['percentage'] is not None else 0
            vol_24h = data['quoteVolume'] if data['quoteVolume'] is not None else 0
            last_price = data['last'] if data['last'] is not None else 0
            
            if vol_24h > 30000 and last_price > 0:
                try:
                    ohlcv = ex_ref.fetch_ohlcv(symbol, timeframe='1h', limit=12)
                    df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
                    
                    vol_actual_1h = df['volume'].iloc[-1]
                    promedio_vol_24h = df['volume'].mean()
                    
                    if promedio_vol_24h > 0:
                        ratio_volumen = round(vol_actual_1h / promedio_vol_24h, 2)
                        procesados.add(ticker_limpio)
                        
                        if ratio_volumen >= 3.2:
                            fase = "ROJO"
                            etiqueta_graf = f"🚨 {ticker_limpio}"
                        elif ratio_volumen >= 2.0 and -4.0 <= price_change_24h <= 5.0:
                            fase = "AMARILLO"
                            etiqueta_graf = f"🟡 {ticker_limpio}"
                        elif ratio_volumen >= 1.3:
                            fase = "VERDE"
                            etiqueta_graf = ticker_limpio
                        else:
                            continue
                        
                        score = round(ratio_volumen * (abs(price_change_24h) + 1.2) * (2.5 if fase == "ROJO" else (1.6 if fase == "AMARILLO" else 1.0)), 2)
                        metricas_avanzadas = analizar_multi_temporalidad_y_liquidaciones(exchange_spot, symbol, ticker_limpio)
                        
                        item_coin = {
                            'symbol': symbol,
                            'ticker': ticker_limpio,
                            'price': last_price,
                            'price_change': round(price_change_24h, 2),
                            'ratio_volumen': ratio_volumen,
                            'fase': fase,
                            'mercado': tipo_mercado,
                            'etiqueta_grafico': etiqueta_graf,
                            'score': score,
                            'metricas_avanzadas': metricas_avanzadas
                        }
                        
                        if fase == "ROJO":
                            candidatas_rojas.append(item_coin)
                        elif fase == "AMARILLO":
                            candidatas_amarillas.append(item_coin)
                        else:
                            candidatas_verdes.append(item_coin)
                except Exception:
                    continue

    candidatas_rojas = sorted(candidatas_rojas, key=lambda x: x['score'], reverse=True)
    candidatas_amarillas = sorted(candidatas_amarillas, key=lambda x: x['score'], reverse=True)
    candidatas_verdes = sorted(candidatas_verdes, key=lambda x: x['score'], reverse=True)

    top_candidatas = (candidatas_rojas + candidatas_amarillas + candidatas_verdes)[:7]
    print(f"📊 Total candidatas en termómetro balanceado: {len(top_candidatas)}")

    if top_candidatas:
        generar_grafico_termometro(top_candidatas)
        resumen_ia = generar_resumen_ia(top_candidatas)
        
        mensaje_telegram = "🧠 **RADAR TÁCTICO • TERMÓMETRO BALANCEADO**\n"
        mensaje_telegram += "🚀 **ANTICIPACIÓN DE GANADORAS (HOY)**\n"
        mensaje_telegram += f"🔍 *Pares analizados:* `{total_pares_analizados}`\n\n"
        mensaje_telegram += f"💡 **Dictamen de Anticipación (IA):**\n{resumen_ia}\n\n"
        mensaje_telegram += "─────────────────────────\n"
        
        for coin in top_candidatas:
            precio_fmt = formatear_precio(coin['price'])
            barras = obtener_barras_fuerza(coin['ratio_volumen'])
            url_netlify = f"{NETLIFY_BASE_URL}/?coin={coin['ticker']}"
            url_binance = f"https://www.binance.com/es/trade/{coin['ticker']}_USDT?type=spot"
            ma = coin['metricas_avanzadas']
            
            if coin['fase'] == "ROJO":
                icono_fase = f"🔴 **[ROJO / {coin['mercado']}: Explosión Inminente]**"
            elif coin['fase'] == "AMARILLO":
                icono_fase = f"🟡 **[AMARILLO / {coin['mercado']}: Acumulación / Rango]**"
            else:
                icono_fase = f"🟢 **[VERDE / {coin['mercado']}: Vigilancia Inicial]**"
            
            mensaje_telegram += (
                f"{icono_fase}\n"
                f"• **{coin['ticker']}** | `{precio_fmt}` | {barras} | `+{coin['price_change']}%`\n"
                f"   ├ ⏳ **Estructura (1H/4H/1D):** `{ma['confluencia_tf']}`\n"
                f"   ├ 🗺️ **Zonas de Presión:** `{ma['zona_liq']}`\n"
                f"   └ 📊 [Detalle IA]({url_netlify}) | 🔶 [Binance]({url_binance}) | Vol 1H: `{coin['ratio_volumen']}x` | Score: `{coin['score']}`\n\n"
            )

        if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
            url_base = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"
            
            with open('grafico_pre_explosion.png', 'rb') as foto:
                payload_foto = {
                    'chat_id': TELEGRAM_CHAT_ID,
                    'caption': "🌡️ **Termómetro Balanceado — Anticipación de Ganadoras**",
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
    "bot_origen": "Radar Termómetro Balanceado",
    "total_analizados": total_pares_analizados if 'total_pares_analizados' in locals() else 0,
    "top_candidatas": top_candidatas if 'top_candidatas' in locals() else []
}
with open("datos_pre_explosion_ia.json", "w") as f:
    json.dump(estructura_ia, f, indent=4)
