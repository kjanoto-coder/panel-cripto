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
    base = {
        "fecha": hoy,
        "mencionadas": {},
        "resumen_dia": [],
        "resumen_enviado_hoy": False,
        "seguimiento_verde": {},
        "graduadas_pre_explosion": {},
        "historia_monedas": {}
    }
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

            h_mon = {}
            for sym, h_info in data.get("historia_monedas", {}).items():
                try:
                    f_ult = datetime.strptime(h_info.get("ultima_fecha_iso", hoy), '%Y-%m-%d').date()
                    if (ahora_art().date() - f_ult).days <= DIAS_SEGUIMIENTO:
                        h_mon[sym] = h_info
                except Exception:
                    continue
            base["historia_monedas"] = h_mon

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

def registrar_pasado_moneda(hist_monedas, sym, prob, precio, chg, rsi, vol_surge, estado):
    hoy_iso = ahora_art().strftime('%Y-%m-%d')
    hora_str = ahora_art().strftime('%H:%M')
    prev = hist_monedas.get(sym, {
        "apariciones": 0,
        "picos_prob": [],
        "precio_min_visto": precio,
        "precio_max_visto": precio,
        "subidas_consistentes": 0,
        "caidas_fuertes": 0
    })
    prev_prob = prev.get("ultima_prob", prob)
    prev_precio = prev.get("ultimo_precio", precio)

    apariciones = int(prev.get("apariciones", 0)) + 1
    picos = list(prev.get("picos_prob", []))
    picos.append(prob)
    picos = picos[-8:]

    p_min = min(float(prev.get("precio_min_visto", precio)), precio)
    p_max = max(float(prev.get("precio_max_visto", precio)), precio)

    subidas = int(prev.get("subidas_consistentes", 0))
    caidas = int(prev.get("caidas_fuertes", 0))
    if prob >= prev_prob and precio >= prev_precio * 0.995:
        subidas += 1
    if precio < prev_precio * 0.965 or prob < prev_prob - 12:
        caidas += 1

    # Puntaje histórico (-20 a +25) según consistencia pasada
    score_hist = 0
    score_hist += min(12, subidas * 3)
    score_hist += 6 if (max(picos) - min(picos) >= 8 and prob >= picos[-2] if len(picos) >= 2 else False) else 0
    score_hist -= min(20, caidas * 7)

    hist_monedas[sym] = {
        "apariciones": apariciones,
        "ultima_prob": prob,
        "ultimo_precio": precio,
        "ultimo_chg_24h": chg,
        "ultimo_rsi": rsi,
        "ultimo_vol": vol_surge,
        "ultimo_estado": estado,
        "picos_prob": picos,
        "precio_min_visto": p_min,
        "precio_max_visto": p_max,
        "subidas_consistentes": subidas,
        "caidas_fuertes": caidas,
        "score_historia": score_hist,
        "ultima_fecha_iso": hoy_iso,
        "ultima_hora": hora_str
    }
    return hist_monedas[sym]

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

def cumple_base_verde(it):
    # Moneda cruda en Verde con base sana, RSI controlado y sin historial degradado
    h = it.get("historia", {})
    caidas = int(h.get("caidas_fuertes", 0))
    return (
        it.get("probabilidad_pct", 0) >= 35
        and 38.0 <= it.get("rsi_1h", 50.0) <= 64.0
        and -2.5 <= it.get("cambio_f", 0.0) <= 3.5
        and caidas <= 1
    )

def cumple_evolucion_amarillo(tec, h):
    # Moneda estable de mirar: vino de Verde, no se pinchó y muestra evolución real
    caidas = int(h.get("caidas_fuertes", 0))
    return (
        tec.get("ok")
        and tec.get("probabilidad_pct", 0) >= 56
        and tec.get("rsi_1h", 100.0) <= 68.0
        and (tec.get("vol_surge", 0.0) >= 1.05 or tec.get("var_1h", -99.0) >= 0.15)
        and caidas <= 1
    )

def cumple_confirmacion_rojo(tec, h):
    # Confirmación para inversión / Pre-Explosión tras haber evolucionado desde Verde
    caidas = int(h.get("caidas_fuertes", 0))
    return (
        tec.get("ok")
        and tec.get("probabilidad_pct", 0) >= 72
        and tec.get("rsi_1h", 100.0) <= 72.0
        and tec.get("vol_surge", 0.0) >= 1.15
        and tec.get("var_1h", -99.0) > 0.0
        and caidas == 0
    )

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

                return {
                    "ok": True,
                    "probabilidad_pct": min(98, max(10, int(round(prob)))),
                    "var_1h": var_1h,
                    "var_15m": var_15m,
                    "rsi_1h": rsi_1h,
                    "ema_estado": ema_est,
                    "vol_surge": vol_surge
                }
        except Exception:
            continue
    return {"ok": False, "probabilidad_pct": 0}

def clasificar_semaforo(prob):
    if prob >= 72:
        return "ROJO", "#ff1744"
    if prob >= 52:
        return "AMARILLO", "#ffd600"
    return "VERDE", "#00e676"

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

def picks_verde_con_historia(v7):
    aptas = [x for x in v7 if cumple_base_verde(x)]
    if not aptas:
        return {}
    aptas.sort(
        key=lambda x: (
            x['probabilidad_pct']
            + int(x.get("historia", {}).get("score_historia", 0))
            + int(x.get("historia", {}).get("apariciones", 0))
        ),
        reverse=True
    )
    out = {}
    for x in aptas[:2]:
        ap = int(x.get("historia", {}).get("apariciones", 1))
        out[x['base']] = f"Hist x{ap}, 24h {x['cambio_f']:+.1f}%, 1h {x['var_1h']:+.2f}%, RSI {x['rsi_1h']}: cruda ⭐."
    return out

def picks_evolucion_con_historia(lista, semillero_previo, nivel):
    if nivel == 2:
        validas = [
            x for x in lista
            if x['base'] in semillero_previo and cumple_evolucion_amarillo(x, x.get("historia", {}))
        ]
    else:
        validas = [
            x for x in lista
            if x['base'] in semillero_previo and cumple_confirmacion_rojo(x, x.get("historia", {}))
        ]
    validas.sort(
        key=lambda x: (x['probabilidad_pct'] + int(x.get("historia", {}).get("score_historia", 0))),
        reverse=True
    )
    out = {}
    for x in validas[:3]:
        ap = int(x.get("historia", {}).get("apariciones", 1))
        if nivel == 2:
            out[x['base']] = f"Vino de ⭐ (hist x{ap}): estable {x['probabilidad_pct']}%, RSI {x['rsi_1h']}, Vol x{x['vol_surge']}."
        else:
            out[x['base']] = f"Pasó 1⭐➔2⭐⭐ (hist x{ap}): confirmada {x['probabilidad_pct']}% para Pre-Explosión."
    return out

def curar_con_gemini(rojas, amarillas, verdes, semillero_previo):
    r7, a7, v7 = rojas[:7], amarillas[:7], verdes[:7]
    destacadas = {
        "ROJO": picks_evolucion_con_historia(r7, semillero_previo, 3),
        "AMARILLO": picks_evolucion_con_historia(a7, semillero_previo, 2),
        "VERDE": picks_verde_con_historia(v7)
    }
    dictamen = "Lógica por historia: 1⭐ Verde cruda ➔ 2⭐⭐ Amarillo estable ➔ 3⭐⭐⭐ Rojo a Pre-Explosión."

    if not GEMINI_API_KEY or not (r7 or a7 or v7):
        return r7, a7, v7, destacadas, dictamen

    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
        fmt = lambda l: "\n".join([
            f"- {i['base']}{' [VINO_DE_VERDE]' if i['base'] in semillero_previo else ''} "
            f"[hist: apar={i.get('historia',{}).get('apariciones',1)}, score={i.get('historia',{}).get('score_historia',0)}, caidas={i.get('historia',{}).get('caidas_fuertes',0)}]: "
            f"prob={i['probabilidad_pct']}%, 24h={i['cambio_f']:+.2f}%, 1h={i['var_1h']:+.2f}%, RSI={i['rsi_1h']}, Vol=x{i['vol_surge']}"
            for i in l
        ]) or "Vacio"

        prompt = (
            "Analista cuantitativo Binance Spot. Evaluá el pasado/historia y el momento actual:\n"
            "1) VERDE (35-51%): moneda cruda potencial. Elegí hasta 2 monedas con base sana y buen historial (sin caídas fuertes) para iniciar 1⭐.\n"
            "2) AMARILLO (52-71%): SOLO monedas [VINO_DE_VERDE] que cumplan evolución estable (prob>=56, RSI<=68, caidas<=1) reciben 2⭐⭐.\n"
            "3) ROJO (>=72%): SOLO monedas [VINO_DE_VERDE] con confirmación sólida (prob>=72, RSI<=72, Vol>=1.15, 1h>0, caidas==0) reciben 3⭐⭐⭐.\n\n"
            f"ROJO (>=72%):\n{fmt(rojas)}\nAMARILLO (52-71%):\n{fmt(amarillas)}\nVERDE (35-51%):\n{fmt(verdes)}\n\n"
            'Responde SOLO JSON válido: {"rojas":["S1"],"amarillas":["S1"],"verdes":["S1"],"dest_roja":[{"symbol":"S1","motivo":"..."}],"dest_amarilla":[{"symbol":"S1","motivo":"..."}],"dest_verde":[{"symbol":"S1","motivo":"..."}],"dictamen":"..."}'
        )
        for mod in ['gemini-2.5-flash', 'gemini-1.5-flash']:
            try:
                res = client.models.generate_content(model=mod, contents=prompt)
                if res and res.text:
                    raw = res.text.strip()
                    if "{" in raw and "}" in raw:
                        raw = raw[raw.find("{"):raw.rfind("}") + 1]
                    data = json.loads(raw)

                    def procesar_grupo(pool, orden_ia, dest_ia, dest_def, nivel):
                        mapa = {x['base']: x for x in pool}
                        picks = {}
                        for d in (dest_ia or [])[:3]:
                            s = str(d.get("symbol", "")).strip().upper()
                            m = str(d.get("motivo", "")).strip()
                            if s not in mapa:
                                continue
                            it_m = mapa[s]
                            h_m = it_m.get("historia", {})
                            if nivel == 1 and cumple_base_verde(it_m) and len(picks) < 2:
                                picks[s] = (m or dest_def.get(s) or "")[:95]
                            elif nivel == 2 and s in semillero_previo and cumple_evolucion_amarillo(it_m, h_m):
                                picks[s] = (m or dest_def.get(s) or "")[:95]
                            elif nivel == 3 and s in semillero_previo and cumple_confirmacion_rojo(it_m, h_m):
                                picks[s] = (m or dest_def.get(s) or "")[:95]

                        if not picks:
                            picks = dest_def

                        sel = []
                        if nivel >= 2:
                            for x in pool:
                                if x['base'] in semillero_previo and x['base'] not in picks and x not in sel:
                                    sel.append(x)
                        for s in picks:
                            if s in mapa and mapa[s] not in sel:
                                sel.append(mapa[s])
                        for s in (orden_ia or []):
                            su = str(s).strip().upper()
                            if su in mapa and mapa[su] not in sel:
                                sel.append(mapa[su])
                        for x in pool:
                            if len(sel) >= 7:
                                break
                            if x not in sel:
                                sel.append(x)
                        f7 = sel[:7]
                        validos = {x['base'] for x in f7}
                        return f7, {k: v for k, v in picks.items() if k in validos and v}

                    r7, dr = procesar_grupo(rojas, data.get("rojas"), data.get("dest_roja"), destacadas["ROJO"], 3)
                    a7, da = procesar_grupo(amarillas, data.get("amarillas"), data.get("dest_amarilla"), destacadas["AMARILLO"], 2)
                    v7, dv = procesar_grupo(verdes, data.get("verdes"), data.get("dest_verde"), destacadas["VERDE"], 1)
                    return r7, a7, v7, {"ROJO": dr, "AMARILLO": da, "VERDE": dv}, str(data.get("dictamen") or dictamen)[:140]
            except Exception:
                continue
    except Exception as e:
        print(f"⚠️ Fallback Gemini: {e}")
    return r7, a7, v7, destacadas, dictamen

def evaluar_evolucion_estrellas(session, mapa_mercado, historial, semillero_previo_syms):
    seg = historial.get("seguimiento_verde", {})
    grad = historial.get("graduadas_pre_explosion", {})
    h_mon = historial.get("historia_monedas", {})
    alertas = []
    hoy_iso, hoy_corta = ahora_art().strftime('%Y-%m-%d'), ahora_art().strftime('%d/%m')

    for sym in list(seg.keys()):
        if sym not in semillero_previo_syms:
            continue
        info = seg.get(sym)
        mkt = mapa_mercado.get(sym)
        if not info or not mkt or int(info.get("estrellas", 0)) < 1:
            continue
        tec = calcular_probabilidad_inversion(session, sym)
        if not tec["ok"]:
            continue

        prob = tec["probabilidad_pct"]
        cat, _ = clasificar_semaforo(prob)
        est_prev = int(info.get("estrellas", 1))
        p_act, p_ini = mkt['precio_f'], float(info.get("precio_deteccion", mkt['precio_f']))
        var_det = ((p_act - p_ini) / p_ini) * 100 if p_ini > 0 else 0.0
        h_info = h_mon.get(sym, {})

        # Si la moneda perdió piso de forma marcada (<32% o caída >6% desde detección), sale de la cadena activa
        if prob < 32 or var_det < -6.0:
            del seg[sym]
            continue

        if cat == "AMARILLO" and cumple_evolucion_amarillo(tec, h_info) and est_prev < 2 and not info.get("alerta_2_estrellas_enviada", False):
            info.update({"estrellas": 2, "estado_actual": "AMARILLO", "alerta_2_estrellas_enviada": True})
            grad[sym] = {
                "symbol": sym, "base": sym[:-4], "estrellas": 2, "probabilidad_pct": prob,
                "precio_ref": p_act, "fecha_iso": hoy_iso, "fecha_corta": hoy_corta,
                "origen": "Evolución desde ⭐ Verde a ⭐⭐ Amarillo"
            }
            alertas.append({
                "base": sym[:-4], "nivel": 2, "prob": prob,
                "fecha_corta": info.get("fecha_corta", ""), "p_ini": p_ini, "p_act": p_act,
                "var_det": var_det, "mkt": mkt, "tec": tec
            })
        elif cat == "ROJO" and cumple_confirmacion_rojo(tec, h_info) and est_prev < 3 and not info.get("alerta_3_estrellas_enviada", False):
            info.update({"estrellas": 3, "estado_actual": "ROJO", "alerta_2_estrellas_enviada": True, "alerta_3_estrellas_enviada": True})
            grad[sym] = {
                "symbol": sym, "base": sym[:-4], "estrellas": 3, "probabilidad_pct": prob,
                "precio_ref": p_act, "fecha_iso": hoy_iso, "fecha_corta": hoy_corta,
                "origen": "Confirmada para Pre-Explosión (⭐⭐⭐)"
            }
            alertas.append({
                "base": sym[:-4], "nivel": 3, "prob": prob,
                "fecha_corta": info.get("fecha_corta", ""), "p_ini": p_ini, "p_act": p_act,
                "var_det": var_det, "mkt": mkt, "tec": tec
            })

        info.update({
            "ultimo_precio": p_act,
            "ultimo_estado": cat,
            "ultima_probabilidad": prob,
            "ultimo_rsi": tec["rsi_1h"],
            "ultimo_vol": tec["vol_surge"],
            "ultima_1h": tec["var_1h"]
        })
        seg[sym] = info

    historial["seguimiento_verde"], historial["graduadas_pre_explosion"] = seg, grad
    return alertas

def motor_ia_seleccion_tactica(session, tickers, activos, historial):
    EXCL = {'USDT','USDC','FDUSD','DAI','TUSD','USDP','EUR','BUSD','USD1','AEUR','EURI','USDE','RLUSD','RWUSD','XUSD','BFUSD','U','USDG','USDS','PYUSD','PAXG','XAUT','BTC','ETH','SOL','ADA','XRP','DOGE','TRX','SHIB','AVAX','LINK','BNB','DOT','NEAR','SUI','PEPE','GBP','TRY','BRL','ARS'}
    menc = historial.get("mencionadas", {})
    for sym in list(menc.keys()):
        menc[sym] -= 1
        if menc[sym] <= 0:
            del menc[sym]

    cand, mapa = [], {}
    for t in tickers:
        sym = t.get('symbol', '')
        if not sym.endswith('USDT') or sym not in activos:
            continue
        base = sym[:-4]
        if base in EXCL or not re.match(r'^[A-Z0-9]+$', base) or base.endswith('B') or any(x in base for x in ['UP','DOWN','BULL','BEAR']):
            continue
        try:
            p, chg, vol, hi, lo = float(t['lastPrice']), float(t['priceChangePercent']), float(t['quoteVolume']), float(t['highPrice']), float(t['lowPrice'])
            if p <= 0:
                continue
            b24 = (p / (1.0 + (chg / 100.0))) if chg > -99.9 else float(t.get('openPrice', p))
            pres = (vol / 1_000_000) / max(((hi - lo) / p) * 100, 1.0)
            it = {'symbol': sym, 'base': base, 'base_24h_f': b24, 'precio_f': p, 'cambio_f': chg, 'vol_f': vol, 'high_f': hi, 'low_f': lo, 'presion': pres}
            mapa[sym] = it
            en_seg = int(historial.get("seguimiento_verde", {}).get(sym, {}).get("estrellas", 0)) >= 1
            if (sym in menc and not en_seg) or not (0.000001 <= p < 5.00 and 600_000 <= vol <= 45_000_000 and -2.5 <= chg <= 5.8):
                continue
            cand.append(it)
        except Exception:
            continue

    seg_prev = historial.get("seguimiento_verde", {})
    semillero_previo_syms = {sym for sym, d in seg_prev.items() if int(d.get("estrellas", 0)) >= 1}

    alertas = evaluar_evolucion_estrellas(session, mapa, historial, semillero_previo_syms)
    seg = historial.get("seguimiento_verde", {})
    semillero_activo_syms = {sym for sym, d in seg.items() if int(d.get("estrellas", 0)) >= 1}
    semillero_activo_bases = {sym[:-4] for sym in semillero_activo_syms}
    h_mon = historial.get("historia_monedas", {})

    r_ok, a_ok, v_ok = [], [], []
    vistos_sym = set()
    prioritarios = [mapa[sym] for sym in semillero_activo_syms if sym in mapa]
    resto = sorted(cand, key=lambda x: x['presion'], reverse=True)[:36]

    for it in prioritarios + resto:
        if it['symbol'] in vistos_sym:
            continue
        vistos_sym.add(it['symbol'])
        tec = calcular_probabilidad_inversion(session, it['symbol'])
        if not tec["ok"] or tec["probabilidad_pct"] < 35:
            continue
        it.update(tec)
        cat, col = clasificar_semaforo(tec["probabilidad_pct"])
        it['categoria'], it['color_hex'] = cat, col

        # Registra y consulta la historia previa de esta moneda
        h_info = registrar_pasado_moneda(
            h_mon, it['symbol'], tec["probabilidad_pct"], it['precio_f'],
            it['cambio_f'], tec["rsi_1h"], tec["vol_surge"], cat
        )
        it['historia'] = h_info
        (r_ok if cat == "ROJO" else (a_ok if cat == "AMARILLO" else v_ok)).append(it)

    for l in (r_ok, a_ok, v_ok):
        l.sort(
            key=lambda x: (
                1 if x['base'] in semillero_activo_bases else 0,
                x['probabilidad_pct'] + int(x.get("historia", {}).get("score_historia", 0))
            ),
            reverse=True
        )

    r7, a7, v7, destacadas, dictamen = curar_con_gemini(r_ok, a_ok, v_ok, semillero_activo_bases)

    grad = historial.get("graduadas_pre_explosion", {})
    hoy_iso, hoy_corta = ahora_art().strftime('%Y-%m-%d'), ahora_art().strftime('%d/%m')

    grupos = {"ROJO": r7, "AMARILLO": a7, "VERDE": v7}
    for ck, lista_g in grupos.items():
        picks_ck = destacadas.get(ck, {})
        for it in lista_g:
            sym, base = it['symbol'], it['base']
            vino_de_verde = sym in semillero_activo_syms
            eleg = base in picks_ck
            h_info = it.get("historia", {})

            it['motivo_ia'] = picks_ck.get(base, "") if eleg else ""
            it['es_evolucion'] = False
            it['estrellas'] = 0

            if ck == "VERDE" and eleg and cumple_base_verde(it):
                it['estrellas'] = 1
                if sym not in seg:
                    seg[sym] = {
                        "fecha_iso": hoy_iso, "fecha_corta": hoy_corta,
                        "precio_deteccion": it['precio_f'], "estrellas": 1,
                        "estado_actual": "VERDE", "ultimo_estado": "VERDE",
                        "ultima_probabilidad": it['probabilidad_pct'],
                        "alerta_2_estrellas_enviada": False, "alerta_3_estrellas_enviada": False
                    }
            elif ck == "AMARILLO" and eleg and vino_de_verde and cumple_evolucion_amarillo(it, h_info):
                it['estrellas'] = 2
                it['es_evolucion'] = True
                seg[sym]["estrellas"] = max(int(seg[sym].get("estrellas", 1)), 2)
                seg[sym]["estado_actual"] = "AMARILLO"
                seg[sym]["ultimo_estado"] = "AMARILLO"
                seg[sym]["ultima_probabilidad"] = it['probabilidad_pct']
            elif ck == "ROJO" and eleg and vino_de_verde and cumple_confirmacion_rojo(it, h_info):
                it['estrellas'] = 3
                it['es_evolucion'] = True
                seg[sym]["estrellas"] = 3
                seg[sym]["estado_actual"] = "ROJO"
                seg[sym]["ultimo_estado"] = "ROJO"
                seg[sym]["ultima_probabilidad"] = it['probabilidad_pct']
                grad[sym] = {
                    "symbol": sym, "base": base, "estrellas": 3,
                    "probabilidad_pct": it['probabilidad_pct'], "precio_ref": it['precio_f'],
                    "fecha_iso": hoy_iso, "fecha_corta": hoy_corta,
                    "origen": "Confirmada para Pre-Explosión (⭐⭐⭐)"
                }

            menc[sym] = 1
            if sym not in historial["resumen_dia"]:
                historial["resumen_dia"].append(sym)

    historial.update({
        "mencionadas": menc,
        "seguimiento_verde": seg,
        "graduadas_pre_explosion": grad,
        "historia_monedas": h_mon
    })
    guardar_historial(historial)
    return grupos, len(cand), historial, dictamen, alertas

def generar_grafico_bloque(items, titulo_graf, subtitulo_graf, filename):
    sims = [f"{'★'*i.get('estrellas',0)}{i['base']}" for i in items]
    probs = [i['probabilidad_pct'] for i in items]
    cols = [i['color_hex'] for i in items]
    ests = [i.get('estrellas', 0) for i in items]

    fig, ax = plt.subplots(figsize=(9.5, 4.6), facecolor='#0b132b')
    ax.set_facecolor('#0b132b')
    bars = ax.bar(sims, probs, color=cols, width=0.52, zorder=3)
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
            bar.set_linewidth(2.5 if est == 3 else (2.0 if est == 2 else 1.6))
            ax.text(xv, yv + 3.0, f"{'★'*est}\n{pr}%", ha='center', va='bottom', color='#ffd700' if est >= 2 else '#ffffff', fontweight='bold', fontsize=8.5)
        else:
            ax.text(xv, yv + 2.5, f"{pr}%", ha='center', va='bottom', color=col, fontweight='bold', fontsize=8.5)
        ax.plot(xv, max(yv / 2.0, 14), marker='o', markersize=17, markerfacecolor='#0f172a', markeredgecolor='#ffd700' if est >= 2 else ('#ffffff' if est == 1 else col), markeredgewidth=2.0 if est > 0 else 1.5, zorder=4)
        ax.text(xv, max(yv / 2.0, 14), it['base'][:5], ha='center', va='center', color='white', fontsize=6.5, fontweight='bold', zorder=5)

    plt.title(titulo_graf, loc='left', color='#ffab00', fontsize=11.5, fontweight='bold', pad=12)
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
    partes, actual = [], ""
    for linea in texto.split("\n"):
        if len(actual) + len(linea) + 1 > 3400:
            if actual.strip():
                partes.append(actual.strip())
            actual = linea + "\n"
        else:
            actual += linea + "\n"
    if actual.strip():
        partes.append(actual.strip())

    for parte in partes:
        payload = {"chat_id": TELEGRAM_CHAT_ID, "text": parte, "parse_mode": "HTML", "disable_web_page_preview": True}
        if tid:
            payload["message_thread_id"] = tid
        try:
            r = requests.post(url, json=payload, timeout=15).json()
            if not r.get("ok") and "thread not found" in str(r.get("description", "")).lower():
                payload.pop("message_thread_id", None)
                requests.post(url, json=payload, timeout=15)
        except Exception as e:
            print(f"⚠️ Error Telegram: {e}")
        time.sleep(1)

def enviar_alerta_evolucion(al):
    sim, mkt, tec, niv = al['base'], al['mkt'], al['tec'], al['nivel']
    uid = int(time.time() * 1000) + random.randint(1, 9999)
    u_ia = f"{BASE_URL_NETLIFY}/?coin={sim}&price={mkt['precio_f']}&change={mkt['cambio_f']}&high={mkt['high_f']}&low={mkt['low_f']}&v={sim}_{uid}"
    u_tr = f"https://www.binance.com/es/trade/{sim}_USDT"
    titulo = "🚨 <b>ALERTA EVOLUCIÓN • ⭐⭐ (ESTABLE DE MIRAR)</b>" if niv == 2 else "🏆 <b>CONFIRMACIÓN INVERSIÓN • ⭐⭐⭐ (PRE-EXPLOSIÓN)</b>"
    zona_txt = f"evolucionó desde ⭐ Verde a 🟡 <b>AMARILLA</b> estable (Prob: <b>{al['prob']}%</b>)." if niv == 2 else f"confirmó su paso a 🔴 <b>ROJA</b> (Prob: <b>{al['prob']}%</b>) y pasa a <b>Pre-Explosión</b>."
    msg = (
        f"{titulo}\n📅 <code>{ahora_art().strftime('%Y-%m-%d %H:%M ART')}</code>\n\n"
        f"⚡ <b>{sim}</b> (iniciada con ⭐ en 🟢 el <code>{al['fecha_corta']}</code> a <code>{formatear_precio(al['p_ini'])}</code>) {zona_txt}\n"
        f"• <b>Actual:</b> <code>{formatear_precio(al['p_act'])}</code> (<b>{al['var_det']:+.2f}%</b> desde detección)\n"
        f"• <b>Técnico:</b> <code>1h: {tec['var_1h']:+.2f}% | RSI: {tec['rsi_1h']} | {tec['ema_estado']} | Vol: x{tec['vol_surge']}</code>\n"
        f"└ <a href=\"{html.escape(u_ia)}\">📊 Resumen IA</a> | <a href=\"{html.escape(u_tr)}\">🔶 Tradear</a>"
    )
    enviar_texto_telegram(msg)

def resumen_cadena_exacta(seg, items_bloque):
    # Refleja exactamente las estrellas asignadas en este bloque (sin desincronizar con el historial)
    marcas = []
    for it in items_bloque:
        est = int(it.get("estrellas", 0))
        if est > 0:
            marcas.append(f"{'⭐'*est} {it['base']} ({it['probabilidad_pct']}%)")
    if marcas:
        return f"📌 <i>Estrellas activas en este bloque: {', '.join(marcas)}</i>\n"
    return ""

def enviar_bloque_color(num_bloque, titulo_msg, titulo_graf, items, seg, dictamen_global=""):
    if not items:
        return
    fname = f"grafico_cazador_{num_bloque}.png"
    fecha_str = ahora_art().strftime('%Y-%m-%d %H:%M ART')
    generar_grafico_bloque(items, titulo_graf, f"Fecha: {fecha_str} | Camino: ★ Verde ➔ ★★ Amarillo ➔ ★★★ Rojo", fname)

    msg = f"🔥 <b>CAZADOR TÁCTICO ({num_bloque}/3)</b>\n{titulo_msg}\n📅 <code>{fecha_str}</code>\n"
    if dictamen_global:
        msg += f"🧠 <i>{html.escape(dictamen_global)}</i>\n"
    nota_cad = resumen_cadena_exacta(seg, items)
    if nota_cad:
        msg += nota_cad
    msg += "\n"

    for it in items:
        sim, sym, est = it['base'], it['symbol'], int(it.get('estrellas', 0))
        uid = int(time.time() * 1000) + random.randint(1, 9999)
        u_ia = f"{BASE_URL_NETLIFY}/?coin={sim}&price={it['precio_f']}&change={it['cambio_f']}&high={it['high_f']}&low={it['low_f']}&v={sim}_{uid}"
        u_tr = f"https://www.binance.com/es/trade/{sim}_USDT"

        tseg = ""
        if sym in seg and it['categoria'] != "VERDE":
            p_det = float(seg[sym].get("precio_deteccion", it['precio_f']))
            var_d = ((it['precio_f'] - p_det) / p_det) * 100 if p_det > 0 else 0.0
            tseg = f" <i>[⭐ {seg[sym]['fecha_corta']} @ {formatear_precio(p_det)} ({var_d:+.2f}%)]</i>"

        if est > 0:
            if it['categoria'] == "ROJO":
                tag_dest = "CONFIRMADA PRE-EXPLOSIÓN"
            elif it['categoria'] == "AMARILLO":
                tag_dest = "EVOLUCIÓN ESTABLE"
            else:
                tag_dest = "CRUDA POTENCIAL"

            mot = html.escape(it.get("motivo_ia", ""))
            msg += (
                f"{'⭐'*est} <b>{sim} [{tag_dest} • Prob: {it['probabilidad_pct']}%]</b> | Base (0%): <code>{formatear_precio(it['base_24h_f'])}</code> ➔ Actual: <code>{formatear_precio(it['precio_f'])}</code> | <b>{it['cambio_f']:+.2f}%</b>\n"
                f"   📐 <code>1h: {it['var_1h']:+.2f}% | RSI: {it['rsi_1h']} | Vol: x{it['vol_surge']}</code>{tseg}\n"
            )
            if mot:
                msg += f"   💡 <i>{mot}</i>\n"
            msg += f"   └ <a href=\"{html.escape(u_ia)}\">📊 Resumen IA</a> | <a href=\"{html.escape(u_tr)}\">🔶 Tradear</a>\n\n"
        else:
            msg += (
                f"• <b>{sim}</b> (Prob: <b>{it['probabilidad_pct']}%</b>) | Base (0%): <code>{formatear_precio(it['base_24h_f'])}</code> ➔ Actual: <code>{formatear_precio(it['precio_f'])}</code> | <b>{it['cambio_f']:+.2f}%</b>\n"
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
                print(f"✅ Bloque {num_bloque}/3 entregado en Telegram.")
                return
        except Exception as e:
            print(f"⚠️ Error bloque {num_bloque}: {e}")
        time.sleep(3)

if __name__ == "__main__":
    print(f"🔥 INICIANDO CAZADOR TÁCTICO CON HISTORIA ({ahora_art().strftime('%H:%M:%S')} ART)...")
    s = crear_sesion_binance()
    activos, datos = obtener_datos_binance(s)
    if datos and activos:
        hist = cargar_historial()
        grupos, tot, hist, dictamen, alertas = motor_ia_seleccion_tactica(s, datos, activos, hist)

        for al in alertas:
            enviar_alerta_evolucion(al)
            time.sleep(1.5)

        seg = hist.get("seguimiento_verde", {})
        enviar_bloque_color(1, "🔴 <b>1. CONFIRMADA PRE-EXPLOSIÓN (72%–98% • ⭐⭐⭐)</b>", "CAZADOR TACTICO (1/3) • CONFIRMADA PRE-EXPLOSION (3 ESTRELLAS)", grupos["ROJO"], seg, dictamen)
        time.sleep(2)
        enviar_bloque_color(2, "🟡 <b>2. EVOLUCIÓN DESDE VERDE (52%–71% • ⭐⭐)</b>", "CAZADOR TACTICO (2/3) • EVOLUCION DESDE VERDE (2 ESTRELLAS)", grupos["AMARILLO"], seg)
        time.sleep(2)
        enviar_bloque_color(3, "🟢 <b>3. INICIO EN VERDE (35%–51% • ⭐)</b>", "CAZADOR TACTICO (3/3) • INICIO EN VERDE (1 ESTRELLA)", grupos["VERDE"], seg)

        if ahora_art().hour >= 21 and not hist.get("resumen_enviado_hoy", False):
            mdia = [x[:-4] for x in hist.get("resumen_dia", [])]
            eradar = [f"{'⭐'*int(d.get('estrellas',1))} {k[:-4]} ({d['fecha_corta']} ➔ {d.get('ultima_probabilidad',0)}%)" for k, d in seg.items() if int(d.get('estrellas', 0)) >= 1]
            if mdia or eradar:
                enviar_texto_telegram(f"📋 <b>RESUMEN DIARIO CAZADOR (21:00 ART)</b>\nHoy: <code>{', '.join(mdia) or 'Ninguna'}</code>\nRadar ⭐: <code>{', '.join(eradar) or 'Vacío'}</code>")
                hist["resumen_enviado_hoy"] = True
                guardar_historial(hist)
    else:
        print("❌ ERROR: Sin datos de Binance.")

# FIN BOT TACTICO
