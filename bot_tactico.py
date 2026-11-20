import os, re, json, time, random, html, requests
from datetime import datetime, timezone, timedelta
import matplotlib.pyplot as plt
from google import genai

TZ_ART = timezone(timedelta(hours=-3))
TELEGRAM_BOT_TOKEN = (os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("TELEGRAM_TOKEN") or "").strip()
TELEGRAM_CHAT_ID = (os.getenv("TELEGRAM_CHAT_ID") or os.getenv("CHAT_ID") or "").strip()
TELEGRAM_TOPIC_ID = (os.getenv("TOPIC_ID_TACTICO") or os.getenv("TOPIC_ID_CENTRAL") or "4").strip()
GEMINI_API_KEY = (os.getenv("GEMINI_API_KEY") or "").strip()
BASE_URL_NETLIFY = "https://gregarious-frangollo-0346c5.netlify.app"
HISTORIAL_FILE = "historial_perlas.json"
DIAS_SEGUIMIENTO = 6

def ahora_art():
    return datetime.now(TZ_ART)

def cargar_historial():
    hoy = ahora_art().strftime('%Y-%m-%d')
    base = {"fecha": hoy, "mencionadas": {}, "resumen_dia": [], "resumen_enviado_hoy": False, "seguimiento_verde": {}, "graduadas_pre_explosion": {}}
    if os.path.exists(HISTORIAL_FILE):
        try:
            with open(HISTORIAL_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
            for k in ["seguimiento_verde", "graduadas_pre_explosion"]:
                limpio = {}
                for sym, info in data.get(k, {}).items():
                    try:
                        f_det = datetime.strptime(info.get("fecha_iso", hoy), '%Y-%m-%d').date()
                        if (ahora_art().date() - f_det).days <= DIAS_SEGUIMIENTO:
                            limpio[sym] = info
                    except Exception:
                        continue
                base[k] = limpio
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
    s = requests.Session()
    s.headers.update({"User-Agent": "Mozilla/5.0", "Accept": "application/json", "Cache-Control": "no-cache"})
    return s

def obtener_datos_binance(session):
    activos, tickers = set(), []
    for url in ["https://api.binance.com/api/v3/exchangeInfo", "https://data-api.binance.vision/api/v3/exchangeInfo"]:
        try:
            r = session.get(url, timeout=12)
            if r.status_code == 200:
                activos = {s['symbol'] for s in r.json().get('symbols', []) if s.get('status') == 'TRADING' and s.get('isSpotTradingAllowed', True) and s.get('quoteAsset') == 'USDT'}
                if activos: break
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
    if not vals: return 0.0
    k = 2 / (p + 1)
    ema = vals[0]
    for v in vals[1:]:
        ema = (v * k) + (ema * (1 - k))
    return ema

def calcular_rsi(cierres, p=14):
    if len(cierres) <= p: return 50.0
    deltas = [cierres[i] - cierres[i - 1] for i in range(1, len(cierres))]
    g = [d if d > 0 else 0.0 for d in deltas]
    per = [-d if d < 0 else 0.0 for d in deltas]
    ag, ap = sum(g[:p]) / p, sum(per[:p]) / p
    for i in range(p, len(g)):
        ag = (ag * (p - 1) + g[i]) / p
        ap = (ap * (p - 1) + per[i]) / p
    return 100.0 if ap == 0 else round(100.0 - (100.0 / (1.0 + (ag / ap))), 1)

def calcular_probabilidad_inversion(session, symbol):
    for base_url in ["https://api.binance.com", "https://data-api.binance.vision"]:
        try:
            r1h = session.get(f"{base_url}/api/v3/klines", params={"symbol": symbol, "interval": "1h", "limit": 25}, timeout=7)
            r15m = session.get(f"{base_url}/api/v3/klines", params={"symbol": symbol, "interval": "15m", "limit": 10}, timeout=7)
            if r1h.status_code == 200 and r15m.status_code == 200:
                k1h, k15m = r1h.json(), r15m.json()
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
                prob += 32 if vol_surge >= 2.2 else (25 if vol_surge >= 1.6 else (18 if vol_surge >= 1.25 else (10 if vol_surge >= 1.05 else 0)))
                if cl1h > ema7 > ema21:
                    ema_est, prob = "Alcista (P>EMA7>EMA21)", prob + 25
                elif cl1h > ema7:
                    ema_est, prob = "Cruce Inicial (>EMA7)", prob + 15
                else:
                    ema_est, prob = "Acumulando Base", prob + 5
                prob += 18 if 50.0 <= rsi_1h <= 66.0 else (13 if 42.0 <= rsi_1h < 50.0 else (8 if 66.0 < rsi_1h <= 74.0 else 0))
                prob += 15 if (0.05 <= var_1h <= 2.2 and var_15m >= 0.0) else (9 if (var_1h >= -0.20 and var_15m > 0.05) else 0)

                return {"ok": True, "probabilidad_pct": min(98, max(10, int(round(prob)))), "var_1h": var_1h, "var_15m": var_15m, "rsi_1h": rsi_1h, "ema_estado": ema_est, "vol_surge": vol_surge}
        except Exception:
            continue
    return {"ok": False, "probabilidad_pct": 0}

def clasificar_semaforo(prob):
    if prob >= 72: return "ROJO", "#ff1744"
    if prob >= 52: return "AMARILLO", "#ffd600"
    return "VERDE", "#00e676"

def formatear_precio(p):
    if p is None or p <= 0: return "$0.00"
    if p >= 100: return f"${p:,.2f}"
    if p >= 1.0: return f"${p:.4f}"
    if p >= 0.01: return f"${p:.5f}"
    if p >= 0.0001: return f"${p:.6f}"
    return f"${p:.8f}"

def curar_con_gemini(rojas, amarillas, verdes):
    def top_def(lista, txt):
        if not lista: return {"symbol": "", "motivo": ""}
        m = max(lista, key=lambda x: x['probabilidad_pct'])
        return {"symbol": m['base'], "motivo": txt}

    fallback = rojas[:7] + amarillas[:7] + verdes[:7]
    tops = {
        "ROJO": top_def(rojas, "Probabilidad máxima: volumen en expansión y medias cruzadas antes de romper."),
        "AMARILLO": top_def(amarillas, "Estructura alcista armándose en 1h con presión compradora sostenida."),
        "VERDE": top_def(verdes, "Detección temprana: absorción silenciosa de volumen con precio aún quieto.")
    }
    dictamen = "Radar de probabilidad Spot en monedas fuera de foco (-2.5% a +5.8%): 1⭐ a 3⭐⭐⭐."
    if not GEMINI_API_KEY or not fallback:
        return fallback, tops, dictamen

    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
        fmt = lambda l: "\n".join([f"- {i['base']}: prob={i['probabilidad_pct']}%, 24h={i['cambio_f']:+.2f}%, 1h={i['var_1h']:+.2f}%, RSI={i['rsi_1h']}, EMAs={i['ema_estado']}, Vol=x{i['vol_surge']}" for i in l]) or "Vacio"
        prompt = (
            "Analista Binance Spot. Evalúa estas 3 listas de monedas ocultas por PROBABILIDAD DE DESPEGUE:\n"
            f"ROJO (>=72%):\n{fmt(rojas)}\nAMARILLO (52-71%):\n{fmt(amarillas)}\nVERDE (35-51%):\n{fmt(verdes)}\n"
            "Ordena las mejores 7 de cada grupo, elige la #1 de cada grupo con motivo (<90 chars) y un dictamen (<120 chars). "
            'Responde SOLO JSON válido: {"rojas":["S1"],"amarillas":["S1"],"verdes":["S1"],"top_roja":{"symbol":"S1","motivo":"..."},"top_amarilla":{"symbol":"S1","motivo":"..."},"top_verde":{"symbol":"S1","motivo":"..."},"dictamen":"..."}'
        )
        for mod in ['gemini-2.5-flash', 'gemini-1.5-flash']:
            try:
                res = client.models.generate_content(model=mod, contents=prompt)
                if res and res.text:
                    data = json.loads(re.sub(r'^```json|
