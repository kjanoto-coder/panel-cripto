import os, json, time, random, html, requests
from datetime import datetime, timezone, timedelta
import matplotlib.pyplot as plt
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment

TZ_ART = timezone(timedelta(hours=-3))
TELEGRAM_BOT_TOKEN = (os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("TELEGRAM_TOKEN") or "").strip()
TELEGRAM_CHAT_ID = (os.getenv("TELEGRAM_CHAT_ID") or os.getenv("CHAT_ID") or "").strip()
TELEGRAM_TOPIC_ID = (os.getenv("TOPIC_ID_SEMANAL") or "18574").strip()
BASE_URL_NETLIFY = "https://gregarious-frangollo-0346c5.netlify.app"

HISTORIAL_PERLAS_FILE = "historial_perlas.json"
PLAN_SEMANAL_FILE = "plan_semanal.json"
EXCEL_SEMANAL_FILE = "AUDITORIA_SEMANAL_PRUEBA.xlsx"

# Parámetros de la prueba semanal ampliada a 4 monedas
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

def verificar_clima_btc(session, mapa_mkt):
    btc = mapa_mkt.get("BTCUSDT")
    if not btc:
        return True, "BTC estable"
    chg_24h = float(btc["cambio_24h"])
    mom_btc = analizar_momentum_1h(session, "BTCUSDT")
    rsi_btc = float(mom_btc.get("rsi_1h", 50.0))
    if chg_24h <= -2.5 or rsi_btc < 35.0:
        return False, f"BTC en alerta (24h: {chg_24h:+.2f}%, RSI 1h: {rsi_btc}). Compras pausadas."
    return True, f"BTC estable (24h: {chg_24h:+.2f}%, RSI 1h: {rsi_btc})"

def cargar_plan_semanal():
    sem = id_semana_actual()
    base = {
        "semana_id": sem,
        "fecha_inicio": ahora_art().strftime("%Y-%m-%d %H:%M"),
        "modo": "PRUEBA_SIMULACION_PRO_4X",
        "capital_total_usd": CAPITAL_INICIAL_PRUEBA,
        "meta_semanal_usd": META_SEMANAL_USD,
        "ganancia_realizada_usd": 0.0,
        "estado_semana": "ACTIVA",
        "fecha_cierre_meta": "",
        "aviso_btc_enviado": False,
        "ultimo_reporte_hora": -1,
        "alternativas_evaluadas": [],
        "posiciones": [],
        "historial_cierres": []
    }
    if os.path.exists(PLAN_SEMANAL_FILE):
        try:
            with open(PLAN_SEMANAL_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if data.get("semana_id") == sem:
                data.setdefault("aviso_btc_enviado", False)
                data.setdefault("ultimo_reporte_hora", -1)
                data.setdefault("alternativas_evaluadas", [])
                return data
            if data.get("historial_cierres"):
                base["historial_cierres"] = data["historial_cierres"][-60:]
        except Exception:
            pass
    return base

def guardar_plan_semanal(plan):
    try:
        with open(PLAN_SEMANAL_FILE, "w", encoding="utf-8") as f:
            json.dump(plan, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"⚠️ Error guardando {PLAN_SEMANAL_FILE}: {e}")

def evaluar_alternativas_al_horno(session, mapa_mkt, excluidas):
    """Evalúa todas las candidatas del embudo, arma el ranking y justifica la elección."""
    if not os.path.exists(HISTORIAL_PERLAS_FILE):
        return []
    try:
        with open(HISTORIAL_PERLAS_FILE, "r", encoding="utf-8") as f:
            perlas = json.load(f)
    except Exception:
        return []

    candidatos = []
    # 1. Graduadas desde Cazador Táctico Rojo -> Pre-Explosión
    for sym, info in perlas.get("graduadas_pre_explosion", {}).items():
        if sym not in mapa_mkt:
            continue
        mkt = mapa_mkt[sym]
        p_ref = float(info.get("precio_ref", mkt["precio"]))
        var_desde_filtro = ((mkt["precio"] - p_ref) / p_ref) * 100 if p_ref > 0 else 0.0
        mom = analizar_momentum_1h(session, sym)
        prob = int(info.get("probabilidad_pct", 70))
        score = prob + 12 + (5 if mom["vol_ratio"] >= 1.2 else 0)

        en_zona = (-3.5 <= var_desde_filtro <= 8.5 and -4.5 <= mkt["cambio_24h"] <= 10.5 and mom["rsi_1h"] <= 68.0)
        motivo_tecnico = (
            f"Confirmada Rojo 3⭐⭐⭐ ({var_desde_filtro:+.1f}% desde filtro) | "
            f"RSI 1h: {mom['rsi_1h']} | Vol 1h: x{mom['vol_ratio']} | Prob: {prob}%"
        )
        candidatos.append({
            "symbol": sym,
            "base": sym[:-4],
            "precio_entrada": mkt["precio"],
            "origen": "Cazador ROJO (⭐⭐⭐)",
            "probabilidad": prob,
            "score": score,
            "en_zona": en_zona and (sym not in excluidas),
            "ya_en_cartera": sym in excluidas,
            "motivo_tecnico": motivo_tecnico,
            "mom": mom
        })

    # 2. En seguimiento dentro de la Posta (Etapa 2 Amarillo / Etapa 3 Rojo)
    for sym, info in perlas.get("posta", {}).items():
        if sym not in mapa_mkt or any(c["symbol"] == sym for c in candidatos):
            continue
        et = int(info.get("etapa", 1))
        if et >= 2:
            mkt = mapa_mkt[sym]
            mom = analizar_momentum_1h(session, sym)
            prob = int(info.get("prob_actual", 65))
            var_seq = float(info.get("var_seq", 0.0))
            score = prob + (8 if et == 3 else 3) + (5 if mom["vol_ratio"] >= 1.2 else 0)
            en_zona = (-4.5 <= mkt["cambio_24h"] <= 10.5 and mom["rsi_1h"] <= 68.0)
            etiqueta = "Cazador ROJO (⭐⭐⭐)" if et == 3 else "Cazador AMARILLO (⭐⭐)"
            motivo_tecnico = (
                f"{etiqueta} ({var_seq:+.1f}% desde base 1D) | "
                f"RSI 1h: {mom['rsi_1h']} | Vol 1h: x{mom['vol_ratio']} | Prob: {prob}%"
            )
            candidatos.append({
                "symbol": sym,
                "base": sym[:-4],
                "precio_entrada": mkt["precio"],
                "origen": etiqueta,
                "probabilidad": prob,
                "score": score,
                "en_zona": en_zona and (sym not in excluidas),
                "ya_en_cartera": sym in excluidas,
                "motivo_tecnico": motivo_tecnico,
                "mom": mom
            })

    candidatos.sort(key=lambda x: (x["en_zona"], x["score"], x["mom"]["vol_ratio"]), reverse=True)
    return candidatos[:TOP_ALTERNATIVAS_MOSTRAR]

def generar_tablero_visual(plan, filename="tablero_semanal.png"):
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11.0, 4.6), facecolor="#0b132b", gridspec_kw={"width_ratios": [1.0, 1.55]})
    for ax in (ax1, ax2):
        ax.set_facecolor("#0f172a")
        for sp in ["top", "right", "left", "bottom"]:
            ax.spines[sp].set_color("#1e293b")

    # Panel 1: Progreso hacia la Cuota Semanal ($600 USD)
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

    # Panel 2: Estado de las 4 Monedas Elegidas vs Objetivo (%)
    posiciones = plan.get("posiciones", [])
    if posiciones:
        nombres = [p["base"] for p in posiciones]
        pnls = [float(p.get("pnl_pct", 0.0)) for p in posiciones]
        objs = [float(p.get("subida_necesaria_pct", 17.14)) for p in posiciones]
        x = range(len(nombres))

        ax2.bar([i - 0.17 for i in x], objs, width=0.32, color="#334155", edgecolor="#94a3b8", label="Subida Esperada (%)", zorder=2)
        bars_act = ax2.bar([i + 0.17 for i in x], pnls, width=0.32, color=["#00e676" if v >= 0 else "#ff1744" for v in pnls], zorder=3, label="Actual (%)")
        ax2.axhline(0, color="#475569", linewidth=1.0)
        ax2.axhline(STOP_PROTECCION_PCT, color="#ff1744", linestyle=":", linewidth=1.3, label=f"Stop ({STOP_PROTECCION_PCT}%)")
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
        ax2.text(0.5, 0.5, "Sin posiciones abiertas\n(Esperando señal o Meta Cumplida)", ha="center", va="center", color="#94a3b8", fontsize=10, transform=ax2.transAxes)
        ax2.tick_params(left=False, labelleft=False, bottom=False, labelbottom=False)

    ax2.set_title(f"CARTERA ELEGIDA ({len(posiciones)}/{MAX_MONEDAS_SEMANA}) • RENDIMIENTO VS ESPERADO", color="#00e676", fontsize=10, fontweight="bold", pad=10)
    fig.suptitle(f"ETAPA 4 • GESTOR Y RADAR SEMANAL ({plan['semana_id']}) | {ahora_art().strftime('%d/%m %H:%M ART')}", color="white", fontsize=11.5, fontweight="bold", y=0.98)
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

    # Pestaña 1: Cartera Elegida y Operada
    ws = wb.active
    ws.title = "1_CARTERA_ELEGIDA"
    headers = [
        "Semana", "Fecha Entrada", "Moneda", "Motivo de Elección", "Capital ($)",
        "Precio Entrada", "Precio Objetivo", "Subida Esperada (%)",
        "Precio Actual", "Máximo Alcanzado", "Rendimiento (%)",
        "PnL ($)", "TP1 (50%)", "Estado", "Fecha Cierre"
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
            "SÍ" if pos.get("tp1_ejecutado") else "NO",
            pos.get("estado", ""),
            pos.get("fecha_cierre", "En curso")
        ])
        celda_pnl = ws.cell(row=row_idx, column=12)
        if pnl_v > 0:
            celda_pnl.fill = fill_verde
        elif pnl_v < 0:
            celda_pnl.fill = fill_rojo

    # Pestaña 2: Alternativas Evaluadas (Top 8 del Radar)
    ws_alt = wb.create_sheet(title="2_ALTERNATIVAS_RADAR")
    headers_alt = ["Ranking", "Moneda", "Origen Señal", "Score IA", "Precio Actual", "Decisión", "Análisis Técnico / Motivo"]
    ws_alt.append(headers_alt)
    for col_idx in range(1, len(headers_alt) + 1):
        c = ws_alt.cell(row=1, column=col_idx)
        c.fill = fill_hdr
        c.font = font_hdr
        c.alignment = Alignment(horizontal="center")

    activas_syms = {p["symbol"] for p in plan.get("posiciones", [])}
    for idx, alt in enumerate(plan.get("alternativas_evaluadas", []), start=1):
        estado_alt = "✅ ELEGIDA EN CARTERA" if alt["symbol"] in activas_syms else ("⏳ EN RESERVA (Lista)" if alt.get("en_zona") else "⚠️ FUERA DE ZONA / RSI ALTO")
        ws_alt.append([
            idx, alt.get("base", ""), alt.get("origen", ""), alt.get("score", 0),
            float(alt.get("precio_entrada", 0)), estado_alt, alt.get("motivo_tecnico", "")
        ])

    # Pestaña 3: Resumen Ejecutivo de Cuota Semanal
    ws2 = wb.create_sheet(title="3_RESUMEN_CUOTA")
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

    for sheet in (ws, ws_alt, ws2):
        for col in sheet.columns:
            max_len = max(len(str(c.value or "")) for c in col)
            sheet.column_dimensions[col[0].column_letter].width = min(max_len + 4, 42)

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

def enviar_foto_telegram(imagen_path, caption):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID or not os.path.exists(imagen_path):
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
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
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendDocument"
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
        f"🔍 <b>GESTOR Y RADAR SEMANAL • BLOQUE 1/3: ALTERNATIVAS DETECTADAS</b>\n"
        f"📅 <code>{ahora_str}</code> | Semana <code>{plan['semana_id']}</code>\n"
        f"<i>Ranking de monedas 'al horno' filtradas desde Cazador Táctico y Pre-Explosión:</i>\n\n"
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

    msg = (
        f"🏆 <b>GESTOR Y RADAR SEMANAL • BLOQUE 2/3: CARTERA ELEGIDA</b>\n"
        f"{evento_titulo}\n"
        f"📅 <code>{ahora_str}</code> | Cuota: <code>${meta:,.0f} USD</code> | Progreso: <b>${real + flot:+.2f} USD ({cump}%)</b>\n\n"
    )

    if not plan["posiciones"]:
        msg += "⏳ <i>Sin posiciones abiertas en este momento.</i>\n"
    else:
        for idx, p in enumerate(plan["posiciones"], start=1):
            uid = int(time.time() * 1000) + random.randint(1, 999)
            u_ia = f"{BASE_URL_NETLIFY}/?coin={p['base']}&price={p['precio_actual']}&v={p['base']}_{uid}"
            u_tr = f"https://www.binance.com/es/trade/{p['base']}_USDT"
            motivo = html.escape(p.get("motivo_eleccion", p.get("origen", "")))
            msg += (
                f"🟢 <b>{idx}. {p['base']}</b> — Asignado: <code>${p['capital_usd']:,.2f} USD</code>\n"
                f"• <b>Por qué se eligió:</b> <i>{motivo}</i>\n"
                f"• <b>Entrada:</b> <code>{formatear_precio(p['precio_entrada'])}</code> ➔ <b>Actual:</b> <code>{formatear_precio(p['precio_actual'])}</code> (<b>{p['pnl_pct']:+.2f}%</b> | <code>${p['pnl_usd']:+.2f}</code>)\n"
                f"• <b>Subida esperada:</b> <b>+{p['subida_necesaria_pct']:.2f}%</b> (Obj: <code>{formatear_precio(p['precio_objetivo'])}</code>) | Stop: <code>{STOP_PROTECCION_PCT}%</code>\n"
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
        pnl_usd = cap * (pnl_pct / 100.0)
        retroceso_desde_max = ((p_act - p_max) / p_max) * 100 if p_max > 0 else 0.0
        horas_abierta = calcular_horas_abierta(pos.get("fecha_entrada", ""))

        pos["precio_actual"] = p_act
        pos["precio_maximo"] = p_max
        pos["pnl_pct"] = round(pnl_pct, 2)
        pos["pnl_usd"] = round(pnl_usd, 2)

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
            motivo_cierre = f"🎯 CIERRE 2ª MITAD (Trailing Stop): tocó máx +{((p_max - p_ent)/p_ent)*100:.1f}% y retrocedió {retroceso_desde_max:.1f}%."
        elif not pos.get("tp1_ejecutado", False) and pnl_pct >= 25.0 and retroceso_desde_max <= -3.5:
            motivo_cierre = f"🚀 EXPLOSIÓN CAPTURADA: +{pnl_pct:.1f}% asegurado antes de corrección."
        elif not pos.get("tp1_ejecutado", False) and pnl_pct <= STOP_PROTECCION_PCT:
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

    # Evaluar alternativas y completar hasta 4 monedas en cartera
    excluidas = {p["symbol"] for p in plan["posiciones"]} | {c["symbol"] for c in plan["historial_cierres"] if c.get("semana_id") == plan["semana_id"]}
    alternativas = evaluar_alternativas_al_horno(s, mapa_mkt, excluidas)
    plan["alternativas_evaluadas"] = alternativas

    if plan["estado_semana"] == "ACTIVA" and len(plan["posiciones"]) < MAX_MONEDAS_SEMANA:
        btc_ok, msg_btc = verificar_clima_btc(s, mapa_mkt)
        if not btc_ok:
            if not plan.get("aviso_btc_enviado", False):
                enviar_telegram_texto(f"🛑 <b>FRENO DE MANO BTC ACTIVADO</b>\n📅 <code>{ahora_str}</code>\n\n⚠️ {html.escape(msg_btc)}")
                plan["aviso_btc_enviado"] = True
        else:
            plan["aviso_btc_enviado"] = False
            cupos = MAX_MONEDAS_SEMANA - len(plan["posiciones"])
            capital_en_uso = sum(float(p["capital_usd"]) for p in plan["posiciones"])
            capital_disponible = max(0.0, float(plan["capital_total_usd"]) + float(plan["ganancia_realizada_usd"]) - capital_en_uso)
            meta_restante = max(50.0, float(plan["meta_semanal_usd"]) - float(plan["ganancia_realizada_usd"]))

            if capital_disponible >= 150.0:
                elegidas = [a for a in alternativas if a.get("en_zona")][:cupos]
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
                            "motivo_eleccion": el["motivo_tecnico"],
                            "fecha_entrada": ahora_str,
                            "capital_usd": round(cap_por_moneda, 2),
                            "precio_entrada": p_ent,
                            "precio_objetivo": p_obj,
                            "subida_necesaria_pct": subida_nec_pct,
                            "precio_actual": p_ent,
                            "precio_maximo": p_ent,
                            "pnl_pct": 0.0,
                            "pnl_usd": 0.0,
                            "tp1_ejecutado": False,
                            "estado": "ACTIVA"
                        }
                        plan["posiciones"].append(nueva_pos)
                        nuevas_entradas.append(nueva_pos)

    actualizar_excel_semanal(plan)

    # Enviar los 3 Bloques Ordenados en Telegram
    es_corte_4h = (ahora_dt.hour % 4 == 0 and plan.get("ultimo_reporte_hora") != ahora_dt.hour)
    hay_novedades = bool(nuevas_entradas or alertas_parciales or alertas_venta or plan["estado_semana"] == "META_CUMPLIDA")

    if hay_novedades or es_corte_4h:
        plan["ultimo_reporte_hora"] = ahora_dt.hour

        # Bloque 1/3: Alternativas analizadas
        enviar_telegram_texto(construir_bloque_1_alternativas(plan))
        time.sleep(1.5)

        # Bloque 2/3: Tablero Gráfico + Cartera de 4 Monedas Elegidas y Motivos
        img = generar_tablero_visual(plan)
        if plan["estado_semana"] == "META_CUMPLIDA":
            titulo_ev = "🏆 <b>¡CUOTA SEMANAL CUMPLIDA — MODO PROTECCIÓN!</b>"
        elif nuevas_entradas:
            titulo_ev = "🆕 <b>SELECCIÓN AMPLIADA A 4 MONEDAS (PRUEBA SEMANAL)</b>"
        elif alertas_venta or alertas_parciales:
            titulo_ev = "💰 <b>ACTUALIZACIÓN DE TOMA DE GANANCIAS / CIERRE</b>"
        else:
            titulo_ev = "📡 <b>RADAR CONTINUO • SEGUIMIENTO DE 4 MONEDAS</b>"

        caption = construir_bloque_2_cartera(plan, titulo_ev)
        enviar_foto_telegram(img, caption)
        time.sleep(1.5)

        # Bloque 3/3: Planilla Excel completa adjunta
        enviar_excel_telegram(
            f"📎 <b>GESTOR Y RADAR SEMANAL • BLOQUE 3/3: PLANILLA EXCEL</b>\n"
            f"📊 Registro completo en 3 pestañas (<code>{EXCEL_SEMANAL_FILE}</code>) — Semana <code>{plan['semana_id']}</code>."
        )

    for v in alertas_venta:
        msg_v = (
            f"🔔 <b>DETALLE DE CIERRE • {v['base']}</b>\n"
            f"• Resultado: <b>{v['pnl_pct']:+.2f}%</b> (<b>{v['pnl_usd']:+.2f} USD</b>) | Máx: <code>{formatear_precio(v['precio_maximo'])}</code>\n"
            f"• Motivo: <i>{html.escape(v.get('motivo_cierre', ''))}</i>"
        )
        enviar_telegram_texto(msg_v)

    guardar_plan_semanal(plan)

if __name__ == "__main__":
    print(f"🧪 INICIANDO GESTOR SEMANAL 4X ORDENADO ({ahora_art().strftime('%H:%M:%S')} ART)...")
    ejecutar_gestor_semanal()
