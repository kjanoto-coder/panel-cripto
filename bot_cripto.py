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
PRECIO_MAX_SILENCIOSA = 5.00  # Tope máximo en USD para altcoins accesibles en Bloque 4

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
    Usa Gemini IA para elegir las 7 mejores altcoins económicas (< $5 USD)
    en acumulación silenciosa alcista (sin BTC/ETH/SOL, sin stablecoins y sin monedas en caída).
    """
    simbolos_bloqueados = {item for reporte in historial_previo for item in reporte}
    pool = [c for c in candidatas if c['symbol'] not in simbolos_bloqueados]
    if len(pool) < 7:
        pool = candidatas

    # Ordena combinando presión de volumen y fortaleza cerca del máximo intradía
    pool_ordenado = sorted(
        pool,
        key=lambda x: (x['factor_vol'] * (0.5 + x['pos_rango'])),
        reverse=True
    )[:22]

    if not GEMINI_API_KEY or not pool_ordenado:
        return pool_ordenado[:7]

    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
        resumen_candidatas = []
        for c in pool_ordenado:
            sim = c['base_asset']
            resumen_candidatas.append(
                f"{sim}: precio={formatear_precio(c['lastPrice_f'])}, var24h={c['priceChangePercent_f']:+.2f}%, "
                f"posEnRango24h={int(c['pos_rango']*100)}%, rango24h={c['pct_rango']:.2f}%, "
                f"volUSDT={int(c['quoteVolume_f']):,}, presion=x{c['factor_vol']:.1f}"
            )

        prompt = (
            "Eres un analista cuantitativo especialista en altcoins económicas en Binance Spot. "
            "De la siguiente lista (todas menores a $5 USD, en verde y sin stablecoins), "
            "selecciona exactamente los 7 tickers con mejor estructura de acumulación silenciosa alcista "
            "(buena liquidez, sosteniéndose en la parte alta de su rango diario y absorbiendo compras antes de romper al alza). "
            "Devuelve ÚNICAMENTE los 7 tickers separados por coma (ejemplo: ARB,OP,SEI,TIA,IMX,PYTH,FET) "
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
                    for c in pool_ordenado:
                        if len(seleccion) >= 7:
                            break
                        if c not in seleccion:
                            seleccion.append(c)
                    print(f"🧠 Gemini IA seleccionó altcoins económicas en acumulación: {[x['base_asset'] for x in seleccion[:7]]}")
                    return seleccion[:7]
            except Exception:
                continue
    except Exception as e:
        print(f"⚠️ Fallback cuantitativo en silenciosas (error Gemini): {e}")

    return pool_ordenado[:7]

def preparar_datos(tickers, simbolos_activos):
    usdt_pairs_todos = {}
    usdt_pairs_spot_web = []

    # Bloqueo estricto de stablecoins, pares fiat, oro tokenizado y tokens deslistados/anómalos
    EXCLUIDOS = {
        'USDT', 'USDC', 'FDUSD', 'DAI', 'TUSD', 'USDP', 'EUR', 'BUSD',
        'AEUR', 'EURI', 'USD1', 'USDE', 'RLUSD', 'RWUSD', 'XUSD', 'BFUSD',
        'PAXG', 'XAUT', 'U', 'USDG', 'USDS', 'PYUSD', 'GUSD', 'SUSD', 'FRAX',
        'CREAM', 'EPX', 'FOR', 'VGX', 'WNXM', 'BOND', 'LOOM', 'OAX',
        'MULTI', 'KP3R', 'AKRO', 'BLZ', 'WRX', 'SNXXB', 'MSTRB', 'GBP', 'TRY', 'BRL', 'ARS'
    }

    for t in tickers:
        symbol = t.get('symbol', '')
        if not symbol.endswith('USDT'):
            continue
        base_name = symbol[:-4]

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
                pos_rango = ((last_p - low_p) / rango_precio) if rango_precio > 0 else 0.5

                t['base_asset'] = base_name
                t['openPrice_f'] = open_p
                t['lastPrice_f'] = last_p
                t['priceChangePercent_f'] = pct_real
                t['pct_api_f'] = pct_api
                t['quoteVolume_f'] = vol_q
                t['highPrice_f'] = high_p
                t['lowPrice_f'] = low_p
                t['pct_rango'] = pct_rango
                t['pos_rango'] = pos_rango

                usdt_pairs_todos[symbol] = t

                if base_name not in EXCLUIDOS and vol_q >= 100_000:
                    usdt_pairs_spot_web.append(t)
            except (ValueError, TypeError):
                continue

    # 1. TOP 7 GANADORAS
    ganadoras = sorted(
        [t for t in usdt_pairs_spot_web if t['priceChangePercent_f'] > 0],
        key=lambda x: x['pct_api_f'],
        reverse=True
    )[:7]

    # 2. TOP 7 PERDEDORAS
    perdedoras = sorted(
        [t for t in usdt_pairs_spot_web if t['priceChangePercent_f'] < 0],
        key=lambda x: x['pct_api_f']
    )[:7]

    # 3. TOP 7 ACUMULACIÓN 24H (Mayor volumen Spot global)
    acumulacion_24h = sorted(
        usdt_pairs_spot_web,
        key=lambda x: x['quoteVolume_f'],
        reverse=True
    )[:7]

    # 4. TOP 7 ACUMULACIÓN SILENCIOSA (IA) — Solo altcoins < $5 USD, en positivo y sin stablecoins
    historial_previo = cargar_memoria_perlas()
    candidatas_silenciosas = []
    for t in usdt_pairs_spot_web:
        precio = t['lastPrice_f']
        var = t['priceChangePercent_f']
        vol = t['quoteVolume_f']
        rango = t['pct_rango']
        pos = t['pos_rango']

        # Filtro estricto:
        # - Precio accesible (< $5 USD, descarta BTC, ETH, SOL, BNB, etc.)
        # - En verde controlado (+0.40% a +7.50%, nunca cayendo ni estable en 0.00%)
        # - Movimiento real (rango > 1.2% para descartar monedas pegadas a $1)
        # - Sosteniéndose en la mitad superior del rango diario (pos >= 0.50)
        # - Liquidez saludable (>= 1.5M USDT)
        if (precio < PRECIO_MAX_SILENCIOSA and
            0.40 <= var <= 7.50 and
            rango >= 1.20 and
            pos >= 0.50 and
            vol >= 1_500_000):

            # Presión relativa normalizada (evita que un solo gigante acapare todo)
            vol_millones = min(vol / 1_000_000, 60.0)
            factor_acum = round(vol_millones / max(rango, 1.0), 2)
            t['factor_vol'] = max(1.3, round(1.2 + (factor_acum * 0.25), 1))
            candidatas_silenciosas.append(t)

    # Respaldo si el mercado está muy rojo y hay pocas en verde: amplia ligeramente el rango positivo
    if len(candidatas_silenciosas) < 7:
        for t in usdt_pairs_spot_web:
            if (t not in candidatas_silenciosas and
                t['lastPrice_f'] < PRECIO_MAX_SILENCIOSA and
                0.15 <= t['priceChangePercent_f'] <= 9.0 and
                t['pct_rango'] >= 1.0 and
                t['quoteVolume_f'] >= 1_000_000):
                vol_millones = min(t['quoteVolume_f'] / 1_000_000, 60.0)
                t['factor_vol'] = max(1.2, round(1.1 + ((vol_millones / max(t['pct_rango'], 1.0)) * 0.25), 1))
                candidatas_silenciosas.append(t)

    acumulacion_silenciosa = seleccionar_silenciosas_con_gemini(candidatas_silenciosas, historial_previo)
    guardar_memoria_perlas(historial_previo + [[t['symbol'] for t in acumulacion_silenciosa]])

    # 5. TUS 5 FAVORITAS
    favoritas_simbolos = ['QI', 'TUT', 'NEIRO', 'LUNC', 'BANK']
    favoritas = [usdt_pairs_todos[f"{sim}USDT"] for sim in favoritas_simbolos if f"{sim}USDT" in usdt_pairs_
