import os
import json
import time
import random
import requests
import html
from datetime import datetime
import numpy as np
import matplotlib.pyplot as plt
from google import genai

# --- CONFIGURACIÓN DE ENTORNO BLINDADAS ---
TELEGRAM_BOT_TOKEN = (os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("TELEGRAM_TOKEN") or "").strip()
TELEGRAM_CHAT_ID = (os.getenv("TELEGRAM_CHAT_ID") or os.getenv("CHAT_ID") or "").strip()
TELEGRAM_TOPIC_ID = (os.getenv("TOPIC_ID_PRE_EXPLOSION") or os.getenv("TELEGRAM_MESSAGE_THREAD_ID") or os.getenv("TOPIC_ID_CENTRAL") or "").strip()
GEMINI_API_KEY = (os.getenv("GEMINI_API_KEY") or "").strip()
BASE_URL_NETLIFY = "https://gregarious-frangollo-0346c5.netlify.app"

HISTORIAL_FILE = "historial_perlas.json"

print("🔥 INICIANDO MOTOR TÁCTICO INTEGRADO (MAPA DE CALOR + IA + SPOT REAL)...")

def cargar_historial():
    if os.path.exists(HISTORIAL_FILE):
        try:
            with open(HISTORIAL_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return {"fecha": datetime.now().strftime('%Y-%m-%d'), "mencionadas": {}, "resumen_dia": []}

def guardar_historial(historial):
    try:
        with open(HISTORIAL_FILE, 'w', encoding='utf-8') as f:
            json.dump(historial, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"⚠️ Error guardando historial: {e}")

def crear_sesion_binance():
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json"
    })
    return session

def obtener_simbolos_spot_activos(session):
    urls = [
        "https://api.binance.com/api/v3/exchangeInfo",
        "https://data-api.binance.vision/api/v3/exchangeInfo"
    ]
    for url in urls:
        try:
            res = session.get(url, timeout=12)
            if res.status_code == 200:
                data = res.json()
                simbolos_activos = set()
                for s in data.get('symbols', []):
                    if (s.get('status') == 'TRADING' and 
                        s.get('isSpotTradingAllowed', True) and 
                        s.get('quoteAsset') == 'USDT'):
                        simbolos_activos.add(s.get('symbol'))
                if len(simbolos_activos) > 0:
                    return simbolos_activos
        except Exception as e:
            print(f"⚠️ Error obteniendo exchangeInfo de {url}: {e}")
    return set()

def obtener_datos_binance(session):
    urls = [
        "https://api.binance.com/api/v3/ticker/24hr",
        "https://data-api.binance.vision/api/v3/ticker/24hr"
    ]
    for url in urls:
        try:
            res = session.get(url, timeout=15)
            if res.status_code == 200:
                data = res.json()
                if isinstance(data, list) and len(data) > 0:
                    return data
        except Exception as e:
            print(f"⚠️ Error al conectar con {url}: {e}")
    return []

def formatear_precio(precio):
    if precio >= 1.0:
        return f"${precio:.2f}"
    elif precio >= 0.01:
        return f"${precio:.4f}"
    elif precio >= 0.0001:
        return f"${precio:.6f}"
    else:
        return f"${precio:.8f}"

def evaluar_estado_semaforo(posicion_pct):
    if posicion_pct > 65.0:
        return "ROJO", "🔴 Próxima Ganadora (Explosión Inminente)", "#ff1744", "🔴"
    elif posicion_pct >= 30.0:
        return "AMARILLO", "🟡 Posibilidad Media (Confirmación Táctica)", "#ffd600", "🟡"
    else:
        return "VERDE", "🟢 Cazada en Inicios (Acumulación Fria)", "#00e676", "🟢"

def motor_ia_seleccion_tactica(tickers, simbolos_activos, historial):
    PALABRAS_PROHIBIDAS_BASE = ['USD', 'EUR', 'GBP', 'AUD', 'BRL', 'DAI', 'USDT', 'USDC', 'FDUSD', 'TUSD', 'USDP', 'BUSD']
    MEGA_CAPS = ['BTC', 'ETH', 'SOL', 'ADA', 'XRP', 'DOGE', 'TRX', 'SHIB', 'AVAX', 'LINK', 'BNB', 'DOT', 'NEAR', 'SUI', 'PEPE']
    EXCLUIDOS_TOTALES = set(MEGA_CAPS)
    
    hoy_str = datetime.now().strftime('%Y-%m-%d')
    if historial.get("fecha") != hoy_str:
        historial = {"fecha": hoy_str, "mencionadas": {}, "resumen_dia": []}
    
    mencionadas = historial.get("mencionadas", {})
    
    for sym in list(mencionadas.keys()):
        mencionadas[sym] -= 1
        if mencionadas[sym] <= 0:
            del mencionadas[sym]

    candidatas_rojas = []
    candidatas_amarillas = []
    candidatas_verdes = []
    total_analizadas = 0
    
    for t in tickers:
        symbol = t.get('symbol', '')
        base = symbol.replace('USDT', '')
        
        if symbol in mencionadas:
            continue
        if any(p in base for p in PALABRAS_PROHIBIDAS_BASE):
            continue
        if any(x in symbol for x in ['UP', 'DOWN', 'BULL', 'BEAR']):
            continue
        
        if (symbol in simbolos_activos and 
            symbol.endswith('USDT') and 
            base not in EXCLUIDOS_TOTALES):
            
            try:
                precio = float(t.get('lastPrice', 0))
                cambio_24h = float(t.get('priceChangePercent', 0))
                vol_usdt = float(t.get('quoteVolume', 0))
                high = float(t.get('highPrice', 0))
                low = float(t.get('lowPrice', 0))
                
                if (0.000001 <= precio < 1.00 and 
                    25_000 <= vol_usdt <= 35_000_000 and 
                    -6.0 <= cambio_24h <= 10.0):
                    
                    total_analizadas += 1
                    
                    pos_liquidez_pct = ((precio - low) / (high - low)) * 100 if high > low else 50.0
                    pos_liquidez_pct = round(pos_liquidez_pct, 1)
                    
                    categoria, estado_texto, color_hex, emoji_semaforo = evaluar_estado_semaforo(pos_liquidez_pct)
                    
                    rango = high - low
                    pct_rango = (rango / precio) * 100 if precio > 0 else 1
                    factor_spike = (vol_usdt / 1_000_000) / (pct_rango if pct_rango > 0 else 1)
                    
                    score_ia = factor_spike * (1.0 + (pos_liquidez_pct / 100.0) if categoria != "VERDE" else 1.5 - (pos_liquidez_pct / 100.0)) * (abs(cambio_24h) + 1.0)
                    
                    item = {
                        'symbol': symbol,
                        'ticker': base,
                        'precio_f': precio,
                        'cambio_f': cambio_24h,
                        'vol_f': vol_usdt,
                        'high_f': high,
                        'low_f': low,
                        'pos_liquidez_pct': pos_liquidez_pct,
                        'categoria': categoria,
                        'estado_texto': estado_texto,
                        'color_hex': color_hex,
                        'emoji_semaforo': emoji_semaforo,
                        'factor_spike': round(factor_spike, 2),
                        'score_ia': score_ia
                    }
                    
                    if categoria == "ROJO":
                        candidatas_rojas.append(item)
                    elif categoria == "AMARILLO":
                        candidatas_amarillas.append(item)
                    else:
                        candidatas_verdes.append(item)
            except (ValueError, TypeError):
                continue
                
    top_rojas = sorted(candidatas_rojas, key=lambda x: x['score_ia'], reverse=True)[:5]
    top_amarillas = sorted(candidatas_amarillas, key=lambda x: x['score_ia'], reverse=True)[:5]
    top_verdes = sorted(candidatas_verdes, key=lambda x: x['score_ia'], reverse=True)[:5]
    
    matriz_15_perlas = top_rojas + top_amarillas + top_verdes
    
    for item in matriz_15_perlas:
        sym = item['symbol']
        mencionadas[sym] = 3
        if sym not in historial["resumen_dia"]:
            historial["resumen_dia"].append(sym)
            
    historial["mencionadas"] = mencionadas
    guardar_historial(historial)
    
    return matriz_15_perlas, total_analizadas, historial

def generar_grafico_matriz(lista_items, filename="grafico_cazador_15.png"):
    simbolos = [item['ticker'] for item in lista_items]
    posiciones = [item['pos_liquidez_pct'] for item in lista_items]
    colores = [item['color_hex'] for item in lista_items]
    
    fig, ax = plt.subplots(figsize=(12, 6), facecolor='#0b132b')
    ax.set_facecolor('#0b132b')
    
    bars = ax.bar(simbolos, posiciones, color=colores, width=0.55, zorder=3)
    ax.grid(True, color='#1e293b', linestyle='-', linewidth=0.8, zorder=1)
    ax.set_axisbelow(True)
    
    ax.set_ylim(0, 115)
    for spine in ['top', 'right', 'left', 'bottom']:
        ax.spines[spine].set_visible(False)
        
    ax.tick_params(left=False, labelleft=False, bottom=False)
    ax.tick_params(axis='x', colors='white', labelsize=8, rotation=35)
    
    for bar, sim, pos, color in zip(bars, simbolos, posiciones, colores):
        yval = bar.get_height()
        xval = bar.get_x() + bar.get_width() / 2.0
        
        ax.text(xval, yval + 2.5, f"{pos:.0f}%", 
                ha='center', va='bottom', color=color, fontweight='bold', fontsize=8)
        
        ax.plot(xval, max(yval / 2.0, 12), marker='o', markersize=12, markerfacecolor='#0f172a', markeredgecolor=color, markeredgewidth=1.8, zorder=4)
        ax.text(xval, max(yval / 2.0, 12), sim, ha='center', va='center', color='white', fontsize=5.5, fontweight='bold', zorder=5)

    fecha_str = datetime.now().strftime('%Y-%m-%d')
    plt.title("🔥 TERMÓMETRO TÁCTICO • 15 PERLAS EN COMPRESIÓN (5 ROJAS / 5 AMARILLAS / 5 VERDES)", loc='left', color='#ffab00', fontsize=10, fontweight='bold', pad=12)
    ax.text(0.0, 1.02, f"Fecha: {fecha_str}", transform=ax.transAxes, color='#94a3b8', fontsize=8)
    
    plt.tight_layout()
    plt.savefig(filename, dpi=300, facecolor=fig.get_facecolor(), edgecolor='none')
    plt.close()
    return filename

def generar_dictamen_ia(lista_items):
    if not GEMINI_API_KEY:
        return "Máxima atención a los activos en fase Roja y Amarilla: compresión extrema detectada para explosión inmediata."
    
    client = genai.Client(api_key=GEMINI_API_KEY)
    lista_texto = "\n".join([f"- {i['ticker']} [{i['categoria']}]: Precio {i['precio_f']}, Var {i['cambio_f']}%, Liquidez Rango: {i['pos_liquidez_pct']}%" for i in lista_items])
    
    prompt = f"""
    Actúa como un analista institucional de criptomonedas y validador de redes sociales experto en pre-explosiones inminentes. Evalúa estas 15 perlas institucionales detectadas en Binance Spot bajo compresión de volumen y mapas de calor:

    {lista_texto}

    Escribe un dictamen táctico directo de máximo 4 líneas destacando cuáles son los activos con mayor presión inminente de ruptura para las próximas horas.
    """
    for mod in ['gemini-2.5-flash', 'gemini-1.5-flash']:
        try:
            response = client.models.generate_content(model=mod, contents=prompt)
            if response and response.text:
                return response.text
        except Exception:
            continue
    return "Máxima atención a los activos en fase Roja y Amarilla: acumulación silenciosa lista para dispararse en corto plazo."

def enviar_telegram(image_path, caption_text):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("⚠️ Faltan credenciales de Telegram.")
        return
        
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "caption": caption_text,
        "parse_mode": "HTML"
    }
    
    if TELEGRAM_TOPIC_ID:
        try:
            payload["message_thread_id"] = int(TELEGRAM_TOPIC_ID)
        except ValueError:
            pass

    try:
        with open(image_path, 'rb') as photo:
            res = requests.post(url, data=payload, files={"photo": photo}, timeout=45)
            resultado = res.json()
            
            if not resultado.get("ok") and "message thread not found" in str(resultado.get("description", "")):
                payload.pop("message_thread_id", None)
                photo.seek(0)
                res = requests.post(url, data=payload, files={"photo": photo}, timeout=45)
                resultado = res.json()

            if not resultado.get("ok"):
                print(f"❌ Telegram rechazó el mensaje: {resultado.get('description')}")
            else:
                print("✅ ¡Foto entregada con éxito en Telegram!")
    except Exception as e:
        print(f"❌ Excepción crítica al conectar con Telegram: {e}")

def enviar_texto_telegram(texto):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": texto,
        "parse_mode": "HTML"
    }
    if TELEGRAM_TOPIC_ID:
        try:
            payload["message_thread_id"] = int(TELEGRAM_TOPIC_ID)
        except ValueError:
            pass
    try:
        res = requests.post(url, data=payload, timeout=30)
        resultado = res.json()
        if not resultado.get("ok") and "message thread not found" in str(resultado.get("description", "")):
            payload.pop("message_thread_id", None)
            requests.post(url, data=payload, timeout=30)
    except Exception as e:
        print(f"⚠️ Error enviando mensaje de texto: {e}")

if __name__ == "__main__":
    print("🔥 EJECUTANDO ESCÁNER TÁCTICO DE 15 PERLAS...")
    session = crear_sesion_binance()
    simbolos_activos = obtener_simbolos_spot_activos(session)
    datos = obtener_datos_binance(session)
    
    if datos and len(simbolos_activos) > 0:
        historial = cargar_historial()
        matriz_15_perlas, total_analizadas, historial = motor_ia_seleccion_tactica(datos, simbolos_activos, historial)
        
        if len(matriz_15_perlas) > 0:
            filename = generar_grafico_matriz(matriz_15_perlas)
            dictamen_ia = generar_dictamen_ia(matriz_15_perlas)
            
            # 1. Enviar la foto con caption corto
            caption_foto = f"🔥 <b>RADAR TÁCTICO • 15 PERLAS (5 POR COLOR)</b>\n📊 <i>Universo analizado: {total_analizadas} altcoins reales Spot</i>"
            enviar_telegram(filename, caption_foto.strip())
            
            # 2. Enviar el desglose completo de las 15 perlas en un mensaje de texto independiente
            mensaje_detalle = f"💡 <b>Dictamen IA / Redes:</b>\n{dictamen_ia}\n\n"
            
            categorias = [
                ("ROJO", "🔴 <b>EXPLOSIÓN INMINENTE (Top 5)</b>"),
                ("AMARILLO", "🟡 <b>CONFIRMACIÓN TÁCTICA (Top 5)</b>"),
                ("VERDE", "🟢 <b>ACUMULACIÓN EN INICIOS (Top 5)</b>")
            ]
            
            for cat_key, cat_title in categorias:
                mensaje_detalle += f"{cat_title}\n"
                for item in matriz_15_perlas:
                    if item['categoria'] == cat_key:
                        sim = item['ticker']
                        precio_str = formatear_precio(item['precio_f'])
                        unique_id = int(time.time() * 1000) + random.randint(1, 9999)
                        url_ia = f"{BASE_URL_NETLIFY}/?coin={sim}&price={item['precio_f']}&change={item['cambio_f']}&high={item['high_f']}&low={item['low_f']}&v={sim}_{unique_id}"
                        url_trade = f"https://www.binance.com/es/trade/{sim}_USDT"
                        
                        mensaje_detalle += f"• <b>{sim}</b> ({item['cambio_f']:+.1f}%) | {precio_str} | Rango: {item['pos_liquidez_pct']}%\n"
                        mensaje_detalle += f"  └ <a href=\"{html.escape(url_ia)}\">📊 Resumen IA</a> | <a href=\"{html.escape(url_trade)}\">🔶 Tradear</a>\n"
                mensaje_detalle += "\n"
                
            enviar_texto_telegram(mensaje_detalle.strip())
            
            # --- CIERRE DIARIO (21:00 hs / 9 PM) ---
            hora_actual = datetime.now().hour
            if hora_actual >= 21 and not historial.get("resumen_enviado_hoy", False):
                monedas_dia = [s.replace('USDT', '') for s in historial.get("resumen_dia", [])]
                if monedas_dia:
                    resumen_texto = f"📋 <b>RESUMEN DIARIO • GANADORAS TÁCTICAS (9 PM)</b>\n"
                    resumen_texto += f"📅 <i>Fecha: {datetime.now().strftime('%Y-%m-%d')}</i>\n\n"
                    resumen_texto += f"Total de perlas analizadas y mencionadas en el día:\n"
                    resumen_texto += f"<code>{', '.join(monedas_dia)}</code>\n\n"
                    resumen_texto += f"<i>Historial consolidado con éxito. ¡Excelente sesión de trading!</i>"
                    
                    enviar_texto_telegram(resumen_texto)
                    historial["resumen_enviado_hoy"] = True
                    guardar_historial(historial)
                    print("✅ Resumen diario de las 9 PM enviado correctamente.")
