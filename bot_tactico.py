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
        "secuencia": {},
        "graduadas_pre_explosion": {}
    }
    if os.path.exists(HISTORIAL_FILE):
        try:
            with open(HISTORIAL_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # Compatibilidad con claves anteriores si existían
            raw_sec = data.get("secuencia") or data.get("seguimiento_verde") or {}
            sec_limpia = {}
            for sym, info in raw_sec.items():
                try:
                    f_det = datetime.strptime(info.get("fecha_iso", hoy), '%Y-%m-%d').date()
                    if (ahora_art().date() - f_det).days <= DIAS_SEGUIMIENTO:
                        paso = int(info.get("paso", info.get("estrellas", 1)))
                        if paso >= 1:
                            info["paso"] = min(3, paso)
                            sec_limpia[sym] = info
                except Exception:
                    continue
            base["secuencia"] = sec_limpia

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

def calcular_metricas_tecnicas(session, symbol):
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

def elegir_inicio_verde_ia(candidatos_verdes):
    # Selecciona hasta 2 monedas crudas sanas para iniciar Paso 1 (🟢 Verde)
    aptas = [
        x for x in candidatos_verdes
        if 35 <= x.get("probabilidad_pct", 0) <= 55
        and 38.0 <= x.get("rsi_1h", 50.0) <= 65.0
        and -2.5 <= x.get("cambio_f", 0.0) <= 4.0
    ]
    if not aptas:
        aptas = sorted(candidatos_verdes, key=lambda x: x.get("probabilidad_pct", 0), reverse=True)
    aptas.sort(key=lambda x: (x.get("probabilidad_pct", 0), x.get("vol_surge", 0.0)), reverse=True)
    defecto = {
        x["base"]: f"Paso 1 ⭐: base {x['cambio_f']:+.1f}%, 1h {x['var_1h']:+.2f}%, RSI {x['rsi_1h']}."
        for x in aptas[:2]
    }
    dictamen = "Secuencia activa: Paso 1 (⭐ Verde) inicia ➔ Paso 2 (⭐⭐ Amarillo) evoluciona ➔ Paso 3 (⭐⭐⭐ Rojo) confirma."

    if not GEMINI_API_KEY or not aptas:
        return defecto, dictamen

    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
        lineas = "\n".join([
            f"- {x['base']}: prob={x['probabilidad_pct']}%, 24h={x['cambio_f']:+.2f}%, 1h={x['var_1h']:+.2f}%, RSI={x['rsi_1h']}, Vol=x{x['vol_surge']}"
            for x in aptas[:10]
        ])
        prompt = (
            "Elegí hasta 2 monedas crudas en base para iniciar el Paso 1 (Verde 1⭐) de una secuencia de inversión.\n"
            f"Candidatas:\n{lineas}\n\n"
            'Responde SOLO JSON válido: {"inicio_verde":[{"symbol":"S1","motivo":"..."}],"dictamen":"..."}'
        )
        for mod in ['gemini-2.5-flash', 'gemini-1.5-flash']:
            try:
                res = client.models.generate_content(model=mod, contents=prompt)
                if res and res.text:
                    raw = res.text.strip()
                    if "{" in raw and "}" in raw:
                        raw = raw[raw.find("{"):raw.rfind("}") + 1]
                    data = json.loads(raw)
                    mapa = {x["base"]: x for x in aptas}
                    picks = {}
                    for item in (data.get("inicio_verde") or [])[:2]:
                        s = str(item.get("symbol", "")).strip().upper()
                        m = str(item.get("motivo", "")).strip()
                        if s in mapa:
                            picks[s] = (m or defecto.get(s) or "Inicia secuencia ⭐")[:95]
                    if picks:
                        return picks, str(data.get("dictamen") or dictamen)[:140]
            except Exception:
                continue
    except Exception as e:
        print(f"⚠️ Fallback Gemini: {e}")
    return defecto, dictamen

def construir_secuencia(session, tickers, activos, historial):
    EXCL = {'USDT','USDC','FDUSD','DAI','TUSD','USDP','EUR','BUSD','USD1','AEUR','EURI','USDE','RLUSD','RWUSD','XUSD','BFUSD','U','USDG','USDS','PYUSD','PAXG','XAUT','BTC','ETH','SOL','ADA','XRP','DOGE','TRX','SHIB','AVAX','LINK','BNB','DOT','NEAR','SUI','PEPE','GBP','TRY','BRL','ARS'}
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
            if sym not in menc and (0.000001 <= p < 5.00 and 600_000 <= vol <= 45_000_000 and -2.5 <= chg <= 5.8):
                cand.append(it)
        except Exception:
            continue

    sec = historial.get("secuencia", {})
    grad = historial.get("graduadas_pre_explosion", {})
    hoy_iso, hoy_corta = ahora_art().strftime('%Y-%m-%d'), ahora_art().strftime('%d/%m')
    alertas = []

    # 1) Evalúa monedas ya iniciadas en la secuencia (Paso 1 -> Paso 2 -> Paso 3)
    for sym in list(sec.keys()):
        info = sec[sym]
        mkt = mapa.get(sym)
        if not mkt:
            continue
        tec = calcular_metricas_tecnicas(session, sym)
        if not tec["ok"]:
            continue

        prob = tec["probabilidad_pct"]
        p_act = mkt["precio_f"]
        p_ini = float(info.get("precio_inicio", p_act))
        var_seq = ((p_act - p_ini) / p_ini) * 100 if p_ini > 0 else 0.0
        paso_prev = int(info.get("paso", 1))

        # Si cae fuerte (< -6% desde inicio o prob < 30%), sale de la secuencia
        if var_seq < -6.0 or prob < 30:
            del sec[sym]
            continue

        # Avance a Paso 2 (Amarillo ⭐⭐): prob >= 52 o mejora >= +6 pts desde inicio con RSI <= 70
        cumple_p2 = (prob >= 52 or prob >= int(info.get("prob_inicio", prob)) + 6) and tec["rsi_1h"] <= 70.0
        # Avance a Paso 3 (Rojo ⭐⭐⭐): ya estuvo en Paso 2 y alcanza prob >= 70 con RSI <= 74
        cumple_p3 = paso_prev >= 2 and prob >= 70 and tec["rsi_1h"] <= 74.0

        paso_nuevo = paso_prev
        if cumple_p3:
            paso_nuevo = 3
            if paso_prev < 3 and not info.get("alerta_p3", False):
                info["alerta_p3"] = True
                alertas.append({
                    "base": sym[:-4], "paso": 3, "prob": prob,
                    "fecha_corta": info.get("fecha_corta", hoy_corta),
                    "p_ini": p_ini, "p_act": p_act, "var_seq": var_seq,
                    "mkt": mkt, "tec": tec
                })
            grad[sym] = {
                "symbol": sym, "base": sym[:-4], "estrellas": 3,
                "probabilidad_pct": prob, "precio_ref": p_act,
                "fecha_iso": hoy_iso, "fecha_corta": hoy_corta,
                "origen": "Secuencia Completa Paso 1 ➔ Paso 2 ➔ Paso 3"
            }
        elif cumple_p2:
            paso_nuevo = max(paso_prev, 2)
            if paso_prev < 2 and not info.get("alerta_p2", False):
                info["alerta_p2"] = True
                alertas.append({
                    "base": sym[:-4], "paso": 2, "prob": prob,
                    "fecha_corta": info.get("fecha_corta", hoy_corta),
                    "p_ini": p_ini, "p_act": p_act, "var_seq": var_seq,
                    "mkt": mkt, "tec": tec
                })

        info.update({
            "paso": paso_nuevo,
            "estrellas": paso_nuevo,
            "prob_actual": prob,
            "precio_actual": p_act,
            "var_seq": round(var_seq, 2),
            "tec": tec
        })
        sec[sym] = info

    # 2) Si hay menos de 2 monedas activas en Paso 1/2, selecciona nuevas candidatas crudas para iniciar Paso 1
    activos_iniciales = [s for s, d in sec.items() if int(d.get("paso", 1)) == 1]
    cand_verdes = []
    if len(activos_iniciales) < 2:
        for it in sorted(cand, key=lambda x: x["presion"], reverse=True)[:24]:
            if it["symbol"] in sec:
                continue
            tec = calcular_metricas_tecnicas(session, it["symbol"])
            if tec["ok"] and 35 <= tec["probabilidad_pct"] <= 55:
                it.update(tec)
                cand_verdes.append(it)

    picks_verde, dictamen = elegir_inicio_verde_ia(cand_verdes)
    for it in cand_verdes:
        sym, base = it["symbol"], it["base"]
        if base in picks_verde and len([s for s, d in sec.items() if int(d.get("paso", 1)) == 1]) < 2:
            sec[sym] = {
                "symbol": sym,
                "base": base,
                "fecha_iso": hoy_iso,
                "fecha_corta": hoy_corta,
                "precio_inicio": it["precio_f"],
                "precio_actual": it["precio_f"],
                "prob_inicio": it["probabilidad_pct"],
                "prob_actual": it["probabilidad_pct"],
                "var_seq": 0.0,
                "paso": 1,
                "estrellas": 1,
                "motivo": picks_verde[base],
                "tec": {
                    "var_1h": it["var_1h"],
                    "rsi_1h": it["rsi_1h"],
                    "ema_estado": it["ema_estado"],
                    "vol_surge": it["vol_surge"]
                },
                "alerta_p2": False,
                "alerta_p3": False
            }
        menc[sym] = 1
        if sym not in historial["resumen_dia"]:
            historial["resumen_dia"].append(sym)

    # Arma los 3 pasos de la secuencia real
    paso3_items, paso2_items, paso1_items = [], [], []
    for sym, d in sec.items():
        mkt = mapa.get(sym)
        if not mkt:
            continue
        tec = d.get("tec") or calcular_metricas_tecnicas(session, sym)
        item_fmt = {
            "symbol": sym,
            "base": sym[:-4],
            "paso": int(d.get("paso", 1)),
            "estrellas": int(d.get("paso", 1)),
            "probabilidad_pct": int(d.get("prob_actual", tec.get("probabilidad_pct", 40))),
            "precio_inicio": float(d.get("precio_inicio", mkt["precio_f"])),
            "precio_f": mkt["precio_f"],
            "base_24h_f": mkt["base_24h_f"],
            "cambio_f": mkt["cambio_f"],
            "high_f": mkt["high_f"],
            "low_f": mkt["low_f"],
            "var_seq": float(d.get("var_seq", 0.0)),
            "fecha_corta": d.get("fecha_corta", hoy_corta),
            "motivo_ia": d.get("motivo", ""),
            "var_1h": tec.get("var_1h", 0.0),
            "rsi_1h": tec.get("rsi_1h", 50.0),
            "vol_surge": tec.get("vol_surge", 1.0),
            "color_hex": "#ff1744" if int(d.get("paso", 1)) == 3 else ("#ffd600" if int(d.get("paso", 1)) == 2 else "#00e676")
        }
        if item_fmt["paso"] == 3:
            paso3_items.append(item_fmt)
        elif item_fmt["paso"] == 2:
            paso2_items.append(item_fmt)
        else:
            paso1_items.append(item_fmt)

    historial.update({
        "mencionadas": menc,
        "secuencia": sec,
        "graduadas_pre_explosion": grad
    })
    guardar_historial(historial)
    return {"PASO_3": paso3_items, "PASO_2": paso2_items, "PASO_1": paso1_items}, historial, dictamen, alertas

def generar_grafico_secuencia(items, titulo_graf, subtitulo_graf, filename):
    if not items:
        return None
    sims = [f"{'★'*i['estrellas']}{i['base']}" for i in items]
    probs = [i['probabilidad_pct'] for i in items]
    cols = [i['color_hex'] for i in items]
    ests = [i['estrellas'] for i in items]

    fig, ax = plt.subplots(figsize=(8.5, 4.2), facecolor='#0b132b')
    ax.set_facecolor('#0b132b')
    bars = ax.bar(sims, probs, color=cols, width=0.45, zorder=3)
    ax.grid(True, color='#1e293b', linewidth=0.8, zorder=1)
    ax.set_ylim(0, 122)
    for sp in ['top', 'right', 'left', 'bottom']:
        ax.spines[sp].set_visible(False)
    ax.tick_params(left=False, labelleft=False, bottom=False)
    ax.tick_params(axis='x', colors='white', labelsize=10)

    for bar, it, pr, col, est in zip(bars, items, probs, cols, ests):
        yv, xv = bar.get_height(), bar.get_x() + bar.get_width() / 2.0
        bar.set_edgecolor('#ffd700' if est >= 2 else '#ffffff')
        bar.set_linewidth(2.2)
        ax.text(xv, yv + 3.0, f"{'★'*est}\n{pr}%", ha='center', va='bottom', color='#ffd700' if est >= 2 else '#ffffff', fontweight='bold', fontsize=9)
        ax.plot(xv, max(yv / 2.0, 14), marker='o', markersize=18, markerfacecolor='#0f172a', markeredgecolor='#ffd700' if est >= 2 else '#ffffff', markeredgewidth=2.0, zorder=4)
        ax.text(xv, max(yv / 2.0, 14), it['base'][:5], ha='center', va='center', color='white', fontsize=7, fontweight='bold', zorder=5)

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

def enviar_alerta_secuencia(al):
    sim, mkt, tec, paso = al['base'], al['mkt'], al['tec'], al['paso']
    uid = int(time.time() * 1000) + random.randint(1, 9999)
    u_ia = f"{BASE_URL_NETLIFY}/?coin={sim}&price={mkt['precio_f']}&change={mkt['cambio_f']}&high={mkt['high_f']}&low={mkt['low_f']}&v={sim}_{uid}"
    u_tr = f"https://www.binance.com/es/trade/{sim}_USDT"
    if paso == 2:
        titulo = "🚨 <b>SECUENCIA • AVANCE A PASO 2 (⭐⭐ AMARILLO)</b>"
        desc = f"avanzó desde <b>Paso 1 (⭐ Verde)</b> ({al['fecha_corta']} @ <code>{formatear_precio(al['p_ini'])}</code>) a <b>Paso 2 (⭐⭐)</b> con Prob <b>{al['prob']}%</b>."
    else:
        titulo = "🏆 <b>SECUENCIA • PASO 3 CONFIRMADO (⭐⭐⭐ PRE-EXPLOSIÓN)</b>"
        desc = f"completó Paso 1 ➔ Paso 2 y alcanzó <b>Paso 3 (⭐⭐⭐)</b> con Prob <b>{al['prob']}%</b>."
    msg = (
        f"{titulo}\n📅 <code>{ahora_art().strftime('%Y-%m-%d %H:%M ART')}</code>\n\n"
        f"⚡ <b>{sim}</b> {desc}\n"
        f"• <b>Actual:</b> <code>{formatear_precio(al['p_act'])}</code> (<b>{al['var_seq']:+.2f}%</b> en secuencia)\n"
        f"• <b>Técnico:</b> <code>1h: {tec['var_1h']:+.2f}% | RSI: {tec['rsi_1h']} | Vol: x{tec['vol_surge']}</code>\n"
        f"└ <a href=\"{html.escape(u_ia)}\">📊 Resumen IA</a> | <a href=\"{html.escape(u_tr)}\">🔶 Tradear</a>"
    )
    enviar_texto_telegram(msg)

def enviar_paso_secuencia(num_paso, titulo_paso, items, mensaje_vacio, dictamen=""):
    fecha_str = ahora_art().strftime('%Y-%m-%d %H:%M ART')
    if not items:
        txt = f"🔗 <b>SECUENCIA TÁCTICA • PASO {num_paso}/3</b>\n{titulo_paso}\n📅 <code>{fecha_str}</code>\n"
        if dictamen:
            txt += f"🧠 <i>{html.escape(dictamen)}</i>\n"
        txt += f"\n⏳ <i>{html.escape(mensaje_vacio)}</i>"
        enviar_texto_telegram(txt)
        return

    fname = f"secuencia_paso_{num_paso}.png"
    generar_grafico_secuencia(items, f"SECUENCIA PASO {num_paso}/3", f"Fecha: {fecha_str} | Cadena: Paso 1 ⭐ ➔ Paso 2 ⭐⭐ ➔ Paso 3 ⭐⭐⭐", fname)

    msg = f"🔗 <b>SECUENCIA TÁCTICA • PASO {num_paso}/3</b>\n{titulo_paso}\n📅 <code>{fecha_str}</code>\n"
    if dictamen:
        msg += f"🧠 <i>{html.escape(dictamen)}</i>\n"
    msg += "\n"

    for it in items:
        sim, est = it["base"], it["estrellas"]
        uid = int(time.time() * 1000) + random.randint(1, 9999)
        u_ia = f"{BASE_URL_NETLIFY}/?coin={sim}&price={it['precio_f']}&change={it['cambio_f']}&high={it['high_f']}&low={it['low_f']}&v={sim}_{uid}"
        u_tr = f"https://www.binance.com/es/trade/{sim}_USDT"
        mot = html.escape(it.get("motivo_ia", ""))
        msg += (
            f"{'⭐'*est} <b>{sim} [Paso {num_paso} • Prob: {it['probabilidad_pct']}%]</b> | Inicio ({it['fecha_corta']}): <code>{formatear_precio(it['precio_inicio'])}</code> ➔ Actual: <code>{formatear_precio(it['precio_f'])}</code> (<b>{it['var_seq']:+.2f}%</b>)\n"
            f"   📐 <code>1h: {it['var_1h']:+.2f}% | RSI: {it['rsi_1h']} | Vol: x{it['vol_surge']}</code>\n"
        )
        if mot:
            msg += f"   💡 <i>{mot}</i>\n"
        msg += f"   └ <a href=\"{html.escape(u_ia)}\">📊 Resumen IA</a> | <a href=\"{html.escape(u_tr)}\">🔶 Tradear</a>\n\n"

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
            print(f"⚠️ Error enviando paso {num_paso}: {e}")
        time.sleep(3)

if __name__ == "__main__":
    print(f"🔗 INICIANDO SECUENCIA TÁCTICA ({ahora_art().strftime('%H:%M:%S')} ART)...")
    s = crear_sesion_binance()
    activos, datos = obtener_datos_binance(s)
    if datos and activos:
        hist = cargar_historial()
        pasos, hist, dictamen, alertas = construir_secuencia(s, datos, activos, hist)

        for al in alertas:
            enviar_alerta_secuencia(al)
            time.sleep(1.5)

        enviar_paso_secuencia(3, "🔴 <b>PASO 3: CONFIRMADA PARA INVERSIÓN (⭐⭐⭐)</b>", pasos["PASO_3"], "Ninguna moneda de la secuencia completó Paso 1 ➔ Paso 2 ➔ Paso 3 aún.", dictamen)
        time.sleep(2)
        enviar_paso_secuencia(2, "🟡 <b>PASO 2: EVOLUCIÓN / EN OBSERVACIÓN (⭐⭐)</b>", pasos["PASO_2"], "Ninguna moneda de Paso 1 cumplió aún el avance a Paso 2.")
        time.sleep(2)
        enviar_paso_secuencia(1, "🟢 <b>PASO 1: INICIO / CRUDA POTENCIAL (⭐)</b>", pasos["PASO_1"], "Sin candidatas crudas nuevas en este ciclo.")
    else:
        print("❌ ERROR: Sin datos de Binance.")

# FIN BOT TACTICO
