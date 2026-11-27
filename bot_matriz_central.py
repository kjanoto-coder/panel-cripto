import os, glob, json, html, hashlib, requests
from datetime import datetime, timezone, timedelta
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment

TZ_ART = timezone(timedelta(hours=-3))
TELEGRAM_BOT_TOKEN = (os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("TELEGRAM_TOKEN") or "").strip()
TELEGRAM_CHAT_ID = (os.getenv("TELEGRAM_CHAT_ID") or os.getenv("CHAT_ID") or "").strip()
TOPIC_ID_MATRIZ_ENV = (os.getenv("TOPIC_ID_MATRIZ") or "").strip()

TELEGRAM_API_BASE = "https://" + "api.telegram.org/bot"
BINANCE_API_BASES = [
    "https://" + "api.binance.com",
    "https://" + "data-api.binance.vision"
]

EXCEL_MATRIZ_CENTRAL_FILE = "MATRIZ_CENTRAL_ECOSISTEMA.xlsx"
MATRIZ_CONFIG_FILE = "matriz_topic_config.json"


def ahora_art():
    return datetime.now(TZ_ART)


def cargar_json_seguro(ruta):
    if not os.path.exists(ruta):
        return {}
    try:
        with open(ruta, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def guardar_json_seguro(ruta, data):
    try:
        with open(ruta, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"⚠️ Error guardando {ruta}: {e}")


def obtener_precios_vivos_binance():
    mapa = {}
    for base_url in BINANCE_API_BASES:
        try:
            r = requests.get(f"{base_url}/api/v3/ticker/24hr", timeout=12)
            if r.status_code == 200:
                for t in r.json():
                    sym = t.get("symbol", "")
                    if sym.endswith("USDT"):
                        mapa[sym] = {
                            "precio": float(t.get("lastPrice", 0.0)),
                            "cambio_24h": float(t.get("priceChangePercent", 0.0)),
                            "vol_24h": float(t.get("quoteVolume", 0.0))
                        }
                if mapa:
                    return mapa
        except Exception:
            continue
    return mapa


def normalizar_symbol(raw):
    if not raw:
        return ""
    s = str(raw).strip().upper().replace("/USDT", "").replace("-USDT", "").replace("USDT", "")
    if not s or len(s) > 14 or not s.isalnum():
        return ""
    return f"{s}USDT"


def buscar_numero(d, claves):
    if not isinstance(d, dict):
        return None
    for k in claves:
        if k in d and d[k] is not None:
            try:
                return float(str(d[k]).replace("%", "").replace("+", "").replace("$", "").replace(",", "").strip())
            except Exception:
                pass
    for k, v in d.items():
        kl = str(k).lower()
        if any(c.lower() in kl for c in claves) and v is not None:
            try:
                return float(str(v).replace("%", "").replace("+", "").replace("$", "").replace(",", "").strip())
            except Exception:
                pass
    return None


def buscar_texto(d, claves):
    if not isinstance(d, dict):
        return ""
    for k in claves:
        if k in d and d[k] is not None and str(d[k]).strip():
            return str(d[k]).strip()
    for k, v in d.items():
        kl = str(k).lower()
        if any(c.lower() in kl for c in claves) and v is not None and str(v).strip():
            return str(v).strip()
    return ""


def parsear_fecha_flexible(fecha_str):
    if not fecha_str:
        return None
    s = str(fecha_str).strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d", "%d/%m/%Y %H:%M", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            dt = datetime.strptime(s[:len(fmt) + 2].strip(), fmt)
            return dt.replace(tzinfo=TZ_ART)
        except Exception:
            continue
    return None


def es_de_hoy_o_24h(fecha_str, ahora_dt):
    if not fecha_str:
        return False, False
    s = str(fecha_str).strip()
    hoy_iso = ahora_dt.strftime("%Y-%m-%d")
    dd_mm = ahora_dt.strftime("%d/%m")
    es_hoy = (hoy_iso in s) or (dd_mm in s)
    dt_p = parsear_fecha_flexible(s)
    es_24h = es_hoy or (dt_p is not None and (ahora_dt - dt_p).total_seconds() <= 86400)
    return es_hoy, es_24h


def descubrir_archivos_ecosistema():
    """Escanea todos los Excel y JSON de Etapas 1, 2, 3 y 4 en el repo (sin Perdedoras)."""
    todos_xlsx = sorted(glob.glob("*.xlsx"))
    todos_json = sorted(glob.glob("*.json"))

    grupos_xlsx = {"E1": [], "E2": [], "E3": [], "E4": []}
    for f in todos_xlsx:
        fu = f.upper()
        if f == EXCEL_MATRIZ_CENTRAL_FILE or "PERDEDORA" in fu:
            continue
        if any(k in fu for k in ("TACTICO", "CAZADOR", "PERLA", "ETAPA_1", "ETAPA1")):
            grupos_xlsx["E1"].append(f)
        elif any(k in fu for k in ("PRE_EXPLOSION", "PREEXPLOSION", "EXPLOSION", "ETAPA_2", "ETAPA2")):
            grupos_xlsx["E2"].append(f)
        elif any(k in fu for k in ("GANADORA", "VERDE", "ETAPA_3", "ETAPA3")):
            grupos_xlsx["E3"].append(f)
        elif any(k in fu for k in ("SEMANAL", "GLOBAL", "AUDITORIA")):
            grupos_xlsx["E4"].append(f)

    grupos_json = {"E1": [], "E2": [], "E3": [], "E4": []}
    for f in todos_json:
        fu = f.upper()
        if "PERDEDORA" in fu or "CONFIG" in fu or f in ("package.json", "tsconfig.json"):
            continue
        if any(k in fu for k in ("TACTICO", "PERLA", "CAZADOR")):
            grupos_json["E1"].append(f)
        if any(k in fu for k in ("PRE_EXPLOSION", "PERLA")):
            grupos_json["E2"].append(f)
        if any(k in fu for k in ("GANADORA", "VERDE")):
            grupos_json["E3"].append(f)
        if any(k in fu for k in ("PLAN_SEMANAL", "CEREBRO")):
            grupos_json["E4"].append(f)

    return grupos_xlsx, grupos_json


def extraer_registros_excel(lista_archivos):
    """Lee todas las pestañas de una lista de Excel y extrae tanto hojas crudas como registros por moneda."""
    hojas_crudas = []
    registros_por_moneda = {}

    for ruta in lista_archivos:
        if not os.path.exists(ruta):
            continue
        try:
            wb = openpyxl.load_workbook(ruta, data_only=True)
            for sname in wb.sheetnames:
                ws = wb[sname]
                raw_rows = list(ws.iter_rows(values_only=True))
                clean_rows = [list(r) for r in raw_rows if any(c is not None and str(c).strip() != "" for c in r)]
                if not clean_rows:
                    continue

                idx_hdr = 0
                if len(clean_rows) > 1:
                    nv0 = sum(1 for c in clean_rows[0] if c is not None and str(c).strip() != "")
                    nv1 = sum(1 for c in clean_rows[1] if c is not None and str(c).strip() != "")
                    if nv0 <= 2 and nv1 >= 3:
                        idx_hdr = 1

                headers = [str(h or f"Col_{i+1}").strip() for i, h in enumerate(clean_rows[idx_hdr])]
                rows = clean_rows[idx_hdr + 1:]
                hojas_crudas.append((ruta, sname, headers, rows))

                col_sym = None
                for i_c, h_txt in enumerate(headers):
                    hu = h_txt.upper()
                    if any(k in hu for k in ("MONEDA", "SYMBOL", "PAR", "TICKER", "ACTIVO", "TOKEN")):
                        col_sym = i_c
                        break

                if col_sym is not None:
                    for r in rows:
                        if col_sym >= len(r):
                            continue
                        sym = normalizar_symbol(r[col_sym])
                        if not sym:
                            continue
                        item = registros_por_moneda.setdefault(sym, {"_fuentes": set()})
                        item["_fuentes"].add(f"{ruta}:{sname}")
                        for i_c, h_txt in enumerate(headers):
                            if i_c < len(r) and r[i_c] is not None and str(r[i_c]).strip() != "":
                                item[h_txt] = r[i_c]
        except Exception as e:
            print(f"⚠️ Error leyendo Excel {ruta}: {e}")

    return hojas_crudas, registros_por_moneda


def extraer_registros_json(lista_archivos, etapa_tag):
    """Extrae todos los registros históricos por moneda desde los JSON de cada etapa."""
    registros = {}
    resumen_ia = ""

    def _walk(obj, contexto_clave=""):
        nonlocal resumen_ia
        if isinstance(obj, dict):
            if not resumen_ia:
                for rk in ("resumen_ia", "diagnostico_general", "veredicto", "resumen", "conclusion", "analisis_global"):
                    if isinstance(obj.get(rk), str) and obj[rk].strip():
                        resumen_ia = obj[rk].strip()[:160]
                        break
            for k, v in obj.items():
                kl = str(k).lower()
                # En historial_perlas.json separar Etapa 1 (posta/descartadas) de Etapa 2 (graduadas_pre_explosion)
                if etapa_tag == "E1" and "graduada" in kl:
                    continue
                if etapa_tag == "E2" and kl in ("posta", "descartadas", "descartadas_tactico"):
                    continue

                sym = normalizar_symbol(k)
                if sym and isinstance(v, dict):
                    dst = registros.setdefault(sym, {})
                    dst.update(v)
                    if contexto_clave and "_subgrupo" not in dst:
                        dst["_subgrupo"] = contexto_clave
                else:
                    _walk(v, k)
        elif isinstance(obj, list):
            for it in obj:
                if isinstance(it, dict):
                    raw_s = it.get("symbol") or it.get("moneda") or it.get("par") or it.get("base")
                    sym = normalizar_symbol(raw_s)
                    if sym:
                        dst = registros.setdefault(sym, {})
                        dst.update(it)

    for ruta in lista_archivos:
        data = cargar_json_seguro(ruta)
        if data:
            _walk(data, ruta)

    return registros, resumen_ia


def construir_tabla_etapa(etapa_num, reg_json, reg_xls, mapa_mkt):
    """Combina JSON + Excel de una etapa en una tabla histórica unificada y ordenada."""
    syms = sorted(set(reg_json.keys()) | set(reg_xls.keys()))
    filas = []
    por_moneda = {}

    for sym in syms:
        dj = reg_json.get(sym, {})
        dx = reg_xls.get(sym, {})
        mkt = mapa_mkt.get(sym, {})

        fecha = (
            buscar_texto(dj, ["fecha_deteccion", "fecha_graduacion", "fecha_entrada", "fecha", "timestamp", "creado"])
            or buscar_texto(dx, ["FECHA", "DIA", "DETECCION", "ENTRADA", "TIMESTAMP"])
        )
        p_ini = (
            buscar_numero(dj, ["precio_entrada", "precio_deteccion", "precio_inicial", "precio_base", "precio_graduacion", "entry_price"])
            or buscar_numero(dx, ["PRECIO ENTRADA", "ENTRADA", "INICIAL", "BASE", "PRECIO DETECCION", "PRECIO"])
            or 0.0
        )
        p_vivo = float(mkt.get("precio", 0.0))
        p_max = (
            buscar_numero(dj, ["precio_maximo", "max_precio", "pico", "high"])
            or buscar_numero(dx, ["MAXIMO", "PICO", "HIGH"])
            or max(p_ini, p_vivo)
        )

        pct_max = buscar_numero(dj, ["max_ganancia_pct", "max_subida_pct", "pico_pct"]) or buscar_numero(dx, ["MAX SUBIDA", "MAX %", "PICO %"])
        if pct_max is None and p_ini > 0 and p_max > 0:
            pct_max = ((p_max - p_ini) / p_ini) * 100.0

        pct_act = buscar_numero(dj, ["ganancia_pct", "rendimiento_pct", "variacion_pct", "subida_pct", "retorno_pct"]) or buscar_numero(dx, ["GANANCIA", "RENDIMIENTO", "VARIACION", "SUBIDA %", "ACTUAL %"])
        if pct_act is None:
            if p_ini > 0 and p_vivo > 0:
                pct_act = ((p_vivo - p_ini) / p_ini) * 100.0
            else:
                pct_act = float(mkt.get("cambio_24h", 0.0))

        if pct_max is None:
            pct_max = max(pct_act, 0.0)

        estado = (
            buscar_texto(dj, ["estado", "status", "semaforo", "etapa", "resultado", "clasificacion", "_subgrupo"])
            or buscar_texto(dx, ["ESTADO", "RESULTADO", "SEMAFORO", "ETAPA", "SETUP", "ESTRUCTURA"])
            or "HISTÓRICO"
        )
        diag_ia = (
            buscar_texto(dj, ["diagnostico_ia", "veredicto_ia", "razon_ia", "analisis", "comentario", "motivo", "detalle"])
            or buscar_texto(dx, ["DIAGNOSTICO", "IA", "COMENTARIO", "ANALISIS", "OBSERVACION", "INTERPRETACION", "DETALLE"])
            or ""
        )

        fila = {
            "symbol": sym,
            "moneda": sym[:-4],
            "etapa": f"Etapa {etapa_num}",
            "fecha": fecha,
            "precio_ini": round(p_ini, 6),
            "precio_vivo": round(p_vivo, 6),
            "pct_max": round(float(pct_max), 2),
            "pct_act": round(float(pct_act), 2),
            "chg_24h": round(float(mkt.get("cambio_24h", 0.0)), 2),
            "estado": estado,
            "diag_ia": diag_ia[:220]
        }
        filas.append(fila)
        por_moneda[sym] = fila

    filas.sort(key=lambda x: (x["fecha"], x["pct_max"]), reverse=True)
    return filas, por_moneda


def construir_matriz_unificada():
    ahora_dt = ahora_art()
    ahora_str = ahora_dt.strftime("%Y-%m-%d %H:%M ART")
    hoy_iso = ahora_dt.strftime("%Y-%m-%d")

    mapa_mkt = obtener_precios_vivos_binance()
    grupos_xlsx, grupos_json = descubrir_archivos_ecosistema()

    # Leer Excel y JSON de cada Etapa
    hojas_e1, xls_e1 = extraer_registros_excel(grupos_xlsx["E1"])
    hojas_e2, xls_e2 = extraer_registros_excel(grupos_xlsx["E2"])
    hojas_e3, xls_e3 = extraer_registros_excel(grupos_xlsx["E3"])
    hojas_e4, _ = extraer_registros_excel(grupos_xlsx["E4"])

    json_e1, res_ia_e1 = extraer_registros_json(grupos_json["E1"], "E1")
    json_e2, res_ia_e2 = extraer_registros_json(grupos_json["E2"], "E2")
    json_e3, res_ia_e3 = extraer_registros_json(grupos_json["E3"], "E3")

    filas_e1, map_e1 = construir_tabla_etapa(1, json_e1, xls_e1, mapa_mkt)
    filas_e2, map_e2 = construir_tabla_etapa(2, json_e2, xls_e2, mapa_mkt)
    filas_e3, map_e3 = construir_tabla_etapa(3, json_e3, xls_e3, mapa_mkt)

    plan_sem = cargar_json_seguro("plan_semanal.json")
    cerebro = cargar_json_seguro("cerebro_evolutivo.json")
    posiciones = plan_sem.get("posiciones", []) if isinstance(plan_sem, dict) else []
    cierres = plan_sem.get("historial_cierres", []) if isinstance(plan_sem, dict) else []
    alts_eval = plan_sem.get("alternativas_evaluadas", []) if isinstance(plan_sem, dict) else []

    pos_map = {p["symbol"]: p for p in posiciones if p.get("symbol")}
    alts_map = {a["symbol"]: a for a in alts_eval if a.get("symbol")}

    # --- 1. Resumen Diario e Histórico por Bot (Etapas 1, 2, 3 y 4) ---
    def _contar_fechas(filas_etapa):
        c_hoy, c_24h = 0, 0
        for f in filas_etapa:
            h_f, h24_f = es_de_hoy_o_24h(f["fecha"], ahora_dt)
            if h_f:
                c_hoy += 1
            if h24_f:
                c_24h += 1
        prom_max = round(sum(f["pct_max"] for f in filas_etapa) / max(len(filas_etapa), 1), 2)
        return c_hoy, c_24h, prom_max

    e1_hoy, e1_24h, e1_prom = _contar_fechas(filas_e1)
    e2_hoy, e2_24h, e2_prom = _contar_fechas(filas_e2)
    e3_hoy, e3_24h, e3_prom = _contar_fechas(filas_e3)

    e4_hoy, e4_24h = 0, 0
    for op in list(cierres) + list(posiciones):
        h_f, h24_f = es_de_hoy_o_24h(op.get("fecha_cierre") or op.get("fecha_entrada"), ahora_dt)
        if h_f:
            e4_hoy += 1
        if h24_f:
            e4_24h += 1

    pnl_sem_neto = round(float(plan_sem.get("ganancia_realizada_usd", 0.0)) + sum(float(p.get("pnl_usd", 0.0)) for p in posiciones), 2)

    resumen_bots = [
        {
            "emoji": "🎯",
            "etapa": "Etapa 1 • Cazador Táctico",
            "archivos": ", ".join(grupos_xlsx["E1"]) or "JSON Táctico",
            "hoy": e1_hoy,
            "h24": e1_24h,
            "total_hist": len(filas_e1),
            "metrica": f"Máx Subida Prom: {e1_prom:+.2f}%",
            "diag_ia": res_ia_e1 or f"{len(filas_e1)} monedas auditadas en radar táctico"
        },
        {
            "emoji": "⚡",
            "etapa": "Etapa 2 • Pre-Explosión",
            "archivos": ", ".join(grupos_xlsx["E2"]) or "JSON Pre-Explosión",
            "hoy": e2_hoy,
            "h24": e2_24h,
            "total_hist": len(filas_e2),
            "metrica": f"Máx Subida Prom: {e2_prom:+.2f}%",
            "diag_ia": res_ia_e2 or f"{len(filas_e2)} monedas acumulando en Etapa 2"
        },
        {
            "emoji": "🟢",
            "etapa": "Etapa 3 • Monedas Ganadoras",
            "archivos": ", ".join(grupos_xlsx["E3"]) or "JSON Ganadoras",
            "hoy": e3_hoy,
            "h24": e3_24h,
            "total_hist": len(filas_e3),
            "metrica": f"Máx Subida Prom: {e3_prom:+.2f}%",
            "diag_ia": res_ia_e3 or f"{len(filas_e3)} monedas confirmadas en Etapa 3"
        },
        {
            "emoji": "🏆",
            "etapa": "Etapa 4 • Gestor 3 Traders + Jefe",
            "archivos": ", ".join(grupos_xlsx["E4"]) or "AUDITORIA_SEMANAL_PRUEBA.xlsx",
            "hoy": e4_hoy,
            "h24": e4_24h,
            "total_hist": len(posiciones) + len(cierres),
            "metrica": f"Balance Semanal: ${pnl_sem_neto:+.2f} USD",
            "diag_ia": plan_sem.get("auditoria_ia", {}).get("diagnostico_24h", "Operando 3 Traders independientes")
        }
    ]

    # --- 2. Matriz Cruzada Completa de TODO el Universo (E1 + E2 + E3 + E4) ---
    todos_syms = sorted(set(map_e1.keys()) | set(map_e2.keys()) | set(map_e3.keys()) | set(pos_map.keys()))
    filas_matriz = []

    for sym in todos_syms:
        mkt = mapa_mkt.get(sym, {})
        p_vivo = float(mkt.get("precio", 0.0))
        chg_24h = round(float(mkt.get("cambio_24h", 0.0)), 2)
        vol_24m = round(float(mkt.get("vol_24h", 0.0)) / 1e6, 2)

        d1 = map_e1.get(sym)
        d2 = map_e2.get(sym)
        d3 = map_e3.get(sym)
        conf = sum([1 if d1 else 0, 1 if d2 else 0, 1 if d3 else 0])

        col_e1 = f"✅ {d1['estado']} (Máx {d1['pct_max']:+.1f}%)" if d1 else "—"
        col_e2 = f"⚡ {d2['estado']} (Máx {d2['pct_max']:+.1f}%)" if d2 else "—"
        col_e3 = f"🟢 {d3['estado']} ({d3['pct_act']:+.1f}% / Máx {d3['pct_max']:+.1f}%)" if d3 else "—"

        fechas_coin = [x["fecha"] for x in (d1, d2, d3) if x and x.get("fecha")]
        primera_fecha = min(fechas_coin) if fechas_coin else ""

        alt = alts_map.get(sym)
        mesa_txt = f"{alt.get('asistentes_aprobados', 0)}/6" if alt else "Radar"

        if sym in pos_map:
            po = pos_map[sym]
            tr_nom = po.get("trader_asignado") or po.get("trader") or po.get("escritorio") or "TRADER"
            estado_tr = f"🟢 {tr_nom} ({float(po.get('pnl_pct', 0)):+.2f}%)"
        elif alt and alt.get("consenso_3_de_3"):
            estado_tr = f"🟡 LISTA ({alt.get('trader_propuesto', 'COLA')})"
        else:
            estado_tr = "OBSERVACIÓN"

        notas = []
        for tag, item in [("E1", d1), ("E2", d2), ("E3", d3)]:
            if item and item.get("diag_ia"):
                notas.append(f"[{tag}] {item['diag_ia']}")
        if not notas and alt and alt.get("jefe_veredicto"):
            notas.append(str(alt["jefe_veredicto"]))
        if not notas:
            notas.append(f"Confluencia {conf}/3 • Var 24h: {chg_24h:+.2f}% • Vol: ${vol_24m:.2f}M")

        filas_matriz.append({
            "symbol": sym,
            "moneda": sym[:-4],
            "primera_fecha": primera_fecha,
            "precio_vivo": p_vivo,
            "chg_24h": chg_24h,
            "vol_24m": vol_24m,
            "confluencia": conf,
            "col_e1": col_e1,
            "col_e2": col_e2,
            "col_e3": col_e3,
            "mesa_txt": mesa_txt,
            "estado_tr": estado_tr,
            "notas_ia": " | ".join(notas)[:250]
        })

    filas_matriz.sort(key=lambda x: (x["confluencia"], x["chg_24h"]), reverse=True)

    # --- 3. Construir Libro Excel Completo ---
    wb = openpyxl.Workbook()
    fill_hdr = PatternFill(start_color="0B132B", end_color="0B132B", fill_type="solid")
    font_hdr = Font(color="FFFFFF", bold=True)
    fill_verde = PatternFill(start_color="D1FAE5", end_color="D1FAE5", fill_type="solid")
    fill_amarillo = PatternFill(start_color="FEF3C7", end_color="FEF3C7", fill_type="solid")

    def _estilizar_hdr(ws, cols):
        ws.append(cols)
        for idx in range(1, len(cols) + 1):
            c = ws.cell(row=1, column=idx)
            c.fill = fill_hdr
            c.font = font_hdr
            c.alignment = Alignment(horizontal="center")

    # Hoja 0: Matriz Unificada Completa
    ws0 = wb.active
    ws0.title = "0_MATRIZ_UNIFICADA"
    _estilizar_hdr(ws0, [
        "Moneda", "Primera Detección", "Precio Vivo ($)", "Var 24h (%)", "Vol 24h ($M)",
        "Confluencia", "Etapa 1: Cazador Táctico", "Etapa 2: Pre-Explosión",
        "Etapa 3: Monedas Ganadoras", "Mesa 6 Asistentes", "Estado 3 Traders",
        "Síntesis IA Combinada", "Actualizado"
    ])
    for r_idx, fm in enumerate(filas_matriz, start=2):
        ws0.append([
            fm["moneda"], fm["primera_fecha"], fm["precio_vivo"], fm["chg_24h"], fm["vol_24m"],
            f"{fm['confluencia']}/3 Etapas", fm["col_e1"], fm["col_e2"], fm["col_e3"],
            fm["mesa_txt"], fm["estado_tr"], fm["notas_ia"], ahora_str
        ])
        cel_c = ws0.cell(row=r_idx, column=6)
        if fm["confluencia"] >= 2:
            cel_c.fill = fill_verde
        elif fm["confluencia"] == 1:
            cel_c.fill = fill_amarillo

    # Hoja 1: Resumen Diario e Histórico por Etapa/Bot
    ws1 = wb.create_sheet(title="1_RESUMEN_DIARIO_ETAPAS")
    _estilizar_hdr(ws1, [
        "Fecha", "Etapa / Bot", "Archivos Fuente", "Señales Hoy",
        "Señales 24h", "Total Histórico Monedas", "Métrica Clave", "Diagnóstico IA"
    ])
    for rb in resumen_bots:
        ws1.append([
            hoy_iso, rb["etapa"], rb["archivos"], rb["hoy"],
            rb["h24"], rb["total_hist"], rb["metrica"], rb["diag_ia"]
        ])

    # Hojas 2, 3 y 4: Historial Consolidado Completo de Etapa 1, Etapa 2 y Etapa 3
    for titulo_et, lista_et in [
        ("2_HIST_ETAPA1_TACTICO", filas_e1),
        ("3_HIST_ETAPA2_PRE_EXP", filas_e2),
        ("4_HIST_ETAPA3_GANADORAS", filas_e3)
    ]:
        ws_et = wb.create_sheet(title=titulo_et)
        _estilizar_hdr(ws_et, [
            "Moneda", "Etapa", "Fecha Detección", "Precio Inicial ($)", "Precio Vivo ($)",
            "Máx Subida (%)", "Rendimiento Actual (%)", "Var 24h (%)", "Estado / Setup", "Diagnóstico IA"
        ])
        for item in lista_et:
            ws_et.append([
                item["moneda"], item["etapa"], item["fecha"], item["precio_ini"],
                item["precio_vivo"], item["pct_max"], item["pct_act"],
                item["chg_24h"], item["estado"], item["diag_ia"]
            ])

    # Hoja 5: Gestor 3 Traders Completo
    ws_tr = wb.create_sheet(title="5_GESTOR_3_TRADERS")
    _estilizar_hdr(ws_tr, [
        "Semana", "Trader", "Moneda", "Estado", "Capital ($)", "Entrada ($)",
        "Actual/Cierre ($)", "PnL Neto (%)", "PnL Neto ($)", "Patrón Origen", "Veredicto Jefe"
    ])
    for idx_op, op in enumerate(list(cierres) + list(posiciones), start=1):
        tr_name = op.get("trader_asignado") or op.get("trader") or op.get("escritorio") or f"TRADER_{(idx_op % 3) + 1}"
        ws_tr.append([
            op.get("semana_id", ""), tr_name, op.get("base", ""),
            op.get("estado", ""), round(float(op.get("capital_usd", 0)), 2),
            float(op.get("precio_entrada", 0)), float(op.get("precio_actual", 0)),
            round(float(op.get("pnl_pct", 0)), 2), round(float(op.get("pnl_usd", 0)), 2),
            op.get("patron_detectado", op.get("origen", "")),
            op.get("jefe_veredicto_entrada") or op.get("motivo_cierre", "")
        ])

    # Hojas 6+: Copia íntegra de TODAS las pestañas originales de cada Excel del repo
    titulos_usados = set(wb.sheetnames)
    for tag_et, lista_hojas in [("E1", hojas_e1), ("E2", hojas_e2), ("E3", hojas_e3), ("E4", hojas_e4)]:
        for ruta_orig, sname_orig, hdrs, rws in lista_hojas:
            base_clean = "".join(c if c.isalnum() or c == "_" else "_" for c in f"{tag_et}_{sname_orig}".upper())[:28]
            titulo_final = base_clean
            suf = 2
            while titulo_final in titulos_usados:
                titulo_final = f"{base_clean[:26]}_{suf}"
                suf += 1
            titulos_usados.add(titulo_final)

            ws_raw = wb.create_sheet(title=titulo_final)
            _estilizar_hdr(ws_raw, hdrs)
            for row_d in rws:
                ws_raw.append(row_d)

    for sheet in wb.worksheets:
        for col in sheet.columns:
            max_len = max(len(str(c.value or "")) for c in col)
            sheet.column_dimensions[col[0].column_letter].width = min(max_len + 4, 52)

    wb.save(EXCEL_MATRIZ_CENTRAL_FILE)
    return ahora_str, hoy_iso, resumen_bots, filas_matriz, cerebro, plan_sem, len(wb.sheetnames)


# ==============================================================================
# TELEGRAM: TABLERO FIJADO + EXCEL COMPLETO DE TODAS LAS ETAPAS
# ==============================================================================

def tg_post(metodo, payload=None, files=None):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return {}
    url = f"{TELEGRAM_API_BASE}{TELEGRAM_BOT_TOKEN}/{metodo}"
    try:
        if files:
            r = requests.post(url, data=payload, files=files, timeout=25)
        else:
            r = requests.post(url, json=payload, timeout=20)
        return r.json()
    except Exception as e:
        print(f"⚠️ Error Telegram ({metodo}): {e}")
        return {}


def asegurar_topic_matriz(cfg):
    if TOPIC_ID_MATRIZ_ENV.isdigit():
        return int(TOPIC_ID_MATRIZ_ENV)
    tid = cfg.get("topic_id")
    if isinstance(tid, int) and tid > 0:
        return tid

    res = tg_post("createForumTopic", {
        "chat_id": TELEGRAM_CHAT_ID,
        "name": "Matriz Central"
    })
    nuevo_id = res.get("result", {}).get("message_thread_id")
    if nuevo_id:
        cfg["topic_id"] = int(nuevo_id)
        return int(nuevo_id)
    return None


def actualizar_tema_matriz_telegram(ahora_str, hoy_iso, resumen_bots, filas_matriz, cerebro, plan_sem, total_pestanas):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return

    cfg = cargar_json_seguro(MATRIZ_CONFIG_FILE)
    topic_id = asegurar_topic_matriz(cfg)

    sem_id = plan_sem.get("semana_id", "2026") if isinstance(plan_sem, dict) else "2026"
    total_hoy = sum(rb["hoy"] for rb in resumen_bots)
    total_24h = sum(rb["h24"] for rb in resumen_bots)
    top_confluencia = [f for f in filas_matriz if f["confluencia"] >= 2][:6]
    en_cartera = [f for f in filas_matriz if "🟢 " in f["estado_tr"]]

    msg = (
        f"📊 <b>MATRIZ CENTRAL • HISTORIAL COMPLETO ETAPAS 1, 2, 3 Y 4</b>\n"
        f"🗓️ <b>Fecha:</b> <code>{hoy_iso}</code> (Semana <code>{sem_id}</code>)\n"
        f"📈 <b>Actividad:</b> <b>{total_hoy} hoy</b> | <b>{total_24h} últimas 24h</b>\n"
        f"📁 <b>Excel Maestro:</b> <code>{EXCEL_MATRIZ_CENTRAL_FILE}</code> (<b>{total_pestanas} pestañas completas</b>)\n\n"
        f"📋 <b>RESUMEN POR ETAPA Y BOT</b>\n\n"
    )

    for rb in resumen_bots:
        msg += (
            f"{rb['emoji']} <b>{html.escape(rb['etapa'])}:</b> <b>{rb['hoy']} hoy</b> (<code>{rb['h24']} en 24h</code>)\n"
            f"• Historial acumulado: <b>{rb['total_hist']} monedas</b> | {html.escape(rb['metrica'])}\n"
            f"• <i>IA: {html.escape(rb['diag_ia'][:115])}</i>\n\n"
        )

    msg += "🔥 <b>TOP CONFLUENCIA CRUZADA (2/3 O 3/3 ETAPAS)</b>\n"
    if top_confluencia:
        for tc in top_confluencia:
            msg += (
                f"• <b>{tc['moneda']}</b> (<code>{tc['confluencia']}/3</code> | 24h: <b>{tc['chg_24h']:+.1f}%</b>) ➔ "
                f"{html.escape(tc['estado_tr'])}\n"
            )
    else:
        msg += "• <i>Sin monedas en confluencia múltiple en este corte.</i>\n"

    if en_cartera:
        msg += "\n🖥️ <b>ESCRITORIOS 3 TRADERS EN VIVO</b>\n"
        for ec in en_cartera:
            msg += f"• <b>{ec['moneda']}</b>: {html.escape(ec['estado_tr'])}\n"

    v_ciclo = cerebro.get("version_ciclo", 1) if isinstance(cerebro, dict) else 1
    msg += (
        f"\n🧬 <i>Cerebro Evolutivo v{v_ciclo} • Universo histórico total: {len(filas_matriz)} monedas</i>\n"
        f"<i>Sincronizado con todos los historiales • {ahora_str}</i>"
    )

    msg_id_tablero = cfg.get("tablero_message_id")
    editado_ok = False
    if msg_id_tablero and cfg.get("fecha_tablero") == hoy_iso:
        r_ed = tg_post("editMessageText", {
            "chat_id": TELEGRAM_CHAT_ID,
            "message_id": int(msg_id_tablero),
            "text": msg.strip(),
            "parse_mode": "HTML",
            "disable_web_page_preview": True
        })
        editado_ok = bool(r_ed.get("ok")) or ("message is not modified" in str(r_ed.get("description", "")).lower())

    if not editado_ok:
        send_payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": msg.strip(),
            "parse_mode": "HTML",
            "disable_web_page_preview": True
        }
        if topic_id:
            send_payload["message_thread_id"] = topic_id
        r_sn = tg_post("sendMessage", send_payload)
        if not r_sn.get("ok") and "thread not found" in str(r_sn.get("description", "")).lower():
            send_payload.pop("message_thread_id", None)
            r_sn = tg_post("sendMessage", send_payload)
        nuevo_msg_id = r_sn.get("result", {}).get("message_id")
        if nuevo_msg_id:
            cfg["tablero_message_id"] = int(nuevo_msg_id)
            cfg["fecha_tablero"] = hoy_iso
            tg_post("pinChatMessage", {
                "chat_id": TELEGRAM_CHAT_ID,
                "message_id": int(nuevo_msg_id),
                "disable_notification": True
            })

    hash_datos = hashlib.md5(
        json.dumps([resumen_bots, [(f["moneda"], f["confluencia"], f["col_e1"], f["col_e2"], f["col_e3"], f["estado_tr"]) for f in filas_matriz]], sort_keys=True).encode()
    ).hexdigest()

    hora_actual = ahora_art().hour
    es_manual = (os.getenv("GITHUB_EVENT_NAME") == "workflow_dispatch")
    if cfg.get("ultimo_hash_excel") != hash_datos or cfg.get("ultima_hora_excel") != hora_actual or es_manual:
        doc_data = {
            "chat_id": TELEGRAM_CHAT_ID,
            "caption": (
                f"📎 <b>{EXCEL_MATRIZ_CENTRAL_FILE}</b> ({total_pestanas} Pestañas • Historial Completo)\n"
                f"🔄 Sincronizado: <code>{ahora_str}</code> | 24h: <b>{total_24h}</b> | Universo Total: <b>{len(filas_matriz)} monedas</b>"
            ),
            "parse_mode": "HTML"
        }
        if topic_id:
            doc_data["message_thread_id"] = topic_id
        with open(EXCEL_MATRIZ_CENTRAL_FILE, "rb") as f_xls:
            r_doc = tg_post("sendDocument", payload=doc_data, files={"document": f_xls})
            if not r_doc.get("ok") and "thread not found" in str(r_doc.get("description", "")).lower():
                doc_data.pop("message_thread_id", None)
                f_xls.seek(0)
                r_doc = tg_post("sendDocument", payload=doc_data, files={"document": f_xls})
        if r_doc.get("ok"):
            cfg["ultimo_hash_excel"] = hash_datos
            cfg["ultima_hora_excel"] = hora_actual

    guardar_json_seguro(MATRIZ_CONFIG_FILE, cfg)


if __name__ == "__main__":
    print(f"📊 SINCRONIZANDO MATRIZ CENTRAL HISTÓRICA COMPLETA ({ahora_art().strftime('%H:%M:%S')} ART)...")
    ahora_s, hoy_s, res_bots, f_mat, cer, pl, tot_p = construir_matriz_unificada()
    actualizar_tema_matriz_telegram(ahora_s, hoy_s, res_bots, f_mat, cer, pl, tot_p)
