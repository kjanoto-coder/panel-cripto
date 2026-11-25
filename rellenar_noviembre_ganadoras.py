import os, json, subprocess, time, html, requests
from datetime import datetime, date, timezone, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

TZ_ART = timezone(timedelta(hours=-3))
TELEGRAM_BOT_TOKEN = (os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("TELEGRAM_TOKEN") or "").strip()
TELEGRAM_CHAT_ID = (os.getenv("TELEGRAM_CHAT_ID") or os.getenv("CHAT_ID") or "").strip()
TELEGRAM_TOPIC_ID = (os.getenv("TOPIC_ID_GANADORAS") or os.getenv("TOPIC_ID_SEMANAL") or "").strip()

TELEGRAM_API_BASE = "https://" + "api.telegram.org/bot"
BINANCE_API_BASES = [
    "https://" + "api.binance.com",
    "https://" + "data-api.binance.vision"
]

ARCHIVO_SALIDA = "AUDITORIA_VERDE_GANADORAS.xlsx"
ANIO_OBJETIVO = 2026
MES_OBJETIVO = 11
DIAS_NOMBRE_ES = ["LUNES", "MARTES", "MIERCOLES", "JUEVES", "VIERNES", "SABADO", "DOMINGO"]

def ejecutar_git(args):
    try:
        res = subprocess.run(["git"] + args, capture_output=True, text=True, encoding="utf-8", errors="ignore")
        if res.returncode == 0:
            return res.stdout
    except Exception:
        pass
    return ""

def obtener_radares_noviembre_git():
    """
    Reconstruye qué monedas estaban detectadas por los bots en cada fecha de noviembre 2026
    leyendo todos los commits del repositorio.
    """
    log_out = ejecutar_git(["log", "--since=2026-10-25", "--reverse", "--format=%H|%ci", "--", "*.json"])
    commits = []
    for linea in log_out.splitlines():
        if "|" in linea:
            h, f_str = linea.strip().split("|", 1)
            try:
                dt = datetime.fromisoformat(f_str.strip()).astimezone(TZ_ART)
            except Exception:
                continue
            commits.append((h.strip(), dt))

    archivos_ignorar = {"package.json", "package-lock.json", "tsconfig.json", "plan_semanal.json"}
    radar_por_fecha = {}   # "2026-11-05" -> set(["ACE", "ATM", ...])
    detalle_senales = {}   # (fecha_str, base) -> dict con info

    for commit_hash, dt_commit in commits:
        fecha_iso = dt_commit.strftime("%Y-%m-%d")
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
            if not isinstance(data, dict):
                continue

            grupos = [data]
            for clave in ("graduadas_pre_explosion", "posta", "registro_verdes", "monedas", "activos"):
                if isinstance(data.get(clave), dict):
                    grupos.append(data[clave])

            for grp in grupos:
                for k, v in grp.items():
                    if isinstance(k, str) and k.endswith("USDT") and isinstance(v, dict):
                        base = k[:-4]
                        if base.endswith(("UP", "DOWN", "BULL", "BEAR")):
                            continue
                        radar_por_fecha.setdefault(fecha_iso, set()).add(base)
                        if dt_commit.year == ANIO_OBJETIVO and dt_commit.month == MES_OBJETIVO:
                            clave_det = (fecha_iso, base)
                            if clave_det not in detalle_senales:
                                p_ref = float(v.get("precio_ref") or v.get("precio_entrada") or v.get("precio") or 0.0)
                                semaforo = str(v.get("semaforo") or v.get("estado") or "DETECTADA").upper()
                                motivo = str(v.get("razon_ia") or v.get("analisis_ia") or v.get("motivo") or v.get("razon") or "")
                                detalle_senales[clave_det] = {
                                    "fecha": dt_commit.strftime("%Y-%m-%d %H:%M"),
                                    "fecha_iso": fecha_iso,
                                    "moneda": base,
                                    "symbol": k,
                                    "fuente": os.path.basename(ruta),
                                    "semaforo": semaforo,
                                    "precio_ref": p_ref,
                                    "motivo": motivo[:140]
                                }

    return radar_por_fecha, list(detalle_senales.values())

def obtener_pares_liquidos_binance():
    s = requests.Session()
    s.headers.update({"User-Agent": "Mozilla/5.0"})
    for base_url in BINANCE_API_BASES:
        try:
            r = s.get(f"{base_url}/api/v3/ticker/24hr", timeout=15)
            if r.status_code == 200 and isinstance(r.json(), list):
                pares = []
                for t in r.json():
                    sym = t.get("symbol", "")
                    if not sym.endswith("USDT"):
                        continue
                    base = sym[:-4]
                    if base.endswith(("UP", "DOWN", "BULL", "BEAR")):
                        continue
                    try:
                        vol = float(t.get("quoteVolume", 0))
                        if vol >= 350_000:
                            pares.append(sym)
                    except Exception:
                        continue
                if pares:
                    return pares
        except Exception:
            continue
    return []

def descargar_velas_mes_par(symbol, start_ms, end_ms):
    for base_url in BINANCE_API_BASES:
        try:
            r = requests.get(
                f"{base_url}/api/v3/klines",
                params={"symbol": symbol, "interval": "1d", "startTime": start_ms, "endTime": end_ms, "limit": 35},
                timeout=8
            )
            if r.status_code == 200 and isinstance(r.json(), list):
                return symbol, r.json()
        except Exception:
            continue
    return symbol, []

def construir_datos_diarios_noviembre(pares, radar_por_fecha):
    """
    Descarga en paralelo las velas diarias de noviembre 2026 y arma el ranking diario
    con Base 0% (apertura), $ Actual (cierre) y % subida.
    """
    dt_ini = datetime(ANIO_OBJETIVO, MES_OBJETIVO, 1, 0, 0, tzinfo=timezone.utc)
    dt_fin = datetime(ANIO_OBJETIVO, MES_OBJETIVO, 25, 23, 59, tzinfo=timezone.utc)
    start_ms = int(dt_ini.timestamp() * 1000)
    end_ms = int(dt_fin.timestamp() * 1000)

    por_dia = {d: [] for d in range(1, 31)}
    velas_por_sym = {}

    with ThreadPoolExecutor(max_workers=12) as pool:
        futuros = [pool.submit(descargar_velas_mes_par, sym, start_ms, end_ms) for sym in pares]
        for fut in as_completed(futuros):
            sym, klines = fut.result()
            if not klines:
                continue
            velas_por_sym[sym] = klines
            base = sym[:-4]
            for k in klines:
                dt_k = datetime.fromtimestamp(int(k[0]) / 1000.0, tz=timezone.utc)
                if dt_k.year != ANIO_OBJETIVO or dt_k.month != MES_OBJETIVO:
                    continue
                dia_num = dt_k.day
                p_open = float(k[1])
                p_close = float(k[4])
                if p_open <= 0:
                    continue
                pct = ((p_close - p_open) / p_open) * 100.0
                if pct > 0.5:
                    fecha_iso = f"{ANIO_OBJETIVO}-{MES_OBJETIVO:02d}-{dia_num:02d}"
                    # Acumula monedas detectadas hasta esa fecha (ventana de 3 días)
                    detectadas_ventana = set()
                    for delta_d in range(0, 4):
                        d_prev = date(ANIO_OBJETIVO, MES_OBJETIVO, dia_num) - timedelta(days=delta_d)
                        detectadas_ventana |= radar_por_fecha.get(d_prev.strftime("%Y-%m-%d"), set())

                    es_acierto = base in detectadas_ventana
                    por_dia[dia_num].append({
                        "nombre": base,
                        "base_0": p_open,
                        "actual": p_close,
                        "pct_subida": round(pct, 2),
                        "acierto": es_acierto
                    })

    for d in por_dia:
        por_dia[d].sort(key=lambda x: x["pct_subida"], reverse=True)
        por_dia[d] = por_dia[d][:20]

    return por_dia, velas_por_sym

def leer_dias_existentes_excel(ruta_excel):
    """
    Si AUDITORIA_VERDE_GANADORAS.xlsx ya existe, extrae los bloques de días ya cargados
    (ej. días 23 y 24) para conservarlos idénticos sin modificarlos.
    """
    dias_existentes = {}
    if not os.path.exists(ruta_excel):
        return dias_existentes
    try:
        wb = openpyxl.load_workbook(ruta_excel, data_only=True)
        if "NOVIEMBRE 2026" not in wb.sheetnames:
            return dias_existentes
        ws = wb["NOVIEMBRE 2026"]
        col = 1
        while col <= ws.max_column:
            val_dia = ws.cell(row=3, column=col).value
            if isinstance(val_dia, (int, float)) and 1 <= int(val_dia) <= 31:
                d_num = int(val_dia)
                filas_dia = []
                for r in range(5, 30):
                    nom = ws.cell(row=r, column=col + 1).value
                    if not nom:
                        continue
                    b0 = ws.cell(row=r, column=col + 2).value
                    act = ws.cell(row=r, column=col + 3).value
                    sub = ws.cell(row=r, column=col + 4).value
                    fill_rgb = str(ws.cell(row=r, column=col + 1).fill.start_color.rgb or "")
                    es_verde = ("D1FAE5" in fill_rgb.upper() or "E2EFDA" in fill_rgb.upper() or "C6EFCE" in fill_rgb.upper() or bool(ws.cell(row=r, column=col + 1).font.bold))
                    pct_num = float(sub) * 100.0 if isinstance(sub, (int, float)) and abs(float(sub)) < 1.5 else float(sub or 0.0)
                    filas_dia.append({
                        "nombre": str(nom).strip(),
                        "base_0": float(b0 or 0.0),
                        "actual": float(act or 0.0),
                        "pct_subida": round(pct_num, 2),
                        "acierto": es_verde
                    })
                if filas_dia:
                    dias_existentes[d_num] = filas_dia
                col += 6
            else:
                col += 1
    except Exception as e:
        print(f"⚠️ No se pudieron leer días previos del Excel: {e}")
    return dias_existentes

def generar_excel_noviembre_completo(por_dia, dias_existentes, detalle_senales, velas_por_sym):
    # Carga el workbook existente para conservar PARAMETROS_RADAR y otras hojas
    if os.path.exists(ARCHIVO_SALIDA):
        wb = openpyxl.load_workbook(ARCHIVO_SALIDA)
        if "NOVIEMBRE 2026" in wb.sheetnames:
            idx_hoja = wb.sheetnames.index("NOVIEMBRE 2026")
            del wb["NOVIEMBRE 2026"]
            ws = wb.create_sheet(title="NOVIEMBRE 2026", index=idx_hoja)
        else:
            ws = wb.create_sheet(title="NOVIEMBRE 2026", index=0)
    else:
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "NOVIEMBRE 2026"

    ws.views.sheetView[0].showGridLines = True

    fill_titulo = PatternFill(start_color="0B132B", end_color="0B132B", fill_type="solid")
    font_titulo = Font(name="Arial", size=12, bold=True, color="FFFFFF")

    fill_dia = PatternFill(start_color="D9E1F2", end_color="D9E1F2", fill_type="solid")
    font_dia = Font(name="Arial", size=10, bold=True, color="0B132B")

    fill_subhdr = PatternFill(start_color="0B132B", end_color="0B132B", fill_type="solid")
    font_subhdr = Font(name="Arial", size=9, bold=True, color="FFFFFF")

    fill_acierto = PatternFill(start_color="D1FAE5", end_color="D1FAE5", fill_type="solid")
    font_acierto = Font(name="Arial", size=9, bold=True, color="000000")
    font_normal = Font(name="Arial", size=9, bold=False, color="000000")

    borde_fino = Side(border_style="thin", color="D1D5DB")
    border_celda = Border(left=borde_fino, right=borde_fino, top=borde_fino, bottom=borde_fino)

    # Banner superior
    ultima_col = 30 * 6 - 1
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=ultima_col)
    c_tit = ws.cell(row=1, column=1, value="MONEDAS GANADORAS • NOVIEMBRE 2026 (CIERRES DIARIOS: BASE 0% VS ACTUAL + RESUMEN SEMANAL)")
    c_tit.fill = fill_titulo
    c_tit.font = font_titulo
    c_tit.alignment = Alignment(horizontal="left", vertical="center")
    ws.row_dimensions[1].height = 26

    # Días 1 al 30 de noviembre 2026
    for dia_num in range(1, 31):
        col_ini = (dia_num - 1) * 6 + 1
        fecha_d = date(ANIO_OBJETIVO, MES_OBJETIVO, dia_num)
        nombre_dia = DIAS_NOMBRE_ES[fecha_d.weekday()]

        # Fila 3: Número de día + NOVIEMBRE - DIA
        c_num = ws.cell(row=3, column=col_ini, value=dia_num)
        c_num.fill = fill_dia
        c_num.font = font_dia
        c_num.alignment = Alignment(horizontal="center", vertical="center")
        c_num.border = border_celda

        ws.merge_cells(start_row=3, start_column=col_ini + 1, end_row=3, end_column=col_ini + 4)
        c_nom_dia = ws.cell(row=3, column=col_ini + 1, value=f"NOVIEMBRE - {nombre_dia}")
        c_nom_dia.fill = fill_dia
        c_nom_dia.font = font_dia
        c_nom_dia.alignment = Alignment(horizontal="left", vertical="center")
        for cc in range(col_ini + 1, col_ini + 5):
            ws.cell(row=3, column=cc).fill = fill_dia
            ws.cell(row=3, column=cc).border = border_celda

        # Fila 4: Encabezados de columnas
        subheaders = ["N°", "NOMBRE", "Base 0%", "$ Actual", "% subida"]
        for idx_sh, txt_sh in enumerate(subheaders):
            c_sh = ws.cell(row=4, column=col_ini + idx_sh, value=txt_sh)
            c_sh.fill = fill_subhdr
            c_sh.font = font_subhdr
            c_sh.alignment = Alignment(horizontal="center", vertical="center")
            c_sh.border = border_celda

        # Usa los días ya existentes en Excel si están (ej. 23 y 24), si no usa los reconstruidos (1 al 22)
        filas_dia = dias_existentes.get(dia_num) if dia_num in dias_existentes else (por_dia.get(dia_num, []) if dia_num <= 24 else [])

        for idx_f, item in enumerate(filas_dia, start=1):
            r = 4 + idx_f
            es_verde = bool(item.get("acierto", False))
            f_usar = font_acierto if es_verde else font_normal

            vals = [idx_f, item["nombre"], item["base_0"], item["actual"], item["pct_subida"] / 100.0]
            for idx_c, v in enumerate(vals):
                cel = ws.cell(row=r, column=col_ini + idx_c, value=v)
                cel.font = f_usar
                cel.border = border_celda
                if es_verde:
                    cel.fill = fill_acierto
                if idx_c == 0:
                    cel.alignment = Alignment(horizontal="center")
                elif idx_c == 1:
                    cel.alignment = Alignment(horizontal="left")
                elif idx_c in (2, 3):
                    cel.alignment = Alignment(horizontal="right")
                    cel.number_format = "0.00000000" if float(v) < 0.01 else ("0.0000" if float(v) < 10 else "0.00")
                elif idx_c == 4:
                    cel.alignment = Alignment(horizontal="right")
                    cel.number_format = "0.0%"

        # Anchos de columna del bloque + separador
        ws.column_dimensions[get_column_letter(col_ini)].width = 4.5
        ws.column_dimensions[get_column_letter(col_ini + 1)].width = 12.5
        ws.column_dimensions[get_column_letter(col_ini + 2)].width = 12.5
        ws.column_dimensions[get_column_letter(col_ini + 3)].width = 12.5
        ws.column_dimensions[get_column_letter(col_ini + 4)].width = 10.0
        if dia_num < 30:
            ws.column_dimensions[get_column_letter(col_ini + 5)].width = 2.5

    # Actualiza o crea DETALLE_OPERACIONES con todas las señales de noviembre
    if "DETALLE_OPERACIONES" in wb.sheetnames:
        del wb["DETALLE_OPERACIONES"]
    ws_det = wb.create_sheet(title="DETALLE_OPERACIONES")
    h_det = ["Fecha Detección", "Moneda", "Fuente Bot", "Semáforo", "Precio Referencia", "Máx. Mes Noviembre", "Max Subida (%)", "Notas IA"]
    ws_det.append(h_det)
    for col_i in range(1, len(h_det) + 1):
        c = ws_det.cell(row=1, column=col_i)
        c.fill = fill_subhdr
        c.font = font_subhdr
        c.alignment = Alignment(horizontal="center")

    detalle_senales.sort(key=lambda x: x["fecha"])
    for r_i, det in enumerate(detalle_senales, start=2):
        sym = det["symbol"]
        klines = velas_por_sym.get(sym, [])
        p_ref = det["precio_ref"]
        if p_ref <= 0 and klines:
            p_ref = float(klines[0][1])
        p_max = p_ref
        for k in klines:
            dt_k = datetime.fromtimestamp(int(k[0]) / 1000.0, tz=timezone.utc).strftime("%Y-%m-%d")
            if dt_k >= det["fecha_iso"] and float(k[2]) > p_max:
                p_max = float(k[2])
        sub_pct = round(((p_max - p_ref) / p_ref) * 100.0, 2) if p_ref > 0 else 0.0
        ws_det.append([det["fecha"], det["moneda"], det["fuente"], det["semaforo"], p_ref, p_max, sub_pct, det["motivo"]])
        if sub_pct >= 5.0:
            ws_det.cell(row=r_i, column=7).fill = fill_acierto

    for col in ws_det.columns:
        max_l = max(len(str(c.value or "")) for c in col)
        ws_det.column_dimensions[col[0].column_letter].width = min(max_l + 4, 42)

    wb.save(ARCHIVO_SALIDA)

def enviar_excel_telegram(total_aciertos_mes):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID or not os.path.exists(ARCHIVO_SALIDA):
        print("⚠️ Sin credenciales Telegram o archivo no encontrado.")
        return
    caption = (
        f"📊 <b>NOVIEMBRE 2026 COMPLETO (DÍAS 1 AL 24) • MONEDAS GANADORAS</b>\n"
        f"✅ <b>Aciertos detectados por el radar en el mes:</b> <code>{total_aciertos_mes}</code>\n"
        f"📎 Se rellenaron los días <b>1 al 22</b> con el historial de Git + Binance Spot y se conservaron intactos los días <b>23 y 24</b> (<code>{ARCHIVO_SALIDA}</code>)."
    )
    url = f"{TELEGRAM_API_BASE}{TELEGRAM_BOT_TOKEN}/sendDocument"
    data = {"chat_id": TELEGRAM_CHAT_ID, "caption": caption, "parse_mode": "HTML"}
    if TELEGRAM_TOPIC_ID.isdigit():
        data["message_thread_id"] = int(TELEGRAM_TOPIC_ID)
    with open(ARCHIVO_SALIDA, "rb") as f:
        r = requests.post(url, data=data, files={"document": f}, timeout=30).json()
        if not r.get("ok") and "thread not found" in str(r.get("description", "")).lower():
            data.pop("message_thread_id", None)
            f.seek(0)
            requests.post(url, data=data, files={"document": f}, timeout=30)

if __name__ == "__main__":
    print("🔍 Reconstruyendo días 1 al 22 de noviembre 2026 para AUDITORIA_VERDE_GANADORAS.xlsx...")
    dias_previos = leer_dias_existentes_excel(ARCHIVO_SALIDA)
    print(f"📂 Días ya existentes en Excel conservados: {sorted(dias_previos.keys())}")

    radar_fechas, detalle_nov = obtener_radares_noviembre_git()
    pares = obtener_pares_liquidos_binance()
    print(f"📡 Pares líquidos analizados: {len(pares)} | Señales de noviembre en Git: {len(detalle_nov)}")

    por_dia, velas_sym = construir_datos_diarios_noviembre(pares, radar_fechas)
    generar_excel_noviembre_completo(por_dia, dias_previos, detalle_nov, velas_sym)

    total_verdes = 0
    for d in range(1, 25):
        lista_d = dias_previos.get(d) if d in dias_previos else por_dia.get(d, [])
        total_verdes += sum(1 for x in lista_d if x.get("acierto"))

    enviar_excel_telegram(total_verdes)
    print(f"🏁 Listo: {ARCHIVO_SALIDA} actualizado con noviembre completo (1 al 24) y {total_verdes} aciertos marcados en verde.")
