import os
import re
import sys
import json
import time
import random
import html
import subprocess
from datetime import datetime, timezone, timedelta

for mod, pkg in [("requests", "requests"), ("matplotlib", "matplotlib"), ("openpyxl", "openpyxl"), ("google.genai", "google-genai")]:
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

TZ_ART = timezone(timedelta(hours=-3))
TELEGRAM_BOT_TOKEN = (os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("TELEGRAM_TOKEN") or "").strip()
TELEGRAM_CHAT_ID = (os.getenv("TELEGRAM_CHAT_ID") or os.getenv("CHAT_ID") or "").strip()
TELEGRAM_TOPIC_ID = (os.getenv("TOPIC_ID_PRE_EXPLOSION") or os.getenv("TELEGRAM_MESSAGE_THREAD_ID") or os.getenv("TOPIC_ID_CENTRAL") or "").strip()
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

MESES_ES = {1: "Enero", 2: "Febrero", 3: "Marzo", 4: "Abril", 5: "Mayo", 6: "Junio", 7: "Julio", 8: "Agosto", 9: "Septiembre", 10: "Octubre", 11: "Noviembre", 12: "Diciembre"}
PRIORIDAD_COLOR = {"VERDE": 1, "AMARILLO": 2, "ROJO": 3}
EXCL_BASE = {'USDT', 'USDC', 'FDUSD', 'DAI', 'TUSD', 'USDP', 'EUR', 'GBP', 'AUD', 'BRL', 'ARS', 'TRY', 'BUSD', 'USD1', 'AEUR', 'EURI', 'USDE', 'RLUSD', 'RWUSD', 'XUSD', 'BFUSD', 'U', 'USDG', 'USDS', 'PYUSD', 'BTC', 'ETH', 'SOL', 'ADA', 'XRP', 'DOGE', 'TRX', 'SHIB', 'AVAX', 'LINK', 'BNB', 'DOT', 'NEAR', 'SUI', 'PEPE'}


def ahora_art():
    return datetime.now(TZ_ART)


def es_simbolo_valido(base):
    if not base or base in EXCL_BASE or not re.match(r'^[A-Z0-9]+$', base) or base.endswith('B'):
        return False
    return not any(x in base for x in ['UP', 'DOWN', 'BULL', 'BEAR'])


def cargar_historial():
    hoy = ahora_art().strftime('%Y-%m-%d')
    ayer = (ahora_art() - timedelta(days=1)).strftime('%Y-%m-%d')
    base = {
        "fecha": hoy, "mencionadas": {}, "resumen_dia": [], "resumen_enviado_hoy": False,
        "posta": {}, "graduadas_pre_explosion": {}, "verdes_hoy": [], "verdes_ayer": [],
        "oro_hoy": [], "registro_cronologico": {}, "apariciones_por_dia": {},
        "eventos_unificados": {}, "ultimo_envio_excel_pre": ""
    }
    if os.path.exists(HISTORIAL_FILE):
        try:
            with open(HISTORIAL_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
            base["posta"] = data.get("posta", {}) if isinstance(data.get("posta"), dict) else {}
            base["registro_cronologico"] = data.get("registro_cronologico", {}) if isinstance(data.get("registro_cronologico"), dict) else {}
            base["eventos_unificados"] = data.get("eventos_unificados", {}) if isinstance(data.get("eventos_unificados"), dict) else {}
            base["ultimo_envio_excel_pre"] = data.get("ultimo_envio_excel_pre", "")

            hoy_dt = ahora_art().date()
            for f_str, bucket in (data.get("apariciones_por_dia") or {}).items():
                try:
                    if (hoy_dt - datetime.strptime(f_str, '%Y-%m-%d').date()).days <= DIAS_RETENCION_CALENDARIO and isinstance(bucket, dict):
                        base["apariciones_por_dia"][f_str] = bucket
                except Exception:
                    continue

            for sym, info in (data.get("graduadas_pre_explosion") or {}).items():
                base_sym = sym[:-4] if sym.endswith("USDT") else sym
                if not es_simbolo_valido(base_sym):
                    continue
                try:
                    if (hoy_dt - datetime.strptime(info.get("fecha_iso", hoy), '%Y-%m-%d').date()).days <= DIAS_GRADUADAS:
                        base["graduadas_pre_explosion"][sym] = info
                except Exception:
                    continue

            if data.get("fecha") == hoy:
                for k in ("mencionadas", "resumen_dia", "resumen_enviado_hoy", "verdes_hoy", "verdes_ayer", "oro_hoy"):
                    base[k] = data.get(k, base[k])
            elif data.get("fecha") == ayer:
                base["verdes_ayer"] = data.get("verdes_hoy", [])
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
    s = requests.Session()
    s.headers.update({"User-Agent": "Mozilla/5.0", "Accept": "application/json", "Cache-Control": "no-cache"})
    return s


def obtener_simbolos_spot_activos(session):
    for url in ["https://api.binance.com/api/v3/exchangeInfo", "https://data-api.binance.vision/api/v3/exchangeInfo"]:
        try:
            res = session.get(url, timeout=12)
            if res.status_code == 200:
                syms = {s.get('symbol') for s in res.json().get('symbols', []) if s.get('status') == 'TRADING' and s.get('isSpotTradingAllowed', True) and s.get('quoteAsset') == 'USDT'}
                if syms:
                    return syms
        except Exception:
            continue
    return set()


def obtener_datos_binance(session):
    for url in ["https://api.binance.com/api/v3/ticker/24hr", "https://data-api.binance.vision/api/v3/ticker/24hr"]:
        try:
            res = session.get(url, timeout=15)
            if res.status_code == 200 and isinstance(res.json(), list) and len(res.json()) > 0:
                return res.json()
        except Exception:
            continue
    return []


def analizar_order_book_blindaje(session, symbol):
    for u in [f"https://api.binance.com/api/v3/depth?symbol={symbol}&limit=20", f"https://data-api.binance.vision/api/v3/depth?symbol={symbol}&limit=20"]:
        try:
            r = session.get(u, timeout=5)
            if r.status_code == 200:
                d = r.json()
                bids, asks = d.get("bids", []), d.get("asks", [])
                if not bids or not asks:
                    continue
                best_bid, best_ask = float(bids[0][0]), float(asks[0][0])
                spread_pct = ((best_ask - best_bid) / best_bid) * 100 if best_bid > 0 else 99.0
                vol_bids = sum(float(b[0]) * float(b[1]) for b in bids)
                vol_asks = sum(float(a[0]) * float(a[1]) for a in asks)
                ratio_ba = round(vol_bids / vol_asks, 2) if vol_asks > 0 else 1.0
                return {"ok": True, "spread_pct": round(spread_pct, 3), "ratio_bids_asks": ratio_ba, "libro_sano": (spread_pct <= 0.45 and ratio_ba >= 0.75)}
        except Exception:
            continue
    return {"ok": False, "spread_pct": 0.1, "ratio_bids_asks": 1.0, "libro_sano": True}


def obtener_metricas_velas(session, symbol):
    cambio_1h, cambio_4h, vol_1h_rel, fib_info = 0.0, 0.0, 1.0, {"ok": False}
    for u in [f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval=1h&limit=25", f"https://data-api.binance.vision/api/v3/klines?symbol={symbol}&interval=1h&limit=25"]:
        try:
            res = session.get(u, timeout=6)
            if res.status_code == 200:
                candles = res.json()
                if len(candles) >= 2:
                    op, cl = float(candles[-1][1]), float(candles[-1][4])
                    if op > 0:
                        cambio_1h = round(((cl - op) / op) * 100, 2)
                    prev_vols = [float(c[7]) for c in candles[:-1] if float(c[7]) > 0]
                    if prev_vols and (sum(prev_vols) / len(prev_vols)) > 0:
                        vol_1h_rel = round(float(candles[-1][7]) / (sum(prev_vols) / len(prev_vols)), 2)
                break
        except Exception:
            continue

    for u in [f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval=4h&limit=36", f"https://data-api.binance.vision/api/v3/klines?symbol={symbol}&interval=4h&limit=36"]:
        try:
            res = session.get(u, timeout=6)
            if res.status_code == 200:
                candles = res.json()
                if len(candles) >= 1:
                    op, cl = float(candles[-1][1]), float(candles[-1][4])
                    if op > 0:
                        cambio_4h = round(((cl - op) / op) * 100, 2)
                if len(candles) >= 12:
                    sh, sl, p_act = max(float(c[2]) for c in candles), min(float(c[3]) for c in candles), float(candles[-1][4])
                    rango = sh - sl
                    if rango > 0:
                        ratio = round((sh - p_act) / rango, 2)
                        en_pb = (0.35 <= ratio <= 0.65)
                        ext = (p_act >= sl + (rango * 1.272) or ratio < 0.08)
                        etiq = f"Pullback Sano Fib ({ratio:.2f})" if en_pb else (f"Extendida Fib ({ratio:.2f})" if ext else (f"Piso Profundo Fib ({ratio:.2f})" if ratio > 0.65 else f"Tramo Alcista Fib ({ratio:.2f})"))
                        fib_info = {"ok": True, "ratio": ratio, "etiqueta_fib": etiq, "en_pullback_sano": en_pb, "extendida_fib": ext, "fib_618": sh - (rango * 0.618), "ext_1618": sl + (rango * 1.618)}
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
    precio, cambio_24h, vol_usdt = float(t.get('lastPrice', 0)), float(t.get('priceChangePercent', 0)), float(t.get('quoteVolume', 0))
    high, low = float(t.get('highPrice', 0)), float(t.get('lowPrice', 0))
    if precio <= 0:
        return None

    cambio_1h, cambio_4h, vol_1h_rel, fib_info = obtener_metricas_velas(session, symbol)
    pos_liq = round(((precio - low) / (high - low)) * 100, 1) if high > low else 50.0
    pct_rango = ((high - low) / precio) * 100 if precio > 0 else 1.0
    factor_spike = (vol_usdt / 1_000_000) / (pct_rango if pct_rango > 0 else 1.0)
    bono_fib = 8.5 if fib_info.get("en_pullback_sano") else (-10.0 if fib_info.get("extendida_fib") else 0.0)
    pen_ext = 14.0 if (pos_liq > 90.0 or cambio_24h > 7.5) else 0.0

    score_ia = round((cambio_1h * 3.2) + (cambio_4h * 2.0) + (cambio_24h * 1.1) + (factor_spike * 1.5) + (vol_1h_rel * 1.8) + (18.0 if desde_posta else 0.0) + bono_fib - pen_ext, 2)
    score_oro = round((vol_1h_rel * 2.5) + (factor_spike * 1.5) + (cambio_1h * 2.0) - abs(3.0 - cambio_24h) + (pos_liq / 30.0) + (bono_fib * 0.6), 2)

    var_grad, fecha_grad = None, ""
    if desde_posta and info_grad:
        p_ref = float(info_grad.get("precio_ref", 0) or 0)
        fecha_grad = str(info_grad.get("fecha_corta", ""))
        if p_ref > 0:
            var_grad = round(((precio - p_ref) / p_ref) * 100, 2)

    return {
        'symbol': symbol, 'ticker': base, 'precio_f': precio, 'cambio_f': cambio_24h,
        'cambio_1h': cambio_1h, 'cambio_4h': cambio_4h, 'vol_1h_rel': vol_1h_rel,
        'vol_f': vol_usdt, 'high_f': high, 'low_f': low, 'pos_liquidez_pct': pos_liq,
        'fib_info': fib_info, 'score_ia': score_ia, 'score_oro': score_oro, 'es_oro': False,
        'desde_posta': bool(desde_posta), 'en_cazador_tactico': bool(info_posta),
        'var_desde_grad': var_grad, 'fecha_grad': fecha_grad, 'certificada_ia': False,
        'blindaje_pct': 0, 'motivo_certificacion': "", 'ratio_bids_asks': 1.0, 'spread_pct': 0.1
    }


def certificar_confluencia_ia(session, seleccion_total, historial):
    if not seleccion_total:
        return
    grad = historial.get("graduadas_pre_explosion", {})
    hoy_str, fecha_corta = ahora_art().strftime('%Y-%m-%d'), ahora_art().strftime('%d/%m %H:%M')
    resumen_ia = []

    for item in seleccion_total:
        ob = analizar_order_book_blindaje(session, item["symbol"])
        fib = item.get("fib_info", {})
        coincide = item.get("desde_posta") or item.get("en_cazador_tactico")
        pts = 50 + (18 if coincide else 0) + (12 if fib.get("en_pullback_sano") else (-15 if fib.get("extendida_fib") else 0)) + (10 if ob.get("libro_sano") else -14) + (8 if item["vol_1h_rel"] >= 1.1 else 0) + (7 if -1.5 <= item["cambio_f"] <= 7.0 else 0)
        blindaje = max(25, min(98, pts))
        cert = (blindaje >= 72 and ob.get("libro_sano", True) and not fib.get("extendida_fib", False))
        razones = (["Coincide Cazador+PreExplosión"] if coincide else []) + ([fib.get("etiqueta_fib", "")] if fib.get("ok") else []) + [f"Libro Bids/Asks: {ob['ratio_bids_asks']}x (Spread {ob['spread_pct']}%)"]

        item.update({"blindaje_pct": blindaje, "certificada_ia": cert, "motivo_certificacion": " | ".join(razones), "ratio_bids_asks": ob["ratio_bids_asks"], "spread_pct": ob["spread_pct"]})
        resumen_ia.append({"moneda": item["ticker"], "categoria": item["categoria"], "coincide": coincide, "1h": item["cambio_1h"], "24h": item["cambio_f"], "fib": fib.get("etiqueta_fib", "N/D"), "ob": ob["ratio_bids_asks"], "blindaje": blindaje})

    if GEMINI_API_KEY and resumen_ia:
        try:
            client = genai.Client(api_key=GEMINI_API_KEY)
            prompt = f"Gestor Certificador IA Binance Spot. Certifica SOLO impulsos sanos con buen libro Bids>=Asks sin FOMO:\n{json.dumps(resumen_ia, ensure_ascii=False)}\nResponde SOLO JSON:\n{{\"MONEDA\":{{\"certificada\":true,\"blindaje_pct\":85,\"nota\":\"motivo corto\"}}}}"
            for mod in MODELOS_GEMINI_PRE:
                try:
                    res = client.models.generate_content(model=mod, contents=prompt)
                    if res and res.text and "{" in res.text:
                        ver = json.loads(res.text[res.text.find("{"):res.text.rfind("}") + 1])
                        for item in seleccion_total:
                            vm = ver.get(item["ticker"])
                            if isinstance(vm, dict):
                                item["certificada_ia"] = bool(vm.get("certificada", item["certificada_ia"]))
                                item["blindaje_pct"] = int(vm.get("blindaje_pct", item["blindaje_pct"]))
                                if vm.get("nota"):
                                    item["motivo_certificacion"] = str(vm["nota"])[:130]
                        break
                except Exception:
                    continue
        except Exception:
            pass

    for item in seleccion_total:
        sym = item["symbol"]
        if item["certificada_ia"] or sym in grad:
            prev = grad.get(sym, {})
            grad[sym] = {
                "symbol": sym, "base": item["ticker"], "estrellas": 3 if item["categoria"] == "ROJO" else 2,
                "probabilidad_pct": item["blindaje_pct"], "precio_ref": float(prev.get("precio_ref") or item["precio_f"]),
                "fecha_iso": prev.get("fecha_iso", hoy_str), "fecha_corta": prev.get("fecha_corta", fecha_corta),
                "certificada_ia": bool(item["certificada_ia"]), "blindaje_pct": int(item["blindaje_pct"]), "motivo_certificacion": item["motivo_certificacion"]
            }
    historial["graduadas_pre_explosion"] = grad


def motor_ia_seleccion_tactica(tickers, simbolos_activos, session, historial):
    hoy_str = ahora_art().strftime('%Y-%m-%d')
    ayer_str = (ahora_art() - timedelta(days=1)).strftime('%Y-%m-%d')
    if historial.get("fecha") != hoy_str:
        historial["verdes_ayer"] = historial.get("verdes_hoy", []) if historial.get("fecha") == ayer_str else []
        historial.update({"verdes_hoy": [], "oro_hoy": [], "fecha": hoy_str, "mencionadas": {}, "resumen_dia": [], "resumen_enviado_hoy": False})

    mencionadas = {s: c - 1 for s, c in historial.get("mencionadas", {}).items() if c - 1 > 0}
    verdes_ayer, verdes_hoy, oro_hoy = set(historial.get("verdes_ayer", [])), set(historial.get("verdes_hoy", [])), set(historial.get("oro_hoy", []))
    grad, posta = historial.get("graduadas_pre_explosion", {}), historial.get("posta", {})

    syms_rojo = {s for s in grad if es_simbolo_valido(s[:-4] if s.endswith("USDT") else s)}
    for sym, d in posta.items():
        base = sym[:-4] if sym.endswith("USDT") else sym
        if es_simbolo_valido(base) and int(d.get("etapa", d.get("paso", 1))) == 3:
            syms_rojo.add(sym)
            grad.setdefault(sym, {"symbol": sym, "base": base, "estrellas": 3, "probabilidad_pct": int(d.get("prob_actual", 75)), "precio_ref": float(d.get("precio_inicio", 0) or 0), "fecha_iso": d.get("fecha_iso", hoy_str), "fecha_corta": d.get("fecha_corta", ahora_art().strftime('%d/%m'))})

    mapa_tickers = {t['symbol']: t for t in tickers if t.get('symbol') in simbolos_activos and t['symbol'].endswith('USDT') and es_simbolo_valido(t['symbol'][:-4])}
    total_analizadas, items_posta, cand_merc = 0, [], []

    for sym in syms_rojo:
        t = mapa_tickers.get(sym)
        if t and float(t.get('lastPrice', 0)) > 0 and float(t.get('quoteVolume', 0)) >= 250_000:
            total_analizadas += 1
            it = construir_item_desde_ticker(session, t, True, grad.get(sym), posta.get(sym))
            if it:
                items_posta.append(it)
    items_posta.sort(key=lambda x: x['score_ia'], reverse=True)
    vistos = {x['symbol'] for x in items_posta}

    for sym, t in mapa_tickers.items():
        if sym in vistos or sym in mencionadas:
            continue
        p, c24, vol = float(t.get('lastPrice', 0)), float(t.get('priceChangePercent', 0)), float(t.get('quoteVolume', 0))
        if 0.000001 <= p < 15.0 and vol >= 1_000_000 and -2.0 <= c24 <= 9.0:
            total_analizadas += 1
            it = construir_item_desde_ticker(session, t, False, None, posta.get(sym))
            if it and (it['cambio_1h'] >= -0.2 or it['cambio_4h'] >= 0.3):
                cand_merc.append(it)

    cand_merc.sort(key=lambda x: x['score_ia'], reverse=True)
    sel_imp = items_posta[:8] + [x for x in cand_merc if x['cambio_f'] <= 6.5][:max(0, 8 - len(items_posta[:8]))]
    top_rojas, top_amarillas = sel_imp[:4], sel_imp[4:8]
    usadas = {x['symbol'] for x in (top_rojas + top_amarillas)}

    cand_oro, cand_piso = [], []
    for it in cand_merc:
        if it['symbol'] in usadas or it['symbol'] in verdes_ayer:
            continue
        if (1.8 <= it['cambio_f'] <= 4.5) and (15.0 <= it['pos_liquidez_pct'] <= 30.0) and it['cambio_1h'] >= 0.0 and it['vol_1h_rel'] >= 1.1:
            it['es_oro'] = True
            cand_oro.append(it)
        elif (-1.5 <= it['cambio_f'] <= 4.5) and (it['pos_liquidez_pct'] <= 35.0):
            cand_piso.append(it)

    cand_oro.sort(key=lambda x: x['score_oro'], reverse=True)
    cand_piso.sort(key=lambda x: x['score_oro'], reverse=True)
    top_verdes = cand_oro[:3]
    for it in cand_piso:
        if len(top_verdes) < 5 and it['symbol'] not in {x['symbol'] for x in top_verdes}:
            top_verdes.append(it)

    for it in top_rojas:
        it.update({'categoria': "ROJO", 'estado_texto': "Explosión Inminente", 'color_hex': "#ff1744"})
    for it in top_amarillas:
        it.update({'categoria': "AMARILLO", 'estado_texto': "Confirmación Táctica", 'color_hex': "#ffd600"})
    for it in top_verdes:
        if it.get('es_oro'):
            it.update({'categoria': "VERDE", 'estado_texto': "🏆 COMPRA AQUÍ (ORO)", 'color_hex': "#ffd700"})
            oro_hoy.add(it['symbol'])
        else:
            it.update({'categoria': "VERDE", 'estado_texto': "Vigilancia / Acumulación", 'color_hex': "#00e676"})
        verdes_hoy.add(it['symbol'])

    sel_total = top_rojas + top_amarillas + top_verdes
    certificar_confluencia_ia(session, sel_total, historial)
    for it in sel_total:
        mencionadas[it['symbol']] = 3
        if it['symbol'] not in historial["resumen_dia"]:
            historial["resumen_dia"].append(it['symbol'])

    historial.update({"mencionadas": mencionadas, "verdes_hoy": list(verdes_hoy), "oro_hoy": list(oro_hoy)})
    guardar_historial(historial)
    return {"ROJO": top_rojas, "AMARILLO": top_amarillas, "VERDE": top_verdes}, total_analizadas, historial, mapa_tickers


def _normalizar_symbol(raw):
    s = str(raw or "").strip().upper()
    return f"{s}USDT" if s and not s.endswith("USDT") else s


def _norm_semaforo_etiqueta(val):
    s = str(val or "").upper()
    return "🏆 TOP ORO" if "ORO" in s else ("🔴 ROJO" if "ROJ" in s else ("🟡 AMARILLO" if "AMAR" in s else "🟢 VERDE"))


def _semaforo_codigo(etiqueta):
    s = str(etiqueta or "").upper()
    return "ROJO" if "ROJ" in s else ("AMARILLO" if "AMAR" in s else "VERDE")


def _parse_ia_frac(val):
    s = str(val or "").replace("%", "").strip()
    if s in ("", "-", "None", "nan"):
        return None
    try:
        v = float(s)
        return round(v / 100.0, 4) if v > 1.0 else round(v, 4)
    except Exception:
        return None


def _parse_ba_float(val):
    s = str(val or "").replace("x", "").strip()
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
    dias, horas = int(horas_totales // 24), int(round(horas_totales % 24))
    if horas == 24:
        dias += 1
        horas = 0
    return f"{dias}d {horas:02d}h" if dias > 0 else f"{horas}h"


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
    p_ent = float(ev.get("Precio_Entrada") or 0.0)
    p_pico = max(float(ev.get("Precio_Pico") or 0.0), p_ent)

    if key not in eventos:
        eventos[key] = {
            "Fecha": fecha, "Hora": hora, "Moneda": mon, "Semaforo_Ini": sem_ini, "Semaforo_Max": sem_max,
            "Escalada": str(ev.get("Escalada") or ("Directo 🔴" if "ROJO" in sem_ini else "-")).strip(),
            "IA_Pct": ev.get("IA_Pct"), "Fib_Zona": ev.get("Fib_Zona"), "Bids_Asks": ev.get("Bids_Asks"),
            "Precio_Entrada": p_ent, "Precio_Pico": p_pico,
            "Estado": str(ev.get("Estado") or "⏳ EN SEGUIMIENTO").strip(),
            "Fecha_Ganadora": str(ev.get("Fecha_Ganadora") or "-").strip(),
            "Precio_Final": float(ev.get("Precio_Final") or p_ent),
            "Tiempo_Ganadora_Txt": str(ev.get("Tiempo_Ganadora_Txt") or "En seguimiento").strip(),
            "Dias_Dec": ev.get("Dias_Dec"), "Fib_1618": str(ev.get("Fib_1618") or "-").strip(),
            "Confluencia": str(ev.get("Confluencia") or "Solo Pre-Explosión").strip(),
            "Origen": str(ev.get("Origen") or "Bot Pre-Explosión").strip()
        }
    else:
        cur = eventos[key]
        if hora != "S/H" and (cur.get("Hora") in ("", "S/H", "00:00") or hora < cur["Hora"]):
            cur["Hora"] = hora
        if PRIORIDAD_COLOR[_semaforo_codigo(sem_max)] > PRIORIDAD_COLOR[_semaforo_codigo(cur.get("Semaforo_Max"))]:
            cur["Semaforo_Max"] = sem_max
        if "ORO" in sem_ini:
            cur["Semaforo_Ini"] = "🏆 TOP ORO"
        if ev.get("IA_Pct") is not None and (cur.get("IA_Pct") is None or ev["IA_Pct"] > float(cur["IA_Pct"])):
            cur["IA_Pct"] = ev["IA_Pct"]
        if cur.get("Precio_Entrada", 0.0) <= 0 and p_ent > 0:
            cur["Precio_Entrada"] = p_ent
        if p_pico > float(cur.get("Precio_Pico") or 0.0):
            cur["Precio_Pico"] = p_pico
        if "GANADORA" in str(ev.get("Estado", "")).upper():
            cur["Estado"] = "🏆 GANADORA"
            if ev.get("Fecha_Ganadora") not in (None, "", "-"):
                cur["Fecha_Ganadora"] = str(ev["Fecha_Ganadora"])
            if float(ev.get("Precio_Final") or 0) > 0:
                cur["Precio_Final"] = float(ev["Precio_Final"])
            if ev.get("Tiempo_Ganadora_Txt") not in (None, "", "-", "En seguimiento"):
                cur["Tiempo_Ganadora_Txt"] = str(ev["Tiempo_Ganadora_Txt"])
            if ev.get("Dias_Dec") is not None:
                cur["Dias_Dec"] = ev["Dias_Dec"]
        if "SÍ" in str(ev.get("Confluencia", "")):
            cur["Confluencia"] = "SÍ (Cazador + Pre-Exp)"
            cur["Origen"] = "Cazador + Pre-Explosión"


def _hidratar_desde_excels_y_json(historial, ganadoras, eventos):
    if os.path.exists(EXCEL_PRE_EXPLOSION_FILE):
        try:
            wb_prev = openpyxl.load_workbook(EXCEL_PRE_EXPLOSION_FILE, data_only=True)
            if "3_REGISTRO_MAESTRO" in wb_prev.sheetnames:
                ws = wb_prev["3_REGISTRO_MAESTRO"]
                for r in range(5, ws.max_row + 1):
                    fecha, mon = str(ws.cell(r, 2).value or "")[:10], str(ws.cell(r, 6).value or "").strip().upper()
                    if fecha and mon:
                        _upsert_evento_unificado(eventos, {
                            "Fecha": fecha, "Hora": ws.cell(r, 5).value, "Moneda": mon,
                            "Semaforo_Ini": ws.cell(r, 7).value, "Semaforo_Max": ws.cell(r, 8).value, "Escalada": ws.cell(r, 9).value,
                            "IA_Pct": _parse_ia_frac(ws.cell(r, 11).value),
                            "Fib_Zona": float(ws.cell(r, 12).value) if isinstance(ws.cell(r, 12).value, (int, float)) else None,
                            "Bids_Asks": _parse_ba_float(ws.cell(r, 13).value),
                            "Precio_Entrada": float(ws.cell(r, 14).value or 0.0) if isinstance(ws.cell(r, 14).value, (int, float)) else 0.0,
                            "Precio_Pico": float(ws.cell(r, 15).value or 0.0) if isinstance(ws.cell(r, 15).value, (int, float)) else 0.0,
                            "Estado": ws.cell(r, 17).value, "Fecha_Ganadora": ws.cell(r, 18).value,
                            "Precio_Final": float(ws.cell(r, 19).value or 0.0) if isinstance(ws.cell(r, 19).value, (int, float)) else 0.0,
                            "Tiempo_Ganadora_Txt": ws.cell(r, 21).value,
                            "Dias_Dec": float(ws.cell(r, 22).value) if isinstance(ws.cell(r, 22).value, (int, float)) else None,
                            "Fib_1618": ws.cell(r, 23).value, "Confluencia": ws.cell(r, 24).value, "Origen": ws.cell(r, 25).value
                        })
        except Exception:
            pass

    if os.path.exists(EXCEL_CAZADOR_FILE):
        try:
            wb_caz = openpyxl.load_workbook(EXCEL_CAZADOR_FILE, data_only=True)
            if "3_REGISTRO_MAESTRO" in wb_caz.sheetnames:
                ws_c = wb_caz["3_REGISTRO_MAESTRO"]
                for r in range(5, ws_c.max_row + 1):
                    paso = str(ws_c.cell(r, 25).value or "")
                    if not paso.startswith("SÍ"):
                        continue
                    fecha, mon = str(ws_c.cell(r, 2).value or "")[:10], str(ws_c.cell(r, 6).value or "").strip().upper()
                    if fecha and mon:
                        m_ia = re.search(r"(\d+)%", str(ws_c.cell(r, 8).value or ""))
                        p_ini = float(ws_c.cell(r, 9).value or 0.0) if isinstance(ws_c.cell(r, 9).value, (int, float)) else 0.0
                        p_max = float(ws_c.cell(r, 14).value or p_ini) if isinstance(ws_c.cell(r, 14).value, (int, float)) else p_ini
                        is_win = ("Ganadoras" in paso) or ("Ambos" in paso) or ("REBOTE_EXITOSO" in str(ws_c.cell(r, 24).value or ""))
                        tp = float(ws_c.cell(r, 17).value) if isinstance(ws_c.cell(r, 17).value, (int, float)) else None
                        _upsert_evento_unificado(eventos, {
                            "Fecha": fecha, "Hora": ws_c.cell(r, 5).value, "Moneda": mon, "Semaforo_Ini": ws_c.cell(r, 7).value,
                            "IA_Pct": round(float(m_ia.group(1)) / 100.0, 4) if m_ia else None,
                            "Precio_Entrada": p_ini, "Precio_Pico": max(p_ini, p_max),
                            "Estado": "🏆 GANADORA" if is_win else "⏳ EN SEGUIMIENTO", "Fecha_Ganadora": fecha if is_win else "-",
                            "Precio_Final": p_max if is_win else p_ini,
                            "Tiempo_Ganadora_Txt": f"{int(round(tp))}h" if (is_win and tp and tp > 0) else ("Mismo día" if is_win else "En seguimiento"),
                            "Dias_Dec": round(tp / 24.0, 2) if (is_win and tp is not None) else None,
                            "Confluencia": "SÍ (Cazador + Pre-Exp)", "Origen": str(ws_c.cell(r, 26).value or "Histórico Cazador")
                        })
        except Exception:
            pass

    for f_str, bucket in (historial.get("apariciones_por_dia") or {}).items():
        if isinstance(bucket, dict):
            for sym, info in bucket.items():
                if isinstance(info, dict):
                    _upsert_evento_unificado(eventos, {
                        "Fecha": f_str, "Hora": info.get("hora", "S/H"), "Moneda": info.get("ticker") or sym,
                        "Semaforo_Ini": "🏆 TOP ORO" if info.get("es_oro") else info.get("color", "VERDE"),
                        "IA_Pct": _parse_ia_frac(info.get("ia_pct")),
                        "Fib_Zona": float(info.get("fib_zona")) if info.get("fib_zona") else None,
                        "Precio_Entrada": float(info.get("precio") or 0.0), "Origen": "Bot Pre-Explosión"
                    })


def ejecutar_asistente_ia_pre_explosion(eventos, bloques):
    todas = list(eventos.values())
    ganadas = [r for r in todas if r.get("Estado") == "🏆 GANADORA"]
    fechas_unicas = sorted({r["Fecha"] for r in todas if r.get("Fecha")})
    monedas_unicas = {r["Moneda"] for r in todas if r.get("Moneda")}
    dias_all = [float(r["Dias_Dec"]) for r in ganadas if isinstance(r.get("Dias_Dec"), (int, float)) and float(r["Dias_Dec"]) >= 0]
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
    stats_seg, tasa_cat, horiz_cat = [], {}, {}
    for cod, nom, sub in segmentos:
        wins = [x for x in sub if x.get("Estado") == "🏆 GANADORA"]
        ds = [float(x["Dias_Dec"]) for x in wins if isinstance(x.get("Dias_Dec"), (int, float))]
        ts = round((len(wins) / len(sub)) * 100, 1) if sub else 0.0
        mh = max(12.0, round((sorted(ds)[len(ds) // 2] if ds else med_dias) * 24.0, 1))
        tasa_cat[cod], horiz_cat[cod] = ts, mh
        stats_seg.append({"codigo": cod, "categoria": nom, "detectadas": len(sub), "ganadoras": len(wins), "tasa_acierto_pct": ts, "demora_mediana_horas": mh, "demora_mediana_txt": _formatear_demora(mh)})

    activas, vistas = [], set()
    for cat in ("ROJO", "AMARILLO", "VERDE"):
        for it in (bloques.get(cat) or []):
            if it["symbol"] in vistas:
                continue
            vistas.add(it["symbol"])
            cod_s = "TOP_ORO" if (cat == "VERDE" and it.get("es_oro")) else cat
            hh = round(horiz_cat.get(cod_s, 48.0), 1)
            hd = round(hh / 24.0, 1)
            fib = it.get("fib_info") or {}
            cert, bl = bool(it.get("certificada_ia")), int(it.get("blindaje_pct") or 50)
            accion = "COMPRA_CONFIRMADA_MADURACION" if (cert and cat in ("ROJO", "AMARILLO")) else ("COMPRA_TEMPRANA_ORO_PACIENCIA" if it.get("es_oro") else ("ACUMULACION_ESCALONADA" if cert else "OBSERVACION_ESPERAR_CONFIRMACION"))
            activas.append({
                "symbol": it["symbol"], "ticker": it["ticker"], "semaforo": cod_s, "certificada_ia": cert, "blindaje_pct": bl,
                "precio_actual": it.get("precio_f", 0.0), "cambio_1h_pct": it.get("cambio_1h", 0.0), "cambio_4h_pct": it.get("cambio_4h", 0.0),
                "cambio_24h_pct": it.get("cambio_f", 0.0), "vol_1h_rel": it.get("vol_1h_rel", 1.0), "ratio_bids_asks": it.get("ratio_bids_asks", 1.0),
                "fib_etiqueta": fib.get("etiqueta_fib", "N/D") if fib.get("ok") else "N/D",
                "tasa_conversion_hist_pct": tasa_cat.get(cod_s, tasa_global), "horizonte_maduracion_horas": hh, "horizonte_maduracion_dias": hd,
                "accion_matriz": accion, "dictamen_ia": f"Señal {cod_s} (blindaje {bl}%); horizonte típico {hd}d ({_formatear_demora(hh)})."
            })

    rep = {
        "etapa": "PRE_EXPLOSION", "actualizado_art": ahora_art().strftime('%Y-%m-%d %H:%M:%S ART'),
        "total_senales_historicas": len(todas), "total_monedas_historicas": len(monedas_unicas),
        "dias_registrados": len(fechas_unicas), "total_ganadoras_confirmadas": len(ganadas),
        "tasa_conversion_global_pct": tasa_global, "demora_mediana_horas": med_horas, "horizonte_tipico_dias": med_dias,
        "diagnostico_global": f"Universo de {len(todas)} señales ({len(monedas_unicas)} monedas • conversión: {tasa_global}%). Maduración media: {_formatear_demora(med_horas)}.",
        "efectividad_por_semaforo": stats_seg, "candidatas_activas_evaluadas": activas
    }
    try:
        with open(REPORTE_IA_PRE_EXPLOSION_FILE, 'w', encoding='utf-8') as f:
            json.dump(rep, f, ensure_ascii=False, indent=2)
    except Exception:
        pass
    return rep


def _generar_excel_pre_explosion(eventos, mapa_tickers, reporte_ia):
    wb = openpyxl.Workbook()
    wb.remove(wb.active)

    f_navy = PatternFill(start_color="0F172A", end_color="0F172A", fill_type="solid")
    f_slate = PatternFill(start_color="1E293B", end_color="1E293B", fill_type="solid")
    f_sub = PatternFill(start_color="F1F5F9", end_color="F1F5F9", fill_type="solid")
    f_sec = PatternFill(start_color="E2E8F0", end_color="E2E8F0", fill_type="solid")
    f_zeb = PatternFill(start_color="F8FAFC", end_color="F8FAFC", fill_type="solid")
    f_grn = PatternFill(start_color="DCFCE7", end_color="DCFCE7", fill_type="solid")
    f_amb = PatternFill(start_color="FEF9C3", end_color="FEF9C3", fill_type="solid")
    f_red = PatternFill(start_color="FEE2E2", end_color="FEE2E2", fill_type="solid")
    f_blu = PatternFill(start_color="DBEAFE", end_color="DBEAFE", fill_type="solid")
    f_gld = PatternFill(start_color="FEF3C7", end_color="FEF3C7", fill_type="solid")

    side = Side(style="thin", color="CBD5E1")
    borde = Border(left=side, right=side, top=side, bottom=side)
    sem_fills = {"🔴 ROJO": f_red, "🟡 AMARILLO": f_amb, "🟢 VERDE": f_grn, "🏆 TOP ORO": f_gld}

    filas_ord = sorted(eventos.values(), key=lambda x: (x.get("Fecha", ""), x.get("Hora", ""), x.get("Moneda", "")))
    END_ROW = 4 + max(1, len(filas_ord))
    fechas_ord = sorted({r["Fecha"] for r in filas_ord if r.get("Fecha")})
    periodos_ord = sorted({r["Fecha"][:7] for r in filas_ord if len(r.get("Fecha", "")) >= 7}) or [ahora_art().strftime("%Y-%m")]
    f_ini_fmt = datetime.strptime(fechas_ord[0], "%Y-%m-%d").strftime("%d/%m/%Y") if fechas_ord else "-"
    f_fin_fmt = datetime.strptime(fechas_ord[-1], "%Y-%m-%d").strftime("%d/%m/%Y") if fechas_ord else "-"

    coin_agg = {}
    for r in filas_ord:
        st = coin_agg.setdefault(r["Moneda"], {"rep": 0, "wins": 0, "best": 0.0})
        st["rep"] += 1
        if r.get("Estado") == "🏆 GANADORA":
            st["wins"] += 1
        p0, p1 = float(r.get("Precio_Entrada") or 0.0), float(r.get("Precio_Pico") or 0.0)
        if p0 > 0 and p1 > 0:
            st["best"] = max(st["best"], (p1 - p0) / p0)
    coin_stats = sorted(coin_agg.items(), key=lambda kv: (-kv[1]["rep"], -kv[1]["wins"], -kv[1]["best"], kv[0]))
    N_COINS = len(coin_stats)

    # PESTAÑA 1
    ws1 = wb.create_sheet("1_RESUMEN_MENSUAL_IA")
    ws1["A1"] = "PRE-EXPLOSIÓN • PANEL EJECUTIVO & RESUMEN MENSUAL IA"
    ws1["A1"].font, ws1["A1"].fill = Font(name="Arial", size=12, bold=True, color="FFFFFF"), f_navy
    ws1.merge_cells("A1:P1")
    ws1["A4"], ws1["B4"] = "MES SELECCIONADO:", periodos_ord[-1]
    ws1["B4"].fill, ws1["B4"].font, ws1["B4"].border = f_gld, Font(name="Arial", size=11, bold=True), borde
    dv = DataValidation(type="list", formula1=f'"{",".join(periodos_ord + ["TODOS"])}"', allow_blank=False)
    ws1.add_data_validation(dv)
    dv.add(ws1["B4"])

    kpis = [
        ("A", "B", "SEÑALES DEL PERÍODO", f'=IF($B$4="TODOS",COUNTA(\'3_REGISTRO_MAESTRO\'!$F$5:$F${END_ROW}),COUNTIF(\'3_REGISTRO_MAESTRO\'!$C$5:$C${END_ROW},$B$4))', "#,##0", f_sub),
        ("C", "D", "GANADORAS CONFIRMADAS", f'=IF($B$4="TODOS",COUNTIF(\'3_REGISTRO_MAESTRO\'!$Q$5:$Q${END_ROW},"🏆 GANADORA"),COUNTIFS(\'3_REGISTRO_MAESTRO\'!$C$5:$C${END_ROW},$B$4,\'3_REGISTRO_MAESTRO\'!$Q$5:$Q${END_ROW},"🏆 GANADORA"))', "#,##0", f_blu),
        ("E", "F", "CONVERSIÓN %", '=IF(A7>0,C7/A7,0)', "0.0%", f_grn),
        ("G", "H", "SUBIDA PICO PROM. %", f'=IFERROR(IF($B$4="TODOS",AVERAGEIF(\'3_REGISTRO_MAESTRO\'!$P$5:$P${END_ROW},">0"),AVERAGEIFS(\'3_REGISTRO_MAESTRO\'!$P$5:$P${END_ROW},\'3_REGISTRO_MAESTRO\'!$C$5:$C${END_ROW},$B$4,\'3_REGISTRO_MAESTRO\'!$P$5:$P${END_ROW},">0")),0)', "+0.0%;-0.0%;0.0%", f_grn),
        ("I", "J", "TIEMPO MEDIO (DÍAS)", f'=IFERROR(IF($B$4="TODOS",AVERAGEIFS(\'3_REGISTRO_MAESTRO\'!$V$5:$V${END_ROW},\'3_REGISTRO_MAESTRO\'!$Q$5:$Q${END_ROW},"🏆 GANADORA"),AVERAGEIFS(\'3_REGISTRO_MAESTRO\'!$V$5:$V${END_ROW},\'3_REGISTRO_MAESTRO\'!$C$5:$C${END_ROW},$B$4,\'3_REGISTRO_MAESTRO\'!$Q$5:$Q${END_ROW},"🏆 GANADORA")),0)', "0.00", f_amb),
        ("K", "L", "CONFLUENCIA CAZADOR", f'=IF($B$4="TODOS",COUNTIF(\'3_REGISTRO_MAESTRO\'!$X$5:$X${END_ROW},"SÍ*"),COUNTIFS(\'3_REGISTRO_MAESTRO\'!$C$5:$C${END_ROW},$B$4,\'3_REGISTRO_MAESTRO\'!$X$5:$X${END_ROW},"SÍ*"))', "#,##0", f_sub),
    ]
    for cs, ce, tit, form, fmt, fl in kpis:
        ws1[f"{cs}6"], ws1[f"{cs}6"].font, ws1[f"{cs}6"].fill = tit, Font(name="Arial", size=8.5, bold=True, color="FFFFFF"), f_slate
        ws1.merge_cells(f"{cs}6:{ce}6")
        ws1[f"{cs}7"], ws1[f"{cs}7"].font, ws1[f"{cs}7"].fill, ws1[f"{cs}7"].number_format = form, Font(name="Arial", size=14, bold=True), fl, fmt
        ws1.merge_cells(f"{cs}7:{ce}7")

    for ci, h in enumerate(["Semáforo", "Señales", "Ganadoras", "Seguimiento", "Conv. %", "Pico Prom.", "Var. Cierre", "Tiempo (d)"], 1):
        c = ws1.cell(10, ci, h)
        c.font, c.fill, c.border = Font(name="Arial", size=9, bold=True, color="FFFFFF"), f_slate, borde

    for off, (slbl, sfl) in enumerate([("🔴 ROJO", f_red), ("🟡 AMARILLO", f_amb), ("🟢 VERDE", f_grn), ("🏆 TOP ORO", f_gld)]):
        rn = 11 + off
        ws1.cell(rn, 1, slbl).fill = sfl
        ws1.cell(rn, 2, f'=IF($B$4="TODOS",COUNTIF(\'3_REGISTRO_MAESTRO\'!$G$5:$G${END_ROW},$A{rn}),COUNTIFS(\'3_REGISTRO_MAESTRO\'!$C$5:$C${END_ROW},$B$4,\'3_REGISTRO_MAESTRO\'!$G$5:$G${END_ROW},$A{rn}))')
        ws1.cell(rn, 3, f'=IF($B$4="TODOS",COUNTIFS(\'3_REGISTRO_MAESTRO\'!$G$5:$G${END_ROW},$A{rn},\'3_REGISTRO_MAESTRO\'!$Q$5:$Q${END_ROW},"🏆 GANADORA"),COUNTIFS(\'3_REGISTRO_MAESTRO\'!$C$5:$C${END_ROW},$B$4,\'3_REGISTRO_MAESTRO\'!$G$5:$G${END_ROW},$A{rn},\'3_REGISTRO_MAESTRO\'!$Q$5:$Q${END_ROW},"🏆 GANADORA"))')
        ws1.cell(rn, 4, f'=B{rn}-C{rn}')
        ws1.cell(rn, 5, f'=IF(B{rn}>0,C{rn}/B{rn},0)').number_format = "0.0%"
        ws1.cell(rn, 6, f'=IFERROR(AVERAGEIFS(\'3_REGISTRO_MAESTRO\'!$P$5:$P${END_ROW},\'3_REGISTRO_MAESTRO\'!$G$5:$G${END_ROW},$A{rn},\'3_REGISTRO_MAESTRO\'!$P$5:$P${END_ROW},">0"),0)').number_format = "+0.0%;-0.0%;0.0%"
        ws1.cell(rn, 7, f'=IFERROR(AVERAGEIFS(\'3_REGISTRO_MAESTRO\'!$T$5:$T${END_ROW},\'3_REGISTRO_MAESTRO\'!$G$5:$G${END_ROW},$A{rn},\'3_REGISTRO_MAESTRO\'!$Q$5:$Q${END_ROW},"🏆 GANADORA"),0)').number_format = "+0.0%;-0.0%;0.0%"
        ws1.cell(rn, 8, f'=IFERROR(AVERAGEIFS(\'3_REGISTRO_MAESTRO\'!$V$5:$V${END_ROW},\'3_REGISTRO_MAESTRO\'!$G$5:$G${END_ROW},$A{rn},\'3_REGISTRO_MAESTRO\'!$Q$5:$Q${END_ROW},"🏆 GANADORA"),0)').number_format = "0.00"
        for ci in range(1, 9):
            ws1.cell(rn, ci).border = borde

    chart = BarChart()
    chart.title = "Señales vs Ganadoras por Semáforo"
    chart.add_data(Reference(ws1, min_col=2, max_col=3, min_row=10, max_row=14), titles_from_data=True)
    chart.set_categories(Reference(ws1, min_col=1, min_row=11, max_row=14))
    ws1.add_chart(chart, "J9")

    # PESTAÑA 2
    ws2 = wb.create_sheet("2_RADAR_ACTIVO_IA")
    ws2["A1"] = "ASISTENTE IA • CANDIDATAS ACTIVAS PRE-EXPLOSIÓN"
    ws2["A1"].font, ws2["A1"].fill = Font(name="Arial", size=12, bold=True, color="FFFFFF"), f_navy
    ws2.merge_cells("A1:K1")
    ws2["A2"] = reporte_ia.get("diagnostico_global", "")
    ws2.merge_cells("A2:K2")
    for ci, h in enumerate(["MONEDA", "SEMÁFORO", "CERTIFICADA", "BLINDAJE", "PRECIO", "EFECTIVIDAD", "MADURACIÓN", "FIBONACCI", "BIDS/ASKS", "ACCIÓN", "DICTAMEN IA"], 1):
        c = ws2.cell(4, ci, h)
        c.font, c.fill, c.border = Font(name="Arial", size=9, bold=True, color="FFFFFF"), f_slate, borde
    for idx_r, a in enumerate(reporte_ia.get("candidatas_activas_evaluadas", [])):
        rn = 5 + idx_r
        vals = [a["ticker"], a["semaforo"], "🛡️ SÍ" if a.get("certificada_ia") else "⏳ NO", round(float(a.get("blindaje_pct", 0)) / 100.0, 4), float(a.get("precio_actual", 0.0)), round(float(a.get("tasa_conversion_hist_pct", 0)) / 100.0, 4), f"{a.get('horizonte_maduracion_dias', 2.0)}d", a.get("fib_etiqueta", "N/D"), f"{a.get('ratio_bids_asks', 1.0)}x", a.get("accion_matriz", ""), a.get("dictamen_ia", "")]
        for ci, v in enumerate(vals, 1):
            c = ws2.cell(rn, ci, v)
            c.border = borde
            if ci in (4, 6):
                c.number_format = "0.0%"

    # PESTAÑA 3
    ws3 = wb.create_sheet("3_REGISTRO_MAESTRO")
    ws3["A1"] = f"PRE-EXPLOSIÓN • REGISTRO MAESTRO UNIFICADO ({f_ini_fmt} AL {f_fin_fmt})"
    ws3["A1"].font, ws3["A1"].fill = Font(name="Arial", size=12, bold=True, color="FFFFFF"), f_navy
    ws3.merge_cells("A1:Y1")
    headers_ws3 = ["ID", "Fecha", "Período", "Mes", "Hora", "Moneda", "Semáforo Ini", "Semáforo Máx", "Escalada", "Veces", "IA %", "Fib", "Bids/Asks", "$ Entrada", "$ Pico", "Subida %", "Estado", "Fecha Win", "$ Actual/Win", "Var Real %", "Tiempo Win", "Días", "Fib 1.618", "Confluencia", "Origen"]
    for ci, h in enumerate(headers_ws3, 1):
        c = ws3.cell(4, ci, h)
        c.font, c.fill, c.border = Font(name="Arial", size=9, bold=True, color="FFFFFF"), f_slate, borde

    for idx, row in enumerate(filas_ord):
        rn = 5 + idx
        is_win = (row.get("Estado") == "🏆 GANADORA")
        p_live = float(mapa_tickers.get(_normalizar_symbol(row["Moneda"]), {}).get("lastPrice", 0) or 0.0)
        p_ent = float(row.get("Precio_Entrada") or 0.0)
        p_pico = max(float(row.get("Precio_Pico") or 0.0), p_ent, p_live)
        p_fin = float(row.get("Precio_Final") or 0.0) if is_win else (p_live if p_live > 0 else float(row.get("Precio_Final") or p_ent))
        vals = [
            idx + 1, row["Fecha"], f"=LEFT(B{rn},7)", f'=C{rn}&" • "&CHOOSE(VALUE(RIGHT(C{rn},2)),"Enero","Febrero","Marzo","Abril","Mayo","Junio","Julio","Agosto","Septiembre","Octubre","Noviembre","Diciembre")',
            row.get("Hora", "S/H"), row["Moneda"], row.get("Semaforo_Ini", "🟢 VERDE"), row.get("Semaforo_Max", "🟢 VERDE"), row.get("Escalada", "-"), f"=COUNTIF($F$5:$F${END_ROW},F{rn})",
            row["IA_Pct"] if isinstance(row.get("IA_Pct"), (int, float)) else "-", row["Fib_Zona"] if isinstance(row.get("Fib_Zona"), (int, float)) else "-",
            row["Bids_Asks"] if isinstance(row.get("Bids_Asks"), (int, float)) else "-", p_ent, p_pico, f"=IF(AND(N{rn}>0,O{rn}>0),(O{rn}-N{rn})/N{rn},0)",
            row.get("Estado", "⏳ EN SEGUIMIENTO"), row.get("Fecha_Ganadora", "-"), p_fin, f"=IF(AND(N{rn}>0,S{rn}>0),(S{rn}-N{rn})/N{rn},0)",
            row.get("Tiempo_Ganadora_Txt", "En seguimiento"), float(row["Dias_Dec"]) if isinstance(row.get("Dias_Dec"), (int, float)) else "-",
            row.get("Fib_1618", "-"), row.get("Confluencia", "Solo Pre-Explosión"), row.get("Origen", "Bot Pre-Explosión")
        ]
        for ci, val in enumerate(vals, 1):
            c = ws3.cell(rn, ci, val)
            c.border = borde
            if ci in (16, 20):
                c.number_format = "+0.00%;-0.00%;0.00%"
            if ci in (7, 8):
                c.fill = sem_fills.get(str(val), f_grn)
            elif is_win:
                c.fill = f_blu
            elif idx % 2 == 1:
                c.fill = f_zeb
    ws3.freeze_panes = "A5"
    ws3.auto_filter.ref = f"A4:Y{END_ROW}"

    # PESTAÑA 4
    ws4 = wb.create_sheet("4_RANKING_MONEDAS")
    ws4["A1"] = f"RANKING DE MONEDAS ÚNICAS ({N_COINS} ACTIVOS)"
    ws4["A1"].font, ws4["A1"].fill = Font(name="Arial", size=12, bold=True, color="FFFFFF"), f_navy
    ws4.merge_cells("A1:K1")
    for ci, h in enumerate(["N°", "Moneda", "Repeticiones", "Rojas", "Amarillas", "Verdes", "Ganadoras", "Conv %", "1ª Fecha", "Última Fecha", "Mejor Pico %"], 1):
        c = ws4.cell(4, ci, h)
        c.font, c.fill, c.border = Font(name="Arial", size=9, bold=True, color="FFFFFF"), f_slate, borde
    for idx_c, (mon, _) in enumerate(coin_stats):
        rn = 5 + idx_c
        vals = [
            idx_c + 1, mon, f"=COUNTIF('3_REGISTRO_MAESTRO'!$F$5:$F${END_ROW},B{rn})",
            f"=COUNTIFS('3_REGISTRO_MAESTRO'!$F$5:$F${END_ROW},B{rn},'3_REGISTRO_MAESTRO'!$G$5:$G${END_ROW},\"🔴 ROJO\")",
            f"=COUNTIFS('3_REGISTRO_MAESTRO'!$F$5:$F${END_ROW},B{rn},'3_REGISTRO_MAESTRO'!$G$5:$G${END_ROW},\"🟡 AMARILLO\")",
            f"=COUNTIFS('3_REGISTRO_MAESTRO'!$F$5:$F${END_ROW},B{rn},'3_REGISTRO_MAESTRO'!$G$5:$G${END_ROW},\"🟢 VERDE\")+COUNTIFS('3_REGISTRO_MAESTRO'!$F$5:$F${END_ROW},B{rn},'3_REGISTRO_MAESTRO'!$G$5:$G${END_ROW},\"🏆 TOP ORO\")",
            f"=COUNTIFS('3_REGISTRO_MAESTRO'!$F$5:$F${END_ROW},B{rn},'3_REGISTRO_MAESTRO'!$Q$5:$Q${END_ROW},\"🏆 GANADORA\")",
            f"=IF(C{rn}>0,G{rn}/C{rn},0)", f"=MINIFS('3_REGISTRO_MAESTRO'!$B$5:$B${END_ROW},'3_REGISTRO_MAESTRO'!$F$5:$F${END_ROW},B{rn})",
            f"=MAXIFS('3_REGISTRO_MAESTRO'!$B$5:$B${END_ROW},'3_REGISTRO_MAESTRO'!$F$5:$F${END_ROW},B{rn})",
            f"=IFERROR(MAXIFS('3_REGISTRO_MAESTRO'!$P$5:$P${END_ROW},'3_REGISTRO_MAESTRO'!$F$5:$F${END_ROW},B{rn}),0)"
        ]
        for ci, v in enumerate(vals, 1):
            c = ws4.cell(rn, ci, v)
            c.border = borde
            if ci in (8, 11):
                c.number_format = "0.0%"

    # PESTAÑA 5
    ws5 = wb.create_sheet("5_AUDITORIA_SETUPS")
    ws5["A1"] = "AUDITORÍA POR SEMÁFORO Y CONFLUENCIA"
    ws5["A1"].font, ws5["A1"].fill = Font(name="Arial", size=12, bold=True, color="FFFFFF"), f_navy
    ws5.merge_cells("A1:E1")
    for ci, h in enumerate(["Setup", "Señales", "Ganadoras", "Efectividad %", "Subida Pico Prom %"], 1):
        c = ws5.cell(4, ci, h)
        c.font, c.fill, c.border = Font(name="Arial", size=9, bold=True, color="FFFFFF"), f_slate, borde
    setups = [
        ("🔴 ROJO", "G", "🔴 ROJO"), ("🟡 AMARILLO", "G", "🟡 AMARILLO"),
        ("🟢 VERDE", "G", "🟢 VERDE"), ("🏆 TOP ORO", "G", "🏆 TOP ORO"),
        ("🛡️ Confluencia Cazador+Pre", "X", "SÍ (Cazador + Pre-Exp)"), ("📡 Solo Pre-Explosión", "X", "Solo Pre-Explosión")
    ]
    for idx_s, (lbl, col_l, crit) in enumerate(setups):
        rn = 5 + idx_s
        ws5.cell(rn, 1, lbl).border = borde
        ws5.cell(rn, 2, f"=COUNTIF('3_REGISTRO_MAESTRO'!${col_l}$5:${col_l}${END_ROW},\"{crit}\")").border = borde
        ws5.cell(rn, 3, f"=COUNTIFS('3_REGISTRO_MAESTRO'!${col_l}$5:${col_l}${END_ROW},\"{crit}\",'3_REGISTRO_MAESTRO'!$Q$5:$Q${END_ROW},\"🏆 GANADORA\")").border = borde
        c4 = ws5.cell(rn, 4, f"=IF(B{rn}>0,C{rn}/B{rn},0)")
        c4.border, c4.number_format = borde, "0.0%"
        c5 = ws5.cell(rn, 5, f"=IFERROR(AVERAGEIFS('3_REGISTRO_MAESTRO'!$P$5:$P${END_ROW},'3_REGISTRO_MAESTRO'!${col_l}$5:${col_l}${END_ROW},\"{crit}\",'3_REGISTRO_MAESTRO'!$P$5:$P${END_ROW},\">0\"),0)")
        c5.border, c5.number_format = borde, "+0.0%;-0.0%;0.0%"

    wb.save(EXCEL_PRE_EXPLOSION_FILE)
    ganadas_tot = sum(1 for r in filas_ord if r.get("Estado") == "🏆 GANADORA")
    return {"total": len(filas_ord), "monedas_unicas": N_COINS, "dias_hist": len(fechas_ord), "ganadas": ganadas_tot, "tasa_pct": round((ganadas_tot / len(filas_ord)) * 100, 1) if filas_ord else 0.0, "prom_txt": _formatear_demora(reporte_ia.get("demora_mediana_horas"))}


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
    except Exception:
        return False


def ejecutar_auditoria_y_excel_pre_explosion(historial, bloques, mapa_tickers):
    ahora = ahora_art()
    hoy_str, ayer_str, hora_now = ahora.strftime("%Y-%m-%d"), (ahora - timedelta(days=1)).strftime("%Y-%m-%d"), ahora.strftime("%H:%M")
    ganadoras = {"dias": {}}
    if os.path.exists(HISTORIAL_GANADORAS_FILE):
        try:
            with open(HISTORIAL_GANADORAS_FILE, "r", encoding="utf-8") as f:
                ganadoras = json.load(f)
        except Exception:
            pass

    eventos = historial.setdefault("eventos_unificados", {})
    _hidratar_desde_excels_y_json(historial, ganadoras, eventos)

    for cat in ("ROJO", "AMARILLO", "VERDE"):
        for it in (bloques.get(cat) or []):
            fib = it.get("fib_info") or {}
            sem_lbl = "🏆 TOP ORO" if (cat == "VERDE" and it.get("es_oro")) else _norm_semaforo_etiqueta(cat)
            coincide = bool(it.get("desde_posta") or it.get("en_cazador_tactico"))
            _upsert_evento_unificado(eventos, {
                "Fecha": hoy_str, "Hora": hora_now, "Moneda": it["ticker"], "Semaforo_Ini": sem_lbl, "Semaforo_Max": sem_lbl,
                "IA_Pct": round(float(it.get("blindaje_pct", 0)) / 100.0, 4), "Fib_Zona": round(float(fib.get("ratio", 0.0)), 2) if fib.get("ok") else None,
                "Bids_Asks": float(it.get("ratio_bids_asks", 0.0)) if it.get("ratio_bids_asks") else None,
                "Precio_Entrada": float(it.get("precio_f", 0.0)), "Precio_Pico": float(it.get("precio_f", 0.0)),
                "Confluencia": "SÍ (Cazador + Pre-Exp)" if coincide else "Solo Pre-Explosión", "Origen": "Cazador + Pre-Explosión" if coincide else "Bot Pre-Explosión"
            })

    dias_win = ganadoras.get("dias", {})
    precios_win = {}
    for fw, lw in dias_win.items():
        for g in (lw if isinstance(lw, list) else (list(lw.values()) if isinstance(lw, dict) else [])):
            if isinstance(g, dict) and _normalizar_symbol(g.get("symbol") or g.get("ticker")):
                precios_win.setdefault(_normalizar_symbol(g.get("symbol") or g.get("ticker")), {})[fw] = g

    for rec in eventos.values():
        f_ini, sym = rec.get("Fecha", ""), _normalizar_symbol(rec.get("Moneda"))
        if not f_ini or not sym:
            continue
        p_live = float(mapa_tickers.get(sym, {}).get("lastPrice", 0) or 0.0)
        rec["Precio_Pico"] = max(float(rec.get("Precio_Pico") or 0.0), float(rec.get("Precio_Entrada") or 0.0), p_live)
        for fw in sorted(dias_win.keys()):
            if fw >= f_ini and fw in precios_win.get(sym, {}):
                m = precios_win[sym][fw]
                rec.update({"Estado": "🏆 GANADORA", "Fecha_Ganadora": fw, "Precio_Final": float(m.get("precio") or rec["Precio_Pico"]), "Tiempo_Ganadora_Txt": "Mismo día" if fw == f_ini else f"{(datetime.strptime(fw, '%Y-%m-%d') - datetime.strptime(f_ini, '%Y-%m-%d')).days}d", "Dias_Dec": float((datetime.strptime(fw, '%Y-%m-%d') - datetime.strptime(f_ini, '%Y-%m-%d')).days)})
                break

    rep_ia = ejecutar_asistente_ia_pre_explosion(eventos, bloques)
    stats = _generar_excel_pre_explosion(eventos, mapa_tickers, rep_ia)

    ult = historial.get("ultimo_envio_excel_pre", "")
    if (ahora.hour == 23 and ahora.minute >= 30 and ult != hoy_str) or (ahora.hour <= 2 and ult != ayer_str) or (os.getenv("GITHUB_EVENT_NAME") == "workflow_dispatch"):
        cap = f"📊 <b>Excel Maestro Pre-Explosión + IA ({hoy_str})</b>\n• Universo: <b>{stats['total']} señales</b> ({stats['monedas_unicas']} monedas)\n• Ganadoras: <b>{stats['ganadas']}</b> ({stats['tasa_pct']}%)"
        if enviar_telegram_documento(EXCEL_PRE_EXPLOSION_FILE, cap):
            historial["ultimo_envio_excel_pre"] = hoy_str
    guardar_historial(historial)


def generar_grafico_color(items, titulo, subtitulo, filename):
    if not items:
        return None
    sims = [f"{'🛡️' if i.get('certificada_ia') else ('🏆' if i.get('es_oro') else '')}{i['ticker']}" for i in items]
    pos, cols = [i['pos_liquidez_pct'] for i in items], [i['color_hex'] for i in items]
    fig, ax = plt.subplots(figsize=(8.5, 4.2), facecolor='#0b132b')
    ax.set_facecolor('#0b132b')
    bars = ax.bar(sims, pos, color=cols, width=0.48, zorder=3)
    ax.grid(True, color='#1e293b', linewidth=0.8, zorder=1)
    ax.set_ylim(0, 118)
    for sp in ax.spines.values():
        sp.set_visible(False)
    ax.tick_params(left=False, labelleft=False, bottom=False)
    ax.tick_params(axis='x', colors='white', labelsize=9)
    for b, it, p, c in zip(bars, items, pos, cols):
        xv = b.get_x() + b.get_width() / 2.0
        ax.text(xv, b.get_height() + 2.5, f"{p:.0f}%", ha='center', color=c, fontweight='bold', fontsize=8.5)
        ax.text(xv, max(b.get_height() / 2.0, 13), it['ticker'][:5], ha='center', va='center', color='white', fontsize=7, fontweight='bold')
    plt.title(titulo, loc='left', color='#ffab00', fontsize=10.5, fontweight='bold', pad=12)
    ax.text(0.0, 1.02, subtitulo, transform=ax.transAxes, color='#94a3b8', fontsize=8)
    plt.tight_layout()
    plt.savefig(filename, dpi=300, facecolor=fig.get_facecolor())
    plt.close()
    return filename


def generar_dictamen_color(cat, items):
    if not items or not GEMINI_API_KEY:
        return f"Lectura {cat}: foco en confluencia Cazador+PreExplosión, libro de órdenes y Fibonacci."
    client = genai.Client(api_key=GEMINI_API_KEY)
    txt = "\n".join([f"- {i['ticker']} (1h {i['cambio_1h']:+.1f}%, 24h {i['cambio_f']:+.1f}%)" for i in items])
    for mod in MODELOS_GEMINI_PRE:
        try:
            r = client.models.generate_content(model=mod, contents=f"Dictamen Spot breve (2 líneas) bloque {cat}:\n{txt}")
            if r and r.text:
                return r.text.strip()
        except Exception:
            continue
    return f"Lectura {cat}: foco en confluencia Cazador+PreExplosión, libro de órdenes y Fibonacci."


def enviar_telegram_foto(path, caption):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "caption": caption[:1020], "parse_mode": "HTML"}
    if TELEGRAM_TOPIC_ID.isdigit():
        payload["message_thread_id"] = int(TELEGRAM_TOPIC_ID)
    try:
        with open(path, 'rb') as f:
            res = requests.post(url, data=payload, files={"photo": f}, timeout=45).json()
            if not res.get("ok") and "thread not found" in str(res.get("description", "")).lower():
                payload.pop("message_thread_id", None)
                f.seek(0)
                requests.post(url, data=payload, files={"photo": f}, timeout=45)
    except Exception:
        pass


def enviar_texto_telegram(texto):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": texto.strip(), "parse_mode": "HTML", "disable_web_page_preview": True}
    if TELEGRAM_TOPIC_ID.isdigit():
        payload["message_thread_id"] = int(TELEGRAM_TOPIC_ID)
    try:
        res = requests.post(url, json=payload, timeout=30).json()
        if not res.get("ok") and "thread not found" in str(res.get("description", "")).lower():
            payload.pop("message_thread_id", None)
            requests.post(url, json=payload, timeout=30)
    except Exception:
        pass


def enviar_mensaje_por_color(num_msg, cat_key, titulo_color, items, total_analizadas):
    fecha_str = ahora_art().strftime('%Y-%m-%d %H:%M ART')
    if not items:
        enviar_texto_telegram(f"🔥 <b>PRE-EXPLOSIÓN ({num_msg}/3)</b>\n{titulo_color}\n📅 <code>{fecha_str}</code>\n\n⏳ <i>Sin monedas en este bloque.</i>")
        return

    fname = f"pre_explosion_{cat_key.lower()}.png"
    generar_grafico_color(items, f"PRE-EXPLOSION ({num_msg}/3) - {cat_key}", f"Fecha: {fecha_str} | Analizadas: {total_analizadas} Spot", fname)
    dictamen = generar_dictamen_color(cat_key, items)
    enviar_telegram_foto(fname, f"🔥 <b>PRE-EXPLOSIÓN ({num_msg}/3)</b>\n{titulo_color}\n📅 <code>{fecha_str}</code>")
    time.sleep(1)

    cuerpo = f"💡 <i>{html.escape(dictamen)}</i>\n\n"
    for item in items:
        sim = item['ticker']
        uid = int(time.time() * 1000) + random.randint(1, 9999)
        url_ia = f"{BASE_URL_NETLIFY}/?coin={sim}&price={item['precio_f']}&change={item['cambio_f']}&high={item['high_f']}&low={item['low_f']}&v={sim}_{uid}"
        url_tr = f"https://www.binance.com/es/trade/{sim}_USDT"
        extra = f" 🏆 <b>[ORO | Rango: {item['pos_liquidez_pct']:.0f}%]</b>" if item.get("es_oro") else (" ⭐⭐⭐ [Posta Roja]" if item.get("desde_posta") else "")
        sello = f"🛡️ <b>CERTIFICADA IA ({item['blindaje_pct']}%)</b>" if item.get("certificada_ia") else f"⏳ <i>Observación IA ({item['blindaje_pct']}%)</i>"
        fib = item.get("fib_info", {})
        lfib = f"  • <i>{html.escape(fib['etiqueta_fib'])}</i> | Ext 1.618: <code>{formatear_precio(fib['ext_1618'])}</code>\n" if fib.get("ok") else ""
        cuerpo += f"• <b>{sim}</b>{extra} (1h: {item['cambio_1h']:+.1f}% | 4h: {item['cambio_4h']:+.1f}% | 24h: {item['cambio_f']:+.1f}%) | <code>{formatear_precio(item['precio_f'])}</code>\n  • {sello} — <i>{html.escape(item.get('motivo_certificacion', ''))}</i>\n{lfib}  └ <a href=\"{html.escape(url_ia)}\">📊 Resumen IA</a> | <a href=\"{html.escape(url_tr)}\">🔶 Tradear</a>\n\n"
    enviar_texto_telegram(cuerpo)


def main():
    print(f"🔥 EJECUTANDO PRE-EXPLOSIÓN V11 + EXCEL MAESTRO ({ahora_art().strftime('%Y-%m-%d %H:%M:%S')} ART)...", flush=True)
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

        if ahora_art().hour >= 21 and not historial.get("resumen_enviado_hoy", False):
            md = [s[:-4] if s.endswith('USDT') else s for s in historial.get("resumen_dia", [])]
            mo = [s[:-4] if s.endswith('USDT') else s for s in historial.get("oro_hoy", [])]
            if md:
                enviar_texto_telegram(f"📋 <b>RESUMEN DIARIO PRE-EXPLOSIÓN (21:00 ART)</b>\n📅 <i>{ahora_art().strftime('%Y-%m-%d')}</i>\n\n🏆 <b>Oro hoy:</b> <code>{', '.join(mo) if mo else 'Ninguna'}</code>\nRadar hoy: <code>{', '.join(md)}</code>")
                historial["resumen_enviado_hoy"] = True
                guardar_historial(historial)

        ejecutar_auditoria_y_excel_pre_explosion(historial, bloques, mapa_tickers)
        print("✅ CICLO COMPLETADO EXITOSAMENTE.", flush=True)
    else:
        print("❌ ERROR: Sin datos o símbolos activos de Binance.", flush=True)


if __name__ == "__main__":
    main()
