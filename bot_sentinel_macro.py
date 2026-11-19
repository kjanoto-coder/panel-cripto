import os
import re
import json
import time
import requests
import datetime
import pandas as pd
import yfinance as yf
import matplotlib.pyplot as plt
import squarify
from bs4 import BeautifulSoup
from google import genai

# ---------------------------------------------------------
# CONFIGURACIÓN DE CREDENCIALES, ZONA HORARIA Y RUTAS
# ---------------------------------------------------------
TZ_ART = datetime.timezone(datetime.timedelta(hours=-3))

TELEGRAM_BOT_TOKEN = (os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("TELEGRAM_TOKEN") or "").strip()
TELEGRAM_CHAT_ID = (os.getenv("TELEGRAM_CHAT_ID") or os.getenv("CHAT_ID") or "").strip()
MESSAGE_THREAD_ID = (os.getenv("TOPIC_ID_SENTINEL_MACRO") or os.getenv("TELEGRAM_MESSAGE_THREAD_ID") or "").strip()
GEMINI_API_KEY = (os.getenv("GEMINI_API_KEY") or "").strip()

ESTADO_PREVIO_FILE = "datos_sentinel_macro.json"
HISTORIAL_NOTICIAS_FILE = "historial_noticias.json"
DATABASE_ECOSISTEMA_FILE = "database_ecosistema.json"

GOOGLE_SHEET_URL = "https://docs.google.com/spreadsheets/d/1qMAWNGK7dMaY12wDQ9x3h3iZwJE9klzdtWuoReGE1pg/edit?usp=sharing"
INTERVALO_REPORTE_COMPLETO_MIN = 30  # Reporte completo cada 30 minutos

# ---------------------------------------------------------
# MEMORIA PERSISTENTE Y DETECCIÓN DE GIROS (VERDE <-> ROJO)
# ---------------------------------------------------------
def ahora_art():
    return datetime.datetime.now(TZ_ART)

def cargar_estado_previo():
    if os.path.exists(ESTADO_PREVIO_FILE):
        try:
            with open(ESTADO_PREVIO_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def guardar_estado_actual(datos_ws, datos_cripto, sesgo_ws, sesgo_cripto, ultimo_reporte_iso):
    estado = {
        "timestamp": ahora_art().isoformat(),
        "ultimo_reporte_completo": ultimo_reporte_iso,
        "sesgo_ws": sesgo_ws,
        "sesgo_cripto": sesgo_cripto,
        "wall_street": datos_ws,
        "cripto": datos_cripto
    }
    try:
        with open(ESTADO_PREVIO_FILE, "w", encoding="utf-8") as f:
            json.dump(estado, f, indent=4)
    except Exception as e:
        print("Error guardando estado previo: " + str(e))

def obtener_sesion_actual_mercado():
    hora_actual = ahora_art().hour
    if hora_actual == 21:
        return "🪙 CIERRE DIARIO DE VELA CRIPTO (21:00 ART)"
    elif 20 <= hora_actual or hora_actual < 4:
        return "🌏 SESIÓN ASIA (Tokio / Hong Kong)"
    elif 4 <= hora_actual < 10:
        return "🌍 SESIÓN EUROPA (Londres / Frankfurt)"
    else:
        return "🌎 SESIÓN EE. UU. (Wall Street / S&P 500)"

def evaluar_giro_mercado(df_ws, df_cripto, estado_previo):
    """
    Evalúa si el mercado global (Cripto o Wall Street) cambió de Rojo a Verde o viceversa,
    o si hubo un movimiento brusco respecto al último chequeo.
    """
    # Promedio ponderado Wall Street
    peso_total_ws = df_ws['weight'].sum() or 1
    prom_ws = round((df_ws['var'] * df_ws['weight']).sum() / peso_total_ws, 2)
    sesgo_ws_act = "VERDE" if prom_ws >= 0 else "ROJO"

    # Promedio ponderado por volumen Cripto
    vol_total_cr = df_cripto['vol'].sum() or 1
    prom_cr = round((df_cripto['var'] * df_cripto['vol']).sum() / vol_total_cr, 2)
    sesgo_cr_act = "VERDE" if prom_cr >= 0 else "ROJO"

    sesgo_ws_prev = estado_previo.get("sesgo_ws")
    sesgo_cr_prev = estado_previo.get("sesgo_cripto")
    prev_cr_dict = estado_previo.get("cripto", {})
    prev_ws_dict = estado_previo.get("wall_street", {})

    alertas_giro = []

    # 1. Giro de índice global Cripto
    if sesgo_cr_prev and sesgo_cr_prev != sesgo_cr_act:
        icono = "🟢🚀" if sesgo_cr_act == "VERDE" else "🔴⚠️"
        alertas_giro.append(
            f"{icono} <b>MERCADO CRIPTO GIRÓ DE {sesgo_cr_prev} A {sesgo_cr_act}</b> (Índice ponderado: <b>{prom_cr:+.2f}%</b>)"
        )

    # 2. Giro de índice global Wall Street
    if sesgo_ws_prev and sesgo_ws_prev != sesgo_ws_act:
        icono = "🟢📈" if sesgo_ws_act == "VERDE" else "🔴📉"
        alertas_giro.append(
            f"{icono} <b>WALL STREET (S&P 500) GIRÓ DE {sesgo_ws_prev} A {sesgo_ws_act}</b> (Índice: <b>{prom_ws:+.2f}%</b>)"
        )

    # 3. Giros bruscos individuales en líderes (BTC, ETH, SOL, NVDA, AAPL)
    lideres_cr = ["BTC", "ETH", "SOL", "BNB", "XRP"]
    for _, r in df_cripto.iterrows():
        t = r['ticker']
        v_act = r['var']
        if t in lideres_cr and t in prev_cr_dict:
            v_prev = prev_cr_dict[t]
            if v_prev < 0 and v_act >= 0.3:
                alertas_giro.append(f"🟢 <b>{t}</b> cruzó a VERDE: {v_prev:+.2f}% ➔ <b>{v_act:+.2f}%</b>")
            elif v_prev > 0 and v_act <= -0.3:
                alertas_giro.append(f"🔴 <b>{t}</b> cruzó a ROJO: {v_prev:+.2f}% ➔ <b>{v_act:+.2f}%</b>")
            elif abs(v_act - v_prev) >= 2.0:
                alertas_giro.append(f"⚡ <b>{t}</b> movimiento brusco: {v_prev:+.2f}% ➔ <b>{v_act:+.2f}%</b>")

    for _, r in df_ws.iterrows():
        t = r['ticker']
        v_act = r['var']
        if t in ["NVDA", "AAPL", "MSFT", "TSLA"] and t in prev_ws_dict:
            v_prev = prev_ws_dict[t]
            if v_prev < 0 and v_act >= 0.3:
                alertas_giro.append(f"🟢 <b>{t}</b> (WS) cruzó a VERDE: {v_prev:+.2f}% ➔ <b>{v_act:+.2f}%</b>")
            elif v_prev > 0 and v_act <= -0.3:
                alertas_giro.append(f"🔴 <b>{t}</b> (WS) cruzó a ROJO: {v_prev:+.2f}% ➔ <b>{v_act:+.2f}%</b>")

    return alertas_giro, sesgo_ws_act, sesgo_cr_act, prom_ws, prom_cr

# ---------------------------------------------------------
# 1. MAPA DE CALOR DE S&P 500 (WALL STREET)
# ---------------------------------------------------------
def obtener_datos_wall_street_treemap():
    acciones = {
        "NVDA": 3.2, "AAPL": 3.4, "MSFT": 3.1, "GOOGL": 2.1, "AMZN": 2.2,
        "META": 1.5, "TSLA": 0.9, "AVGO": 0.9, "JPM": 0.7, "AMD": 0.4,
        "NFLX": 0.4, "INTC": 0.3, "QCOM": 0.3, "PEP": 0.4, "KO": 0.4,
        "DIS": 0.3, "PYPL": 0.2, "CSCO": 0.3
    }
    tickers = list(acciones.keys())
    datos = []
    hist_bulk = None

    try:
        hist_bulk = yf.download(tickers, period="5d", interval="1d", progress=False, threads=True)
    except Exception as e:
        print(f"⚠️ Descarga masiva yfinance falló, usando modo individual: {e}")

    for label, mcap_weight in acciones.items():
        var = 0.0
        try:
            if hist_bulk is not None and not hist_bulk.empty and 'Close' in hist_bulk:
                serie = hist_bulk['Close'][label].dropna()
                if len(serie) >= 2:
                    p_act = float(serie.iloc[-1])
                    p_prev = float(serie.iloc[-2])
                    var = round(((p_act - p_prev) / p_prev) * 100, 2)
            else:
                hist = yf.Ticker(label).history(period="5d")
                if len(hist) >= 2:
                    p_act = float(hist['Close'].iloc[-1])
                    p_prev = float(hist['Close'].iloc[-2])
                    var = round(((p_act - p_prev) / p_prev) * 100, 2)
        except Exception:
            var = 0.0
        datos.append({"ticker": label, "weight": mcap_weight, "var": var})
    return pd.DataFrame(datos)

def generar_treemap_wall_street(df):
    fig, ax = plt.subplots(figsize=(12, 7), facecolor='#0b0e14')
    ax.set_facecolor('#0b0e14')

    sizes = df['weight']
    labels = [f"{row['ticker']}\n{row['var']:+.2f}%" for _, row in df.iterrows()]
    colors = ['#00796b' if v >= 2 else ('#26a69a' if v >= 0 else ('#e53935' if v <= -2 else '#c62828')) for v in df['var']]

    squarify.plot(sizes=sizes, label=labels, color=colors, alpha=0.95,
                  pad=True, edgecolor="#0b0e14", linewidth=2,
                  text_kwargs={'color': 'white', 'fontsize': 9, 'weight': 'bold'}, ax=ax)

    plt.title("MAPA DE CALOR PROFESIONAL — S&P 500 (WALL STREET)", color='#FFD700', fontsize=13, fontweight='bold', pad=15)
    plt.axis('off')
    plt.tight_layout()
    plt.savefig('heatmap_wall_street.png', dpi=300, facecolor=fig.get_facecolor(), edgecolor='none')
    plt.close()

# ---------------------------------------------------------
# 2. MAPA DE CALOR DE CRIPTO (BINANCE MULTI-ENDPOINT)
# ---------------------------------------------------------
def obtener_datos_cripto_treemap():
    criptos = [
        "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT",
        "DOGEUSDT", "ADAUSDT", "AVAXUSDT", "LINKUSDT", "DOTUSDT",
        "POLUSDT", "NEARUSDT", "UNIUSDT", "ATOMUSDT", "LTCUSDT"
    ]
    endpoints = [
        "https://data-api.binance.vision/api/v3/ticker/24hr",
        "https://api.binance.com/api/v3/ticker/24hr",
        "https://api1.binance.com/api/v3/ticker/24hr",
        "https://api3.binance.com/api/v3/ticker/24hr"
    ]
    datos = []
    res_json = None

    for url in endpoints:
        try:
            r = requests.get(url, timeout=8)
            if r.status_code == 200:
                res_json = r.json()
                break
        except Exception as e:
            print(f"⚠️ Falló endpoint Binance {url}: {e}")

    if res_json:
        dict_res = {item['symbol']: item for item in res_json if 'symbol' in item}
        for symbol in criptos:
            if symbol in dict_res:
                item = dict_res[symbol]
                ticker_clean = symbol.replace("USDT", "")
                vol = float(item['quoteVolume'])
                var = round(float(item['priceChangePercent']), 2)
                datos.append({"ticker": ticker_clean, "vol": max(vol, 1.0), "var": var})

    if not datos:
        datos = [{"ticker": "BTC", "vol": 100, "var": 0.0}, {"ticker": "ETH", "vol": 60, "var": 0.0}]

    return pd.DataFrame(datos)

def generar_treemap_cripto(df):
    fig, ax = plt.subplots(figsize=(12, 7), facecolor='#0b0e14')
    ax.set_facecolor('#0b0e14')

    sizes = df['vol']
    labels = [f"{row['ticker']}\n{row['var']:+.2f}%" for _, row in df.iterrows()]
    colors = ['#00796b' if v >= 2 else ('#26a69a' if v >= 0 else ('#e53935' if v <= -2 else '#c62828')) for v in df['var']]

    squarify.plot(sizes=sizes, label=labels, color=colors, alpha=0.95,
                  pad=True, edgecolor="#0b0e14", linewidth=2,
                  text_kwargs={'color': 'white', 'fontsize': 9, 'weight': 'bold'}, ax=ax)

    plt.title("MAPA DE CALOR PROFESIONAL — BINANCE CRIPTO MARKET", color='#FFD700', fontsize=13, fontweight='bold', pad=15)
    plt.axis('off')
    plt.tight_layout()
    plt.savefig('heatmap_cripto.png', dpi=300, facecolor=fig.get_facecolor(), edgecolor='none')
    plt.close()

# ---------------------------------------------------------
# 3. NOTICIAS EN VIVO
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
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept-Language": "es-ES,es;q=0.9,en;q=0.8"
    }
    url_tv = "https://es.tradingview.com/markets/cryptocurrencies/news/"
    feeds = [
        "https://es.cointelegraph.com/rss",
        "https://es.beincrypto.com/feed/"
    ]

    for feed_url in feeds:
        if len(noticias_candidatas) >= 3:
            break
        try:
            res_ct = requests.get(feed_url, headers=headers, timeout=10)
            if res_ct.status_code == 200:
                soup_rss = BeautifulSoup(res_ct.content, features="xml")
                for item in soup_rss.find_all('item')[:5]:
                    t_elem = item.find('title')
                    if t_elem:
                        titular = t_elem.text.strip().replace("<![CDATA[", "").replace("]]>", "")
                        if titular and not any(n['titular'] == titular for n in noticias_candidatas):
                            noticias_candidatas.append({
                                'titular': limpiar_html(titular),
                                'enlace': url_tv,
                                'fuente': 'TradingView / Market Feed'
                            })
                            if len(noticias_candidatas) >= 3:
                                break
        except Exception as e:
            print(f"⚠️ Error obteniendo feed {feed_url}: {e}")

    noticias_actuales = noticias_candidatas[:3]
    historial = cargar_historial_noticias()
    hay_novedades = set(n['titular'] for n in noticias_actuales) != set(n['titular'] for n in historial)
    if hay_novedades and noticias_actuales:
        guardar_historial_noticias(noticias_actuales)

    return noticias_actuales, hay_novedades

# ---------------------------------------------------------
# 4. DIAGNÓSTICO IA
# ---------------------------------------------------------
def analizar_mercado_ia(df, sesion, prev_dict, mercado_nombre):
    if not GEMINI_API_KEY:
        return "📊 Diagnóstico: Mercado operando con volatilidad moderada.\n🚨 Alerta: Monitorear niveles clave de soporte y resistencia."
    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
        giros = []
        partes_txt = []
        for _, r in df.iterrows():
            t, val_act = r['ticker'], r['var']
            partes_txt.append(f"{t}: {val_act:+.2f}%")
            val_prev = prev_dict.get(t, val_act)
            if val_prev < 0 and val_act > 0:
                giros.append(f"{t} giró a verde ({val_act:+.2f}%)")
            elif val_prev > 0 and val_act < 0:
                giros.append(f"{t} giró a rojo ({val_act:+.2f}%)")

        prompt = (
            f"Actúa como estratega cuantitativo de {mercado_nombre}. Sesión: {sesion}. "
            f"Datos: {', '.join(partes_txt)}. Giros: {', '.join(giros) if giros else 'Sin cambios drásticos'}. "
            "Devuelve estrictamente dos líneas cortas: "
            "📊 Diagnóstico: [texto] y 🚨 Alerta: [texto]."
        )
        for mod in ['gemini-2.5-flash', 'gemini-1.5-flash']:
            try:
                res = client.models.generate_content(model=mod, contents=prompt)
                if res and res.text:
                    return res.text.strip()
            except Exception:
                continue
    except Exception as e:
        print(f"Error IA ({mercado_nombre}): {e}")
    return "📊 Diagnóstico: Mercado operando con volatilidad moderada.\n🚨 Alerta: Monitorear niveles clave."

# ---------------------------------------------------------
# 5. ENVÍO BLINDADO MULTICAPA A TELEGRAM
# ---------------------------------------------------------
def quitar_etiquetas_html(texto):
    return re.sub(r'<[^>]+>', '', texto)

def enviar_mensaje_blindado(url_base, payload_base, max_reintentos=3):
    """
    Intenta enviar el mensaje por múltiples vías:
    1. Envío normal con HTML y thread_id.
    2. Si falla el tópico, reintenta sin message_thread_id (canal General).
    3. Si falla el formato HTML (HTTP 400), limpia etiquetas y envía texto plano.
    4. Reintenta ante fallos de red o límite de velocidad (HTTP 429).
    """
    esperas = [2, 5, 10]
    for intento in range(1, max_reintentos + 1):
        try:
            res = requests.post(url_base + "/sendMessage", json=payload_base, timeout=15)
            data = res.json()
            if data.get("ok"):
                return data

            desc = str(data.get("description", "")).lower()

            # Fallback 1: Tópico inválido o cerrado -> enviar a General
            if "thread not found" in desc or "topic_closed" in desc:
                p_gen = payload_base.copy()
                p_gen.pop("message_thread_id", None)
                res2 = requests.post(url_base + "/sendMessage", json=p_gen, timeout=15).json()
                if res2.get("ok"):
                    print("⚠️ Enviado a General como respaldo de tópico.")
                    return res2

            # Fallback 2: Error de parseo HTML -> enviar como texto plano
            if "parse entities" in desc or res.status_code == 400:
                p_plain = payload_base.copy()
                p_plain.pop("parse_mode", None)
                p_plain["text"] = quitar_etiquetas_html(p_plain["text"])
                res3 = requests.post(url_base + "/sendMessage", json=p_plain, timeout=15).json()
                if res3.get("ok"):
                    print("⚠️ Enviado en texto plano como respaldo de formato.")
                    return res3

            # Fallback 3: Rate limit de Telegram
            if res.status_code == 429:
                retry_after = data.get("parameters", {}).get("retry_after", 5)
                time.sleep(int(retry_after) + 1)
                continue

            print(f"⚠️ Telegram rechazó intento {intento}: {data}")
        except Exception as e:
            print(f"⚠️ Error de red en intento {intento}: {e}")

        if intento < max_reintentos:
            time.sleep(esperas[intento - 1])

    return None

def enviar_foto_blindada(url_base, payload_base, image_path, max_reintentos=3):
    esperas = [2, 5, 10]
    for intento in range(1, max_reintentos + 1):
        try:
            with open(image_path, 'rb') as f:
                res = requests.post(url_base + "/sendPhoto", data=payload_base, files={'photo': f}, timeout=20)
                data = res.json()
                if data.get("ok"):
                    return True

                desc = str(data.get("description", "")).lower()
                if "thread not found" in desc or "topic_closed" in desc:
                    p_gen = payload_base.copy()
                    p_gen.pop("message_thread_id", None)
                    f.seek(0)
                    res2 = requests.post(url_base + "/sendPhoto", data=p_gen, files={'photo': f}, timeout=20).json()
                    if res2.get("ok"):
                        return True
        except Exception as e:
            print(f"⚠️ Error enviando foto (intento {intento}): {e}")

        if intento < max_reintentos:
            time.sleep(esperas[intento - 1])
    return False

# ---------------------------------------------------------
# 6. ACTUALIZACIÓN WEB
# ---------------------------------------------------------
def actualizar_base_datos_web(noticias):
    datos_actuales = {}
    if os.path.exists(DATABASE_ECOSISTEMA_FILE):
        try:
            with open(DATABASE_ECOSISTEMA_FILE, "r", encoding="utf-8") as f:
                datos_actuales = json.load(f)
        except Exception:
            datos_actuales = {}

    datos_actuales["noticias"] = noticias
    datos_actuales["ultima_actualizacion"] = ahora_art().strftime("%Y-%m-%d %H:%M:%S")

    try:
        with open(DATABASE_ECOSISTEMA_FILE, "w", encoding="utf-8") as f:
            json.dump(datos_actuales, f, ensure_ascii=False, indent=4)
    except Exception as e:
        print("⚠️ Error actualizando base web: " + str(e))

# ---------------------------------------------------------
# 7. EJECUCIÓN PRINCIPAL (GIRO INMEDIATO + REPORTE 30 MIN)
# ---------------------------------------------------------
if __name__ == "__main__":
    print(f"🌐 Ejecutando Sentinel Macro ({ahora_art().strftime('%H:%M:%S')} ART)...")

    sesion_actual = obtener_sesion_actual_mercado()
    estado_previo = cargar_estado_previo()

    df_ws = obtener_datos_wall_street_treemap()
    df_cripto = obtener_datos_cripto_treemap()

    alertas_giro, sesgo_ws, sesgo_cr, prom_ws, prom_cr = evaluar_giro_mercado(df_ws, df_cripto, estado_previo)

    # Verificar si ya pasaron 30 minutos desde el último reporte completo
    enviar_completo = False
    ultimo_rep_str = estado_previo.get("ultimo_reporte_completo")
    if not ultimo_rep_str:
        enviar_completo = True
    else:
        try:
            ultimo_rep_dt = datetime.datetime.fromisoformat(ultimo_rep_str)
            mins_transcurridos = (ahora_art() - ultimo_rep_dt).total_seconds() / 60.0
            if mins_transcurridos >= (INTERVALO_REPORTE_COMPLETO_MIN - 2):
                enviar_completo = True
        except Exception:
            enviar_completo = True

    thread_id = int(MESSAGE_THREAD_ID) if MESSAGE_THREAD_ID.isdigit() else None
    url_base = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"

    # 1. ALERTA INMEDIATA SI HUBO GIRO DE MERCADO (VERDE <-> ROJO)
    if alertas_giro and TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
        print("🚨 ¡Giro brusco detectado! Enviando alerta inmediata...")
        msg_flash = (
            f"🚨 <b>ALERTA DE GIRO DE MERCADO — SENTINEL MACRO</b>\n"
            f"🕒 <b>Hora ART:</b> <code>{ahora_art().strftime('%H:%M')}</code> | {sesion_actual}\n\n"
            + "\n".join(alertas_giro) +
            f"\n\n📊 <b>Estado Global:</b> Cripto <b>{sesgo_cr} ({prom_cr:+.2f}%)</b> | Wall Street <b>{sesgo_ws} ({prom_ws:+.2f}%)</b>"
        )
        p_flash = {
            'chat_id': TELEGRAM_CHAT_ID,
            'text': msg_flash,
            'parse_mode': 'HTML',
            'disable_notification': False
        }
        if thread_id:
            p_flash['message_thread_id'] = thread_id
        enviar_mensaje_blindado(url_base, p_flash)

    # 2. REPORTE COMPLETO CADA 30 MINUTOS
    nuevo_ultimo_reporte = ultimo_rep_str
    if enviar_completo:
        print("📊 Generando reporte completo de 30 minutos...")
        generar_treemap_wall_street(df_ws)
        generar_treemap_cripto(df_cripto)

        causas_ws = analizar_mercado_ia(df_ws, sesion_actual, estado_previo.get("wall_street", {}), "Wall Street S&P 500")
        causas_cripto = analizar_mercado_ia(df_cripto, sesion_actual, estado_previo.get("cripto", {}), "Binance Cripto")

        msg_ws = (
            f"🏛️ <b>SENTINEL MACRO — 1. S&P 500 & TRADFI ({sesgo_ws} {prom_ws:+.2f}%)</b>\n"
            f"🕒 <b>Sesión:</b> <code>{sesion_actual}</code>\n\n{causas_ws}\n"
        )
        msg_cripto = (
            f"🪙 <b>SENTINEL MACRO — 2. BINANCE CRIPTO MARKET ({sesgo_cr} {prom_cr:+.2f}%)</b>\n"
            f"🕒 <b>Sesión:</b> <code>{sesion_actual}</code>\n\n{causas_cripto}\n"
        )

        noticias_tv, _ = obtener_noticias_cripto_multifuente()
        actualizar_base_datos_web(noticias_tv)

        if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
            teclado_ws = {"inline_keyboard": [[{"text": "📊 Ver Mapa Interactivo S&P 500 (Investing)", "url": "https://es.investing.com/markets/heatmap"}]]}
            teclado_cripto = {"inline_keyboard": [[{"text": "🪙 Ver Mapa Interactivo Binance Futures", "url": "https://www.binance.com/es-AR/futures/crypto-heatmap"}]]}
            teclado_central = {
                "inline_keyboard": [
                    [{"text": "🌐 Abrir Panel Web", "url": "https://kjanoto-coder.github.io/panel-cripto/"}],
                    [{"text": "📊 Ver Planilla de Auditoría", "url": GOOGLE_SHEET_URL}]
                ]
            }

            # Bloque 1: Wall Street
            p_f1 = {'chat_id': TELEGRAM_CHAT_ID, 'caption': f"🗺️ <b>Mapa de Calor — S&P 500 ({sesion_actual})</b>", 'parse_mode': 'HTML'}
            if thread_id: p_f1['message_thread_id'] = thread_id
            enviar_foto_blindada(url_base, p_f1, 'heatmap_wall_street.png')

            p_m1 = {'chat_id': TELEGRAM_CHAT_ID, 'text': msg_ws, 'parse_mode': 'HTML', 'reply_markup': teclado_ws}
            if thread_id: p_m1['message_thread_id'] = thread_id
            enviar_mensaje_blindado(url_base, p_m1)

            # Bloque 2: Cripto
            p_f2 = {'chat_id': TELEGRAM_CHAT_ID, 'caption': f"🗺️ <b>Mapa de Calor — Cripto ({sesion_actual})</b>", 'parse_mode': 'HTML'}
            if thread_id: p_f2['message_thread_id'] = thread_id
            enviar_foto_blindada(url_base, p_f2, 'heatmap_cripto.png')

            p_m2 = {'chat_id': TELEGRAM_CHAT_ID, 'text': msg_cripto, 'parse_mode': 'HTML', 'reply_markup': teclado_cripto}
            if thread_id: p_m2['message_thread_id'] = thread_id
            enviar_mensaje_blindado(url_base, p_m2)

            # Bloque 3: Noticias
            if noticias_tv:
                msg_noticias = "📰 <b>SENTINEL NOTICIAS — TRADINGVIEW & MARKET HEADLINES</b>\n\n"
                for idx, noticia in enumerate(noticias_tv, 1):
                    msg_noticias += f"{idx}. ⚡ <b>{noticia['titular']}</b>\n🔗 <a href=\"{noticia['enlace']}\">Leer en TradingView</a>\n\n"

                p_news = {
                    'chat_id': TELEGRAM_CHAT_ID,
                    'text': msg_noticias,
                    'parse_mode': 'HTML',
                    'disable_web_page_preview': True,
                    'reply_markup': teclado_central
                }
                if thread_id: p_news['message_thread_id'] = thread_id
                enviar_mensaje_blindado(url_base, p_news)

        nuevo_ultimo_reporte = ahora_art().isoformat()
    else:
        print("⏳ Aún no se cumplen 30 min para el reporte completo (solo se vigiló giro de mercado).")

    # Guardar memoria actualizada para la próxima comparación
    dict_ws_save = {r['ticker']: r['var'] for _, r in df_ws.iterrows()}
    dict_cripto_save = {r['ticker']: r['var'] for _, r in df_cripto.iterrows()}
    guardar_estado_actual(dict_ws_save, dict_cripto_save, sesgo_ws, sesgo_cr, nuevo_ultimo_reporte)
