import os
import json
import requests
import datetime
import pandas as pd
import yfinance as yf
import matplotlib.pyplot as plt
import squarify
from bs4 import BeautifulSoup
import xml.etree.ElementTree as ET
from google import genai

# ---------------------------------------------------------
# CONFIGURACIÓN DE CREDENCIALES Y RUTAS
# ---------------------------------------------------------
TELEGRAM_BOT_TOKEN = (os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("TELEGRAM_TOKEN") or "").strip()
TELEGRAM_CHAT_ID = (os.getenv("TELEGRAM_CHAT_ID") or os.getenv("CHAT_ID") or "").strip()
MESSAGE_THREAD_ID = (os.getenv("TOPIC_ID_SENTINEL_MACRO") or os.getenv("TELEGRAM_MESSAGE_THREAD_ID") or "").strip()
GEMINI_API_KEY = (os.getenv("GEMINI_API_KEY") or "").strip()

ESTADO_PREVIO_FILE = "datos_sentinel_macro.json"
HISTORIAL_NOTICIAS_FILE = "historial_noticias.json"
DATABASE_ECOSISTEMA_FILE = "database_ecosistema.json"

# ---------------------------------------------------------
# MEMORIA Y COMPARATIVA DE GIROS
# ---------------------------------------------------------
def cargar_estado_previo():
    if os.path.exists(ESTADO_PREVIO_FILE):
        try:
            with open(ESTADO_PREVIO_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def guardar_estado_actual(datos_ws, datos_cripto):
    estado = {
        "timestamp": datetime.datetime.now().isoformat(),
        "wall_street": datos_ws,
        "cripto": datos_cripto
    }
    try:
        with open(ESTADO_PREVIO_FILE, "w", encoding="utf-8") as f:
            json.dump(estado, f, indent=4)
    except Exception as e:
        print("Error guardando estado previo: " + str(e))

def obtener_sesion_actual_mercado():
    hora_actual = datetime.datetime.now().hour
    if 20 <= hora_actual or hora_actual < 4:
        return "🌏 SESIÓN ASIA (Tokio / Hong Kong)"
    elif 4 <= hora_actual < 10:
        return "🌍 SESIÓN EUROPA (Londres / Frankfurt)"
    elif 21 == hora_actual:
        return "🪙 CIERRE DIARIO DE VELA CRIPTO (21:00 ART)"
    else:
        return "🌎 SESIÓN EE. UU. (Wall Street / S&P 500)"

# ---------------------------------------------------------
# 1. MAPA DE CALOR DE S&P 500 (WALL STREET)
# ---------------------------------------------------------
def obtener_datos_wall_street_treemap():
    acciones = {
        "NVDA": ("NVDA", 3.2), "AAPL": ("AAPL", 3.4), "MSFT": ("MSFT", 3.1),
        "GOOGL": ("GOOGL", 2.1), "AMZN": ("AMZN", 2.2), "META": ("META", 1.5),
        "TSLA": ("TSLA", 0.9), "AVGO": ("AVGO", 0.9), "JPM": ("JPM", 0.7),
        "AMD": ("AMD", 0.4), "NFLX": ("NFLX", 0.4), "INTC": ("INTC", 0.3),
        "QCOM": ("QCOM", 0.3), "PEP": ("PEP", 0.4), "KO": ("KO", 0.4),
        "DIS": ("DIS", 0.3), "PYPL": ("PYPL", 0.2), "CSCO": ("CSCO", 0.3)
    }
    datos = []
    for label, (ticker_str, mcap_weight) in acciones.items():
        try:
            t = yf.Ticker(ticker_str)
            hist = t.history(period="2d")
            if len(hist) >= 2:
                p_act = hist['Close'].iloc[-1]
                p_prev = hist['Close'].iloc[-2]
                var = round(((p_act - p_prev) / p_prev) * 100, 2)
            else:
                var = 0.0
        except Exception:
            var = 0.0
        datos.append({"ticker": label, "weight": mcap_weight, "var": var})
    return pd.DataFrame(datos)

def generar_treemap_wall_street(df):
    fig, ax = plt.subplots(figsize=(12, 7), facecolor='#0b0e14')
    ax.set_facecolor('#0b0e14')

    sizes = df['weight']
    labels = [row['ticker'] + "\n" + str(row['var']) + "%" for _, row in df.iterrows()]
    colors = ['#00796b' if v >= 2 else ('#26a69a' if v >= 0 else ('#e53935' if v <= -2 else '#c62828')) for v in df['var']]

    squarify.plot(sizes=sizes, label=labels, color=colors, alpha=0.95,
                  pad=True, edgecolor="#0b0e14", linewidth=2,
                  text_kwargs={'color':'white', 'fontsize':9, 'weight':'bold'}, ax=ax)

    plt.title("MAPA DE CALOR PROFESIONAL — S&P 500 (WALL STREET)", color='#FFD700', fontsize=13, fontweight='bold', pad=15)
    plt.axis('off')
    plt.tight_layout()
    plt.savefig('heatmap_wall_street.png', dpi=300, facecolor=fig.get_facecolor(), edgecolor='none')
    plt.close()

# ---------------------------------------------------------
# 2. MAPA DE CALOR DE CRIPTO (BINANCE)
# ---------------------------------------------------------
def obtener_datos_cripto_treemap():
    criptos = [
        "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", 
        "DOGEUSDT", "ADAUSDT", "AVAXUSDT", "LINKUSDT", "DOTUSDT", 
        "MATICUSDT", "NEARUSDT", "UNIUSDT", "ATOMUSDT", "LTCUSDT"
    ]
    datos = []
    try:
        res = requests.get("https://data-api.binance.vision/api/v3/ticker/24hr", timeout=5).json()
        dict_res = {item['symbol']: item for item in res}
        
        for symbol in criptos:
            if symbol in dict_res:
                item = dict_res[symbol]
                ticker_clean = symbol.replace("USDT", "")
                vol = float(item['quoteVolume'])
                var = round(float(item['priceChangePercent']), 2)
                datos.append({"ticker": ticker_clean, "vol": vol, "var": var})
    except Exception:
        pass
        
    if not datos:
        datos = [{"ticker": "BTC", "vol": 100, "var": -1.5}, {"ticker": "ETH", "vol": 60, "var": -2.8}]
        
    return pd.DataFrame(datos)

def generar_treemap_cripto(df):
    fig, ax = plt.subplots(figsize=(12, 7), facecolor='#0b0e14')
    ax.set_facecolor('#0b0e14')

    sizes = df['vol']
    labels = [row['ticker'] + "\n" + str(row['var']) + "%" for _, row in df.iterrows()]
    colors = ['#00796b' if v >= 2 else ('#26a69a' if v >= 0 else ('#e53935' if v <= -2 else '#c62828')) for v in df['var']]

    squarify.plot(sizes=sizes, label=labels, color=colors, alpha=0.95,
                  pad=True, edgecolor="#0b0e14", linewidth=2,
                  text_kwargs={'color':'white', 'fontsize':9, 'weight':'bold'}, ax=ax)

    plt.title("MAPA DE CALOR PROFESIONAL — BINANCE CRIPTO MARKET", color='#FFD700', fontsize=13, fontweight='bold', pad=15)
    plt.axis('off')
    plt.tight_layout()
    plt.savefig('heatmap_cripto.png', dpi=300, facecolor=fig.get_facecolor(), edgecolor='none')
    plt.close()

# ---------------------------------------------------------
# 3. EXTRAER NOTICIAS EXACTAS DE TRADINGVIEW EN VIVO
# ---------------------------------------------------------
def limpiar_html(texto):
    return texto.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").strip()

def cargar_historial_noticias():
    if os.path.exists(HISTORIAL_NOTICIAS_FILE):
        try:
            with open(HISTORIAL_NOTICIAS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []

def guardar_historial_noticias(noticias):
    try:
        with open(HISTORIAL_NOTICIAS_FILE, "w", encoding="utf-8") as f:
            json.dump(noticias, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print("Error guardando historial de noticias: " + str(e))

def obtener_noticias_cripto_multifuente():
    noticias_candidatas = []
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
        "Referer": "https://es.tradingview.com/"
    }

    # Extracción directa del endpoint de noticias de TradingView en español
    url_tv = "https://es.tradingview.com/markets/cryptocurrencies/news/"
    try:
        res_tv = requests.get(url_tv, headers=headers, timeout=10)
        if res_tv.status_code == 200:
            soup = BeautifulSoup(res_tv.content, "html.parser")
            
            # Buscar elementos de titulares específicos de la tabla de TradingView
            links = soup.find_all("a", href=lambda h: h and ("/news/" in h or "articulo" in h.lower()))
            for l in links:
                titular = l.text.strip()
                href = l.get("href", "")
                if href.startswith("/"):
                    href = "https://es.tradingview.com" + href
                
                # Filtrar textos cortos o menús de navegación irrelevantes
                if titular and len(titular) > 25 and not any(n['titular'] == titular for n in noticias_candidatas):
                    # Intentar detectar el proveedor si está en el contenedor
                    fuente_nombre = "TradingView Markets"
                    parent = l.find_parent("div")
                    if parent:
                        texto_padre = parent.text
                        for prov in ["Cointelegraph", "BeInCrypto", "Investing", "Binance", "Bloomberg", "Reuters"]:
                            if prov.lower() in texto_padre.lower():
                                fuente_nombre = prov
                                break

                    noticias_candidatas.append({
                        'titular': limpiar_html(titular),
                        'enlace': href,
                        'fuente': fuente_nombre
                    })
                    if len(noticias_candidatas) >= 3:
                        break
    except Exception as e:
        print(f"⚠️ Error obteniendo noticias de TradingView: {e}")

    # Respaldo robusto mediante RSS si la estructura web cambia temporalmente
    if len(noticias_candidatas) < 3:
        sources_rss = [
            ("https://es.cointelegraph.com/rss", "Cointelegraph"),
            ("https://es.beincrypto.com/feed/", "BeInCrypto")
        ]
        for url_rss, nombre_fuente in sources_rss:
            try:
                res_rss = requests.get(url_rss, headers=headers, timeout=8)
                if res_rss.status_code == 200:
                    soup_rss = BeautifulSoup(res_rss.content, features="xml")
                    items = soup_rss.find_all('item')
                    for item in items[:5]:
                        t_elem = item.find('title')
                        l_elem = item.find('link')
                        if t_elem and l_elem:
                            titular = t_elem.text.strip().replace("<![CDATA[", "").replace("]]>", "")
                            enlace = l_elem.text.strip()
                            if titular and not any(n['titular'] == titular for n in noticias_candidatas):
                                noticias_candidatas.append({
                                    'titular': limpiar_html(titular),
                                    'enlace': enlace,
                                    'fuente': nombre_fuente
                                })
                                if len(noticias_candidatas) >= 3:
                                    break
                if len(noticias_candidatas) >= 3:
                    break
            except Exception as e:
                print(f"⚠️ Error en RSS respaldo: {e}")

    noticias_actuales = noticias_candidatas[:3]
    
    # Control de memoria y duplicados respecto al último ciclo de 30 minutos
    historial = cargar_historial_noticias()
    titulos_actuales = [n['titular'] for n in noticias_actuales]
    titulos_historial = [n['titular'] for n in historial]
    
    hay_novedades = set(titulos_actuales) != set(titulos_historial)
    
    if hay_novedades and noticias_actuales:
        guardar_historial_noticias(noticias_actuales)

    return noticias_actuales, hay_novedades

# ---------------------------------------------------------
# 4. GENERACIÓN DE DIAGNÓSTICO Y ALERTA DE IA
# ---------------------------------------------------------
def analizar_wall_street_ia(df_ws, sesion, estado_previo):
    if not GEMINI_API_KEY: 
        return "📊 Diagnóstico: Renta variable operando con volatilidad moderada.\n🚨 Alerta: Mantener cautela en posiciones apalancadas."
    
    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
        detalle_actual = {}
        for _, r in df_ws.iterrows():
            detalle_actual[r['ticker']] = r['var']

        prev_ws = estado_previo.get("wall_street", {})
        
        giros = []
        for t, val_act in detalle_actual.items():
            val_prev = prev_ws.get(t, val_act)
            if val_prev < 0 and val_act > 0:
                giros.append(t + " cambió de rojo a verde (+" + str(val_act) + "%)")
            elif val_prev > 0 and val_act < 0:
                giros.append(t + " cambió de verde a rojo (" + str(val_act) + "%)")

        texto_giros = ", ".join(giros) if giros else "Sin cambios drásticos."
        
        partes_txt = []
        for _, r in df_ws.iterrows():
            partes_txt.append(r['ticker'] + ": " + str(r['var']) + "%")
        datos_txt = ", ".join(partes_txt)

        prompt = (
            "Actúa como estratega macro de Wall Street. "
            "Sesión: " + sesion + ". "
            "Datos S&P 500: " + datos_txt + ". "
            "Giros: " + texto_giros + ". "
            "Devuelve strictly dos líneas: "
            "📊 Diagnóstico: [texto corto] y 🚨 Alerta: [texto corto]."
        )

        for mod in ['gemini-2.5-flash', 'gemini-1.5-flash']:
            try:
                res = client.models.generate_content(model=mod, contents=prompt)
                if res and res.text:
                    return res.text.strip()
            except Exception:
                continue
    except Exception as e:
        print("Error analizando Wall Street con Gemini: " + str(e))
        
    return "📊 Diagnóstico: Renta variable operando con volatilidad moderada.\n🚨 Alerta: Mantener cautela en posiciones apalancadas."

def analizar_cripto_ia(df_cripto, sesion, estado_previo):
    if not GEMINI_API_KEY: 
        return "📊 Diagnóstico: Mercado buscando estabilización.\n🚨 Alerta: Monitoreando flujos de liquidez."
    
    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
        detalle_actual = {}
        for _, r in df_cripto.iterrows():
            detalle_actual[r['ticker']] = r['var']

        prev_cripto = estado_previo.get("cripto", {})
        
        giros = []
        for t, val_act in detalle_actual.items():
            val_prev = prev_cripto.get(t, val_act)
            if val_prev < 0 and val_act > 0:
                giros.append(t + " giró a verde (+" + str(val_act) + "%)")
            elif val_prev > 0 and val_act < 0:
                giros.append(t + " giró a rojo (" + str(val_act) + "%)")

        texto_giros = ", ".join(giros) if giros else "Sin giros drásticos."
        
        partes_txt = []
        for _, r in df_cripto.iterrows():
            partes_txt.append(r['ticker'] + ": " + str(r['var']) + "%")
        datos_txt = ", ".join(partes_txt)

        prompt = (
            "Actúa como analista cuantitativo crypto. "
            "Sesión: " + sesion + ". "
            "Binance: " + datos_txt + ". "
            "Giros: " + texto_giros + ". "
            "Devuelve strictly dos líneas: "
            "📊 Diagnóstico: [texto corto] y 🚨 Alerta: [texto corto]."
        )

        for mod in ['gemini-2.5-flash', 'gemini-1.5-flash']:
            try:
                res = client.models.generate_content(model=mod, contents=prompt)
                if res and res.text:
                    return res.text.strip()
            except Exception:
                continue
    except Exception as e:
        print("Error analizando Cripto con Gemini: " + str(e))
        
    return "📊 Diagnóstico: Mercado buscando estabilización.\n🚨 Alerta: Monitoreando flujos de liquidez."

# ---------------------------------------------------------
# FUNCIONES DE ENVÍO ROBUSTO A TELEGRAM (HTML)
# ---------------------------------------------------------
def enviar_foto_telegram(url_base, payload_base, image_path):
    try:
        with open(image_path, 'rb') as f:
            res = requests.post(url_base + "/sendPhoto", data=payload_base, files={'photo': f})
            resultado = res.json()
            if not resultado.get("ok") and "message thread not found" in str(resultado.get("description", "")):
                payload_copia = payload_base.copy()
                payload_copia.pop("message_thread_id", None)
                f.seek(0)
                res = requests.post(url_base + "/sendPhoto", data=payload_copia, files={'photo': f})
    except Exception as e:
        print("⚠️ Error al enviar foto: " + str(e))

def enviar_mensaje_telegram(url_base, payload_base):
    try:
        res = requests.post(url_base + "/sendMessage", json=payload_base)
        resultado = res.json()
        if not resultado.get("ok") and "message thread not found" in str(resultado.get("description", "")):
            payload_copia = payload_base.copy()
            payload_copia.pop("message_thread_id", None)
            res = requests.post(url_base + "/sendMessage", json=payload_copia)
            resultado = res.json()
        print("Telegram Response:", resultado)
        return resultado
    except Exception as e:
        print("⚠️ Error al enviar mensaje: " + str(e))
        return None

# ---------------------------------------------------------
# 6. ACTUALIZACIÓN DEL ECOSISTEMA WEB (JSON)
# ---------------------------------------------------------
def actualizar_base_datos_web(noticias):
    try:
        datos_actuales = {}
        if os.path.exists(DATABASE_ECOSISTEMA_FILE):
            with open(DATABASE_ECOSISTEMA_FILE, "r", encoding="utf-8") as f:
                datos_actuales = json.load(f)
                
        datos_actuales["noticias"] = noticias
        datos_actuales["ultima_actualizacion"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        with open(DATABASE_ECOSISTEMA_FILE, "w", encoding="utf-8") as f:
            json.dump(datos_actuales, f, ensure_ascii=False, indent=4)
        print("📊 Base de datos del ecosistema web actualizada correctamente.")
    except Exception as e:
        print("⚠️ Error actualizando base web: " + str(e))

# ---------------------------------------------------------
# 5. EJECUCIÓN Y ENVÍO
# ---------------------------------------------------------
if __name__ == "__main__":
    print("🌐 Ejecutando Sentinel Macro...")

    sesion_actual = obtener_sesion_actual_mercado()
    estado_previo = cargar_estado_previo()

    # 1. S&P 500
    df_ws = obtener_datos_wall_street_treemap()
    generar_treemap_wall_street(df_ws)
    causas_ws = analizar_wall_street_ia(df_ws, sesion_actual, estado_previo)
    msg_ws = "🏛️ <b>SENTINEL MACRO — 1. S&P 500 & TRADFI</b>\n🕒 <b>Sesión:</b> 🌎 <code>" + sesion_actual + "</code>\n\n" + causas_ws + "\n"

    # 2. Cripto Market
    df_cripto = obtener_datos_cripto_treemap()
    generar_treemap_cripto(df_cripto)
    causas_cripto = analizar_cripto_ia(df_cripto, sesion_actual, estado_previo)
    msg_cripto = "🪙 <b>SENTINEL MACRO — 2. BINANCE CRIPTO MARKET</b>\n🕒 <b>Sesión:</b> 🌎 <code>" + sesion_actual + "</code>\n\n" + causas_cripto + "\n"

    dict_ws_save = {}
    for _, r in df_ws.iterrows():
        dict_ws_save[r['ticker']] = r['var']

    dict_cripto_save = {}
    for _, r in df_cripto.iterrows():
        dict_cripto_save[r['ticker']] = r['var']

    guardar_estado_actual(dict_ws_save, dict_cripto_save)

    # 3. Obtener Noticias y actualizar la Web
    print("📰 Procesando titulares de noticias...")
    noticias_tv, hay_novedades = obtener_noticias_cripto_multifuente()
    actualizar_base_datos_web(noticias_tv)

    if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
        url_base = "https://api.telegram.org/bot" + TELEGRAM_BOT_TOKEN
        thread_id = None
        if MESSAGE_THREAD_ID:
            try:
                thread_id = int(MESSAGE_THREAD_ID)
            except ValueError:
                pass

        teclado_ws = {"inline_keyboard": [[{"text": "📊 Ver Mapa Interactivo S&P 500 (Investing)", "url": "https://es.investing.com/markets/heatmap"}]]}
        teclado_cripto = {"inline_keyboard": [[{"text": "🪙 Ver Mapa Interactivo Binance Futures", "url": "https://www.binance.com/es-AR/futures/crypto-heatmap"}]]}

        # Enviar 1: S&P 500
        p_f1 = {'chat_id': TELEGRAM_CHAT_ID, 'caption': "🗺️ <b>Mapa de Calor — S&P 500 (" + sesion_actual + ")</b>", 'parse_mode': 'HTML'}
        if thread_id: p_f1['message_thread_id'] = thread_id
        enviar_foto_telegram(url_base, p_f1, 'heatmap_wall_street.png')

        p_m1 = {'chat_id': TELEGRAM_CHAT_ID, 'text': msg_ws, 'parse_mode': 'HTML', 'reply_markup': teclado_ws}
        if thread_id: p_m1['message_thread_id'] = thread_id
        enviar_mensaje_telegram(url_base, p_m1)

        # Enviar 2: Cripto
        p_f2 = {'chat_id': TELEGRAM_CHAT_ID, 'caption': "🗺️ <b>Mapa de Calor — Cripto (" + sesion_actual + ")</b>", 'parse_mode': 'HTML'}
        if thread_id: p_f2['message_thread_id'] = thread_id
        enviar_foto_telegram(url_base, p_f2, 'heatmap_cripto.png')

        p_m2 = {'chat_id': TELEGRAM_CHAT_ID, 'text': msg_cripto, 'parse_mode': 'HTML', 'reply_markup': teclado_cripto}
        if thread_id: p_m2['message_thread_id'] = thread_id
        enviar_mensaje_telegram(url_base, p_m2)

        # Enviar 3: NOTICIAS (Solo si hay novedades respecto al ciclo anterior)
        if hay_novedades:
            print("✨ ¡Nuevas noticias detectadas! Enviando alerta a Telegram...")
            msg_noticias = "📰 <b>SENTINEL NOTICIAS — TRADINGVIEW & MARKET HEADLINES</b>\n\n"
            for idx, noticia in enumerate(noticias_tv, 1):
                msg_noticias += str(idx) + ". ⚡ <b>" + noticia['titular'] + "</b>\n"
                msg_noticias += "🔗 <a href=\"" + noticia['enlace'] + "\">Leer en " + noticia['fuente'] + "</a>\n\n"

            p_news = {
                'chat_id': TELEGRAM_CHAT_ID,
                'text': msg_noticias,
                'parse_mode': 'HTML',
                'disable_web_page_preview': True
            }
            if thread_id: p_news['message_thread_id'] = thread_id

            res_noticias = enviar_mensaje_telegram(url_base, p_news)
            print("✅ Resultado del envío de Noticias:", res_noticias)
        else:
            print("ℹ️ Las noticias extraídas coinciden con las del último ciclo. Se omite el envío a Telegram para evitar repetición.")

        print("✅ Ejecución completada exitosamente.")
    else:
        print("⚠️ No se pudo enviar a Telegram: Faltan credenciales.")
