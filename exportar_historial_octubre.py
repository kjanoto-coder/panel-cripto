import os, json, subprocess, time, html, requests
from datetime import datetime, timezone, timedelta
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment

TZ_ART = timezone(timedelta(hours=-3))
TELEGRAM_BOT_TOKEN = (os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("TELEGRAM_TOKEN") or "").strip()
TELEGRAM_CHAT_ID = (os.getenv("TELEGRAM_CHAT_ID") or os.getenv("CHAT_ID") or "").strip()
TELEGRAM_TOPIC_ID = (os.getenv("TOPIC_ID_SEMANAL") or "18574").strip()

TELEGRAM_API_BASE = "https://" + "api.telegram.org/bot"
BINANCE_API_BASES = [
    "https://" + "api.binance.com",
    "https://" + "data-api.binance.vision"
]

FECHA_INICIO_RESCATE = "2026-10-01"
ARCHIVO_EXCEL_HISTORICO = "HISTORIAL_COMPLETO_OCT_NOV_2026.xlsx"
CAPITAL_REF_SIMULACION = 875.0
COMISION_TOTAL_PCT = 0.20
TP1_PCT = 4.8
STOP_MAX_USD = 16.0

def ejecutar_git(args):
    try:
        res = subprocess.run(["git"] + args, capture_output=True, text=True, encoding="utf-8", errors="ignore")
        if res.returncode == 0:
            return res.stdout
    except Exception:
        pass
    return ""

def extraer_registros_de_json(data, archivo, fecha_commit_dt):
    """Extrae pares USDT y sus metadatos desde cualquier estructura JSON de los bots."""
    hallazgos = []
    if not isinstance(data, dict):
        return hallazgos

    def procesar_diccionario(dic, origen_sub):
        for k, v in dic.items():
            if isinstance(k, str) and k.endswith("USDT") and isinstance(v, dict):
                base = k[:-4]
                if base.endswith(("UP", "DOWN", "BULL", "BEAR")):
                    continue
                p_ref = float(v.get("precio_ref") or v.get("precio_entrada") or v.get("precio") or 0.0)
                semaforo = str(v.get("semaforo") or v.get("estado") or "DETECTADA").upper()
                etapa = v.get("etapa", "")
                motivo = str(v.get("razon_ia") or v.get("analisis_ia") or v.get("motivo") or v.get("razon") or "")
                fecha_txt = str(v.get("fecha") or v.get("fecha_entrada") or v.get("timestamp") or "")
                hallazgos.append({
                    "symbol": k,
                    "base": base,
                    "origen": f"{archivo} ({origen_sub})" if origen_sub else archivo,
                    "semaforo": semaforo,
                    "etapa": str(etapa),
                    "precio_ref": p_ref,
                    "motivo": motivo[:140],
                    "fecha_raw": fecha_txt,
                    "dt_deteccion": fecha_commit_dt
                })

    for clave_grupo in ("graduadas_pre_explosion", "posta", "registro_verdes", "monedas", "activos"):
        if isinstance(data.get(clave_grupo), dict):
            procesar_diccionario(data[clave_grupo], clave_grupo)

    procesar_diccionario(data, "raiz")
    return hallazgos

def reconstruir_historial_git():
    """Recorre todos los commits desde octubre 2026 para rescatar cada señal generada."""
    log_out = ejecutar_git(["log", f"--since={FECHA_INICIO_RESCATE}", "--reverse", "--format=%H|%ci", "--", "*.json"])
    commits = []
    for linea in log_out.splitlines():
        if "|" in linea:
            h, fecha_str = linea.strip().split("|", 1)
            try:
                dt = datetime.fromisoformat(fecha_str.strip()).astimezone(TZ_ART)
            except Exception:
                dt = datetime.now(TZ_ART)
            commits.append((h.strip(), dt))

    print(f"📚 Commits con JSON encontrados desde {FECHA_INICIO_RESCATE}: {len(commits)}")
    archivos_ignorar = {"package.json", "package-lock.json", "tsconfig.json", "plan_semanal.json"}
    eventos_unicos = {}

    for commit_hash, dt_commit in commits:
        archivos_txt = ejecutar_git(["ls-tree", "-r", "--name-only", commit_hash])
        for ruta in archivos_txt.splitlines():
            ruta = ruta.strip()
            if not ruta.endswith(".json") or os.path.basename(ruta) in archivos_ignorar:
                continue
            contenido = ejecutar_git(["show", f"{commit_hash}:{ruta}"])
            if not contenido:
                continue
            try:
                data = json.loads(contenido)
            except Exception:
                continue

            for item in extraer_registros_de_json(data, os.path.basename(ruta), dt_commit):
                sym = item["symbol"]
                # Agrupa por moneda y bloque de 7 días (si vuelve a salir >7 días después, cuenta como nueva señal)
                clave_evento = None
                for k_ev, prev in eventos_unicos.items():
                    if prev["symbol"] == sym and abs((dt_commit - prev["dt_deteccion"]).total_seconds()) < 7 * 86400:
                        clave_evento = k_ev
                        break

                if clave_evento is None:
                    clave_evento = f"{sym}_{dt_commit.strftime('%Y%m%d_%H%M')}"
                    eventos_unicos[clave_evento] = item
                else:
                    # Enriquece si luego obtuvo mejor etiqueta o precio_ref válido
                    if eventos_unicos[clave_evento]["precio_ref"] <= 0 and item["precio_ref"] > 0:
                        eventos_unicos[clave_evento]["precio_ref"] = item["precio_ref"]
                    if not eventos_unicos[clave_evento]["motivo"] and item["motivo"]:
                        eventos_unicos[clave_evento]["motivo"] = item["motivo"]
                    if "VERDE" in item["semaforo"] or "GANADORA" in item["semaforo"]:
                        eventos_unicos[clave_evento]["semaforo"] = item["semaforo"]

    # También revisa los archivos JSON actuales en disco por si algo no estaba en el log
    for ruta in os.listdir("."):
        if ruta.endswith(".json") and ruta not in archivos_ignorar:
            try:
                with open(ruta, "r", encoding="utf-8") as f:
                    data = json.load(f)
                dt_now = datetime.now(TZ_ART)
                for item in extraer_registros_de_json(data, ruta, dt_now):
                    sym = item["symbol"]
                    if not any(v["symbol"] == sym for v in eventos_unicos.values()):
                        eventos_unicos[f"{sym}_ACTUAL"] = item
            except Exception:
                continue

    lista = list(eventos_unicos.values())
    lista.sort(key=lambda x: x["dt_deteccion"])
    return lista

def consultar_velas_historicas(session, symbol, dt_inicio):
    """Descarga velas de 4H desde la fecha de detección hasta hoy en Binance."""
    start_ms = int(dt_inicio.timestamp() * 1000)
    for base_url in BINANCE_API_BASES:
        try:
            r = session.get(
                f"{base_url}/api/v3/klines",
                params={"symbol": symbol, "interval": "4h", "startTime": start_ms, "limit": 1000},
                timeout=8
            )
            if r.status_code == 200 and isinstance(r.json(), list) and len(r.json()) > 0:
                return r.json()
        except Exception:
            continue
    return []

def simular_desempeno_historico(ev, klines):
    p_ini = float(ev["precio_ref"])
    if p_ini <= 0:
        p_ini = float(klines[0][1])

    p_max = p_ini
    p_min = p_ini
    p_ult = float(klines[-1][4])

    stop_pct = -(STOP_MAX_USD / CAPITAL_REF_SIMULACION) * 100.0  # ~ -1.83%
    toco_tp1 = False
    toco_stop = False
    resultado_sim_txt = "EN CURSO / LATERAL"
    pnl_sim_usd = 0.0

    for k in klines:
        high_k = float(k[2])
        low_k = float(k[3])
        if high_k > p_max:
            p_max = high_k
        if low_k < p_min:
            p_min = low_k

        var_high_neta = (((high_k - p_ini) / p_ini) * 100.0) - COMISION_TOTAL_PCT
        var_low_neta = (((low_k - p_ini) / p_ini) * 100.0) - COMISION_TOTAL_PCT

        if not toco_tp1 and not toco_stop:
            if var_low_neta <= stop_pct:
                toco_stop = True
                resultado_sim_txt = "🛑 STOP PREVENTIVO (-$16)"
                pnl_sim_usd = -STOP_MAX_USD
            elif var_high_neta >= TP1_PCT:
                toco_tp1 = True
                # Cobra 50% en +4.8% y la 2da mitad queda blindada en +2.0% mínimo
                gan_mitad1 = (CAPITAL_REF_SIMULACION * 0.5) * (TP1_PCT / 100.0)
                gan_mitad2 = (CAPITAL_REF_SIMULACION * 0.5) * (2.0 / 100.0)
                pnl_sim_usd = round(gan_mitad1 + gan_mitad2, 2)
                resultado_sim_txt = f"✅ TP1 (+{TP1_PCT}%) + CORREDOR"

    if not toco_tp1 and not toco_stop:
        var_act_neta = (((p_ult - p_ini) / p_ini) * 100.0) - COMISION_TOTAL_PCT
        pnl_sim_usd = round(CAPITAL_REF_SIMULACION * (var_act_neta / 100.0), 2)

    max_subida_pct = round(((p_max - p_ini) / p_ini) * 100.0, 2)
    max_caida_pct = round(((p_min - p_ini) / p_ini) * 100.0, 2)
    var_actual_pct = round(((p_ult - p_ini) / p_ini) * 100.0, 2)

    iso_y, iso_w, _ = ev["dt_deteccion"].isocalendar()
    return {
        "semana": f"{iso_y}-W{iso_w:02d}",
        "fecha": ev["dt_deteccion"].strftime("%Y-%m-%d %H:%M"),
        "moneda": ev["base"],
        "origen": ev["origen"],
        "semaforo": ev["semaforo"],
        "precio_ini": p_ini,
        "precio_max": p_max,
        "precio_min": p_min,
        "precio_ult": p_ult,
        "max_subida_pct": max_subida_pct,
        "max_caida_pct": max_caida_pct,
        "var_actual_pct": var_actual_pct,
        "toco_tp1": toco_tp1,
        "resultado_sim": resultado_sim_txt,
        "pnl_sim_usd": pnl_sim_usd,
        "motivo": ev["motivo"]
    }

def generar_excel_historico(filas):
    wb = openpyxl.Workbook()
    fill_hdr = PatternFill(start_color="0B132B", end_color="0B132B", fill_type="solid")
    font_hdr = Font(color="FFFFFF", bold=True)
    fill_verde = PatternFill(start_color="D1FAE5", end_color="D1FAE5", fill_type="solid")
    fill_rojo = PatternFill(start_color="FEE2E2", end_color="FEE2E2", fill_type="solid")

    # Pestaña 1: Todas las señales rescatadas desde octubre
    ws1 = wb.active
    ws1.title = "1_SENALES_DESDE_OCTUBRE"
    h1 = [
        "Semana", "Fecha Detección", "Moneda", "Bot / Fuente", "Semáforo Radar",
        "Precio Detección", "Máximo Alcanzado", "Peor Caída", "Precio Actual",
        "Máx. Subida (%)", "Peor Caída (%)", "Var. Actual (%)",
        "Simulación Regla Nueva", "PnL Simulado ($)", "Notas / Tesis IA"
    ]
    ws1.append(h1)
    for idx in range(1, len(h1) + 1):
        c = ws1.cell(row=1, column=idx)
        c.fill = fill_hdr
        c.font = font_hdr
        c.alignment = Alignment(horizontal="center")

    for r_idx, f in enumerate(filas, start=2):
        ws1.append([
            f["semana"], f["fecha"], f["moneda"], f["origen"], f["semaforo"],
            f["precio_ini"], f["precio_max"], f["precio_min"], f["precio_ult"],
            f["max_subida_pct"], f["max_caida_pct"], f["var_actual_pct"],
            f["resultado_sim"], f["pnl_sim_usd"], f["motivo"]
        ])
        c_sub = ws1.cell(row=r_idx, column=10)
        c_pnl = ws1.cell(row=r_idx, column=14)
        if f["max_subida_pct"] >= TP1_PCT:
            c_sub.fill = fill_verde
        if f["pnl_sim_usd"] > 0:
            c_pnl.fill = fill_verde
        elif f["pnl_sim_usd"] < 0:
            c_pnl.fill = fill_rojo

    # Pestaña 2: Resumen por Semana (Octubre -> Noviembre)
    ws2 = wb.create_sheet(title="2_RESUMEN_POR_SEMANA")
    h2 = ["Semana", "Señales Detectadas", "Llegaron a +4.8% (TP1)", "Tasa Éxito TP1 (%)", "PnL Simulado Neto ($)"]
    ws2.append(h2)
    for idx in range(1, len(h2) + 1):
        c = ws2.cell(row=1, column=idx)
        c.fill = fill_hdr
        c.font = font_hdr
        c.alignment = Alignment(horizontal="center")

    por_sem = {}
    for f in filas:
        s = f["semana"]
        por_sem.setdefault(s, {"tot": 0, "tp1": 0, "pnl": 0.0})
        por_sem[s]["tot"] += 1
        if f["toco_tp1"]:
            por_sem[s]["tp1"] += 1
        por_sem[s]["pnl"] += f["pnl_sim_usd"]

    for sem in sorted(por_sem.keys()):
        d = por_sem[sem]
        tasa = round((d["tp1"] / d["tot"]) * 100, 1) if d["tot"] > 0 else 0.0
        ws2.append([sem, d["tot"], d["tp1"], tasa, round(d["pnl"], 2)])

    # Pestaña 3: Ranking Top Subidas Históricas
    ws3 = wb.create_sheet(title="3_TOP_SUBIDAS_OCT_NOV")
    h3 = ["Ranking", "Semana", "Fecha", "Moneda", "Bot / Fuente", "Máx. Subida (%)", "Peor Caída (%)", "Simulación Regla Nueva"]
    ws3.append(h3)
    for idx in range(1, len(h3) + 1):
        c = ws3.cell(row=1, column=idx)
        c.fill = fill_hdr
        c.font = font_hdr
        c.alignment = Alignment(horizontal="center")

    top_filas = sorted(filas, key=lambda x: x["max_subida_pct"], reverse=True)
    for rk, f in enumerate(top_filas, start=1):
        ws3.append([rk, f["semana"], f["fecha"], f["moneda"], f["origen"], f["max_subida_pct"], f["max_caida_pct"], f["resultado_sim"]])

    for sh in (ws1, ws2, ws3):
        for col in sh.columns:
            max_l = max(len(str(c.value or "")) for c in col)
            sh.column_dimensions[col[0].column_letter].width = min(max_l + 4, 44)

    wb.save(ARCHIVO_EXCEL_HISTORICO)

def enviar_excel_telegram(total_senales, total_tp1, pnl_total):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID or not os.path.exists(ARCHIVO_EXCEL_HISTORICO):
        print("⚠️ Sin credenciales Telegram o Excel no encontrado.")
        return
    tasa = round((total_tp1 / total_senales) * 100, 1) if total_senales > 0 else 0.0
    caption = (
        f"🗄️ <b>RESCATE HISTÓRICO COMPLETO (OCTUBRE - NOVIEMBRE 2026)</b>\n"
        f"• <b>Señales rescatadas de Git:</b> <code>{total_senales}</code>\n"
        f"• <b>Alcanzaron TP1 (+{TP1_PCT}%):</b> <code>{total_tp1}</code> (<b>{tasa}%</b>)\n"
        f"• <b>Balance Simulado Regla Nueva:</b> <b>${pnl_total:+,.2f} USD</b>\n"
        f"📎 Archivo adjunto: <code>{ARCHIVO_EXCEL_HISTORICO}</code>"
    )
    url = f"{TELEGRAM_API_BASE}{TELEGRAM_BOT_TOKEN}/sendDocument"
    data = {"chat_id": TELEGRAM_CHAT_ID, "caption": caption, "parse_mode": "HTML"}
    if TELEGRAM_TOPIC_ID.isdigit():
        data["message_thread_id"] = int(TELEGRAM_TOPIC_ID)
    with open(ARCHIVO_EXCEL_HISTORICO, "rb") as f:
        r = requests.post(url, data=data, files={"document": f}, timeout=30).json()
        if not r.get("ok") and "thread not found" in str(r.get("description", "")).lower():
            data.pop("message_thread_id", None)
            f.seek(0)
            requests.post(url, data=data, files={"document": f}, timeout=30)

if __name__ == "__main__":
    print("🔍 Reconstruyendo historial completo de todos los bots desde octubre 2026...")
    eventos = reconstruir_historial_git()
    print(f"✅ Señales únicas encontradas: {len(eventos)}")

    ses = requests.Session()
    ses.headers.update({"User-Agent": "Mozilla/5.0"})
    resultados = []

    for idx, ev in enumerate(eventos, start=1):
        klines = consultar_velas_historicas(ses, ev["symbol"], ev["dt_deteccion"])
        if klines:
            res = simular_desempeno_historico(ev, klines)
            resultados.append(res)
        time.sleep(0.08)

    generar_excel_historico(resultados)
    tot_tp1 = sum(1 for r in resultados if r["toco_tp1"])
    pnl_tot = sum(r["pnl_sim_usd"] for r in resultados)
    enviar_excel_telegram(len(resultados), tot_tp1, pnl_tot)
    print(f"🏁 Listo: {len(resultados)} señales volcadas a {ARCHIVO_EXCEL_HISTORICO}")
