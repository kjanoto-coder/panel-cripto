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
                    raw = res.text.strip()
                    if "{" in raw and "}" in raw:
                        raw = raw[raw.find("{"):raw.rfind("}") + 1]
                    data = json.loads(raw)
                    def ordenar(pool, eleg, tobj, tdef):
                        mapa = {x['base']: x for x in pool}
                        tsym = str((tobj or {}).get("symbol", "")).strip().upper()
                        tmot = str((tobj or {}).get("motivo", "")).strip() or tdef["motivo"]
                        sel = [mapa[tsym]] if tsym in mapa else []
                        for s in eleg:
                            su = str(s).strip().upper()
                            if su in mapa and mapa[su] not in sel: sel.append(mapa[su])
                        for x in pool:
                            if len(sel) >= 7: break
                            if x not in sel: sel.append(x)
                        f7 = sel[:7]
                        return f7, {"symbol": f7[0]['base'] if f7 else "", "motivo": tmot[:105]}
                    rf, tr = ordenar(rojas, data.get("rojas", []), data.get("top_roja"), tops["ROJO"])
                    af, ta = ordenar(amarillas, data.get("amarillas", []), data.get("top_amarilla"), tops["AMARILLO"])
                    vf, tv = ordenar(verdes, data.get("verdes", []), data.get("top_verde"), tops["VERDE"])
                    return rf + af + vf, {"ROJO": tr, "AMARILLO": ta, "VERDE": tv}, str(data.get("dictamen") or dictamen)[:140]
            except Exception:
                continue
    except Exception as e:
        print(f"⚠️ Fallback Gemini: {e}")
    return fallback, tops, dictamen

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

        if cat == "AMARILLO" and est_prev == 1 and not info.get("alerta_2_estrellas_enviada", False):
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
    matriz, tops, dictamen = curar_con_gemini(r_ok, a_ok, v_ok)
    top_syms = {tops[k]["symbol"] for k in tops if tops[k].get("symbol")}

    seg, grad = historial.get("seguimiento_verde", {}), historial.get("graduadas_pre_explosion", {})
    hoy_iso, hoy_corta = ahora_art().strftime('%Y-%m-%d'), ahora_art().strftime('%d/%m')

    for it in matriz:
        sym, base = it['symbol'], it['base']
        eleg = base in top_syms
        est_seg = int(seg.get(sym, {}).get("estrellas", 0))
        if it['categoria'] == "VERDE" and eleg and (sym not in seg or est_seg < 1):
            seg[sym] = {"fecha_iso": hoy_iso, "fecha_corta": hoy_corta, "precio_deteccion": it['precio_f'], "estrellas": 1, "estado_actual": "VERDE", "ultimo_estado": "VERDE", "ultima_probabilidad": it['probabilidad_pct'], "alerta_2_estrellas_enviada": False, "alerta_3_estrellas_enviada": False}
            est_seg = 1
        it['estrellas'] = est_seg if est_seg >= 2 else (max(est_seg, 1) if eleg else 0)
        if (it['categoria'] in ["ROJO", "AMARILLO"] and eleg) or it['estrellas'] >= 2:
            grad[sym] = {"symbol": sym, "base": base, "estrellas": it['estrellas'], "probabilidad_pct": it['probabilidad_pct'], "precio_ref": it['precio_f'], "fecha_iso": hoy_iso, "fecha_corta": hoy_corta, "origen": f"Cazador ({it['categoria']} {'⭐'*it['estrellas']})"}
        menc[sym] = 1
        if sym not in historial["resumen_dia"]: historial["resumen_dia"].append(sym)

    historial.update({"mencionadas": menc, "seguimiento_verde": seg, "graduadas_pre_explosion": grad})
    guardar_historial(historial)
    return matriz, len(cand), historial, tops, dictamen, alertas

def generar_grafico_matriz(items, filename="grafico_cazador_21.png"):
    sims = [f"{'★'*i.get('estrellas',0)}{i['base']}" for i in items]
    probs = [i['probabilidad_pct'] for i in items]
    cols = [i['color_hex'] for i in items]
    ests = [i.get('estrellas', 0) for i in items]

    fig, ax = plt.subplots(figsize=(15, 5.8), facecolor='#0b132b')
    ax.set_facecolor('#0b132b')
    bars = ax.bar(sims, probs, color=cols, width=0.58, zorder=3)
    ax.grid(True, color='#1e293b', linewidth=0.8, zorder=1)
    ax.set_ylim(0, 122)
    for sp in ['top', 'right', 'left', 'bottom']: ax.spines[sp].set_visible(False)
    ax.tick_params(left=False, labelleft=False, bottom=False)
    ax.tick_params(axis='x', colors='white', labelsize=8, rotation=32)

    for bar, it, pr, col, est in zip(bars, items, probs, cols, ests):
        yv, xv = bar.get_height(), bar.get_x() + bar.get_width() / 2.0
        if est > 0:
            bar.set_edgecolor('#ffd700' if est >= 2 else '#ffffff')
            bar.set_linewidth(2.4 if est == 3 else 1.8)
            ax.text(xv, yv + 3.0, f"{'★'*est}\n{pr}%", ha='center', va='bottom', color='#ffd700' if est >= 2 else '#ffffff', fontweight='bold', fontsize=8)
        else:
            ax.text(xv, yv + 2.5, f"{pr}%", ha='center', va='bottom', color=col, fontweight='bold', fontsize=8)
        ax.plot(xv, max(yv / 2.0, 14), marker='o', markersize=15, markerfacecolor='#0f172a', markeredgecolor='#ffd700' if est >= 2 else ('#ffffff' if est == 1 else col), markeredgewidth=2.0 if est > 0 else 1.5, zorder=4)
        ax.text(xv, max(yv / 2.0, 14), it['base'][:5], ha='center', va='center', color='white', fontsize=5.8, fontweight='bold', zorder=5)

    plt.title("CAZADOR TACTICO • PROBABILIDAD DE EXPLOSION (MONEDAS OCULTAS)", loc='left', color='#ffab00', fontsize=11.5, fontweight='bold', pad=12)
    ax.text(0.0, 1.02, f"Fecha: {ahora_art().strftime('%Y-%m-%d %H:%M ART')} | ★=Inicio | ★★=Evolucion | ★★★=Confirmada Pre-Explosion", transform=ax.transAxes, color='#94a3b8', fontsize=8.5)
    plt.tight_layout()
    plt.savefig(filename, dpi=300, facecolor=fig.get_facecolor())
    plt.close()
    return filename

def enviar_texto_telegram(texto):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID: return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    tid = int(TELEGRAM_TOPIC_ID) if TELEGRAM_TOPIC_ID.isdigit() else None
    partes, actual = [], ""
    for linea in texto.split("\n"):
        if len(actual) + len(linea) + 1 > 3400:
            if actual.strip(): partes.append(actual.strip())
            actual = linea + "\n"
        else:
            actual += linea + "\n"
    if actual.strip(): partes.append(actual.strip())

    for idx, parte in enumerate(partes, 1):
        payload = {"chat_id": TELEGRAM_CHAT_ID, "text": parte, "parse_mode": "HTML", "disable_web_page_preview": True}
        if tid: payload["message_thread_id"] = tid
        try:
            r = requests.post(url, json=payload, timeout=15).json()
            if not r.get("ok") and "thread not found" in str(r.get("description", "")).lower():
                payload.pop("message_thread_id", None)
                r = requests.post(url, json=payload, timeout=15).json()
            print(f"✅ Bloque texto {idx}/{len(partes)} entregado." if r.get("ok") else f"❌ Error bloque {idx}: {r.get('description')}")
        except Exception as e:
            print(f"⚠️ Error Telegram: {e}")
        time.sleep(1)

def enviar_alerta_evolucion(al):
    sim, mkt, tec, niv = al['base'], al['mkt'], al['tec'], al['nivel']
    uid = int(time.time() * 1000) + random.randint(1, 9999)
    u_ia = f"{BASE_URL_NETLIFY}/?coin={sim}&price={mkt['precio_f']}&change={mkt['cambio_f']}&high={mkt['high_f']}&low={mkt['low_f']}&v={sim}_{uid}"
    u_tr = f"https://www.binance.com/es/trade/{sim}_USDT"
    titulo = "🚨 <b>ALERTA EVOLUCIÓN • ⭐⭐ (2 ESTRELLAS)</b>" if niv == 2 else "🏆 <b>CONFIRMACIÓN INVERSIÓN • ⭐⭐⭐ (3 ESTRELLAS)</b>"
    zona_txt = f"subió a zona 🟡 <b>AMARILLA</b> (Prob: <b>{al['prob']}%</b>)." if niv == 2 else f"alcanzó zona 🔴 <b>ROJA</b> (Prob: <b>{al['prob']}%</b>) y queda confirmada para <b>Pre-Explosión</b>."
    msg = (
        f"{titulo}\n📅 <code>{ahora_art().strftime('%Y-%m-%d %H:%M ART')}</code>\n\n"
        f"⚡ <b>*{sim}*</b> (cazada con ⭐ en 🟢 el <code>{al['fecha_corta']}</code> a <code>{formatear_precio(al['p_ini'])}</code>) {zona_txt}\n"
        f"• <b>Actual:</b> <code>{formatear_precio(al['p_act'])}</code> (<b>{al['var_det']:+.2f}%</b> desde detección)\n"
        f"• <b>Técnico:</b> <code>1h: {tec['var_1h']:+.2f}% | RSI: {tec['rsi_1h']} | {tec['ema_estado']} | Vol: x{tec['vol_surge']}</code>\n"
        f"└ <a href=\"{html.escape(u_ia)}\">📊 Resumen IA</a> | <a href=\"{html.escape(u_tr)}\">🔶 Tradear</a>"
    )
    enviar_texto_telegram(msg)

def enviar_telegram_blindado(img, texto):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID: return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
    tid = int(TELEGRAM_TOPIC_ID) if TELEGRAM_TOPIC_ID.isdigit() else None
    for _ in range(3):
        try:
            pf = {"chat_id": TELEGRAM_CHAT_ID}
            if tid: pf["message_thread_id"] = tid
            with open(img, 'rb') as ph:
                res = requests.post(url, data=pf, files={"photo": ph}, timeout=25).json()
                if not res.get("ok") and "thread not found" in str(res.get("description", "")).lower():
                    pf.pop("message_thread_id", None)
                    ph.seek(0)
                    res = requests.post(url, data=pf, files={"photo": ph}, timeout=25).json()
            if res.get("ok"):
                print("✅ Gráfico Cazador Táctico entregado.")
                enviar_texto_telegram(texto)
                return
        except Exception as e:
            print(f"⚠️ Error foto: {e}")
        time.sleep(3)

if __name__ == "__main__":
    print(f"🔥 INICIANDO CAZADOR TÁCTICO ({ahora_art().strftime('%H:%M:%S')} ART)...")
    s = crear_sesion_binance()
    activos, datos = obtener_datos_binance(s)
    if datos and activos:
        hist = cargar_historial()
        matriz, tot, hist, tops, dictamen, alertas = motor_ia_seleccion_tactica(s, datos, activos, hist)
        for al in alertas:
            enviar_alerta_evolucion(al)
            time.sleep(1.5)
        if matriz:
            fname = generar_grafico_matriz(matriz)
            msg = f"🔥 <b>CAZADOR TÁCTICO • PROBABILIDAD ({len(matriz)} OCULTAS)</b>\n📅 <code>{ahora_art().strftime('%Y-%m-%d %H:%M ART')}</code> | Analizadas: {tot}\n🧠 <i>{html.escape(dictamen)}</i>\n\n"
            cats = [("ROJO", "🔴 <b>PROBABILIDAD MÁXIMA (72%–98%)</b>"), ("AMARILLO", "🟡 <b>PROBABILIDAD ALTA (52%–71%)</b>"), ("VERDE", "🟢 <b>PROBABILIDAD INICIAL (35%–51%)</b>")]
            seg = hist.get("seguimiento_verde", {})
            for ck, ct in cats:
                ic = [i for i in matriz if i['categoria'] == ck]
                if not ic: continue
                msg += f"{ct}\n"
                for it in ic:
                    sim, sym, est = it['base'], it['symbol'], it.get('estrellas', 0)
                    uid = int(time.time() * 1000) + random.randint(1, 9999)
                    u_ia = f"{BASE_URL_NETLIFY}/?coin={sim}&price={it['precio_f']}&change={it['cambio_f']}&high={it['high_f']}&low={it['low_f']}&v={sim}_{uid}"
                    u_tr = f"https://www.binance.com/es/trade/{sim}_USDT"
                    tseg = f" <i>[👁️ {seg[sym]['fecha_corta']}]</i>" if sym in seg else ""
                    if est > 0:
                        mot = html.escape(tops.get(ck, {}).get("motivo", ""))
                        msg += f"{'⭐'*est} <b>*{sim}* [MEJOR OPCIÓN • Prob: {it['probabilidad_pct']}%]</b> | Base (0%): <code>{formatear_precio(it['base_24h_f'])}</code> ➔ Actual: <code>{formatear_precio(it['precio_f'])}</code> | <b>{it['cambio_f']:+.2f}%</b>\n   📐 <code>1h: {it['var_1h']:+.2f}% | RSI: {it['rsi_1h']} | Vol: x{it['vol_surge']}</code>{tseg}\n   💡 <i>{mot}</i>\n   └ <a href=\"{html.escape(u_ia)}\">📊 Resumen IA</a> | <a href=\"{html.escape(u_tr)}\">🔶 Tradear</a>\n"
                    else:
                        msg += f"• <b>{sim}</b> (Prob: <b>{it['probabilidad_pct']}%</b>) | Base (0%): <code>{formatear_precio(it['base_24h_f'])}</code> ➔ Actual: <code>{formatear_precio(it['precio_f'])}</code> | <b>{it['cambio_f']:+.2f}%</b>{tseg}\n  └ <a href=\"{html.escape(u_ia)}\">📊 Resumen IA</a> | <a href=\"{html.escape(u_tr)}\">🔶 Tradear</a>\n"
                msg += "\n"
            enviar_telegram_blindado(fname, msg.strip())

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
