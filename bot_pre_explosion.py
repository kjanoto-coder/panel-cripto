import os
import re
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

EXCL_BASE = {
    'USDT', 'USDC', 'FDUSD', 'DAI', 'TUSD', 'USDP', 'EUR', 'GBP', 'AUD', 'BRL', 'ARS', 'TRY', 'BUSD',
    'USD1', 'AEUR', 'EURI', 'USDE', 'RLUSD', 'RWUSD', 'XUSD', 'BFUSD', 'U', 'USDG', 'USDS', 'PYUSD',
    'BTC', 'ETH', 'SOL', 'ADA', 'XRP', 'DOGE', 'TRX', 'SHIB', 'AVAX', 'LINK', 'BNB', 'DOT', 'NEAR', 'SUI', 'PEPE'
}

def ahora_art():
    return datetime.now(TZ_ART)

def cargar_historial():
    hoy = ahora_art().strftime('%Y-%m-%d')
    ayer = (ahora_art() - timedelta(days=1)).strftime('%Y-%m-%d')
    base = {
        "fecha": hoy,
        "mencionadas": {},
        "resumen_dia": [],
        "resumen_enviado_hoy": False,
        "posta": {},
        "graduadas_pre_explosion": {},
        "verdes_hoy": [],
        "verdes_ayer": [],
        "oro_hoy": []
    }
    if os.path.exists(HISTORIAL_FILE):
        try:
            with open(HISTORIAL_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)

            base["posta"] = data.get("posta", {}) if isinstance(data.get("posta"), dict) else {}

            grad_limpia = {}
            for sym, info in (data.get("graduadas_pre_explosion") or {}).items():
                base_sym = sym[:-4] if sym.endswith("USDT") else sym
                if base_sym in EXCL_BASE:
                    continue
                try:
                    f_det = datetime.strptime(info.get("fecha_iso", hoy), '%Y-%m-%d').date()
                    if (ahora_art().date() - f_det).days <= DIAS_GRADUADAS:
                        grad_limpia[sym] = info
                except Exception:
                    continue
            base["graduadas_pre_explosion"] = grad_limpia

            fecha_guardada = data.get("fecha")
            if fecha_guardada == hoy:
                base["mencionadas"] = data.get("mencionadas", {})
                base["resumen_dia"] = data.get("resumen_dia", [])
                base["resumen_enviado_hoy"] = data.get("resumen_enviado_hoy", False)
                base["verdes_hoy"] = data.get("verdes_hoy", [])
                base["verdes_ayer"] = data.get("verdes_ayer", [])
                base["oro_hoy"] = data.get("oro_hoy", [])
            elif fecha_guardada == ayer:
                base["verdes_ayer"] = data.get("verdes_hoy", [])
                base["verdes_hoy"] = []
                base["oro_hoy"] = []
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

def analizar_order_book_blindaje(session, symbol):
    """Audita el libro de órdenes real (20 niveles) para detectar muros vendedores o vacío de liquidez."""
    urls = [
        f"https://api.binance.com/api/v3/depth?symbol={symbol}&limit=20",
        f"https://data-api.binance.vision/api/v3/depth?symbol={symbol}&limit=20"
    ]
    for u in urls:
        try:
            r = session.get(u, timeout=5)
            if r.status_code == 200:
                d = r.json()
                bids = d.get("bids", [])
                asks = d.get("asks", [])
                if not bids or not asks:
                    continue
                best_bid = float(bids[0][0])
                best_ask = float(asks[0][0])
                spread_pct = ((best_ask - best_bid) / best_bid) * 100 if best_bid > 0 else 99.0
                vol_bids = sum(float(b[0]) * float(b[1]) for b in bids)
                vol_asks = sum(float(a[0]) * float(a[1]) for a in asks)
                ratio_ba = round(vol_bids / vol_asks, 2) if vol_asks > 0 else 1.0
                libro_sano = (spread_pct <= 0.45 and ratio_ba >= 0.75)
                return {
                    "ok": True,
                    "spread_pct": round(spread_pct, 3),
                    "ratio_bids_asks": ratio_ba,
                    "libro_sano": libro_sano
                }
        except Exception:
            continue
    return {"ok": False, "spread_pct": 0.1, "ratio_bids_asks": 1.0, "libro_sano": True}

def obtener_metricas_velas(session, symbol):
    """Obtiene cambio 1h, cambio 4h, volumen relativo 1h y niveles geométricos Fibonacci 4H."""
    cambio_1h = 0.0
    cambio_4h = 0.0
    vol_1h_rel = 1.0
    fib_info = {"ok": False}

    urls_1h = [
        f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval=1h&limit=25",
        f"https://data-api.binance.vision/api/v3/klines?symbol={symbol}&interval=1h&limit=25"
    ]
    for u in urls_1h:
        try:
            res = session.get(u, timeout=6)
            if res.status_code == 200:
                candles = res.json()
                if len(candles) >= 2:
                    open_p = float(candles[-1][1])
                    close_p = float(candles[-1][4])
                    if open_p > 0:
                        cambio_1h = round(((close_p - open_p) / open_p) * 100, 2)
                    vol_actual = float(candles[-1][7])
                    prev_vols = [float(c[7]) for c in candles[:-1] if float(c[7]) > 0]
                    if prev_vols:
                        prom_vol = sum(prev_vols) / len(prev_vols)
                        if prom_vol > 0:
                            vol_1h_rel = round(vol_actual / prom_vol, 2)
                break
        except Exception:
            continue

    urls_4h = [
        f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval=4h&limit=36",
        f"https://data-api.binance.vision/api/v3/klines?symbol={symbol}&interval=4h&limit=36"
    ]
    for u in urls_4h:
        try:
            res = session.get(u, timeout=6)
            if res.status_code == 200:
                candles = res.json()
                if len(candles) >= 1:
                    open_p = float(candles[-1][1])
                    close_p = float(candles[-1][4])
                    if open_p > 0:
                        cambio_4h = round(((close_p - open_p) / open_p) * 100, 2)

                if len(candles) >= 12:
                    highs = [float(c[2]) for c in candles]
                    lows = [float(c[3]) for c in candles]
                    swing_high = max(highs)
                    swing_low = min(lows)
                    rango = swing_high - swing_low
                    p_act = float(candles[-1][4])
                    if rango > 0:
                        ratio = round((swing_high - p_act) / rango, 2)
                        fib_618 = swing_high - (rango * 0.618)
                        ext_1272 = swing_low + (rango * 1.272)
                        ext_1618 = swing_low + (rango * 1.618)

                        en_pullback_sano = (0.35 <= ratio <= 0.65)
                        extendida_fib = (p_act >= ext_1272 or ratio < 0.08)

                        if en_pullback_sano:
                            etiqueta_fib = f"Pullback Sano Fib ({ratio:.2f})"
                        elif extendida_fib:
                            etiqueta_fib = f"Extendida Fib ({ratio:.2f})"
                        elif ratio > 0.65:
                            etiqueta_fib = f"Piso Profundo Fib ({ratio:.2f})"
                        else:
                            etiqueta_fib = f"Tramo Alcista Fib ({ratio:.2f})"

                        fib_info = {
                            "ok": True,
                            "ratio": ratio,
                            "etiqueta_fib": etiqueta_fib,
                            "en_pullback_sano": en_pullback_sano,
                            "extendida_fib": extendida_fib,
                            "fib_618": fib_618,
                            "ext_1618": ext_1618
                        }
                break
        except Exception:
            continue

    return cambio_1h, cambio_4h, vol_1h_rel, fib_info

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

def es_simbolo_valido(base):
    if not base or base in EXCL_BASE:
        return False
    if not re.match(r'^[A-Z0-9]+$', base):
        return False
    if any(x in base for x in ['UP', 'DOWN', 'BULL', 'BEAR']):
        return False
    return True

def construir_item_desde_ticker(session, t, desde_posta=False, info_grad=None, info_posta=None):
    symbol = t.get('symbol', '')
    base = symbol[:-4] if symbol.endswith('USDT') else symbol
    precio = float(t.get('lastPrice', 0))
    cambio_24h = float(t.get('priceChangePercent', 0))
    vol_usdt = float(t.get('quoteVolume', 0))
    high = float(t.get('highPrice', 0))
    low = float(t.get('lowPrice', 0))

    if precio <= 0:
        return None

    cambio_1h, cambio_4h, vol_1h_rel, fib_info = obtener_metricas_velas(session, symbol)
    pos_liquidez_pct = round(((precio - low) / (high - low)) * 100, 1) if high > low else 50.0
    rango = high - low
    pct_rango = (rango / precio) * 100 if precio > 0 else 1.0
    factor_spike = (vol_usdt / 1_000_000) / (pct_rango if pct_rango > 0 else 1.0)

    bono_fib = 0.0
    if fib_info.get("ok"):
        if fib_info.get("en_pullback_sano"):
            bono_fib = 8.5
        elif fib_info.get("extendida_fib"):
            bono_fib = -10.0

    penalizacion_extension = 14.0 if (pos_liquidez_pct > 90.0 or cambio_24h > 7.5) else 0.0
    bonus_posta = 18.0 if desde_posta else 0.0
    score_ia = round(
        (cambio_1h * 3.2) + (cambio_4h * 2.0) + (cambio_24h * 1.1) + (factor_spike * 1.5) + (vol_1h_rel * 1.8) + bonus_posta + bono_fib - penalizacion_extension,
        2
    )

    score_oro = round(
        (vol_1h_rel * 2.5) + (factor_spike * 1.5) + (cambio_1h * 2.0) - abs(3.0 - cambio_24h) + (pos_liquidez_pct / 30.0) + (bono_fib * 0.6),
        2
    )

    var_desde_grad = None
    fecha_grad = ""
    if desde_posta and info_grad:
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
        'vol_1h_rel': vol_1h_rel,
        'vol_f': vol_usdt,
        'high_f': high,
        'low_f': low,
        'pos_liquidez_pct': pos_liquidez_pct,
        'fib_info': fib_info,
        'score_ia': score_ia,
        'score_oro': score_oro,
        'es_oro': False,
        'desde_posta': bool(desde_posta),
        'en_cazador_tactico': bool(info_posta),
        'etapa_tactica': int(info_posta.get("etapa", 0)) if info_posta else 0,
        'var_desde_grad': var_desde_grad,
        'fecha_grad': fecha_grad,
        'certificada_ia': False,
        'blindaje_pct': 0,
        'motivo_certificacion': ""
    }

def certificar_confluencia_ia(session, seleccion_total, historial):
    """
    GESTOR CERTIFICADOR IA:
    Cruza Cazador Táctico + Pre-Explosión + Fibonacci + Order Book Depth y certifica con Gemini
    qué monedas están blindadas y aptas para pasar a la cartera semanal.
    """
    if not seleccion_total:
        return

    grad = historial.get("graduadas_pre_explosion", {})
    hoy_str = ahora_art().strftime('%Y-%m-%d')
    fecha_corta = ahora_art().strftime('%d/%m %H:%M')

    resumen_para_ia = []
    for item in seleccion_total:
        sym = item["symbol"]
        ob = analizar_order_book_blindaje(session, sym)
        fib = item.get("fib_info", {})

        # Cálculo determinístico base de blindaje (0 a 100)
        puntos = 50
        coincide_etapas = item.get("desde_posta") or item.get("en_cazador_tactico")
        if coincide_etapas:
            puntos += 18  # Coincidencia confirmada entre Cazador Táctico y Pre-Explosión
        if fib.get("en_pullback_sano"):
            puntos += 12
        elif fib.get("extendida_fib"):
            puntos -= 15
        if ob.get("libro_sano"):
            puntos += 10
        else:
            puntos -= 14
        if item["vol_1h_rel"] >= 1.1:
            puntos += 8
        if -1.5 <= item["cambio_f"] <= 7.0:
            puntos += 7

        blindaje_pct = max(25, min(98, puntos))
        certificada = (blindaje_pct >= 72 and ob.get("libro_sano", True) and not fib.get("extendida_fib", False))

        razones = []
        if coincide_etapas:
            razones.append("Coincide Cazador+PreExplosión")
        if fib.get("ok"):
            razones.append(fib.get("etiqueta_fib", ""))
        razones.append(f"Libro Bids/Asks: {ob['ratio_bids_asks']}x (Spread {ob['spread_pct']}%)")

        item["blindaje_pct"] = blindaje_pct
        item["certificada_ia"] = certificada
        item["motivo_certificacion"] = " | ".join(razones)

        resumen_para_ia.append({
            "moneda": item["ticker"],
            "categoria": item["categoria"],
            "coincide_cazador_y_preexplosion": coincide_etapas,
            "cambio_1h": item["cambio_1h"],
            "cambio_24h": item["cambio_f"],
            "vol_1h_rel": item["vol_1h_rel"],
            "fibonacci": fib.get("etiqueta_fib", "N/D"),
            "order_book_ratio": ob["ratio_bids_asks"],
            "spread_pct": ob["spread_pct"],
            "blindaje_base": blindaje_pct
        })

    # Segunda opinión IA con Gemini para refinar la certificación
    if GEMINI_API_KEY and resumen_para_ia:
        try:
            client = genai.Client(api_key=GEMINI_API_KEY)
            prompt = (
                "Eres el Gestor Certificador IA de un sistema cuantitativo en Binance Spot.\n"
                "Revisa las siguientes candidatas que pasaron por Cazador Táctico y Pre-Explosión. "
                "Certifica SOLO las que tengan coincidencia real de impulso sano, buen libro de órdenes (Bids >= Asks, spread bajo) y no estén extendidas en FOMO.\n"
                f"CANDIDATAS:\n{json.dumps(resumen_para_ia, ensure_ascii=False)}\n\n"
                "Responde ÚNICAMENTE en JSON válido:\n"
                '{"MONEDA":{"certificada":true,"blindaje_pct":85,"nota":"motivo técnico corto de 1 línea"}}'
            )
            for mod in ["gemini-2.5-flash", "gemini-1.5-flash"]:
                try:
                    res = client.models.generate_content(model=mod, contents=prompt)
                    if res and res.text:
                        raw = res.text.strip()
                        if "{" in raw and "}" in raw:
                            raw = raw[raw.find("{"):raw.rfind("}") + 1]
                        veredictos = json.loads(raw)
                        for item in seleccion_total:
                            v_mon = veredictos.get(item["ticker"])
                            if isinstance(v_mon, dict):
                                item["certificada_ia"] = bool(v_mon.get("certificada", item["certificada_ia"]))
                                item["blindaje_pct"] = int(v_mon.get("blindaje_pct", item["blindaje_pct"]))
                                if v_mon.get("nota"):
                                    item["motivo_certificacion"] = str(v_mon["nota"])[:130]
                        break
                except Exception:
                    continue
        except Exception as e:
            print(f"⚠️ Fallback Certificador IA: {e}")

    # Grabar el sello de certificación en historial_perlas.json para que el Gestor Semanal lo lea
    for item in seleccion_total:
        sym = item["symbol"]
        if item["certificada_ia"] or sym in grad:
            prev = grad.get(sym, {})
            grad[sym] = {
                "symbol": sym,
                "base": item["ticker"],
                "estrellas": 3 if item["categoria"] == "ROJO" else 2,
                "probabilidad_pct": item["blindaje_pct"],
                "precio_ref": float(prev.get("precio_ref") or item["precio_f"]),
                "fecha_iso": prev.get("fecha_iso", hoy_str),
                "fecha_corta": prev.get("fecha_corta", fecha_corta),
                "certificada_ia": bool(item["certificada_ia"]),
                "blindaje_pct": int(item["blindaje_pct"]),
                "motivo_certificacion": item["motivo_certificacion"]
            }

    historial["graduadas_pre_explosion"] = grad

def motor_ia_seleccion_tactica(tickers, simbolos_activos, session, historial):
    hoy_str = ahora_art().strftime('%Y-%m-%d')
    ayer_str = (ahora_art() - timedelta(days=1)).strftime('%Y-%m-%d')

    if historial.get("fecha") != hoy_str:
        if historial.get("fecha") == ayer_str:
            historial["verdes_ayer"] = historial.get("verdes_hoy", [])
        else:
            historial["verdes_ayer"] = []
        historial["verdes_hoy"] = []
        historial["oro_hoy"] = []
        historial["fecha"] = hoy_str
        historial["mencionadas"] = {}
        historial["resumen_dia"] = []
        historial["resumen_enviado_hoy"] = False

    mencionadas = historial.get("mencionadas", {})
    for sym in list(mencionadas.keys()):
        mencionadas[sym] -= 1
        if mencionadas[sym] <= 0:
            del mencionadas[sym]

    verdes_ayer = set(historial.get("verdes_ayer", []))
    verdes_hoy = set(historial.get("verdes_hoy", []))
    oro_hoy = set(historial.get("oro_hoy", []))

    grad = historial.get("graduadas_pre_explosion", {})
    posta = historial.get("posta", {})

    syms_rojo_tactico = set()
    for sym in list(grad.keys()):
        base = sym[:-4] if sym.endswith("USDT") else sym
        if es_simbolo_valido(base):
            syms_rojo_tactico.add(sym)

    for sym, d in posta.items():
        base = sym[:-4] if sym.endswith("USDT") else sym
        if es_simbolo_valido(base) and int(d.get("etapa", d.get("paso", 1))) == 3:
            syms_rojo_tactico.add(sym)
            if sym not in grad:
                grad[sym] = {
                    "symbol": sym,
                    "base": base,
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
            if es_simbolo_valido(base):
                mapa_tickers[sym] = t

    total_analizadas = 0
    items_posta_roja = []
    candidatas_mercado = []

    for sym in list(syms_rojo_tactico):
        t = mapa_tickers.get(sym)
        if not t:
            continue
        try:
            precio = float(t.get('lastPrice', 0))
            vol_usdt = float(t.get('quoteVolume', 0))
            if precio > 0 and vol_usdt >= 250_000:
                total_analizadas += 1
                it = construir_item_desde_ticker(session, t, desde_posta=True, info_grad=grad.get(sym), info_posta=posta.get(sym))
                if it:
                    items_posta_roja.append(it)
        except (ValueError, TypeError):
            continue

    items_posta_roja.sort(key=lambda x: x['score_ia'], reverse=True)
    vistos = {x['symbol'] for x in items_posta_roja}

    for sym, t in mapa_tickers.items():
        if sym in vistos or sym in mencionadas:
            continue
        try:
            precio = float(t.get('lastPrice', 0))
            cambio_24h = float(t.get('priceChangePercent', 0))
            vol_usdt = float(t.get('quoteVolume', 0))
            if 0.000001 <= precio < 15.0 and vol_usdt >= 1_000_000 and -2.0 <= cambio_24h <= 9.0:
                total_analizadas += 1
                it = construir_item_desde_ticker(session, t, desde_posta=False, info_grad=None, info_posta=posta.get(sym))
                if it and (it['cambio_1h'] >= -0.2 or it['cambio_4h'] >= 0.3):
                    candidatas_mercado.append(it)
        except (ValueError, TypeError):
            continue

    candidatas_mercado.sort(key=lambda x: x['score_ia'], reverse=True)
    candidatas_impulso = [x for x in candidatas_mercado if x['cambio_f'] <= 6.5]
    seleccion_impulso = items_posta_roja[:8]
    cupo_impulso = max(0, 8 - len(seleccion_impulso))
    if cupo_impulso > 0:
        seleccion_impulso.extend(candidatas_impulso[:cupo_impulso])

    top_rojas = seleccion_impulso[:4]
    top_amarillas = seleccion_impulso[4:8]
    usadas_arriba = {x['symbol'] for x in (top_rojas + top_amarillas)}

    candidatas_oro = []
    candidatas_piso_respaldo = []

    for it in candidatas_mercado:
        sym = it['symbol']
        if sym in usadas_arriba:
            continue

        var_24h = it['cambio_f']
        rango = it['pos_liquidez_pct']
        fresca = (sym not in verdes_ayer)

        if (1.8 <= var_24h <= 4.5) and (15.0 <= rango <= 30.0) and fresca and it['cambio_1h'] >= 0.0 and it['vol_1h_rel'] >= 1.1:
            it['es_oro'] = True
            candidatas_oro.append(it)
        elif (-1.5 <= var_24h <= 4.5) and (rango <= 35.0) and fresca:
            candidatas_piso_respaldo.append(it)

    candidatas_oro.sort(key=lambda x: x['score_oro'], reverse=True)
    candidatas_piso_respaldo.sort(key=lambda x: x['score_oro'], reverse=True)

    top_verdes = candidatas_oro[:3]
    syms_oro = {x['symbol'] for x in top_verdes}
    for it in candidatas_piso_respaldo:
        if len(top_verdes) >= 5:
            break
        if it['symbol'] not in syms_oro:
            top_verdes.append(it)

    for item in top_rojas:
        item['categoria'], item['estado_texto'], item['color_hex'] = "ROJO", "Explosión Inminente", "#ff1744"
    for item in top_amarillas:
        item['categoria'], item['estado_texto'], item['color_hex'] = "AMARILLO", "Confirmación Táctica", "#ffd600"
    for item in top_verdes:
        if item.get('es_oro'):
            item['categoria'], item['estado_texto'], item['color_hex'] = "VERDE", "🏆 COMPRA AQUÍ (ORO)", "#ffd700"
            oro_hoy.add(item['symbol'])
        else:
            item['categoria'], item['estado_texto'], item['color_hex'] = "VERDE", "Vigilancia / Acumulación", "#00e676"
        verdes_hoy.add(item['symbol'])

    seleccion_total = top_rojas + top_amarillas + top_verdes

    # Ejecutar Gestor Certificador IA sobre las finalistas
    certificar_confluencia_ia(session, seleccion_total, historial)

    for item in seleccion_total:
        sym = item['symbol']
        mencionadas[sym] = 3
        if sym not in historial["resumen_dia"]:
            historial["resumen_dia"].append(sym)

    historial["mencionadas"] = mencionadas
    historial["verdes_hoy"] = list(verdes_hoy)
    historial["oro_hoy"] = list(oro_hoy)
    guardar_historial(historial)

    return {"ROJO": top_rojas, "AMARILLO": top_amarillas, "VERDE": top_verdes}, total_analizadas, historial

def generar_grafico_color(lista_items, titulo_graf, subtitulo_graf, filename):
    if not lista_items:
        return None
    simbolos = [
        f"{'🛡️' if item.get('certificada_ia') else ('🏆' if item.get('es_oro') else '')}{item['ticker']}"
        for item in lista_items
    ]
    posiciones = [item['pos_liquidez_pct'] for item in lista_items]
    colores = [item['color_hex'] for item in lista_items]

    fig, ax = plt.subplots(figsize=(8.5, 4.2), facecolor='#0b132b')
    ax.set_facecolor('#0b132b')

    bars = ax.bar(simbolos, posiciones, color=colores, width=0.48, zorder=3)
    ax.grid(True, color='#1e293b', linestyle='-', linewidth=0.8, zorder=1)
    ax.set_axisbelow(True)

    ax.set_ylim(0, 118)
    for spine in ['top', 'right', 'left', 'bottom']:
        ax.spines[spine].set_visible(False)

    ax.tick_params(left=False, labelleft=False, bottom=False)
    ax.tick_params(axis='x', colors='white', labelsize=9)

    for bar, item, pos, color in zip(bars, lista_items, posiciones, colores):
        yval = bar.get_height()
        xval = bar.get_x() + bar.get_width() / 2.0
        sim = item['ticker']
        if item.get('certificada_ia') or item.get('es_oro'):
            bar.set_edgecolor('#00e676' if item.get('certificada_ia') else '#ffd700')
            bar.set_linewidth(2.2)

        ax.text(xval, yval + 2.5, f"{pos:.0f}%", ha='center', va='bottom', color=color, fontweight='bold', fontsize=8.5)
        ax.plot(xval, max(yval / 2.0, 13), marker='o', markersize=15, markerfacecolor='#0f172a', markeredgecolor=color, markeredgewidth=1.8, zorder=4)
        ax.text(xval, max(yval / 2.0, 13), sim[:5], ha='center', va='center', color='white', fontsize=6.5, fontweight='bold', zorder=5)

    plt.title(titulo_graf, loc='left', color='#ffab00', fontsize=10.5, fontweight='bold', pad=12)
    ax.text(0.0, 1.02, subtitulo_graf, transform=ax.transAxes, color='#94a3b8', fontsize=8)

    plt.tight_layout()
    plt.savefig(filename, dpi=300, facecolor=fig.get_facecolor(), edgecolor='none')
    plt.close()
    return filename

def generar_dictamen_color(cat_key, lista_items):
    if not lista_items:
        return ""
    if not GEMINI_API_KEY:
        return f"Lectura {cat_key}: foco en confluencia Cazador+PreExplosión, libro de órdenes y Fibonacci."

    client = genai.Client(api_key=GEMINI_API_KEY)
    lista_texto = "\n".join([
        f"- {i['ticker']} ({'CERTIFICADA_IA ' + str(i['blindaje_pct']) + '%' if i.get('certificada_ia') else 'OBSERVACIÓN'}): "
        f"1h {i['cambio_1h']:+.2f}%, 24h {i['cambio_f']:+.2f}%, Vol1H {i['vol_1h_rel']:.1f}x, {i.get('motivo_certificacion', '')}"
        for i in lista_items
    ])
    prompt = (
        f"Analista Spot Binance. Dá un dictamen breve (máximo 2 líneas) para el bloque {cat_key} de Pre-Explosión "
        f"destacando las monedas que recibieron el sello CERTIFICADA_IA para cartera semanal:\n{lista_texto}"
    )
    for mod in ['gemini-2.5-flash', 'gemini-1.5-flash']:
        try:
            response = client.models.generate_content(model=mod, contents=prompt)
            if response and response.text:
                return response.text.strip()
        except Exception:
            continue
    return f"Lectura {cat_key}: foco en confluencia Cazador+PreExplosión, libro de órdenes y Fibonacci."

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
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": texto.strip(), "parse_mode": "HTML", "disable_web_page_preview": True}
    if tid:
        payload["message_thread_id"] = tid
    try:
        res = requests.post(url, json=payload, timeout=30).json()
        if not res.get("ok") and "thread not found" in str(res.get("description", "")).lower():
            payload.pop("message_thread_id", None)
            requests.post(url, json=payload, timeout=30)
    except Exception as e:
        print(f"⚠️ Error enviando texto: {e}")

def enviar_mensaje_por_color(num_msg, cat_key, titulo_color, items, total_analizadas):
    fecha_str = ahora_art().strftime('%Y-%m-%d %H:%M ART')
    if not items:
        enviar_texto_telegram(
            f"🔥 <b>PRE-EXPLOSIÓN ({num_msg}/3)</b>\n{titulo_color}\n📅 <code>{fecha_str}</code>\n\n"
            f"⏳ <i>Sin monedas en este bloque en este ciclo.</i>"
        )
        return

    fname = f"pre_explosion_{cat_key.lower()}.png"
    generar_grafico_color(
        items,
        f"PRE-EXPLOSION ({num_msg}/3) - {cat_key}",
        f"Fecha: {fecha_str} | Analizadas: {total_analizadas} Spot | 🛡️ = Certificada IA | 🏆 = Oro",
        fname
    )
    dictamen = generar_dictamen_color(cat_key, items)

    caption = (
        f"🔥 <b>PRE-EXPLOSIÓN ({num_msg}/3)</b>\n"
        f"{titulo_color}\n"
        f"📅 <code>{fecha_str}</code>"
    )
    enviar_telegram_foto(fname, caption)
    time.sleep(1)

    cuerpo = f"💡 <i>{html.escape(dictamen)}</i>\n\n"
    for item in items:
        sim = item['ticker']
        precio_str = formatear_precio(item['precio_f'])
        unique_id = int(time.time() * 1000) + random.randint(1, 9999)
        url_ia = f"{BASE_URL_NETLIFY}/?coin={sim}&price={item['precio_f']}&change={item['cambio_f']}&high={item['high_f']}&low={item['low_f']}&v={sim}_{unique_id}"
        url_trade = f"https://www.binance.com/es/trade/{sim}_USDT"

        etiqueta_extra = ""
        if item.get("es_oro"):
            etiqueta_extra = f" 🏆 <b>[COMPRA AQUÍ • ORO | Rango: {item['pos_liquidez_pct']:.0f}% | Vol1H: {item['vol_1h_rel']:.1f}x]</b>"
        elif item.get("desde_posta"):
            if item.get("var_desde_grad") is not None:
                etiqueta_extra = f" ⭐⭐⭐ [Posta {item.get('fecha_grad')}: <b>{item['var_desde_grad']:+.2f}%</b>]"
            else:
                etiqueta_extra = " ⭐⭐⭐ [Posta Roja]"

        sello_cert = (
            f"🛡️ <b>CERTIFICADA IA ({item['blindaje_pct']}%)</b>"
            if item.get("certificada_ia")
            else f"⏳ <i>En observación IA ({item['blindaje_pct']}%)</i>"
        )
        motivo_c = html.escape(item.get("motivo_certificacion", ""))

        fib = item.get("fib_info", {})
        linea_fib = ""
        if fib.get("ok"):
            linea_fib = f"  • <i>{html.escape(fib['etiqueta_fib'])}</i> | Ext 1.618: <code>{formatear_precio(fib['ext_1618'])}</code>\n"

        cuerpo += (
            f"• <b>{sim}</b>{etiqueta_extra} (1h: {item['cambio_1h']:+.1f}% | 4h: {item['cambio_4h']:+.1f}% | 24h: {item['cambio_f']:+.1f}%) | <code>{precio_str}</code>\n"
            f"  • {sello_cert} — <i>{motivo_c}</i>\n"
            f"{linea_fib}"
            f"  └ <a href=\"{html.escape(url_ia)}\">📊 Resumen IA</a> | <a href=\"{html.escape(url_trade)}\">🔶 Tradear</a>\n\n"
        )

    enviar_texto_telegram(cuerpo)

if __name__ == "__main__":
    print(f"🔥 EJECUTANDO PRE-EXPLOSIÓN V8 + CERTIFICADOR IA ({ahora_art().strftime('%Y-%m-%d %H:%M:%S')} ART)...")
    session = crear_sesion_binance()
    simbolos_activos = obtener_simbolos_spot_activos(session)
    datos = obtener_datos_binance(session)

    if datos and simbolos_activos:
        historial = cargar_historial()
        bloques, total_analizadas, historial = motor_ia_seleccion_tactica(datos, simbolos_activos, session, historial)

        enviar_mensaje_por_color(1, "ROJO", "🔴 <b>1. EXPLOSIÓN INMINENTE (ROJO)</b>", bloques["ROJO"], total_analizadas)
        time.sleep(2)
        enviar_mensaje_por_color(2, "AMARILLO", "🟡 <b>2. CONFIRMACIÓN TÁCTICA (AMARILLO)</b>", bloques["AMARILLO"], total_analizadas)
        time.sleep(2)
        enviar_mensaje_por_color(3, "VERDE", "🟢 <b>3. COMPRA TEMPRANA • TOP ORO (VERDE)</b>", bloques["VERDE"], total_analizadas)

        hora_actual = ahora_art().hour
        if hora_actual >= 21 and not historial.get("resumen_enviado_hoy", False):
            monedas_dia = [s[:-4] if s.endswith('USDT') else s for s in historial.get("resumen_dia", [])]
            monedas_oro = [s[:-4] if s.endswith('USDT') else s for s in historial.get("oro_hoy", [])]
            if monedas_dia:
                resumen_texto = (
                    f"📋 <b>RESUMEN DIARIO PRE-EXPLOSIÓN (21:00 ART)</b>\n"
                    f"📅 <i>Fecha: {ahora_art().strftime('%Y-%m-%d')}</i>\n\n"
                    f"🏆 <b>Opciones de Oro detectadas hoy:</b>\n<code>{', '.join(monedas_oro) if monedas_oro else 'Ninguna en rango estricto'}</code>\n\n"
                    f"Todas las monedas del radar hoy:\n<code>{', '.join(monedas_dia)}</code>"
                )
                enviar_texto_telegram(resumen_texto)
                historial["resumen_enviado_hoy"] = True
                guardar_historial(historial)
    else:
        print("❌ ERROR: Sin datos o sin símbolos activos de Binance.")
