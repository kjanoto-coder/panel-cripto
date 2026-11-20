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
        "graduadas_pre_explosion": {}
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

def pasa_requisito_amarillo(tec):
    return (
        tec.get("ok")
        and tec.get("probabilidad_pct", 0) >= 58
        and tec.get("rsi_1h", 100) <= 68.0
        and (tec.get("vol_surge", 0) >= 1.15 or tec.get("var_1h", -99) >= 0.25)
    )

def pasa_requisito_rojo(tec):
    return (
        tec.get("ok")
        and tec.get("probabilidad_pct", 0) >= 75
        and tec.get("rsi_1h", 100) <= 72.0
        and (tec.get("vol_surge", 0) >= 1.20 and tec.get("var_1h", -99) > -0.20)
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

def curar_con_gemini(rojas, amarillas, verdes, semillero_previo):
    def picks_verde(lista):
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
        return {
            x['base']: f"Base {x['cambio_f']:+.1f}%, 1h {x['var_1h']:+.2f}% y RSI {x['rsi_1h']}: inicia camino ⭐."
            for x in top_n
        }

    def picks_evolucion(lista, nivel):
        if nivel == 2:
            validas = [x for x in lista if x['base'] in semillero_previo and pasa_requisito_amarillo(x)]
        else:
            validas = [x for x in lista if x['base'] in semillero_previo and pasa_requisito_rojo(x)]
        validas.sort(key=lambda x: x['probabilidad_pct'], reverse=True)
        out = {}
        for x in validas[:3]:
            if nivel == 2:
                out[x['base']] = f"Vino de ⭐ Verde: 1h {x['var_1h']:+.2f}%, RSI {x['rsi_1h']} y Vol x{x['vol_surge']}: evoluciona ⭐⭐."
            else:
                out[x['base']] = f"Vino de ⭐ Verde: Prob {x['probabilidad_pct']}%, 1h {x['var_1h']:+.2f}% y Vol x{x['vol_surge']}: confirmada ⭐⭐⭐."
        return out

    r7, a7, v7 = rojas[:7], amarillas[:7], verdes[:7]
    destacadas = {
        "ROJO": picks_evolucion(r7, 3),
        "AMARILLO": picks_evolucion(a7, 2),
        "VERDE": picks_verde(v7)
    }
    dictamen = "Camino por etapas: ⭐ Verde inicia ➔ ⭐⭐ Amarillo evoluciona ➔ ⭐⭐⭐ Rojo confirma para Pre-Explosión."

    if not GEMINI_API_KEY or not (r7 or a7 or v7):
        return r7, a7, v7, destacadas, dictamen

    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
        fmt = lambda l: "\n".join([
            f"- {i['base']}{' [SEMILLERO_PREVIO]' if i['base'] in semillero_previo else ''}: prob={i['probabilidad_pct']}%, 24h={i['cambio_f']:+.2f}%, 1h={i['var_1h']:+.2f}%, RSI={i['rsi_1h']}, EMAs={i['ema_estado']}, Vol=x{i['vol_surge']}"
            for i in l
        ]) or "Vacio"

        prompt = (
            "Analista cuantitativo Binance Spot. Cada moneda debe arrancar en VERDE (1⭐) y evolucionar en etapas:\n"
            "- VERDE (35-51%): elegí 1 a 2 monedas de base sana y margen para iniciar el camino (1⭐).\n"
            "- AMARILLO (52-71%): SOLO monedas marcadas [SEMILLERO_PREVIO] que cumplan requisitos técnicos sólidos (RSI<=68 y buen volumen/impulso) reciben 2⭐⭐.\n"
            "- ROJO (>=72%): SOLO monedas marcadas [SEMILLERO_PREVIO] que cumplan requisitos técnicos sólidos reciben 3⭐⭐⭐ para pasar a Pre-Explosión.\n\n"
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

                    def procesar_grupo(pool, orden_ia, dest_ia, dest_def, exigir_previo=False, nivel=1):
                        mapa = {x['base']: x for x in pool}
                        picks = {}
                        for d in (dest_ia or [])[:3]:
                            s = str(d.get("symbol", "")).strip().upper()
                            m = str(d.get("motivo", "")).strip()
                            if s in mapa:
                                ok_req = True
                                if exigir_previo:
                                    ok_req = (s in semillero_previo) and (pasa_requisito_rojo(mapa[s]) if nivel == 3 else pasa_requisito_amarillo(mapa[s]))
                                if ok_req:
                                    picks[s] = (m or dest_def.get(s) or list(dest_def.values())[0])[:95]
                        if not picks:
                            picks = dest_def

                        sel = []
                        if exigir_previo:
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
                        return f7, {k: v for k, v in picks.items() if k in validos}

                    r7, dr = procesar_grupo(rojas, data.get("rojas"), data.get("dest_roja"), destacadas["ROJO"], exigir_previo=True, nivel=3)
                    a7, da = procesar_grupo(amarillas, data.get("amarillas"), data.get("dest_amarilla"), destacadas["AMARILLO"], exigir_previo=True, nivel=2)
                    v7, dv = procesar_grupo(verdes, data.get("verdes"), data.get("dest_verde"), destacadas["VERDE"], exigir_previo=False, nivel=1)
                    return r7, a7, v7, {"ROJO": dr, "AMARILLO": da, "VERDE": dv}, str(data.get("dictamen") or dictamen)[:140]
            except Exception:
                continue
    except Exception as e:
        print(f"⚠️ Fallback Gemini: {e}")
    return r7, a7, v7, destacadas, dictamen

def evaluar_evolucion_estrellas(session, mapa_mercado, historial, semillero_previo_syms):
    seg = historial.get("seguimiento_verde", {})
    grad = historial.get("graduadas_pre_explosion", {})
    alertas = []
    hoy_iso, hoy_corta = ahora_art().strftime('%Y-%m-%d'), ahora_art().strftime('%d/%m')

    # Solo evalúa monedas que ya venían de una corrida anterior (no las recién elegidas en este mismo ciclo)
    for sym in semillero_previo_syms:
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

        if cat == "AMARILLO" and pasa_requisito_amarillo(tec) and est_prev < 2 and not info.get("alerta_2_estrellas_enviada", False):
            info.update({"estrellas": 2, "estado_actual": "AMARILLO", "alerta_2_estrellas_enviada": True})
            grad[sym] = {
                "symbol": sym, "base": sym[:-4], "estrellas": 2, "probabilidad_pct": prob,
                "precio_ref": p_act, "fecha_iso": hoy_iso, "fecha_corta": hoy_corta,
                "origen": "Evolución desde ⭐ Verde (⭐⭐)"
            }
            alertas.append({
                "base": sym[:-4], "nivel": 2, "prob": prob,
                "fecha_corta": info.get("fecha_corta", ""), "p_ini": p_ini, "p_act": p_act,
                "var_det": var_det, "mkt": mkt, "tec": tec
            })
        elif cat == "ROJO" and pasa_requisito_rojo(tec) and est_prev < 3 and not info.get("alerta_3_estrellas_enviada", False):
            info.update({"estrellas": 3, "estado_actual": "ROJO", "alerta_2_estrellas_enviada": True, "alerta_3_estrellas_enviada": True})
            grad[sym] = {
                "symbol": sym, "base": sym[:-4], "estrellas": 3, "probabilidad_pct": prob,
                "precio_ref": p_act, "fecha_iso": hoy_iso, "fecha_corta": hoy_corta,
                "origen": "Confirmada desde ⭐ Verde (⭐⭐⭐)"
            }
            alertas.append({
                "base": sym[:-4], "nivel": 3, "prob": prob,
                "fecha_corta": info.get("fecha_corta", ""), "p_ini": p_ini, "p_act": p_act,
                "var_det": var_det, "mkt": mkt, "tec": tec
            })

        info.update({"ultimo_precio": p_act, "ultimo_estado": cat, "ultima_probabilidad": prob})
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
    semillero_previo_bases = {sym[:-4] for sym in semillero_previo_syms}

    alertas = evaluar_evolucion_estrellas(session, mapa, historial, semillero_previo_syms)
    seg = historial.get("seguimiento_verde", {})

    r_ok, a_ok, v_ok = [], [], []
    vistos_sym = set()
    prioritarios = [mapa[sym] for sym in semillero_previo_syms if sym in mapa]
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
        (r_ok if cat == "ROJO" else (a_ok if cat == "AMARILLO" else v_ok)).append(it)

    for l in (r_ok, a_ok, v_ok):
        l.sort(key=lambda x: (1 if x['base'] in semillero_previo_bases else 0, x['probabilidad_pct']), reverse=True)

    r7, a7, v7, destacadas, dictamen = curar_con_gemini(r_ok, a_ok, v_ok, semillero_previo_bases)

    grad = historial.get("graduadas_pre_explosion", {})
    hoy_iso, hoy_corta = ahora_art().strftime('%Y-%m-%d'), ahora_art().strftime('%d/%m')

    grupos = {"ROJO": r7, "AMARILLO": a7, "VERDE": v7}
    for ck, lista_g in grupos.items():
        picks_ck = destacadas.get(ck, {})
        for it in lista_g:
            sym, base = it['symbol'], it['base']
            vino_de_verde = sym in semillero_previo_syms
            eleg = base in picks_ck

            it['motivo_ia'] = picks_ck.get(base, "") if eleg else ""
            it['es_evolucion'] = False

            if ck == "VERDE" and eleg and not vino_de_verde:
                it['estrellas'] = 1
                if sym not in seg:
                    seg[sym] = {
                        "fecha_iso": hoy_iso, "fecha_corta": hoy_corta,
                        "precio_deteccion": it['precio_f'], "estrellas": 1,
                        "estado_actual": "VERDE", "ultimo_estado": "VERDE",
                        "ultima_probabilidad": it['probabilidad_pct'],
                        "alerta_2_estrellas_enviada": False, "alerta_3_estrellas_enviada": False
                    }
            elif ck == "AMARILLO" and eleg and vino_de_verde and pasa_requisito_amarillo(it):
                it['estrellas'] = 2
                it['es_evolucion'] = True
                seg[sym]["estrellas"] = max(int(seg[sym].get("estrellas", 1)), 2)
                seg[sym]["ultimo_estado"] = "AMARILLO"
                seg[sym]["ultima_probabilidad"] = it['probabilidad_pct']
            elif ck == "ROJO" and eleg and vino_de_verde and pasa_requisito_rojo(it):
                it['estrellas'] = 3
                it['es_evolucion'] = True
                seg[sym]["estrellas"] = 3
                seg[sym]["ultimo_estado"] = "ROJO"
                seg[sym]["ultima_probabilidad"] = it['probabilidad_pct']
                grad[sym] = {
                    "symbol": sym, "base": base, "estrellas": 3,
                    "probabilidad_pct": it['probabilidad_pct'], "precio_ref": it['precio_f'],
                    "fecha_iso": hoy_iso, "fecha_corta": hoy_corta,
                    "origen": "Camino Completo Verde ➔ Rojo (⭐⭐⭐)"
                }
            else:
                it['estrellas'] = 0

            menc[sym] = 1
            if sym not in historial["resumen_dia"]:
                historial["resumen_dia"].append(sym)

    historial.update({"mencionadas": menc, "seguimiento_verde": seg, "graduadas_pre_explosion": grad})
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
    titulo = "🚨 <b>ALERTA EVOLUCIÓN • ⭐⭐ (2 ESTRELLAS)</b>" if niv == 2 else "🏆 <b>CONFIRMACIÓN INVERSIÓN • ⭐⭐⭐ (3 ESTRELLAS)</b>"
    zona_txt = f"evolucionó desde ⭐ Verde a zona 🟡 <b>AMARILLA</b> (Prob: <b>{al['prob']}%</b>)." if niv == 2 else f"alcanzó zona 🔴 <b>ROJA</b> (Prob: <b>{al['prob']}%</b>) y pasa confirmada al radar verde de <b>Pre-Explosión</b>."
    msg = (
        f"{titulo}\n📅 <code>{ahora_art().strftime('%Y-%m-%d %H:%M ART')}</code>\n\n"
        f"⚡ <b>{sim}</b> (iniciada con ⭐ en 🟢 el <code>{al['fecha_corta']}</code> a <code>{formatear_precio(al['p_ini'])}</code>) {zona_txt}\n"
        f"• <b>Actual:</b> <code>{formatear_precio(al['p_act'])}</code> (<b>{al['var_det']:+.2f}%</b> desde detección)\n"
        f"• <b>Técnico:</b> <code>1h: {tec['var_1h']:+.2f}% | RSI: {tec['rsi_1h']} | {tec['ema_estado']} | Vol: x{tec['vol_surge']}</code>\n"
        f"└ <a href=\"{html.escape(u_ia)}\">📊 Resumen IA</a> | <a href=\"{html.escape(u_tr)}\">🔶 Tradear</a>"
    )
    enviar_texto_telegram(msg)

def enviar_bloque_color(num_bloque, titulo_msg, titulo_graf, items, seg, dictamen_global=""):
    if not items:
        return
    fname = f"grafico_cazador_{num_bloque}.png"
    fecha_str = ahora_art().strftime('%Y-%m-%d %H:%M ART')
    generar_grafico_bloque(items, titulo_graf, f"Fecha: {fecha_str} | Camino: ★ Verde ➔ ★★ Amarillo ➔ ★★★ Rojo", fname)

    msg = f"🔥 <b>CAZADOR TÁCTICO ({num_bloque}/3)</b>\n{titulo_msg}\n📅 <code>{fecha_str}</code>\n"
    if dictamen_global:
        msg += f"🧠 <i>{html.escape(dictamen_global)}</i>\n"
    msg += "\n"

    for it in items:
        sim, sym, est = it['base'], it['symbol'], it.get('estrellas', 0)
        uid = int(time.time() * 1000) + random.randint(1, 9999)
        u_ia = f"{BASE_URL_NETLIFY}/?coin={sim}&price={it['precio_f']}&change={it['cambio_f']}&high={it['high_f']}&low={it['low_f']}&v={sim}_{uid}"
        u_tr = f"https://www.binance.com/es/trade/{sim}_USDT"
        tseg = f" <i>[👁️ {seg[sym]['fecha_corta']}]</i>" if (sym in seg and it['categoria'] != "VERDE") else ""

        if est > 0:
            if it['categoria'] == "ROJO":
                tag_dest = "CONFIRMADA PRE-EXPLOSIÓN"
            elif it['categoria'] == "AMARILLO":
                tag_dest = "EVOLUCIÓN CONFIRMADA"
            else:
                tag_dest = "INICIO CAMINO VERDE"

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
    print(f"🔥 INICIANDO CAZADOR TÁCTICO POR ETAPAS ({ahora_art().strftime('%H:%M:%S')} ART)...")
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
