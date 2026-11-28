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
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.chart import BarChart, Reference
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
EXCEL_CAZADOR_FILE = "HISTORICO_CAZADOR_TACTICO.xlsx"
REPORTE_IA_PRE_EXPLOSION_FILE = "reporte_ia_pre_explosion.json"
DIAS_GRADUADAS = 7
DIAS_RETENCION_CALENDARIO = 730
MODELOS_GEMINI_PRE = ["gemini-2.5-flash", "gemini-2.5-flash-lite"]

MESES_ES = {
    1: "Enero", 2: "Febrero", 3: "Marzo", 4: "Abril",
    5: "Mayo", 6: "Junio", 7: "Julio", 8: "Agosto",
    9: "Septiembre", 10: "Octubre", 11: "Noviembre", 12: "Diciembre"
}
PRIORIDAD_COLOR = {"VERDE": 1, "AMARILLO": 2, "ROJO": 3}

EXCL_BASE = {
    'USDT', 'USDC', 'FDUSD', 'DAI', 'TUSD', 'USDP', 'EUR', 'GBP', 'AUD', 'BRL', 'ARS', 'TRY', 'BUSD',
    'USD1', 'AEUR', 'EURI', 'USDE', 'RLUSD', 'RWUSD', 'XUSD', 'BFUSD', 'U', 'USDG', 'USDS', 'PYUSD',
    'BTC', 'ETH', 'SOL', 'ADA', 'XRP', 'DOGE', 'TRX', 'SHIB', 'AVAX', 'LINK', 'BNB', 'DOT', 'NEAR', 'SUI', 'PEPE'
}


def ahora_art():
    return datetime.now(TZ_ART)


def es_simbolo_valido(base):
    if not base or base in EXCL_BASE:
        return False
    if not re.match(r'^[A-Z0-9]+$', base):
        return False
    if base.endswith('B'):
        return False
    if any(x in base for x in ['UP', 'DOWN', 'BULL', 'BEAR']):
        return False
    return True


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
        "eventos_unificados": {},
        "ultimo_envio_excel_pre": ""
    }
    if os.path.exists(HISTORIAL_FILE):
        try:
            with open(HISTORIAL_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)

            base["posta"] = data.get("posta", {}) if isinstance(data.get("posta"), dict) else {}
            base["registro_cronologico"] = data.get("registro_cronologico", {}) if isinstance(data.get("registro_cronologico"), dict) else {}
            base["eventos_unificados"] = data.get("eventos_unificados", {}) if isinstance(data.get("eventos_unificados"), dict) else {}
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
                if not es_simbolo_valido(base_sym):
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
            for mod in MODELOS_GEMINI_PRE:
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
# UNIFICACIÓN HISTÓRICA COMPLETA + ASISTENTE IA + EXCEL EJECUTIVO DE 5 PESTAÑAS
# ==============================================================================
def _normalizar_symbol(raw):
    s = str(raw or "").strip().upper()
    if not s:
        return ""
    if not s.endswith("USDT"):
        s = f"{s}USDT"
    return s


def _norm_semaforo_etiqueta(val):
    s = str(val or "").upper()
    if "ORO" in s:
        return "🏆 TOP ORO"
    if "ROJ" in s:
        return "🔴 ROJO"
    if "AMAR" in s:
        return "🟡 AMARILLO"
    return "🟢 VERDE"


def _semaforo_codigo(etiqueta):
    s = str(etiqueta or "").upper()
    if "ROJ" in s:
        return "ROJO"
    if "AMAR" in s:
        return "AMARILLO"
    return "VERDE"


def _parse_ia_frac(val):
    if val is None:
        return None
    s = str(val).replace("%", "").strip()
    if s in ("", "-", "None", "nan"):
        return None
    try:
        v = float(s)
        return round(v / 100.0, 4) if v > 1.0 else round(v, 4)
    except Exception:
        return None


def _parse_ba_float(val):
    if val is None:
        return None
    s = str(val).replace("x", "").strip()
    if s in ("", "-", "None", "nan"):
        return None
    try:
        return round(float(s), 2)
    except Exception:
        return None


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


def _upsert_evento_unificado(eventos, ev):
    """Inserta o actualiza un evento único indexado por 'YYYY-MM-DD|MONEDA' para no perder ni duplicar historial."""
    fecha = str(ev.get("Fecha") or "")[:10]
    mon = str(ev.get("Moneda") or "").strip().upper()
    if mon.endswith("USDT"):
        mon = mon[:-4]
    if not fecha or not es_simbolo_valido(mon):
        return

    key = f"{fecha}|{mon}"
    hora = str(ev.get("Hora") or "S/H").strip()
    if hora in ("", "00:00", "None", "nan"):
        hora = "S/H"

    sem_ini = _norm_semaforo_etiqueta(ev.get("Semaforo_Ini"))
    sem_max = _norm_semaforo_etiqueta(ev.get("Semaforo_Max") or sem_ini)
    escalada = str(ev.get("Escalada") or ("Directo 🔴" if "ROJO" in sem_ini else "-")).strip()
    ia_frac = ev.get("IA_Pct")
    fib_zona = ev.get("Fib_Zona")
    bids_asks = ev.get("Bids_Asks")
    p_ent = float(ev.get("Precio_Entrada") or 0.0)
    p_pico = max(float(ev.get("Precio_Pico") or 0.0), p_ent)
    estado = str(ev.get("Estado") or "⏳ EN SEGUIMIENTO").strip()
    f_win = str(ev.get("Fecha_Ganadora") or "-").strip()
    p_fin = float(ev.get("Precio_Final") or p_ent)
    t_txt = str(ev.get("Tiempo_Ganadora_Txt") or "En seguimiento").strip()
    dias_dec = ev.get("Dias_Dec")
    fib_1618 = str(ev.get("Fib_1618") or "-").strip()
    confluencia = str(ev.get("Confluencia") or "Solo Pre-Explosión").strip()
    origen = str(ev.get("Origen") or "Bot Pre-Explosión").strip()

    if key not in eventos:
        eventos[key] = {
            "Fecha": fecha,
            "Hora": hora,
            "Moneda": mon,
            "Semaforo_Ini": sem_ini,
            "Semaforo_Max": sem_max,
            "Escalada": escalada,
            "IA_Pct": ia_frac,
            "Fib_Zona": fib_zona,
            "Bids_Asks": bids_asks,
            "Precio_Entrada": p_ent,
            "Precio_Pico": p_pico,
            "Estado": estado,
            "Fecha_Ganadora": f_win,
            "Precio_Final": p_fin,
            "Tiempo_Ganadora_Txt": t_txt,
            "Dias_Dec": dias_dec,
            "Fib_1618": fib_1618,
            "Confluencia": confluencia,
            "Origen": origen
        }
    else:
        cur = eventos[key]
        if hora != "S/H" and (cur.get("Hora") in ("", "S/H", "00:00") or hora < cur["Hora"]):
            cur["Hora"] = hora
        if PRIORIDAD_COLOR[_semaforo_codigo(sem_max)] > PRIORIDAD_COLOR[_semaforo_codigo(cur.get("Semaforo_Max"))]:
            cur["Semaforo_Max"] = sem_max
        if "ORO" in sem_ini:
            cur["Semaforo_Ini"] = "🏆 TOP ORO"
        if escalada not in ("", "-") and cur.get("Escalada") in ("", "-"):
            cur["Escalada"] = escalada
        if ia_frac is not None and (cur.get("IA_Pct") is None or ia_frac > float(cur["IA_Pct"])):
            cur["IA_Pct"] = ia_frac
        if fib_zona is not None and cur.get("Fib_Zona") is None:
            cur["Fib_Zona"] = fib_zona
        if bids_asks is not None and cur.get("Bids_Asks") is None:
            cur["Bids_Asks"] = bids_asks
        if cur.get("Precio_Entrada", 0.0) <= 0 and p_ent > 0:
            cur["Precio_Entrada"] = p_ent
        if p_pico > float(cur.get("Precio_Pico") or 0.0):
            cur["Precio_Pico"] = p_pico
        if "GANADORA" in estado.upper():
            cur["Estado"] = "🏆 GANADORA"
            if f_win not in ("", "-"):
                cur["Fecha_Ganadora"] = f_win
            if p_fin > 0:
                cur["Precio_Final"] = p_fin
            if t_txt not in ("", "-", "En seguimiento"):
                cur["Tiempo_Ganadora_Txt"] = t_txt
            if dias_dec is not None:
                cur["Dias_Dec"] = dias_dec
            if fib_1618 not in ("", "-"):
                cur["Fib_1618"] = fib_1618
        elif p_fin > 0 and cur.get("Estado") != "🏆 GANADORA":
            cur["Precio_Final"] = p_fin
            if t_txt not in ("", "-"):
                cur["Tiempo_Ganadora_Txt"] = t_txt
            if dias_dec is not None:
                cur["Dias_Dec"] = dias_dec
        if "SÍ" in confluencia:
            cur["Confluencia"] = "SÍ (Cazador + Pre-Exp)"
            if "Cazador" not in cur.get("Origen", ""):
                cur["Origen"] = "Cazador + Pre-Explosión"


def _hidratar_desde_excels_y_json(historial, ganadoras, eventos):
    """Rescata todo el historial previo desde AUDITORIA_PRE_EXPLOSION.xlsx, HISTORICO_CAZADOR_TACTICO.xlsx y JSONs."""
    # 1. Leer AUDITORIA_PRE_EXPLOSION.xlsx previo (formato nuevo de 5 hojas o formato anterior)
    if os.path.exists(EXCEL_PRE_EXPLOSION_FILE):
        try:
            wb_prev = openpyxl.load_workbook(EXCEL_PRE_EXPLOSION_FILE, data_only=True)
            if "3_REGISTRO_MAESTRO" in wb_prev.sheetnames:
                ws = wb_prev["3_REGISTRO_MAESTRO"]
                for r in range(5, ws.max_row + 1):
                    fecha = str(ws.cell(r, 2).value or "")[:10]
                    mon = str(ws.cell(r, 6).value or "").strip().upper()
                    if not fecha or not mon:
                        continue
                    _upsert_evento_unificado(eventos, {
                        "Fecha": fecha,
                        "Hora": ws.cell(r, 5).value,
                        "Moneda": mon,
                        "Semaforo_Ini": ws.cell(r, 7).value,
                        "Semaforo_Max": ws.cell(r, 8).value,
                        "Escalada": ws.cell(r, 9).value,
                        "IA_Pct": _parse_ia_frac(ws.cell(r, 11).value),
                        "Fib_Zona": float(ws.cell(r, 12).value) if isinstance(ws.cell(r, 12).value, (int, float)) else None,
                        "Bids_Asks": _parse_ba_float(ws.cell(r, 13).value),
                        "Precio_Entrada": float(ws.cell(r, 14).value or 0.0) if isinstance(ws.cell(r, 14).value, (int, float)) else 0.0,
                        "Precio_Pico": float(ws.cell(r, 15).value or 0.0) if isinstance(ws.cell(r, 15).value, (int, float)) else 0.0,
                        "Estado": ws.cell(r, 17).value,
                        "Fecha_Ganadora": ws.cell(r, 18).value,
                        "Precio_Final": float(ws.cell(r, 19).value or 0.0) if isinstance(ws.cell(r, 19).value, (int, float)) else 0.0,
                        "Tiempo_Ganadora_Txt": ws.cell(r, 21).value,
                        "Dias_Dec": float(ws.cell(r, 22).value) if isinstance(ws.cell(r, 22).value, (int, float)) else None,
                        "Fib_1618": ws.cell(r, 23).value,
                        "Confluencia": ws.cell(r, 24).value,
                        "Origen": ws.cell(r, 25).value
                    })
            elif "CRUCE_TIEMPOS_GANADORA" in wb_prev.sheetnames:
                ws = wb_prev["CRUCE_TIEMPOS_GANADORA"]
                start_r = 2
                for probe in range(1, 6):
                    if str(ws.cell(probe, 1).value or "").strip().upper() == "MONEDA":
                        start_r = probe + 1
                        break
                for r in range(start_r, ws.max_row + 1):
                    mon = str(ws.cell(r, 1).value or "").strip().upper()
                    ts_raw = str(ws.cell(r, 2).value or "").strip()
                    if not mon or not ts_raw:
                        continue
                    fecha = ts_raw[:10]
                    hora = ts_raw[11:16] if len(ts_raw) >= 16 and "(S/H)" not in ts_raw else "S/H"
                    _upsert_evento_unificado(eventos, {
                        "Fecha": fecha,
                        "Hora": hora,
                        "Moneda": mon,
                        "Semaforo_Ini": ws.cell(r, 3).value,
                        "Semaforo_Max": ws.cell(r, 4).value,
                        "Escalada": ws.cell(r, 5).value,
                        "IA_Pct": _parse_ia_frac(ws.cell(r, 7).value),
                        "Fib_Zona": float(ws.cell(r, 8).value) if isinstance(ws.cell(r, 8).value, (int, float)) else None,
                        "Bids_Asks": _parse_ba_float(ws.cell(r, 9).value),
                        "Precio_Entrada": float(ws.cell(r, 10).value or 0.0) if isinstance(ws.cell(r, 10).value, (int, float)) else 0.0,
                        "Precio_Pico": float(ws.cell(r, 11).value or 0.0) if isinstance(ws.cell(r, 11).value, (int, float)) else 0.0,
                        "Estado": ws.cell(r, 13).value,
                        "Fecha_Ganadora": ws.cell(r, 14).value,
                        "Precio_Final": float(ws.cell(r, 15).value or 0.0) if isinstance(ws.cell(r, 15).value, (int, float)) else 0.0,
                        "Tiempo_Ganadora_Txt": ws.cell(r, 17).value,
                        "Dias_Dec": float(ws.cell(r, 18).value) if isinstance(ws.cell(r, 18).value, (int, float)) else None,
                        "Fib_1618": ws.cell(r, 19).value,
                        "Origen": "Bot Pre-Explosión"
                    })
        except Exception as e:
            print(f"⚠️ Error leyendo {EXCEL_PRE_EXPLOSION_FILE} previo: {e}")

    # 2. Leer señales históricas desde HISTORICO_CAZADOR_TACTICO.xlsx que pasaron a Pre-Exp / Ganadoras
    if os.path.exists(EXCEL_CAZADOR_FILE):
        try:
            wb_caz = openpyxl.load_workbook(EXCEL_CAZADOR_FILE, data_only=True)
            if "3_REGISTRO_MAESTRO" in wb_caz.sheetnames:
                ws_c = wb_caz["3_REGISTRO_MAESTRO"]
                for r in range(5, ws_c.max_row + 1):
                    paso = str(ws_c.cell(r, 25).value or "")
                    if not paso.startswith("SÍ"):
                        continue
                    fecha = str(ws_c.cell(r, 2).value or "")[:10]
                    mon = str(ws_c.cell(r, 6).value or "").strip().upper()
                    if not fecha or not mon:
                        continue
                    etapa_b = str(ws_c.cell(r, 8).value or "")
                    m_ia = re.search(r"(\d+)%", etapa_b)
                    ia_f = round(float(m_ia.group(1)) / 100.0, 4) if m_ia else None
                    p_ini = float(ws_c.cell(r, 9).value or 0.0) if isinstance(ws_c.cell(r, 9).value, (int, float)) else 0.0
                    p_max = float(ws_c.cell(r, 14).value or p_ini) if isinstance(ws_c.cell(r, 14).value, (int, float)) else p_ini
                    res_aud = str(ws_c.cell(r, 24).value or "")
                    is_win = ("Ganadoras" in paso) or ("Ambos" in paso) or ("REBOTE_EXITOSO" in res_aud)
                    t_pico = ws_c.cell(r, 17).value
                    t_pico_f = float(t_pico) if isinstance(t_pico, (int, float)) else None
                    _upsert_evento_unificado(eventos, {
                        "Fecha": fecha,
                        "Hora": ws_c.cell(r, 5).value,
                        "Moneda": mon,
                        "Semaforo_Ini": ws_c.cell(r, 7).value,
                        "IA_Pct": ia_f,
                        "Precio_Entrada": p_ini,
                        "Precio_Pico": max(p_ini, p_max),
                        "Estado": "🏆 GANADORA" if is_win else "⏳ EN SEGUIMIENTO",
                        "Fecha_Ganadora": fecha if is_win else "-",
                        "Precio_Final": p_max if is_win else p_ini,
                        "Tiempo_Ganadora_Txt": f"{int(round(t_pico_f))}h" if (is_win and t_pico_f and t_pico_f > 0) else ("Mismo día" if is_win else "En seguimiento"),
                        "Dias_Dec": round(t_pico_f / 24.0, 2) if (is_win and t_pico_f is not None) else None,
                        "Confluencia": "SÍ (Cazador + Pre-Exp)",
                        "Origen": str(ws_c.cell(r, 26).value or "Histórico Cazador")
                    })
        except Exception as e:
            print(f"⚠️ Error leyendo {EXCEL_CAZADOR_FILE}: {e}")

    # 3. Migrar apariciones_por_dia y registro_cronologico desde historial_perlas.json
    for f_str, bucket in (historial.get("apariciones_por_dia") or {}).items():
        if not isinstance(bucket, dict):
            continue
        for sym, info in bucket.items():
            if not isinstance(info, dict):
                continue
            col = "VERDE"
            if info.get("es_oro"):
                col = "🏆 TOP ORO"
            else:
                col = info.get("color", "VERDE")
            _upsert_evento_unificado(eventos, {
                "Fecha": f_str,
                "Hora": info.get("hora", "S/H"),
                "Moneda": info.get("ticker") or sym,
                "Semaforo_Ini": col,
                "IA_Pct": _parse_ia_frac(info.get("ia_pct")),
                "Fib_Zona": float(info.get("fib_zona")) if info.get("fib_zona") else None,
                "Precio_Entrada": float(info.get("precio") or 0.0),
                "Origen": "Bot Pre-Explosión"
            })


# ==============================================================================
# ASISTENTE IA DEDICADO: PRE-EXPLOSIÓN
# ==============================================================================
def ejecutar_asistente_ia_pre_explosion(eventos, bloques):
    todas = list(eventos.values())
    ganadas = [r for r in todas if r.get("Estado") == "🏆 GANADORA"]
    fechas_unicas = sorted({r["Fecha"] for r in todas if r.get("Fecha")})
    monedas_unicas = {r["Moneda"] for r in todas if r.get("Moneda")}

    dias_all = [
        float(r["Dias_Dec"]) for r in ganadas
        if isinstance(r.get("Dias_Dec"), (int, float)) and float(r["Dias_Dec"]) >= 0
    ]
    med_dias = round(sorted(dias_all)[len(dias_all) // 2], 1) if dias_all else 2.0
    med_horas = round(med_dias * 24.0, 1)
    tasa_global = round((len(ganadas) / len(todas)) * 100, 1) if todas else 0.0

    segmentos = [
        ("TOP_ORO", "🏆 TOP ORO", [r for r in todas if r.get("Semaforo_Ini") == "🏆 TOP ORO"]),
        ("VERDE", "🟢 VERDE", [r for r in todas if r.get("Semaforo_Ini") == "🟢 VERDE"]),
        ("AMARILLO", "🟡 AMARILLO", [r for r in todas if r.get("Semaforo_Ini") == "🟡 AMARILLO"]),
        ("ROJO", "🔴 ROJO", [r for r in todas if r.get("Semaforo_Ini") == "🔴 ROJO"]),
        ("CONFLUENCIA_CAZADOR", "🛡️ CONFLUENCIA CAZADOR+PRE", [r for r in todas if "SÍ" in str(r.get("Confluencia", ""))])
    ]

    stats_segmentos = []
    tasa_por_cat = {}
    horizonte_por_cat = {}
    for cod, nombre, sub in segmentos:
        tot_s = len(sub)
        wins_s = [x for x in sub if x.get("Estado") == "🏆 GANADORA"]
        d_s = [float(x["Dias_Dec"]) for x in wins_s if isinstance(x.get("Dias_Dec"), (int, float))]
        tasa_s = round((len(wins_s) / tot_s) * 100, 1) if tot_s > 0 else 0.0
        med_d_s = round(sorted(d_s)[len(d_s) // 2], 1) if d_s else med_dias
        med_h_s = max(12.0, round(med_d_s * 24.0, 1))

        tasa_por_cat[cod] = tasa_s
        horizonte_por_cat[cod] = med_h_s
        stats_segmentos.append({
            "codigo": cod,
            "categoria": nombre,
            "detectadas": tot_s,
            "ganadoras": len(wins_s),
            "tasa_acierto_pct": tasa_s,
            "demora_mediana_horas": med_h_s,
            "demora_mediana_txt": _formatear_demora(med_h_s)
        })

    activas_eval = []
    vistas = set()
    for cat_key in ("ROJO", "AMARILLO", "VERDE"):
        for it in (bloques.get(cat_key) or []):
            sym = it["symbol"]
            if sym in vistas:
                continue
            vistas.add(sym)
            cod_seg = "TOP_ORO" if (cat_key == "VERDE" and it.get("es_oro")) else cat_key
            tasa_hist = tasa_por_cat.get(cod_seg, tasa_global)
            horiz_h = round(horizonte_por_cat.get(cod_seg, 48.0), 1)
            horiz_dias = round(horiz_h / 24.0, 1)

            fib = it.get("fib_info") or {}
            cert = bool(it.get("certificada_ia"))
            blindaje = int(it.get("blindaje_pct") or 50)

            if cert and cat_key in ("ROJO", "AMARILLO"):
                accion = "COMPRA_CONFIRMADA_MADURACION"
            elif it.get("es_oro"):
                accion = "COMPRA_TEMPRANA_ORO_PACIENCIA"
            elif cert:
                accion = "ACUMULACION_ESCALONADA"
            else:
                accion = "OBSERVACION_ESPERAR_CONFIRMACION"

            nota_default = (
                f"Señal {cod_seg} (blindaje {blindaje}%, efectividad hist. {tasa_hist}%); "
                f"horizonte típico de maduración {horiz_dias}d ({_formatear_demora(horiz_h)})."
            )

            activas_eval.append({
                "symbol": sym,
                "ticker": it["ticker"],
                "semaforo": cod_seg,
                "certificada_ia": cert,
                "blindaje_pct": blindaje,
                "precio_actual": it.get("precio_f", 0.0),
                "cambio_1h_pct": it.get("cambio_1h", 0.0),
                "cambio_4h_pct": it.get("cambio_4h", 0.0),
                "cambio_24h_pct": it.get("cambio_f", 0.0),
                "vol_1h_rel": it.get("vol_1h_rel", 1.0),
                "ratio_bids_asks": it.get("ratio_bids_asks", 1.0),
                "fib_etiqueta": fib.get("etiqueta_fib", "N/D") if fib.get("ok") else "N/D",
                "ext_1618": round(float(fib.get("ext_1618") or 0.0), 8) if fib.get("ok") else 0.0,
                "tasa_conversion_hist_pct": tasa_hist,
                "horizonte_maduracion_horas": horiz_h,
                "horizonte_maduracion_dias": horiz_dias,
                "accion_matriz": accion,
                "dictamen_ia": nota_default
            })

    f_ini = fechas_unicas[0] if fechas_unicas else "-"
    f_fin = fechas_unicas[-1] if fechas_unicas else "-"
    diagnostico_global = (
        f"Universo unificado de {len(todas)} señales ({len(monedas_unicas)} monedas únicas desde {f_ini} al {f_fin} • "
        f"conversión real a Ganadora: {tasa_global}%). Ventana típica de maduración: {_formatear_demora(med_horas)} ({med_dias}d)."
    )

    if GEMINI_API_KEY and activas_eval:
        try:
            client = genai.Client(api_key=GEMINI_API_KEY)
            res_act = "\n".join([
                f"- {a['ticker']} ({a['semaforo']}, blindaje {a['blindaje_pct']}%, cert={a['certificada_ia']}): 1h {a['cambio_1h_pct']:+.1f}%, 24h {a['cambio_24h_pct']:+.1f}%, OB {a['ratio_bids_asks']}x, {a['fib_etiqueta']}"
                for a in activas_eval[:12]
            ])
            prompt = (
                "Sos el Asistente IA de la etapa PRE-EXPLOSIÓN en Binance Spot. "
                "Analizá las candidatas activas de hoy y devolvé SOLO JSON válido:\n"
                '{"dictamenes":{"TICKER":"recomendación táctica concreta de 1 línea con horizonte de espera"}}\n\n'
                f"Candidatas activas:\n{res_act}"
            )
            for mod in MODELOS_GEMINI_PRE:
                try:
                    resp = client.models.generate_content(model=mod, contents=prompt)
                    if resp and resp.text:
                        raw = re.sub(r'^```(?:json)?\s*|\s*```$', '', resp.text.strip()).strip()
                        parsed = json.loads(raw)
                        d_map = parsed.get("dictamenes") or {}
                        for a in activas_eval:
                            if a["ticker"] in d_map:
                                a["dictamen_ia"] = str(d_map[a["ticker"]]).strip()
                        break
                except Exception:
                    continue
        except Exception as e:
            print(f"⚠️ Fallback Asistente IA Pre-Explosión: {e}")

    reporte_json = {
        "etapa": "PRE_EXPLOSION",
        "actualizado_art": ahora_art().strftime('%Y-%m-%d %H:%M:%S ART'),
        "total_senales_historicas": len(todas),
        "total_monedas_historicas": len(monedas_unicas),
        "dias_registrados": len(fechas_unicas),
        "total_ganadoras_confirmadas": len(ganadas),
        "tasa_conversion_global_pct": tasa_global,
        "demora_mediana_horas": med_horas,
        "horizonte_tipico_dias": med_dias,
        "diagnostico_global": diagnostico_global,
        "efectividad_por_semaforo": stats_segmentos,
        "candidatas_activas_evaluadas": activas_eval
    }

    try:
        with open(REPORTE_IA_PRE_EXPLOSION_FILE, 'w', encoding='utf-8') as f:
            json.dump(reporte_json, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"⚠️ Error guardando {REPORTE_IA_PRE_EXPLOSION_FILE}: {e}")

    return reporte_json


# ==============================================================================
# GENERADOR EXCEL EJECUTIVO DE 5 PESTAÑAS (ESTRUCTURA MAESTRA UNIFICADA)
# ==============================================================================
def _generar_excel_pre_explosion(eventos, mapa_tickers, reporte_ia):
    wb = openpyxl.Workbook()
    wb.remove(wb.active)

    fill_navy = PatternFill(start_color="0F172A", end_color="0F172A", fill_type="solid")
    fill_slate_hdr = PatternFill(start_color="1E293B", end_color="1E293B", fill_type="solid")
    fill_subhdr = PatternFill(start_color="F1F5F9", end_color="F1F5F9", fill_type="solid")
    fill_sec_hdr = PatternFill(start_color="E2E8F0", end_color="E2E8F0", fill_type="solid")
    fill_zebra = PatternFill(start_color="F8FAFC", end_color="F8FAFC", fill_type="solid")
    fill_green = PatternFill(start_color="DCFCE7", end_color="DCFCE7", fill_type="solid")
    fill_amber = PatternFill(start_color="FEF9C3", end_color="FEF9C3", fill_type="solid")
    fill_red = PatternFill(start_color="FEE2E2", end_color="FEE2E2", fill_type="solid")
    fill_blue = PatternFill(start_color="DBEAFE", end_color="DBEAFE", fill_type="solid")
    fill_gold = PatternFill(start_color="FEF3C7", end_color="FEF3C7", fill_type="solid")

    thin_side = Side(style="thin", color="CBD5E1")
    borde = Border(left=thin_side, right=thin_side, top=thin_side, bottom=thin_side)
    sem_fills = {
        "🔴 ROJO": fill_red,
        "🟡 AMARILLO": fill_amber,
        "🟢 VERDE": fill_green,
        "🏆 TOP ORO": fill_gold
    }

    filas_ord = sorted(eventos.values(), key=lambda x: (x.get("Fecha", ""), x.get("Hora", ""), x.get("Moneda", "")))
    N_ROWS = max(1, len(filas_ord))
    END_ROW = 4 + len(filas_ord)

    fechas_ord = sorted({r["Fecha"] for r in filas_ord if r.get("Fecha")})
    periodos_ord = sorted({r["Fecha"][:7] for r in filas_ord if len(r.get("Fecha", "")) >= 7})
    if not periodos_ord:
        periodos_ord = [ahora_art().strftime("%Y-%m")]
    mes_actual_cod = periodos_ord[-1]

    try:
        f_ini_fmt = datetime.strptime(fechas_ord[0], "%Y-%m-%d").strftime("%d/%m/%Y") if fechas_ord else "-"
        f_fin_fmt = datetime.strptime(fechas_ord[-1], "%Y-%m-%d").strftime("%d/%m/%Y") if fechas_ord else "-"
    except Exception:
        f_ini_fmt = fechas_ord[0] if fechas_ord else "-"
        f_fin_fmt = fechas_ord[-1] if fechas_ord else "-"

    # Estadística por moneda única para 4_RANKING_MONEDAS
    coin_agg = {}
    for r in filas_ord:
        m = r["Moneda"]
        st = coin_agg.setdefault(m, {"rep": 0, "wins": 0, "best_up": 0.0})
        st["rep"] += 1
        if r.get("Estado") == "🏆 GANADORA":
            st["wins"] += 1
        p0 = float(r.get("Precio_Entrada") or 0.0)
        p1 = float(r.get("Precio_Pico") or 0.0)
        if p0 > 0 and p1 > 0:
            st["best_up"] = max(st["best_up"], (p1 - p0) / p0)

    coin_stats = sorted(coin_agg.items(), key=lambda kv: (-kv[1]["rep"], -kv[1]["wins"], -kv[1]["best_up"], kv[0]))
    N_COINS = len(coin_stats)
    END_COIN_ROW = 4 + max(1, N_COINS)

    # --------------------------------------------------------------------------
    # PESTAÑA 1: 1_RESUMEN_MENSUAL_IA
    # --------------------------------------------------------------------------
    ws1 = wb.create_sheet("1_RESUMEN_MENSUAL_IA")
    ws1.views.sheetView[0].showGridLines = True

    ws1["A1"] = "PRE-EXPLOSIÓN • PANEL EJECUTIVO & RESUMEN MENSUAL IA (DATOS UNIFICADOS REALES)"
    ws1["A1"].font = Font(name="Arial", size=12, bold=True, color="FFFFFF")
    ws1["A1"].fill = fill_navy
    ws1.merge_cells("A1:P1")
    ws1.row_dimensions[1].height = 28

    ws1["A2"] = (
        f"Consolidación automática de '3_REGISTRO_MAESTRO' ({len(filas_ord):,} señales históricas • {f_ini_fmt} al {f_fin_fmt} • {N_COINS} monedas únicas). "
        "Cambiá el período en B4 para inspeccionar cualquier mes o el acumulado total."
    ).replace(",", ".")
    ws1["A2"].font = Font(name="Arial", size=9.5, italic=True, color="334155")
    ws1["A2"].fill = fill_subhdr
    ws1.merge_cells("A2:P2")
    ws1.row_dimensions[2].height = 20

    ws1["A4"] = "MES SELECCIONADO:"
    ws1["A4"].font = Font(name="Arial", size=10, bold=True, color="0F172A")
    ws1["B4"] = mes_actual_cod
    ws1["B4"].font = Font(name="Arial", size=11, bold=True, color="0F172A")
    ws1["B4"].fill = fill_gold
    ws1["B4"].alignment = Alignment(horizontal="center", vertical="center")
    ws1["B4"].border = borde
    ws1["C4"] = f"◄ Seleccioná el período en B4 ({', '.join(periodos_ord + ['TODOS'])}) para actualizar dinámicamente las tarjetas KPI y el desglose por semáforo."
    ws1["C4"].font = Font(name="Arial", size=9, italic=True, color="475569")
    ws1.merge_cells("C4:P4")
    ws1.row_dimensions[4].height = 22

    opciones_dv = ",".join(periodos_ord + ["TODOS"])
    dv_mes = DataValidation(type="list", formula1=f'"{opciones_dv}"', allow_blank=False)
    ws1.add_data_validation(dv_mes)
    dv_mes.add(ws1["B4"])

    kpis = [
        ("A", "B", "SEÑALES DEL PERÍODO",
         f'=IF($B$4="TODOS",COUNTA(\'3_REGISTRO_MAESTRO\'!$F$5:$F${END_ROW}),COUNTIF(\'3_REGISTRO_MAESTRO\'!$C$5:$C${END_ROW},$B$4))',
         "#,##0", fill_subhdr),
        ("C", "D", "GANADORAS CONFIRMADAS",
         f'=IF($B$4="TODOS",COUNTIF(\'3_REGISTRO_MAESTRO\'!$Q$5:$Q${END_ROW},"🏆 GANADORA"),COUNTIFS(\'3_REGISTRO_MAESTRO\'!$C$5:$C${END_ROW},$B$4,\'3_REGISTRO_MAESTRO\'!$Q$5:$Q${END_ROW},"🏆 GANADORA"))',
         "#,##0", fill_blue),
        ("E", "F", "CONVERSIÓN A GANADORA (%)",
         '=IF(A7>0,C7/A7,0)',
         "0.0%", fill_green),
        ("G", "H", "SUBIDA PICO PROM. (%)",
         f'=IFERROR(IF($B$4="TODOS",AVERAGEIF(\'3_REGISTRO_MAESTRO\'!$P$5:$P${END_ROW},">0"),AVERAGEIFS(\'3_REGISTRO_MAESTRO\'!$P$5:$P${END_ROW},\'3_REGISTRO_MAESTRO\'!$C$5:$C${END_ROW},$B$4,\'3_REGISTRO_MAESTRO\'!$P$5:$P${END_ROW},">0")),0)',
         "+0.0%;-0.0%;0.0%", fill_green),
        ("I", "J", "TIEMPO MEDIO GANADORA (DÍAS)",
         f'=IFERROR(IF($B$4="TODOS",AVERAGEIFS(\'3_REGISTRO_MAESTRO\'!$V$5:$V${END_ROW},\'3_REGISTRO_MAESTRO\'!$Q$5:$Q${END_ROW},"🏆 GANADORA"),AVERAGEIFS(\'3_REGISTRO_MAESTRO\'!$V$5:$V${END_ROW},\'3_REGISTRO_MAESTRO\'!$C$5:$C${END_ROW},$B$4,\'3_REGISTRO_MAESTRO\'!$Q$5:$Q${END_ROW},"🏆 GANADORA")),0)',
         "0.00", fill_amber),
        ("K", "L", "CONFLUENCIA CAZADOR+PRE",
         f'=IF($B$4="TODOS",COUNTIF(\'3_REGISTRO_MAESTRO\'!$X$5:$X${END_ROW},"SÍ*"),COUNTIFS(\'3_REGISTRO_MAESTRO\'!$C$5:$C${END_ROW},$B$4,\'3_REGISTRO_MAESTRO\'!$X$5:$X${END_ROW},"SÍ*"))',
         "#,##0", fill_subhdr),
    ]

    ws1.row_dimensions[6].height = 20
    ws1.row_dimensions[7].height = 28
    for c_start, c_end, title_kpi, formula_kpi, num_fmt, fl in kpis:
        ws1[f"{c_start}6"] = title_kpi
        ws1[f"{c_start}6"].font = Font(name="Arial", size=8.5, bold=True, color="FFFFFF")
        ws1[f"{c_start}6"].fill = fill_slate_hdr
        ws1[f"{c_start}6"].alignment = Alignment(horizontal="center", vertical="center")
        ws1.merge_cells(f"{c_start}6:{c_end}6")

        ws1[f"{c_start}7"] = formula_kpi
        ws1[f"{c_start}7"].font = Font(name="Arial", size=14, bold=True, color="0F172A")
        ws1[f"{c_start}7"].fill = fl
        ws1[f"{c_start}7"].alignment = Alignment(horizontal="center", vertical="center")
        ws1[f"{c_start}7"].number_format = num_fmt
        ws1.merge_cells(f"{c_start}7:{c_end}7")
        for cc in (c_start, c_end):
            ws1[f"{cc}6"].border = borde
            ws1[f"{cc}7"].border = borde

    ws1["A9"] = "1. DESGLOSE DINÁMICO POR SEMÁFORO DE ENTRADA (SEGÚN MES SELECCIONADO EN B4)"
    ws1["A9"].font = Font(name="Arial", size=10, bold=True, color="0F172A")
    ws1["A9"].fill = fill_sec_hdr
    ws1.merge_cells("A9:H9")
    ws1.row_dimensions[9].height = 22

    hdrs_t1 = ["Semáforo Inicial", "Señales Detectadas", "Ganadoras", "En Seguimiento", "Conversión %", "Subida Pico Prom.", "Var. Real Cierre", "Tiempo Prom. (d)"]
    ws1.row_dimensions[10].height = 24
    for idx, h in enumerate(hdrs_t1, start=1):
        c = ws1.cell(10, idx, h)
        c.font = Font(name="Arial", size=9, bold=True, color="FFFFFF")
        c.fill = fill_slate_hdr
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        c.border = borde

    sems_list = [
        ("🔴 ROJO", fill_red),
        ("🟡 AMARILLO", fill_amber),
        ("🟢 VERDE", fill_green),
        ("🏆 TOP ORO", fill_gold),
    ]
    for offset, (sem_lbl, sem_fill) in enumerate(sems_list):
        r_num = 11 + offset
        ws1.row_dimensions[r_num].height = 21
        ws1.cell(r_num, 1, sem_lbl).fill = sem_fill
        ws1.cell(r_num, 1).font = Font(name="Arial", size=9.5, bold=True)
        ws1.cell(r_num, 1).alignment = Alignment(horizontal="left", vertical="center")

        ws1.cell(r_num, 2, f'=IF($B$4="TODOS",COUNTIF(\'3_REGISTRO_MAESTRO\'!$G$5:$G${END_ROW},$A{r_num}),COUNTIFS(\'3_REGISTRO_MAESTRO\'!$C$5:$C${END_ROW},$B$4,\'3_REGISTRO_MAESTRO\'!$G$5:$G${END_ROW},$A{r_num}))')
        ws1.cell(r_num, 3, f'=IF($B$4="TODOS",COUNTIFS(\'3_REGISTRO_MAESTRO\'!$G$5:$G${END_ROW},$A{r_num},\'3_REGISTRO_MAESTRO\'!$Q$5:$Q${END_ROW},"🏆 GANADORA"),COUNTIFS(\'3_REGISTRO_MAESTRO\'!$C$5:$C${END_ROW},$B$4,\'3_REGISTRO_MAESTRO\'!$G$5:$G${END_ROW},$A{r_num},\'3_REGISTRO_MAESTRO\'!$Q$5:$Q${END_ROW},"🏆 GANADORA"))')
        ws1.cell(r_num, 4, f'=B{r_num}-C{r_num}')
        ws1.cell(r_num, 5, f'=IF(B{r_num}>0,C{r_num}/B{r_num},0)')
        ws1.cell(r_num, 6, f'=IFERROR(IF($B$4="TODOS",AVERAGEIFS(\'3_REGISTRO_MAESTRO\'!$P$5:$P${END_ROW},\'3_REGISTRO_MAESTRO\'!$G$5:$G${END_ROW},$A{r_num},\'3_REGISTRO_MAESTRO\'!$P$5:$P${END_ROW},">0"),AVERAGEIFS(\'3_REGISTRO_MAESTRO\'!$P$5:$P${END_ROW},\'3_REGISTRO_MAESTRO\'!$C$5:$C${END_ROW},$B$4,\'3_REGISTRO_MAESTRO\'!$G$5:$G${END_ROW},$A{r_num},\'3_REGISTRO_MAESTRO\'!$P$5:$P${END_ROW},">0")),0)')
        ws1.cell(r_num, 7, f'=IFERROR(IF($B$4="TODOS",AVERAGEIFS(\'3_REGISTRO_MAESTRO\'!$T$5:$T${END_ROW},\'3_REGISTRO_MAESTRO\'!$G$5:$G${END_ROW},$A{r_num},\'3_REGISTRO_MAESTRO\'!$Q$5:$Q${END_ROW},"🏆 GANADORA"),AVERAGEIFS(\'3_REGISTRO_MAESTRO\'!$T$5:$T${END_ROW},\'3_REGISTRO_MAESTRO\'!$C$5:$C${END_ROW},$B$4,\'3_REGISTRO_MAESTRO\'!$G$5:$G${END_ROW},$A{r_num},\'3_REGISTRO_MAESTRO\'!$Q$5:$Q${END_ROW},"🏆 GANADORA")),0)')
        ws1.cell(r_num, 8, f'=IFERROR(IF($B$4="TODOS",AVERAGEIFS(\'3_REGISTRO_MAESTRO\'!$V$5:$V${END_ROW},\'3_REGISTRO_MAESTRO\'!$G$5:$G${END_ROW},$A{r_num},\'3_REGISTRO_MAESTRO\'!$Q$5:$Q${END_ROW},"🏆 GANADORA"),AVERAGEIFS(\'3_REGISTRO_MAESTRO\'!$V$5:$V${END_ROW},\'3_REGISTRO_MAESTRO\'!$C$5:$C${END_ROW},$B$4,\'3_REGISTRO_MAESTRO\'!$G$5:$G${END_ROW},$A{r_num},\'3_REGISTRO_MAESTRO\'!$Q$5:$Q${END_ROW},"🏆 GANADORA")),0)')

        for ci in range(1, 9):
            cell = ws1.cell(r_num, ci)
            cell.border = borde
            if ci > 1:
                cell.font = Font(name="Arial", size=9.5)
                cell.alignment = Alignment(horizontal="center", vertical="center")
            if ci in (2, 3, 4):
                cell.number_format = "#,##0"
            elif ci == 5:
                cell.number_format = "0.0%"
            elif ci in (6, 7):
                cell.number_format = "+0.0%;-0.0%;0.0%"
            elif ci == 8:
                cell.number_format = "0.00"

    ws1.row_dimensions[15].height = 22
    ws1.cell(15, 1, "TOTAL PERÍODO").font = Font(name="Arial", size=9.5, bold=True)
    ws1.cell(15, 2, "=SUM(B11:B14)").number_format = "#,##0"
    ws1.cell(15, 3, "=SUM(C11:C14)").number_format = "#,##0"
    ws1.cell(15, 4, "=SUM(D11:D14)").number_format = "#,##0"
    ws1.cell(15, 5, "=IF(B15>0,C15/B15,0)").number_format = "0.0%"
    ws1.cell(15, 6, "=AVERAGE(F11:F13)").number_format = "+0.0%;-0.0%;0.0%"
    ws1.cell(15, 7, "=AVERAGE(G11:G13)").number_format = "+0.0%;-0.0%;0.0%"
    ws1.cell(15, 8, "=AVERAGE(H11:H13)").number_format = "0.00"
    for ci in range(1, 9):
        c = ws1.cell(15, ci)
        c.font = Font(name="Arial", size=9.5, bold=True)
        c.fill = fill_subhdr
        c.border = borde
        if ci > 1:
            c.alignment = Alignment(horizontal="center", vertical="center")

    ws1["A17"] = f"2. EVOLUCIÓN MENSUAL COMPARATIVA ({f_ini_fmt} AL {f_fin_fmt} • DESDE EL INICIO)"
    ws1["A17"].font = Font(name="Arial", size=10, bold=True, color="0F172A")
    ws1["A17"].fill = fill_sec_hdr
    ws1.merge_cells("A17:H17")
    ws1.row_dimensions[17].height = 22

    hdrs_t2 = ["Período", "Nombre Mes", "Señales Totales", "Ganadoras", "Conversión %", "Subida Pico Prom.", "Confluencia Cazador", "Tiempo Prom. (d)"]
    ws1.row_dimensions[18].height = 24
    for idx, h in enumerate(hdrs_t2, start=1):
        c = ws1.cell(18, idx, h)
        c.font = Font(name="Arial", size=9, bold=True, color="FFFFFF")
        c.fill = fill_slate_hdr
        c.alignment = Alignment(horizontal="center", vertical="center")
        c.border = borde

    for idx_m, per_cod in enumerate(periodos_ord):
        rn = 19 + idx_m
        ws1.row_dimensions[rn].height = 21
        try:
            anio_m, mes_m = per_cod.split("-")
            per_nom = f"{MESES_ES.get(int(mes_m), per_cod)} {anio_m}"
        except Exception:
            per_nom = per_cod
        ws1.cell(rn, 1, per_cod)
        ws1.cell(rn, 2, per_nom)
        ws1.cell(rn, 3, f'=COUNTIF(\'3_REGISTRO_MAESTRO\'!$C$5:$C${END_ROW},$A{rn})')
        ws1.cell(rn, 4, f'=COUNTIFS(\'3_REGISTRO_MAESTRO\'!$C$5:$C${END_ROW},$A{rn},\'3_REGISTRO_MAESTRO\'!$Q$5:$Q${END_ROW},"🏆 GANADORA")')
        ws1.cell(rn, 5, f'=IF(C{rn}>0,D{rn}/C{rn},0)')
        ws1.cell(rn, 6, f'=IFERROR(AVERAGEIFS(\'3_REGISTRO_MAESTRO\'!$P$5:$P${END_ROW},\'3_REGISTRO_MAESTRO\'!$C$5:$C${END_ROW},$A{rn},\'3_REGISTRO_MAESTRO\'!$P$5:$P${END_ROW},">0"),0)')
        ws1.cell(rn, 7, f'=COUNTIFS(\'3_REGISTRO_MAESTRO\'!$C$5:$C${END_ROW},$A{rn},\'3_REGISTRO_MAESTRO\'!$X$5:$X${END_ROW},"SÍ*")')
        ws1.cell(rn, 8, f'=IFERROR(AVERAGEIFS(\'3_REGISTRO_MAESTRO\'!$V$5:$V${END_ROW},\'3_REGISTRO_MAESTRO\'!$C$5:$C${END_ROW},$A{rn},\'3_REGISTRO_MAESTRO\'!$Q$5:$Q${END_ROW},"🏆 GANADORA"),0)')
        for ci in range(1, 9):
            c = ws1.cell(rn, ci)
            c.border = borde
            c.font = Font(name="Arial", size=9.5, bold=(ci == 1))
            c.alignment = Alignment(horizontal="left" if ci == 2 else "center", vertical="center")
            if ci in (3, 4, 7):
                c.number_format = "#,##0"
            elif ci == 5:
                c.number_format = "0.0%"
            elif ci == 6:
                c.number_format = "+0.0%;-0.0%;0.0%"
            elif ci == 8:
                c.number_format = "0.00"

    r_tot_m = 19 + len(periodos_ord)
    ws1.row_dimensions[r_tot_m].height = 22
    ws1.cell(r_tot_m, 1, "ACUMULADO")
    ws1.cell(r_tot_m, 2, "Total Histórico Unificado")
    ws1.cell(r_tot_m, 3, f"=SUM(C19:C{r_tot_m - 1})").number_format = "#,##0"
    ws1.cell(r_tot_m, 4, f"=SUM(D19:D{r_tot_m - 1})").number_format = "#,##0"
    ws1.cell(r_tot_m, 5, f"=IF(C{r_tot_m}>0,D{r_tot_m}/C{r_tot_m},0)").number_format = "0.0%"
    ws1.cell(r_tot_m, 6, f"=AVERAGE(F19:F{r_tot_m - 1})").number_format = "+0.0%;-0.0%;0.0%"
    ws1.cell(r_tot_m, 7, f"=SUM(G19:G{r_tot_m - 1})").number_format = "#,##0"
    ws1.cell(r_tot_m, 8, f"=AVERAGE(H19:H{r_tot_m - 1})").number_format = "0.00"
    for ci in range(1, 9):
        c = ws1.cell(r_tot_m, ci)
        c.font = Font(name="Arial", size=9.5, bold=True)
        c.fill = fill_subhdr
        c.border = borde
        c.alignment = Alignment(horizontal="left" if ci == 2 else "center", vertical="center")

    chart = BarChart()
    chart.type = "col"
    chart.style = 10
    chart.grouping = "clustered"
    chart.title = "Señales Detectadas vs. Ganadoras por Semáforo"
    chart.y_axis.title = "Cantidad"
    chart.x_axis.title = "Semáforo"
    data_ref = Reference(ws1, min_col=2, max_col=3, min_row=10, max_row=14)
    cats_ref = Reference(ws1, min_col=1, min_row=11, max_row=14)
    chart.add_data(data_ref, titles_from_data=True)
    chart.set_categories(cats_ref)
    chart.width = 16
    chart.height = 10
    ws1.add_chart(chart, "J9")

    col_widths_ws1 = [18, 22, 16, 16, 15, 18, 18, 17, 4, 14, 14, 14, 14, 14, 14, 14]
    for idx, w in enumerate(col_widths_ws1, start=1):
        ws1.column_dimensions[get_column_letter(idx)].width = w

    # --------------------------------------------------------------------------
    # PESTAÑA 2: 2_RADAR_ACTIVO_IA
    # --------------------------------------------------------------------------
    ws2 = wb.create_sheet("2_RADAR_ACTIVO_IA")
    ws2.views.sheetView[0].showGridLines = True

    ws2["A1"] = "ASISTENTE IA • ETAPA PRE-EXPLOSIÓN (MADURACIÓN REAL, CONVERSIÓN A GANADORA Y CANDIDATAS ACTIVAS)"
    ws2["A1"].font = Font(name="Arial", size=12, bold=True, color="FFFFFF")
    ws2["A1"].fill = fill_navy
    ws2.merge_cells("A1:K1")
    ws2.row_dimensions[1].height = 28

    ws2["A2"] = f"Diagnóstico Global IA ({reporte_ia.get('actualizado_art', '')}): {reporte_ia.get('diagnostico_global', '')}"
    ws2["A2"].font = Font(name="Arial", size=9.5, bold=True, color="0F172A")
    ws2["A2"].fill = fill_gold
    ws2["A2"].alignment = Alignment(wrap_text=True, vertical="center")
    ws2.merge_cells("A2:K2")
    ws2.row_dimensions[2].height = 34

    hdrs_ws2 = [
        "MONEDA", "SEMÁFORO", "CERTIFICADA IA", "BLINDAJE %", "PRECIO ACTUAL",
        "EFECTIVIDAD HIST %", "HORIZONTE MADURACIÓN", "FIBONACCI", "BIDS/ASKS",
        "ACCIÓN MATRIZ", "DICTAMEN ASISTENTE IA"
    ]
    ws2.row_dimensions[4].height = 25
    for ci, h in enumerate(hdrs_ws2, start=1):
        c = ws2.cell(4, ci, h)
        c.font = Font(name="Arial", size=9.5, bold=True, color="FFFFFF")
        c.fill = fill_slate_hdr
        c.alignment = Alignment(horizontal="center", vertical="center")
        c.border = borde

    for idx_r, a in enumerate(reporte_ia.get("candidatas_activas_evaluadas", [])):
        rn = 5 + idx_r
        ws2.row_dimensions[rn].height = 23
        is_cert = bool(a.get("certificada_ia"))
        vals = [
            a["ticker"],
            a["semaforo"],
            "🛡️ SÍ" if is_cert else "⏳ NO",
            round(float(a.get("blindaje_pct", 0)) / 100.0, 4),
            float(a.get("precio_actual", 0.0)),
            round(float(a.get("tasa_conversion_hist_pct", 0)) / 100.0, 4),
            f"{a['horizonte_maduracion_dias']}d ({_formatear_demora(a['horizonte_maduracion_horas'])})",
            a.get("fib_etiqueta", "N/D"),
            f"{a.get('ratio_bids_asks', 1.0)}x",
            a.get("accion_matriz", ""),
            a.get("dictamen_ia", "")
        ]
        for ci, val in enumerate(vals, start=1):
            c = ws2.cell(rn, ci, val)
            c.border = borde
            c.font = Font(name="Arial", size=9.5, bold=is_cert)
            c.alignment = Alignment(horizontal="left" if ci in (10, 11) else "center", vertical="center")
            if ci in (4, 6):
                c.number_format = "0.0%"
            c.fill = fill_green if is_cert else fill_amber

    widths_ws2 = [12, 14, 15, 12, 14, 17, 21, 22, 12, 30, 58]
    for i, w in enumerate(widths_ws2, start=1):
        ws2.column_dimensions[get_column_letter(i)].width = w

    # --------------------------------------------------------------------------
    # PESTAÑA 3: 3_REGISTRO_MAESTRO
    # --------------------------------------------------------------------------
    ws3 = wb.create_sheet("3_REGISTRO_MAESTRO")
    ws3.views.sheetView[0].showGridLines = True

    ws3["A1"] = "PRE-EXPLOSIÓN • REGISTRO MAESTRO UNIFICADO (HISTÓRICO CAZADOR + BOT PRE-EXPLOSIÓN + GANADORAS)"
    ws3["A1"].font = Font(name="Arial", size=12, bold=True, color="FFFFFF")
    ws3["A1"].fill = fill_navy
    ws3.merge_cells("A1:Y1")
    ws3.row_dimensions[1].height = 28

    ws3["A2"] = (
        f"Base única consolidada y deduplicada ({f_ini_fmt} al {f_fin_fmt} • {len(filas_ord):,} registros • {N_COINS} monedas únicas). "
        "Ordenada cronológicamente desde el inicio con fórmulas dinámicas."
    ).replace(",", ".")
    ws3["A2"].font = Font(name="Arial", size=9.5, italic=True, color="334155")
    ws3["A2"].fill = fill_subhdr
    ws3.merge_cells("A2:Y2")
    ws3.row_dimensions[2].height = 20

    headers_ws3 = [
        "ID", "Fecha", "Período (AAAA-MM)", "Nombre Mes", "Hora", "Moneda",
        "Semáforo Inicial", "Semáforo Máx", "Escalada Semáforo", "Veces Vista",
        "IA Máx %", "Fib Zona", "Bids/Asks", "$ Entrada", "$ Pico Máx",
        "Subida Pico %", "Estado", "Fecha Ganadora", "$ Ganadora / Actual",
        "Var. Real %", "Tiempo hasta Ganadora", "Días Dec.", "Fib 1.618",
        "Confluencia Cazador", "Origen Dato"
    ]
    ws3.row_dimensions[4].height = 28
    for ci, h in enumerate(headers_ws3, start=1):
        c = ws3.cell(4, ci, h)
        c.font = Font(name="Arial", size=9, bold=True, color="FFFFFF")
        c.fill = fill_slate_hdr
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        c.border = borde

    for idx, row in enumerate(filas_ord):
        rn = 5 + idx
        ws3.row_dimensions[rn].height = 20
        is_win = (row.get("Estado") == "🏆 GANADORA")
        sym = _normalizar_symbol(row["Moneda"])
        p_live = float(mapa_tickers.get(sym, {}).get("lastPrice", 0) or 0.0)
        p_ent = float(row.get("Precio_Entrada") or 0.0)
        p_pico = max(float(row.get("Precio_Pico") or 0.0), p_ent, p_live)
        p_fin = float(row.get("Precio_Final") or 0.0) if is_win else (p_live if p_live > 0 else float(row.get("Precio_Final") or p_ent))

        vals = [
            idx + 1,
            row["Fecha"],
            f"=LEFT(B{rn},7)",
            f'=C{rn}&" • "&CHOOSE(VALUE(RIGHT(C{rn},2)),"Enero","Febrero","Marzo","Abril","Mayo","Junio","Julio","Agosto","Septiembre","Octubre","Noviembre","Diciembre")',
            row.get("Hora", "S/H"),
            row["Moneda"],
            row.get("Semaforo_Ini", "🟢 VERDE"),
            row.get("Semaforo_Max", "🟢 VERDE"),
            row.get("Escalada", "-"),
            f"=COUNTIF($F$5:$F${END_ROW},F{rn})",
            row["IA_Pct"] if isinstance(row.get("IA_Pct"), (int, float)) else "-",
            row["Fib_Zona"] if isinstance(row.get("Fib_Zona"), (int, float)) else "-",
            row["Bids_Asks"] if isinstance(row.get("Bids_Asks"), (int, float)) else "-",
            p_ent,
            p_pico,
            f"=IF(AND(N{rn}>0,O{rn}>0),(O{rn}-N{rn})/N{rn},0)",
            row.get("Estado", "⏳ EN SEGUIMIENTO"),
            row.get("Fecha_Ganadora", "-"),
            p_fin,
            f"=IF(AND(N{rn}>0,S{rn}>0),(S{rn}-N{rn})/N{rn},0)",
            row.get("Tiempo_Ganadora_Txt", "En seguimiento"),
            float(row["Dias_Dec"]) if isinstance(row.get("Dias_Dec"), (int, float)) else "-",
            row.get("Fib_1618", "-"),
            row.get("Confluencia", "Solo Pre-Explosión"),
            row.get("Origen", "Bot Pre-Explosión")
        ]

        for ci, val in enumerate(vals, start=1):
            c = ws3.cell(rn, ci, val)
            c.border = borde
            c.font = Font(name="Arial", size=9, bold=(is_win or ci == 6))
            c.alignment = Alignment(
                horizontal="left" if ci in (4, 24, 25) else ("right" if ci in (14, 15, 19) else "center"),
                vertical="center"
            )
            if ci == 11 and isinstance(val, (int, float)):
                c.number_format = "0%"
            elif ci == 12 and isinstance(val, (int, float)):
                c.number_format = "0.00"
            elif ci == 13 and isinstance(val, (int, float)):
                c.number_format = '0.00"x"'
            elif ci in (16, 20):
                c.number_format = "+0.00%;-0.00%;0.00%"
            elif ci == 22 and isinstance(val, (int, float)):
                c.number_format = "0.00"

            if ci in (7, 8):
                c.fill = sem_fills.get(str(val), fill_green)
            elif is_win:
                c.fill = fill_blue
            elif idx % 2 == 1:
                c.fill = fill_zebra

    ws3.freeze_panes = "A5"
    ws3.auto_filter.ref = f"A4:Y{END_ROW}"

    widths_ws3 = [7, 13, 16, 20, 9, 12, 16, 16, 16, 12, 10, 10, 11, 13, 13, 14, 18, 17, 16, 13, 21, 11, 10, 22, 23]
    for i, w in enumerate(widths_ws3, start=1):
        ws3.column_dimensions[get_column_letter(i)].width = w

    # --------------------------------------------------------------------------
    # PESTAÑA 4: 4_RANKING_MONEDAS
    # --------------------------------------------------------------------------
    ws4 = wb.create_sheet("4_RANKING_MONEDAS")
    ws4.views.sheetView[0].showGridLines = True

    ws4["A1"] = f"PRE-EXPLOSIÓN • RANKING MAESTRO DE MONEDAS ÚNICAS ({f_ini_fmt} AL {f_fin_fmt})"
    ws4["A1"].font = Font(name="Arial", size=12, bold=True, color="FFFFFF")
    ws4["A1"].fill = fill_navy
    ws4.merge_cells("A1:P1")
    ws4.row_dimensions[1].height = 28

    ws4["A2"] = (
        f"Métricas 100% dinámicas vinculadas a '3_REGISTRO_MAESTRO' ({N_COINS} monedas únicas). "
        "Ordenadas por recurrencia histórica y ganadoras confirmadas para identificar los mejores runners."
    )
    ws4["A2"].font = Font(name="Arial", size=9.5, italic=True, color="334155")
    ws4["A2"].fill = fill_subhdr
    ws4.merge_cells("A2:P2")
    ws4.row_dimensions[2].height = 20

    hdrs_ws4 = [
        "N°", "Moneda", "Rep. Históricas", "Rep. Mes Anterior", "Rep. Mes Actual",
        "Veces ROJA", "Veces AMARILLA", "Veces VERDE", "Veces Ganadora",
        "Tasa Conversión %", "1ª Aparición", "Última Aparición",
        "Mejor Subida Pico %", "Tiempo Prom. Ganadora (d)", "Semáforo Dominante",
        "Diagnóstico / Prioridad"
    ]
    ws4.row_dimensions[4].height = 28
    for ci, h in enumerate(hdrs_ws4, start=1):
        c = ws4.cell(4, ci, h)
        c.font = Font(name="Arial", size=9, bold=True, color="FFFFFF")
        c.fill = fill_slate_hdr
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        c.border = borde

    per_prev = periodos_ord[-2] if len(periodos_ord) >= 2 else periodos_ord[-1]
    per_curr = periodos_ord[-1]

    for idx_c, (mon, _) in enumerate(coin_stats):
        rn = 5 + idx_c
        ws4.row_dimensions[rn].height = 20
        vals = [
            idx_c + 1,
            mon,
            f"=COUNTIF('3_REGISTRO_MAESTRO'!$F$5:$F${END_ROW},B{rn})",
            f"=COUNTIFS('3_REGISTRO_MAESTRO'!$F$5:$F${END_ROW},B{rn},'3_REGISTRO_MAESTRO'!$C$5:$C${END_ROW},\"{per_prev}\")",
            f"=COUNTIFS('3_REGISTRO_MAESTRO'!$F$5:$F${END_ROW},B{rn},'3_REGISTRO_MAESTRO'!$C$5:$C${END_ROW},\"{per_curr}\")",
            f"=COUNTIFS('3_REGISTRO_MAESTRO'!$F$5:$F${END_ROW},B{rn},'3_REGISTRO_MAESTRO'!$G$5:$G${END_ROW},\"🔴 ROJO\")",
            f"=COUNTIFS('3_REGISTRO_MAESTRO'!$F$5:$F${END_ROW},B{rn},'3_REGISTRO_MAESTRO'!$G$5:$G${END_ROW},\"🟡 AMARILLO\")",
            f"=COUNTIFS('3_REGISTRO_MAESTRO'!$F$5:$F${END_ROW},B{rn},'3_REGISTRO_MAESTRO'!$G$5:$G${END_ROW},\"🟢 VERDE\")+COUNTIFS('3_REGISTRO_MAESTRO'!$F$5:$F${END_ROW},B{rn},'3_REGISTRO_MAESTRO'!$G$5:$G${END_ROW},\"🏆 TOP ORO\")",
            f"=COUNTIFS('3_REGISTRO_MAESTRO'!$F$5:$F${END_ROW},B{rn},'3_REGISTRO_MAESTRO'!$Q$5:$Q${END_ROW},\"🏆 GANADORA\")",
            f"=IF(C{rn}>0,I{rn}/C{rn},0)",
            f"=MINIFS('3_REGISTRO_MAESTRO'!$B$5:$B${END_ROW},'3_REGISTRO_MAESTRO'!$F$5:$F${END_ROW},B{rn})",
            f"=MAXIFS('3_REGISTRO_MAESTRO'!$B$5:$B${END_ROW},'3_REGISTRO_MAESTRO'!$F$5:$F${END_ROW},B{rn})",
            f"=IFERROR(MAXIFS('3_REGISTRO_MAESTRO'!$P$5:$P${END_ROW},'3_REGISTRO_MAESTRO'!$F$5:$F${END_ROW},B{rn}),0)",
            f"=IFERROR(AVERAGEIFS('3_REGISTRO_MAESTRO'!$V$5:$V${END_ROW},'3_REGISTRO_MAESTRO'!$F$5:$F${END_ROW},B{rn},'3_REGISTRO_MAESTRO'!$Q$5:$Q${END_ROW},\"🏆 GANADORA\"),0)",
            f'=IF(AND(F{rn}>=G{rn},F{rn}>=H{rn}),"🔴 ROJO",IF(G{rn}>=H{rn},"🟡 AMARILLO","🟢 VERDE"))',
            f'=IF(AND(I{rn}>=2,M{rn}>=0.15),"🔥 RUNNER TOP (ALTA CONVERSIÓN)",IF(I{rn}>=1,"✅ GANADORA VALIDADA",IF(C{rn}>=4,"⏳ ALTA RECURRENCIA","⚪ EN OBSERVACIÓN")))'
        ]
        for ci, val in enumerate(vals, start=1):
            c = ws4.cell(rn, ci, val)
            c.border = borde
            c.font = Font(name="Arial", size=9, bold=(ci in (2, 9, 16)))
            c.alignment = Alignment(horizontal="left" if ci == 16 else "center", vertical="center")
            if ci in (3, 4, 5, 6, 7, 8, 9):
                c.number_format = "#,##0"
            elif ci in (10, 13):
                c.number_format = "0.0%"
            elif ci == 14:
                c.number_format = "0.00"
            if idx_c % 2 == 1:
                c.fill = fill_zebra

    ws4.freeze_panes = "A5"
    ws4.auto_filter.ref = f"A4:P{END_COIN_ROW}"

    widths_ws4 = [7, 12, 15, 16, 15, 12, 15, 13, 15, 17, 14, 15, 18, 22, 19, 32]
    for i, w in enumerate(widths_ws4, start=1):
        ws4.column_dimensions[get_column_letter(i)].width = w

    # --------------------------------------------------------------------------
    # PESTAÑA 5: 5_AUDITORIA_SETUPS
    # --------------------------------------------------------------------------
    ws5 = wb.create_sheet("5_AUDITORIA_SETUPS")
    ws5.views.sheetView[0].showGridLines = True

    ws5["A1"] = "AUDITORÍA ESTADÍSTICA POR SEMÁFORO, CONFLUENCIA Y RESULTADO REAL • PRE-EXPLOSIÓN"
    ws5["A1"].font = Font(name="Arial", size=12, bold=True, color="FFFFFF")
    ws5["A1"].fill = fill_navy
    ws5.merge_cells("A1:G1")
    ws5.row_dimensions[1].height = 28

    ws5["A2"] = (
        f"Conteo dinámico en vivo sobre las {len(filas_ord):,} señales unificadas de '3_REGISTRO_MAESTRO' ({f_ini_fmt} al {f_fin_fmt})."
    ).replace(",", ".")
    ws5["A2"].font = Font(name="Arial", size=9.5, italic=True, color="334155")
    ws5["A2"].fill = fill_subhdr
    ws5.merge_cells("A2:G2")
    ws5.row_dimensions[2].height = 20

    def escribir_tabla_auditoria(start_row, titulo, filas_def):
        ws5.cell(start_row, 1, titulo).font = Font(name="Arial", size=10, bold=True, color="0F172A")
        ws5.cell(start_row, 1).fill = fill_sec_hdr
        ws5.merge_cells(start_row=start_row, start_column=1, end_row=start_row, end_column=7)
        ws5.row_dimensions[start_row].height = 22

        hdrs = ["Segmento / Setup", "Señales Totales", "Ganadoras", "Efectividad %", "Subida Pico Prom %", "Var. Real Cierre %", "Tiempo Prom. (d)"]
        hr = start_row + 1
        ws5.row_dimensions[hr].height = 24
        for ci, h in enumerate(hdrs, start=1):
            c = ws5.cell(hr, ci, h)
            c.font = Font(name="Arial", size=9, bold=True, color="FFFFFF")
            c.fill = fill_slate_hdr
            c.alignment = Alignment(horizontal="center", vertical="center")
            c.border = borde

        for idx_f, (lbl, crit_col, crit_val) in enumerate(filas_def):
            rn = hr + 1 + idx_f
            ws5.row_dimensions[rn].height = 21
            ws5.cell(rn, 1, lbl)
            ws5.cell(rn, 2, f'=COUNTIF(\'3_REGISTRO_MAESTRO\'!${crit_col}$5:${crit_col}${END_ROW},"{crit_val}")')
            ws5.cell(rn, 3, f'=COUNTIFS(\'3_REGISTRO_MAESTRO\'!${crit_col}$5:${crit_col}${END_ROW},"{crit_val}",\'3_REGISTRO_MAESTRO\'!$Q$5:$Q${END_ROW},"🏆 GANADORA")')
            ws5.cell(rn, 4, f'=IF(B{rn}>0,C{rn}/B{rn},0)')
            ws5.cell(rn, 5, f'=IFERROR(AVERAGEIFS(\'3_REGISTRO_MAESTRO\'!$P$5:$P${END_ROW},\'3_REGISTRO_MAESTRO\'!${crit_col}$5:${crit_col}${END_ROW},"{crit_val}",\'3_REGISTRO_MAESTRO\'!$P$5:$P${END_ROW},">0"),0)')
            ws5.cell(rn, 6, f'=IFERROR(AVERAGEIFS(\'3_REGISTRO_MAESTRO\'!$T$5:$T${END_ROW},\'3_REGISTRO_MAESTRO\'!${crit_col}$5:${crit_col}${END_ROW},"{crit_val}",\'3_REGISTRO_MAESTRO\'!$Q$5:$Q${END_ROW},"🏆 GANADORA"),0)')
            ws5.cell(rn, 7, f'=IFERROR(AVERAGEIFS(\'3_REGISTRO_MAESTRO\'!$V$5:$V${END_ROW},\'3_REGISTRO_MAESTRO\'!${crit_col}$5:${crit_col}${END_ROW},"{crit_val}",\'3_REGISTRO_MAESTRO\'!$Q$5:$Q${END_ROW},"🏆 GANADORA"),0)')

            for ci in range(1, 8):
                c = ws5.cell(rn, ci)
                c.border = borde
                c.font = Font(name="Arial", size=9.5, bold=(ci == 1))
                c.alignment = Alignment(horizontal="left" if ci == 1 else "center", vertical="center")
                if ci in (2, 3):
                    c.number_format = "#,##0"
                elif ci == 4:
                    c.number_format = "0.0%"
                elif ci in (5, 6):
                    c.number_format = "+0.0%;-0.0%;0.0%"
                elif ci == 7:
                    c.number_format = "0.00"
                if idx_f % 2 == 1:
                    c.fill = fill_zebra
        return hr + 1 + len(filas_def) + 1

    r_next = escribir_tabla_auditoria(4, "1. AUDITORÍA POR SEMÁFORO DE DETECCIÓN INICIAL", [
        ("🔴 ROJO (Explosión Inminente)", "G", "🔴 ROJO"),
        ("🟡 AMARILLO (Confirmación Táctica)", "G", "🟡 AMARILLO"),
        ("🟢 VERDE (Compra Temprana)", "G", "🟢 VERDE"),
        ("🏆 TOP ORO (Verde Prioritario)", "G", "🏆 TOP ORO"),
    ])

    r_next = escribir_tabla_auditoria(r_next, "2. AUDITORÍA POR CONFLUENCIA CAZADOR TÁCTICO + PRE-EXPLOSIÓN", [
        ("🛡️ Confluencia Cazador + Pre-Explosión", "X", "SÍ (Cazador + Pre-Exp)"),
        ("📡 Señal Exclusiva Pre-Explosión", "X", "Solo Pre-Explosión"),
    ])

    escribir_tabla_auditoria(r_next, "3. AUDITORÍA POR NIVEL DE BLINDAJE IA", [
        ("IA >= 90% (Alta Convicción)", "K", ">=0.90"),
        ("IA 75% – 89% (Validada)", "K", ">=0.75"),
        ("IA < 75% (Observación)", "K", "<0.75"),
    ])

    widths_ws5 = [38, 17, 14, 16, 20, 20, 18]
    for i, w in enumerate(widths_ws5, start=1):
        ws5.column_dimensions[get_column_letter(i)].width = w

    wb.save(EXCEL_PRE_EXPLOSION_FILE)

    ganadas_tot = sum(1 for r in filas_ord if r.get("Estado") == "🏆 GANADORA")
    tasa_pct = round((ganadas_tot / len(filas_ord)) * 100, 1) if filas_ord else 0.0
    return {
        "total": len(filas_ord),
        "monedas_unicas": N_COINS,
        "dias_hist": len(fechas_ord),
        "ganadas": ganadas_tot,
        "tasa_pct": tasa_pct,
        "prom_txt": _formatear_demora(reporte_ia.get("demora_mediana_horas"))
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
    """Consolida todo el historial desde el inicio, cruza Ganadoras, corre Asistente IA y genera Excel de 5 pestañas."""
    ahora = ahora_art()
    hoy_str = ahora.strftime("%Y-%m-%d")
    ayer_str = (ahora - timedelta(days=1)).strftime("%Y-%m-%d")
    hora_now_str = ahora.strftime("%H:%M")

    ganadoras = {"dias": {}, "registro_verdes": {}}
    if os.path.exists(HISTORIAL_GANADORAS_FILE):
        try:
            with open(HISTORIAL_GANADORAS_FILE, "r", encoding="utf-8") as f:
                data_g = json.load(f)
            if isinstance(data_g, dict):
                ganadoras = data_g
        except Exception as e:
            print(f"⚠️ Error leyendo {HISTORIAL_GANADORAS_FILE}: {e}")

    eventos = historial.setdefault("eventos_unificados", {})
    _hidratar_desde_excels_y_json(historial, ganadoras, eventos)

    # Registrar las señales activas de esta corrida
    for cat_key in ("ROJO", "AMARILLO", "VERDE"):
        for it in (bloques.get(cat_key) or []):
            fib = it.get("fib_info") or {}
            sem_lbl = "🏆 TOP ORO" if (cat_key == "VERDE" and it.get("es_oro")) else _norm_semaforo_etiqueta(cat_key)
            coincide = bool(it.get("desde_posta") or it.get("en_cazador_tactico"))
            _upsert_evento_unificado(eventos, {
                "Fecha": hoy_str,
                "Hora": hora_now_str,
                "Moneda": it["ticker"],
                "Semaforo_Ini": sem_lbl,
                "Semaforo_Max": sem_lbl,
                "Escalada": "Directo 🔴" if cat_key == "ROJO" else "-",
                "IA_Pct": round(float(it.get("blindaje_pct", 0)) / 100.0, 4),
                "Fib_Zona": round(float(fib.get("ratio", 0.0)), 2) if fib.get("ok") else None,
                "Bids_Asks": float(it.get("ratio_bids_asks", 0.0)) if it.get("ratio_bids_asks") else None,
                "Precio_Entrada": float(it.get("precio_f", 0.0)),
                "Precio_Pico": float(it.get("precio_f", 0.0)),
                "Confluencia": "SÍ (Cazador + Pre-Exp)" if coincide else "Solo Pre-Explosión",
                "Origen": "Cazador + Pre-Explosión" if coincide else "Bot Pre-Explosión"
            })

    # Cruzar con historial_ganadoras.json para marcar cierres ganadores y demora real
    dias_win = ganadoras.get("dias", {})
    fechas_win_ord = sorted(dias_win.keys())
    ts_cierre_win_default = str(ganadoras.get("ultima_actualizacion", ""))[:16]

    precios_hist_win = {}
    for f_w, lista_w in dias_win.items():
        items_w = lista_w if isinstance(lista_w, list) else (list(lista_w.values()) if isinstance(lista_w, dict) else [])
        for g in items_w:
            if not isinstance(g, dict):
                continue
            sym_g = _normalizar_symbol(g.get("symbol") or g.get("ticker"))
            if sym_g:
                precios_hist_win.setdefault(sym_g, {})[f_w] = g

    for key, rec in eventos.items():
        f_ini = rec.get("Fecha", "")
        sym = _normalizar_symbol(rec.get("Moneda"))
        if not f_ini or not sym:
            continue

        p_ini = float(rec.get("Precio_Entrada") or 0.0)
        p_live = float(mapa_tickers.get(sym, {}).get("lastPrice", 0) or 0.0)
        p_pico = max(float(rec.get("Precio_Pico") or 0.0), p_ini, p_live)

        for f_w, g_info in precios_hist_win.get(sym, {}).items():
            if f_w >= f_ini:
                p_pico = max(p_pico, float(g_info.get("high") or g_info.get("precio") or 0.0))
        rec["Precio_Pico"] = p_pico

        for f_win in fechas_win_ord:
            if f_win < f_ini:
                continue
            match = precios_hist_win.get(sym, {}).get(f_win)
            if match:
                p_win = float(match.get("precio") or p_pico or p_ini)
                hora_ini = rec.get("Hora", "S/H")
                if f_win == f_ini and hora_ini in ("", "S/H", "00:00"):
                    horas_diff = 0.0
                    dias_diff = 0.0
                    tiempo_txt = "Mismo día"
                else:
                    try:
                        h_str = hora_ini if len(hora_ini) == 5 else "00:00"
                        dt_ini = datetime.strptime(f"{f_ini} {h_str}", "%Y-%m-%d %H:%M")
                    except Exception:
                        dt_ini = datetime.strptime(f_ini[:10], "%Y-%m-%d")

                    ts_w_str = ts_cierre_win_default if ts_cierre_win_default.startswith(f_win) else f"{f_win} 23:45"
                    try:
                        dt_win = datetime.strptime(ts_w_str, "%Y-%m-%d %H:%M")
                    except Exception:
                        dt_win = datetime.strptime(f_win[:10], "%Y-%m-%d") + timedelta(hours=23, minutes=45)

                    if dt_win <= dt_ini and f_win == f_ini:
                        horas_diff = 0.0
                        dias_diff = 0.0
                        tiempo_txt = "Mismo día (0h)"
                    else:
                        horas_diff = max(0.0, round((dt_win - dt_ini).total_seconds() / 3600.0, 1))
                        dias_diff = round(horas_diff / 24.0, 2)
                        tiempo_txt = _formatear_demora(horas_diff)

                ts_w_final = ts_cierre_win_default if ts_cierre_win_default.startswith(f_win) else f"{f_win} 23:45"
                rec["Estado"] = "🏆 GANADORA"
                rec["Fecha_Ganadora"] = ts_w_final
                rec["Precio_Final"] = p_win
                rec["Tiempo_Ganadora_Txt"] = tiempo_txt
                rec["Dias_Dec"] = dias_diff
                break

    reporte_ia = ejecutar_asistente_ia_pre_explosion(eventos, bloques)
    stats = _generar_excel_pre_explosion(eventos, mapa_tickers, reporte_ia)

    ultimo_envio = historial.get("ultimo_envio_excel_pre", "")
    es_cierre = (ahora.hour == 23 and ahora.minute >= 30 and ultimo_envio != hoy_str)
    es_recupero = (ahora.hour <= 2 and ultimo_envio != ayer_str)
    es_manual = (os.getenv("GITHUB_EVENT_NAME") == "workflow_dispatch")

    if es_cierre or es_recupero or es_manual:
        fecha_lbl = ayer_str if (es_recupero and not es_cierre) else hoy_str
        caption = (
            f"📊 <b>Excel Maestro Pre-Explosión + IA ({fecha_lbl})</b>\n"
            f"• Universo unificado: <b>{stats['total']} señales</b> ({stats['monedas_unicas']} monedas en <b>{stats['dias_hist']} días</b>)\n"
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
    for mod in MODELOS_GEMINI_PRE:
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
    print(f"🔥 EJECUTANDO PRE-EXPLOSIÓN V10 + EXCEL MAESTRO 5 PESTAÑAS ({ahora_art().strftime('%Y-%m-%d %H:%M:%S')} ART)...")
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
