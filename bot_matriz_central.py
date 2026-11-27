import os, json, html, hashlib, requests
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

# Archivos reales de tus 4 temas (sin Perdedoras)
EXCEL_GANADORAS_FILE = "AUDITORIA_VERDE_GANADORAS.xlsx"
EXCEL_CAZADOR_HIST_FILE = "HISTORICO_CAZADOR_TACTICO.xlsx"
EXCEL_CAZADOR_AUD_FILE = "AUDITORIA_CAZADOR_TACTICO.xlsx"
EXCEL_PRE_EXPLOSION_FILE = "AUDITORIA_PRE_EXPLOSION.xlsx"
EXCEL_SEMANAL_FILE = "AUDITORIA_SEMANAL_PRUEBA.xlsx"

HISTORIAL_GANADORAS_FILE = "historial_ganadoras.json"
HISTORIAL_PERLAS_FILE = "historial_perlas.json"
DATOS_PRE_EXPLOSION_FILE = "datos_pre_explosion_ia.json"
PLAN_SEMANAL_FILE = "plan_semanal.json"
CEREBRO_EVOLUTIVO_FILE = "cerebro_evolutivo.json"

REPORTE_IA_GANADORAS_FILE = "reporte_ia_ganadoras.json"
REPORTE_IA_TACTICO_FILE = "reporte_ia_tactico.json"
REPORTE_IA_PRE_EXPLOSION_FILE = "reporte_ia_pre_explosion.json"

# Salidas unificadas
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


def leer_hoja_excel_cruda(rutas_posibles):
    """Lee el primer Excel disponible de la lista y devuelve (nombre_archivo, headers, filas)."""
    for ruta_excel in rutas_posibles:
        if not os.path.exists(ruta_excel):
            continue
        try:
            wb = openpyxl.load_workbook(ruta_excel, data_only=True)
            hoja_elegida = wb.sheetnames[0]
            for pref in ("DETALLE", "HISTORICO", "1_", "0_", "AUDITORIA", "RADAR"):
                for sname in wb.sheetnames:
                    if pref in sname.upper():
                        hoja_elegida = sname
                        break
            ws = wb[hoja_elegida]
            filas_totales = list(ws.iter_rows(values_only=True))
            if not filas_totales:
                continue
            headers = [str(h or f"Col_{i+1}").strip() for i, h in enumerate(filas_totales[0])]
            filas = [list(r) for r in filas_totales[1:] if any(cell is not None and str(cell).strip() != "" for cell in r)]
            return ruta_excel, headers, filas
        except Exception as e:
            print(f"⚠️ No se pudo leer {ruta_excel}: {e}")
    return rutas_posibles[0], [], []


def extraer_resumen_reporte_ia(ruta_json):
    data = cargar_json_seguro(ruta_json)
    if not isinstance(data, dict) or not data:
        return "Sin reporte IA reciente", {}
    resumen = ""
    for k in ("resumen_ia", "diagnostico_general", "veredicto", "resumen", "conclusion", "analisis_global"):
        val = data.get(k)
        if isinstance(val, str) and val.strip():
            resumen = val.strip()[:150]
            break

    mapa_mon = {}
    for k, v in data.items():
        if isinstance(k, str) and k.endswith("USDT") and isinstance(v, dict):
            mapa_mon[k] = v
        elif isinstance(v, dict):
            for sub_k, sub_v in v.items():
                if isinstance(sub_k, str) and sub_k.endswith("USDT") and isinstance(sub_v, dict):
                    mapa_mon[sub_k] = sub_v
        elif isinstance(v, list):
            for it in v:
                if isinstance(it, dict):
                    s = str(it.get("symbol") or it.get("moneda") or it.get("par") or "").upper().strip()
                    if s:
                        mapa_mon[s if s.endswith("USDT") else f"{s}USDT"] = it
    return (resumen or f"Activo ({len(mapa_mon)} monedas analizadas)"), mapa_mon


def es_de_hoy(fecha_str, hoy_iso):
    if not fecha_str:
        return False
    s = str(fecha_str).strip()
    dd_mm = datetime.strptime(hoy_iso, "%Y-%m-%d").strftime("%d/%m")
    dd_mm_yy = datetime.strptime(hoy_iso, "%Y-%m-%d").strftime("%d-%m-%Y")
    return (hoy_iso in s) or (dd_mm in s) or (dd_mm_yy in s)


def construir_matriz_unificada():
    ahora_dt = ahora_art()
    ahora_str = ahora_dt.strftime("%Y-%m-%d %H:%M ART")
    hoy_iso = ahora_dt.strftime("%Y-%m-%d")

    mapa_mkt = obtener_precios_vivos_binance()
    gan_json = cargar_json_seguro(HISTORIAL_GANADORAS_FILE)
    perlas_json = cargar_json_seguro(HISTORIAL_PERLAS_FILE)
    pre_json = cargar_json_seguro(DATOS_PRE_EXPLOSION_FILE)
    plan_sem = cargar_json_seguro(PLAN_SEMANAL_FILE)
    cerebro = cargar_json_seguro(CEREBRO_EVOLUTIVO_FILE)

    reg_verdes = gan_json.get("registro_verdes", {}) if isinstance(gan_json, dict) else {}
    posta_e1 = perlas_json.get("posta", {}) if isinstance(perlas_json, dict) else {}
    graduadas_e2 = dict(perlas_json.get("graduadas_pre_explosion", {})) if isinstance(perlas_json, dict) else {}
    if isinstance(pre_json, dict):
        for k, v in pre_json.items():
            if isinstance(k, str) and k.endswith("USDT") and isinstance(v, dict):
                graduadas_e2.setdefault(k, v)

    res_ia_gan, ia_gan_map = extraer_resumen_reporte_ia(REPORTE_IA_GANADORAS_FILE)
    res_ia_tac, ia_tac_map = extraer_resumen_reporte_ia(REPORTE_IA_TACTICO_FILE)
    res_ia_pre, ia_pre_map = extraer_resumen_reporte_ia(REPORTE_IA_PRE_EXPLOSION_FILE)

    arch_gan, h_gan, rows_gan = leer_hoja_excel_cruda([EXCEL_GANADORAS_FILE])
    arch_tac, h_tac, rows_tac = leer_hoja_excel_cruda([EXCEL_CAZADOR_HIST_FILE, EXCEL_CAZADOR_AUD_FILE])
    arch_pre, h_pre, rows_pre = leer_hoja_excel_cruda([EXCEL_PRE_EXPLOSION_FILE])

    posiciones = plan_sem.get("posiciones", []) if isinstance(plan_sem, dict) else []
    cierres = plan_sem.get("historial_cierres", []) if isinstance(plan_sem, dict) else []
    alts_eval = plan_sem.get("alternativas_evaluadas", []) if isinstance(plan_sem, dict) else []

    pos_map = {p["symbol"]: p for p in posiciones if p.get("symbol")}
    alts_map = {a["symbol"]: a for a in alts_eval if a.get("symbol")}

    # --- 1. Resumen Diario por Bot ---
    gan_hoy = [v for v in reg_verdes.values() if isinstance(v, dict) and es_de_hoy(v.get("fecha_entrada") or v.get("fecha"), hoy_iso)]
    tac_hoy = [v for v in posta_e1.values() if isinstance(v, dict) and es_de_hoy(v.get("fecha_deteccion") or v.get("fecha"), hoy_iso)]
    pre_hoy = [v for v in graduadas_e2.values() if isinstance(v, dict) and es_de_hoy(v.get("fecha_graduacion") or v.get("fecha"), hoy_iso)]
    ops_sem_hoy = [c for c in cierres if es_de_hoy(c.get("fecha_cierre"), hoy_iso)] + [p for p in posiciones if es_de_hoy(p.get("fecha_entrada"), hoy_iso)]

    prom_gan = round(
        sum(float(v.get("max_ganancia_pct", v.get("ganancia_pct", 0.0))) for v in reg_verdes.values() if isinstance(v, dict)) / max(len(reg_verdes), 1), 2
    )
    pnl_sem_neto = round(float(plan_sem.get("ganancia_realizada_usd", 0.0)) + sum(float(p.get("pnl_usd", 0.0)) for p in posiciones), 2)

    resumen_diario_bots = [
        {
            "emoji": "🟢",
            "bot": "Monedas Ganadoras",
            "archivo_excel": arch_gan,
            "senales_hoy": len(gan_hoy),
            "total_activas_radar": len(reg_verdes),
            "excel_filas": len(rows_gan),
            "metrica_clave": f"Máx Promedio: +{prom_gan}%",
            "diagnostico_ia": res_ia_gan
        },
        {
            "emoji": "🎯",
            "bot": "Cazador Táctico (E1)",
            "archivo_excel": arch_tac,
            "senales_hoy": len(tac_hoy),
            "total_activas_radar": len(posta_e1),
            "excel_filas": len(rows_tac),
            "metrica_clave": f"Radar E1: {len(posta_e1)} monedas",
            "diagnostico_ia": res_ia_tac
        },
        {
            "emoji": "⚡",
            "bot": "Pre-Explosión (E2)",
            "archivo_excel": arch_pre,
            "senales_hoy": len(pre_hoy),
            "total_activas_radar": len(graduadas_e2),
            "excel_filas": len(rows_pre),
            "metrica_clave": f"Graduadas E2: {len(graduadas_e2)} monedas",
            "diagnostico_ia": res_ia_pre
        },
        {
            "emoji": "🏆",
            "bot": "Gestor y Radar Semanal",
            "archivo_excel": EXCEL_SEMANAL_FILE,
            "senales_hoy": len(ops_sem_hoy),
            "total_activas_radar": len(posiciones),
            "excel_filas": len(posiciones) + len(cierres),
            "metrica_clave": f"Balance Sem: ${pnl_sem_neto:+.2f} USD",
            "diagnostico_ia": plan_sem.get("auditoria_ia", {}).get("diagnostico_24h", "3 Traders independientes activos")
        }
    ]

    # --- 2. Tabla Cruzada Unificada de Monedas ---
    todos_syms = sorted(
        set(reg_verdes.keys()) | set(posta_e1.keys()) | set(graduadas_e2.keys())
        | set(ia_gan_map.keys()) | set(ia_tac_map.keys()) | set(ia_pre_map.keys()) | set(pos_map.keys())
    )

    filas_matriz = []
    for sym in todos_syms:
        mkt = mapa_mkt.get(sym, {})
        p_vivo = float(mkt.get("precio", 0.0))
        chg_24h = round(float(mkt.get("cambio_24h", 0.0)), 2)
        vol_24m = round(float(mkt.get("vol_24h", 0.0)) / 1e6, 2)

        en_g = (sym in reg_verdes) or (sym in ia_gan_map)
        en_t = (sym in posta_e1) or (sym in ia_tac_map)
        en_p = (sym in graduadas_e2) or (sym in ia_pre_map)
        conf = sum([1 if en_g else 0, 1 if en_t else 0, 1 if en_p else 0])

        v_info = reg_verdes.get(sym, {})
        t_info = posta_e1.get(sym, {})
        p_info = graduadas_e2.get(sym, {})

        col_gan = f"✅ {v_info.get('estado', 'ACTIVA')} ({float(v_info.get('max_ganancia_pct', v_info.get('ganancia_pct', 0))):+.1f}%)" if en_g else "—"
        col_tac = f"✅ Etapa {t_info.get('etapa', ia_tac_map.get(sym, {}).get('etapa', 1))}" if en_t else "—"
        col_pre = f"⚡ {p_info.get('semaforo', ia_pre_map.get(sym, {}).get('semaforo', 'VERDE'))}" if en_p else "—"

        alt = alts_map.get(sym)
        mesa_txt = f"{alt.get('asistentes_aprobados', 0)}/6" if alt else "Radar"

        if sym in pos_map:
            po = pos_map[sym]
            estado_tr = f"🟢 {po.get('trader_asignado', 'TRADER')} ({float(po.get('pnl_pct', 0)):+.2f}%)"
        elif alt and alt.get("consenso_3_de_3"):
            estado_tr = f"🟡 LISTA ({alt.get('trader_propuesto', 'COLA')})"
        else:
            estado_tr = "OBSERVACIÓN"

        notas_ia = []
        for tag, m_ia in [("Gan", ia_gan_map), ("Tac", ia_tac_map), ("Pre", ia_pre_map)]:
            d = m_ia.get(sym, {})
            txt = d.get("diagnostico_ia") or d.get("veredicto_ia") or d.get("razon_ia") or d.get("analisis") or ""
            if isinstance(txt, str) and txt.strip():
                notas_ia.append(f"[{tag}] {txt.strip()}")
        if not notas_ia and alt:
            notas_ia.append(alt.get("jefe_veredicto", ""))

        filas_matriz.append({
            "symbol": sym,
            "moneda": sym[:-4],
            "precio_vivo": p_vivo,
            "chg_24h": chg_24h,
            "vol_24m": vol_24m,
            "confluencia": conf,
            "col_gan": col_gan,
            "col_tac": col_tac,
            "col_pre": col_pre,
            "mesa_txt": mesa_txt,
            "estado_tr": estado_tr,
            "notas_ia": " | ".join(notas_ia)[:220]
        })

    filas_matriz.sort(key=lambda x: (x["confluencia"], x["chg_24h"]), reverse=True)

    # --- 3. Excel Unificado (6 Pestañas) ---
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

    ws0 = wb.active
    ws0.title = "0_MATRIZ_UNIFICADA"
    _estilizar_hdr(ws0, [
        "Moneda", "Precio Vivo ($)", "Var 24h (%)", "Vol 24h ($M)", "Confluencia",
        "Monedas Ganadoras", "Cazador Táctico", "Pre-Explosión",
        "Mesa 6 Asistentes", "Estado 3 Traders", "Síntesis IA Combinada", "Actualizado"
    ])
    for r_idx, fm in enumerate(filas_matriz, start=2):
        ws0.append([
            fm["moneda"], fm["precio_vivo"], fm["chg_24h"], fm["vol_24m"],
            f"{fm['confluencia']}/3 Motores", fm["col_gan"], fm["col_tac"], fm["col_pre"],
            fm["mesa_txt"], fm["estado_tr"], fm["notas_ia"], ahora_str
        ])
        cel_c = ws0.cell(row=r_idx, column=5)
        if fm["confluencia"] >= 2:
            cel_c.fill = fill_verde
        elif fm["confluencia"] == 1:
            cel_c.fill = fill_amarillo

    ws1 = wb.create_sheet(title="1_RESUMEN_DIARIO_BOTS")
    _estilizar_hdr(ws1, [
        "Fecha", "Bot / Tema Telegram", "Excel Origen", "Señales Hoy",
        "Activas en Radar", "Filas Totales Excel", "Métrica Clave", "Diagnóstico IA Actual"
    ])
    for rb in resumen_diario_bots:
        ws1.append([
            hoy_iso, rb["bot"], rb["archivo_excel"], rb["senales_hoy"],
            rb["total_activas_radar"], rb["excel_filas"], rb["metrica_clave"], rb["diagnostico_ia"]
        ])

    for titulo_h, headers_h, rows_h in [
        ("2_EXCEL_GANADORAS", h_gan, rows_gan),
        ("3_EXCEL_CAZADOR_TACTICO", h_tac, rows_tac),
        ("4_EXCEL_PRE_EXPLOSION", h_pre, rows_pre)
    ]:
        ws_esp = wb.create_sheet(title=titulo_h)
        if headers_h:
            _estilizar_hdr(ws_esp, headers_h)
            for row_data in rows_h:
                ws_esp.append(row_data)
        else:
            _estilizar_hdr(ws_esp, ["Estado"])
            ws_esp.append(["Sin datos registrados todavía en el Excel individual."])

    ws5 = wb.create_sheet(title="5_GESTOR_3_TRADERS")
    _estilizar_hdr(ws5, [
        "Semana", "Trader", "Moneda", "Estado", "Capital ($)", "Entrada ($)",
        "Actual/Cierre ($)", "PnL Neto (%)", "PnL Neto ($)", "Patrón Origen", "Veredicto Jefe"
    ])
    for op in list(cierres) + list(posiciones):
        ws5.append([
            op.get("semana_id", ""), op.get("trader_asignado", ""), op.get("base", ""),
            op.get("estado", ""), round(float(op.get("capital_usd", 0)), 2),
            float(op.get("precio_entrada", 0)), float(op.get("precio_actual", 0)),
            round(float(op.get("pnl_pct", 0)), 2), round(float(op.get("pnl_usd", 0)), 2),
            op.get("patron_detectado", op.get("origen", "")),
            op.get("jefe_veredicto_entrada") or op.get("motivo_cierre", "")
        ])

    for sheet in wb.worksheets:
        for col in sheet.columns:
            max_len = max(len(str(c.value or "")) for c in col)
            sheet.column_dimensions[col[0].column_letter].width = min(max_len + 4, 52)

    wb.save(EXCEL_MATRIZ_CENTRAL_FILE)
    return ahora_str, hoy_iso, resumen_diario_bots, filas_matriz, cerebro, plan_sem


# ==============================================================================
# TELEGRAM: MISMO ESTILO VISUAL QUE EL TEMA "RESUMEN" (MENSAJE FIJADO + EXCEL)
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


def actualizar_tema_matriz_telegram(ahora_str, hoy_iso, resumen_diario_bots, filas_matriz, cerebro, plan_sem):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return

    cfg = cargar_json_seguro(MATRIZ_CONFIG_FILE)
    topic_id = asegurar_topic_matriz(cfg)

    sem_id = plan_sem.get("semana_id", "2026") if isinstance(plan_sem, dict) else "2026"
    total_hoy = sum(rb["senales_hoy"] for rb in resumen_diario_bots)
    top_confluencia = [f for f in filas_matriz if f["confluencia"] >= 2][:6]
    en_cartera = [f for f in filas_matriz if "🟢 TRADER_" in f["estado_tr"]]

    # Formato calcado al tema "Resumen" de tu captura
    msg = (
        f"📊 <b>MATRIZ CENTRAL • EXCEL UNIFICADO Y RESUMEN DIARIO</b>\n"
        f"🗓️ <b>Fecha:</b> <code>{hoy_iso}</code> (Semana <code>{sem_id}</code>) | <b>Señales hoy:</b> <b>{total_hoy}</b>\n"
        f"📁 <b>Archivo Maestro:</b> <code>{EXCEL_MATRIZ_CENTRAL_FILE}</code> (6 pestañas)\n"
        f"🔄 <b>Sincronización en vivo:</b> Cada 15 min junto a cada bot\n\n"
        f"📋 <b>RESUMEN DIARIO POR BOT</b>\n\n"
    )

    for rb in resumen_diario_bots:
        msg += (
            f"{rb['emoji']} <b>{html.escape(rb['bot'])}:</b> <b>{rb['senales_hoy']} señales hoy</b>\n"
            f"• Activas en radar: <code>{rb['total_activas_radar']}</code> | Registros Excel: <code>{rb['excel_filas']}</code>\n"
            f"• {html.escape(rb['metrica_clave'])}\n"
            f"• <i>IA: {html.escape(rb['diagnostico_ia'][:115])}</i>\n\n"
        )

    msg += "🔥 <b>TOP CONFLUENCIA CRUZADA (2/3 O 3/3 MOTORES)</b>\n"
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
        f"\n🧬 <i>Cerebro Evolutivo v{v_ciclo} • Universo cruzado: {len(filas_matriz)} monedas</i>\n"
        f"<i>Sincronizado con los 4 Excel • {ahora_str}</i>"
    )

    # 1. Actualizar/Fijar el mensaje tablero principal (igual que "Mensaje fijado" en Resumen)
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

    # 2. Subir el Excel Matriz unificado cuando cambia cualquier dato o en cada corte horario
    hash_datos = hashlib.md5(
        json.dumps([resumen_diario_bots, [(f["moneda"], f["confluencia"], f["estado_tr"]) for f in filas_matriz]], sort_keys=True).encode()
    ).hexdigest()

    hora_actual = ahora_art().hour
    es_manual = (os.getenv("GITHUB_EVENT_NAME") == "workflow_dispatch")
    if cfg.get("ultimo_hash_excel") != hash_datos or cfg.get("ultima_hora_excel") != hora_actual or es_manual:
        doc_data = {
            "chat_id": TELEGRAM_CHAT_ID,
            "caption": (
                f"📎 <b>{EXCEL_MATRIZ_CENTRAL_FILE}</b> (6 Pestañas Unificadas)\n"
                f"🔄 Sincronizado: <code>{ahora_str}</code> | Señales hoy: <b>{total_hoy}</b> | Cruzadas: <b>{len(filas_matriz)}</b>"
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
    print(f"📊 SINCRONIZANDO MATRIZ CENTRAL UNIFICADA ({ahora_art().strftime('%H:%M:%S')} ART)...")
    ahora_s, hoy_s, res_bots, f_mat, cer, pl = construir_matriz_unificada()
    actualizar_tema_matriz_telegram(ahora_s, hoy_s, res_bots, f_mat, cer, pl)
