import os
import re
import json
import time
import random
import html
from datetime import datetime, timezone, timedelta
import requests

TZ_ART = timezone(timedelta(hours=-3))
TELEGRAM_BOT_TOKEN = (os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("TELEGRAM_TOKEN") or "").strip()
TELEGRAM_CHAT_ID = (os.getenv("TELEGRAM_CHAT_ID") or os.getenv("CHAT_ID") or "").strip()
TELEGRAM_TOPIC_ID = (
    os.getenv("TOPIC_ID_PERDEDORAS")
    or os.getenv("TOPIC_ID_DIPS")
    or os.getenv("TOPIC_ID_CENTRAL")
    or "14669"
).strip()
BASE_URL_NETLIFY = "https://gregarious-frangollo-0346c5.netlify.app"

ESTADO_FILE = "perdedoras_silenciosas.json"

EXCL_BASE = {
    'USDT', 'USDC', 'FDUSD', 'DAI', 'TUSD', 'USDP', 'EUR', 'GBP', 'AUD', 'BRL', 'ARS', 'TRY', 'BUSD',
    'USD1', 'AEUR', 'EURI', 'USDE', 'RLUSD', 'RWUSD', 'XUSD', 'BFUSD', 'U', 'USDG', 'USDS', 'PYUSD',
    'BTC', 'ETH', 'SOL', 'ADA', 'XRP', 'DOGE', 'TRX', 'SHIB', 'AVAX', 'LINK', 'BNB', 'DOT', 'NEAR', 'SUI', 'PEPE'
}

def ahora_art():
    return datetime.now(TZ_ART)

def cargar_estado():
    hoy = ahora_art().strftime('%Y-%m-%d')
    base = {
        "fecha": hoy,
        "alertadas_hoy": {},
        "historial_caidas": {}
    }
    if os.path.exists(ESTADO_FILE):
        try:
            with open(ESTADO_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
            base["historial_caidas"] = data.get("historial_caidas") if isinstance(data.get("historial_caidas"), dict) else {}
            if data.get("fecha") == hoy:
                base["alertadas_hoy"] = data.get("alertadas_hoy") if isinstance(data.get("alertadas_hoy"), dict) else {}
        except Exception:
            pass
    return base

def guardar_estado(estado):
    estado["actualizado_art"] = ahora_art().strftime('%Y-%m-%d %H:%M:%S')
    try:
        with open(ESTADO_FILE, 'w', encoding='utf-8') as f:
            json.dump(estado, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"⚠️ Error guardando {ESTADO_FILE}: {e}")

def crear_sesion():
    s = requests.Session()
    s.headers.update({
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json",
        "Cache-Control": "no-cache"
    })
    return s

def obtener_mercado_spot(session):
    activos, tickers = set(), []
    for url in ["https://api.binance.com/api/v3/exchangeInfo", "https://data-api.binance.vision/api/v3/exchangeInfo"]:
        try:
            r = session.get(url, timeout=12)
            if r.status_code == 200:
                activos = {
                    s.get("symbol")
                    for s in r.json().get("symbols", [])
                    if s.get("status") == "TRADING"
                    and s.get("isSpotTradingAllowed", True)
                    and s.get("quoteAsset") == "USDT"
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

def obtener_klines(session, symbol, interval, limit):
    for base_url in ["https://api.binance.com", "https://data-api.binance.vision"]:
        try:
            r = session.get(f"{base_url}/api/v3/klines", params={"symbol": symbol, "interval": interval, "limit": limit}, timeout=7)
            if r.status_code == 200 and isinstance(r.json(), list) and r.json():
                return r.json()
        except Exception:
            continue
    return []

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

def es_base_valida(base):
    if not base or base in EXCL_BASE:
        return False
    if not re.match(r'^[A-Z0-9]+$', base):
        return False
    if any(x in base for x in ['UP', 'DOWN', 'BULL', 'BEAR']):
        return False
    return True

def evaluar_oportunidad_en_baja(session, t, hist_moneda):
    symbol = t.get("symbol", "")
    base = symbol[:-4] if symbol.endswith("USDT") else symbol
    precio = float(t.get("lastPrice", 0) or 0)
    chg_24h = float(t.get("priceChangePercent", 0) or 0)
    vol_24h = float(t.get("quoteVolume", 0) or 0)
    high_24h = float(t.get("highPrice", precio) or precio)
    low_24h = float(t.get("lowPrice", precio) or precio)

    if not (0.000001 <= precio < 25.0):
        return None
    if vol_24h < 600_000:
        return None
    if not (-28.0 <= chg_24h <= -6.0):
        return None

    k1d = obtener_klines(session, symbol, "1d", 180)
    k1h = obtener_klines(session, symbol, "1h", 20)
    k15m = obtener_klines(session, symbol, "15m", 10)
    if len(k1d) < 15 or len(k1h) < 10 or len(k15m) < 4:
        return None

    min_hist = min(float(x[3]) for x in k1d)
    max_hist = max(float(x[2]) for x in k1d)
    rango_hist = max_hist - min_hist
    pos_rango_hist = round(((precio - min_hist) / rango_hist) * 100, 1) if rango_hist > 0 else 50.0
    dist_min_pct = round(((precio - min_hist) / min_hist) * 100, 1) if min_hist > 0 else 0.0

    rebotes_hist = 0
    cierres_1d = [float(x[4]) for x in k1d]
    for i in range(5, len(cierres_1d) - 3):
        piso = min(cierres_1d[i - 5:i + 1])
        techo = max(cierres_1d[i + 1:min(len(cierres_1d), i + 11)])
        if piso > 0 and ((techo - piso) / piso) * 100 >= 12.0:
            rebotes_hist += 1

    c1h = [float(x[4]) for x in k1h]
    v1h = [float(x[7]) for x in k1h]
    o1h, cl1h = float(k1h[-1][1]), c1h[-1]
    var_1h = round(((cl1h - o1h) / o1h) * 100, 2) if o1h > 0 else 0.0
    rsi_1h = calcular_rsi(c1h, 14)

    v_rec = sum(v1h[-2:]) / 2.0
    v_prev = sum(v1h[-10:-2]) / 8.0 if len(v1h) >= 10 else v_rec
    vol_surge = round(v_rec / v_prev, 2) if v_prev > 0 else 1.0

    o15, h15, l15, c15 = float(k15m[-1][1]), float(k15m[-1][2]), float(k15m[-1][3]), float(k15m[-1][4])
    var_15m = round(((c15 - o15) / o15) * 100, 2) if o15 > 0 else 0.0
    rebote_desde_min_24h = round(((precio - low_24h) / low_24h) * 100, 2) if low_24h > 0 else 0.0
    mecha_rebote = (c15 > o15) and ((c15 - l15) > (h15 - c15) * 1.25)

    senal_rebote = (
        pos_rango_hist <= 55.0
        and rsi_1h >= 24.0
        and vol_surge >= 1.05
        and (
            (var_15m >= 0.35 and (var_1h >= -1.0 or rebote_desde_min_24h >= 1.2))
            or (mecha_rebote and rebote_desde_min_24h >= 0.8 and var_1h >= -2.0)
        )
    )

    hoy_iso = ahora_art().strftime('%Y-%m-%d')
    eventos = hist_moneda.get("eventos") or []
    if not eventos or eventos[-1].get("fecha") != hoy_iso:
        eventos.append({
            "fecha": hoy_iso,
            "precio_caida": precio,
            "chg_24h": chg_24h,
            "senal_rebote": senal_rebote
        })
        hist_moneda["eventos"] = eventos[-20:]
    elif senal_rebote:
        eventos[-1]["senal_rebote"] = True

    if not senal_rebote:
        return None

    score = round(abs(chg_24h) * 1.2 + max(0.0, var_15m) * 4.0 + max(0.0, var_1h) * 2.0 + vol_surge * 5.0 + min(rebotes_hist, 8) * 2.0, 1)

    return {
        "symbol": symbol,
        "base": base,
        "precio": precio,
        "chg_24h": round(chg_24h, 2),
        "var_1h": var_1h,
        "var_15m": var_15m,
        "rebote_min_24h": rebote_desde_min_24h,
        "rsi_1h": rsi_1h,
        "vol_surge": vol_surge,
        "vol_24h": vol_24h,
        "high_24h": high_24h,
        "low_24h": low_24h,
        "pos_rango_hist": pos_rango_hist,
        "dist_min_pct": dist_min_pct,
        "rebotes_hist": rebotes_hist,
        "score": score
    }

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

def enviar_telegram(texto):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("ℹ️ Sin credenciales de Telegram; no se envía mensaje.")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    tid = int(TELEGRAM_TOPIC_ID) if TELEGRAM_TOPIC_ID.isdigit() else None
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": texto.strip(),
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }
    if tid:
        payload["message_thread_id"] = tid
    try:
        r = requests.post(url, json=payload, timeout=25).json()
        if not r.get("ok") and "thread not found" in str(r.get("description", "")).lower():
            payload.pop("message_thread_id", None)
            requests.post(url, json=payload, timeout=25)
    except Exception as e:
        print(f"⚠️ Error enviando a Telegram: {e}")

if __name__ == "__main__":
    print(f"🤫 INICIANDO BOT PERDEDORAS SILENCIOSO ({ahora_art().strftime('%Y-%m-%d %H:%M:%S')} ART)...")
    session = crear_sesion()
    activos, tickers = obtener_mercado_spot(session)
    if not activos or not tickers:
        print("🤫 Sin datos completos de Binance; modo silencioso.")
        raise SystemExit(0)

    estado = cargar_estado()
    alertadas_hoy = estado.get("alertadas_hoy", {})
    hist_caidas = estado.get("historial_caidas", {})

    perdedoras_raw = []
    for t in tickers:
        sym = t.get("symbol", "")
        if not sym.endswith("USDT") or sym not in activos:
            continue
        base = sym[:-4]
        if not es_base_valida(base):
            continue
        try:
            chg = float(t.get("priceChangePercent", 0) or 0)
            vol = float(t.get("quoteVolume", 0) or 0)
            if -28.0 <= chg <= -6.0 and vol >= 600_000:
                perdedoras_raw.append((chg, vol, t))
        except (ValueError, TypeError):
            continue

    perdedoras_raw.sort(key=lambda x: x[0])
    oportunidades = []

    for _, _, t in perdedoras_raw[:30]:
        sym = t.get("symbol", "")
        precio_act = float(t.get("lastPrice", 0) or 0)
        hm = hist_caidas.setdefault(sym, {"eventos": []})
        ev = evaluar_oportunidad_en_baja(session, t, hm)
        if not ev:
            continue

        prev = alertadas_hoy.get(sym)
        if prev:
            p_prev = float(prev.get("precio", precio_act) or precio_act)
            if p_prev > 0 and abs((precio_act - p_prev) / p_prev) * 100 < 2.5:
                continue

        oportunidades.append(ev)

    guardar_estado(estado)

    if not oportunidades:
        print("🤫 Modo silencioso: no hay perdedoras con señal de rebote/compra en este ciclo.")
        raise SystemExit(0)

    oportunidades.sort(key=lambda x: x["score"], reverse=True)
    top_op = oportunidades[:6]

    for op in top_op:
        alertadas_hoy[op["symbol"]] = {
            "hora_art": ahora_art().strftime('%H:%M'),
            "precio": op["precio"]
        }
    estado["alertadas_hoy"] = alertadas_hoy
    guardar_estado(estado)

    fecha_str = ahora_art().strftime('%Y-%m-%d %H:%M ART')
    msg = (
        f"📉➡️📈 <b>REPORTE SILENCIOSO • PERDEDORAS CON REBOTE</b>\n"
        f"📅 <code>{fecha_str}</code>\n"
        f"<i>Detectadas {len(top_op)} monedas que cayeron en 24h y muestran reacción para evaluar en Spot:</i>\n\n"
    )

    for op in top_op:
        sim = op["base"]
        uid = int(time.time() * 1000) + random.randint(1, 9999)
        u_ia = f"{BASE_URL_NETLIFY}/?coin={sim}&price={op['precio']}&change={op['chg_24h']}&high={op['high_24h']}&low={op['low_24h']}&v={sim}_{uid}"
        u_tr = f"https://www.binance.com/es/trade/{sim}_USDT"

        msg += (
            f"🎯 <b>{sim}</b> — <code>{formatear_precio(op['precio'])}</code> (24h: <b>{op['chg_24h']:+.2f}%</b>)\n"
            f"   ⚡ <code>15m: {op['var_15m']:+.2f}% | 1h: {op['var_1h']:+.2f}% | +min24h: +{op['rebote_min_24h']:.2f}% | RSI 1h: {op['rsi_1h']} | Vol x{op['vol_surge']}</code>\n"
            f"   🕰️ <code>Hist 1d: rango {op['pos_rango_hist']}% (+{op['dist_min_pct']}% vs min) | Rebotes >=12%: {op['rebotes_hist']}</code>\n"
            f"   └ <a href=\"{html.escape(u_ia)}\">📊 Resumen IA</a> | <a href=\"{html.escape(u_tr)}\">🔶 Ver en Binance</a>\n\n"
        )

    msg += "<i>Chequeá siempre el informe/riesgos de la moneda en Binance y el contexto de BTC antes de comprar.</i>"
    enviar_telegram(msg)
    print(f"✅ Enviado reporte de {len(top_op)} oportunidades en baja.")

# FIN BOT PERDEDORAS SILENCIOSO
