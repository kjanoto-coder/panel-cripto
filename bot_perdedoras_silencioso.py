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

# Lista base de Favoritos (podés sumar o editar libremente en perdedoras_silenciosas.json -> "favoritos")
FAVORITOS_INICIAL = [
    "NEIROUSDT",
    "TUTUSDT",
    "PUMPUSDT",
    "ONDOUSDT",
    "QIUSDT",
    "ALTUSDT",
    "XECUSDT",
    "JSTUSDT",
    "ALGOUSDT",
    "PENGUUSDT",
    "JUPUSDT",
    "ZECUSDT",
    "ALLOUSDT",
    "MANTRAUSDT",
    "TNSRUSDT",
    "MITOUSDT",
    "BANKUSDT",
    "ETHFIUSDT",
    "OPENUSDT",
    "GIGGLEUSDT"
]

EXCL_BASE = {
    'USDT', 'USDC', 'FDUSD', 'DAI', 'TUSD', 'USDP', 'EUR', 'GBP', 'AUD', 'BRL', 'ARS', 'TRY', 'BUSD',
    'USD1', 'AEUR', 'EURI', 'USDE', 'RLUSD', 'RWUSD', 'XUSD', 'BFUSD', 'U', 'USDG', 'USDS', 'PYUSD'
}

def ahora_art():
    return datetime.now(TZ_ART)

def normalizar_simbolo(raw):
    s = re.sub(r'[^A-Z0-9]', '', str(raw or "").upper())
    if not s:
        return ""
    if s == "QL":
        s = "QI"
    if not s.endswith("USDT"):
        s = f"{s}USDT"
    return s

def es_activo_apalancado_o_derivado(base):
    if not base or base in EXCL_BASE:
        return True
    if not re.match(r'^[A-Z0-9]+$', base):
        return True
    if any(k in base for k in ['UP', 'DOWN', 'BULL', 'BEAR', '2X', '3X', '5X']):
        return True
    # Filtra tokens tipo bStocks / acciones tokenizadas apalancadas terminadas en B tras ticker largo
    if len(base) >= 4 and base.endswith("B") and base[:-1] in {'SNXX', 'NVDA', 'TSLA', 'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META'}:
        return True
    return False

def cargar_estado():
    hoy = ahora_art().strftime('%Y-%m-%d')
    favs_def = [normalizar_simbolo(x) for x in FAVORITOS_INICIAL if normalizar_simbolo(x)]
    base = {
        "fecha": hoy,
        "favoritos": favs_def,
        "alertadas_hoy": {},
        "historial_caidas": {}
    }
    if os.path.exists(ESTADO_FILE):
        try:
            with open(ESTADO_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
            cargados = [normalizar_simbolo(x) for x in (data.get("favoritos") or []) if normalizar_simbolo(x)]
            base["favoritos"] = list(dict.fromkeys(favs_def + cargados))
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

def obtener_tickers_24h(session):
    for url in ["https://api.binance.com/api/v3/ticker/24hr", "https://data-api.binance.vision/api/v3/ticker/24hr"]:
        try:
            r = session.get(url, timeout=15)
            if r.status_code == 200 and isinstance(r.json(), list) and r.json():
                return {t.get("symbol"): t for t in r.json() if t.get("symbol")}
        except Exception:
            continue
    return {}

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

def evaluar_favorito_en_baja(session, symbol, t, btc_chg_24h, hist_moneda):
    base = symbol[:-4] if symbol.endswith("USDT") else symbol
    if es_activo_apalancado_o_derivado(base):
        return None

    precio = float(t.get("lastPrice", 0) or 0)
    chg_24h = float(t.get("priceChangePercent", 0) or 0)
    vol_24h = float(t.get("quoteVolume", 0) or 0)
    high_24h = float(t.get("highPrice", precio) or precio)
    low_24h = float(t.get("lowPrice", precio) or precio)

    if precio <= 0 or vol_24h < 250_000:
        return None

    # Toda caída mayor al 5% en 24h entra en análisis de baja
    if chg_24h > -5.0:
        return None

    k1d = obtener_klines(session, symbol, "1d", 240)
    k1h = obtener_klines(session, symbol, "1h", 24)
    k15m = obtener_klines(session, symbol, "15m", 12)
    if len(k1d) < 10 or len(k1h) < 6 or len(k15m) < 4:
        return None

    min_hist = min(float(x[3]) for x in k1d)
    max_hist = max(float(x[2]) for x in k1d)
    rango_hist = max_hist - min_hist
    pos_rango_hist = round(((precio - min_hist) / rango_hist) * 100, 1) if rango_hist > 0 else 50.0
    dist_min_pct = round(((precio - min_hist) / min_hist) * 100, 1) if min_hist > 0 else 0.0

    # Historial diario: cuántos rebotes >= 12% hubo en los últimos meses
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
    rebote_min_24h = round(((precio - low_24h) / low_24h) * 100, 2) if low_24h > 0 else 0.0
    mecha_rebote = (c15 > o15) and ((c15 - l15) > (h15 - c15) * 1.2)

    # Distingue si la caída es más afín a arrastre de mercado/BTC o a caída pesada/desarme propio
    arrastre_btc = (btc_chg_24h <= -2.5) and (chg_24h >= btc_chg_24h * 3.2) and (chg_24h > -22.0)

    # Condición de oportunidad de rebote a revisar: caída > 5% con señal inicial de freno/recuperación
    senal_oportunidad = (
        pos_rango_hist <= 65.0
        and rsi_1h >= 18.0
        and (
            (var_15m >= 0.15 and (var_1h >= -1.5 or rebote_min_24h >= 0.7))
            or (mecha_rebote and rebote_min_24h >= 0.5)
            or (rebote_min_24h >= 1.5 and var_15m >= 0.0 and vol_surge >= 0.9)
        )
    )

    hoy_iso = ahora_art().strftime('%Y-%m-%d')
    eventos = hist_moneda.get("eventos_caida") or []
    if not eventos or eventos[-1].get("fecha") != hoy_iso:
        eventos.append({
            "fecha": hoy_iso,
            "precio_caida": precio,
            "min_24h": low_24h,
            "chg_24h": chg_24h,
            "arrastre_btc": arrastre_btc,
            "senal_oportunidad": senal_oportunidad
        })
        hist_moneda["eventos_caida"] = eventos[-25:]
    else:
        ev_hoy = eventos[-1]
        if precio < float(ev_hoy.get("precio_caida", precio) or precio):
            ev_hoy["precio_caida"] = precio
        if low_24h < float(ev_hoy.get("min_24h", low_24h) or low_24h):
            ev_hoy["min_24h"] = low_24h
        ev_hoy["chg_24h"] = chg_24h
        if senal_oportunidad:
            ev_hoy["senal_oportunidad"] = True

    hist_moneda["ultimo_precio"] = precio
    hist_moneda["ultimo_chg_24h"] = chg_24h
    hist_moneda["rebotes_hist_1d"] = rebotes_hist

    if not senal_oportunidad:
        return None

    score = round(
        min(abs(chg_24h), 22.0) * 1.1
        + max(0.0, var_15m) * 4.5
        + max(0.0, var_1h) * 2.0
        + rebote_min_24h * 1.5
        + (5.0 if arrastre_btc else 0.0)
        + min(rebotes_hist, 10) * 1.8,
        1
    )

    return {
        "symbol": symbol,
        "base": base,
        "precio": precio,
        "chg_24h": round(chg_24h, 2),
        "var_1h": var_1h,
        "var_15m": var_15m,
        "rebote_min_24h": rebote_min_24h,
        "rsi_1h": rsi_1h,
        "vol_surge": vol_surge,
        "vol_24h": vol_24h,
        "high_24h": high_24h,
        "low_24h": low_24h,
        "pos_rango_hist": pos_rango_hist,
        "dist_min_pct": dist_min_pct,
        "rebotes_hist": rebotes_hist,
        "arrastre_btc": arrastre_btc,
        "total_caidas_reg": len(eventos),
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
    mapa_tickers = obtener_tickers_24h(session)
    if not mapa_tickers:
        print("🤫 Sin datos de Binance; modo silencioso.")
        raise SystemExit(0)

    estado = cargar_estado()
    favoritos = estado.get("favoritos", [])
    alertadas_hoy = estado.get("alertadas_hoy", {})
    hist_caidas = estado.get("historial_caidas", {})

    btc_t = mapa_tickers.get("BTCUSDT", {})
    btc_precio = float(btc_t.get("lastPrice", 0) or 0)
    btc_chg_24h = float(btc_t.get("priceChangePercent", 0) or 0)

    oportunidades = []
    for sym in favoritos:
        t = mapa_tickers.get(sym)
        if not t:
            continue
        precio_act = float(t.get("lastPrice", 0) or 0)
        hm = hist_caidas.setdefault(sym, {"eventos_caida": []})
        ev = evaluar_favorito_en_baja(session, sym, t, btc_chg_24h, hm)
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
        print("🤫 Modo silencioso: ningún favorito en baja (>5%) muestra señal de rebote en este ciclo.")
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
        f"📉➡️📈 <b>FAVORITOS EN BAJA (&gt;5%) • REBOTE A EVALUAR</b>\n"
        f"📅 <code>{fecha_str}</code> | 🪙 BTC: <code>{formatear_precio(btc_precio)}</code> (<b>{btc_chg_24h:+.2f}%</b>)\n"
        f"<i>Favoritos que cayeron &gt;5% con reacción inicial; verificá su ficha IA en Binance antes de entrar en Spot:</i>\n\n"
    )

    for op in top_op:
        sim = op["base"]
        uid = int(time.time() * 1000) + random.randint(1, 9999)
        u_ia = f"{BASE_URL_NETLIFY}/?coin={sim}&price={op['precio']}&change={op['chg_24h']}&high={op['high_24h']}&low={op['low_24h']}&v={sim}_{uid}"
        u_tr = f"https://www.binance.com/es/trade/{sim}_USDT"
        contexto_caida = "Arrastre mercado/BTC" if op["arrastre_btc"] else "Caída fuerte / revisar causa"

        msg += (
            f"🎯 <b>{sim}</b> — <code>{formatear_precio(op['precio'])}</code> (24h: <b>{op['chg_24h']:+.2f}%</b>) • <i>{html.escape(contexto_caida)}</i>\n"
            f"   ⚡ <code>15m: {op['var_15m']:+.2f}% | 1h: {op['var_1h']:+.2f}% | +min24h: +{op['rebote_min_24h']:.2f}% | RSI 1h: {op['rsi_1h']}</code>\n"
            f"   🕰️ <code>Hist 1d: rango {op['pos_rango_hist']}% (+{op['dist_min_pct']}% vs min) | Rebotes >=12%: {op['rebotes_hist']} | Caídas: {op['total_caidas_reg']}</code>\n"
            f"   └ <a href=\"{html.escape(u_ia)}\">📊 Resumen IA</a> | <a href=\"{html.escape(u_tr)}\">🔶 Ver en Binance</a>\n\n"
        )

    msg += "<i>Revisá el informe de Binance IA para descartar ventas institucionales/desbloqueos o problemas internos.</i>"
    enviar_telegram(msg)
    print(f"✅ Enviado reporte de {len(top_op)} favoritos en baja con señal de rebote.")

# FIN BOT PERDEDORAS SILENCIOSO
