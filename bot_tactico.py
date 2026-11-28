import os
import re
import sys
import json
import time
import random
import html
import subprocess
from collections import Counter
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
from google import genai

TZ_ART = timezone(timedelta(hours=-3))
TELEGRAM_BOT_TOKEN = (os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("TELEGRAM_TOKEN") or "").strip()
TELEGRAM_CHAT_ID = (os.getenv("TELEGRAM_CHAT_ID") or os.getenv("CHAT_ID") or "").strip()
TELEGRAM_TOPIC_ID = (os.getenv("TOPIC_ID_TACTICO") or os.getenv("TOPIC_ID_CENTRAL") or "4").strip()
GEMINI_API_KEY = (os.getenv("GEMINI_API_KEY") or "").strip()
BASE_URL_NETLIFY = "https://gregarious-frangollo-0346c5.netlify.app"

HISTORIAL_FILE = "historial_perlas.json"
HISTORIAL_GANADORAS_FILE = "historial_ganadoras.json"
MAESTRO_BASE_FILE = "CAZADOR_TACTICO_MAESTRO_UNIFICADO.xlsx"
EXCEL_TACTICO_FILE = "HISTORICO_CAZADOR_TACTICO.xlsx"
REPORTE_IA_TACTICO_FILE = "reporte_ia_tactico.json"

DIAS_SEGUIMIENTO = 12
MODELOS_GEMINI_TACTICO = ["gemini-2.5-flash", "gemini-2.5-flash-lite"]

EXCL_RADAR = {
    'USDT', 'USDC', 'FDUSD', 'DAI', 'TUSD', 'USDP', 'EUR', 'BUSD', 'USD1', 'AEUR', 'EURI', 'USDE',
    'RLUSD', 'RWUSD', 'XUSD', 'BFUSD', 'U', 'USDG', 'USDS', 'PYUSD', 'PAXG', 'XAUT', 'GBP', 'TRY', 'BRL', 'ARS',
    'BTC', 'ETH', 'SOL', 'ADA', 'XRP', 'DOGE', 'TRX', 'SHIB', 'AVAX', 'LINK', 'BNB', 'DOT', 'NEAR', 'SUI', 'PEPE',
    'UNI', 'HBAR', 'FIL', 'XLM', 'ATOM', 'ICP', 'AAVE', 'LTC', 'BCH', 'ETC', 'APT', 'ARB', 'OP', 'INJ', 'RENDER',
    'TON', 'SEI', 'TIA', 'STX', 'IMX', 'VET', 'ALGO', 'GRT', 'THETA', 'FTM', 'RUNE', 'MKR', 'LDO', 'QNT',
    'KAS', 'TAO', 'FET', 'WIF', 'BONK', 'FLOKI', 'ENA', 'WLD', 'ONDO', 'JUP', 'PYTH', 'STRK', 'ZK', 'EIGEN'
}


def ahora_art():
    return datetime.now(TZ_ART)


def cargar_historial():
    hoy = ahora_art().strftime('%Y-%m-%d')
    base = {
        "fecha": hoy,
        "mencionadas": {},
        "resumen_dia": [],
        "resumen_enviado_hoy": False,
        "ultimo_envio_excel": "",
        "posta": {},
        "graduadas_pre_explosion": {},
        "verdes_hoy": [],
        "oro_hoy": [],
        "historial_completo": {}
    }
    if os.path.exists(HISTORIAL_FILE):
        try:
            with open(HISTORIAL_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)

            base["ultimo_envio_excel"] = data.get("ultimo_envio_excel", "")
            hist_comp = data.get("historial_completo")
            base["historial_completo"] = hist_comp if isinstance(hist_comp, dict) else {}

            raw_posta = data.get("posta") or data.get("secuencia") or data.get("seguimiento_verde") or {}
            posta_limpia = {}
            for sym, info in raw_posta.items():
                base_sym = sym[:-4] if sym.endswith("USDT") else sym
                if base_sym in EXCL_RADAR:
                    continue
                try:
                    f_det = datetime.strptime(info.get("fecha_iso", hoy), '%Y-%m-%d').date()
                    dias_activa = (ahora_art().date() - f_det).days
                    etapa = int(info.get("etapa", info.get("paso", info.get("estrellas", 1))))
                    max_dias = 7 if etapa == 3 else DIAS_SEGUIMIENTO
                    if dias_activa <= max_dias:
                        p_ini = float(info.get("precio_inicio", info.get("precio_deteccion", 0.0)))
                        if p_ini > 0 and etapa >= 1:
                            info["precio_inicio"] = p_ini
                            info["etapa"] = min(3, etapa)
                            info["paso"] = info["etapa"]
                            info["estrellas"] = info["etapa"]
                            posta_limpia[sym] = info
                except Exception:
                    continue
            base["posta"] = posta_limpia

            grad_limpia = {}
            for sym, info in data.get("graduadas_pre_explosion", {}).items():
                try:
                    f_det = datetime.strptime(info.get("fecha_iso", hoy), '%Y-%m-%d').date()
                    if (ahora_art().date() - f_det).days <= DIAS_SEGUIMIENTO:
                        grad_limpia[sym] = info
                except Exception:
                    continue
            base["graduadas_pre_explosion"] = grad_limpia

            if data.get("fecha") == hoy:
                base["mencionadas"] = data.get("mencionadas", {})
                base["resumen_dia"] = data.get("resumen_dia", [])
                base["resumen_enviado_hoy"] = data.get("resumen_enviado_hoy", False)
                base["verdes_hoy"] = data.get("verdes_hoy", [])
                base["oro_hoy"] = data.get("oro_hoy", [])
        except Exception as e:
            print(f"⚠️ Error cargando {HISTORIAL_FILE}: {e}")
    return base


def guardar_historial(historial):
    try:
        with open(HISTORIAL_FILE, 'w', encoding='utf-8') as f:
            json.dump(historial, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"⚠️ Error guardando historial: {e}")


def inyectar_rojo_en_auditoria_excel(sym, base, p_act, motivo):
    hoy_iso = ahora_art().strftime('%Y-%m-%d')
    ts_now = ahora_art().strftime('%Y-%m-%d %H:%M')
    data_g = {
        "ultima_actualizacion": ts_now,
        "dias": {},
        "ultimo_reporte_semanal": "",
        "registro_verdes": {}
    }
    if os.path.exists(HISTORIAL_GANADORAS_FILE):
        try:
            with open(HISTORIAL_GANADORAS_FILE, 'r', encoding='utf-8') as f:
                loaded = json.load(f)
            if isinstance(loaded, dict):
                data_g = loaded
        except Exception:
            pass

    reg = data_g.setdefault("registro_verdes", {})
    if sym not in reg:
        reg[sym] = {
            "symbol": sym,
            "ticker": base,
            "fecha_verde": hoy_iso,
            "ts_verde": ts_now,
            "precio_verde": float(p_act),
            "es_oro": False,
            "origen": "CAZADOR_TACTICO_ROJO",
            "estado": "PENDIENTE",
            "fecha_ganadora": "",
            "precio_ganadora": 0.0,
            "subida_real_pct": 0.0,
            "subida_24h_dia_pct": 0.0,
            "dias_demora": None
        }
        try:
            with open(HISTORIAL_GANADORAS_FILE, 'w', encoding='utf-8') as f:
                json.dump(data_g, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"⚠️ Error inyectando en {HISTORIAL_GANADORAS_FILE}: {e}")


def crear_sesion_binance():
    s = requests.Session()
    s.headers.update({"User-Agent": "Mozilla/5.0", "Accept": "application/json", "Cache-Control": "no-cache"})
    return s


def obtener_datos_binance(session):
    activos, tickers = set(), []
    for url in ["https://api.binance.com/api/v3/exchangeInfo", "https://data-api.binance.vision/api/v3/exchangeInfo"]:
        try:
            r = session.get(url, timeout=12)
            if r.status_code == 200:
                activos = {
                    s['symbol'] for s in r.json().get('symbols', [])
                    if s.get('status') == 'TRADING' and s.get('isSpotTradingAllowed', True) and s.get('quoteAsset') == 'USDT'
                }
                if activos:
                    break
        except Exception:
            continue
    for url in ["https://api.binance.com/api/v3/ticker/24hr", "https://data-api.binance.vision/api/v3/ticker/24hr"]:
        try:
            r = session.get(url, timeout=15)
            if r.status_code == 200 and isinstance(r.json(), list) and r.json():
                tickers = r.json()
                break
        except Exception:
            continue
    return activos, tickers


def calcular_ema(vals, p):
    if not vals:
        return 0.0
    k = 2 / (p + 1)
    ema = vals[0]
    for v in vals[1:]:
        ema = (v * k) + (ema * (1 - k))
    return ema


def calcular_rsi(cierres, p=14):
    if len(cierres) <= p:
        return 50.0
    deltas = [cierres[i] - cierres[i - 1] for i in range(1, len(cierres))]
    g = [d if d > 0 else 0.0 for d in deltas]
    per = [-d if d < 0 else 0.0 for d in deltas]
    ag, ap = sum(g[:p]) / p, sum(per[:p]) / p
    for i in range(p, len(g)):
        ag = (ag * (p - 1) + g[i]) / p
        ap = (ap * (p - 1) + per[i]) / p
    return 100.0 if ap == 0 else round(100.0 - (100.0 / (1.0 + (ag / ap))), 1)


def auditar_order_book_tactico(session, symbol):
    """Verifica liquidez real en libro de órdenes (spread y proporción compra/venta)."""
    for base_url in ["https://api.binance.com", "https://data-api.binance.vision"]:
        try:
            r = session.get(f"{base_url}/api/v3/depth", params={"symbol": symbol, "limit": 20}, timeout=5)
            if r.status_code == 200:
                d = r.json()
                bids, asks = d.get("bids", []), d.get("asks", [])
                if not bids or not asks:
                    continue
                b0, a0 = float(bids[0][0]), float(asks[0][0])
                spread = ((a0 - b0) / b0) * 100 if b0 > 0 else 99.0
                vb = sum(float(x[0]) * float(x[1]) for x in bids)
                va = sum(float(x[0]) * float(x[1]) for x in asks)
                ratio = round(vb / va, 2) if va > 0 else 1.0
                return {"ok": True, "spread_pct": round(spread, 3), "ratio_ba": ratio, "sano": (spread <= 0.50 and ratio >= 0.72)}
        except Exception:
            continue
    return {"ok": False, "spread_pct": 0.1, "ratio_ba": 1.0, "sano": True}


def analizar_historia_y_tecnico(session, symbol):
    for base_url in ["https://api.binance.com", "https://data-api.binance.vision"]:
        try:
            r1d = session.get(f"{base_url}/api/v3/klines", params={"symbol": symbol, "interval": "1d", "limit": 150}, timeout=8)
            r4h = session.get(f"{base_url}/api/v3/klines", params={"symbol": symbol, "interval": "4h", "limit": 36}, timeout=7)
            r1h = session.get(f"{base_url}/api/v3/klines", params={"symbol": symbol, "interval": "1h", "limit": 25}, timeout=7)
            r15m = session.get(f"{base_url}/api/v3/klines", params={"symbol": symbol, "interval": "15m", "limit": 10}, timeout=7)
            if r1d.status_code == 200 and r1h.status_code == 200 and r15m.status_code == 200:
                k1d, k1h, k15m = r1d.json(), r1h.json(), r15m.json()
                k4h = r4h.json() if r4h.status_code == 200 else []
                if len(k1d) < 20 or len(k1h) < 15:
                    continue

                c1d = [float(x[4]) for x in k1d]
                l1d = [float(x[3]) for x in k1d]
                h1d = [float(x[2]) for x in k1d]
                v1d = [float(x[7]) for x in k1d]

                p_act = c1d[-1]
                min_hist = min(l1d)
                max_hist = max(h1d)
                dist_min_pct = round(((p_act - min_hist) / min_hist) * 100, 1) if min_hist > 0 else 0.0
                rango_hist = max_hist - min_hist
                pos_rango_pct = round(((p_act - min_hist) / rango_hist) * 100, 1) if rango_hist > 0 else 50.0

                vol_1d_rec = sum(v1d[-3:]) / 3.0
                vol_1d_base = sum(v1d[-23:-3]) / 20.0 if len(v1d) >= 23 else vol_1d_rec
                vol_1d_ratio = round(vol_1d_rec / vol_1d_base, 2) if vol_1d_base > 0 else 1.0

                if pos_rango_pct <= 35:
                    estructura_1d = "Suelo / Base 1d"
                elif pos_rango_pct <= 60:
                    estructura_1d = "Recuperación 1d"
                else:
                    estructura_1d = "Tramo Alto 1d"

                # Geometría Fibonacci 4H
                fib_tag = "Fib N/D"
                fib_sano = True
                if len(k4h) >= 12:
                    hi4 = max(float(x[2]) for x in k4h)
                    lo4 = min(float(x[3]) for x in k4h)
                    rng4 = hi4 - lo4
                    if rng4 > 0:
                        rat_fib = round((hi4 - p_act) / rng4, 2)
                        if 0.35 <= rat_fib <= 0.65:
                            fib_tag = f"Zona Dorada Fib ({rat_fib:.2f})"
                        elif rat_fib < 0.08:
                            fib_tag = f"Extendida Fib ({rat_fib:.2f})"
                            fib_sano = False
                        else:
                            fib_tag = f"Fib ({rat_fib:.2f})"

                c1h = [float(x[4]) for x in k1h]
                v1h = [float(x[7]) for x in k1h]
                o1h, cl1h = float(k1h[-1][1]), c1h[-1]
                o15, cl15 = float(k15m[-1][1]), float(k15m[-1][4])

                var_1h = round(((cl1h - o1h) / o1h) * 100, 2) if o1h > 0 else 0.0
                var_15m = round(((cl15 - o15) / o15) * 100, 2) if o15 > 0 else 0.0
                rsi_1h = calcular_rsi(c1h, 14)
                ema7, ema21 = calcular_ema(c1h[-15:], 7), calcular_ema(c1h, 21)

                v_rec = sum(v1h[-2:]) / 2.0
                v_prev = sum(v1h[-12:-2]) / 10.0 if len(v1h) >= 12 else v_rec
                vol_surge = round(v_rec / v_prev, 2) if v_prev > 0 else 1.0

                prob = 20.0
                prob += 28 if vol_surge >= 1.8 else (20 if vol_surge >= 1.3 else (12 if vol_surge >= 1.05 else 0))
                prob += 15 if vol_1d_ratio >= 1.25 else (8 if vol_1d_ratio >= 0.95 else 0)
                if cl1h > ema7 > ema21:
                    ema_est, prob = "Alcista (P>EMA7>EMA21)", prob + 18
                elif cl1h > ema7:
                    ema_est, prob = "Cruce Inicial (>EMA7)", prob + 11
                else:
                    ema_est, prob = "Acumulando Base", prob + 5
                prob += 12 if 45.0 <= rsi_1h <= 66.0 else (7 if 38.0 <= rsi_1h < 45.0 else 0)
                prob += 10 if (var_1h > 0.0 and var_15m >= 0.0) else (4 if var_1h >= -0.3 else 0)
                if not fib_sano:
                    prob -= 10

                return {
                    "ok": True,
                    "probabilidad_pct": min(98, max(10, int(round(prob)))),
                    "var_1h": var_1h,
                    "var_15m": var_15m,
                    "rsi_1h": rsi_1h,
                    "ema_estado": ema_est,
                    "vol_surge": vol_surge,
                    "estructura_1d": estructura_1d,
                    "pos_rango_pct": pos_rango_pct,
                    "dist_min_pct": dist_min_pct,
                    "vol_1d_ratio": vol_1d_ratio,
                    "fib_tag": fib_tag,
                    "fib_sano": fib_sano
                }
        except Exception:
            continue
    return {"ok": False, "probabilidad_pct": 0}


def certificar_graduacion_ia(session, sym, base, tec, var_seq):
    """
    GESTOR CERTIFICADOR IA ETAPA 1:
    Verifica Order Book + Fibonacci + Gemini antes de graduar una moneda a Rojo (⭐⭐⭐)
    y enviarla hacia Pre-Explosión y Cartera Semanal.
    """
    ob = auditar_order_book_tactico(session, sym)
    if not ob.get("sano", True) or not tec.get("fib_sano", True):
        return False, 45, f"Bloqueada por blindaje (OB ratio {ob['ratio_ba']}x, {tec.get('fib_tag', '')})"

    blindaje = min(98, int(tec["probabilidad_pct"] + (8 if ob["ratio_ba"] >= 1.1 else 0)))
    nota_cert = f"Certificada Etapa 1 ({tec.get('fib_tag', '')} | OB {ob['ratio_ba']}x)"

    if GEMINI_API_KEY:
        try:
            client = genai.Client(api_key=GEMINI_API_KEY)
            prompt = (
                "Eres el Gestor Certificador IA de Etapa 1 (Cazador Táctico) en Binance Spot. "
                "Una moneda está a punto de graduarse a ROJO (⭐⭐⭐) para pasar a Pre-Explosión y Cartera Semanal. "
                "Evalúa si los datos coinciden y son seguros (sin FOMO ni falta de liquidez):\n"
                f"Moneda: {base} | Avance secuencia: {var_seq:+.2f}% | Probabilidad: {tec['probabilidad_pct']}% | "
                f"Estructura: {tec['estructura_1d']} | {tec.get('fib_tag', '')} | RSI 1h: {tec['rsi_1h']} | "
                f"Vol 1h: x{tec['vol_surge']} | Order Book Bids/Asks: {ob['ratio_ba']}x (Spread {ob['spread_pct']}%)\n\n"
                'Responde SOLO en JSON válido: {"aprobar":true,"blindaje_pct":84,"motivo":"resumen técnico corto de 1 línea"}'
            )
            for mod in MODELOS_GEMINI_TACTICO:
                try:
                    res = client.models.generate_content(model=mod, contents=prompt)
                    if res and res.text:
                        raw = res.text.strip()
                        if "{" in raw and "}" in raw:
                            raw = raw[raw.find("{"):raw.rfind("}") + 1]
                        d = json.loads(raw)
                        aprobar = bool(d.get("aprobar", True))
                        blindaje = int(d.get("blindaje_pct", blindaje))
                        if d.get("motivo"):
                            nota_cert = str(d["motivo"])[:125]
                        return aprobar, blindaje, nota_cert
                except Exception:
                    continue
        except Exception:
            pass

    return True, blindaje, nota_cert


def formatear_precio(p):
    if p is None or p <= 0:
        return "$0.00"
    if p >= 100:
        return f"${p:,.2f}"
    if p >= 1.0:
        return f"${p:.4f}"
    if p >= 0.01:
        return f"${p:.5f}"
    if p >= 0.0001:
        return f"${p:.6f}"
    return f"${p:.8f}"


def gemini_destacar_verdes(candidatos):
    if not candidatos:
        return {}, "Sin monedas ocultas en Verde en este ciclo."

    ordenados = sorted(candidatos, key=lambda x: (x.get("probabilidad_pct", 0), x.get("vol_1d_ratio", 1.0)), reverse=True)
    defecto = {
        x["base"]: f"Destacada 1⭐ ({x['estructura_1d']}, +{x['dist_min_pct']}% vs suelo 1d, RSI {x['rsi_1h']})."
        for x in ordenados[:2]
    }
    dictamen = "Etapa 1 + Certificador IA: 1⭐ Verde -> 2⭐⭐ Amarillo -> 3⭐⭐⭐ Rojo Blindado (pasa a Etapa 2)."

    if not GEMINI_API_KEY:
        return defecto, dictamen

    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
        lineas = "\n".join([
            f"- {x['base']}: prob={x['probabilidad_pct']}%, 1d={x['estructura_1d']} ({x.get('fib_tag', '')}), vol1d=x{x['vol_1d_ratio']}, vol1h=x{x['vol_surge']}, 1h={x['var_1h']:+.2f}%, RSI={x['rsi_1h']}"
            for x in ordenados[:10]
        ])
        prompt = (
            "Sos un analista cuantitativo buscando altcoins fuera del radar masivo. De estas monedas en VERDE, marcá con 1 estrella (hasta 2 monedas) "
            "las que tengan mejor acumulación silenciosa en suelo/base para iniciar la posta (Verde -> Amarillo -> Rojo -> Pre-Explosión).\n"
            f"Monedas verdes:\n{lineas}\n\n"
            'Responde SOLO JSON válido: {"destacadas_verde":[{"symbol":"S1","motivo":"..."}],"dictamen":"..."}'
        )
        for mod in MODELOS_GEMINI_TACTICO:
            try:
                res = client.models.generate_content(model=mod, contents=prompt)
                if res and res.text:
                    raw = res.text.strip()
                    if "{" in raw and "}" in raw:
                        raw = raw[raw.find("{"):raw.rfind("}") + 1]
                    data = json.loads(raw)
                    mapa = {x["base"]: x for x in ordenados}
                    picks = {}
                    for d in (data.get("destacadas_verde") or [])[:2]:
                        s = str(d.get("symbol", "")).strip().upper()
                        m = str(d.get("motivo", "")).strip()
                        if s in mapa:
                            picks[s] = (m or defecto.get(s) or "Destacada por Gemini (1⭐)")[:95]
                    if picks:
                        return picks, str(data.get("dictamen") or dictamen)[:140]
            except Exception:
                continue
    except Exception as e:
        print(f"⚠️ Fallback Gemini: {e}")
    return defecto, dictamen


def pasa_filtro_amarillo(tec, var_seq):
    return (
        var_seq >= -3.0
        and tec["rsi_1h"] <= 70.0
        and (
            tec["probabilidad_pct"] >= 52
            or tec["vol_surge"] >= 1.20
            or tec["vol_1d_ratio"] >= 1.15
            or tec["var_1h"] >= 0.30
        )
    )


def pasa_filtro_rojo(tec, var_seq):
    return (
        var_seq >= -1.0
        and tec["rsi_1h"] <= 73.0
        and tec["probabilidad_pct"] >= 68
        and (tec["vol_surge"] >= 1.15 or tec["vol_1d_ratio"] >= 1.15)
    )


def ejecutar_posta_colores(session, tickers, activos, historial):
    menc = historial.get("mencionadas", {})
    for sym in list(menc.keys()):
        menc[sym] -= 1
        if menc[sym] <= 0:
            del menc[sym]

    mapa = {}
    cand = []
    for t in tickers:
        sym = t.get('symbol', '')
        if not sym.endswith('USDT') or sym not in activos:
            continue
        base = sym[:-4]
        if base in EXCL_RADAR or not re.match(r'^[A-Z0-9]+$', base) or base.endswith('B') or any(x in base for x in ['UP', 'DOWN', 'BULL', 'BEAR']):
            continue
        try:
            p, chg, vol, hi, lo = float(t['lastPrice']), float(t['priceChangePercent']), float(t['quoteVolume']), float(t['highPrice']), float(t['lowPrice'])
            if p <= 0:
                continue
            b24 = (p / (1.0 + (chg / 100.0))) if chg > -99.9 else float(t.get('openPrice', p))
            pres = (vol / 1_000_000) / max(((hi - lo) / p) * 100, 1.0)
            it = {'symbol': sym, 'base': base, 'base_24h_f': b24, 'precio_f': p, 'cambio_f': chg, 'vol_f': vol, 'high_f': hi, 'low_f': lo, 'presion': pres}
            mapa[sym] = it
            if sym not in menc and (0.000001 <= p < 5.00 and 600_000 <= vol <= 25_000_000 and -3.0 <= chg <= 6.5):
                cand.append(it)
        except Exception:
            continue

    posta = historial.get("posta", {})
    grad = historial.get("graduadas_pre_explosion", {})
    verdes_hoy = set(historial.get("verdes_hoy", []))
    hoy_iso, hoy_corta = ahora_art().strftime('%Y-%m-%d'), ahora_art().strftime('%d/%m')
    alertas = []

    for sym in list(posta.keys()):
        info = posta[sym]
        mkt = mapa.get(sym)
        if not mkt:
            continue
        tec = analizar_historia_y_tecnico(session, sym)
        if not tec["ok"]:
            continue

        p_act = float(mkt["precio_f"])
        p_ini = float(info.get("precio_inicio", p_act))
        var_seq = ((p_act - p_ini) / p_ini) * 100 if p_ini > 0 else 0.0

        if var_seq < -8.0 or (int(info.get("etapa", 1)) == 3 and var_seq >= 16.0):
            del posta[sym]
            continue

        etapa_prev = int(info.get("etapa", 1))
        etapa_nueva = etapa_prev
        motivo_etapa = info.get("motivo", "")

        if etapa_prev == 1:
            if pasa_filtro_amarillo(tec, var_seq):
                etapa_nueva = 2
                motivo_etapa = f"Pasó filtro Amarillo (2⭐⭐): {var_seq:+.1f}% vs base, Vol 1h x{tec['vol_surge']} | {tec.get('fib_tag', '')}."
                if not info.get("alerta_a2", False):
                    info["alerta_a2"] = True
                    alertas.append({
                        "base": sym[:-4], "etapa": 2, "prob": tec["probabilidad_pct"],
                        "fecha_corta": info.get("fecha_corta", hoy_corta),
                        "p_ini": p_ini, "p_act": p_act, "var_seq": var_seq,
                        "mkt": mkt, "tec": tec, "motivo": motivo_etapa
                    })
        elif etapa_prev == 2:
            if pasa_filtro_rojo(tec, var_seq):
                aprobada_ia, blindaje_e1, nota_e1 = certificar_graduacion_ia(session, sym, sym[:-4], tec, var_seq)
                if aprobada_ia:
                    etapa_nueva = 3
                    info["certificada_etapa1"] = True
                    info["blindaje_etapa1"] = blindaje_e1
                    motivo_etapa = f"🛡️ Certificada IA ({blindaje_e1}%): {nota_e1}"
                    if not info.get("alerta_a3", False):
                        info["alerta_a3"] = True
                        alertas.append({
                            "base": sym[:-4], "etapa": 3, "prob": blindaje_e1,
                            "fecha_corta": info.get("fecha_corta", hoy_corta),
                            "p_ini": p_ini, "p_act": p_act, "var_seq": var_seq,
                            "mkt": mkt, "tec": tec, "motivo": motivo_etapa
                        })
                else:
                    motivo_etapa = f"⏳ Retenida en Amarillo por Certificador IA: {nota_e1}"

        if etapa_nueva == 3:
            verdes_hoy.add(sym)
            grad[sym] = {
                "symbol": sym,
                "base": sym[:-4],
                "estrellas": 3,
                "probabilidad_pct": int(info.get("blindaje_etapa1", tec["probabilidad_pct"])),
                "precio_ref": p_act,
                "fecha_iso": hoy_iso,
                "fecha_corta": hoy_corta,
                "origen": "CAZADOR_TACTICO_ROJO",
                "certificada_etapa1": True,
                "blindaje_etapa1": int(info.get("blindaje_etapa1", tec["probabilidad_pct"]))
            }
            inyectar_rojo_en_auditoria_excel(sym, sym[:-4], p_act, motivo_etapa)

        info.update({
            "etapa": etapa_nueva,
            "paso": etapa_nueva,
            "estrellas": etapa_nueva,
            "prob_actual": tec["probabilidad_pct"],
            "precio_actual": p_act,
            "var_seq": round(var_seq, 2),
            "motivo": motivo_etapa,
            "tec": tec
        })
        posta[sym] = info

    cand_verdes = []
    for it in sorted(cand, key=lambda x: x["presion"], reverse=True)[:24]:
        if it["symbol"] in posta:
            continue
        tec = analizar_historia_y_tecnico(session, it["symbol"])
        if tec["ok"] and 35 <= tec["probabilidad_pct"] <= 55:
            it.update(tec)
            cand_verdes.append(it)

    picks_1star, dictamen = gemini_destacar_verdes(cand_verdes)

    for it in cand_verdes:
        sym, base = it["symbol"], it["base"]
        if base in picks_1star and sym not in posta:
            posta[sym] = {
                "symbol": sym,
                "base": base,
                "fecha_iso": hoy_iso,
                "fecha_corta": hoy_corta,
                "precio_inicio": it["precio_f"],
                "precio_actual": it["precio_f"],
                "prob_inicio": it["probabilidad_pct"],
                "prob_actual": it["probabilidad_pct"],
                "var_seq": 0.0,
                "etapa": 1,
                "paso": 1,
                "estrellas": 1,
                "motivo": picks_1star[base],
                "tec": {
                    "var_1h": it["var_1h"],
                    "rsi_1h": it["rsi_1h"],
                    "ema_estado": it["ema_estado"],
                    "vol_surge": it["vol_surge"],
                    "estructura_1d": it["estructura_1d"],
                    "vol_1d_ratio": it["vol_1d_ratio"],
                    "fib_tag": it.get("fib_tag", "")
                },
                "alerta_a2": False,
                "alerta_a3": False
            }
        menc[sym] = 1
        if sym not in historial["resumen_dia"]:
            historial["resumen_dia"].append(sym)

    verdes_fmt, amarillas_fmt, rojas_fmt = [], [], []

    for it in cand_verdes[:7]:
        sym, base = it["symbol"], it["base"]
        en_p1 = sym in posta and int(posta[sym].get("etapa", 1)) == 1
        d_p = posta.get(sym, {})
        verdes_fmt.append({
            "symbol": sym,
            "base": base,
            "estrellas": 1 if en_p1 else 0,
            "probabilidad_pct": it["probabilidad_pct"],
            "precio_inicio": float(d_p.get("precio_inicio", it["precio_f"])),
            "precio_f": it["precio_f"],
            "base_24h_f": it["base_24h_f"],
            "cambio_f": it["cambio_f"],
            "high_f": it["high_f"],
            "low_f": it["low_f"],
            "var_seq": float(d_p.get("var_seq", 0.0)),
            "fecha_corta": d_p.get("fecha_corta", hoy_corta),
            "motivo_ia": d_p.get("motivo", "") if en_p1 else "",
            "var_1h": it["var_1h"],
            "rsi_1h": it["rsi_1h"],
            "vol_surge": it["vol_surge"],
            "estructura_1d": it["estructura_1d"],
            "fib_tag": it.get("fib_tag", ""),
            "color_hex": "#00e676"
        })

    for sym, d in posta.items():
        mkt = mapa.get(sym)
        if not mkt:
            continue
        tec = d.get("tec") or analizar_historia_y_tecnico(session, sym)
        p_ini = float(d.get("precio_inicio", mkt["precio_f"]))
        p_act = float(mkt["precio_f"])
        var_real = ((p_act - p_ini) / p_ini) * 100 if p_ini > 0 else 0.0
        etapa = int(d.get("etapa", 1))

        item_posta = {
            "symbol": sym,
            "base": sym[:-4],
            "estrellas": etapa,
            "probabilidad_pct": int(d.get("blindaje_etapa1", d.get("prob_actual", tec.get("probabilidad_pct", 50)))),
            "precio_inicio": p_ini,
            "precio_f": p_act,
            "base_24h_f": mkt["base_24h_f"],
            "cambio_f": mkt["cambio_f"],
            "high_f": mkt["high_f"],
            "low_f": mkt["low_f"],
            "var_seq": round(var_real, 2),
            "fecha_corta": d.get("fecha_corta", hoy_corta),
            "motivo_ia": d.get("motivo", ""),
            "var_1h": tec.get("var_1h", 0.0),
            "rsi_1h": tec.get("rsi_1h", 50.0),
            "vol_surge": tec.get("vol_surge", 1.0),
            "estructura_1d": tec.get("estructura_1d", "1d"),
            "fib_tag": tec.get("fib_tag", ""),
            "color_hex": "#ffd600" if etapa == 2 else "#ff1744"
        }
        if etapa == 2:
            amarillas_fmt.append(item_posta)
        elif etapa == 3:
            rojas_fmt.append(item_posta)

    rojas_fmt.sort(key=lambda x: x["probabilidad_pct"], reverse=True)
    amarillas_fmt.sort(key=lambda x: x["probabilidad_pct"], reverse=True)

    historial.update({
        "mencionadas": menc,
        "posta": posta,
        "graduadas_pre_explosion": grad,
        "verdes_hoy": sorted(list(verdes_hoy))
    })
    guardar_historial(historial)
    return {"ROJO": rojas_fmt[:8], "AMARILLO": amarillas_fmt[:8], "VERDE": verdes_fmt}, historial, dictamen, alertas, mapa


# ==============================================================================
# HISTORIAL COMPLETO PERMANENTE + BACKFILL DE RENDIMIENTO REAL (BINANCE KLINES)
# ==============================================================================
def _evaluar_evolucion_historica_binance(session, sym, fecha_iso, p_inicio, p_actual_mkt):
    """Mide drawdown mínimo previo al rebote y máxima subida real alcanzada desde la detección."""
    try:
        dt_ini = datetime.strptime(fecha_iso, '%Y-%m-%d').replace(tzinfo=TZ_ART)
        start_ms = int(dt_ini.timestamp() * 1000)
    except Exception:
        return None

    for base_url in ["https://api.binance.com", "https://data-api.binance.vision"]:
        try:
            r = session.get(
                f"{base_url}/api/v3/klines",
                params={"symbol": sym, "interval": "1h", "startTime": start_ms, "limit": 120},
                timeout=7
            )
            if r.status_code == 200:
                kl = r.json()
                if not kl or p_inicio <= 0:
                    continue
                highs = [float(x[2]) for x in kl]
                lows = [float(x[3]) for x in kl]
                closes = [float(x[4]) for x in kl]

                max_p = max(highs + ([p_actual_mkt] if p_actual_mkt > 0 else []))
                min_p = min(lows + ([p_actual_mkt] if p_actual_mkt > 0 else []))
                max_gain = round(((max_p - p_inicio) / p_inicio) * 100, 2)
                max_dd = round(((min_p - p_inicio) / p_inicio) * 100, 2)

                ret_24h = round(((closes[min(23, len(closes) - 1)] - p_inicio) / p_inicio) * 100, 2) if len(closes) >= 12 else None
                ret_48h = round(((closes[min(47, len(closes) - 1)] - p_inicio) / p_inicio) * 100, 2) if len(closes) >= 36 else None
                ret_72h = round(((closes[min(71, len(closes) - 1)] - p_inicio) / p_inicio) * 100, 2) if len(closes) >= 60 else None

                return {
                    "precio_max": round(max_p, 8),
                    "precio_min": round(min_p, 8),
                    "max_gain_pct": max_gain,
                    "max_dd_pct": max_dd,
                    "ret_24h_pct": ret_24h,
                    "ret_48h_pct": ret_48h,
                    "ret_72h_pct": ret_72h
                }
        except Exception:
            continue
    return None


def _cargar_filas_excel_en_historial(hist_comp):
    """Carga todas las filas existentes de `3_REGISTRO_MAESTRO` en `hist_comp` sin perder ningún dato."""
    base_source = None
    for candidate in [EXCEL_TACTICO_FILE, MAESTRO_BASE_FILE]:
        if candidate and os.path.exists(candidate):
            base_source = candidate
            break
    if not base_source:
        return

    try:
        wb = openpyxl.load_workbook(base_source, data_only=True)
        if "3_REGISTRO_MAESTRO" not in wb.sheetnames:
            return
        ws = wb["3_REGISTRO_MAESTRO"]
        for r in range(5, ws.max_row + 1):
            fec = ws.cell(r, 2).value
            mon = ws.cell(r, 6).value
            if not fec or not mon:
                continue
            fecha = str(fec)[:10].strip()
            moneda = str(mon).strip().upper()
            if not fecha or not moneda:
                continue
            sym = f"{moneda}USDT"
            key = f"{sym}_{fecha}"

            cat = str(ws.cell(r, 7).value or "VERDE").strip().upper()
            etapa_lbl = str(ws.cell(r, 8).value or "").strip()
            if "ROJ" in cat or "3⭐⭐⭐" in etapa_lbl:
                etapa_max = 3
                etiqueta_etapa = etapa_lbl or "3⭐⭐⭐ ROJO CERTIFICADO"
            elif "AMAR" in cat or "2⭐⭐" in etapa_lbl:
                etapa_max = 2
                etiqueta_etapa = etapa_lbl or "2⭐⭐ AMARILLO"
            else:
                etapa_max = 1
                etiqueta_etapa = etapa_lbl or "1⭐ VERDE"

            p_ini = float(ws.cell(r, 9).value or 0.0)
            p_max = float(ws.cell(r, 14).value or 0.0)
            max_gain_raw = ws.cell(r, 15).value
            max_dd_raw = ws.cell(r, 16).value
            ret_24h_raw = ws.cell(r, 19).value
            ret_48h_raw = ws.cell(r, 20).value
            est_1d = str(ws.cell(r, 21).value or "").strip()
            fib_tag = str(ws.cell(r, 22).value or "").strip()
            rsi_1h = ws.cell(r, 23).value
            res_aud = str(ws.cell(r, 24).value or "").strip()
            paso_pre = str(ws.cell(r, 25).value or "").strip()
            operada = str(ws.cell(r, 26).value or "").strip()
            origen = str(ws.cell(r, 27).value or "").strip()

            max_gain_pct = round(float(max_gain_raw) * 100.0, 2) if isinstance(max_gain_raw, (int, float)) else (
                round(((p_max - p_ini) / p_ini) * 100.0, 2) if (p_ini > 0 and p_max > 0) else 0.0
            )
            max_dd_pct = round(float(max_dd_raw) * 100.0, 2) if isinstance(max_dd_raw, (int, float)) else 0.0

            entry = hist_comp.get(key, {})
            entry.update({
                "id": key,
                "symbol": sym,
                "ticker": moneda,
                "fecha_deteccion": fecha,
                "etapa_max": max(int(entry.get("etapa_max", 1)), etapa_max),
                "etiqueta_etapa": etiqueta_etapa,
                "precio_inicio": p_ini if p_ini > 0 else float(entry.get("precio_inicio") or 0.0),
                "precio_actual": float(entry.get("precio_actual") or p_max or p_ini or 0.0),
                "precio_max": max(float(entry.get("precio_max") or 0.0), p_max, p_ini),
                "max_gain_pct": max(float(entry.get("max_gain_pct") or 0.0), max_gain_pct),
                "max_dd_pct": max_dd_pct,
                "ret_24h_pct": round(float(ret_24h_raw) * 100.0, 2) if isinstance(ret_24h_raw, (int, float)) else entry.get("ret_24h_pct"),
                "ret_48h_pct": round(float(ret_48h_raw) * 100.0, 2) if isinstance(ret_48h_raw, (int, float)) else entry.get("ret_48h_pct"),
                "estructura_1d": est_1d or entry.get("estructura_1d") or "1d",
                "fib_tag": fib_tag or entry.get("fib_tag") or "",
                "rsi_1h": float(rsi_1h) if isinstance(rsi_1h, (int, float)) else entry.get("rsi_1h", 50.0),
                "resultado_real": res_aud or entry.get("resultado_real") or "EN_MADURACION (<=3d)",
                "paso_pre_exp": paso_pre or entry.get("paso_pre_exp") or ("SÍ (Pre-Exp)" if etapa_max == 3 else "NO"),
                "operada_trader": operada or entry.get("operada_trader") or "NO",
                "origen_dato": origen or entry.get("origen_dato") or "Bot Cazador Táctico",
            })
            hist_comp[key] = entry
    except Exception as e:
        print(f"⚠️ Error cargando filas históricas desde Excel: {e}")


def actualizar_historial_completo_tactico(session, historial, mapa_mkt):
    """Consolida todas las alertas históricas sin borrarlas jamás y audita su resultado real."""
    hist_comp = historial.setdefault("historial_completo", {})
    _cargar_filas_excel_en_historial(hist_comp)

    hoy_iso = ahora_art().strftime('%Y-%m-%d')
    hoy_dt = ahora_art().date()

    for sym, info in historial.get("graduadas_pre_explosion", {}).items():
        f_iso = info.get("fecha_iso", hoy_iso)
        key = f"{sym}_{f_iso}"
        if key not in hist_comp and float(info.get("precio_ref", 0.0)) > 0:
            hist_comp[key] = {
                "id": key,
                "symbol": sym,
                "ticker": info.get("base", sym[:-4]),
                "fecha_deteccion": f_iso,
                "etapa_max": int(info.get("estrellas", 3)),
                "etiqueta_etapa": "3⭐⭐⭐ ROJO CERTIFICADO",
                "precio_inicio": float(info.get("precio_ref", 0.0)),
                "precio_actual": float(info.get("precio_ref", 0.0)),
                "probabilidad": int(info.get("probabilidad_pct", 70)),
                "estructura_1d": "Recuperación / Base",
                "fib_tag": "Fib Auditado",
                "rsi_1h": 55.0,
                "vol_surge": 1.2,
                "motivo": info.get("origen", "GRADUADA_HISTORICA"),
                "auditada_completa": False
            }

    if os.path.exists(HISTORIAL_GANADORAS_FILE):
        try:
            with open(HISTORIAL_GANADORAS_FILE, 'r', encoding='utf-8') as f:
                dg = json.load(f)
            for sym, rinfo in (dg.get("registro_verdes") or {}).items():
                if rinfo.get("origen") == "CAZADOR_TACTICO_ROJO":
                    f_iso = rinfo.get("fecha_verde", hoy_iso)
                    key = f"{sym}_{f_iso}"
                    p_ref = float(rinfo.get("precio_verde") or 0.0)
                    if key not in hist_comp and p_ref > 0:
                        hist_comp[key] = {
                            "id": key,
                            "symbol": sym,
                            "ticker": rinfo.get("ticker", sym[:-4]),
                            "fecha_deteccion": f_iso,
                            "etapa_max": 3,
                            "etiqueta_etapa": "3⭐⭐⭐ ROJO CERTIFICADO",
                            "precio_inicio": p_ref,
                            "precio_actual": p_ref,
                            "probabilidad": 75,
                            "estructura_1d": "Suelo / Base 1d",
                            "fib_tag": "Fib Auditado",
                            "rsi_1h": 55.0,
                            "vol_surge": 1.3,
                            "motivo": "Importada de Auditoría Excel",
                            "auditada_completa": False
                        }
        except Exception:
            pass

    for sym, info in historial.get("posta", {}).items():
        f_iso = info.get("fecha_iso", hoy_iso)
        key = f"{sym}_{f_iso}"
        etapa = int(info.get("etapa", 1))
        etiqueta = "3⭐⭐⭐ ROJO CERTIFICADO" if etapa == 3 else ("2⭐⭐ AMARILLO" if etapa == 2 else "1⭐ VERDE")
        tec = info.get("tec") or {}
        p_ini = float(info.get("precio_inicio", 0.0))
        p_act = float(info.get("precio_actual", p_ini))

        if key not in hist_comp:
            hist_comp[key] = {
                "id": key,
                "symbol": sym,
                "ticker": sym[:-4],
                "fecha_deteccion": f_iso,
                "etapa_max": etapa,
                "etiqueta_etapa": etiqueta,
                "precio_inicio": p_ini,
                "precio_actual": p_act,
                "probabilidad": int(info.get("blindaje_etapa1", info.get("prob_actual", 50))),
                "estructura_1d": tec.get("estructura_1d", "1d"),
                "fib_tag": tec.get("fib_tag", ""),
                "rsi_1h": tec.get("rsi_1h", 50.0),
                "vol_surge": tec.get("vol_surge", 1.0),
                "motivo": info.get("motivo", ""),
                "auditada_completa": False
            }
        else:
            reg = hist_comp[key]
            if etapa >= int(reg.get("etapa_max", 1)):
                reg["etapa_max"] = etapa
                reg["etiqueta_etapa"] = etiqueta
            if p_act > 0:
                reg["precio_actual"] = p_act
            reg["probabilidad"] = max(int(reg.get("probabilidad", 50)), int(info.get("blindaje_etapa1", info.get("prob_actual", 50))))
            if info.get("motivo"):
                reg["motivo"] = info["motivo"]
            if tec.get("estructura_1d"):
                reg["estructura_1d"] = tec["estructura_1d"]
            if tec.get("fib_tag"):
                reg["fib_tag"] = tec["fib_tag"]

    actualizaciones_klines = 0
    for key, reg in hist_comp.items():
        sym = reg["symbol"]
        mkt = mapa_mkt.get(sym, {})
        p_act = float(mkt.get("precio_f") or reg.get("precio_actual") or 0.0)
        if p_act > 0:
            reg["precio_actual"] = p_act
        p_ini = float(reg.get("precio_inicio") or 0.0)
        if p_ini <= 0:
            continue

        try:
            d_det = datetime.strptime(reg["fecha_deteccion"], '%Y-%m-%d').date()
            dias_trans = (hoy_dt - d_det).days
        except Exception:
            dias_trans = 0

        if not reg.get("auditada_completa") and actualizaciones_klines < 35:
            ev = _evaluar_evolucion_historica_binance(session, sym, reg["fecha_deteccion"], p_ini, p_act)
            actualizaciones_klines += 1
            if ev:
                reg.update(ev)
                if dias_trans >= 5:
                    reg["auditada_completa"] = True

        var_actual = round(((p_act - p_ini) / p_ini) * 100, 2) if p_act > 0 else 0.0
        reg["var_actual_pct"] = var_actual
        max_g = float(reg.get("max_gain_pct") if reg.get("max_gain_pct") is not None else max(0.0, var_actual))
        max_dd = float(reg.get("max_dd_pct") if reg.get("max_dd_pct") is not None else min(0.0, var_actual))
        reg["max_gain_pct"] = max_g
        reg["max_dd_pct"] = max_dd

        if not reg.get("resultado_real"):
            if max_g >= 8.0:
                reg["resultado_real"] = "REBOTE_EXITOSO (>=+8%)"
            elif max_g >= 4.0:
                reg["resultado_real"] = "AVANCE_MODERADO (+4% a +8%)"
            elif dias_trans <= 3:
                reg["resultado_real"] = "EN_MADURACION (<=3d)"
            elif max_dd <= -7.0:
                reg["resultado_real"] = "INVALIDADA (<-7%)"
            else:
                reg["resultado_real"] = "LATERAL_SIN_IMPULSO"

    guardar_historial(historial)
    return hist_comp


# ==============================================================================
# ASISTENTE IA DEDICADO: CAZADOR TÁCTICO (CALIBRACIÓN DE SETUPS Y STOPS)
# ==============================================================================
def ejecutar_asistente_ia_tactico(hist_comp, grupos):
    registros = list(hist_comp.values())
    total = len(registros)

    exitosos = [r for r in registros if r.get("max_gain_pct", 0.0) >= 6.0]
    tasa_exito = round((len(exitosos) / total) * 100, 1) if total > 0 else 0.0
    prom_max_gain = round(sum(r.get("max_gain_pct", 0.0) for r in registros) / total, 2) if total > 0 else 0.0

    dds_ganadoras = [abs(r.get("max_dd_pct", 0.0)) for r in exitosos if r.get("max_dd_pct") is not None]
    dd_tipico_rebote = round(sorted(dds_ganadoras)[len(dds_ganadoras) // 2], 2) if dds_ganadoras else 3.8
    stop_sugerido_global = round(min(7.5, max(3.5, dd_tipico_rebote + 1.2)), 1)

    stats_etapas = []
    for et, nombre_et in [(3, "3⭐⭐⭐ ROJO CERTIFICADO"), (2, "2⭐⭐ AMARILLO"), (1, "1⭐ VERDE")]:
        sub = [r for r in registros if int(r.get("etapa_max", 1)) == et]
        if sub:
            ok_sub = [r for r in sub if r.get("max_gain_pct", 0.0) >= 6.0]
            dds_sub = [abs(r.get("max_dd_pct", 0.0)) for r in ok_sub] or [abs(r.get("max_dd_pct", 0.0)) for r in sub]
            dd_med = round(sorted(dds_sub)[len(dds_sub) // 2], 2) if dds_sub else 3.5
            stats_etapas.append({
                "categoria": nombre_et,
                "cantidad": len(sub),
                "aciertos_6pct": len(ok_sub),
                "efectividad_pct": round((len(ok_sub) / len(sub)) * 100, 1),
                "max_gain_prom_pct": round(sum(r.get("max_gain_pct", 0.0) for r in sub) / len(sub), 2),
                "dd_previo_mediano_pct": -dd_med,
                "stop_optimo_pct": -round(min(7.5, max(3.5, dd_med + 1.2)), 1)
            })

    stats_estructuras = []
    for est_1d in ["Suelo / Base 1d", "Recuperación 1d", "Tramo Alto 1d"]:
        sub = [r for r in registros if est_1d.lower() in str(r.get("estructura_1d", "")).lower()]
        if sub:
            ok_sub = [r for r in sub if r.get("max_gain_pct", 0.0) >= 6.0]
            dds_sub = [abs(r.get("max_dd_pct", 0.0)) for r in sub]
            dd_med = round(sorted(dds_sub)[len(dds_sub) // 2], 2) if dds_sub else 3.5
            stats_estructuras.append({
                "categoria": est_1d,
                "cantidad": len(sub),
                "aciertos_6pct": len(ok_sub),
                "efectividad_pct": round((len(ok_sub) / len(sub)) * 100, 1),
                "max_gain_prom_pct": round(sum(r.get("max_gain_pct", 0.0) for r in sub) / len(sub), 2),
                "dd_previo_mediano_pct": -dd_med,
                "stop_optimo_pct": -round(min(7.5, max(3.5, dd_med + 1.2)), 1)
            })

    activas_eval = []
    vistas = set()
    for grp_name in ["ROJO", "AMARILLO", "VERDE"]:
        for it in grupos.get(grp_name, []):
            sym = it["symbol"]
            if sym in vistas:
                continue
            vistas.add(sym)
            est = int(it.get("estrellas", 0))
            stop_coin = -stop_sugerido_global if est >= 2 else -round(stop_sugerido_global + 0.8, 1)
            accion = (
                "APTA_ENTRADA_ESCALONADA" if grp_name == "ROJO"
                else ("EN_OBSERVACION_PRE_ROJO" if grp_name == "AMARILLO" else "RADAR_TEMPRANO_NO_FORZAR")
            )
            activas_eval.append({
                "symbol": sym,
                "ticker": it["base"],
                "etapa_actual": grp_name,
                "estrellas": est,
                "blindaje_pct": it.get("probabilidad_pct", 50),
                "precio_inicio": it.get("precio_inicio", it.get("precio_f", 0.0)),
                "precio_actual": it.get("precio_f", 0.0),
                "var_seq_pct": it.get("var_seq", 0.0),
                "estructura_1d": it.get("estructura_1d", ""),
                "fib_tag": it.get("fib_tag", ""),
                "rsi_1h": it.get("rsi_1h", 50.0),
                "vol_surge": it.get("vol_surge", 1.0),
                "stop_sugerido_pct": stop_coin,
                "horizonte_horas": 48 if grp_name == "ROJO" else 72,
                "accion_matriz": accion,
                "dictamen_ia": it.get("motivo_ia") or f"Setup {grp_name} en {it.get('estructura_1d', '1d')} con stop calibrado en {stop_coin}%."
            })

    diagnostico_global = (
        f"Base histórica de {total} señales tácticas auditadas (efectividad rebote >=6%: {tasa_exito}%). "
        f"Las operaciones ganadoras retroceden en mediana -{dd_tipico_rebote}% antes de despegar, por lo que el stop óptimo calibrado es -{stop_sugerido_global}%."
    )

    if GEMINI_API_KEY and (activas_eval or stats_etapas):
        try:
            client = genai.Client(api_key=GEMINI_API_KEY)
            resumen_stats = "\n".join([
                f"- {s['categoria']}: {s['cantidad']} señales, efectividad {s['efectividad_pct']}%, máx gain prom +{s['max_gain_prom_pct']}%, DD previo {s['dd_previo_mediano_pct']}%"
                for s in (stats_etapas + stats_estructuras)
            ])
            resumen_act = "\n".join([
                f"- {a['ticker']} ({a['etapa_actual']}, blindaje {a['blindaje_pct']}%): var {a['var_seq_pct']:+.1f}%, {a['estructura_1d']}, {a['fib_tag']}, RSI {a['rsi_1h']}"
                for a in activas_eval[:10]
            ])
            prompt = (
                "Sos el Asistente IA de Etapa 1 (CAZADOR TÁCTICO) en Binance Spot. "
                "Analizá el historial real y las señales activas, y devolvé SOLO JSON válido:\n"
                '{"diagnostico_global":"2 oraciones concretas sobre qué setups funcionan mejor y qué stop usar para evitar barridas", '
                '"dictamenes":{"TICKER":"recomendación táctica de 1 línea con gestión de riesgo"}}\n\n'
                f"Estadísticas reales:\n{resumen_stats}\n\nSeñales activas:\n{resumen_act}"
            )
            for mod in MODELOS_GEMINI_TACTICO:
                try:
                    resp = client.models.generate_content(model=mod, contents=prompt)
                    if resp and resp.text:
                        raw = resp.text.strip()
                        raw = re.sub(r'^```(?:json)?\s*|\s*```$', '', raw).strip()
                        parsed = json.loads(raw)
                        if isinstance(parsed, dict):
                            if parsed.get("diagnostico_global"):
                                diagnostico_global = str(parsed["diagnostico_global"]).strip()
                            d_map = parsed.get("dictamenes") or {}
                            for a in activas_eval:
                                if a["ticker"] in d_map:
                                    a["dictamen_ia"] = str(d_map[a["ticker"]]).strip()
                        break
                except Exception:
                    continue
        except Exception as e:
            print(f"⚠️ Fallback Asistente IA Táctico: {e}")

    reporte_json = {
        "etapa": "CAZADOR_TACTICO",
        "actualizado_art": ahora_art().strftime('%Y-%m-%d %H:%M:%S ART'),
        "total_senales_historicas": total,
        "tasa_exito_6pct": tasa_exito,
        "prom_max_gain_pct": prom_max_gain,
        "dd_tipico_previo_rebote_pct": -dd_tipico_rebote,
        "stop_optimo_sugerido_pct": -stop_sugerido_global,
        "diagnostico_global": diagnostico_global,
        "auditoria_por_etapa": stats_etapas,
        "auditoria_por_estructura": stats_estructuras,
        "senales_activas_evaluadas": activas_eval
    }

    try:
        with open(REPORTE_IA_TACTICO_FILE, 'w', encoding='utf-8') as f:
            json.dump(reporte_json, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"⚠️ Error guardando {REPORTE_IA_TACTICO_FILE}: {e}")

    return reporte_json


# ==============================================================================
# ACTUALIZACIÓN INCREMENTAL DEL EXCEL MAESTRO UNIFICADO (5 HOJAS)
# ==============================================================================
def _map_etapa_a_cat(etiqueta_etapa: str) -> str:
    up = str(etiqueta_etapa or "").upper()
    if "ROJ" in up or "3⭐⭐⭐" in up:
        return "ROJA"
    if "AMAR" in up or "2⭐⭐" in up:
        return "AMARILLA"
    return "VERDE"


def generar_excel_tactico(hist_comp, reporte_ia):
    """
    Actualiza el libro unificado de 5 hojas (`1_RESUMEN_MENSUAL_IA`, `2_RADAR_ACTIVO_IA`,
    `3_REGISTRO_MAESTRO`, `4_RANKING_MONEDAS`, `5_AUDITORIA_SETUPS`) preservando todos
    los datos existentes sin borrar ni pisar valores no nulos.
    """
    base_source = None
    for candidate in [EXCEL_TACTICO_FILE, MAESTRO_BASE_FILE]:
        if candidate and os.path.exists(candidate):
            base_source = candidate
            break

    if not base_source:
        raise FileNotFoundError(f"No se encontró {MAESTRO_BASE_FILE} ni {EXCEL_TACTICO_FILE}")

    wb = openpyxl.load_workbook(base_source)

    required_sheets = {
        "1_RESUMEN_MENSUAL_IA",
        "2_RADAR_ACTIVO_IA",
        "3_REGISTRO_MAESTRO",
        "4_RANKING_MONEDAS",
        "5_AUDITORIA_SETUPS",
    }
    if not required_sheets.issubset(set(wb.sheetnames)) and os.path.exists(MAESTRO_BASE_FILE):
        wb = openpyxl.load_workbook(MAESTRO_BASE_FILE)

    ws_rad = wb["2_RADAR_ACTIVO_IA"]
    ws_reg = wb["3_REGISTRO_MAESTRO"]
    ws_mon = wb["4_RANKING_MONEDAS"]
    ws_aud = wb["5_AUDITORIA_SETUPS"]

    # 1. Refrescar `2_RADAR_ACTIVO_IA`
    act_list = reporte_ia.get("senales_activas_evaluadas", [])
    ws_rad["A2"] = (
        f"Diagnóstico Global IA ({reporte_ia.get('actualizado_art', '')}): "
        f"{reporte_ia.get('diagnostico_global', '')}"
    )
    max_rad_rows = max(45, ws_rad.max_row - 4)
    for idx in range(max_rad_rows):
        r = 5 + idx
        if idx < len(act_list):
            a = act_list[idx]
            ws_rad.cell(r, 1).value = a["ticker"]
            ws_rad.cell(r, 2).value = a["etapa_actual"]
            ws_rad.cell(r, 3).value = round(float(a["blindaje_pct"]) / 100.0, 4)
            ws_rad.cell(r, 4).value = float(a["precio_inicio"])
            ws_rad.cell(r, 5).value = float(a["precio_actual"])
            ws_rad.cell(r, 6).value = f"=IF(D{r}>0,(E{r}-D{r})/D{r},0)"
            ws_rad.cell(r, 7).value = a["estructura_1d"]
            ws_rad.cell(r, 8).value = a["fib_tag"]
            ws_rad.cell(r, 9).value = round(float(a["stop_sugerido_pct"]) / 100.0, 4)
            ws_rad.cell(r, 10).value = a["accion_matriz"]
            ws_rad.cell(r, 11).value = a["dictamen_ia"]
        else:
            for c_i in range(1, 12):
                ws_rad.cell(r, c_i).value = None

    # 2. Deduplicar e insertar/actualizar señales en `3_REGISTRO_MAESTRO` sin perder datos
    existing_by_key = {}
    last_used_row = 4
    for r in range(5, ws_reg.max_row + 1):
        fec = ws_reg.cell(r, 2).value
        mon = ws_reg.cell(r, 6).value
        if fec and mon:
            key = (str(fec)[:10].strip(), str(mon).strip().upper())
            existing_by_key[key] = r
            if r > last_used_row:
                last_used_row = r

    next_row = last_used_row + 1
    hora_actual = ahora_art().strftime("%H:%M")

    registros_ord = sorted(
        hist_comp.values(),
        key=lambda x: (x.get("fecha_deteccion", ""), x.get("etapa_max", 1))
    )

    for reg in registros_ord:
        fecha = str(reg.get("fecha_deteccion") or ahora_art().strftime("%Y-%m-%d"))[:10].strip()
        moneda = str(reg.get("ticker") or (reg.get("symbol", "")[:-4] if str(reg.get("symbol", "")).endswith("USDT") else reg.get("symbol", ""))).strip().upper()
        if not moneda or not fecha:
            continue

        key = (fecha, moneda)
        p_ini = float(reg.get("precio_inicio") or 0.0)
        p_act = float(reg.get("precio_actual") or p_ini)
        p_max = float(reg.get("precio_max") or max(p_ini, p_act))
        max_dd = round(float(reg.get("max_dd_pct") or 0.0) / 100.0, 4)
        ret_24h = round(float(reg["ret_24h_pct"]) / 100.0, 4) if reg.get("ret_24h_pct") is not None else None
        ret_48h = round(float(reg["ret_48h_pct"]) / 100.0, 4) if reg.get("ret_48h_pct") is not None else None
        cat = _map_etapa_a_cat(reg.get("etiqueta_etapa", ""))
        etapa_lbl = str(reg.get("etiqueta_etapa") or f"{reg.get('etapa_max', 1)}⭐")
        res_aud = str(reg.get("resultado_real") or "EN_MADURACION (<=3d)")

        if key in existing_by_key:
            r = existing_by_key[key]
            if p_ini > 0 and ws_reg.cell(r, 9).value is None:
                ws_reg.cell(r, 9).value = p_ini
            prev_pmax = ws_reg.cell(r, 14).value
            if p_max > 0 and (prev_pmax is None or float(prev_pmax) < p_max):
                ws_reg.cell(r, 14).value = p_max
            if cat == "ROJA" or ws_reg.cell(r, 7).value is None:
                ws_reg.cell(r, 7).value = cat
            if etapa_lbl and ws_reg.cell(r, 8).value is None:
                ws_reg.cell(r, 8).value = etapa_lbl
            if ws_reg.cell(r, 16).value is None and max_dd != 0:
                ws_reg.cell(r, 16).value = max_dd
            if ret_24h is not None and ws_reg.cell(r, 19).value is None:
                ws_reg.cell(r, 19).value = ret_24h
            if ret_48h is not None and ws_reg.cell(r, 20).value is None:
                ws_reg.cell(r, 20).value = ret_48h
            if reg.get("estructura_1d") and ws_reg.cell(r, 21).value is None:
                ws_reg.cell(r, 21).value = reg.get("estructura_1d")
            if reg.get("fib_tag") and ws_reg.cell(r, 22).value is None:
                ws_reg.cell(r, 22).value = reg.get("fib_tag")
            if reg.get("rsi_1h") is not None and ws_reg.cell(r, 23).value is None:
                ws_reg.cell(r, 23).value = reg.get("rsi_1h")
            if res_aud and ws_reg.cell(r, 24).value is None:
                ws_reg.cell(r, 24).value = res_aud
            if cat == "ROJA":
                ws_reg.cell(r, 25).value = "SÍ (Pre-Exp)"
        else:
            r = next_row
            next_row += 1
            existing_by_key[key] = r

            if not ws_reg.cell(r, 1).value:
                ws_reg.cell(r, 1).value = f'=IF(F{r}="","",ROW()-4)'
            if not ws_reg.cell(r, 3).value:
                ws_reg.cell(r, 3).value = f'=IF(B{r}="","",IF(ISNUMBER(B{r}),TEXT(B{r},"yyyy-mm"),LEFT(B{r},7)))'
            if not ws_reg.cell(r, 4).value:
                ws_reg.cell(r, 4).value = f'=IF(C{r}="","",C{r}&" • "&CHOOSE(VALUE(RIGHT(C{r},2)),"Enero","Febrero","Marzo","Abril","Mayo","Junio","Julio","Agosto","Septiembre","Octubre","Noviembre","Diciembre"))'
            if not ws_reg.cell(r, 15).value:
                ws_reg.cell(r, 15).value = f'=IF(AND(ISNUMBER(I{r}),ISNUMBER(N{r}),I{r}>0),(N{r}-I{r})/I{r},"")'

            ws_reg.cell(r, 2).value = fecha
            ws_reg.cell(r, 5).value = hora_actual
            ws_reg.cell(r, 6).value = moneda
            ws_reg.cell(r, 7).value = cat
            ws_reg.cell(r, 8).value = etapa_lbl
            ws_reg.cell(r, 9).value = p_ini if p_ini > 0 else None
            ws_reg.cell(r, 10).value = 0.0
            ws_reg.cell(r, 11).value = reg.get("vol_surge")
            ws_reg.cell(r, 12).value = None
            ws_reg.cell(r, 13).value = "LATERAL"
            ws_reg.cell(r, 14).value = p_max if p_max > 0 else None
            ws_reg.cell(r, 16).value = max_dd
            ws_reg.cell(r, 17).value = 0.0
            ws_reg.cell(r, 18).value = "LATERAL"
            ws_reg.cell(r, 19).value = ret_24h
            ws_reg.cell(r, 20).value = ret_48h
            ws_reg.cell(r, 21).value = reg.get("estructura_1d")
            ws_reg.cell(r, 22).value = reg.get("fib_tag")
            ws_reg.cell(r, 23).value = reg.get("rsi_1h")
            ws_reg.cell(r, 24).value = res_aud
            ws_reg.cell(r, 25).value = "SÍ (Pre-Exp)" if cat == "ROJA" else "NO"
            ws_reg.cell(r, 26).value = "NO"
            ws_reg.cell(r, 27).value = "Bot Cazador Táctico"

    # 3. Reordenar `4_RANKING_MONEDAS` por recurrencia histórica conservando fórmulas
    counts = Counter(k[1] for k in existing_by_key.keys())
    ranked_coins = sorted(counts.keys(), key=lambda c: (-counts[c], c))
    for idx in range(500):
        r = 5 + idx
        ws_mon.cell(r, 2).value = ranked_coins[idx] if idx < len(ranked_coins) else None

    # 4. Actualizar Tabla 1 de `5_AUDITORIA_SETUPS` sin tocar la Tabla 2 dinámica
    filas_set = reporte_ia.get("auditoria_por_etapa", []) + reporte_ia.get("auditoria_por_estructura", [])
    for idx, st in enumerate(filas_set[:6]):
        r = 6 + idx
        ws_aud.cell(r, 1).value = st["categoria"]
        ws_aud.cell(r, 2).value = int(st["cantidad"])
        ws_aud.cell(r, 3).value = int(st["aciertos_6pct"])
        ws_aud.cell(r, 4).value = f"=IF(B{r}>0,C{r}/B{r},0)"
        ws_aud.cell(r, 5).value = round(float(st["max_gain_prom_pct"]) / 100.0, 4)
        ws_aud.cell(r, 6).value = round(float(st["dd_previo_mediano_pct"]) / 100.0, 4)
        ws_aud.cell(r, 7).value = round(float(st["stop_optimo_pct"]) / 100.0, 4)

    wb.save(EXCEL_TACTICO_FILE)
    if MAESTRO_BASE_FILE and MAESTRO_BASE_FILE != EXCEL_TACTICO_FILE:
        wb.save(MAESTRO_BASE_FILE)


# ==============================================================================
# GRÁFICOS Y TELEGRAM
# ==============================================================================
def generar_grafico_bloque(items, titulo_graf, subtitulo_graf, filename):
    if not items:
        return None
    sims = [f"[{'*' * i['estrellas'] if i['estrellas']>0 else '-'}]{i['base']}" for i in items]
    probs = [i['probabilidad_pct'] for i in items]
    cols = [i['color_hex'] for i in items]
    ests = [i['estrellas'] for i in items]

    fig, ax = plt.subplots(figsize=(9.0, 4.3), facecolor='#0b132b')
    ax.set_facecolor('#0b132b')
    bars = ax.bar(sims, probs, color=cols, width=0.48, zorder=3)
    ax.grid(True, color='#1e293b', linewidth=0.8, zorder=1)
    ax.set_ylim(0, 122)
    for sp in ['top', 'right', 'left', 'bottom']:
        ax.spines[sp].set_visible(False)
    ax.tick_params(left=False, labelleft=False, bottom=False)
    ax.tick_params(axis='x', colors='white', labelsize=9.5)

    for bar, it, pr, col, est in zip(bars, items, probs, cols, ests):
        yv, xv = bar.get_height(), bar.get_x() + bar.get_width() / 2.0
        if est > 0:
            bar.set_edgecolor('#ffd700' if est >= 2 else '#ffffff')
            bar.set_linewidth(2.2)
            ax.text(xv, yv + 3.0, f"{'*' * est}\n{pr}%", ha='center', va='bottom', color='#ffd700' if est >= 2 else '#ffffff', fontweight='bold', fontsize=9)
        else:
            ax.text(xv, yv + 2.5, f"{pr}%", ha='center', va='bottom', color=col, fontweight='bold', fontsize=8.5)
        ax.plot(xv, max(yv / 2.0, 14), marker='o', markersize=17, markerfacecolor='#0f172a', markeredgecolor='#ffd700' if est >= 2 else ('#ffffff' if est == 1 else col), markeredgewidth=2.0 if est > 0 else 1.5, zorder=4)
        ax.text(xv, max(yv / 2.0, 14), it['base'][:5], ha='center', va='center', color='white', fontsize=6.5, fontweight='bold', zorder=5)

    plt.title(titulo_graf, loc='left', color='#ffab00', fontsize=11, fontweight='bold', pad=12)
    ax.text(0.0, 1.02, subtitulo_graf, transform=ax.transAxes, color='#94a3b8', fontsize=8.5)
    plt.tight_layout()
    plt.savefig(filename, dpi=300, facecolor=fig.get_facecolor())
    plt.close()
    return filename


def enviar_texto_telegram(texto):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    tid = int(TELEGRAM_TOPIC_ID) if TELEGRAM_TOPIC_ID.isdigit() else None
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": texto.strip(), "parse_mode": "HTML", "disable_web_page_preview": True}
    if tid:
        payload["message_thread_id"] = tid
    try:
        r = requests.post(url, json=payload, timeout=15).json()
        if not r.get("ok") and "thread not found" in str(r.get("description", "")).lower():
            payload.pop("message_thread_id", None)
            requests.post(url, json=payload, timeout=15)
    except Exception as e:
        print(f"⚠️ Error Telegram: {e}")


def enviar_telegram_documento(doc_path, caption_text):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID or not os.path.exists(doc_path):
        return False
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendDocument"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "caption": caption_text[:1020], "parse_mode": "HTML"}
    if TELEGRAM_TOPIC_ID.isdigit():
        payload["message_thread_id"] = int(TELEGRAM_TOPIC_ID)
    try:
        with open(doc_path, 'rb') as doc:
            res = requests.post(url, data=payload, files={"document": doc}, timeout=45).json()
            if not res.get("ok") and "thread not found" in str(res.get("description", "")).lower():
                payload.pop("message_thread_id", None)
                doc.seek(0)
                res = requests.post(url, data=payload, files={"document": doc}, timeout=45).json()
            return bool(res.get("ok"))
    except Exception as e:
        print(f"❌ Error enviando documento Telegram: {e}")
        return False


def enviar_alerta_posta(al):
    sim, mkt, tec, etapa = al['base'], al['mkt'], al['tec'], al['etapa']
    uid = int(time.time() * 1000) + random.randint(1, 9999)
    u_ia = f"{BASE_URL_NETLIFY}/?coin={sim}&price={mkt['precio_f']}&change={mkt['cambio_f']}&high={mkt['high_f']}&low={mkt['low_f']}&v={sim}_{uid}"
    u_tr = f"https://www.binance.com/es/trade/{sim}_USDT"
    if etapa == 2:
        titulo = "🚨 <b>POSTA ETAPA 1 • AVANCE A AMARILLO (⭐⭐)</b>"
        desc = f"destacada con ⭐ en Verde ({al['fecha_corta']} @ <code>{formatear_precio(al['p_ini'])}</code>) pasó el filtro Amarillo (<b>⭐⭐</b>)."
    else:
        titulo = "🛡️ <b>CERTIFICADA IA ETAPA 1 ➔ 2 • CONFIRMADA ROJO (⭐⭐⭐)</b>"
        desc = f"superó el filtro técnico + Order Book + Certificador IA y entra blindada a <b>Pre-Explosión</b>."
    msg = (
        f"{titulo}\n📅 <code>{ahora_art().strftime('%Y-%m-%d %H:%M ART')}</code>\n\n"
        f"⚡ <b>{sim}</b> {desc}\n"
        f"• <b>Actual:</b> <code>{formatear_precio(al['p_act'])}</code> (<b>{al['var_seq']:+.2f}%</b> vs inicio)\n"
        f"• <b>Técnico:</b> <code>{tec['estructura_1d']} | {tec.get('fib_tag', '')} | 1h: {tec['var_1h']:+.2f}% | RSI: {tec['rsi_1h']}</code>\n"
        f"• <b>Certificación:</b> <i>{html.escape(al.get('motivo', ''))}</i>\n"
        f"└ <a href=\"{html.escape(u_ia)}\">📊 Resumen IA</a> | <a href=\"{html.escape(u_tr)}\">🔶 Tradear</a>"
    )
    enviar_texto_telegram(msg)


def enviar_bloque_posta(num_bloque, titulo_bloque, items, msg_vacio, dictamen=""):
    fecha_str = ahora_art().strftime('%Y-%m-%d %H:%M ART')
    if not items:
        txt = f"🔥 <b>CAZADOR TÁCTICO + CERTIFICADOR IA ({num_bloque}/3)</b>\n{titulo_bloque}\n📅 <code>{fecha_str}</code>\n"
        if dictamen:
            txt += f"🧠 <i>{html.escape(dictamen)}</i>\n"
        txt += f"\n⏳ <i>{html.escape(msg_vacio)}</i>"
        enviar_texto_telegram(txt)
        return

    fname = f"posta_bloque_{num_bloque}.png"
    generar_grafico_bloque(items, f"ETAPA 1 • CAZADOR TACTICO + IA ({num_bloque}/3)", f"Fecha: {fecha_str} | 1* Verde -> 2** Amarillo -> 3*** Rojo Certificado IA", fname)

    msg = f"🔥 <b>CAZADOR TÁCTICO + CERTIFICADOR IA ({num_bloque}/3)</b>\n{titulo_bloque}\n📅 <code>{fecha_str}</code>\n"
    if dictamen:
        msg += f"🧠 <i>{html.escape(dictamen)}</i>\n"
    msg += "\n"

    for it in items:
        sim, est = it["base"], int(it["estrellas"])
        uid = int(time.time() * 1000) + random.randint(1, 9999)
        u_ia = f"{BASE_URL_NETLIFY}/?coin={sim}&price={it['precio_f']}&change={it['cambio_f']}&high={it['high_f']}&low={it['low_f']}&v={sim}_{uid}"
        u_tr = f"https://www.binance.com/es/trade/{sim}_USDT"
        mot = html.escape(it.get("motivo_ia", ""))

        if est > 0:
            msg += (
                f"{'⭐'*est} <b>{sim} [Blindaje: {it['probabilidad_pct']}%]</b> | Inicio ({it['fecha_corta']}): <code>{formatear_precio(it['precio_inicio'])}</code> ➔ Actual: <code>{formatear_precio(it['precio_f'])}</code> (<b>{it['var_seq']:+.2f}%</b>)\n"
                f"   📐 <code>{it['estructura_1d']} | 1h: {it['var_1h']:+.2f}% | RSI: {it['rsi_1h']} | Vol: x{it['vol_surge']}</code>\n"
            )
            if mot:
                msg += f"   💡 <i>{mot}</i>\n"
            msg += f"   └ <a href=\"{html.escape(u_ia)}\">📊 Resumen IA</a> | <a href=\"{html.escape(u_tr)}\">🔶 Tradear</a>\n\n"
        else:
            msg += (
                f"• <b>{sim}</b> (Prob: <b>{it['probabilidad_pct']}%</b>) | Actual: <code>{formatear_precio(it['precio_f'])}</code> | <b>{it['cambio_f']:+.2f}%</b>\n"
                f"  └ <a href=\"{html.escape(u_ia)}\">📊 Resumen IA</a> | <a href=\"{html.escape(u_tr)}\">🔶 Tradear</a>\n\n"
            )

    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
    tid = int(TELEGRAM_TOPIC_ID) if TELEGRAM_TOPIC_ID.isdigit() else None
    texto_limpio = msg.strip()
    cabe = len(texto_limpio) <= 1020

    for _ in range(3):
        try:
            pf = {"chat_id": TELEGRAM_CHAT_ID}
            if tid:
                pf["message_thread_id"] = tid
            if cabe:
                pf.update({"caption": texto_limpio, "parse_mode": "HTML"})
            with open(fname, 'rb') as ph:
                res = requests.post(url, data=pf, files={"photo": ph}, timeout=25).json()
                if not res.get("ok") and "thread not found" in str(res.get("description", "")).lower():
                    pf.pop("message_thread_id", None)
                    ph.seek(0)
                    res = requests.post(url, data=pf, files={"photo": ph}, timeout=25).json()
            if res.get("ok"):
                if not cabe:
                    enviar_texto_telegram(texto_limpio)
                return
        except Exception as e:
            print(f"⚠️ Error bloque {num_bloque}: {e}")
        time.sleep(3)


if __name__ == "__main__":
    print(f"🔥 INICIANDO ETAPA 1 • CAZADOR TÁCTICO + HISTORIAL COMPLETO + ASISTENTE IA ({ahora_art().strftime('%H:%M:%S')} ART)...")
    s = crear_sesion_binance()
    activos, datos = obtener_datos_binance(s)
    if datos and activos:
        hist = cargar_historial()
        grupos, hist, dictamen, alertas, mapa_mkt = ejecutar_posta_colores(s, datos, activos, hist)

        hist_comp = actualizar_historial_completo_tactico(s, hist, mapa_mkt)
        reporte_ia = ejecutar_asistente_ia_tactico(hist_comp, grupos)
        generar_excel_tactico(hist_comp, reporte_ia)

        for al in alertas:
            enviar_alerta_posta(al)
            time.sleep(1.5)

        enviar_bloque_posta(1, "🔴 <b>1. ROJO • CERTIFICADAS IA (⭐⭐⭐ ➔ PASA A ETAPA 2)</b>", grupos["ROJO"], "Ninguna moneda oculta completó aún la certificación Verde -> Amarillo -> Rojo.", dictamen)
        time.sleep(2)
        enviar_bloque_posta(2, "🟡 <b>2. AMARILLO • FILTRO DE EVOLUCIÓN (⭐⭐)</b>", grupos["AMARILLO"], "Ninguna moneda destacada en Verde (⭐) pasó aún el filtro Amarillo.")
        time.sleep(2)
        enviar_bloque_posta(3, "🟢 <b>3. VERDE • HALLAZGOS FUERA DEL RADAR (⭐)</b>", grupos["VERDE"], "Sin monedas ocultas en Verde en este ciclo.")

        hoy = ahora_art()
        hoy_str = hoy.strftime('%Y-%m-%d')
        es_manual = (os.getenv("GITHUB_EVENT_NAME") == "workflow_dispatch")
        es_cierre = (hoy.hour == 23 and hoy.minute >= 30 and hist.get("ultimo_envio_excel") != hoy_str)
        if es_cierre or es_manual:
            time.sleep(1.5)
            cap_xls = (
                f"📊 <b>Excel Histórico Cazador Táctico ({hoy_str}):</b> "
                f"{reporte_ia['total_senales_historicas']} señales auditadas | "
                f"Stop óptimo calibrado: <code>{reporte_ia['stop_optimo_sugerido_pct']}%</code>."
            )
            if enviar_telegram_documento(EXCEL_TACTICO_FILE, cap_xls) and not es_manual:
                hist["ultimo_envio_excel"] = hoy_str
                guardar_historial(hist)
    else:
        print("❌ ERROR: Sin datos de Binance.")
