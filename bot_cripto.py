import os
import re
import json
import time
import random
import requests
import html
from datetime import datetime, timezone, timedelta
import numpy as np
import matplotlib.pyplot as plt
from google import genai

# --- CONFIGURACIÓN DE VARIABLES DE ENTORNO ---
TZ_ART = timezone(timedelta(hours=-3))

TELEGRAM_BOT_TOKEN = (os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("TELEGRAM_TOKEN") or "").strip()
TELEGRAM_CHAT_ID = (os.getenv("TELEGRAM_CHAT_ID") or os.getenv("CHAT_ID") or "").strip()
TELEGRAM_TOPIC_ID = (os.getenv("TOPIC_ID_CENTRAL") or "1").strip()
GEMINI_API_KEY = (os.getenv("GEMINI_API_KEY") or "").strip()
BASE_URL_NETLIFY = "https://gregarious-frangollo-0346c5.netlify.app"

ARCHIVO_MEMORIA = "ultimas_perlas.json"

def ahora_art():
    return datetime.now(TZ_ART)

def cargar_memoria_perlas():
    if os.path.exists(ARCHIVO_MEMORIA):
        try:
            with open(ARCHIVO_MEMORIA, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return []
    return []

def guardar_memoria_perlas(historial_reportes):
    try:
        with open(ARCHIVO_MEMORIA, 'w', encoding='utf-8') as f:
            json.dump(historial_reportes[-2:], f, indent=2)
    except Exception as e:
        print(f"Error guardando memoria: {e}")

def crear_sesion_binance():
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json"
    })
    return session

def obtener_simbolos_spot_activos(session):
    urls = [
        "https://data-api.binance.vision/api/v3/exchangeInfo",
        "https://api.binance.com/api/v3/exchangeInfo",
        "https://api1.binance.com/api/v3/exchangeInfo"
    ]
    for url in urls:
        try:
            res = session.get(url, timeout=12)
            if res.status_code == 200:
                simbolos_activos = set()
                for s in res.json().get('symbols', []):
                    # Solo pares Spot USDT activos en el tablero principal (excluye permisos especiales o deslistados)
                    if (s.get('status') == 'TRADING' and
                        s.get('isSpotTradingAllowed', True) and
                        s.get('quoteAsset') == 'USDT'):
                        simbolos_activos.add(s.get('symbol'))
                if simbolos_activos:
                    print(f"✅ Catálogo Spot validado: {len(simbolos_activos)} pares USDT activos.")
                    return simbolos_activos
        except Exception as e:
            print(f"⚠️ Error catálogo {url}: {e}")
    return set()

def obtener_datos_binance(session):
    urls = [
        "https://data-api.binance.vision/api/v3/ticker/24hr",
        "https://api.binance.com/api/v3/ticker/24hr",
        "https://api1.binance.com/api/v3/ticker/24hr"
    ]
    for url in urls:
        try:
            response = session.get(url, timeout=15)
            if response.status_code == 200 and isinstance(response.json(), list):
                data = response.json()
                if data:
                    print(f"✅ Se obtuvieron {len(data)} tickers en vivo.")
                    return data
        except Exception as e:
            print(f"⚠️ Error conectando a {url}: {e}")
    return []

def formatear_precio(precio):
    if precio is None or precio <= 0:
        return "$0.00"
    elif precio >= 100:
        return f"${precio:,.2f}"
    elif precio >= 1.0:
        return f"${precio:.4f}"
    elif precio >= 0.01:
        return f"${precio:.5f}"
    elif precio >= 0.0001:
        return f"${precio:.6f}"
    else:
        return f"${precio:.8f}"

def generar_barra_progreso(cambio, tipo_bloque=""):
    if tipo_bloque == "acumulacion_24h":
        return "🟨🟨🟨⬜⬜"
    elif tipo_bloque == "silenciosa":
        return "💎💎💎💎⬜"
    if cambio >= 50:
        return "🟢🟢🟢🟢🟢"
    elif cambio >= 25:
        return "🟢🟢🟢🟢⬜"
    elif cambio >= 15:
        return "🟢🟢🟢⬜⬜"
    elif cambio >= 5:
        return "🟢🟢⬜⬜⬜"
    elif cambio > 0:
        return "🟢⬜⬜⬜⬜"
    elif cambio > -5:
        return "🟥🟥⬜⬜⬜"
    elif cambio > -12:
        return "🟥🟥🟥⬜⬜"
    elif cambio > -20:
        return "🟥🟥🟥🟥⬜"
    else:
        return "🟥🟥🟥🟥🟥"

def seleccionar_silenciosas_con_gemini(candidatas, historial_previo):
    """
    Usa Gemini IA para elegir las 7 mejores monedas en acumulación silenciosa
    analizando compresión de rango, liquidez y rotación.
    """
    simbolos_bloqueados = {item for reporte in historial_previo for item in reporte}
    pool = [c for c in candidatas if c['symbol'] not in simbolos_bloqueados]
    if len(pool) < 7:
        pool = candidatas

    # Orden base por presión de volumen sobre rango estrecho
    pool_ordenado = sorted(pool, key=lambda x: x['factor_vol'], reverse=True)[:20]

    if not GEMINI_API_KEY or not pool_ordenado:
        return pool_ordenado[:7]

    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
        resumen_candidatas = []
        for c in pool_ordenado:
            sim = c['base_asset']
            resumen_candidatas.append(
                f"{sim}: precio={formatear_precio(c['lastPrice_f'])}, var24h={c['priceChangePercent_f']:+.2f}%, "
                f"rango24h={c['pct_rango']:.2f}%, volUSDT={int(c['quoteVolume_f']):,}, presion=x{c['factor_vol']}"
            )

        prompt = (
            "Eres un analista cuantitativo de criptomonedas en Binance Spot. "
            "De la siguiente lista de activos con alta liquidez y movimiento lateral/contenido, "
            "selecciona exactamente los 7 símbolos con mayor probabilidad de acumulación silenciosa institucional "
            "antes de una ruptura alcista. Devuelve ÚNICAMENTE los 7 tickers separados por coma (ejemplo: ARB,OP,NEAR,SEI,TIA,IMX,INJ) "
            "sin texto adicional.\n\nCandidatas:\n" + "\n".join(resumen_candidatas)
        )

        for mod in ['gemini-2.5-flash', 'gemini-1.5-flash']:
            try:
                res = client.models.generate_content(model=mod, contents=prompt)
                if res and res.text:
                    elegidos_raw = [x.strip().upper().replace("USDT", "") for x in res.text.split(",")]
                    mapa = {c['base_asset']: c for c in pool_ordenado}
                    seleccion = []
                    for sym in elegidos_raw:
                        if sym in mapa and mapa[sym] not in seleccion:
                            seleccion.append(mapa[sym])
                    # Completar hasta 7 si Gemini devolvió menos
                    for c in pool_ordenado:
                        if len(seleccion) >= 7:
                            break
                        if c not in seleccion:
                            seleccion.append(c)
                    print(f"🧠 Gemini IA seleccionó acumulación silenciosa: {[x['base_asset'] for x in seleccion[:7]]}")
                    return seleccion[:7]
            except Exception:
                continue
    except Exception as e:
        print(f"⚠️ Fallback cuantitativo en silenciosas (error Gemini): {e}")

    return pool_ordenado[:7]

def preparar_datos(tickers, simbolos_activos):
    usdt_pairs_todos = {}
    usdt_pairs_spot_web = []

    # Excluir monedas estables, fiat y tokens apalancados/anómalos fuera del tablero principal
    EXCLUIDOS = {
        'USDT', 'USDC', 'FDUSD', 'DAI', 'TUSD', 'USDP', 'EUR', 'BUSD',
        'AEUR', 'EURI', 'USD1', 'USDE', 'RLUSD', 'XUSD', 'BFUSD', 'PAXG',
        'CREAM', 'EPX', 'FOR', 'VGX', 'WNXM', 'BOND', 'LOOM', 'OAX',
        'MULTI', 'KP3R', 'AKRO', 'BLZ', 'WRX', 'SNXXB', 'MSTRB'
    }

    for t in tickers:
        symbol = t.get('symbol', '')
        if not symbol.endswith('USDT'):
            continue
        base_name = symbol[:-4]

        # Filtrar caracteres no latinos (ej. tickers chinos) y tokens apalancados
        if not re.match(r'^[A-Z0-9]+$', base_name):
            continue
        if any(x in base_name for x in ['UP', 'DOWN', 'BULL', 'BEAR']):
            continue

        if symbol in simbolos_activos:
            try:
                open_p = float(t.get('openPrice', 0))
                last_p = float(t.get('lastPrice', 0))
                vol_q = float(t.get('quoteVolume', 0))
                high_p = float(t.get('highPrice', 0))
                low_p = float(t.get('lowPrice', 0))
                pct_api = float(t.get('priceChangePercent', 0))

                if open_p <= 0 or last_p <= 0:
                    continue

                pct_real = ((last_p - open_p) / open_p) * 100
                rango_precio = high_p - low_p
                pct_rango = (rango_precio / last_p) * 100 if last_p > 0 else 1.0

                t['base_asset'] = base_name
                t['openPrice_f'] = open_p
                t['lastPrice_f'] = last_p
                t['priceChangePercent_f'] = pct_real
                t['pct_api_f'] = pct_api
                t['quoteVolume_f'] = vol_q
                t['highPrice_f'] = high_p
                t['lowPrice_f'] = low_p
                t['pct_rango'] = pct_rango

                usdt_pairs_todos[symbol] = t

                # Universo espejo de Binance Web Rankings (excluyendo estables)
                if base_name not in EXCLUIDOS and vol_q >= 100_000:
                    usdt_pairs_spot_web.append(t)
            except (ValueError, TypeError):
                continue

    # 1. TOP 7 GANADORAS (Espejo web Binance)
    ganadoras = sorted(
        [t for t in usdt_pairs_spot_web if t['priceChangePercent_f'] > 0],
        key=lambda x: x['pct_api_f'],
        reverse=True
    )[:7]

    # 2. TOP 7 PERDEDORAS (Espejo web Binance)
    perdedoras = sorted(
        [t for t in usdt_pairs_spot_web if t['priceChangePercent_f'] < 0],
        key=lambda x: x['pct_api_f']
    )[:7]

    # 3. TOP 7 ACUMULACIÓN 24H (Espejo de mayor volumen real en 24h en Binance Spot)
    acumulacion_24h = sorted(
        usdt_pairs_spot_web,
        key=lambda x: x['quoteVolume_f'],
        reverse=True
    )[:7]

    # 4. TOP 7 ACUMULACIÓN SILENCIOSA (Seleccionadas con Gemini IA)
    historial_previo = cargar_memoria_perlas()
    candidatas_silenciosas = []
    for t in usdt_pairs_spot_web:
        if -3.0 <= t['priceChangePercent_f'] <= 3.5 and t['quoteVolume_f'] >= 1_500_000:
            factor_acum = round((t['quoteVolume_f'] / 1_000_000) / max(t['pct_rango'], 0.5), 2)
            t['factor_vol'] = max(1.2, round(1.0 + (factor_acum * 0.12), 1))
            candidatas_silenciosas.append(t)

    acumulacion_silenciosa = seleccionar_silenciosas_con_gemini(candidatas_silenciosas, historial_previo)
    guardar_memoria_perlas(historial_previo + [[t['symbol'] for t in acumulacion_silenciosa]])

    # 5. TUS 5 FAVORITAS
    favoritas_simbolos = ['QI', 'TUT', 'NEIRO', 'LUNC', 'BANK']
    favoritas = [usdt_pairs_todos[f"{sim}USDT"] for sim in favoritas_simbolos if f"{sim}USDT" in usdt_pairs_todos]

    return ganadoras, perdedoras, acumulacion_24h, acumulacion_silenciosa, favoritas

def generar_grafico_tema(lista_items, titulo_grafico, color_barra, filename):
    items_ordenados = sorted(lista_items, key=lambda x: x['priceChangePercent_f'])
    simbolos = [item['base_asset'] for item in items_ordenados]
    cambios = [item['priceChangePercent_f'] for item in items_ordenados]

    fig, ax = plt.subplots(figsize=(8, 4.5), facecolor='#0b132b')
    ax.set_facecolor('#0b132b')

    bars = ax.bar(simbolos, cambios, color=color_barra, width=0.5, zorder=3)
    ax.grid(True, color='#1e293b', linestyle='-', linewidth=0.8, zorder=1)
    ax.set_axisbelow(True)

    for spine in ['top', 'right', 'left', 'bottom']:
        ax.spines[spine].set_visible(False)

    ax.tick_params(left=False, labelleft=False, bottom=False)
    ax.tick_params(axis='x', colors='white', labelsize=10)

    for bar, sim, cambio in zip(bars, simbolos, cambios):
        yval = bar.get_height()
        xval = bar.get_x() + bar.get_width() / 2.0
        offset = 2.5 if yval >= 0 else -5.5

        ax.text(xval, yval + offset, f"+{cambio:.2f}%" if cambio >= 0 else f"{cambio:.2f}%",
                ha='center', va='bottom' if yval >= 0 else 'top', color=color_barra, fontweight='bold', fontsize=9)

        ax.plot(xval, yval + (1.2 if yval >= 0 else -1.2), marker='o', markersize=18, markerfacecolor='#0f172a', markeredgecolor=color_barra, markeredgewidth=1.5, zorder=4)
        ax.text(xval, yval + (1.2 if yval >= 0 else -1.2), sim[:5], ha='center', va='center', color='white', fontsize=7, fontweight='bold', zorder=5)

    fecha_str = ahora_art().strftime('%Y-%m-%d %H:%M ART')
    plt.title(titulo_grafico, loc='left', color='#ffab00', fontsize=12, fontweight='bold', pad=12)
    ax.text(0.0, 1.02, f"Fecha: {fecha_str}", transform=ax.transAxes, color='#94a3b8', fontsize=8)

    plt.tight_layout()
    plt.savefig(filename, dpi=300, facecolor=fig.get_facecolor(), edgecolor='none')
    plt.close()
    return filename

def enviar_foto_y_detalle_blindado(image_path, texto_detalle, max_reintentos=3):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("⚠️ Faltan credenciales de Telegram.")
        return False

    url_base = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"
    thread_id = int(TELEGRAM_TOPIC_ID) if TELEGRAM_TOPIC_ID.isdigit() else None
    esperas = [2, 5, 10]
    cabe_en_caption = len(texto_detalle) <= 1020

    for intento in range(1, max_reintentos + 1):
        try:
            payload_foto = {"chat_id": TELEGRAM_CHAT_ID}
            if thread_id:
                payload_foto["message_thread_id"] = thread_id
            if cabe_en_caption:
                payload_foto["caption"] = texto_detalle
                payload_foto["parse_mode"] = "HTML"

            with open(image_path, 'rb') as photo:
                res = requests.post(f"{url_base}/sendPhoto", data=payload_foto, files={"photo": photo}, timeout=20).json()
                if not res.get("ok") and "thread not found" in str(res.get("description", "")).lower():
                    payload_foto.pop("message_thread_id", None)
                    photo.seek(0)
                    res = requests.post(f"{url_base}/sendPhoto", data=payload_foto, files={"photo": photo}, timeout=20).json()

            if res.get("ok"):
                if not cabe_en_caption:
                    payload_msg = {
                        "chat_id": TELEGRAM_CHAT_ID,
                        "text": texto_detalle,
                        "parse_mode": "HTML",
                        "disable_web_page_preview": True
                    }
                    if thread_id:
                        payload_msg["message_thread_id"] = thread_id
                    res_m = requests.post(f"{url_base}/sendMessage", json=payload_msg, timeout=15).json()
                    if not res_m.get("ok") and "thread not found" in str(res_m.get("description", "")).lower():
                        payload_msg.pop("message_thread_id", None)
                        requests.post(f"{url_base}/sendMessage", json=payload_msg, timeout=15)
                print("✅ Bloque enviado exitosamente.")
                return True
        except Exception as e:
            print(f"⚠️ Error envío intento {intento}: {e}")

        if intento < max_reintentos:
            time.sleep(esperas[intento - 1])

    return False

def procesar_y_enviar_bloque_unificado(num_bloque, titulo_bloque, icono, lista_items, color_grafico, filename_grafico, tipo_bloque=""):
    if not lista_items:
        return

    print(f"Generando Bloque {num_bloque}/5: {titulo_bloque}...")
    generar_grafico_tema(lista_items, f"{icono} {titulo_bloque.upper()} • Ranking 24h", color_grafico, filename_grafico)

    fecha_str = ahora_art().strftime('%Y-%m-%d %H:%M ART')
    titulo_seguro = html.escape(titulo_bloque.upper())

    detalle = (
        f"🧠 <b>CENTRAL DE INTELIGENCIA DE MERCADO ({num_bloque}/5)</b>\n"
        f"{icono} <b>{num_bloque}. {titulo_seguro} (Detalle)</b>\n"
        f"📅 Fecha: <code>{fecha_str}</code>\n\n"
    )

    for item in lista_items:
        sim = item['base_asset']
        base_str = formatear_precio(item['openPrice_f'])
        actual_str = formatear_precio(item['lastPrice_f'])
        cambio = item['priceChangePercent_f']
        high = item['highPrice_f']
        low = item['lowPrice_f']

        barra = generar_barra_progreso(cambio, tipo_bloque=tipo_bloque)
        unique_id = int(time.time() * 1000) + random.randint(1, 99999)

        url_ia = f"{BASE_URL_NETLIFY}/?coin={sim}&price={item['lastPrice_f']}&change={cambio:.2f}&high={high}&low={low}&v={sim}_{unique_id}"
        url_trade = f"https://www.binance.com/es/trade/{sim}_USDT"

        cambio_fmt = f"+{cambio:.2f}%" if cambio >= 0 else f"{cambio:.2f}%"

        if tipo_bloque == "silenciosa":
            vol_rel = item.get('factor_vol', 1.2)
            detalle += (
                f"• <b>{sim}</b> | Base (0%): <code>{base_str}</code> ➔ Actual: <code>{actual_str}</code> | <b>{cambio_fmt}</b>\n"
                f"{barra} <i>[IA Gemini • Presión x{vol_rel:.1f}]</i>\n"
                f"└ <a href=\"{html.escape(url_ia)}\">📊 Resumen IA</a> | <a href=\"{html.escape(url_trade)}\">🔶 Tradear</a>\n\n"
            )
        else:
            detalle += (
                f"• <b>{sim}</b> | Base (0%): <code>{base_str}</code> ➔ Actual: <code>{actual_str}</code> | <b>{cambio_fmt}</b>\n"
                f"{barra}\n"
                f"└ <a href=\"{html.escape(url_ia)}\">📊 Resumen IA</a> | <a href=\"{html.escape(url_trade)}\">🔶 Tradear</a>\n\n"
            )

    enviar_foto_y_detalle_blindado(filename_grafico, detalle.strip())
    time.sleep(2)

if __name__ == "__main__":
    print(f"🚀 INICIANDO CENTRAL DE INTELIGENCIA ({ahora_art().strftime('%H:%M:%S')} ART)...")

    session = crear_sesion_binance()
    simbolos_activos = obtener_simbolos_spot_activos(session)
    datos = obtener_datos_binance(session)

    if datos and simbolos_activos:
        ganadoras, perdedoras, acumulacion_24h, acumulacion_silenciosa, favoritas = preparar_datos(datos, simbolos_activos)

        procesar_y_enviar_bloque_unificado(1, "TOP 7 GANADORAS", "🚀", ganadoras, "#00c853", "grafico_ganadoras.png")
        procesar_y_enviar_bloque_unificado(2, "TOP 7 PERDEDORAS", "📉", perdedoras, "#f6465d", "grafico_perdedoras.png")
        procesar_y_enviar_bloque_unificado(3, "TOP 7 ACUMULACION 24H", "💎", acumulacion_24h, "#ffab00", "grafico_acumulacion_24h.png", tipo_bloque="acumulacion_24h")
        procesar_y_enviar_bloque_unificado(4, "TOP 7 ACUMULACION SILENCIOSA (IA)", "🕵️‍♂️", acumulacion_silenciosa, "#00bcd4", "grafico_silenciosa.png", tipo_bloque="silenciosa")
        procesar_y_enviar_bloque_unificado(5, "TUS 5 FAVORITAS", "⭐", favoritas, "#3861fb", "grafico_favoritas.png")

        print("🎉 ¡Los 5 bloques se enviaron en el nuevo orden y formato!")
    else:
        print("❌ ERROR CRÍTICO: No se pudieron obtener los datos de Binance.")
