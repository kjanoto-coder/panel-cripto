import os
import json
import time
import random
import html
from datetime import datetime, timezone, timedelta
import requests
import matplotlib.pyplot as plt
from google import genai

# --- CONFIGURACIÓN DE ENTORNO BLINDADA ---
TZ_ART = timezone(timedelta(hours=-3))
TELEGRAM_BOT_TOKEN = (os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("TELEGRAM_TOKEN") or "").strip()
TELEGRAM_CHAT_ID = (os.getenv("TELEGRAM_CHAT_ID") or os.getenv("CHAT_ID") or "").strip()
TELEGRAM_TOPIC_ID = (os.getenv("TOPIC_ID_PRE_EXPLOSION") or os.getenv("TELEGRAM_MESSAGE_THREAD_ID") or os.getenv("TOPIC_ID_CENTRAL") or "").strip()
GEMINI_API_KEY = (os.getenv("GEMINI_API_KEY") or "").strip()
BASE_URL_NETLIFY = "https://gregarious-frangollo-0346c5.netlify.app"

HISTORIAL_FILE = "historial_perlas.json"
DIAS_GRADUADAS = 7

def ahora_art():
    return datetime.now(TZ_ART)

def cargar_historial():
    hoy = ahora_art().strftime('%Y-%m-%d')
    base = {
        "fecha": hoy,
        "mencionadas": {},
        "resumen_dia": [],
        "resumen_enviado_hoy": False,
        "posta": {},
        "graduadas_pre_explosion": {}
    }
    if os.path.exists(HISTORIAL_FILE):
        try:
            with open(HISTORIAL_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)

            base["posta"] = data.get("posta", {}) if isinstance(data.get("posta"), dict) else {}

            grad_limpia = {}
            for sym, info in (data.get("graduadas_pre_explosion") or {}).items():
                try:
                    f_det = datetime.strptime(info.get("fecha_iso", hoy), '%Y-%m-%d').date()
                    if (ahora_art().date() - f_det).days <= DIAS_GRADUADAS:
                        grad_limpia[sym] = info
                except Exception:
                    continue
            base["graduadas_pre_explosion"] = grad_limpia

            if data.get("fecha") == hoy:
                base["mencionadas"] = data.get("mencionadas", {})
                base["resumen_dia"] = data.get("resumen_dia", [])
                base["resumen_enviado_hoy"] = data.get("resumen_enviado_hoy", False)
        except Exception:
            pass
    return base

def guardar_historial(historial):
    try:
        with open(HISTORIAL_FILE, 'w', encoding='utf-8') as f:
            json.dump(historial, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"⚠️ Error guardando historial: {e}")

def crear_sesion_binance():
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json",
        "Cache-Control": "no-cache"
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
                simbolos_activos = {
                    s.get('symbol')
                    for s in data.get('symbols', [])
                    if s.get('status') == 'TRADING'
                    and s.get('isSpotTradingAllowed', True)
                    and s.get('quoteAsset') == 'USDT'
                }
                if simbolos_activos:
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

def obtener_cambios_temporalidades(session, symbol):
    cambio_1h = 0.0
    cambio_4h = 0.0
    for interval in ("1h", "4h"):
        urls = [
            f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit=2",
            f"https://data-api.binance.vision/api/v3/klines?symbol={symbol}&interval={interval}&limit=2"
        ]
        for u in urls:
            try:
                res = session.get(u, timeout=5)
                if res.status_code == 200:
                    candles = res.json()
                    if len(candles) >= 1:
                        open_p = float(candles[-1][1])
                        close_p = float(candles[-1][4])
                        if open_p > 0:
                            pct = round(((close_p - open_p) / open_p) * 100, 2)
                            if interval == "1h":
                                cambio_1h = pct
                            else:
                                cambio_4h = pct
                    break
            except Exception:
                continue
    return cambio_1h, cambio_4h

def formatear_precio(precio):
    if precio is None or precio <= 0:
        return "$0.00"
    if precio >= 100:
        return f"${precio:,.2f}"
    if precio >= 1.0:
        return f"${precio:.4f}"
    if precio >= 0.01:
        return f"${precio:.5f}"
    if precio >= 0.0001:
        return f"${precio:.6f}"
    return f"${precio:.8f}"

def construir_item_desde_ticker(session, t, desde_posta=False, info_grad=None):
    symbol = t.get('symbol', '')
    base = symbol[:-4] if symbol.endswith('USDT') else symbol
    precio = float(t.get('lastPrice', 0))
    cambio_24h = float(t.get('priceChangePercent', 0))
    vol_usdt = float(t.get('quoteVolume', 0))
    high = float(t.get('highPrice', 0))
    low = float(t.get('lowPrice', 0))

    if precio <= 0:
        return None

    cambio_1h, cambio_4h = obtener_cambios_temporalidades(session, symbol)
    pos_liquidez_pct = round(((precio - low) / (high - low)) * 100, 1) if high > low else 50.0
    rango = high - low
    pct_rango = (rango / precio) * 100 if precio > 0 else 1.0
    factor_spike = (vol_usdt / 1_000_000) / (pct_rango if pct_rango > 0 else 1.0)

    # Prioriza impulso fresco en 1h/4h y evita perseguir monedas ya agotadas arriba del 92% del rango diario
    penalizacion_extension = 12.0 if pos_liquidez_pct > 92.0 else 0.0
    bonus_posta = 18.0 if desde_posta else 0.0
    score_ia = round(
        (cambio_1h * 3.2) + (cambio_4h * 2.0) + (cambio_24h * 1.2) + (factor_spike * 1.6) + bonus_posta - penalizacion_extension,
        2
    )

    var_desde_grad = None
    fecha_grad = ""
    if info_grad:
        p_ref = float(info_grad.get("precio_ref", 0) or 0)
        fecha_grad = str(info_grad.get("fecha_corta", ""))
        if p_ref > 0:
            var_desde_grad = round(((precio - p_ref) / p_ref) * 100, 2)

    return {
        'symbol': symbol,
        'ticker': base,
        'precio_f': precio,
        'cambio_f': cambio_24h,
        'cambio_1h': cambio_1h,
        'cambio_4h': cambio_4h,
        'vol_f': vol_usdt,
        'high_f': high,
        'low_f': low,
        'pos_liquidez_pct': pos_liquidez_pct,
        'score_ia': score_ia,
        'desde_posta': desde_posta,
        'var_desde_grad': var_desde_grad,
        'fecha_grad': fecha_grad
    }

def motor_ia_seleccion_tactica(tickers, simbolos_activos, session, historial):
    EXCL_BASE = {
        'USDT', 'USDC', 'FDUSD', 'DAI', 'TUSD', 'USDP', 'EUR', 'GBP', 'AUD', 'BRL', 'ARS', 'TRY', 'BUSD',
        'BTC', 'ETH', 'SOL', 'ADA', 'XRP', 'DOGE', 'TRX', 'SHIB', 'AVAX', 'LINK', 'BNB', 'DOT', 'NEAR', 'SUI', 'PEPE'
    }

    hoy_str = ahora_art().strftime('%Y-%m-%d')
    if historial.get("fecha") != hoy_str:
        historial["fecha"] = hoy_str
        historial["mencionadas"] = {}
        historial["resumen_dia"] = []
        historial["resumen_enviado_hoy"] = False

    mencionadas = historial.get("mencionadas", {})
    for sym in list(mencionadas.keys()):
        mencionadas[sym] -= 1
        if mencionadas[sym] <= 0:
            del mencionadas[sym]

    grad = historial.get("graduadas_pre_explosion", {})
    posta = historial.get("posta", {})

    # Identifica símbolos confirmados en Rojo (⭐⭐⭐) desde Cazador Táctico
    syms_rojo_tactico = set(grad.keys())
    for sym, d in posta.items():
        if int(d.get("etapa", d.get("paso", 1))) == 3:
            syms_rojo_tactico.add(sym)
            if sym not in grad:
                grad[sym] = {
                    "symbol": sym,
                    "base": sym[:-4] if sym.endswith("USDT") else sym,
                    "estrellas": 3,
                    "probabilidad_pct": int(d.get("prob_actual", 75)),
                    "precio_ref": float(d.get("precio_inicio", d.get("precio_actual", 0)) or 0),
                    "fecha_iso": d.get("fecha_iso", hoy_str),
                    "fecha_corta": d.get("fecha_corta", ahora_art().strftime('%d/%m'))
                }

    mapa_tickers = {}
    for t in tickers:
        sym = t.get('symbol', '')
        if sym in simbolos_activos and sym.endswith('USDT'):
            base = sym[:-4]
            if base not in EXCL_BASE and not any(x in base for x in ['UP', 'DOWN', 'BULL', 'BEAR']):
                mapa_tickers[sym] = t

    total_analizadas = 0
    items_posta_roja = []
    candidatas_mercado = []

    # 1) Evalúa primero las monedas confirmadas en Rojo de Cazador Táctico
    for sym in list(syms_rojo_tactico):
        t = mapa_tickers.get(sym)
        if not t:
            continue
        try:
            precio = float(t.get('lastPrice', 0))
            vol_usdt = float(t.get('quoteVolume', 0))
            if precio > 0 and vol_usdt >= 50_000:
                total_analizadas += 1
                it = construir_item_desde_ticker(session, t, desde_posta=True, info_grad=grad.get(sym))
                if it:
                    items_posta_roja.append(it)
        except (ValueError, TypeError):
            continue

    items_posta_roja.sort(key=lambda x: x['score_ia'], reverse=True)
    vistos = {x['symbol'] for x in items_posta_roja}

    # 2) Analiza candidatas Spot adicionales con impulso/estructura sana
    for sym, t in mapa_tickers.items():
        if sym in vistos:
            continue
        if sym in mencionadas:
            continue
        try:
            precio = float(t.get('lastPrice', 0))
            cambio_24h = float(t.get('priceChangePercent', 0))
            vol_usdt = float(t.get('quoteVolume', 0))
            if 0.000001 <= precio < 10.0 and vol_usdt >= 250_000 and -1.5 <= cambio_24h <= 12.0:
                total_analizadas += 1
                it = construir_item_desde_ticker(session, t, desde_posta=False, info_grad=None)
                if it and (it['cambio_1h'] >= -0.2 or it['cambio_4h'] >= 0.3):
                    candidatas_mercado.append(it)
        except (ValueError, TypeError):
            continue

    candidatas_mercado.sort(key=lambda x: x['score_ia'], reverse=True)

    # Completa hasta 15 perlas dando prioridad a las graduadas en Rojo de Cazador Táctico
    seleccion = items_posta_roja[:15]
    cupo_restante = max(0, 15 - len(seleccion))
    if cupo_restante > 0:
        seleccion.extend(candidatas_mercado[:cupo_restante])

    top_rojas = seleccion[:5]
    top_amarillas = seleccion[5:10]
    top_verdes = seleccion[10:15]

    for item in top_rojas:
        item['categoria'], item['estado_texto'], item['color_hex'] = "ROJO", "Pre-Explosión Confirmada", "#ff1744"
    for item in top_amarillas:
        item['categoria'], item['estado_texto'], item['color_hex'] = "AMARILLO", "Confirmación Táctica", "#ffd600"
    for item in top_verdes:
        item['categoria'], item['estado_texto'], item['color_hex'] = "VERDE", "Acumulación / Vigilancia", "#00e676"

    for item in seleccion:
        sym = item['symbol']
        mencionadas[sym] = 2
        if sym not in historial["resumen_dia"]:
            historial["resumen_dia"].append(sym)

    historial["mencionadas"] = mencionadas
    historial["graduadas_pre_explosion"] = grad
    guardar_historial(historial)

    return seleccion, total_analizadas, historial

def generar_grafico_matriz(lista_items, filename="grafico_cazador_15.png"):
    simbolos = [f"{'***' if item.get('desde_posta') else ''}{item['ticker']}" for item in lista_items]
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

    for bar, item, pos, color in zip(bars, lista_items, posiciones, colores):
        yval = bar.get_height()
        xval = bar.get_x() + bar.get_width() / 2.0
        sim = item['ticker']
        if item.get('desde_posta'):
            bar.set_edgecolor('#ffd700')
            bar.set_linewidth(2.0)

        ax.text(xval, yval + 2.5, f"{pos:.0f}%", ha='center', va='bottom', color=color, fontweight='bold', fontsize=8)
        ax.plot(xval, max(yval / 2.0, 12), marker='o', markersize=12, markerfacecolor='#0f172a', markeredgecolor=color, markeredgewidth=1.8, zorder=4)
        ax.text(xval, max(yval / 2.0, 12), sim[:5], ha='center', va='center', color='white', fontsize=5.5, fontweight='bold', zorder=5)

    fecha_str = ahora_art().strftime('%Y-%m-%d %H:%M ART')
    plt.title("PRE-EXPLOSION MULTITEMPORAL (1H / 4H / 24H + POSTA ROJA)", loc='left', color='#ffab00', fontsize=10, fontweight='bold', pad=12)
    ax.text(0.0, 1.02, f"Fecha: {fecha_str} | *** = Viene de Rojo Cazador Tactico", transform=ax.transAxes, color='#94a3b8', fontsize=8)

    plt.tight_layout()
    plt.savefig(filename, dpi=300, facecolor=fig.get_facecolor(), edgecolor='none')
    plt.close()
    return filename

def generar_dictamen_ia(lista_items):
    if not GEMINI_API_KEY or not lista_items:
        return "Prioridad a las monedas graduadas en Rojo desde Cazador Tactico y a las lecturas alineadas en 1h/4h/24h."

    client = genai.Client(api_key=GEMINI_API_KEY)
    lista_texto = "\n".join([
        f"- {i['ticker']} [{'POSTA_ROJA' if i.get('desde_posta') else i['categoria']}]: Precio {i['precio_f']}, 1h: {i['cambio_1h']:+.2f}%, 4h: {i['cambio_4h']:+.2f}%, 24h: {i['cambio_f']:+.2f}%"
        for i in lista_items
    ])

    prompt = f"""
    Analista cuantitativo Binance Spot. Evaluá estas candidatas de Pre-Explosión (algunas vienen confirmadas como POSTA_ROJA desde Cazador Táctico):
    {lista_texto}

    Escribí un dictamen breve (máximo 4 líneas) destacando cuáles tienen mejor alineación multitemporal (1h/4h/24h) y seguimiento desde la posta.
    """
    for mod in ['gemini-2.5-flash', 'gemini-1.5-flash']:
        try:
            response = client.models.generate_content(model=mod, contents=prompt)
            if response and response.text:
                return response.text.strip()
        except Exception:
            continue
    return "Prioridad a las monedas graduadas en Rojo desde Cazador Tactico y a las lecturas alineadas en 1h/4h/24h."

def enviar_telegram_foto(image_path, caption_text):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "caption": caption_text[:1020], "parse_mode": "HTML"}
    if TELEGRAM_TOPIC_ID.isdigit():
        payload["message_thread_id"] = int(TELEGRAM_TOPIC_ID)

    try:
        with open(image_path, 'rb') as photo:
            res = requests.post(url, data=payload, files={"photo": photo}, timeout=45).json()
            if not res.get("ok") and "thread not found" in str(res.get("description", "")).lower():
                payload.pop("message_thread_id", None)
                photo.seek(0)
                requests.post(url, data=payload, files={"photo": photo}, timeout=45)
    except Exception as e:
        print(f"❌ Error enviando foto a Telegram: {e}")

def enviar_texto_telegram(texto):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    tid = int(TELEGRAM_TOPIC_ID) if TELEGRAM_TOPIC_ID.isdigit() else None

    partes, actual = [], ""
    for linea in texto.split("\n"):
        if len(actual) + len(linea) + 1 > 3400:
            if actual.strip():
                partes.append(actual.strip())
            actual = linea + "\n"
        else:
            actual += linea + "\n"
    if actual.strip():
        partes.append(actual.strip())

    for parte in partes:
        payload = {"chat_id": TELEGRAM_CHAT_ID, "text": parte, "parse_mode": "HTML", "disable_web_page_preview": True}
        if tid:
            payload["message_thread_id"] = tid
        try:
            res = requests.post(url, json=payload, timeout=30).json()
            if not res.get("ok") and "thread not found" in str(res.get("description", "")).lower():
                payload.pop("message_thread_id", None)
                requests.post(url, json=payload, timeout=30)
        except Exception as e:
            print(f"⚠️ Error enviando texto: {e}")
        time.sleep(0.8)

if __name__ == "__main__":
    print(f"🔥 EJECUTANDO PRE-EXPLOSIÓN ({ahora_art().strftime('%Y-%m-%d %H:%M:%S')} ART)...")
    session = crear_sesion_binance()
    simbolos_activos = obtener_simbolos_spot_activos(session)
    datos = obtener_datos_binance(session)

    if datos and simbolos_activos:
        historial = cargar_historial()
        matriz_15_perlas, total_analizadas, historial = motor_ia_seleccion_tactica(datos, simbolos_activos, session, historial)

        if matriz_15_perlas:
            filename = generar_grafico_matriz(matriz_15_perlas)
            dictamen_ia = generar_dictamen_ia(matriz_15_perlas)

            grad_count = sum(1 for x in matriz_15_perlas if x.get("desde_posta"))
            caption_foto = (
                f"🔥 <b>RADAR PRE-EXPLOSIÓN MULTITEMPORAL</b>\n"
                f"📊 <i>Analizadas: {total_analizadas} Spot | Desde Rojo Táctico: {grad_count}</i>"
            )
            enviar_telegram_foto(filename, caption_foto)

            mensaje_detalle = f"💡 <b>Dictamen IA:</b>\n{html.escape(dictamen_ia)}\n\n"

            categorias = [
                ("ROJO", "🔴 <b>EXPLOSIÓN INMINENTE (Top 5)</b>"),
                ("AMARILLO", "🟡 <b>CONFIRMACIÓN TÁCTICA (Top 5)</b>"),
                ("VERDE", "🟢 <b>VIGILANCIA / ACUMULACIÓN (Top 5)</b>")
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

                        etiqueta_posta = ""
                        if item.get("desde_posta"):
                            if item.get("var_desde_grad") is not None:
                                etiqueta_posta = f" ⭐⭐⭐ [Posta {item.get('fecha_grad')}: <b>{item['var_desde_grad']:+.2f}%</b>]"
                            else:
                                etiqueta_posta = " ⭐⭐⭐ [Posta Roja]"

                        mensaje_detalle += (
                            f"• <b>{sim}</b>{etiqueta_posta} (1h: {item['cambio_1h']:+.1f}% | 4h: {item['cambio_4h']:+.1f}% | 24h: {item['cambio_f']:+.1f}%) | <code>{precio_str}</code>\n"
                            f"  └ <a href=\"{html.escape(url_ia)}\">📊 Resumen IA</a> | <a href=\"{html.escape(url_trade)}\">🔶 Tradear</a>\n"
                        )
                mensaje_detalle += "\n"

            enviar_texto_telegram(mensaje_detalle.strip())

            hora_actual = ahora_art().hour
            if hora_actual >= 21 and not historial.get("resumen_enviado_hoy", False):
                monedas_dia = [s[:-4] if s.endswith('USDT') else s for s in historial.get("resumen_dia", [])]
                if monedas_dia:
                    resumen_texto = (
                        f"📋 <b>RESUMEN DIARIO PRE-EXPLOSIÓN (21:00 ART)</b>\n"
                        f"📅 <i>Fecha: {ahora_art().strftime('%Y-%m-%d')}</i>\n\n"
                        f"Monedas mencionadas hoy:\n<code>{', '.join(monedas_dia)}</code>"
                    )
                    enviar_texto_telegram(resumen_texto)
                    historial["resumen_enviado_hoy"] = True
                    guardar_historial(historial)
    else:
        print("❌ ERROR: Sin datos o sin símbolos activos de Binance.")

# FIN BOT PRE EXPLOSION
