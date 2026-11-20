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

ESTRELLAS_POR_ZONA = {"VERDE": 1, "AMARILLO": 2, "ROJO": 3}

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
    def fallback_picks(lista, zona):
        if not lista:
            return {}
        rank = sorted(
            lista,
            key=lambda x: (
                x['probabilidad_pct']
                + (6 if 40.0 <= x.get('rsi_1h', 50) <= 62.0 else 0)
                + (5 if -2.5 <= x.get('cambio_f', 0) <= 2.5 else 0)
            ),
            reverse=True
        )
        top_n = rank[:2] if len(rank) >= 4 else rank[:1]
        out = {}
        for x in top_n:
            if zona == "VERDE":
                out[x['base']] = f"Base {x['cambio_f']:+.1f}%, 1h {x['var_1h']:+.2f}% y RSI {x['rsi_1h']}: margen limpio para escalar."
            elif zona == "AMARILLO":
                out[x['base']] = f"Estructura 1h {x['var_1h']:+.2f}%, RSI {x['rsi_1h']} y Vol x{x['vol_surge']}: ganando tracción."
            else:
                out[x['base']] = f"Prob {x['probabilidad_pct']}%, 1h {x['var_1h']:+.2f}% y Vol x{x['vol_surge']}: lista para Pre-Explosión."
        return out

    r7, a7, v7 = rojas[:7], amarillas[:7], verdes[:7]
    destacadas = {
        "ROJO": fallback_picks(r7, "ROJO"),
        "AMARILLO": fallback_picks(a7, "AMARILLO"),
        "VERDE": fallback_picks(v7, "VERDE")
    }
    dictamen = "Radar IA Spot (-2.5% a +5.8%): 1⭐ base/evolución, 2⭐⭐ estructura, 3⭐⭐⭐ lista Pre-Explosión."

    if not GEMINI_API_KEY or not (r7 or a7 or v7):
        return r7, a7, v7, destacadas, dictamen

    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
        fmt = lambda l: "\n".join([
            f"- {i['base']}: prob={i['probabilidad_pct']}%, 24h={i['cambio_f']:+.2f}%, 1h={i['var_1h']:+.2f}%, RSI={i['rsi_1h']}, EMAs={i['ema_estado']}, Vol=x{i['vol_surge']}"
            for i in l
        ]) or "Vacio"

        prompt = (
            "Analista cuantitativo Binance Spot. Evalúa estas 3 listas de monedas ocultas:\n"
            f"ROJO (>=72% - 3 estrellas, listas para radar Pre-Explosión):\n{fmt(rojas)}\n"
            f"AMARILLO (52-71% - 2 estrellas, estructura armada):\n{fmt(amarillas)}\n"
            f"VERDE (35-51% - 1 estrella, base temprana con margen antes de subir):\n{fmt(verdes)}\n\n"
            "Reglas estrictas:\n"
            "1. Ordena las mejores 7 de cada color.\n"
            "2. Elige entre 1 y 3 monedas destacadas por color.\n"
            "3. En VERDE, prioriza monedas que no estén ya disparadas en 24h y tengan RSI/estructura sana para poder escalar; escribe un motivo DISTINTO y específico para cada moneda elegida citando sus datos reales (<85 chars).\n"
            "4. Escribe un dictamen breve (<120 chars).\n"
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

                    def procesar_grupo(pool, orden_ia, dest_ia, dest_def):
                        mapa = {x['base']: x for x in pool}
                        picks = {}
                        for d in (dest_ia or [])[:3]:
                            s = str(d.get("symbol", "")).strip().upper()
                            m = str(d.get("motivo", "")).strip()
                            if s in mapa:
                                picks[s] = (m or dest_def.get(s) or list(dest_def.values())[0])[:95]
                        if not picks:
                            picks = dest_def

                        sel = [mapa[s] for s in picks if s in mapa]
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
                        validos_f7 = {x['base'] for x in f7}
                        picks_final = {k: v for k, v in picks.items() if k in validos_f7}
                        return f7, picks_final

                    r7, dr = procesar_grupo(rojas, data.get("rojas"), data.get("dest_roja"), destacadas["ROJO"])
                    a7, da = procesar_grupo(amarillas, data.get("amarillas"), data.get("dest_amarilla"), destacadas["AMARILLO"])
                    v7, dv = procesar_grupo(verdes, data.get("verdes"), data.get("dest_verde"), destacadas["VERDE"])
                    return r7, a7, v7, {"ROJO": dr, "AMARILLO": da, "VERDE": dv}, str(data.get("dictamen") or dictamen)[:140]
            except Exception:
                continue
    except Exception as e:
        print(f"⚠️ Fallback Gemini: {e}")
    return r7, a7, v7, destacadas, dictamen

def evaluar_evolucion_estrellas(session, mapa_mercado, historial):
    seg = historial.get("seguimiento_verde", {})
    grad = historial.get("graduadas_pre_explosion", {})
    alertas = []
    hoy_iso, hoy_corta = ahora_art().strftime('%Y-%m-%d'), ahora_art().strftime('%d/%m')

    for sym, info in list(seg.items()):
        mkt = mapa_mercado.get(sym)
        if not mkt or int(info.get("estrellas", 0)) < 1:
            continue
        tec = calcular_probabilidad_inversion(session, sym)
        if not tec["ok"]:
            continue

        prob = tec["probabilidad_pct"]
        cat, _ = clasificar_semaforo(prob)
        est_prev = int(info.get("estrellas", 1))
        p_act, p_ini = mkt['precio_f'], float(info.get("precio_deteccion", mkt['precio_f']))
        var_det = ((p_act - p_ini) / p_ini) * 100 if p_ini > 0 else 0.0

        if cat == "AMARILLO" and est_prev < 2 and not info.get("alerta_2_estrellas_enviada", False):
            info.update({"estrellas": 2, "estado_actual": "AMARILLO", "alerta_2_estrellas_enviada": True})
            grad[sym] = {"symbol": sym, "base": sym[:-4], "estrellas": 2, "probabilidad_pct": prob, "precio_ref": p_act, "fecha_iso": hoy_iso, "fecha_corta": hoy_corta, "origen": "Evolución Cazador (⭐⭐)"}
            alertas.append({"base": sym[:-4], "nivel": 2, "prob": prob, "fecha_corta": info.get("fecha_corta", ""), "p_ini": p_ini, "p_act": p_act, "var_det": var_det, "mkt": mkt, "tec": tec})
        elif cat == "ROJO" and est_prev < 3 and not info.get("alerta_3_estrellas_enviada", False):
            info.update({"estrellas": 3, "estado_actual": "ROJO", "alerta_2_estrellas_enviada": True, "alerta_3_estrellas_enviada": True})
            grad[sym] = {"symbol": sym, "base": sym[:-4], "estrellas": 3, "probabilidad_pct": prob, "precio_ref": p_act, "fecha_iso": hoy_iso, "fecha_corta": hoy_corta, "origen": "Confirmación Máxima (⭐⭐⭐)"}
            alertas.append({"base": sym[:-4], "nivel": 3, "prob": prob, "fecha_corta": info.get("fecha_corta", ""), "p_ini": p_ini, "p_act": p_act, "var_det": var_det, "mkt": mkt, "tec": tec})

        info.update({"ultimo_precio": p_act, "ultimo_estado": cat, "ultima_probabilidad": prob})
        seg[sym] = info

    historial["seguimiento_verde"], historial["graduadas_pre_explosion"] = seg, grad
    return alertas

def motor_ia_seleccion_tactica(session, tickers, activos, historial):
    EXCL = {'USDT','USDC','FDUSD','DAI','TUSD','USDP','EUR','BUSD','USD1','AEUR','EURI','USDE','RLUSD','RWUSD','XUSD','BFUSD','U','USDG','USDS','PYUSD','PAXG','XAUT','BTC','ETH','SOL','ADA','XRP','DOGE','TRX','SHIB','AVAX','LINK','BNB','DOT','NEAR','SUI','PEPE','GBP','TRY','BRL','ARS'}
    menc = historial.get("mencionadas", {})
    for sym in list(menc.keys()):
        menc[sym] -= 1
        if menc[sym] <= 0: del menc[sym]

    cand, mapa = [], {}
    for t in tickers:
        sym = t.get('symbol', '')
        if not sym.endswith('USDT') or sym not in activos: continue
        base = sym[:-4]
        if base in EXCL or not re.match(r'^[A-Z0-9]+$', base) or base.endswith('B') or any(x in base for x in ['UP','DOWN','BULL','BEAR']): continue
        try:
            p, chg, vol, hi, lo = float(t['lastPrice']), float(t['priceChangePercent']), float(t['quoteVolume']), float(t['highPrice']), float(t['lowPrice'])
            if p <= 0: continue
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

    alertas = evaluar_evolucion_estrellas(session, mapa, historial)
    r_ok, a_ok, v_ok = [], [], []
    for it in sorted(cand, key=lambda x: x['presion'], reverse=True)[:36]:
        tec = calcular_probabilidad_inversion(session, it['symbol'])
        if not tec["ok"] or tec["probabilidad_pct"] < 35: continue
        it.update(tec)
        cat, col = clasificar_semaforo(tec["probabilidad_pct"])
        it['categoria'], it['color_hex'] = cat, col
        (r_ok if cat == "ROJO" else (a_ok if cat == "AMARILLO" else v_ok)).append(it)

    for l in (r_ok, a_ok, v_ok): l.sort(key=lambda x: x['probabilidad_pct'], reverse=True)
    r7, a7, v7, destacadas, dictamen = curar_con_gemini(r_ok, a_ok, v_ok)

    seg, grad = historial.get("seguimiento_verde", {}), historial.get("graduadas_pre_explosion", {})
    hoy_iso, hoy_corta = ahora_art().strftime('%Y-%m-%d'), ahora_art().strftime('%d/%m')

    grupos = {"ROJO": r7, "AMARILLO": a7, "VERDE": v7}
    for ck, lista_g in grupos.items():
        picks_ck = destacadas.get(ck, {})
        est_zona = ESTRELLAS_POR_ZONA[ck]
        for it in lista_g:
            sym, base = it['symbol'], it['base']
            eleg = base in picks_ck
            it['motivo_ia'] = picks_ck.get(base, "") if eleg else ""
            it['estrellas'] = est_zona if eleg else 0
            it['es_evolucion'] = bool(eleg and ck in ("AMARILLO", "ROJO") and int(seg.get(sym, {}).get("estrellas", 0)) >= 2)

            if ck == "VERDE" and eleg and sym not in seg:
                seg[sym] = {"fecha_iso": hoy_iso, "fecha_corta": hoy_corta, "precio_deteccion": it['precio_f'], "estrellas": 1, "estado_actual": "VERDE", "ultimo_estado": "VERDE", "ultima_probabilidad": it['probabilidad_pct'], "alerta_2_estrellas_enviada": False, "alerta_3_estrellas_enviada": False}
            elif sym in seg and ck in ("AMARILLO", "ROJO"):
                seg[sym]["estrellas"] = max(int(seg
