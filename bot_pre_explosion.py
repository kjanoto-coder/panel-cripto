import os
import re
import sys
import json
import time
import random
import html
import subprocess
from datetime import datetime, timezone, timedelta

# Auto-instalación blindada de dependencias
for mod, pkg in [
    ("requests", "requests"),
    ("matplotlib", "matplotlib"),
    ("openpyxl", "openpyxl"),
    ("google.genai", "google-genai")
]:
    try:
        __import__(mod)
    except ImportError:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", pkg])

import requests
import matplotlib.pyplot as plt
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from google import genai

# --- CONFIGURACIÓN DE ENTORNO BLINDADA ---
TZ_ART = timezone(timedelta(hours=-3))
TELEGRAM_BOT_TOKEN = (os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("TELEGRAM_TOKEN") or "").strip()
TELEGRAM_CHAT_ID = (os.getenv("TELEGRAM_CHAT_ID") or os.getenv("CHAT_ID") or "").strip()
TELEGRAM_TOPIC_ID = (
    os.getenv("TOPIC_ID_PRE_EXPLOSION")
    or os.getenv("TELEGRAM_MESSAGE_THREAD_ID")
    or os.getenv("TOPIC_ID_CENTRAL")
    or ""
).strip()
GEMINI_API_KEY = (os.getenv("GEMINI_API_KEY") or "").strip()
BASE_URL_NETLIFY = "https://gregarious-frangollo-0346c5.netlify.app"

HISTORIAL_FILE = "historial_perlas.json"
HISTORIAL_GANADORAS_FILE = "historial_ganadoras.json"
EXCEL_PRE_EXPLOSION_FILE = "AUDITORIA_PRE_EXPLOSION.xlsx"
DIAS_GRADUADAS = 7
DIAS_RETENCION_CALENDARIO = 90

MESES_ES = {
    1: "ENERO", 2: "FEBRERO", 3: "MARZO", 4: "ABRIL",
    5: "MAYO", 6: "JUNIO", 7: "JULIO", 8: "AGOSTO",
    9: "SEPTIEMBRE", 10: "OCTUBRE", 11: "NOVIEMBRE", 12: "DICIEMBRE"
}
DIAS_SEMANA_ES = {
    0: "LUNES", 1: "MARTES", 2: "MIERCOLES", 3: "JUEVES",
    4: "VIERNES", 5: "SABADO", 6: "DOMINGO"
}
PRIORIDAD_COLOR = {"VERDE": 1, "AMARILLO": 2, "ROJO": 3}

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
        "oro_hoy": [],
        "registro_cronologico": {},
        "apariciones_por_dia": {},
        "ultimo_envio_excel_pre": ""
    }
    if os.path.exists(HISTORIAL_FILE):
        try:
            with open(HISTORIAL_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)

            base["posta"] = data.get("posta", {}) if isinstance(data.get("posta"), dict) else {}
            base["registro_cronologico"] = data.get("registro_cronologico", {}) if isinstance(data.get("registro_cronologico"), dict) else {}
            base["ultimo_envio_excel_pre"] = data.get("ultimo_envio_excel_pre", "")

            por_dia_limpio = {}
            hoy_dt = ahora_art().date()
            for f_str, bucket in (data.get("apariciones_por_dia") or {}).items():
                try:
                    f_dt = datetime.strptime(f_str, '%Y-%m-%d').date()
                    if (hoy_dt - f_dt).days <= DIAS_RETENCION_CALENDARIO and isinstance(bucket, dict):
                        por_dia_limpio[f_str] = bucket
                except Exception:
                    continue
            base["apariciones_por_dia"] = por_dia_limpio

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
        'motivo_certificacion': "",
        'ratio_bids_asks': 1.0,
        'spread_pct': 0.1
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

        puntos = 50
        coincide_etapas = item.get("desde_posta") or item.get("en_cazador_tactico")
        if coincide_etapas:
            puntos += 18
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
        item["ratio_bids_asks"] = ob["ratio_bids_asks"]
        item["spread_pct"] = ob["spread_pct"]

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

    return {"ROJO": top_rojas, "AMARILLO": top_amarillas, "VERDE": top_verdes}, total_analizadas, historial, mapa_tickers

# ==============================================================================
# AUDITORÍA HISTÓRICA + CRUCE CON MONEDAS GANADORAS + EXCEL DIARIO
# ==============================================================================
def _normalizar_symbol(raw):
    s = str(raw or "").strip().upper()
    if not s:
        return ""
    if not s.endswith("USDT"):
        s = f"{s}USDT"
    return s

def _normalizar_ts(ts_raw, fallback_fecha):
    """Devuelve (fecha_iso, ts_iso, tiene_hora_real)."""
    txt = str(ts_raw or "").strip().replace("T", " ")
    m_full = re.search(r"(\d{4}-\d{2}-\d{2})[ T](\d{2}:\d{2})", txt)
    if m_full:
        hhmm = m_full.group(2)
        return m_full.group(1), f"{m_full.group(1)} {hhmm}", (hhmm != "00:00")
    m_date = re.search(r"(\d{4}-\d{2}-\d{2})", txt)
    if m_date:
        return m_date.group(1), f"{m_date.group(1)} 00:00", False
    m_short = re.search(r"(\d{2})/(\d{2})(?:[ T](\d{2}:\d{2}))?", txt)
    if m_short:
        anio = fallback_fecha[:4] if len(fallback_fecha) >= 4 else str(ahora_art().year)
        f_iso = f"{anio}-{m_short.group(2)}-{m_short.group(1)}"
        hhmm = m_short.group(3)
        if hhmm:
            return f_iso, f"{f_iso} {hhmm}", (hhmm != "00:00")
        return f_iso, f"{f_iso} 00:00", False
    f_base = fallback_fecha[:10] if len(fallback_fecha) >= 10 else ahora_art().strftime("%Y-%m-%d")
    return f_base, f"{f_base} 00:00", False

def _formatear_demora(horas_totales, mismo_dia_sin_hora=False):
    if mismo_dia_sin_hora:
        return "Mismo día"
    if horas_totales is None or horas_totales < 0:
        return "-"
    dias = int(horas_totales // 24)
    horas = int(round(horas_totales % 24))
    if horas == 24:
        dias += 1
        horas = 0
    if dias > 0:
        return f"{dias}d {horas:02d}h"
    return f"{horas}h"

def _calcular_velocidad_escalada(rec):
    """Mide el tiempo de aceleración entre colores del semáforo."""
    def _parse(ts_s):
        if not ts_s or ts_s.endswith("00:00"):
            return None
        try:
            return datetime.strptime(ts_s[:16], "%Y-%m-%d %H:%M")
        except Exception:
            return None

    dt_v = _parse(rec.get("ts_verde", ""))
    dt_a = _parse(rec.get("ts_amarillo", ""))
    dt_r = _parse(rec.get("ts_rojo", ""))

    if dt_v and dt_r and dt_r > dt_v:
        h = (dt_r - dt_v).total_seconds() / 3600.0
        return f"🟢➔🔴 {_formatear_demora(h)}"
    if dt_v and dt_a and dt_a > dt_v:
        h = (dt_a - dt_v).total_seconds() / 3600.0
        return f"🟢➔🟡 {_formatear_demora(h)}"
    if dt_a and dt_r and dt_r > dt_a:
        h = (dt_r - dt_a).total_seconds() / 3600.0
        return f"🟡➔🔴 {_formatear_demora(h)}"
    if rec.get("color_inicial") == "ROJO":
        return "Directo 🔴"
    return "-"

def _etiqueta_semaforo(rec_o_item):
    col = str(rec_o_item.get("color_inicial") or rec_o_item.get("color") or "VERDE").upper()
    if col == "VERDE" and rec_o_item.get("es_oro"):
        return "🏆 TOP ORO"
    return {"VERDE": "🟢 VERDE", "AMARILLO": "🟡 AMARILLO", "ROJO": "🔴 ROJO"}.get(col, col)

def _insertar_evento_historico(registro, por_dia, evento):
    sym = _normalizar_symbol(evento.get("symbol") or evento.get("ticker"))
    if not sym:
        return
    ticker = sym[:-4]
    if not es_simbolo_valido(ticker):
        return

    color = str(evento.get("color") or "VERDE").upper()
    if color not in PRIORIDAD_COLOR:
        color = "VERDE"
    es_oro = bool(evento.get("es_oro", False))
    coincide_caz = bool(evento.get("coincide_cazador", False))
    precio = float(evento.get("precio") or 0.0)
    ia_pct = int(float(evento.get("ia_pct") or 0))
    fib_zona = float(evento.get("fib_zona") or 0.0)
    fib_etiqueta = str(evento.get("fib_etiqueta") or "")
    ext_1618 = float(evento.get("ext_1618") or 0.0)
    bids_asks = float(evento.get("bids_asks") or 0.0)
    fecha_det, ts_det, tiene_hora = _normalizar_ts(evento.get("ts"), evento.get("fecha") or ahora_art().strftime("%Y-%m-%d"))

    if sym not in registro:
        registro[sym] = {
            "symbol": sym,
            "ticker": ticker,
            "fecha_primera": fecha_det,
            "ts_primera": ts_det,
            "tiene_hora_primera": tiene_hora,
            "color_inicial": color,
            "color_maximo": color,
            "es_oro": es_oro,
            "coincide_cazador": coincide_caz,
            "precio_inicial": precio,
            "precio_pico": precio,
            "ia_max_pct": ia_pct,
            "fib_zona": fib_zona,
            "fib_etiqueta": fib_etiqueta,
            "ext_1618": ext_1618,
            "bids_asks": bids_asks,
            "apariciones_count": 1,
            "fechas_vistas": [fecha_det],
            "ts_verde": ts_det if (color == "VERDE" and tiene_hora) else "",
            "ts_amarillo": ts_det if (color == "AMARILLO" and tiene_hora) else "",
            "ts_rojo": ts_det if (color == "ROJO" and tiene_hora) else "",
            "estado": "ACTIVA",
            "fecha_ganadora": "",
            "ts_ganadora": "",
            "precio_ganadora": 0.0,
            "subida_real_pct": 0.0,
            "subida_pico_pct": 0.0,
            "subida_dia_win_pct": 0.0,
            "horas_hasta_ganadora": None,
            "dias_hasta_ganadora": None,
            "mismo_dia_sin_hora": False,
            "alcanzo_fib_1618": False
        }
    else:
        rec = registro[sym]
        vistas = rec.setdefault("fechas_vistas", [])
        if fecha_det not in vistas:
            vistas.append(fecha_det)
            vistas.sort()
        rec["apariciones_count"] = max(len(vistas), int(rec.get("apariciones_count") or 1))

        # Si encontramos una fecha anterior o completamos la hora real del mismo primer día
        f_prev = rec.get("fecha_primera", "9999-99-99")
        if fecha_det < f_prev or (fecha_det == f_prev and tiene_hora and not rec.get("tiene_hora_primera", False)):
            rec["fecha_primera"] = fecha_det
            rec["ts_primera"] = ts_det
            rec["tiene_hora_primera"] = tiene_hora
            rec["color_inicial"] = color
            if precio > 0:
                rec["precio_inicial"] = precio

        if es_oro:
            rec["es_oro"] = True
        if coincide_caz:
            rec["coincide_cazador"] = True
        if PRIORIDAD_COLOR[color] > PRIORIDAD_COLOR.get(rec.get("color_maximo", "VERDE"), 1):
            rec["color_maximo"] = color
        if tiene_hora:
            if color == "VERDE" and (not rec.get("ts_verde") or ts_det < rec["ts_verde"]):
                rec["ts_verde"] = ts_det
            elif color == "AMARILLO" and (not rec.get("ts_amarillo") or ts_det < rec["ts_amarillo"]):
                rec["ts_amarillo"] = ts_det
            elif color == "ROJO" and (not rec.get("ts_rojo") or ts_det < rec["ts_rojo"]):
                rec["ts_rojo"] = ts_det

        if rec.get("precio_inicial", 0.0) <= 0 and precio > 0:
            rec["precio_inicial"] = precio
        if precio > float(rec.get("precio_pico") or 0.0):
            rec["precio_pico"] = precio
        if ia_pct > int(rec.get("ia_max_pct") or 0):
            rec["ia_max_pct"] = ia_pct
        if fib_zona > 0 and rec.get("fib_zona", 0.0) <= 0:
            rec["fib_zona"] = fib_zona
        if fib_etiqueta and not rec.get("fib_etiqueta"):
            rec["fib_etiqueta"] = fib_etiqueta
        if ext_1618 > 0 and rec.get("ext_1618", 0.0) <= 0:
            rec["ext_1618"] = ext_1618
        if bids_asks > 0 and rec.get("bids_asks", 0.0) <= 0:
            rec["bids_asks"] = bids_asks

    dia_bucket = por_dia.setdefault(fecha_det, {})
    hora_str = ts_det[11:16] if tiene_hora else "S/H"
    if sym not in dia_bucket:
        dia_bucket[sym] = {
            "symbol": sym,
            "ticker": ticker,
            "hora": hora_str,
            "color": color,
            "es_oro": es_oro,
            "ia_pct": ia_pct,
            "fib_zona": fib_zona,
            "precio": precio,
            "ext_1618": ext_1618
        }
    else:
        db = dia_bucket[sym]
        if hora_str != "S/H" and (db.get("hora") in ("", "00:00", "S/H") or hora_str < db["hora"]):
            db["hora"] = hora_str
        elif db.get("hora") == "00:00":
            db["hora"] = "S/H"
        if PRIORIDAD_COLOR[color] > PRIORIDAD_COLOR.get(db.get("color", "VERDE"), 1):
            db["color"] = color
        if es_oro:
            db["es_oro"] = True
        if ia_pct > int(db.get("ia_pct") or 0):
            db["ia_pct"] = ia_pct
        if fib_zona > 0:
            db["fib_zona"] = fib_zona
        if db.get("precio", 0.0) <= 0 and precio > 0:
            db["precio"] = precio
        if ext_1618 > 0:
            db["ext_1618"] = ext_1618

def migrar_historial_existente(historial, ganadoras, registro, por_dia):
    """Rescata todo el historial previo en historial_perlas.json e historial_ganadoras.json."""
    hoy_str = historial.get("fecha") or ahora_art().strftime("%Y-%m-%d")
    ayer_str = (ahora_art() - timedelta(days=1)).strftime("%Y-%m-%d")

    for sym, info in (ganadoras.get("registro_verdes") or {}).items():
        if not isinstance(info, dict):
            continue
        _insertar_evento_historico(registro, por_dia, {
            "symbol": sym,
            "ticker": info.get("ticker"),
            "color": "VERDE",
            "es_oro": bool(info.get("es_oro", False)),
            "precio": info.get("precio_verde") or 0.0,
            "fecha": info.get("fecha_verde") or hoy_str,
            "ts": info.get("ts_verde") or info.get("fecha_verde") or hoy_str
        })

    for sym, info in (historial.get("posta") or {}).items():
        if not isinstance(info, dict):
            continue
        etapa = int(info.get("etapa", info.get("paso", 1)))
        col_posta = "ROJO" if etapa >= 3 else ("AMARILLO" if etapa == 2 else "VERDE")
        _insertar_evento_historico(registro, por_dia, {
            "symbol": sym,
            "ticker": info.get("base") or info.get("ticker"),
            "color": col_posta,
            "coincide_cazador": True,
            "precio": info.get("precio_inicio") or info.get("precio_actual") or 0.0,
            "ia_pct": info.get("prob_actual") or 0,
            "fecha": info.get("fecha_iso") or hoy_str,
            "ts": info.get("ts") or info.get("fecha_iso") or hoy_str
        })

    for sym, info in (historial.get("graduadas_pre_explosion") or {}).items():
        if not isinstance(info, dict):
            continue
        origen = str(info.get("origen", "")).upper()
        estrellas = int(info.get("estrellas") or 0)
        col_grad = "AMARILLO" if "SEGUNDA_OLA" in origen else ("ROJO" if estrellas >= 3 else "VERDE")
        _insertar_evento_historico(registro, por_dia, {
            "symbol": sym,
            "ticker": info.get("base") or info.get("ticker"),
            "color": col_grad,
            "es_oro": estrellas >= 3 and col_grad == "VERDE",
            "coincide_cazador": True,
            "precio": info.get("precio_ref") or info.get("precio") or 0.0,
            "ia_pct": info.get("blindaje_pct") or info.get("probabilidad_pct") or 0,
            "fecha": info.get("fecha_iso") or hoy_str,
            "ts": info.get("ts") or info.get("fecha_iso") or hoy_str
        })

    for sym in (historial.get("verdes_ayer") or []):
        _insertar_evento_historico(registro, por_dia, {
            "symbol": sym,
            "color": "VERDE",
            "fecha": ayer_str,
            "ts": ayer_str
        })

    oros_set = set(historial.get("oro_hoy") or [])
    for sym in (historial.get("verdes_hoy") or []):
        _insertar_evento_historico(registro, por_dia, {
            "symbol": sym,
            "color": "VERDE",
            "es_oro": sym in oros_set,
            "fecha": hoy_str,
            "ts": hoy_str
        })

    for sym in (historial.get("resumen_dia") or []):
        _insertar_evento_historico(registro, por_dia, {
            "symbol": sym,
            "color": "VERDE",
            "es_oro": sym in oros_set,
            "fecha": hoy_str,
            "ts": hoy_str
        })

def _generar_excel_pre_explosion(registro, por_dia, mapa_tickers):
    wb = openpyxl.Workbook()
    wb.remove(wb.active)

    fill_titulo = PatternFill(start_color="0F172A", end_color="0F172A", fill_type="solid")
    fill_dia_hdr = PatternFill(start_color="E2E8F0", end_color="E2E8F0", fill_type="solid")
    fill_col_hdr = PatternFill(start_color="1E293B", end_color="1E293B", fill_type="solid")
    fill_verde = PatternFill(start_color="DCFCE7", end_color="DCFCE7", fill_type="solid")
    fill_amarillo = PatternFill(start_color="FEF9C3", end_color="FEF9C3", fill_type="solid")
    fill_rojo = PatternFill(start_color="FEE2E2", end_color="FEE2E2", fill_type="solid")
    fill_win = PatternFill(start_color="DBEAFE", end_color="DBEAFE", fill_type="solid")
    fill_gold = PatternFill(start_color="FEF3C7", end_color="FEF3C7", fill_type="solid")

    borde = Border(
        left=Side(style="thin", color="CBD5E1"),
        right=Side(style="thin", color="CBD5E1"),
        top=Side(style="thin", color="CBD5E1"),
        bottom=Side(style="thin", color="CBD5E1")
    )
    color_fills = {"VERDE": fill_verde, "AMARILLO": fill_amarillo, "ROJO": fill_rojo}

    # --- 1. HOJAS MENSUALES (CALENDARIO LUNES A DOMINGO DINÁMICO SIN RECORTES) ---
    meses = set()
    for f_str in por_dia.keys():
        try:
            d = datetime.strptime(f_str, "%Y-%m-%d").date()
            meses.add((d.year, d.month))
        except Exception:
            continue
    if not meses:
        h = ahora_art().date()
        meses.add((h.year, h.month))

    sub_hdrs = ["Hora", "MONEDA", "Semáforo", "IA %", "$ Entrada", "Estado"]

    for anio, mes in sorted(meses):
        ws = wb.create_sheet(f"{MESES_ES[mes]} {anio}")
        ws.views.sheetView[0].showGridLines = True

        ws["A1"] = f"RADAR PRE-EXPLOSIÓN • {MESES_ES[mes]} {anio} (APARICIONES POR FECHA + CONVERSIÓN A GANADORA)"
        ws["A1"].font = Font(name="Arial", size=12, bold=True, color="FFFFFF")
        ws["A1"].fill = fill_titulo
        ws.merge_cells("A1:AW1")
        ws.row_dimensions[1].height = 26

        fechas_mes = []
        for f_str in sorted(por_dia.keys()):
            try:
                d = datetime.strptime(f_str, "%Y-%m-%d").date()
                if d.year == anio and d.month == mes:
                    fechas_mes.append(d)
            except Exception:
                continue

        semanas_map = {}
        for d in fechas_mes:
            lunes = d - timedelta(days=d.weekday())
            semanas_map.setdefault(lunes, {})[d.weekday()] = d

        fila_base = 3
        for lunes in sorted(semanas_map.keys()):
            # Alto dinámico para que ningún día recorte alertas de Amarillo o Verde
            max_en_semana = max(
                (len(por_dia.get((lunes + timedelta(days=w)).strftime("%Y-%m-%d"), {})) for w in range(7)),
                default=25
            )
            max_filas = max(25, max_en_semana)

            for w_idx in range(7):
                col_ini = 1 + (w_idx * 7)
                dia_dt = lunes + timedelta(days=w_idx)
                f_str = dia_dt.strftime("%Y-%m-%d")
                bucket = por_dia.get(f_str, {}) if dia_dt.month == mes else {}

                lista_dia = sorted(
                    bucket.values(),
                    key=lambda x: (-PRIORIDAD_COLOR.get(x.get("color", "VERDE"), 1), -int(x.get("ia_pct") or 0), x.get("hora", ""))
                )

                ws.cell(fila_base, col_ini, dia_dt.day)
                ws.cell(fila_base, col_ini + 1, f"{MESES_ES[dia_dt.month]} - {DIAS_SEMANA_ES[w_idx]}")
                ws.merge_cells(start_row=fila_base, start_column=col_ini + 1, end_row=fila_base, end_column=col_ini + 5)

                for cc in range(col_ini, col_ini + 6):
                    ch = ws.cell(fila_base, cc)
                    ch.fill = fill_dia_hdr
                    ch.font = Font(name="Arial", size=9.5, bold=True, color="0F172A")
                    ch.border = borde
                    ch.alignment = Alignment(horizontal="center" if cc == col_ini else "left", vertical="center")

                for off, h_txt in enumerate(sub_hdrs):
                    sh = ws.cell(fila_base + 1, col_ini + off, h_txt)
                    sh.fill = fill_col_hdr
                    sh.font = Font(name="Arial", size=9, bold=True, color="FFFFFF")
                    sh.alignment = Alignment(horizontal="center", vertical="center")
                    sh.border = borde

                for r_off in range(max_filas):
                    fa = fila_base + 2 + r_off
                    if r_off < len(lista_dia):
                        it = lista_dia[r_off]
                        sym = it["symbol"]
                        rec_global = registro.get(sym, {})
                        es_win = (rec_global.get("estado") == "GANADORA")
                        col_cod = it.get("color", "VERDE")

                        demora_lbl = _formatear_demora(
                            rec_global.get("horas_hasta_ganadora"),
                            rec_global.get("mismo_dia_sin_hora", False)
                        )
                        estado_txt = f"🏆 WIN ({demora_lbl})" if es_win else "⏳ Activa"
                        hora_mostrar = "S/H" if it.get("hora") in ("", "00:00", "S/H") else it.get("hora")

                        vals = [
                            hora_mostrar,
                            it.get("ticker", ""),
                            _etiqueta_semaforo(it),
                            f"{it.get('ia_pct', 0)}%" if it.get("ia_pct") else "-",
                            float(it.get("precio") or 0.0),
                            estado_txt
                        ]
                        for off, val in enumerate(vals):
                            c = ws.cell(fa, col_ini + off, val)
                            c.font = Font(name="Arial", size=8.5, bold=es_win)
                            c.border = borde
                            c.alignment = Alignment(
                                horizontal="center" if off in (0, 2, 3, 5) else ("right" if off == 4 else "left")
                            )
                            if off == 2:
                                c.fill = color_fills.get(col_cod, fill_verde)
                            elif es_win:
                                c.fill = fill_win
                    else:
                        for off in range(6):
                            ce = ws.cell(fa, col_ini + off, "")
                            ce.border = borde

            ws.row_dimensions[fila_base].height = 20
            ws.row_dimensions[fila_base + 1].height = 19
            fila_base += max_filas + 4

        for b_idx in range(7):
            cs = 1 + (b_idx * 7)
            ws.column_dimensions[openpyxl.utils.get_column_letter(cs)].width = 6.5
            ws.column_dimensions[openpyxl.utils.get_column_letter(cs + 1)].width = 10.5
            ws.column_dimensions[openpyxl.utils.get_column_letter(cs + 2)].width = 13.5
            ws.column_dimensions[openpyxl.utils.get_column_letter(cs + 3)].width = 6.5
            ws.column_dimensions[openpyxl.utils.get_column_letter(cs + 4)].width = 10.5
            ws.column_dimensions[openpyxl.utils.get_column_letter(cs + 5)].width = 16.5
            if b_idx < 6:
                ws.column_dimensions[openpyxl.utils.get_column_letter(cs + 6)].width = 2.5

    # --- 2. PESTAÑA CRUCE_TIEMPOS_GANADORA ---
    ws_cruce = wb.create_sheet("CRUCE_TIEMPOS_GANADORA")
    headers_cruce = [
        "MONEDA", "1ª APARICIÓN", "SEMÁFORO INICIAL", "SEMÁFORO MÁX",
        "ESCALADA SEMÁFORO", "VECES VISTA", "IA MÁX %", "FIB ZONA", "BIDS/ASKS",
        "$ ENTRADA", "$ PICO MÁX", "SUBIDA PICO %", "ESTADO",
        "FECHA GANADORA", "$ GANADORA / ACTUAL", "VAR. REAL %",
        "TIEMPO HASTA GANADORA", "DÍAS DEC.", "FIB 1.618"
    ]
    ws_cruce.append(headers_cruce)
    ws_cruce.row_dimensions[1].height = 30
    for ci in range(1, len(headers_cruce) + 1):
        ch = ws_cruce.cell(1, ci)
        ch.font = Font(name="Arial", size=9, bold=True, color="FFFFFF")
        ch.fill = fill_titulo
        ch.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

    ordenadas = sorted(registro.values(), key=lambda x: x.get("ts_primera", ""), reverse=True)
    hoy_dt = ahora_art()

    for r_i, rec in enumerate(ordenadas, start=2):
        sym = rec["symbol"]
        es_win = (rec.get("estado") == "GANADORA")
        p_ini = float(rec.get("precio_inicial") or 0.0)
        t_live = mapa_tickers.get(sym, {})
        p_live = float(t_live.get("lastPrice", 0) or 0.0)
        p_pico = max(float(rec.get("precio_pico") or 0.0), p_ini, p_live, float(rec.get("precio_ganadora") or 0.0))
        sub_pico = round(((p_pico - p_ini) / p_ini) * 100, 2) if (p_ini > 0 and p_pico > 0) else 0.0

        ts_mostrar = (
            rec["ts_primera"][:16]
            if rec.get("tiene_hora_primera", not str(rec.get("ts_primera", "")).endswith("00:00"))
            else f"{rec.get('fecha_primera', '')} (S/H)"
        )

        if es_win:
            p_ref_final = float(rec.get("precio_ganadora") or p_live)
            var_pct = float(rec.get("subida_real_pct") or 0.0)
            tiempo_str = _formatear_demora(
                rec.get("horas_hasta_ganadora"),
                rec.get("mismo_dia_sin_hora", False)
            )
            dias_dec = rec.get("dias_hasta_ganadora")
        else:
            p_ref_final = p_live
            var_pct = round(((p_live - p_ini) / p_ini) * 100, 2) if (p_ini > 0 and p_live > 0) else 0.0
            try:
                if rec.get("tiene_hora_primera", not str(rec.get("ts_primera", "")).endswith("00:00")):
                    dt0 = datetime.strptime(rec["ts_primera"][:16], "%Y-%m-%d %H:%M").replace(tzinfo=TZ_ART)
                    h_esp = max(0.0, (hoy_dt - dt0).total_seconds() / 3600.0)
                    tiempo_str = f"Esperando ({_formatear_demora(h_esp)})"
                    dias_dec = round(h_esp / 24.0, 2)
                else:
                    d0 = datetime.strptime(rec["fecha_primera"], "%Y-%m-%d").date()
                    d_esp = max(0, (hoy_dt.date() - d0).days)
                    tiempo_str = "Esperando (Hoy)" if d_esp == 0 else f"Esperando ({d_esp}d)"
                    dias_dec = float(d_esp)
            except Exception:
                tiempo_str = "Esperando"
                dias_dec = 0.0

        row = [
            rec.get("ticker"),
            ts_mostrar,
            _etiqueta_semaforo(rec),
            {"VERDE": "🟢 VERDE", "AMARILLO": "🟡 AMARILLO", "ROJO": "🔴 ROJO"}.get(rec.get("color_maximo", "VERDE"), ""),
            _calcular_velocidad_escalada(rec),
            int(rec.get("apariciones_count") or 1),
            f"{rec.get('ia_max_pct', 0)}%" if rec.get("ia_max_pct") else "-",
            round(float(rec.get("fib_zona") or 0.0), 2) if rec.get("fib_zona") else "-",
            f"{rec.get('bids_asks')}x" if rec.get("bids_asks") else "-",
            p_ini,
            p_pico if p_ini > 0 else 0.0,
            f"{sub_pico:+.2f}%" if p_ini > 0 else "-",
            "🏆 GANADORA" if es_win else "⏳ EN SEGUIMIENTO",
            rec.get("ts_ganadora") if es_win else "-",
            p_ref_final,
            f"{var_pct:+.2f}%" if (p_ini > 0 or es_win) else "-",
            tiempo_str,
            dias_dec,
            "SÍ" if rec.get("alcanzo_fib_1618") else ("NO" if es_win else "-")
        ]
        ws_cruce.append(row)
        for ci in range(1, len(headers_cruce) + 1):
            cell = ws_cruce.cell(r_i, ci)
            cell.border = borde
            cell.font = Font(name="Arial", size=9.5, bold=es_win)
            if es_win:
                cell.fill = fill_win
            elif sub_pico >= 10.0:
                cell.fill = fill_verde

    anchos_cruce = [12, 19, 17, 16, 18, 12, 11, 11, 12, 13, 13, 14, 18, 18, 21, 13, 23, 12, 11]
    for i, w in enumerate(anchos_cruce, start=1):
        ws_cruce.column_dimensions[openpyxl.utils.get_column_letter(i)].width = w

    # --- 3. PESTAÑA ANALISIS_PATRONES ---
    ws_pat = wb.create_sheet("ANALISIS_PATRONES")
    ws_pat["A1"] = "ANÁLISIS ESTADÍSTICO DE PATRONES • PRE-EXPLOSIÓN ➔ GANADORA"
    ws_pat["A1"].font = Font(name="Arial", size=12, bold=True, color="FFFFFF")
    ws_pat["A1"].fill = fill_titulo
    ws_pat.merge_cells("A1:G1")
    ws_pat.row_dimensions[1].height = 26

    todas = list(registro.values())
    ganadas = [r for r in todas if r.get("estado") == "GANADORA"]

    def _resumir_grupo(nombre, sublista):
        tot = len(sublista)
        wins = [x for x in sublista if x.get("estado") == "GANADORA"]
        horas = [
            x["horas_hasta_ganadora"] for x in wins
            if x.get("horas_hasta_ganadora") is not None and not x.get("mismo_dia_sin_hora", False)
        ]
        subs = [float(x.get("subida_real_pct") or 0.0) for x in wins]
        picos = [float(x.get("subida_pico_pct") or 0.0) for x in sublista if float(x.get("precio_inicial") or 0.0) > 0]
        tasa = f"{round((len(wins)/tot)*100, 1)}%" if tot > 0 else "0.0%"
        if horas:
            dem_prom = _formatear_demora(sum(horas) / len(horas))
        elif wins:
            dem_prom = "Mismo día"
        else:
            dem_prom = "-"
        sub_prom = f"{(sum(subs)/len(subs)):+.1f}%" if subs else "-"
        pico_prom = f"{(sum(picos)/len(picos)):+.1f}%" if picos else "-"
        return [nombre, tot, len(wins), tasa, dem_prom, sub_prom, pico_prom]

    bloques_tabla = [
        ("1. RENDIMIENTO SEGÚN SEMÁFORO DE ENTRADA", [
            _resumir_grupo("🏆 TOP ORO (Verde Prioritario)", [r for r in todas if r.get("color_inicial") == "VERDE" and r.get("es_oro")]),
            _resumir_grupo("🟢 VERDE (Compra Temprana)", [r for r in todas if r.get("color_inicial") == "VERDE" and not r.get("es_oro")]),
            _resumir_grupo("🟡 AMARILLO (Confirmación Táctica)", [r for r in todas if r.get("color_inicial") == "AMARILLO"]),
            _resumir_grupo("🔴 ROJO (Explosión Inminente)", [r for r in todas if r.get("color_inicial") == "ROJO"]),
        ]),
        ("2. RENDIMIENTO SEGÚN CERTIFICACIÓN IA Y CONFLUENCIA", [
            _resumir_grupo("Coincide Cazador + Pre-Explosión", [r for r in todas if r.get("coincide_cazador")]),
            _resumir_grupo("IA >= 90% (Alta Convicción)", [r for r in todas if int(r.get("ia_max_pct") or 0) >= 90]),
            _resumir_grupo("IA 75% – 89% (Validada)", [r for r in todas if 75 <= int(r.get("ia_max_pct") or 0) < 90]),
            _resumir_grupo("IA < 75% o Sin Dato Histórico", [r for r in todas if int(r.get("ia_max_pct") or 0) < 75]),
        ]),
        ("3. RENDIMIENTO SEGÚN LIBRO DE ÓRDENES (BIDS / ASKS)", [
            _resumir_grupo("Libro Comprador Fuerte (Bids/Asks >= 1.25x)", [r for r in todas if float(r.get("bids_asks") or 0.0) >= 1.25]),
            _resumir_grupo("Libro Equilibrado (1.00x – 1.24x)", [r for r in todas if 1.0 <= float(r.get("bids_asks") or 0.0) < 1.25]),
            _resumir_grupo("Libro Débil (< 1.00x) o Sin Dato Histórico", [r for r in todas if float(r.get("bids_asks") or 0.0) < 1.0]),
        ]),
        ("4. RENDIMIENTO SEGÚN ZONA FIBONACCI Y RECURRENCIA", [
            _resumir_grupo("Pullback Sano Fib (0.35 – 0.65)", [r for r in todas if 0.35 <= float(r.get("fib_zona") or 0.0) <= 0.65]),
            _resumir_grupo("Piso Profundo Fib (> 0.65)", [r for r in todas if float(r.get("fib_zona") or 0.0) > 0.65]),
            _resumir_grupo("Persistentes (2+ días en Pre-Explosión)", [r for r in todas if int(r.get("apariciones_count") or 1) >= 2]),
        ]),
        ("5. RENDIMIENTO SEGÚN DÍA DE APARICIÓN", [
            _resumir_grupo(DIAS_SEMANA_ES[d_idx], [
                r for r in todas
                if r.get("fecha_primera") and datetime.strptime(r["fecha_primera"], "%Y-%m-%d").weekday() == d_idx
            ])
            for d_idx in range(7)
        ])
    ]

    fila_p = 3
    cols_pat = ["Segmento / Patrón", "Detectadas", "Ganadoras", "Tasa Acierto", "Demora Promedio", "Subida Cierre", "Pico Máx Prom."]
    for titulo_bloque, filas_datos in bloques_tabla:
        ws_pat.cell(fila_p, 1, titulo_bloque).font = Font(name="Arial", size=10.5, bold=True, color="0F172A")
        ws_pat.cell(fila_p, 1).fill = fill_dia_hdr
        ws_pat.merge_cells(start_row=fila_p, start_column=1, end_row=fila_p, end_column=7)
        fila_p += 1

        for ci, h_txt in enumerate(cols_pat, start=1):
            c = ws_pat.cell(fila_p, ci, h_txt)
            c.fill = fill_col_hdr
            c.font = Font(name="Arial", size=9.5, bold=True, color="FFFFFF")
            c.alignment = Alignment(horizontal="center")
            c.border = borde
        fila_p += 1

        for row_vals in filas_datos:
            for ci, val in enumerate(row_vals, start=1):
                c = ws_pat.cell(fila_p, ci, val)
                c.border = borde
                c.font = Font(name="Arial", size=9.5, bold=(ci == 4 and val != "0.0%"))
                c.alignment = Alignment(horizontal="left" if ci == 1 else "center")
                if row_vals[2] > 0:
                    c.fill = fill_verde
            fila_p += 1
        fila_p += 1

    anchos_pat = [42, 13, 13, 15, 19, 15, 16]
    for i, w in enumerate(anchos_pat, start=1):
        ws_pat.column_dimensions[openpyxl.utils.get_column_letter(i)].width = w

    # --- 4. PESTAÑA DIAGNOSTICO_HISTORICO ---
    ws_diag = wb.create_sheet("DIAGNOSTICO_HISTORICO")
    ws_diag["A1"] = "DIAGNÓSTICO AUTOMÁTICO DE DATOS ACUMULADOS"
    ws_diag["A1"].font = Font(name="Arial", size=12, bold=True, color="FFFFFF")
    ws_diag["A1"].fill = fill_titulo
    ws_diag.merge_cells("A1:B1")
    ws_diag.row_dimensions[1].height = 26

    horas_all = [
        r["horas_hasta_ganadora"] for r in ganadas
        if r.get("horas_hasta_ganadora") is not None and not r.get("mismo_dia_sin_hora", False)
    ]
    prom_h = round(sum(horas_all) / len(horas_all), 1) if horas_all else None
    med_h = sorted(horas_all)[len(horas_all) // 2] if horas_all else None
    tasa_global = round((len(ganadas) / len(todas)) * 100, 1) if todas else 0.0

    en_curso_subiendo = []
    for r in todas:
        if r.get("estado") != "GANADORA":
            p0 = float(r.get("precio_inicial") or 0.0)
            p1 = float(mapa_tickers.get(r["symbol"], {}).get("lastPrice", 0) or 0.0)
            if p0 > 0 and p1 > 0:
                v = round(((p1 - p0) / p0) * 100, 2)
                if v > 0:
                    en_curso_subiendo.append((r["ticker"], v, r["fecha_primera"]))
    en_curso_subiendo.sort(key=lambda x: x[1], reverse=True)

    top_flotantes_txt = (
        ", ".join([f"{t} ({v:+.2f}% desde {f})" for t, v, f in en_curso_subiendo[:6]])
        if en_curso_subiendo else "Aún sin precios de entrada históricos previos"
    )
    ganadas_txt = (
        ", ".join([
            f"{g['ticker']} ({_formatear_demora(g.get('horas_hasta_ganadora'), g.get('mismo_dia_sin_hora', False))}, {float(g.get('subida_real_pct', 0)):+.2f}%)"
            for g in ganadas[:10]
        ])
        if ganadas else "En acumulación de cierres"
    )

    diag_rows = [
        ("Universo Histórico Migrado", f"{len(todas)} monedas únicas distribuidas en {len(por_dia)} días registrados"),
        ("Conversión Confirmada a Ganadoras", f"{len(ganadas)} monedas ({tasa_global}% del total detectado)"),
        ("Tiempo Promedio de Consolidación", f"{_formatear_demora(prom_h)} (Mediana: {_formatear_demora(med_h)})" if prom_h is not None else "Mismo día / En acumulación"),
        ("Monedas que ya Completaron el Ciclo", ganadas_txt),
        ("Monedas Históricas Subiendo en Seguimiento", top_flotantes_txt),
    ]

    for idx, (k, v) in enumerate(diag_rows, start=3):
        c1 = ws_diag.cell(idx, 1, k)
        c2 = ws_diag.cell(idx, 2, v)
        c1.font = Font(name="Arial", size=10, bold=True)
        c2.font = Font(name="Arial", size=10)
        c1.fill = fill_gold if idx in (4, 5) else fill_dia_hdr
        c2.fill = fill_gold if idx in (4, 5) else PatternFill(fill_type=None)
        c1.border = borde
        c2.border = borde

    ws_diag.column_dimensions["A"].width = 40
    ws_diag.column_dimensions["B"].width = 80

    wb.save(EXCEL_PRE_EXPLOSION_FILE)
    return {
        "total": len(todas),
        "dias_hist": len(por_dia),
        "ganadas": len(ganadas),
        "tasa_pct": tasa_global,
        "prom_txt": _formatear_demora(prom_h) if prom_h is not None else "Mismo día"
    }

def enviar_telegram_documento(doc_path, caption_text):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID or not os.path.exists(doc_path):
        return False
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendDocument"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "caption": caption_text[:1020], "parse_mode": "HTML"}
    if TELEGRAM_TOPIC_ID.isdigit():
        payload["message_thread_id"] = int(TELEGRAM_TOPIC_ID)
    try:
        with open(doc_path, "rb") as doc:
            res = requests.post(url, data=payload, files={"document": doc}, timeout=45).json()
            if not res.get("ok") and "thread not found" in str(res.get("description", "")).lower():
                payload.pop("message_thread_id", None)
                doc.seek(0)
                res = requests.post(url, data=payload, files={"document": doc}, timeout=45).json()
            return bool(res.get("ok"))
    except Exception as e:
        print(f"❌ Error enviando Excel Pre-Explosión: {e}")
        return False

def ejecutar_auditoria_y_excel_pre_explosion(historial, bloques, mapa_tickers):
    """Migra historial, cruza con Monedas Ganadoras, genera AUDITORIA_PRE_EXPLOSION.xlsx y lo envía al cierre."""
    ahora = ahora_art()
    hoy_str = ahora.strftime("%Y-%m-%d")
    ayer_str = (ahora - timedelta(days=1)).strftime("%Y-%m-%d")
    ts_now_str = ahora.strftime("%Y-%m-%d %H:%M")

    ganadoras = {"dias": {}, "registro_verdes": {}}
    if os.path.exists(HISTORIAL_GANADORAS_FILE):
        try:
            with open(HISTORIAL_GANADORAS_FILE, "r", encoding="utf-8") as f:
                data_g = json.load(f)
            if isinstance(data_g, dict):
                ganadoras = data_g
        except Exception as e:
            print(f"⚠️ Error leyendo {HISTORIAL_GANADORAS_FILE}: {e}")

    registro = historial.setdefault("registro_cronologico", {})
    por_dia = historial.setdefault("apariciones_por_dia", {})

    # 1. Migrar historia previa
    migrar_historial_existente(historial, ganadoras, registro, por_dia)

    # 2. Registrar detecciones del ciclo actual
    for cat_key in ("ROJO", "AMARILLO", "VERDE"):
        for it in (bloques.get(cat_key) or []):
            fib = it.get("fib_info") or {}
            _insertar_evento_historico(registro, por_dia, {
                "symbol": it["symbol"],
                "ticker": it["ticker"],
                "color": cat_key,
                "es_oro": bool(it.get("es_oro", False)),
                "coincide_cazador": bool(it.get("desde_posta") or it.get("en_cazador_tactico")),
                "precio": it.get("precio_f", 0.0),
                "ia_pct": it.get("blindaje_pct", 0),
                "fib_zona": fib.get("ratio", 0.0) if fib.get("ok") else 0.0,
                "fib_etiqueta": fib.get("etiqueta_fib", "") if fib.get("ok") else "",
                "ext_1618": fib.get("ext_1618", 0.0) if fib.get("ok") else 0.0,
                "bids_asks": it.get("ratio_bids_asks", 0.0),
                "fecha": hoy_str,
                "ts": ts_now_str
            })

    # 3. Actualizar picos máximos y cruzar contra Monedas Ganadoras
    dias_win = ganadoras.get("dias", {})
    fechas_win_ord = sorted(dias_win.keys())
    ts_cierre_win_default = str(ganadoras.get("ultima_actualizacion", ""))[:16]

    precios_hist_win = {}
    for f_w, lista_w in dias_win.items():
        for g in lista_w:
            sym_g = g.get("symbol", "")
            if sym_g:
                precios_hist_win.setdefault(sym_g, {})[f_w] = g

    for sym, rec in registro.items():
        f_ini = rec.get("fecha_primera", "")
        if not f_ini:
            continue

        if float(rec.get("precio_inicial") or 0.0) <= 0:
            if sym in precios_hist_win and f_ini in precios_hist_win[sym]:
                p_b = float(precios_hist_win[sym][f_ini].get("precio_base") or 0.0)
                if p_b > 0:
                    rec["precio_inicial"] = p_b
            elif sym in mapa_tickers and f_ini == hoy_str:
                rec["precio_inicial"] = float(mapa_tickers[sym].get("lastPrice", 0) or 0.0)

        p_ini = float(rec.get("precio_inicial") or 0.0)
        p_live = float(mapa_tickers.get(sym, {}).get("lastPrice", 0) or 0.0)
        p_pico_actual = max(float(rec.get("precio_pico") or 0.0), p_ini, p_live)

        # Revisar también el máximo diario registrado en Ganadoras en fechas >= f_ini
        for f_w, g_info in precios_hist_win.get(sym, {}).items():
            if f_w >= f_ini:
                p_pico_actual = max(p_pico_actual, float(g_info.get("high") or g_info.get("precio") or 0.0))

        rec["precio_pico"] = p_pico_actual
        if p_ini > 0 and p_pico_actual > 0:
            rec["subida_pico_pct"] = round(((p_pico_actual - p_ini) / p_ini) * 100, 2)

        dia_b = por_dia.get(f_ini, {}).get(sym)
        if dia_b and float(dia_b.get("precio") or 0.0) <= 0 and p_ini > 0:
            dia_b["precio"] = p_ini

        # Recalcular o completar cruce con Ganadoras
        for f_win in fechas_win_ord:
            if f_win < f_ini:
                continue
            match = precios_hist_win.get(sym, {}).get(f_win)
            if match:
                p_win = float(match.get("precio") or 0.0)
                subida_real = (
                    round(((p_win - p_ini) / p_ini) * 100, 2)
                    if p_ini > 0 else float(match.get("cambio_24h", 0.0))
                )
                tiene_hora_ini = rec.get("tiene_hora_primera", not str(rec.get("ts_primera", "")).endswith("00:00"))
                mismo_dia_sh = (f_win == f_ini and not tiene_hora_ini)

                if mismo_dia_sh:
                    horas_diff = 0.0
                    dias_diff = 0.0
                else:
                    try:
                        dt_ini = datetime.strptime(rec["ts_primera"][:16], "%Y-%m-%d %H:%M")
                    except Exception:
                        dt_ini = datetime.strptime(f_ini, "%Y-%m-%d")

                    ts_w_str = ts_cierre_win_default if ts_cierre_win_default.startswith(f_win) else f"{f_win} 23:45"
                    try:
                        dt_win = datetime.strptime(ts_w_str, "%Y-%m-%d %H:%M")
                    except Exception:
                        dt_win = datetime.strptime(f_win, "%Y-%m-%d") + timedelta(hours=23, minutes=45)

                    horas_diff = max(0.0, round((dt_win - dt_ini).total_seconds() / 3600.0, 1))
                    dias_diff = round(horas_diff / 24.0, 2)

                ts_w_final = ts_cierre_win_default if ts_cierre_win_default.startswith(f_win) else f"{f_win} 23:45"
                rec["estado"] = "GANADORA"
                rec["fecha_ganadora"] = f_win
                rec["ts_ganadora"] = ts_w_final
                rec["precio_ganadora"] = p_win
                rec["subida_real_pct"] = subida_real
                rec["subida_dia_win_pct"] = float(match.get("cambio_24h", 0.0))
                rec["horas_hasta_ganadora"] = horas_diff
                rec["dias_hasta_ganadora"] = dias_diff
                rec["mismo_dia_sin_hora"] = mismo_dia_sh
                ext_target = float(rec.get("ext_1618") or 0.0)
                rec["alcanzo_fib_1618"] = bool(ext_target > 0 and max(p_win, p_pico_actual) >= ext_target)
                break

    # 4. Generar Excel completo
    stats = _generar_excel_pre_explosion(registro, por_dia, mapa_tickers)

    # 5. Enviar Excel diario a Telegram
    ultimo_envio = historial.get("ultimo_envio_excel_pre", "")
    es_cierre = (ahora.hour == 23 and ahora.minute >= 30 and ultimo_envio != hoy_str)
    es_recupero = (ahora.hour <= 2 and ultimo_envio != ayer_str)
    es_manual = (os.getenv("GITHUB_EVENT_NAME") == "workflow_dispatch")

    if es_cierre or es_recupero or es_manual:
        fecha_lbl = ayer_str if (es_recupero and not es_cierre) else hoy_str
        caption = (
            f"📊 <b>Excel Pre-Explosión + Historial ({fecha_lbl})</b>\n"
            f"• Universo histórico: <b>{stats['total']} monedas</b> en <b>{stats['dias_hist']} días</b>\n"
            f"• Convertidas en Ganadoras: <b>{stats['ganadas']}</b> ({stats['tasa_pct']}%)\n"
            f"• ⏱️ Tiempo medio hasta Ganadora: <code>{stats['prom_txt']}</code>"
        )
        time.sleep(1.5)
        if enviar_telegram_documento(EXCEL_PRE_EXPLOSION_FILE, caption):
            if not es_manual:
                historial["ultimo_envio_excel_pre"] = fecha_lbl

    guardar_historial(historial)

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
    print(f"🔥 EJECUTANDO PRE-EXPLOSIÓN V8 + CERTIFICADOR IA + EXCEL ({ahora_art().strftime('%Y-%m-%d %H:%M:%S')} ART)...")
    session = crear_sesion_binance()
    simbolos_activos = obtener_simbolos_spot_activos(session)
    datos = obtener_datos_binance(session)

    if datos and simbolos_activos:
        historial = cargar_historial()
        bloques, total_analizadas, historial, mapa_tickers = motor_ia_seleccion_tactica(datos, simbolos_activos, session, historial)

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

        ejecutar_auditoria_y_excel_pre_explosion(historial, bloques, mapa_tickers)
    else:
        print("❌ ERROR: Sin datos o sin símbolos activos de Binance.")
