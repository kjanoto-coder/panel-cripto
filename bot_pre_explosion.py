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

    for f_str, bucket in (historial.get("apariciones_por_dia") or {}).items():
        if not isinstance(bucket, dict):
            continue
        for sym, info in bucket.items():
            if not isinstance(info, dict):
                continue
            col = "🏆 TOP ORO" if info.get("es_oro") else info.get("color", "VERDE")
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
