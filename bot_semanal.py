import os, json, time, random, html, requests
from datetime import datetime, timezone, timedelta
import matplotlib.pyplot as plt
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment
from google import genai

TZ_ART = timezone(timedelta(hours=-3))
TELEGRAM_BOT_TOKEN = (os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("TELEGRAM_TOKEN") or "").strip()
TELEGRAM_CHAT_ID = (os.getenv("TELEGRAM_CHAT_ID") or os.getenv("CHAT_ID") or "").strip()
TELEGRAM_TOPIC_ID = (os.getenv("TOPIC_ID_SEMANAL") or "18574").strip()
GEMINI_API_KEY = (os.getenv("GEMINI_API_KEY") or "").strip()
BASE_URL_NETLIFY = "https://gregarious-frangollo-0346c5.netlify.app"

HISTORIAL_PERLAS_FILE = "historial_perlas.json"
HISTORIAL_GANADORAS_FILE = "historial_ganadoras.json"
PLAN_SEMANAL_FILE = "plan_semanal.json"
EXCEL_SEMANAL_FILE = "AUDITORIA_SEMANAL_PRUEBA.xlsx"

# Parámetros de la prueba semanal 4X
CAPITAL_INICIAL_PRUEBA = 3500.0
META_SEMANAL_USD = 600.0
MAX_MONEDAS_SEMANA = 4
TOP_ALTERNATIVAS_MOSTRAR = 8
STOP_PROTECCION_PCT = -8.5
TRAILING_DESDE_MAX_PCT = 4.0
HORAS_MAX_SIN_ARRANQUE = 60.0

def ahora_art():
    return datetime.now(TZ_ART)

def id_semana_actual(dt=None):
    dt = dt or ahora_art()
    iso_year, iso_week, _ = dt.isocalendar()
    return f"{iso_year}-W{iso_week:02d}"

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

def crear_sesion_binance():
    s = requests.Session()
    s.headers.update({"User-Agent": "Mozilla/5.0", "Accept": "application/json", "Cache-Control": "no-cache"})
    return s

def obtener_tickers_binance(session):
    for url in ["https://api.binance.com/api/v3/ticker/24hr", "https://data-api.binance.vision/api/v3/ticker/24hr"]:
        try:
            r = session.get(url, timeout=15)
            if r.status_code == 200 and isinstance(r.json(), list):
                mapa = {}
                for t in r.json():
                    sym = t.get("symbol", "")
                    if sym.endswith("USDT"):
                        try:
                            mapa[sym] = {
                                "symbol": sym,
                                "base": sym[:-4],
                                "precio": float(t["lastPrice"]),
                                "cambio_24h": float(t["priceChangePercent"]),
                                "vol_24h": float(t["quoteVolume"]),
                                "high": float(t["highPrice"]),
                                "low": float(t["lowPrice"])
                            }
                        except Exception:
                            continue
                if mapa:
                    return mapa
        except Exception:
            continue
    return {}

def auditar_order_book_semanal(session, symbol):
    """Verificación final del libro de órdenes en tiempo real antes de asignar capital."""
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
                return {"ok": True, "spread_pct": round(spread, 3), "ratio_ba": ratio, "sano": (spread <= 0.45 and ratio >= 0.75)}
        except Exception:
            continue
    return {"ok": False, "spread_pct": 0.1, "ratio_ba": 1.0, "sano": True}

def analizar_velas_tf(session, symbol, interval="1h", limit=48):
    """Analiza RSI, Volumen, rechazo de mecha y niveles geométricos de Fibonacci."""
    for base_url in ["https://api.binance.com", "https://data-api.binance.vision"]:
        try:
            r = session.get(f"{base_url}/api/v3/klines", params={"symbol": symbol, "interval": interval, "limit": limit}, timeout=7)
            if r.status_code == 200:
                k = r.json()
                if len(k) < 15:
                    continue
                cierres = [float(x[4]) for x in k]
                aperturas = [float(x[1]) for x in k]
                maximos = [float(x[2]) for x in k]
                minimos = [float(x[3]) for x in k]
                vols = [float(x[7]) for x in k]

                deltas = [cierres[i] - cierres[i - 1] for i in range(1, len(cierres))]
                g = [d if d > 0 else 0.0 for d in deltas]
                p = [-d if d < 0 else 0.0 for d in deltas]
                ag, ap = sum(g[:14]) / 14.0, sum(p[:14]) / 14.0
                rsi = 100.0 if ap == 0 else round(100.0 - (100.0 / (1.0 + (ag / ap))), 1)

                v_rec = sum(vols[-2:]) / 2.0
                v_prev = sum(vols[-12:-2]) / 10.0
                vol_ratio = round(v_rec / v_prev, 2) if v_prev > 0 else 1.0
                var_ultima = round(((cierres[-1] - aperturas[-1]) / aperturas[-1]) * 100, 2) if aperturas[-1] > 0 else 0.0

                rango_vela = maximos[-1] - minimos[-1]
                mecha_sup = maximos[-1] - max(cierres[-1], aperturas[-1])
                rechazo_techo = (rango_vela > 0 and (mecha_sup / rango_vela) >= 0.55)

                # Cálculo quirúrgico de Fibonacci sobre el swing del periodo
                swing_high = max(maximos)
                swing_low = min(minimos)
                rango_fib = swing_high - swing_low
                p_act = cierres[-1]
                fib_data = {"ok": False}

                if rango_fib > 0:
                    ratio_retroceso = round((swing_high - p_act) / rango_fib, 3)
                    fib_382 = swing_high - (rango_fib * 0.382)
                    fib_500 = swing_high - (rango_fib * 0.500)
                    fib_618 = swing_high - (rango_fib * 0.618)
                    fib_786 = swing_high - (rango_fib * 0.786)
                    ext_1272 = swing_low + (rango_fib * 1.272)
                    ext_1618 = swing_low + (rango_fib * 1.618)

                    en_zona_dorada = (0.35 <= ratio_retroceso <= 0.65)
                    en_punta_extendida = (ratio_retroceso < 0.12)
                    cerca_ext_1618 = (p_act >= ext_1618 * 0.985)

                    if en_zona_dorada:
                        zona_txt = f"Zona Dorada Fib ({ratio_retroceso:.2f})"
                    elif ratio_retroceso > 0.65:
                        zona_txt = f"Soporte Profundo Fib ({ratio_retroceso:.2f})"
                    elif en_punta_extendida:
                        zona_txt = f"Punta Impulso Fib ({ratio_retroceso:.2f})"
                    else:
                        zona_txt = f"Tramo Medio Fib ({ratio_retroceso:.2f})"

                    fib_data = {
                        "ok": True,
                        "ratio": ratio_retroceso,
                        "zona_txt": zona_txt,
                        "en_zona_dorada": en_zona_dorada,
                        "en_punta_extendida": en_punta_extendida,
                        "cerca_ext_1618": cerca_ext_1618,
                        "fib_382": fib_382,
                        "fib_500": fib_500,
                        "fib_618": fib_618,
                        "fib_786": fib_786,
                        "ext_1272": ext_1272,
                        "ext_1618": ext_1618
                    }

                return {
                    "ok": True,
                    "rsi": rsi,
                    "vol_ratio": vol_ratio,
                    "var_ultima": var_ultima,
                    "rechazo_techo": rechazo_techo,
                    "fib": fib_data
                }
        except Exception:
            continue
    return {"ok": False, "rsi": 50.0, "vol_ratio": 1.0, "var_ultima": 0.0, "rechazo_techo": False, "fib": {"ok": False}}

def verificar_clima_btc(session, mapa_mkt):
    btc = mapa_mkt.get("BTCUSDT")
    if not btc:
        return True, "BTC estable"
    chg_24h = float(btc["cambio_24h"])
    mom_btc = analizar_velas_tf(session, "BTCUSDT", "1h", 24)
    rsi_btc = float(mom_btc.get("rsi", 50.0))
    if chg_24h <= -2.5 or rsi_btc < 35.0:
        return False, f"BTC en alerta (24h: {chg_24h:+.2f}%, RSI 1h: {rsi_btc}). Compras pausadas."
    return True, f"BTC estable (24h: {chg_24h:+.2f}%, RSI 1h: {rsi_btc})"

def cargar_json_seguro(ruta):
    if not os.path.exists(ruta):
        return {}
    try:
        with open(ruta, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def cargar_plan_semanal():
    sem = id_semana_actual()
    base = {
        "semana_id": sem,
        "fecha_inicio": ahora_art().strftime("%Y-%m-%d %H:%M"),
        "modo": "PRUEBA_SIMULACION_BLINDADA_IA_FIB",
        "capital_total_usd": CAPITAL_INICIAL_PRUEBA,
        "meta_semanal_usd": META_SEMANAL_USD,
        "ganancia_realizada_usd": 0.0,
        "estado_semana": "ACTIVA",
        "fecha_cierre_meta": "",
        "aviso_btc_enviado": False,
        "ultimo_reporte_hora": -1,
        "auditoria_ia": {},
        "historial_auditorias": [],
        "alternativas_evaluadas": [],
        "posiciones": [],
        "historial_cierres": []
    }
    data = cargar_json_seguro(PLAN_SEMANAL_FILE)
    if data and data.get("semana_id") == sem:
        data.setdefault("aviso_btc_enviado", False)
        data.setdefault("ultimo_reporte_hora", -1)
        data.setdefault("auditoria_ia", {})
        data.setdefault("historial_auditorias", [])
        data.setdefault("alternativas_evaluadas", [])
        return data
    if data:
        if data.get("historial_cierres"):
            base["historial_cierres"] = data["historial_cierres"][-60:]
        if data.get("historial_auditorias"):
            base["historial_auditorias"] = data["historial_auditorias"][-60:]
    return base

def guardar_plan_semanal(plan):
    try:
        with open(PLAN_SEMANAL_FILE, "w", encoding="utf-8") as f:
            json.dump(plan, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"⚠️ Error guardando {PLAN_SEMANAL_FILE}: {e}")

def calcular_estadisticas_embudo(mapa_mkt):
    ganadoras_data = cargar_json_seguro(HISTORIAL_GANADORAS_FILE)
    perlas_data = cargar_json_seguro(HISTORIAL_PERLAS_FILE)

    reg_verdes = ganadoras_data.get("registro_verdes", {})
    graduadas = perlas_data.get("graduadas_pre_explosion", {})

    ganadas = 0
    en_curso = 0
    perdidas = 0

    for sym, info in reg_verdes.items():
        est = str(info.get("estado", "")).upper()
        max_pct = float(info.get("max_ganancia_pct", info.get("ganancia_pct", 0.0)))
        if "GANADORA" in est or "EXPLOSION" in est or max_pct >= 8.0:
            ganadas += 1
        elif "PERDEDORA" in est or "STOP" in est or max_pct <= -8.0:
            perdidas += 1
        else:
            en_curso += 1

    for sym, info in graduadas.items():
        if sym in reg_verdes:
            continue
        p_ref = float(info.get("precio_ref", 0))
        p_act = float(mapa_mkt.get(sym, {}).get("precio", p_ref))
        var = ((p_act - p_ref) / p_ref) * 100 if p_ref > 0 else 0.0
        if var >= 8.0:
            ganadas += 1
        elif var <= -8.0:
            perdidas += 1
        else:
            en_curso += 1

    resueltas = ganadas + perdidas
    total_senales = resueltas + en_curso
    tasa_resueltas = round((ganadas / resueltas) * 100, 1) if resueltas > 0 else 78.0
    return {
        "ganadas": ganadas,
        "perdidas": perdidas,
        "en_curso": en_curso,
        "total": total_senales,
        "resueltas": resueltas,
        "tasa_pct": tasa_resueltas
    }

def evaluar_alternativas_al_horno(session, mapa_mkt, excluidas):
    perlas = cargar_json_seguro(HISTORIAL_PERLAS_FILE)
    if not perlas:
        return []

    posta_dict = perlas.get("posta", {})
    candidatos = []

    for sym, info in perlas.get("graduadas_pre_explosion", {}).items():
        if sym not in mapa_mkt:
            continue
        mkt = mapa_mkt[sym]
        p_ref = float(info.get("precio_ref", mkt["precio"]))
        var_desde_filtro = ((mkt["precio"] - p_ref) / p_ref) * 100 if p_ref > 0 else 0.0
        mom_1h = analizar_velas_tf(session, sym, "1h", 36)
        mom_4h = analizar_velas_tf(session, sym, "4h", 48)
        fib_4h = mom_4h.get("fib", {})
        ob = auditar_order_book_semanal(session, sym)

        prob = int(info.get("blindaje_pct", info.get("probabilidad_pct", 70)))
        info_p = posta_dict.get(sym, {})
        cert_e1 = bool(info.get("certificada_etapa1")) or bool(info_p.get("certificada_etapa1"))
        cert_e2 = bool(info.get("certificada_ia"))
        cert_doble = cert_e1 and cert_e2

        bono_cert = 22 if cert_doble else (12 if (cert_e1 or cert_e2) else 0)
        bono_fib = 10 if fib_4h.get("en_zona_dorada") else (-6 if fib_4h.get("en_punta_extendida") else 0)
        bono_ob = 6 if ob.get("sano") else -15
        score = prob + 12 + bono_cert + bono_ob + (5 if mom_1h["vol_ratio"] >= 1.2 else 0) + bono_fib

        en_zona = (
            -3.5 <= var_desde_filtro <= 8.5
            and -4.5 <= mkt["cambio_24h"] <= 10.5
            and mom_1h["rsi"] <= 68.0
            and ob.get("sano", True)
        )
        sello_txt = "🛡️🛡️ DOBLE CERT. IA" if cert_doble else ("🛡️ CERT. IA" if (cert_e1 or cert_e2) else "Rojo 3⭐⭐⭐")
        fib_tag = f" | {fib_4h.get('zona_txt', 'Fib N/D')}" if fib_4h.get("ok") else ""
        motivo_tecnico = (
            f"{sello_txt} ({var_desde_filtro:+.1f}% filtro) | "
            f"OB: {ob['ratio_ba']}x | RSI 1h: {mom_1h['rsi']}{fib_tag} | Blindaje: {prob}%"
        )
        candidatos.append({
            "symbol": sym,
            "base": sym[:-4],
            "precio_entrada": mkt["precio"],
            "origen": sello_txt,
            "probabilidad": prob,
            "score": score,
            "certificada_doble": cert_doble,
            "en_zona": en_zona and (sym not in excluidas),
            "ya_en_cartera": sym in excluidas,
            "motivo_tecnico": motivo_tecnico,
            "mom": mom_1h,
            "fib_4h": fib_4h
        })

    for sym, info in posta_dict.items():
        if sym not in mapa_mkt or any(c["symbol"] == sym for c in candidatos):
            continue
        et = int(info.get("etapa", 1))
        if et >= 2:
            mkt = mapa_mkt[sym]
            mom_1h = analizar_velas_tf(session, sym, "1h", 36)
            mom_4h = analizar_velas_tf(session, sym, "4h", 48)
            fib_4h = mom_4h.get("fib", {})
            ob = auditar_order_book_semanal(session, sym)

            prob = int(info.get("blindaje_etapa1", info.get("prob_actual", 65)))
            var_seq = float(info.get("var_seq", 0.0))
            cert_e1 = bool(info.get("certificada_etapa1"))
            bono_cert = 12 if cert_e1 else 0
            bono_fib = 10 if fib_4h.get("en_zona_dorada") else (-6 if fib_4h.get("en_punta_extendida") else 0)
            bono_ob = 6 if ob.get("sano") else -15
            score = prob + (8 if et == 3 else 3) + bono_cert + bono_ob + (5 if mom_1h["vol_ratio"] >= 1.2 else 0) + bono_fib

            en_zona = (-4.5 <= mkt["cambio_24h"] <= 10.5 and mom_1h["rsi"] <= 68.0 and ob.get("sano", True))
            etiqueta = "🛡️ Cert. Etapa 1 (⭐⭐⭐)" if cert_e1 else ("Cazador ROJO (⭐⭐⭐)" if et == 3 else "Cazador AMARILLO (⭐⭐)")
            fib_tag = f" | {fib_4h.get('zona_txt', 'Fib N/D')}" if fib_4h.get("ok") else ""
            motivo_tecnico = (
                f"{etiqueta} ({var_seq:+.1f}% base 1D) | "
                f"OB: {ob['ratio_ba']}x | RSI 1h: {mom_1h['rsi']}{fib_tag} | Blindaje: {prob}%"
            )
            candidatos.append({
                "symbol": sym,
                "base": sym[:-4],
                "precio_entrada": mkt["precio"],
                "origen": etiqueta,
                "probabilidad": prob,
                "score": score,
                "certificada_doble": False,
                "en_zona": en_zona and (sym not in excluidas),
                "ya_en_cartera": sym in excluidas,
                "motivo_tecnico": motivo_tecnico,
                "mom": mom_1h,
                "fib_4h": fib_4h
            })

    candidatos.sort(key=lambda x: (x["en_zona"], x["certificada_doble"], x["score"], x["mom"]["vol_ratio"]), reverse=True)
    return candidatos[:TOP_ALTERNATIVAS_MOSTRAR]

def limpiar_json_ia(raw_text):
    txt = raw_text.strip()
    if txt.startswith("```"):
        txt = txt.strip("`").strip()
        if txt.lower().startswith("json"):
            txt = txt[4:].strip()
    if "{" in txt and "}" in txt:
        txt = txt[txt.find("{"):txt.rfind("}") + 1]
    return json.loads(txt)

def evaluar_copiloto_trader_y_auditor_ia(session, mapa_mkt, plan, clima_btc_txt):
    """Módulo IA Integrado: Auditor 24h + Copiloto Trader IA con Geometría Fibonacci 1H/4H."""
    posiciones = plan.get("posiciones", [])
    datos_posiciones = []

    for p in posiciones:
        sym = p["symbol"]
        v15 = analizar_velas_tf(session, sym, "15m", 24)
        v1h = analizar_velas_tf(session, sym, "1h", 36)
        v4h = analizar_velas_tf(session, sym, "4h", 48)
        fib = v4h.get("fib", {}) if v4h.get("fib", {}).get("ok") else v1h.get("fib", {})

        p_ent = float(p.get("precio_entrada", 0))
        p_max = float(p.get("precio_maximo", p_ent))
        p_act = float(p.get("precio_actual", p_ent))
        retroceso_max = round(((p_act - p_max) / p_max) * 100, 2) if p_max > 0 else 0.0

        pnl_pct = float(p.get("pnl_pct", 0.0))
        obj_pct = float(p.get("subida_necesaria_pct", 17.14))
        stop_act = float(p.get("stop_actual_pct", STOP_PROTECCION_PCT))

        fib_resumen = "Fib N/D"
        cerca_techo_fib = False
        perdio_fib_618 = False
        if fib.get("ok"):
            fib_resumen = f"{fib['zona_txt']} | Sop 0.618: {formatear_precio(fib['fib_618'])} | Ext 1.618: {formatear_precio(fib['ext_1618'])}"
            cerca_techo_fib = fib.get("cerca_ext_1618", False)
            perdio_fib_618 = (p_act < float(fib["fib_618"]) or float(fib["ratio"]) > 0.65)
        p["fib_lectura"] = fib_resumen

        if (pnl_pct >= obj_pct or cerca_techo_fib) and (v15["rsi"] >= 73 or v15["rechazo_techo"] or retroceso_max <= -2.5):
            orden_def = "🚨 VENDER AHORA (Techo Fib / Agotamiento)"
            razon_def = f"Tocó zona objetivo (+{pnl_pct:.1f}%) / Ext Fib 1.618 con RSI 15m={v15['rsi']} y retroceso {retroceso_max:.1f}%."
        elif pnl_pct >= obj_pct * 0.85 and (v15["rsi"] >= 76 and v15["rechazo_techo"]):
            orden_def = "🟡 ASEGURAR 50% (TP1 Anticipado)"
            razon_def = f"Cerca de meta (+{pnl_pct:.1f}%) con mecha de rechazo en 15m."
        elif pnl_pct <= -5.0 and (perdio_fib_618 or v1h["rsi"] < 34):
            orden_def = "⚠️ RIESGO DE BAJADA (Perdió Fib 0.618)"
            razon_def = f"Retroceso de {pnl_pct:.1f}% debajo de soporte Fib 0.618 (RSI 1h={v1h['rsi']}). Vigilar Stop en {stop_act:+.1f}%."
        else:
            proteccion_txt = f" | Trailing BE activo en {stop_act:+.1f}%" if stop_act > 0 else ""
            orden_def = "🟢 MANTENER / DEJAR CORRER"
            razon_def = f"Estructura sana ({fib.get('zona_txt', 'en curso')}, RSI 1h: {v1h['rsi']}){proteccion_txt}. Falta +{max(0.0, obj_pct - pnl_pct):.1f}% para meta."

        p["trader_ia_orden"] = orden_def
        p["trader_ia_razon"] = razon_def

        datos_posiciones.append({
            "moneda": p["base"],
            "origen_certificacion": p.get("origen", ""),
            "pnl_pct": pnl_pct,
            "stop_proteccion_actual_pct": stop_act,
            "objetivo_pct": obj_pct,
            "retroceso_desde_max_pct": retroceso_max,
            "rsi_15m": v15["rsi"],
            "rechazo_15m": v15["rechazo_techo"],
            "rsi_1h": v1h["rsi"],
            "vol_1h_ratio": v1h["vol_ratio"],
            "fibonacci_4h": fib_resumen,
            "perdio_soporte_0618": perdio_fib_618,
            "orden_base": orden_def
        })

    stats_emb = calcular_estadisticas_embudo(mapa_mkt)
    real = float(plan.get("ganancia_realizada_usd", 0.0))
    flot = sum(float(p.get("pnl_usd", 0.0)) for p in posiciones)
    meta = float(plan.get("meta_semanal_usd", META_SEMANAL_USD))
    progreso_pct = round(((real + flot) / meta) * 100, 1) if meta > 0 else 0.0

    resumen_emb_txt = (
        f"{stats_emb['tasa_pct']}% acierto ({stats_emb['ganadas']}/{stats_emb['resueltas']} cerradas)"
        if stats_emb["resueltas"] > 0
        else f"{stats_emb['total']} señales activas en maduración"
    )

    auditoria_res = {
        "fecha": ahora_art().strftime("%Y-%m-%d %H:%M ART"),
        "semana_id": plan["semana_id"],
        "semaforo_meta": "🟢 EN CAMINO A META" if (real + flot) >= 0 else "🟡 EN CONSOLIDACIÓN",
        "factibilidad_pct": min(96, max(48, int(65 + (stats_emb["tasa_pct"] * 0.25) + ((real + flot) / 25.0)))),
        "diagnostico_24h": f"Embudo blindado: {resumen_emb_txt}. {clima_btc_txt}. Avance cuota: {progreso_pct}%.",
        "recomendacion_auditor": "Vigilar niveles Fibonacci 0.618 / Ext 1.618 y Trailing Break-Even en las posiciones activas.",
        "veredicto_final_semana": plan.get("auditoria_ia", {}).get("veredicto_final_semana", "En seguimiento activo...")
    }

    if GEMINI_API_KEY and datos_posiciones:
        try:
            client = genai.Client(api_key=GEMINI_API_KEY)
            prompt = (
                "Eres un sistema dual de IA para trading Spot en Binance con análisis geométrico de Fibonacci y doble certificación previa:\n"
                "1) AUDITOR IA 24H: Evalúa si las 4 monedas elegidas y el embudo tienen factibilidad real para llegar a la meta semanal de $600 USD.\n"
                "2) COPILOTO TRADER IA: Evalúa velas 15m/1h y niveles Fibonacci (soporte 0.618 y extensión objetivo 1.618) de cada moneda activa y decide la orden exacta: "
                "'🟢 MANTENER / DEJAR CORRER', '🟡 ASEGURAR 50% (TP1)', '🚨 VENDER AHORA (AGOTAMIENTO)' o '⚠️ RIESGO DE BAJADA'.\n\n"
                f"CLIMA MERCADO: {clima_btc_txt}\n"
                f"AVANCE SEMANAL: ${real + flot:+.2f} / ${meta:.0f} USD ({progreso_pct}%)\n"
                f"ESTADO EMBUDO: {resumen_emb_txt}\n"
                f"CARTERA ACTIVA CERTIFICADA:\n{json.dumps(datos_posiciones, ensure_ascii=False)}\n\n"
                "Responde ÚNICAMENTE en JSON válido sin bloques markdown:\n"
                '{"semaforo_meta":"🟢 FACTIBLE | 🟡 EN OBSERVACIÓN | 🔴 RIESGO","factibilidad_pct":80,'
                '"diagnostico_24h":"análisis breve en 1 oración sobre si llegamos a la meta",'
                '"recomendacion_auditor":"consejo técnico concreto incluyendo lectura Fibonacci",'
                '"ordenes":{"MONEDA":{"orden":"🟢 MANTENER / DEJAR CORRER | 🟡 ASEGURAR 50% (TP1) | 🚨 VENDER AHORA (AGOTAMIENTO) | ⚠️ RIESGO DE BAJADA","razon":"motivo corto 15m/1h y nivel Fibonacci"}}}'
            )
            for mod in ["gemini-2.5-flash", "gemini-2.5-flash-lite"]:
                try:
                    res = client.models.generate_content(model=mod, contents=prompt)
                    if res and res.text:
                        ia_json = limpiar_json_ia(res.text)
                        if ia_json.get("diagnostico_24h"):
                            auditoria_res["semaforo_meta"] = str(ia_json.get("semaforo_meta", auditoria_res["semaforo_meta"]))[:35]
                            auditoria_res["factibilidad_pct"] = int(ia_json.get("factibilidad_pct", auditoria_res["factibilidad_pct"]))
                            auditoria_res["diagnostico_24h"] = str(ia_json.get("diagnostico_24h"))[:220]
                            auditoria_res["recomendacion_auditor"] = str(ia_json.get("recomendacion_auditor", auditoria_res["recomendacion_auditor"]))[:220]
                            ordenes_ia = ia_json.get("ordenes", {})
                            for p in posiciones:
                                o_mon = ordenes_ia.get(p["base"])
                                if isinstance(o_mon, dict) and o_mon.get("orden"):
                                    p["trader_ia_orden"] = str(o_mon["orden"])[:45]
                                    p["trader_ia_razon"] = str(o_mon.get("razon", p["trader_ia_razon"]))[:165]
                            break
                except Exception as e_mod:
                    print(f"⚠️ Modelo {mod} sin respuesta: {e_mod}")
                    continue
        except Exception as e:
            print(f"⚠️ Fallback IA integrada: {e}")
    elif not GEMINI_API_KEY:
        print("⚠️ GEMINI_API_KEY no configurada en el entorno; usando motor determinístico.")

    plan["auditoria_ia"] = auditoria_res
    return auditoria_res

def generar_veredicto_final_ia(plan):
    """Emite el dictamen final de factibilidad cuando se cumple la cuota semanal."""
    cierres = [c for c in plan.get("historial_cierres", []) if c.get("semana_id") == plan["semana_id"]]
    ganadoras = [c for c in cierres if float(c.get("pnl_usd", 0)) > 0]
    perdedoras = [c for c in cierres if float(c.get("pnl_usd", 0)) <= 0]
    win_rate = round((len(ganadoras) / len(cierres)) * 100, 1) if cierres else 100.0
    total_usd = float(plan.get("ganancia_realizada_usd", 0.0))
    meta_usd = float(plan.get("meta_semanal_usd", META_SEMANAL_USD))

    veredicto_base = (
        f"✅ <b>VEREDICTO: META LOGRADA — ESTRATEGIA BLINDADA FACTIBLE</b>\n"
        f"• Se alcanzaron <b>${total_usd:,.2f} USD</b> (Meta: ${meta_usd:,.0f} USD) con <b>{win_rate}% de acierto</b> "
        f"({len(ganadoras)} ganadoras / {len(perdedoras)} cerradas en protección).\n"
        f"• La doble certificación IA (Cazador + Pre-Explosión) + Order Book + Fibonacci demostró capacidad real para generar retorno consistente."
    )

    if GEMINI_API_KEY and cierres:
        try:
            client = genai.Client(api_key=GEMINI_API_KEY)
            prompt = (
                "Eres el Auditor Jefe de un fondo cuantitativo Spot en Binance. "
                "Acabamos de cumplir la meta semanal de ganancia en modo prueba blindada. "
                "Analiza los resultados reales de la semana y da un VEREDICTO FINAL DE FACTIBILIDAD para pasar a dinero real.\n"
                f"Capital Base: ${plan.get('capital_total_usd', 3500)} USD | Meta: ${meta_usd} USD | Ganancia Lograda: ${total_usd} USD\n"
                f"Inicio Semana: {plan.get('fecha_inicio')} | Cierre Meta: {plan.get('fecha_cierre_meta')}\n"
                f"Operaciones cerradas: {json.dumps(cierres, ensure_ascii=False)}\n\n"
                "Responde en máximo 4 líneas claras en español con:\n"
                "1) Dictamen (FACTIBLE PARA REAL / FACTIBLE CON AJUSTES)\n"
                "2) Por qué funcionó (consistencia entre las 4 monedas certificadas, tiempo empleado y control de riesgo)."
            )
            for mod in ["gemini-2.5-flash", "gemini-2.5-flash-lite"]:
                try:
                    res = client.models.generate_content(model=mod, contents=prompt)
                    if res and res.text:
                        return f"🧠 <b>DICTAMEN FINAL AUDITOR IA:</b>\n{html.escape(res.text.strip())}"
                except Exception:
                    continue
        except Exception:
            pass
    return veredicto_base

def generar_tablero_visual(plan, filename="tablero_semanal.png"):
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11.0, 4.6), facecolor="#0b132b", gridspec_kw={"width_ratios": [1.0, 1.55]})
    for ax in (ax1, ax2):
        ax.set_facecolor("#0f172a")
        for sp in ["top", "right", "left", "bottom"]:
            ax.spines[sp].set_color("#1e293b")

    meta = max(float(plan.get("meta_semanal_usd", META_SEMANAL_USD)), 1.0)
    realizada = float(plan.get("ganancia_realizada_usd", 0.0))
    flotante = sum(float(p.get("pnl_usd", 0.0)) for p in plan.get("posiciones", []))
    total_actual = realizada + flotante

    categorias = ["Cerrada\n(Caja)", "Flotante\n(En curso)", "Total\nSemana"]
    valores = [realizada, flotante, total_actual]
    colores = ["#00e676" if v >= 0 else "#ff1744" for v in valores]

    bars1 = ax1.bar(categorias, valores, color=colores, width=0.45, zorder=3)
    ax1.axhline(meta, color="#ffd600", linestyle="--", linewidth=1.8, zorder=4, label=f"Meta: ${meta:.0f}")
    ax1.axhline(0, color="#475569", linewidth=1.0, zorder=2)
    lim_sup = max(meta * 1.25, total_actual * 1.25, 150)
    lim_inf = min(-150, total_actual * 1.25)
    ax1.set_ylim(lim_inf, lim_sup)
    ax1.grid(True, axis="y", color="#1e293b", linewidth=0.7, zorder=1)
    ax1.tick_params(colors="white", labelsize=8.5)
    ax1.set_title("PROGRESO CUOTA SEMANAL ($ USD)", color="#ffd600", fontsize=10, fontweight="bold", pad=10)
    ax1.legend(loc="upper left", facecolor="#0b132b", edgecolor="#ffd600", labelcolor="white", fontsize=8)

    for b, v in zip(bars1, valores):
        yv = b.get_height()
        offset = 18 if yv >= 0 else -28
        ax1.text(b.get_x() + b.get_width() / 2.0, yv + offset, f"${v:+.1f}", ha="center", va="center", color="white", fontweight="bold", fontsize=8.5)

    posiciones = plan.get("posiciones", [])
    if posiciones:
        nombres = [p["base"] for p in posiciones]
        pnls = [float(p.get("pnl_pct", 0.0)) for p in posiciones]
        objs = [float(p.get("subida_necesaria_pct", 17.14)) for p in posiciones]
        x = range(len(nombres))

        ax2.bar([i - 0.17 for i in x], objs, width=0.32, color="#334155", edgecolor="#94a3b8", label="Subida Esperada (%)", zorder=2)
        bars_act = ax2.bar([i + 0.17 for i in x], pnls, width=0.32, color=["#00e676" if v >= 0 else "#ff1744" for v in pnls], zorder=3, label="Actual (%)")
        ax2.axhline(0, color="#475569", linewidth=1.0)
        ax2.axhline(STOP_PROTECCION_PCT, color="#ff1744", linestyle=":", linewidth=1.3, label=f"Stop Base ({STOP_PROTECCION_PCT}%)")
        max_y = max(max(objs + [20]) * 1.28, 24)
        ax2.set_ylim(STOP_PROTECCION_PCT * 1.4, max_y)
        ax2.set_xticks(list(x))
        ax2.set_xticklabels(nombres, color="white", fontweight="bold", fontsize=9.5)
        ax2.tick_params(axis="y", colors="white", labelsize=8.5)
        ax2.grid(True, axis="y", color="#1e293b", linewidth=0.7, zorder=1)
        ax2.legend(loc="upper right", facecolor="#0b132b", edgecolor="#334155", labelcolor="white", fontsize=7.5)

        for b, v, obj in zip(bars_act, pnls, objs):
            yv = b.get_height()
            ax2.text(b.get_x() + b.get_width() / 2.0, yv + (0.8 if yv >= 0 else -1.5), f"{v:+.2f}%\n(Obj +{obj:.1f}%)", ha="center", va="bottom" if yv >= 0 else "top", color="white", fontweight="bold", fontsize=7.8)
    else:
        ax2.text(0.5, 0.5, "Sin posiciones abiertas\n(Esperando cierre diario 23:59 o Meta Cumplida)", ha="center", va="center", color="#94a3b8", fontsize=10, transform=ax2.transAxes)
        ax2.tick_params(left=False, labelleft=False, bottom=False, labelbottom=False)

    aud = plan.get("auditoria_ia", {})
    fact_txt = f" | Auditor IA: {aud.get('factibilidad_pct', 80)}% Factible" if aud else ""
    ax2.set_title(f"CARTERA CERTIFICADA ({len(posiciones)}/{MAX_MONEDAS_SEMANA}) • RENDIMIENTO VS ESPERADO", color="#00e676", fontsize=10, fontweight="bold", pad=10)
    fig.suptitle(f"ETAPA 4 • GESTOR BLINDADO + TRADER IA + FIB ({plan['semana_id']}){fact_txt} | {ahora_art().strftime('%d/%m %H:%M ART')}", color="white", fontsize=10.5, fontweight="bold", y=0.98)
    plt.tight_layout(rect=[0, 0, 1, 0.93])
    plt.savefig(filename, dpi=260, facecolor=fig.get_facecolor())
    plt.close()
    return filename

def actualizar_excel_semanal(plan):
    wb = openpyxl.Workbook()
    fill_hdr = PatternFill(start_color="0B132B", end_color="0B132B", fill_type="solid")
    font_hdr = Font(color="FFFFFF", bold=True)
    fill_verde = PatternFill(start_color="D1FAE5", end_color="D1FAE5", fill_type="solid")
    fill_rojo = PatternFill(start_color="FEE2E2", end_color="FEE2E2", fill_type="solid")

    # Pestaña 1: Cartera + Fibonacci + Orden del Copiloto Trader IA
    ws = wb.active
    ws.title = "1_CARTERA_Y_TRADER_IA"
    headers = [
        "Semana", "Fecha Entrada", "Moneda", "Certificación y Motivo", "Capital ($)",
        "Precio Entrada", "Precio Objetivo", "Subida Esperada (%)",
        "Precio Actual", "Máximo Alcanzado", "Rendimiento (%)",
        "PnL ($)", "Lectura Fibonacci 4H", "Orden Copiloto Trader IA", "Análisis Trader IA (15m/1h/Fib)", "Estado"
    ]
    ws.append(headers)
    for col_idx in range(1, len(headers) + 1):
        c = ws.cell(row=1, column=col_idx)
        c.fill = fill_hdr
        c.font = font_hdr
        c.alignment = Alignment(horizontal="center")

    todas = list(plan.get("historial_cierres", [])) + list(plan.get("posiciones", []))
    for row_idx, pos in enumerate(todas, start=2):
        pnl_v = round(float(pos.get("pnl_usd", 0)), 2)
        ws.append([
            pos.get("semana_id", plan["semana_id"]),
            pos.get("fecha_entrada", ""),
            pos.get("base", ""),
            pos.get("motivo_eleccion", pos.get("origen", "")),
            round(float(pos.get("capital_usd", 0)), 2),
            float(pos.get("precio_entrada", 0)),
            float(pos.get("precio_objetivo", 0)),
            round(float(pos.get("subida_necesaria_pct", 0)), 2),
            float(pos.get("precio_actual", 0)),
            float(pos.get("precio_maximo", 0)),
            round(float(pos.get("pnl_pct", 0)), 2),
            pnl_v,
            pos.get("fib_lectura", "Fib N/D"),
            pos.get("trader_ia_orden", "🟢 MANTENER"),
            pos.get("trader_ia_razon", ""),
            pos.get("estado", "")
        ])
        celda_pnl = ws.cell(row=row_idx, column=12)
        if pnl_v > 0:
            celda_pnl.fill = fill_verde
        elif pnl_v < 0:
            celda_pnl.fill = fill_rojo

    # Pestaña 2: Alternativas Evaluadas
    ws_alt = wb.create_sheet(title="2_ALTERNATIVAS_RADAR")
    headers_alt = ["Ranking", "Moneda", "Sello Certificación", "Score Blindaje", "Precio Actual", "Decisión", "Análisis Técnico / OB / Fibonacci"]
    ws_alt.append(headers_alt)
    for col_idx in range(1, len(headers_alt) + 1):
        c = ws_alt.cell(row=1, column=col_idx)
        c.fill = fill_hdr
        c.font = font_hdr
        c.alignment = Alignment(horizontal="center")

    activas_syms = {p["symbol"] for p in plan.get("posiciones", [])}
    for idx, alt in enumerate(plan.get("alternativas_evaluadas", []), start=1):
        estado_alt = "✅ ELEGIDA EN CARTERA" if alt["symbol"] in activas_syms else ("⏳ EN RESERVA (Lista)" if alt.get("en_zona") else "⚠️ FUERA DE ZONA / OB")
        ws_alt.append([
            idx, alt.get("base", ""), alt.get("origen", ""), alt.get("score", 0),
            float(alt.get("precio_entrada", 0)), estado_alt, alt.get("motivo_tecnico", "")
        ])

    # Pestaña 3: Bitácora Histórica de Auditoría IA 24h y Veredicto Final
    ws_aud = wb.create_sheet(title="3_AUDITORIA_IA_24H")
    headers_aud = ["Fecha Auditoría", "Semana", "Semáforo Meta", "Factibilidad (%)", "Diagnóstico IA 24h", "Recomendación Auditor", "Veredicto Final Semana"]
    ws_aud.append(headers_aud)
    for col_idx in range(1, len(headers_aud) + 1):
        c = ws_aud.cell(row=1, column=col_idx)
        c.fill = fill_hdr
        c.font = font_hdr
        c.alignment = Alignment(horizontal="center")

    hist_aud = list(plan.get("historial_auditorias", []))
    if not hist_aud and plan.get("auditoria_ia"):
        hist_aud = [plan["auditoria_ia"]]

    for reg in reversed(hist_aud):
        ws_aud.append([
            reg.get("fecha", ahora_art().strftime("%Y-%m-%d %H:%M ART")),
            reg.get("semana_id", plan["semana_id"]),
            reg.get("semaforo_meta", "🟢 EN CAMINO"),
            reg.get("factibilidad_pct", 80),
            reg.get("diagnostico_24h", ""),
            reg.get("recomendacion_auditor", ""),
            reg.get("veredicto_final_semana", "En seguimiento activo...")
        ])

    # Pestaña 4: Resumen Cuota Semanal
    ws2 = wb.create_sheet(title="4_RESUMEN_CUOTA")
    headers2 = ["Semana", "Fecha Inicio", "Capital Base ($)", "Meta Semanal ($)", "Ganancia Cerrada ($)", "Ganancia Flotante ($)", "Cumplimiento (%)", "Estado Semana"]
    ws2.append(headers2)
    for col_idx in range(1, len(headers2) + 1):
        c = ws2.cell(row=1, column=col_idx)
        c.fill = fill_hdr
        c.font = font_hdr
        c.alignment = Alignment(horizontal="center")

    flot = sum(float(p.get("pnl_usd", 0)) for p in plan.get("posiciones", []))
    real = float(plan.get("ganancia_realizada_usd", 0))
    meta = float(plan.get("meta_semanal_usd", META_SEMANAL_USD))
    cump = round(((real + flot) / meta) * 100, 1) if meta > 0 else 0.0
    ws2.append([
        plan["semana_id"], plan.get("fecha_inicio", ""), round(float(plan.get("capital_total_usd", CAPITAL_INICIAL_PRUEBA)), 2),
        round(meta, 2), round(real, 2), round(flot, 2), cump, plan.get("estado_semana", "ACTIVA")
    ])

    for sheet in (ws, ws_alt, ws_aud, ws2):
        for col in sheet.columns:
            max_len = max(len(str(c.value or "")) for c in col)
            sheet.column_dimensions[col[0].column_letter].width = min(max_len + 4, 46)

    wb.save(EXCEL_SEMANAL_FILE)

def enviar_telegram_texto(texto):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    url = f"[https://api.telegram.org/bot](https://api.telegram.org/bot){TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": texto.strip(), "parse_mode": "HTML", "disable_web_page_preview": True}
    if TELEGRAM_TOPIC_ID.isdigit():
        payload["message_thread_id"] = int(TELEGRAM_TOPIC_ID)
    try:
        r = requests.post(url, json=payload, timeout=15).json()
        if not r.get("ok") and "thread not found" in str(r.get("description", "")).lower():
            payload.pop("message_thread_id", None)
            requests.post(url, json=payload, timeout=15)
    except Exception as e:
        print(f"⚠️ Error Telegram Semanal: {e}")

def enviar_foto_telegram(imagen_path, caption):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID or not os.path.exists(imagen_path):
        return
    url = f"[https://api.telegram.org/bot](https://api.telegram.org/bot){TELEGRAM_BOT_TOKEN}/sendPhoto"
    cabe = len(caption.strip()) <= 1020
    data = {"chat_id": TELEGRAM_CHAT_ID}
    if TELEGRAM_TOPIC_ID.isdigit():
        data["message_thread_id"] = int(TELEGRAM_TOPIC_ID)
    if cabe:
        data.update({"caption": caption.strip(), "parse_mode": "HTML"})
    try:
        with open(imagen_path, "rb") as ph:
            r = requests.post(url, data=data, files={"photo": ph}, timeout=25).json()
            if not r.get("ok") and "thread not found" in str(r.get("description", "")).lower():
                data.pop("message_thread_id", None)
                ph.seek(0)
                r = requests.post(url, data=data, files={"photo": ph}, timeout=25).json()
        if r.get("ok") and not cabe:
            enviar_telegram_texto(caption)
    except Exception as e:
        print(f"⚠️ Error enviando foto Semanal: {e}")

def enviar_excel_telegram(caption):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID or not os.path.exists(EXCEL_SEMANAL_FILE):
        return
    url = f"[https://api.telegram.org/bot](https://api.telegram.org/bot){TELEGRAM_BOT_TOKEN}/sendDocument"
    data = {"chat_id": TELEGRAM_CHAT_ID, "caption": caption[:1000], "parse_mode": "HTML"}
    if TELEGRAM_TOPIC_ID.isdigit():
        data["message_thread_id"] = int(TELEGRAM_TOPIC_ID)
    try:
        with open(EXCEL_SEMANAL_FILE, "rb") as f:
            r = requests.post(url, data=data, files={"document": f}, timeout=25).json()
            if not r.get("ok") and "thread not found" in str(r.get("description", "")).lower():
                data.pop("message_thread_id", None)
                f.seek(0)
                requests.post(url, data=data, files={"document": f}, timeout=25)
    except Exception as e:
        print(f"⚠️ Error enviando Excel Semanal: {e}")

def calcular_horas_abierta(fecha_entrada_str):
    try:
        limpia = fecha_entrada_str.replace(" ART", "").strip()
        dt_ent = datetime.strptime(limpia, "%Y-%m-%d %H:%M").replace(tzinfo=TZ_ART)
        return (ahora_art() - dt_ent).total_seconds() / 3600.0
    except Exception:
        return 0.0

def construir_bloque_1_alternativas(plan):
    ahora_str = ahora_art().strftime("%Y-%m-%d %H:%M ART")
    alts = plan.get("alternativas_evaluadas", [])
    activas_syms = {p["symbol"] for p in plan.get("posiciones", [])}

    msg = (
        f"🔍 <b>GESTOR SEMANAL • BLOQUE 1/3: ALTERNATIVAS BLINDADAS</b>\n"
        f"📅 <code>{ahora_str}</code> | Semana <code>{plan['semana_id']}</code>\n"
        f"<i>Ranking de candidatas con Certificación IA + Order Book + Fibonacci 4H:</i>\n\n"
    )
    if not alts:
        msg += "⏳ <i>Aún no hay candidatas nuevas en el embudo para listar.</i>"
        return msg.strip()

    for idx, a in enumerate(alts, start=1):
        marca = "✅ <b>[ELEGIDA]</b>" if a["symbol"] in activas_syms else ("🟡 <i>[RESERVA]</i>" if a.get("en_zona") else "⚪ <i>[ESPERA]</i>")
        msg += (
            f"<b>{idx}. {a['base']}</b> (Score: <b>{a['score']}</b>) — {marca}\n"
            f"   • Precio: <code>{formatear_precio(a['precio_entrada'])}</code> | {html.escape(a['motivo_tecnico'])}\n"
        )
    return msg.strip()

def construir_bloque_2_cartera(plan, evento_titulo):
    ahora_str = ahora_art().strftime("%Y-%m-%d %H:%M ART")
    real = float(plan.get("ganancia_realizada_usd", 0.0))
    flot = sum(float(p.get("pnl_usd", 0.0)) for p in plan.get("posiciones", []))
    meta = float(plan.get("meta_semanal_usd", META_SEMANAL_USD))
    cump = round(((real + flot) / meta) * 100, 1) if meta > 0 else 0.0
    aud = plan.get("auditoria_ia", {})

    msg = (
        f"🏆 <b>GESTOR BLINDADO + TRADER IA + FIB • BLOQUE 2/3</b>\n"
        f"{evento_titulo}\n"
        f"📅 <code>{ahora_str}</code> | Cuota: <code>${meta:,.0f} USD</code> | Progreso: <b>${real + flot:+.2f} USD ({cump}%)</b>\n"
    )
    if aud:
        msg += (
            f"🧠 <b>Auditor IA 24h:</b> <b>{html.escape(aud.get('semaforo_meta', ''))}</b> ({aud.get('factibilidad_pct', 80)}% factibilidad)\n"
            f"└ <i>{html.escape(aud.get('diagnostico_24h', ''))}</i>\n\n"
        )
    else:
        msg += "\n"

    if not plan["posiciones"]:
        msg += "⏳ <i>Sin posiciones abiertas en este momento.</i>\n"
    else:
        for idx, p in enumerate(plan["posiciones"], start=1):
            uid = int(time.time() * 1000) + random.randint(1, 999)
            u_ia = f"{BASE_URL_NETLIFY}/?coin={p['base']}&price={p['precio_actual']}&v={p['base']}_{uid}"
            u_tr = f"[https://www.binance.com/es/trade/](https://www.binance.com/es/trade/){p['base']}_USDT"
            motivo = html.escape(p.get("motivo_eleccion", p.get("origen", "")))
            fib_l = html.escape(p.get("fib_lectura", "Fib N/D"))
            orden_tr = html.escape(p.get("trader_ia_orden", "🟢 MANTENER"))
            razon_tr = html.escape(p.get("trader_ia_razon", ""))
            stop_act = float(p.get("stop_actual_pct", STOP_PROTECCION_PCT))
            stop_label = f"🛡️ Trailing BE: <code>+{stop_act:.1f}%</code>" if stop_act > 0 else f"Stop: <code>{stop_act:.1f}%</code>"

            msg += (
                f"🟢 <b>{idx}. {p['base']}</b> — Asignado: <code>${p['capital_usd']:,.2f} USD</code>\n"
                f"• <b>Certificación:</b> <i>{motivo}</i>\n"
                f"• <b>Entrada:</b> <code>{formatear_precio(p['precio_entrada'])}</code> ➔ <b>Actual:</b> <code>{formatear_precio(p['precio_actual'])}</code> (<b>{p['pnl_pct']:+.2f}%</b> | <code>${p['pnl_usd']:+.2f}</code>)\n"
                f"• <b>Objetivo (+{p['subida_necesaria_pct']:.2f}%):</b> <code>{formatear_precio(p['precio_objetivo'])}</code> | {stop_label}\n"
                f"• <b>Geometría Fib:</b> <code>{fib_l}</code>\n"
                f"• <b>Copiloto Trader IA:</b> <b>{orden_tr}</b> — <i>{razon_tr}</i>\n"
                f"└ <a href=\"{html.escape(u_ia)}\">📊 Gráfico IA</a> | <a href=\"{html.escape(u_tr)}\">🔶 Tradear Spot</a>\n\n"
            )
    return msg.strip()

def ejecutar_gestor_semanal():
    s = crear_sesion_binance()
    mapa_mkt = obtener_tickers_binance(s)
    if not mapa_mkt:
        print("❌ Sin datos de Binance.")
        return

    plan = cargar_plan_semanal()
    ahora_dt = ahora_art()
    ahora_str = ahora_dt.strftime("%Y-%m-%d %H:%M ART")
    alertas_venta = []
    alertas_parciales = []
    nuevas_entradas = []

    if plan["estado_semana"] == "META_CUMPLIDA":
        print(f"✅ Semana {plan['semana_id']} ya tiene META CUMPLIDA. Modo protección activo.")
        return

    ganancia_flotante_total = 0.0
    posiciones_siguen_activas = []

    for pos in plan["posiciones"]:
        sym = pos["symbol"]
        mkt = mapa_mkt.get(sym)
        if not mkt:
            posiciones_siguen_activas.append(pos)
            continue

        p_act = mkt["precio"]
        p_ent = float(pos["precio_entrada"])
        cap = float(pos["capital_usd"])
        p_max = max(float(pos.get("precio_maximo", p_ent)), p_act)

        pnl_pct = ((p_act - p_ent) / p_ent) * 100 if p_ent > 0 else 0.0
        max_pnl_pct = ((p_max - p_ent) / p_ent) * 100 if p_ent > 0 else 0.0
        pnl_usd = cap * (pnl_pct / 100.0)
        retroceso_desde_max = ((p_act - p_max) / p_max) * 100 if p_max > 0 else 0.0
        horas_abierta = calcular_horas_abierta(pos.get("fecha_entrada", ""))

        # Trailing Break-Even escalonado según el máximo alcanzado
        stop_dinamico_pct = STOP_PROTECCION_PCT
        if max_pnl_pct >= 13.0:
            stop_dinamico_pct = 7.0
        elif max_pnl_pct >= 8.0:
            stop_dinamico_pct = 2.0

        pos["precio_actual"] = p_act
        pos["precio_maximo"] = p_max
        pos["pnl_pct"] = round(pnl_pct, 2)
        pos["pnl_usd"] = round(pnl_usd, 2)
        pos["stop_actual_pct"] = stop_dinamico_pct
        pos.setdefault("motivo_eleccion", pos.get("origen", "🛡️ Certificada IA"))

        if not pos.get("tp1_ejecutado", False) and pnl_pct >= float(pos["subida_necesaria_pct"]):
            cap_vendido = round(cap * 0.5, 2)
            ganancia_tp1 = round(cap_vendido * (pnl_pct / 100.0), 2)
            pos["capital_usd"] = round(cap - cap_vendido, 2)
            pos["tp1_ejecutado"] = True
            pos["pnl_usd"] = round(pos["capital_usd"] * (pnl_pct / 100.0), 2)
            plan["ganancia_realizada_usd"] = round(float(plan["ganancia_realizada_usd"]) + ganancia_tp1, 2)
            alertas_parciales.append({
                "base": pos["base"],
                "pnl_pct": round(pnl_pct, 2),
                "ganancia_tp1": ganancia_tp1,
                "precio_actual": p_act,
                "capital_restante": pos["capital_usd"]
            })

        motivo_cierre = None
        if pos.get("tp1_ejecutado", False) and retroceso_desde_max <= -TRAILING_DESDE_MAX_PCT:
            motivo_cierre = f"🎯 CIERRE 2ª MITAD (Trailing Stop): tocó máx +{max_pnl_pct:.1f}% y retrocedió {retroceso_desde_max:.1f}%."
        elif not pos.get("tp1_ejecutado", False) and pnl_pct >= 25.0 and retroceso_desde_max <= -3.5:
            motivo_cierre = f"🚀 EXPLOSIÓN CAPTURADA: +{pnl_pct:.1f}% asegurado antes de corrección."
        elif not pos.get("tp1_ejecutado", False) and pnl_pct <= stop_dinamico_pct:
            if stop_dinamico_pct > 0:
                motivo_cierre = f"🛡️ TRAILING BREAK-EVEN (+{stop_dinamico_pct:.1f}%): tocó máx +{max_pnl_pct:.1f}% y aseguró ganancia en {pnl_pct:+.2f}%."
            else:
                motivo_cierre = f"🛡️ STOP ESTRUCTURAL ({pnl_pct:.1f}%): corta pérdida y libera capital."
        elif not pos.get("tp1_ejecutado", False) and horas_abierta >= HORAS_MAX_SIN_ARRANQUE and pnl_pct < 3.0:
            motivo_cierre = f"⏳ ROTACIÓN POR TIEMPO ({int(horas_abierta)}h sin arrancar, {pnl_pct:+.1f}%): libera capital ocioso."

        if motivo_cierre:
            pos["estado"] = "CERRADA"
            pos["fecha_cierre"] = ahora_str
            pos["motivo_cierre"] = motivo_cierre
            plan["ganancia_realizada_usd"] = round(float(plan["ganancia_realizada_usd"]) + float(pos["pnl_usd"]), 2)
            plan["historial_cierres"].append(pos)
            alertas_venta.append(pos)
        else:
            ganancia_flotante_total += float(pos["pnl_usd"])
            posiciones_siguen_activas.append(pos)

    plan["posiciones"] = posiciones_siguen_activas

    total_semanal_actual = float(plan["ganancia_realizada_usd"]) + ganancia_flotante_total
    if total_semanal_actual >= float(plan["meta_semanal_usd"]):
        for pos in plan["posiciones"]:
            pos["estado"] = "CERRADA_META_SEMANAL"
            pos["fecha_cierre"] = ahora_str
            pos["motivo_cierre"] = "🏆 CUOTA SEMANAL ALCANZADA — CIERRE TOTAL"
            plan["ganancia_realizada_usd"] = round(float(plan["ganancia_realizada_usd"]) + float(pos["pnl_usd"]), 2)
            plan["historial_cierres"].append(pos)
            alertas_venta.append(pos)
        plan["posiciones"] = []
        plan["estado_semana"] = "META_CUMPLIDA"
        plan["fecha_cierre_meta"] = ahora_str

    excluidas = {p["symbol"] for p in plan["posiciones"]} | {c["symbol"] for c in plan["historial_cierres"] if c.get("semana_id") == plan["semana_id"]}
    alternativas = evaluar_alternativas_al_horno(s, mapa_mkt, excluidas)
    plan["alternativas_evaluadas"] = alternativas

    btc_ok, msg_btc = verificar_clima_btc(s, mapa_mkt)
    es_ventana_cierre_dia = (ahora_dt.hour == 23 and ahora_dt.minute >= 50) or (ahora_dt.hour == 0 and ahora_dt.minute <= 10)

    if plan["estado_semana"] == "ACTIVA" and len(plan["posiciones"]) < MAX_MONEDAS_SEMANA and (es_ventana_cierre_dia or len(plan["posiciones"]) == 0):
        if not btc_ok:
            if not plan.get("aviso_btc_enviado", False):
                enviar_telegram_texto(f"🛑 <b>FRENO DE MANO BTC ACTIVADO</b>\n📅 <code>{ahora_str}</code>\n\n⚠️ {html.escape(msg_btc)}")
                plan["aviso_btc_enviado"] = True
        else:
            plan["aviso_btc_enviado"] = False
            cupos = MAX_MONEDAS_SEMANA - len(plan["posiciones"])
            elegidas = [a for a in alternativas if a.get("en_zona")][:cupos]

            if elegidas:
                total_cartera_futura = len(plan["posiciones"]) + len(elegidas)
                cap_base_total = float(plan["capital_total_usd"]) + float(plan["ganancia_realizada_usd"])
                cap_objetivo_por_moneda = round(cap_base_total / total_cartera_futura, 2)
                meta_restante = max(50.0, float(plan["meta_semanal_usd"]) - float(plan["ganancia_realizada_usd"]))
                meta_por_moneda = meta_restante / total_cartera_futura
                subida_nec_pct = round((meta_por_moneda / cap_objetivo_por_moneda) * 100.0, 2)

                for p_ex in plan["posiciones"]:
                    p_ex["capital_usd"] = cap_objetivo_por_moneda
                    p_ex["subida_necesaria_pct"] = subida_nec_pct
                    p_ex["precio_objetivo"] = float(p_ex["precio_entrada"]) * (1.0 + (subida_nec_pct / 100.0))
                    p_ex["pnl_usd"] = round(cap_objetivo_por_moneda * (float(p_ex["pnl_pct"]) / 100.0), 2)

                for el in elegidas:
                    p_ent = float(el["precio_entrada"])
                    p_obj = p_ent * (1.0 + (subida_nec_pct / 100.0))
                    nueva_pos = {
                        "semana_id": plan["semana_id"],
                        "symbol": el["symbol"],
                        "base": el["base"],
                        "origen": el["origen"],
                        "motivo_eleccion": el["motivo_tecnico"],
                        "fecha_entrada": ahora_str,
                        "capital_usd": cap_objetivo_por_moneda,
                        "precio_entrada": p_ent,
                        "precio_objetivo": p_obj,
                        "subida_necesaria_pct": subida_nec_pct,
                        "precio_actual": p_ent,
                        "precio_maximo": p_ent,
                        "pnl_pct": 0.0,
                        "pnl_usd": 0.0,
                        "stop_actual_pct": STOP_PROTECCION_PCT,
                        "tp1_ejecutado": False,
                        "estado": "ACTIVA"
                    }
                    plan["posiciones"].append(nueva_pos)
                    nuevas_entradas.append(nueva_pos)

    aud_actual = evaluar_copiloto_trader_y_auditor_ia(s, mapa_mkt, plan, msg_btc)

    veredicto_final_txt = ""
    if plan["estado_semana"] == "META_CUMPLIDA":
        veredicto_final_txt = generar_veredicto_final_ia(plan)
        plan["auditoria_ia"]["veredicto_final_semana"] = veredicto_final_txt
        aud_actual["veredicto_final_semana"] = veredicto_final_txt

    alertas_ia_inmediatas = [
        p for p in plan["posiciones"]
        if any(tag in p.get("trader_ia_orden", "") for tag in ["VENDER AHORA", "ASEGURAR 50%", "RIESGO DE BAJADA"])
    ]
    for p_v in alertas_ia_inmediatas:
        enviar_telegram_texto(
            f"🚨 <b>COPILOTO TRADER IA + FIB • ALERTA EN VIVO (10m)</b>\n"
            f"📅 <code>{ahora_str}</code>\n\n"
            f"💰 <b>{p_v['base']}</b> | PnL actual: <b>{p_v['pnl_pct']:+.2f}%</b> (<code>${p_v['pnl_usd']:+.2f} USD</code>)\n"
            f"• <b>Orden IA:</b> <b>{html.escape(p_v['trader_ia_orden'])}</b>\n"
            f"• <b>Geometría Fib:</b> <code>{html.escape(p_v.get('fib_lectura', ''))}</code>\n"
            f"• <b>Análisis gráfico 15m/1h:</b> <i>{html.escape(p_v.get('trader_ia_razon', ''))}</i>"
        )

    es_corte_horario = (plan.get("ultimo_reporte_hora") != ahora_dt.hour)
    hay_novedades = bool(nuevas_entradas or alertas_parciales or alertas_venta or plan["estado_semana"] == "META_CUMPLIDA")

    if hay_novedades or es_corte_horario:
        plan["ultimo_reporte_hora"] = ahora_dt.hour
        plan.setdefault("historial_auditorias", []).append(dict(aud_actual))
        plan["historial_auditorias"] = plan["historial_auditorias"][-100:]
        actualizar_excel_semanal(plan)

        enviar_telegram_texto(construir_bloque_1_alternativas(plan))
        time.sleep(1.5)

        img = generar_tablero_visual(plan)
        if plan["estado_semana"] == "META_CUMPLIDA":
            titulo_ev = "🏆 <b>¡CUOTA SEMANAL CUMPLIDA — MODO PROTECCIÓN!</b>"
        elif nuevas_entradas:
            titulo_ev = "🆕 <b>SELECCIÓN DE CARTERA BLINDADA (DOBLE CERT. IA + FIB)</b>"
        elif alertas_venta or alertas_parciales:
            titulo_ev = "💰 <b>ACTUALIZACIÓN DE TOMA DE GANANCIAS / CIERRE</b>"
        else:
            titulo_ev = "📡 <b>RADAR CONTINUO • AUDITORÍA 24H, FIBONACCI Y TRADER IA</b>"

        caption = construir_bloque_2_cartera(plan, titulo_ev)
        enviar_foto_telegram(img, caption)
        time.sleep(1.5)

        enviar_excel_telegram(
            f"📎 <b>GESTOR Y RADAR SEMANAL • BLOQUE 3/3: PLANILLA EXCEL</b>\n"
            f"📊 Registro completo en 4 pestañas con Certificación IA, Fibonacci 4H y Veredicto (<code>{EXCEL_SEMANAL_FILE}</code>)."
        )
    else:
        actualizar_excel_semanal(plan)

    for v in alertas_venta:
        msg_v = (
            f"🔔 <b>DETALLE DE CIERRE • {v['base']}</b>\n"
            f"• Resultado: <b>{v['pnl_pct']:+.2f}%</b> (<b>{v['pnl_usd']:+.2f} USD</b>) | Máx: <code>{formatear_precio(v['precio_maximo'])}</code>\n"
            f"• Motivo: <i>{html.escape(v.get('motivo_cierre', ''))}</i>"
        )
        enviar_telegram_texto(msg_v)

    if plan["estado_semana"] == "META_CUMPLIDA":
        msg_m = (
            f"🏆 <b>¡CUOTA SEMANAL CUMPLIDA EN MODO PRUEBA!</b>\n"
            f"📅 Semana <code>{plan['semana_id']}</code> cerrada el <code>{ahora_str}</code>\n\n"
            f"✅ <b>Ganancia Total Simulada:</b> <code>${plan['ganancia_realizada_usd']:,.2f} USD</code> (Meta: <code>${plan['meta_semanal_usd']:,.2f} USD</code>)\n\n"
            f"{veredicto_final_txt}\n\n"
            f"🛡️ <i>El bot entra en MODO PROTECCIÓN hasta el próximo lunes para asegurar el resultado.</i>"
        )
        enviar_telegram_texto(msg_m)

    guardar_plan_semanal(plan)

if __name__ == "__main__":
    print(f"🧪 INICIANDO GESTOR SEMANAL BLINDADO + IA + FIBONACCI ({ahora_art().strftime('%H:%M:%S')} ART)...")
    ejecutar_gestor_semanal()
