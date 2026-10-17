import os
import json
import requests
import ccxt
import pandas as pd
import matplotlib.pyplot as plt
from google import genai

# ---------------------------------------------------------
# CONFIGURACIÓN DE CREDENCIALES Y PARÁMETROS (COMPATIBILIDAD TOTAL)
# ---------------------------------------------------------
TELEGRAM_BOT_TOKEN = (os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("TELEGRAM_TOKEN") or "").strip()
TELEGRAM_CHAT_ID = (os.getenv("TELEGRAM_CHAT_ID") or os.getenv("CHAT_ID") or "").strip()
MESSAGE_THREAD_ID = (os.getenv("TOPIC_ID_PRE_EXPLOSION") or os.getenv("TELEGRAM_MESSAGE_THREAD_ID") or "").strip()
GEMINI_API_KEY = (os.getenv("GEMINI_API_KEY") or "").strip()

NETLIFY_BASE_URL = "https://tu-nuevo-motor-pre-explosion.netlify.app"
HISTORIAL_FILE = "historial_alertas_recientes.json"

print("🚀 Ejecutando Radar con Estructura Obligatoria de 3 Fases...")

# ---------------------------------------------------------
# FUNCIONES DE MEMORIA Y ROTACIÓN
# ---------------------------------------------------------
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

# ---------------------------------------------------------
# FUNCIONES AUXILIARES
# ---------------------------------------------------------
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

def analizar_multi_temporalidad_y_liquidaciones(exchange_spot, symbol, ticker):
    metricas = {
        "zona_liq": "🛡️ Zonas Estables",
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
        
        if media_4h > 0 and (vol_4h_reciente / media_4h) >= 1.4 and tendencia_1d_alcista:
            metricas["confluencia_tf"] = "🚀 Confluencia Total (1H + 4H + 1D Alcista)"
        elif tendencia_1d_alcista:
            metricas["confluencia_tf"] = "⚡ Estructura 1D Favorable"
        else:
            metricas["confluencia_tf"] = "💤 Acumulación en Soporte"

        url_fapi = f"https://fapi.binance.com/fapi/v1/ticker/24hr?symbol={ticker}USDT"
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
        'ROJO': '#FF3D00',     # Detonación inminente
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
    Señala cuál de estas monedas tiene la mayor probabilidad de convertirse en la ganadora explosiva das próximas horas basándote en su compresión y volumen.
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
# FUNCIONES DE ENVÍO ROBUSTO A TELEGRAM
# ---------------------------------------------------------
def enviar_foto_telegram(url_base, payload_base, image_path):
    with open(image_path, 'rb') as foto:
        res = requests.post(f"{url_base}/sendPhoto", data=payload_base, files={'photo': foto}, timeout=30)
        resultado = res.json()
        
        if not resultado.get("ok") and "message thread not found" in str(resultado.get("description", "")):
            print("⚠️ Hilo de Telegram no encontrado para la foto. Reintentando al chat principal...")
            payload_copia = payload_base.copy()
            payload_copia.pop("message_thread_id", None)
            foto.seek(0)
            res = requests.post(f"{url_base}/sendPhoto", data=payload_copia, files={'photo': foto}, timeout=30)
            resultado = res.json()
            
        if resultado.get("ok"):
            print("✅ Foto enviada a Telegram.")
        else:
            print(f"⚠️ Error enviando foto a Telegram: {resultado}")

def enviar_mensaje_telegram(url_base, payload_base):
    res = requests.post(f"{url_base}/sendMessage", json=payload_base, timeout=20)
    resultado = res.json()
    
    if not resultado.get("ok") and "message thread not found" in str(resultado.get("description", "")):
        print("⚠️ Hilo de Telegram no encontrado para el mensaje. Reintentando al chat principal...")
        payload_copia = payload_base.copy()
        payload_copia.pop("message_thread_id", None)
        res = requests.post(f"{url_base}/sendMessage", json=payload_copia, timeout=20)
        resultado = res.json()
        
    if resultado.get("ok"):
        print("✅ Mensaje enviado a Telegram.")
    else:
        print(f"⚠️ Error enviando mensaje a Telegram: {resultado}")

# ---------------------------------------------------------
# ESCÁNER CON SELECCIÓN BALANCEADA OBLIGATORIA
# ---------------------------------------------------------
try:
    exchange_spot = ccxt.binance({
        'enableRateLimit': True,
        'options': {'defaultType': 'spot', 'fetchMarkets': ['spot']},
        'urls': {'api': {'public': 'https://data-api.binance.vision/api/v3', 'spot': 'https://data-api.binance.vision/api/v3'}}
    })

    tickers_spot = exchange_spot.fetch_tickers()
    total_pares_analizados = len(tickers_spot)
    
    historial_excluidos = cargar_historial_reciente()

    candidatas_rojas = []
    candidatas_amarillas = []
    candidatas_verdes = []

    for symbol, data in tickers_spot.items():
        if not symbol.endswith('/USDT'):
            continue
        ticker_limpio = symbol.split('/')[0]
        
        if ticker_limpio in historial_excluidos:
            continue
        
        price_change_24h = data['percentage'] if data['percentage'] is not None else 0
        vol_24h = data['quoteVolume'] if data['quoteVolume'] is not None else 0
        last_price = data['last'] if data['last'] is not None else 0
        
        if vol_24h > 25000 and last_price > 0:
            try:
                ohlcv = exchange_spot.fetch_ohlcv(symbol, timeframe='1h', limit=12)
                df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
                
                vol_actual_1h = df['volume'].iloc[-1]
                promedio_vol_24h = df['volume'].mean()
                
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
                    metricas_avanzadas = analizar_multi_temporalidad_y_liquidaciones(exchange_spot, symbol, ticker_limpio)
                    
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

    candidatas_rojas = sorted(candidatas_rojas, key=lambda x: x['score'], reverse=True)
    candidatas_amarillas = sorted(candidatas_amarillas, key=lambda x: x['score'], reverse=True)
    candidatas_verdes = sorted(candidatas_verdes, key=lambda x: x['score'], reverse=True)

    top_candidatas = []
    top_candidatas.extend(candidatas_rojas[:2])
    top_candidatas.extend(candidatas_amarillas[:3])
    top_candidatas.extend(candidatas_verdes[:2])

    if len(top_candidatas) < 7:
        restantes = [c for c in (candidatas_rojas + candidatas_amarillas + candidatas_verdes) if c not in top_candidatas]
        restantes_ordenados = sorted(restantes, key=lambda x: x['score'], reverse=True)
        top_candidatas.extend(restantes_ordenados[:(7 - len(top_candidatas))])

    top_candidatas = top_candidatas[:7]
    print(f"📊 Selección balanceada lista (Rojos: {len([c for c in top_candidatas if c['fase']=='ROJO'])}, Amarillos: {len([c for c in top_candidatas if c['fase']=='AMARILLO'])}, Verdes: {len([c for c in top_candidatas if c['fase']=='VERDE'])})")

    if top_candidatas:
        nuevos_tickers_historial = [c['ticker'] for c in top_candidatas]
        guardar_historial_reciente(nuevos_tickers_historial)

        generar_grafico_termometro(top_candidatas)
        resumen_ia = generar_resumen_ia(top_candidatas)
        
        mensaje_telegram = "🧠 **RADAR TÁCTICO • TERMÓMETRO BALANCEADO 3-FASES**\n"
        mensaje_telegram +=
