import os, json, time, random, html, requests
from datetime import datetime, timezone, timedelta
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment

TZ_ART = timezone(timedelta(hours=-3))
TELEGRAM_BOT_TOKEN = (os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("TELEGRAM_TOKEN") or "").strip()
TELEGRAM_CHAT_ID = (os.getenv("TELEGRAM_CHAT_ID") or os.getenv("CHAT_ID") or "").strip()
# Recuerda cambiar por el ID de tópico de tu nuevo canal "Gestor y radar semanal" (o "4" por defecto)
TELEGRAM_TOPIC_ID = "18574"  # Es el ID visible en el enlace que creaste en la captura

HISTORIAL_PERLAS_FILE = "historial_perlas.json"
PLAN_SEMANAL_FILE = "plan_semanal.json"
EXCEL_SEMANAL_FILE = "AUDITORIA_SEMANAL_PRUEBA.xlsx"

# Parámetros de la prueba semanal (puedes ajustarlos a tu gusto)
CAPITAL_INICIAL_PRUEBA = 3500.0
META_SEMANAL_USD = 600.0
MAX_MONEDAS_SEMANA = 2
STOP_PROTECCION_PCT = -7.5
TRAILING_DESDE_MAX_PCT = 3.5

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

def analizar_momentum_1h(session, symbol):
    for base_url in ["https://api.binance.com", "https://data-api.binance.vision"]:
        try:
            r = session.get(f"{base_url}/api/v3/klines", params={"symbol": symbol, "interval": "1h", "limit": 20}, timeout=7)
            if r.status_code == 200:
                k = r.json()
                if len(k) < 15:
                    continue
                cierres = [float(x[4]) for x in k]
                vols = [float(x[7]) for x in k]
                deltas = [cierres[i] - cierres[i - 1] for i in range(1, len(cierres))]
                g = [d if d > 0 else 0.0 for d in deltas]
                p = [-d if d < 0 else 0.0 for d in deltas]
                ag, ap = sum(g[:14]) / 14.0, sum(p[:14]) / 14.0
                rsi = 100.0 if ap == 0 else round(100.0 - (100.0 / (1.0 + (ag / ap))), 1)
                v_rec = sum(vols[-2:]) / 2.0
                v_prev = sum(vols[-12:-2]) / 10.0
                vol_ratio = round(v_rec / v_prev, 2) if v_prev > 0 else 1.0
                var_1h = round(((cierres[-1] - float(k[-1][1])) / float(k[-1][1])) * 100, 2)
                return {"ok": True, "rsi_1h": rsi, "vol_ratio": vol_ratio, "var_1h": var_1h}
        except Exception:
            continue
    return {"ok": False, "rsi_1h": 50.0, "vol_ratio": 1.0, "var_1h": 0.0}

def cargar_plan_semanal():
    sem = id_semana_actual()
    base = {
        "semana_id": sem,
        "fecha_inicio": ahora_art().strftime("%Y-%m-%d %H:%M"),
        "modo": "PRUEBA_SIMULACION",
        "capital_total_usd": CAPITAL_INICIAL_PRUEBA,
        "meta_semanal_usd": META_SEMANAL_USD,
        "ganancia_realizada_usd": 0.0,
        "estado_semana": "ACTIVA",
        "fecha_cierre_meta": "",
        "posiciones": [],
        "historial_cierres": []
    }
    if os.path.exists(PLAN_SEMANAL_FILE):
        try:
            with open(PLAN_SEMANAL_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if data.get("semana_id") == sem:
                return data
            if data.get("historial_cierres"):
                base["historial_cierres"] = data["historial_cierres"][-30:]
        except Exception:
            pass
    return base

def guardar_plan_semanal(plan):
    try:
        with open(PLAN_SEMANAL_FILE, "w", encoding="utf-8") as f:
            json.dump(plan, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"⚠️ Error guardando {PLAN_SEMANAL_FILE}: {e}")

def seleccionar_monedas_al_horno(session, mapa_mkt, excluidas, cantidad):
    if not os.path.exists(HISTORIAL_PERLAS_FILE):
        return []
    try:
        with open(HISTORIAL_PERLAS_FILE, "r", encoding="utf-8") as f:
            perlas = json.load(f)
    except Exception:
        return []

    candidatos = []
    for sym, info in perlas.get("graduadas_pre_explosion", {}).items():
        if sym in excluidas or sym not in mapa_mkt:
            continue
        mkt = mapa_mkt[sym]
        p_ref = float(info.get("precio_ref", mkt["precio"]))
        var_desde_filtro = ((mkt["precio"] - p_ref) / p_ref) * 100 if p_ref > 0 else 0.0
        if -3.0 <= var_desde_filtro <= 8.0 and -4.0 <= mkt["cambio_24h"] <= 10.0:
            mom = analizar_momentum_1h(session, sym)
            if mom["rsi_1h"] <= 68.0:
                score = int(info.get("probabilidad_pct", 70)) + (10 if info.get("origen") == "CAZADOR_TACTICO_ROJO" else 0)
                candidatos.append({
                    "symbol": sym,
                    "base": sym[:-4],
                    "precio_entrada": mkt["precio"],
                    "origen": info.get("origen", "VERDE_PRE_EXPLOSION"),
                    "score": score,
                    "mom": mom
                })

    for sym, info in perlas.get("posta", {}).items():
        if sym in excluidas or sym not in mapa_mkt or any(c["symbol"] == sym for c in candidatos):
            continue
        if int(info.get("etapa", 1)) >= 2:
            mkt = mapa_mkt[sym]
            if -4.0 <= mkt["cambio_24h"] <= 10.0:
                mom = analizar_momentum_1h(session, sym)
                if mom["rsi_1h"] <= 68.0:
                    candidatos.append({
                        "symbol": sym,
                        "base": sym[:-4],
                        "precio_entrada": mkt["precio"],
                        "origen": f"POSTA_ETAPA_{info.get('etapa')}",
                        "score": int(info.get("prob_actual", 65)),
                        "mom": mom
                    })

    candidatos.sort(key=lambda x: (x["score"], x["mom"]["vol_ratio"]), reverse=True)
    return candidatos[:cantidad]

def actualizar_excel_semanal(plan):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "PRUEBA_SEMANAL"

    headers = [
        "Semana", "Fecha Entrada", "Moneda", "Origen Señal", "Capital Invertido ($)",
        "Precio Entrada", "Precio Objetivo (+%)", "Subida Necesaria (%)",
        "Precio Actual / Cierre", "Máximo Alcanzado", "Rendimiento Real (%)",
        "Ganancia / Pérdida ($)", "Estado Posición", "Meta Semanal ($)", "Estado Semana"
    ]
    ws.append(headers)

    fill_hdr = PatternFill(start_color="0B132B", end_color="0B132B", fill_type="solid")
    font_hdr = Font(color="FFFFFF", bold=True)
    for col_idx in range(1, len(headers) + 1):
        cell = ws.cell(row=1, column=col_idx)
        cell.fill = fill_hdr
        cell.font = font_hdr
        cell.alignment = Alignment(horizontal="center")

    todas = list(plan.get("historial_cierres", [])) + list(plan.get("posiciones", []))
    for pos in todas:
        ws.append([
            pos.get("semana_id", plan["semana_id"]),
            pos.get("fecha_entrada", ""),
            pos.get("base", ""),
            pos.get("origen", ""),
            round(float(pos.get("capital_usd", 0)), 2),
            float(pos.get("precio_entrada", 0)),
            float(pos.get("precio_objetivo", 0)),
            round(float(pos.get("subida_necesaria_pct", 0)), 2),
            float(pos.get("precio_actual", 0)),
            float(pos.get("precio_maximo", 0)),
            round(float(pos.get("pnl_pct", 0)), 2),
            round(float(pos.get("pnl_usd", 0)), 2),
            pos.get("estado", ""),
            round(float(plan.get("meta_semanal_usd", META_SEMANAL_USD)), 2),
            plan.get("estado_semana", "ACTIVA")
        ])

    for col in ws.columns:
        max_len = max(len(str(c.value or "")) for c in col)
        ws.column_dimensions[col[0].column_letter].width = min(max_len + 4, 26)

    wb.save(EXCEL_SEMANAL_FILE)

def enviar_telegram_texto(texto):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
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

def enviar_excel_telegram(caption):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID or not os.path.exists(EXCEL_SEMANAL_FILE):
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendDocument"
    data = {"chat_id": TELEGRAM_CHAT_ID, "caption": caption[:1000], "parse_mode": "HTML"}
    if TELEGRAM_TOPIC_ID.isdigit():
        data["message_thread_id"] = int(TELEGRAM_TOPIC_ID)
    try:
        with open(EXCEL_SEMANAL_FILE, "rb") as f:
            requests.post(url, data=data, files={"document": f}, timeout=25)
    except Exception as e:
        print(f"⚠️ Error enviando Excel Semanal: {e}")

def ejecutar_gestor_semanal():
    s = crear_sesion_binance()
    mapa_mkt = obtener_tickers_binance(s)
    if not mapa_mkt:
        print("❌ Sin datos de Binance.")
        return

    plan = cargar_plan_semanal()
    ahora_str = ahora_art().strftime("%Y-%m-%d %H:%M ART")
    alertas_venta = []
    nuevas_entradas = []

    if plan["estado_semana"] == "META_CUMPLIDA":
        print(f"✅ Semana {plan['semana_id']} ya tiene META CUMPLIDA (${plan['ganancia_realizada_usd']:.2f}). Modo protección activo.")
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
        pnl_usd = cap * (pnl_pct / 100.0)
        retroceso_desde_max = ((p_act - p_max) / p_max) * 100 if p_max > 0 else 0.0

        pos["precio_actual"] = p_act
        pos["precio_maximo"] = p_max
        pos["pnl_pct"] = round(pnl_pct, 2)
        pos["pnl_usd"] = round(pnl_usd, 2)

        motivo_cierre = None
        if pnl_pct >= float(pos["subida_necesaria_pct"]) and retroceso_desde_max <= -TRAILING_DESDE_MAX_PCT:
            motivo_cierre = f"🎯 VENTA EN MÁXIMO (Trailing Stop): alcanzó +{((p_max - p_ent)/p_ent)*100:.1f}% y retrocedió {retroceso_desde_max:.1f}% desde techo."
        elif pnl_pct >= 25.0 and retroceso_desde_max <= -3.0:
            motivo_cierre = f"🚀 EXPLOSIÓN CAPTURADA: +{pnl_pct:.1f}% asegurado antes de corrección."
        elif pnl_pct <= STOP_PROTECCION_PCT:
            motivo_cierre = f"🛡️ STOP DE PROTECCIÓN ({pnl_pct:.1f}%): corta pérdida y libera capital."

        if motivo_cierre:
            pos["estado"] = "CERRADA"
            pos["fecha_cierre"] = ahora_str
            pos["motivo_cierre"] = motivo_cierre
            plan["ganancia_realizada_usd"] = round(float(plan["ganancia_realizada_usd"]) + pnl_usd, 2)
            plan["historial_cierres"].append(pos)
            alertas_venta.append(pos)
        else:
            ganancia_flotante_total += pnl_usd
            posiciones_siguen_activas.append(pos)

    plan["posiciones"] = posiciones_siguen_activas

    total_semanal_actual = float(plan["ganancia_realizada_usd"]) + ganancia_flotante_total
    if total_semanal_actual >= float(plan["meta_semanal_usd"]):
        for pos in plan["posiciones"]:
            pos["estado"] = "CERRADA_META_SEMANAL"
            pos["fecha_cierre"] = ahora_str
            pos["motivo_cierre"] = "🏆 CUOTA SEMANAL DE $600 ALCANZADA — CIERRE TOTAL"
            plan["ganancia_realizada_usd"] = round(float(plan["ganancia_realizada_usd"]) + float(pos["pnl_usd"]), 2)
            plan["historial_cierres"].append(pos)
            alertas_venta.append(pos)
        plan["posiciones"] = []
        plan["estado_semana"] = "META_CUMPLIDA"
        plan["fecha_cierre_meta"] = ahora_str

    if plan["estado_semana"] == "ACTIVA" and len(plan["posiciones"]) < MAX_MONEDAS_SEMANA:
        cupos = MAX_MONEDAS_SEMANA - len(plan["posiciones"])
        capital_en_uso = sum(float(p["capital_usd"]) for p in plan["posiciones"])
        capital_disponible = max(0.0, float(plan["capital_total_usd"]) + float(plan["ganancia_realizada_usd"]) - capital_en_uso)
        meta_restante = max(50.0, float(plan["meta_semanal_usd"]) - float(plan["ganancia_realizada_usd"]))

        if capital_disponible >= 200.0:
            excluidas = {p["symbol"] for p in plan["posiciones"]} | {c["symbol"] for c in plan["historial_cierres"] if c.get("semana_id") == plan["semana_id"]}
            elegidas = seleccionar_monedas_al_horno(s, mapa_mkt, excluidas, cupos)
            if elegidas:
                cap_por_moneda = capital_disponible / len(elegidas)
                meta_por_moneda = meta_restante / len(elegidas)
                for el in elegidas:
                    subida_nec_pct = round((meta_por_moneda / cap_por_moneda) * 100.0, 2)
                    p_ent = float(el["precio_entrada"])
                    p_obj = p_ent * (1.0 + (subida_nec_pct / 100.0))
                    nueva_pos = {
                        "semana_id": plan["semana_id"],
                        "symbol": el["symbol"],
                        "base": el["base"],
                        "origen": el["origen"],
                        "fecha_entrada": ahora_str,
                        "capital_usd": round(cap_por_moneda, 2),
                        "precio_entrada": p_ent,
                        "precio_objetivo": p_obj,
                        "subida_necesaria_pct": subida_nec_pct,
                        "precio_actual": p_ent,
                        "precio_maximo": p_ent,
                        "pnl_pct": 0.0,
                        "pnl_usd": 0.0,
                        "estado": "ACTIVA"
                    }
                    plan["posiciones"].append(nueva_pos)
                    nuevas_entradas.append(nueva_pos)

    guardar_plan_semanal(plan)
    actualizar_excel_semanal(plan)

    if nuevas_entradas:
        msg = (
            f"🧪 <b>PLAN SEMANAL (PRUEBA) • NUEVA ASIGNACIÓN</b>\n"
            f"📅 Semana <code>{plan['semana_id']}</code> | Meta: <b>${plan['meta_semanal_usd']:.0f} USD</b>\n\n"
        )
        for p in nuevas_entradas:
            uid = int(time.time() * 1000) + random.randint(1, 999)
            u_ia = f"{BASE_URL_NETLIFY}/?coin={p['base']}&price={p['precio_entrada']}&v={p['base']}_{uid}"
            msg += (
                f"🟢 <b>{p['base']}</b> (<i>{p['origen']}</i>)\n"
                f"• <b>Capital Simulado:</b> <code>${p['capital_usd']:,.2f} USD</code>\n"
                f"• <b>Entrada:</b> <code>{formatear_precio(p['precio_entrada'])}</code> ➔ <b>Objetivo:</b> <code>{formatear_precio(p['precio_objetivo'])}</code>\n"
                f"• <b>Subida necesaria para cuota:</b> <b>+{p['subida_necesaria_pct']:.2f}%</b>\n"
                f"└ <a href=\"{html.escape(u_ia)}\">📊 Ver Gráfico IA</a>\n\n"
            )
        enviar_telegram_texto(msg)

    for v in alertas_venta:
        msg_v = (
            f"🔔 <b>RADAR DE SALIDA • OPERACIÓN CERRADA (PRUEBA)</b>\n"
            f"📅 <code>{ahora_str}</code>\n\n"
            f"💰 <b>{v['base']}</b> | Resultado: <b>{v['pnl_pct']:+.2f}%</b> (<b>{v['pnl_usd']:+.2f} USD</b>)\n"
            f"• Entrada: <code>{formatear_precio(v['precio_entrada'])}</code> ➔ Salida: <code>{formatear_precio(v['precio_actual'])}</code> (Máx: <code>{formatear_precio(v['precio_maximo'])}</code>)\n"
            f"• Motivo: <i>{html.escape(v.get('motivo_cierre', ''))}</i>\n"
            f"📊 <b>Acumulado Semana:</b> <code>${plan['ganancia_realizada_usd']:,.2f} / ${plan['meta_semanal_usd']:,.2f} USD</code>"
        )
        enviar_telegram_texto(msg_v)

    if plan["estado_semana"] == "META_CUMPLIDA":
        msg_m = (
            f"🏆 <b>¡CUOTA SEMANAL CUMPLIDA EN MODO PRUEBA!</b>\n"
            f"📅 Semana <code>{plan['semana_id']}</code> cerrada el <code>{ahora_str}</code>\n\n"
            f"✅ <b>Ganancia Total Simulada:</b> <code>${plan['ganancia_realizada_usd']:,.2f} USD</code> (Meta: <code>${plan['meta_semanal_usd']:,.2f} USD</code>)\n"
            f"🛡️ <i>El bot entra en MODO PROTECCIÓN hasta el próximo lunes para asegurar el resultado.</i>"
        )
        enviar_telegram_texto(msg_m)
        enviar_excel_telegram(f"📎 Planilla semanal cerrada ({plan['semana_id']}): +${plan['ganancia_realizada_usd']:,.2f} USD.")

if __name__ == "__main__":
    print(f"🧪 INICIANDO GESTOR SEMANAL DE PRUEBA ({ahora_art().strftime('%H:%M:%S')} ART)...")
    ejecutar_gestor_semanal()
