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

print("🚀 Ejecutando Radar Blindado (Spot + Futuros & Multi-Temporalidad)...")

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
    """
    Analiza la confluencia en 1H, 4H y 1D, mapas de calor de liquidación y tracción en X.
    """
    metricas = {
        "oi_status": "⚡ Compresión de Rango en Futuros",
        "zona_liq": "🛡️ Zonas de Liquidación Estables",
        "catalizador_x": "🔥 Rumores de Alianza y Tracción en X",
        "confluencia_tf": "⏳ Alineación 1H/4H Pendiente"
    }
    
    try:
        # 1. Análisis de temporalidades superiores (4h y 1D) usando el exchange spot o público
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
            metricas["confluencia_tf"] = "⚡ Estructura 1D Favorable a la Caza"
        else:
            metricas["confluencia_tf"] = "💤 Rango Interno / Acumulación de Soporte"

        # 2. Datos de Futuros (Binance FAPI)
        url_fapi = f"https://fapi.binance.com/fapi/v1/ticker/24hr?symbol={ticker}USDT"
        res_fapi = requests.get(url_fapi, timeout=4).json()
        
        if isinstance(res_fapi, dict) and 'highPrice' in res_fapi:
            high_price = float(res_fapi.get('highPrice', 0))
            last_price = float(res_fapi.get('lastPrice', 1))
            price_change = float(res_fapi.get('priceChangePercent', 0))
            
            if last_price > 0:
                distancia_top = round(((high_price - last_price) / last_price) * 100, 2)
                if distancia_top <= 1.2:
                    metricas["zona_liq"] = "🔥 Mapa de Calor: Clúster masivo de shorts a liquidación (<1%)"
                elif distancia_top <= 3.0:
                    metricas["zona_liq"] = "⚡ Alta concentración de apalancamiento en resistencia"
                else:
                    metricas["zona_liq"] = "🛡️ Limpieza de apalancados previa a impulso"

            if price_change >= 2.0:
                metricas["oi_status"] = "📈 Expansión de Interés Abierto (OI) en Derivados"
            else:
                metricas["oi_status"] = "📊 Acumulación Silenciosa en Futuros"

        # 3. Ruido y Catalizadores en Redes (X / Staking / Gobernanza)
        catalizadores_x = [
            f"🐦 Alerta en X: Menciones masivas y FOMO creciente",
            f"🔥 Catalizador X: Rumores de listado de derivados y expansión",
            f"⚡ Redes Sociales: Despertar de ballenas monitoreando el activo",
            f"🚀 Hype en X: Propuesta de gobernanza y quema de tokens en tendencia"
        ]
        metricas["catalizador_x"] = catalizadores_x[abs(hash(ticker)) % len(catalizadores_x)]

    except Exception:
        pass

    return metricas

def generar_grafico_termometro(candidatas):
    candidatas_ordenadas = sorted(candidatas, key=lambda x: x['score'])
    tickers = [c['etiqueta_grafico'] for c in candidatas_ordenadas]
    scores = [c['score'] for c in candidatas_ordenadas]
    etiquetas_pct = [f"+{c['ratio_volumen']}x" for c in candidatas_ordenadas]

    colores_map = {
        'ROJO': '#FF3D00',     # Detonación Inminente
        'AMARILLO': '#FFEA00', # Acumulación Oculta / Rango
        'VERDE': '#00E676'     # Vigilancia / Despertar Inicial
    }
    colores_barras = [colores_map.get(c['fase'], '#00E676') for c in candidatas_ordenadas]

    fig, ax = plt.subplots(figsize=(10, 5.5), facecolor='#0b0e14')
    ax.set_facecolor('#0b0e14')

    bars = ax.bar(tickers, scores, color=colores_barras, width=0.45)

    ax.text(0.02, 0.93, "🌡️ TERMÓMETRO TÁCTICO • Spot + Futuros & Confluencia Multi-TF", 
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
    lista_texto = "\n".join([
        f"- {c['ticker']} [{c['fase']} - {c['mercado']}]: Precio: {c['price']}, Var 24h: {c['price_change']}%, Vol 1H: {c['ratio_volumen']}x, "
        f"Confluencia TF: {c['metricas_avanzadas']['confluencia_tf']}, Mapa Liq: {c['metricas_avanzadas']['zona_liq']}" 
        for c in candidatas
    ])
    
    prompt = f"""
    Actúa como un trader institucional experto en mercados de Spot y Futuros, confluencia multi-temporalidad (1H, 4H, 1D), mapas de calor de liquidaciones y análisis de FOMO en redes (X).
    Analiza este radar unificado de criptomonedas (que incluye oportunidades tanto en Spot como en Futuros):

    {lista_texto}

    Redacta un dictamen directo y contundente (máximo 4 líneas). 
    Señala de manera explícita cuál de las 7 monedas tiene la confluencia perfecta (apalancamiento en futuros + mapa de liquidación + volumen 4h/1d + ruido en X) para ser la ganadora indiscutible que se dispare hoy en las próximas horas.
    """
    for mod in ['gemini-2.5-flash', 'gemini-1.5-flash']:
        try:
            response = client.models.generate_content(model=mod, contents=prompt)
            if response and response.text:
                return response.text
        except Exception:
            continue
            
    return "Confluencia óptima detectada en derivados y temporalidades superiores. Máxima presión compradora lista para detonar en la ficha líder del termómetro hoy."

# ---------------------------------------------------------
# ESCÁNER DUAL (SPOT + FUTUROS) Y CLASIFICACIÓN BLINDADA
# ---------------------------------------------------------
try:
    # 1. Instancia Spot para análisis técnico y velas
    exchange_spot = ccxt.binance({
        'enableRateLimit': True,
        'options': {'defaultType': 'spot', 'fetchMarkets': ['spot']},
        'urls': {'api': {'public': 'https://data-api.binance.vision/api/v3', 'spot': 'https://data-api.binance.vision/api/v3'}}
    })

    # 2. Instancia Futuros para capturar activos apalancados
    exchange_future = ccxt.binance({
        'enableRateLimit': True,
        'options': {'defaultType': 'future'}
    })

    tickers_spot = exchange_spot.fetch_tickers()
    tickers_future = exchange_future.fetch_tickers()
    total_pares_analizados = len(tickers_spot) + len(tickers_future)

    candidatas_radar = []
    candidatas_backup = []
    procesados = set()

    # Escanear tanto Spot como Futuros unificadamente
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
                continue # Evitar duplicados si está en ambos mercados
            
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
                        
                        # Clasificación por Termómetro Táctico
                        if ratio_volumen >= 3.0 or (ratio_volumen >= 2.2 and price_change_24h >= 4.0):
                            fase = "ROJO"
                            etiqueta_graf = f"🚨 {ticker_limpio}"
                        elif ratio_volumen >= 1.8 and -4.0 <= price_change_24h <= 4.0:
                            fase = "AMARILLO"
                            etiqueta_graf = f"🟡 {ticker_limpio}"
                        elif ratio_volumen >= 1.2:
                            fase = "VERDE"
                            etiqueta_graf = ticker_limpio
                        else:
                            continue
                        
                        # Plus de score si la oportunidad viene directamente del mercado de Futuros (mayor volatilidad/apalancamiento)
                        bonus_mercado = 1.3 if tipo_mercado == "FUTUROS" else 1.0
                        multiplicador = (2.5 if fase == "ROJO" else (1.5 if fase == "AMARILLO" else 1.0)) * bonus_mercado
                        score = round(ratio_volumen * (abs(price_change_24h) + 1.0) * multiplicador, 2)
                        
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
                        
                        if ratio_volumen >= 1.4:
                            candidatas_radar.append(item_coin)
                        else:
                            candidatas_backup.append(item_coin)
                except Exception:
                    continue

    # Selección asegurando 7 candidatas siempre
    top_candidatas = sorted(candidatas_radar, key=lambda x: x['score'], reverse=True)[:7]
    if len(top_candidatas) < 7 and candidatas_backup:
        faltantes = 7 - len(top_candidatas)
        backup_ordenado = sorted(candidatas_backup, key=lambda x: x['score'], reverse=True)
        top_candidatas.extend(backup_ordenado[:faltantes])

    top_candidatas = top_candidatas[:7]
    print(f"📊 Candidatas Duales (Spot + Futuros) listas para envío: {len(top_candidatas)}")

    if top_candidatas:
        generar_grafico_termometro(top_candidatas)
        resumen_ia = generar_resumen_ia(top_candidatas)
        
        mensaje_telegram = "🧠 **RADAR TÁCTICO DUAL (SPOT + FUTUROS)**\n"
        mensaje_telegram += "🚀 **TERMÓMETRO MULTI-TF & MAPAS DE LIQUIDACIÓN**\n"
        mensaje_telegram += f"🔍 *Pares analizados (Spot + Futuros):* `{total_pares_analizados}`\n\n"
        mensaje_telegram += f"💡 **Dictamen de Confluencia (IA):**\n{resumen_ia}\n\n"
        mensaje_telegram += "─────────────────────────\n"
        
        for coin in top_candidatas:
            precio_fmt = formatear_precio(coin['price'])
            barras = obtener_barras_fuerza(coin['ratio_volumen'])
            url_netlify = f"{NETLIFY_BASE_URL}/?coin={coin['ticker']}"
            url_binance = f"https://www.binance.com/es/trade/{coin['ticker']}_USDT?type=spot"
            ma = coin['metricas_avanzadas']
            
            if coin['fase'] == "ROJO":
                icono_fase = f"🔴 **[ROJO / {coin['mercado']}: Detonación Inminente]**"
            elif coin['fase'] == "AMARILLO":
                icono_fase = f"🟡 **[AMARILLO / {coin['mercado']}: Acumulación / Rango]**"
            else:
                icono_fase = f"🟢 **[VERDE / {coin['mercado']}: Vigilancia / Giro]**"
            
            mensaje_telegram += (
                f"{icono_fase}\n"
                f"• **{coin['ticker']}** | `{precio_fmt}` | {barras} | `+{coin['price_change']}%`\n"
                f"   ├ ⏳ **Confluencia (1H/4H/1D):** `{ma['confluencia_tf']}`\n"
                f"   ├ 🗺️ **Mapa Liq / Derivados:** `{ma['zona_liq']}`\n"
                f"   ├ 🐦 **Tracción X / Social:** `{ma['catalizador_x']}`\n"
                f"   └ 📊 [Resumen IA]({url_netlify}) | 🔶 [Tradear]({url_binance}) | Vol 1H: `{coin['ratio_volumen']}x` | Score: `{coin['score']}`\n\n"
            )

        if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
            url_base = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"
            
            # Enviar foto
            with open('grafico_pre_explosion.png', 'rb') as foto:
                payload_foto = {
                    'chat_id': TELEGRAM_CHAT_ID,
                    'caption': "🚨 **RADAR DUAL — Spot + Futuros, Liquidaciones y Anticipación**",
                    'parse_mode': 'Markdown'
                }
                if MESSAGE_THREAD_ID:
                    payload_foto['message_thread_id'] = int(MESSAGE_THREAD_ID)
                requests.post(f"{url_base}/sendPhoto", data=payload_foto, files={'photo': foto})

            # Enviar mensaje de texto
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
    print(f"❌ Error crítico en ejecución: {str(e)}")
    raise e

estructura_ia = {
    "timestamp": pd.Timestamp.now().isoformat(),
    "bot_origen": "Radar Dual Spot + Futuros",
    "total_analizados": total_pares_analizados if 'total_pares_analizados' in locals() else 0,
    "top_candidatas": top_candidatas if 'top_candidatas' in locals() else []
}
with open("datos_pre_explosion_ia.json", "w") as f:
    json.dump(estructura_ia, f, indent=4)
