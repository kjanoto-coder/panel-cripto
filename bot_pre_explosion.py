import os
import json
import requests
import pandas as pd
import matplotlib.pyplot as plt
from google import genai

# ---------------------------------------------------------
# CONFIGURACIÓN DE CREDENCIALES Y PARÁMETROS
# ---------------------------------------------------------
TELEGRAM_BOT_TOKEN = (os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("TELEGRAM_TOKEN") or "").strip()
TELEGRAM_CHAT_ID = (os.getenv("TELEGRAM_CHAT_ID") or os.getenv("CHAT_ID") or "").strip()
MESSAGE_THREAD_ID = (os.getenv("TOPIC_ID_PRE_EXPLOSION") or os.getenv("TELEGRAM_MESSAGE_THREAD_ID") or "").strip()
GEMINI_API_KEY = (os.getenv("GEMINI_API_KEY") or "").strip()

NETLIFY_BASE_URL = "https://tu-nuevo-motor-pre-explosion.netlify.app"
HISTORIAL_FILE = "historial_alertas_recientes.json"

print("🚀 Ejecutando Radar con Estructura Obligatoria de 3 Fases...")

def cargar_historial_reciente():
    if os.path.exists(HISTORIAL_FILE):
        try:
            with open(HISTORIAL_FILE, "r") as f:
                data = json.load(f)
                return data.get("recent_tickers", [])
        except Exception:
            return []
    return []

def guardar_historial_reciente(tickers_actuales):
    try:
        data = {"recent_tickers": tickers_actuales}
        with open(HISTORIAL_FILE, "w") as f:
            json.dump(data, f, indent=4)
    except Exception:
        pass

def obtener_barras_fuerza(ratio_volumen):
    if ratio_volumen >= 3.5:
        return "🟢🟢🟢🟢🟢"
    elif ratio_volumen >= 2.5:
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

def obtener_score(item):
    return item.get('score', 0)

def obtener_ohlcv_binance(symbol, interval='1h', limit=12):
    try:
        url = f"https://data-api.binance.vision/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}"
        res = requests.get(url, timeout=5).json()
        if isinstance(res, list):
            df = pd.DataFrame(res, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'close_time', 'qav', 'num_trades', 'taker_base_vol', 'taker_quote_vol', 'ignore'])
            for col in ['open', 'high', 'low', 'close', 'volume']:
                df[col] = df[col].astype(float)
            return df
    except Exception:
        pass
    return None

def analizar_multi_temporalidad_y_liquidaciones(symbol, ticker):
    metricas = {
        "zona_liq": "🛡️ Zonas Estables",
        "confluencia_tf": "⏳ Alineación 1H/4H en Curso"
    }
    try:
        df_4h = obtener_ohlcv_binance(symbol, interval='4h', limit=6)
        df_1d = obtener_ohlcv_binance(symbol, interval='1d', limit=3)
        
        if df_4h is not None and len(df_4h) > 0 and df_1d is not None and len(df_1d) > 0:
            vol_4h_reciente = df_4h['volume'].iloc[-1]
            media_4h = df_4h['volume'].mean()
            tendencia_1d_alcista = df_1d['close'].iloc[-1] > df_1d['open'].iloc[-1]
            
            if media_4h > 0 and (vol_4h_reciente / media_4h) >= 1.4 and tendencia_1d_alcista:
                metricas["confluencia_tf"] = "🚀 Confluencia Total (1H + 4H + 1D Alcista)"
            elif tendencia_1d_alcista:
                metricas["confluencia_tf"] = "⚡ Estructura 1D Favorable"
            else:
                metricas["confluencia_tf"] = "💤 Acumulación en Soporte"

            high_price = float(df_4h['high'].max())
            last_price = float(df_4h['close'].iloc[-1])
            
            if last_price > 0:
                distancia_top = round(((high_price - last_price) / last_price) * 100, 2)
                if distancia_top <= 1.5:
                    metricas["zona_liq"] = "🔥 Presión en Máximos de Rango (<1.5%)"
                else:
                    metricas["zona_liq"] = "🛡️ Zona de Acumulación Limpia"
    except Exception:
        pass
    return metricas

def generar_grafico_termometro(candidatas):
    candidatas_ordenadas = sorted(candidatas, key=obtener_score)
    tickers = [c['etiqueta_grafico'] for c in candidatas_ordenadas]
    scores = [c['score'] for c in candidatas_ordenadas]
    etiquetas_pct = [f"+{c['ratio_volumen']}x" for c in candidatas_ordenadas]

    colores_map = {
        'ROJO': '#FF3D00',
        'AMARILLO': '#FFD600',
        'VERDE': '#00E676'
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

def enviar_foto_telegram(url_base, payload_base, image_path):
    with open(image_path, 'rb') as foto:
        try:
            res = requests.post(f"{url_base}/sendPhoto", data=payload_base, files={'photo': foto}, timeout=30)
            resultado = res.json()
        except Exception:
            resultado = {"ok": False}
        
        if not resultado.get("ok"):
            print("⚠️ Reintentando foto al chat principal...")
            payload_copia = payload_base.copy()
            payload_copia.pop("message_thread_id", None)
            foto.seek(0)
            try:
                res = requests.post(f"{url_base}/sendPhoto", data=payload_copia, files={'photo': foto}, timeout=30)
                resultado = res.json()
            except Exception:
                pass
        if resultado.get("ok"):
            print("✅ Foto enviada.")

def enviar_mensaje_telegram(url_base, payload_base):
    try:
        res = requests.post(f"{url_base}/sendMessage", json=payload_base, timeout=20)
        resultado = res.json()
    except Exception:
        resultado = {"ok": False}
    
    if not resultado.get("ok"):
        print("⚠️ Reintentando mensaje al chat principal...")
        payload_copia = payload_base.copy()
        payload_copia.pop("message_thread_id", None)
        try:
            res = requests.post(f"{url_base}/sendMessage", json=payload_copia, timeout=20)
            resultado = res.json()
        except Exception:
            pass
    if resultado.get("ok"):
        print("✅ Mensaje enviado.")

# ---------------------------------------------------------
# ESCÁNER CON SELECCIÓN BALANCEADA OBLIGATORIA
# ---------------------------------------------------------
try:
    url_tickers = "https://data-api.binance.vision/api/v3/ticker/24hr"
    res_tickers = requests.get(url_tickers, timeout=10).json()
    
    if not isinstance(res_tickers, list):
        raise Exception("No se pudieron obtener los tickers de Binance Vision.")

    total_pares_analizados = len(res_tickers)
    historial_excluidos = cargar_historial_reciente()

    candidatas_rojas = []
    candidatas_amarillas = []
    candidatas_verdes = []

    for item in res_tickers:
        symbol = item.get('symbol', '')
        if not symbol.endswith('USDT'):
            continue
        ticker_limpio = symbol[:-4]
        
        if ticker_limpio in historial_excluidos:
            continue
        
        try:
            price_change_24h = float(item.get('priceChangePercent', 0))
            vol_24h = float(item.get('quoteVolume', 0))
            last_price = float(item.get('lastPrice', 0))
            
            if vol_24h > 25000 and last_price > 0:
                df_1h = obtener_ohlcv_binance(symbol, interval='1h', limit=12)
                if df_1h is not None and len(df_1h) > 0:
                    vol_actual_1h = df_1h['volume'].iloc[-1]
                    promedio_vol_24h = df_1h['volume'].mean()
                    
                    if promedio_vol_24h > 0:
                        ratio_volumen = round(vol_actual_1h / promedio_vol_24h, 2)
                        
                        if ratio_volumen >= 2.6:
                            fase = "ROJO"
                            etiqueta_graf = f"🚨 {ticker_limpio}"
                        elif ratio_volumen >= 1.7 and -5.0 <= price_change_24h <= 5.0:
                            fase = "AMARILLO"
                            etiqueta_graf = f"🟡 {ticker_limpio}"
                        elif ratio_volumen >= 1.2:
                            fase = "VERDE"
                            etiqueta_graf = ticker_limpio
                        else:
                            continue
                        
                        score = round(ratio_volumen * (abs(price_change_24h) + 1.2), 2)
                        metricas_avanzadas = analizar_multi_temporalidad_y_liquidaciones(symbol, ticker_limpio)
                        
                        item_coin = {
                            'symbol': symbol,
                            'ticker': ticker_limpio,
                            'price': last_price,
                            'price_change': round(price_change_24h, 2),
                            'ratio_volumen': ratio_volumen,
                            'fase': fase,
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

    candidatas_rojas = sorted(candidatas_rojas, key=obtener_score, reverse=True)
    candidatas_amarillas = sorted(candidatas_amarillas, key=obtener_score, reverse=True)
    candidatas_verdes = sorted(candidatas_verdes, key=obtener_score, reverse=True)

    top_candidatas = []
    top_candidatas.extend(candidatas_rojas[:2])
    top_candidatas.extend(candidatas_amarillas[:3])
    top_candidatas.extend(candidatas_verdes[:2])

    if len(top_candidatas) < 7:
        restantes = [c for c in (candidatas_rojas + candidatas_amarillas + candidatas_verdes) if c not in top_candidatas]
        restantes_ordenados = sorted(restantes, key=obtener_score, reverse=True)
        top_candidatas.extend(restantes_ordenados[:(7 - len(top_candidatas))])

    top_candidatas = top_candidatas[:7]
    print(f"📊 Selección balanceada lista (Rojos: {len([c for c in top_candidatas if c['fase']=='ROJO'])}, Amarillos: {len([c for c in top_candidatas if c['fase']=='AMARILLO'])}, Verdes: {len([c for c in top_candidatas if c['fase']=='VERDE'])})")

    if top_candidatas:
        nuevos_tickers_historial = [c['ticker'] for c in top_candidatas]
        guardar_historial_reciente(nuevos_tickers_historial)

        generar_grafico_termometro(top_candidatas)
        resumen_ia = generar_resumen_ia(top_candidatas)
        
        mensaje_telegram = "🧠 **RADAR TÁCTICO • TERMÓMETRO BALANCEADO 3-FASES**\n"
        mensaje_telegram += "🚀 **ANTICIPACIÓN DE GANADORAS (ROJO / AMARILLO / VERDE)**\n"
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
                icono_fase = "🔴 **[ROJO: Explosión Inminente]**"
            elif coin['fase'] == "AMARILLO":
                icono_fase = "🟡 **[AMARILLO: Acumulación / Rango]**"
            else:
                icono_fase = "🟢 **[VERDE: Vigilancia Inicial]**"
            
            mensaje_telegram += (
                f"{icono_fase}\n"
                f"• **{coin['ticker']}** | `{precio_fmt}` | {barras} | `+{coin['price_change']}%`\n"
                f"   ├ ⏳ **Estructura (1H/4H/1D):** `{ma['confluencia_tf']}`\n"
                f"   ├ 🗺️ **Zonas de Presión:** `{ma['zona_liq']}`\n"
                f"   └ 📊 [Detalle IA]({url_netlify}) | 🔶 [Binance]({url_binance}) | Vol 1H: `{coin['ratio_volumen']}x` | Score: `{coin['score']}`\n\n"
            )

        if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
            url_base = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"
            
            thread_id = None
            if MESSAGE_THREAD_ID:
                try:
                    thread_id = int(MESSAGE_THREAD_ID)
                except ValueError:
                    pass

            payload_foto = {
                'chat_id': TELEGRAM_CHAT_ID,
                'caption': "🌡️ **Termómetro Táctico — 3 Fases de Anticipación (Hoy)**",
                'parse_mode': 'Markdown'
            }
            if thread_id:
                payload_foto['message_thread_id'] = thread_id
            
            enviar_foto_telegram(url_base, payload_foto, 'grafico_pre_explosion.png')

            payload_msg = {
                'chat_id': TELEGRAM_CHAT_ID,
                'text': mensaje_telegram,
                'parse_mode': 'Markdown',
                'disable_web_page_preview': True
            }
            if thread_id:
                payload_msg['message_thread_id'] = thread_id
                
            enviar_mensaje_telegram(url_base, payload_msg)
        else:
            print("⚠️ No se pudo enviar a Telegram: Faltan credenciales.")

except Exception as e:
    print(f"❌ Error crítico: {str(e)}")
    raise e

estructura_ia = {
    "timestamp": pd.Timestamp.now().isoformat(),
    "bot_origen": "Radar Termómetro Balanceado 3 Fases",
    "total_analizados": total_pares_analizados if 'total_pares_analizados' in locals() else 0,
    "top_candidatas": top_candidatas if 'top_candidatas' in locals() else []
}
with open("datos_pre_explosion_ia.json", "w") as f:
    json.dump(estructura_ia, f, indent=4)
