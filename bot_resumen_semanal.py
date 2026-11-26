import os
import json
import html
import requests
from datetime import datetime, timezone, timedelta
import openpyxl

TZ_ART = timezone(timedelta(hours=-3))
TELEGRAM_BOT_TOKEN = (os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("TELEGRAM_TOKEN") or "").strip()
TELEGRAM_CHAT_ID = (os.getenv("TELEGRAM_CHAT_ID") or os.getenv("CHAT_ID") or "").strip()
TOPIC_ID_RESUMEN_ENV = (os.getenv("TOPIC_ID_RESUMEN") or "").strip()

TELEGRAM_API_BASE = "https://" + "api.telegram.org/bot"
ARCHIVO_EXCEL = "AUDITORIA_SEMANAL_PRUEBA.xlsx"
PLAN_SEMANAL_FILE = "plan_semanal.json"
CEREBRO_EVOLUTIVO_FILE = "cerebro_evolutivo.json"
CONFIG_TOPIC_FILE = "resumen_topic_config.json"
META_DEFAULT_USD = 600.0
NOMBRES_TRADERS = ["TRADER_1", "TRADER_2", "TRADER_3"]


def a_float(valor, default=0.0):
    """Convierte celdas o valores a float de forma segura aunque tengan $ o %."""
    if valor is None:
        return default
    if isinstance(valor, (int, float)):
        return float(valor)
    txt = str(valor).replace("$", "").replace("%", "").replace(",", ".").strip()
    try:
        return float(txt)
    except Exception:
        return default


def cargar_json_seguro(ruta):
    if not os.path.exists(ruta):
        return {}
    try:
        with open(ruta, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def obtener_o_crear_topic_resumen():
    """Obtiene el ID del tema 'Resumen' desde Secret, archivo local o lo crea en Telegram."""
    if TOPIC_ID_RESUMEN_ENV.isdigit():
        return int(TOPIC_ID_RESUMEN_ENV)

    if os.path.exists(CONFIG_TOPIC_FILE):
        try:
            with open(CONFIG_TOPIC_FILE, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            tid = str(cfg.get("topic_id", "")).strip()
            if tid.isdigit():
                return int(tid)
        except Exception:
            pass

    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return None

    url = f"{TELEGRAM_API_BASE}{TELEGRAM_BOT_TOKEN}/createForumTopic"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "name": "Resumen",
        "icon_color": 7322096
    }
    try:
        r = requests.post(url, json=payload, timeout=15).json()
        if r.get("ok") and r.get("result", {}).get("message_thread_id"):
            tid = int(r["result"]["message_thread_id"])
            with open(CONFIG_TOPIC_FILE, "w", encoding="utf-8") as f:
                json.dump({"topic_id": tid, "nombre": "Resumen"}, f, indent=2)
            print(f"✅ Tema 'Resumen' creado automáticamente con ID: {tid}")
            return tid
        else:
            print(f"⚠️ No se pudo crear el tema automáticamente: {r.get('description')}")
    except Exception as e:
        print(f"⚠️ Error al crear tema en Telegram: {e}")

    return None


def leer_estado_cerebro_evolutivo():
    """Lee las métricas acumuladas de aprendizaje automático desde cerebro_evolutivo.json."""
    data = cargar_json_seguro(CEREBRO_EVOLUTIVO_FILE)
    if not isinstance(data, dict) or "metricas_globales" not in data:
        return None
    m = data.get("metricas_globales", {})
    u = data.get("umbrales", {})
    ver = int(data.get("version_ciclo", 1))
    tot_op = int(m.get("total_operadas", 0))
    tot_gan = int(m.get("total_ganadas", 0))
    tasa = round((tot_gan / tot_op) * 100.0, 1) if tot_op > 0 else 0.0
    return {
        "version": ver,
        "operadas": tot_op,
        "ganadas": tot_gan,
        "tasa_pct": tasa,
        "runners_20": int(m.get("runners_20_logrados", 0)),
        "vetos_ok": int(m.get("vetos_acertados", 0)),
        "vol_min": u.get("min_ratio_vol_1h", 1.8),
        "taker_min": u.get("min_taker_buy_pct", 55.0),
        "stop_base": u.get("stop_base_pct", -3.4)
    }


def extraer_datos_semanales():
    """
    Extrae los datos sincronizados de la semana activa priorizando plan_semanal.json
    y respaldando con AUDITORIA_SEMANAL_PRUEBA.xlsx (1_CARTERA_3_TRADERS / 4_RESUMEN_CUOTA).
    """
    ahora = datetime.now(TZ_ART)
    iso_y, iso_w, iso_wd = ahora.isocalendar()  # iso_wd: 1=Lunes ... 7=Domingo
    semana_actual = f"{iso_y}-W{iso_w:02d}"

    meta_usd = META_DEFAULT_USD
    ganancia_cerrada_neta = 0.0
    ganancia_flotante_neta = 0.0
    cumplimiento_excel_pct = None

    ganancia_positiva_usd = 0.0
    perdida_negativa_usd = 0.0
    ops_ganadoras = 0
    ops_perdedoras = 0
    ops_activas = 0
    dias_con_ops = set()
    escritorios_traders = {tid: None for tid in NOMBRES_TRADERS}
    fuente_datos = "plan_semanal.json"

    plan = cargar_json_seguro(PLAN_SEMANAL_FILE)
    if isinstance(plan, dict) and plan.get("semana_id"):
        semana_actual = str(plan.get("semana_id", semana_actual)).strip()
        meta_usd = a_float(plan.get("meta_semanal_usd"), META_DEFAULT_USD)
        ganancia_cerrada_neta = a_float(plan.get("ganancia_realizada_usd"), 0.0)

        cierres_sem = [
            c for c in plan.get("historial_cierres", [])
            if isinstance(c, dict) and str(c.get("semana_id", semana_actual)).strip() == semana_actual
        ]
        posiciones_act = [
            p for p in plan.get("posiciones", [])
            if isinstance(p, dict)
        ]

        for c in cierres_sem:
            pnl = a_float(c.get("pnl_usd"), 0.0)
            f_txt = str(c.get("fecha_entrada") or c.get("fecha_cierre") or "").strip()
            if len(f_txt) >= 10:
                dias_con_ops.add(f_txt[:10])
            if pnl > 0:
                ganancia_positiva_usd += pnl
                ops_ganadoras += 1
            elif pnl < 0:
                perdida_negativa_usd += pnl
                ops_perdedoras += 1

        sin_trader = []
        for p in posiciones_act:
            ops_activas += 1
            pnl_f = a_float(p.get("pnl_usd"), 0.0)
            ganancia_flotante_neta += pnl_f
            f_txt = str(p.get("fecha_entrada") or "").strip()
            if len(f_txt) >= 10:
                dias_con_ops.add(f_txt[:10])
            if pnl_f > 0:
                ganancia_positiva_usd += pnl_f
                ops_ganadoras += 1
            elif pnl_f < 0:
                perdida_negativa_usd += pnl_f
                ops_perdedoras += 1

            tid = str(p.get("trader_asignado", "")).strip()
            info_desk = {
                "base": str(p.get("base", "")).strip(),
                "pnl_pct": a_float(p.get("pnl_pct"), 0.0),
                "pnl_usd": pnl_f,
                "tp1": bool(p.get("tp1_ejecutado", False)),
                "tp2": bool(p.get("tp2_ejecutado", False))
            }
            if tid in escritorios_traders and escritorios_traders[tid] is None:
                escritorios_traders[tid] = info_desk
            else:
                sin_trader.append(info_desk)

        for info_desk in sin_trader:
            for tid in NOMBRES_TRADERS:
                if escritorios_traders[tid] is None:
                    escritorios_traders[tid] = info_desk
                    break

        ganancia_flotante_neta = round(ganancia_flotante_neta, 2)

    elif os.path.exists(ARCHIVO_EXCEL):
        fuente_datos = ARCHIVO_EXCEL
        wb = openpyxl.load_workbook(ARCHIVO_EXCEL, data_only=True)

        if "4_RESUMEN_CUOTA" in wb.sheetnames:
            ws_res = wb["4_RESUMEN_CUOTA"]
            headers_res = [str(ws_res.cell(row=1, column=c).value or "").strip() for c in range(1, ws_res.max_column + 1)]
            col_estado_sem = next((i + 1 for i, h in enumerate(headers_res) if "Estado" in h), ws_res.max_column)

            fila_objetivo = None
            for r in range(2, ws_res.max_row + 1):
                sem_val = str(ws_res.cell(row=r, column=1).value or "").strip()
                if not sem_val:
                    continue
                fila_objetivo = r
                est_sem = str(ws_res.cell(row=r, column=col_estado_sem).value or "").strip().upper()
                if est_sem == "ACTIVA":
                    break

            if fila_objetivo:
                semana_actual = str(ws_res.cell(row=fila_objetivo, column=1).value or semana_actual).strip()
                for c_idx, h_name in enumerate(headers_res, start=1):
                    val = ws_res.cell(row=fila_objetivo, column=c_idx).value
                    if val is None:
                        continue
                    if "Meta Semanal" in h_name:
                        meta_usd = a_float(val, META_DEFAULT_USD)
                    elif "Ganancia Cerrada" in h_name:
                        ganancia_cerrada_neta = a_float(val, 0.0)
                    elif "Ganancia Flotante" in h_name:
                        ganancia_flotante_neta = a_float(val, 0.0)
                    elif "Cumplimiento" in h_name:
                        cumplimiento_excel_pct = a_float(val, None)

        hoja_cartera = next(
            (name for name in ("1_CARTERA_3_TRADERS", "1_CARTERA_Y_TRADER_IA") if name in wb.sheetnames),
            None
        )
        if hoja_cartera:
            ws_ops = wb[hoja_cartera]
            headers_ops = [str(ws_ops.cell(row=1, column=c).value or "").strip() for c in range(1, ws_ops.max_column + 1)]
            col_sem = next((i + 1 for i, h in enumerate(headers_ops) if "Semana" in h), 1)
            col_trader = next((i + 1 for i, h in enumerate(headers_ops) if "Trader Asignado" in h), None)
            col_mon = next((i + 1 for i, h in enumerate(headers_ops) if "Moneda" in h), 4)
            col_pnl = next((i + 1 for i, h in enumerate(headers_ops) if "PnL Neto" in h), None)
            col_rend = next((i + 1 for i, h in enumerate(headers_ops) if "Rend. Neto" in h), None)
            col_fecha = next((i + 1 for i, h in enumerate(headers_ops) if "Fecha Entrada" in h), None)
            col_estado = next((i + 1 for i, h in enumerate(headers_ops) if "Estado" in h), None)

            if col_pnl:
                for r in range(2, ws_ops.max_row + 1):
                    sem_op = str(ws_ops.cell(row=r, column=col_sem).value or "").strip()
                    if sem_op and sem_op != semana_actual:
                        continue

                    pnl_raw = ws_ops.cell(row=r, column=col_pnl).value
                    if pnl_raw is None:
                        continue
                    pnl = a_float(pnl_raw, None)
                    if pnl is None:
                        continue

                    est_op = str(ws_ops.cell(row=r, column=col_estado).value or "").strip().upper() if col_estado else ""
                    if est_op == "ACTIVA":
                        ops_activas += 1
                        tid = str(ws_ops.cell(row=r, column=col_trader).value or "").strip() if col_trader else ""
                        mon_txt = str(ws_ops.cell(row=r, column=col_mon).value or "").strip()
                        rend_v = a_float(ws_ops.cell(row=r, column=col_rend).value, 0.0) if col_rend else 0.0
                        info_desk = {"base": mon_txt, "pnl_pct": rend_v, "pnl_usd": pnl, "tp1": False, "tp2": False}
                        if tid in escritorios_traders and escritorios_traders[tid] is None:
                            escritorios_traders[tid] = info_desk

                    if col_fecha:
                        f_txt = str(ws_ops.cell(row=r, column=col_fecha).value or "").strip()
                        if len(f_txt) >= 10:
                            dias_con_ops.add(f_txt[:10])

                    if pnl > 0:
                        ganancia_positiva_usd += pnl
                        ops_ganadoras += 1
                    elif pnl < 0:
                        perdida_negativa_usd += pnl
                        ops_perdedoras += 1

    balance_neto = round(ganancia_cerrada_neta + ganancia_flotante_neta, 2)
    if balance_neto == 0.0 and (ganancia_positiva_usd != 0.0 or perdida_negativa_usd != 0.0):
        balance_neto = round(ganancia_positiva_usd + perdida_negativa_usd, 2)

    dias_transcurridos = iso_wd
    dias_restantes = max(0, 7 - iso_wd)
    dias_operados = len(dias_con_ops)

    pct_avance_neto = round(cumplimiento_excel_pct, 1) if cumplimiento_excel_pct is not None else (
        round((balance_neto / meta_usd) * 100.0, 1) if meta_usd > 0 else 0.0
    )
    usd_falta_neto = round(max(0.0, meta_usd - balance_neto), 2)
    pct_falta_neto = round((usd_falta_neto / meta_usd) * 100.0, 1) if meta_usd > 0 else 0.0

    pct_ganancia_meta = round((ganancia_positiva_usd / meta_usd) * 100.0, 1) if meta_usd > 0 else 0.0
    usd_falta_desde_ganancia = round(max(0.0, meta_usd - ganancia_positiva_usd), 2)
    pct_falta_desde_ganancia = round((usd_falta_desde_ganancia / meta_usd) * 100.0, 1) if meta_usd > 0 else 0.0
    pct_perdida_meta = round((perdida_negativa_usd / meta_usd) * 100.0, 1) if meta_usd > 0 else 0.0

    ritmo_diario_necesario = round(usd_falta_neto / dias_restantes, 2) if dias_restantes > 0 else usd_falta_neto

    return {
        "hora_art": ahora.strftime("%Y-%m-%d %H:%M ART"),
        "semana": semana_actual,
        "fuente_datos": fuente_datos,
        "meta_usd": meta_usd,
        "dias_transcurridos": dias_transcurridos,
        "dias_restantes": dias_restantes,
        "dias_operados": dias_operados,
        "pct_avance_neto": pct_avance_neto,
        "usd_falta_neto": usd_falta_neto,
        "pct_falta_neto": pct_falta_neto,
        "ganancia_pos_usd": round(ganancia_positiva_usd, 2),
        "ops_ganadoras": ops_ganadoras,
        "pct_ganancia_meta": pct_ganancia_meta,
        "usd_falta_desde_ganancia": usd_falta_desde_ganancia,
        "pct_falta_desde_ganancia": pct_falta_desde_ganancia,
        "perdida_neg_usd": round(perdida_negativa_usd, 2),
        "ops_perdedoras": ops_perdedoras,
        "pct_perdida_meta": pct_perdida_meta,
        "ops_activas": ops_activas,
        "ganancia_flotante": round(ganancia_flotante_neta, 2),
        "balance_neto": balance_neto,
        "ritmo_diario": ritmo_diario_necesario,
        "escritorios_traders": escritorios_traders,
        "cerebro": leer_estado_cerebro_evolutivo()
    }


def enviar_mensaje_resumen(datos, topic_id):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("⚠️ Faltan credenciales de Telegram.")
        return

    lineas_traders = [f"🖥️ <b>ESCRITORIOS 3 TRADERS ({datos['ops_activas']}/3 ACTIVOS)</b>"]
    for tid in NOMBRES_TRADERS:
        desk = datos["escritorios_traders"].get(tid)
        if desk:
            fase_tp = " [Runner 30%]" if desk.get("tp2") else (" [TP1 OK]" if desk.get("tp1") else "")
            lineas_traders.append(
                f"   • <b>{tid}:</b> <b>{html.escape(desk['base'])}</b> "
                f"(<b>{desk['pnl_pct']:+.2f}%</b> | <code>${desk['pnl_usd']:+,.2f}</code>){fase_tp}"
            )
        else:
            lineas_traders.append(f"   • <b>{tid}:</b> <i>LIBRE (esperando consenso 6/6 + Jefe)</i>")
    bloque_traders = "\n".join(lineas_traders) + "\n\n"

    cer = datos.get("cerebro")
    bloque_cerebro = ""
    if cer:
        bloque_cerebro = (
            f"🧬 <b>Cerebro Evolutivo v{cer['version']}:</b> "
            f"Acierto <code>{cer['tasa_pct']}%</code> ({cer['ganadas']}/{cer['operadas']}) | "
            f"Runners +20%: <code>{cer['runners_20']}</code> | Vetos OK: <code>{cer['vetos_ok']}</code>\n"
        )

    texto = (
        f"📊 <b>RESUMEN SEMANAL • META Y RENDIMIENTO</b>\n"
        f"🗓️ <b>Semana:</b> <code>{datos['semana']}</code> | <b>Días de trading:</b> <code>Día {datos['dias_transcurridos']} de 7</code> "
        f"<i>({datos['dias_operados']} operados / {datos['dias_restantes']} restantes)</i>\n"
        f"🎯 <b>Meta a alcanzar:</b> <b>${datos['meta_usd']:,.2f} USD</b>\n"
        f"📈 <b>Porcentaje actual para llegar a la meta:</b> <b>{datos['pct_avance_neto']:+.1f}%</b> "
        f"<i>(Falta: <b>{datos['pct_falta_neto']:.1f}%</b> / <b>${datos['usd_falta_neto']:,.2f} USD</b>)</i>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📋 <b>DATOS DETALLADOS</b>\n\n"
        f"🟢 <b>Ganancia actual ({datos['ops_ganadoras']} ops):</b> <b>+${datos['ganancia_pos_usd']:,.2f} USD</b>\n"
        f"   • Avance sobre meta: <b>{datos['pct_ganancia_meta']:.1f}%</b>\n"
        f"   • Falta para cumplir meta: <b>${datos['usd_falta_desde_ganancia']:,.2f} USD</b> (<b>{datos['pct_falta_desde_ganancia']:.1f}%</b>)\n\n"
        f"🔴 <b>Pérdida actual ({datos['ops_perdedoras']} ops):</b> <b>${datos['perdida_neg_usd']:,.2f} USD</b>\n"
        f"   • Impacto sobre meta: <b>{datos['pct_perdida_meta']:.1f}%</b>\n"
        f"   • Total a remontar para llegar a meta: <b>${datos['usd_falta_neto']:,.2f} USD</b> (<b>{datos['pct_falta_neto']:.1f}%</b>)\n\n"
        f"{bloque_traders}"
        f"⚖️ <b>Balance Neto Semanal:</b> <b>${datos['balance_neto']:+,.2f} USD</b> (<b>{datos['pct_avance_neto']:+.1f}%</b>) "
        f"<i>(Flotante: ${datos['ganancia_flotante']:+,.2f})</i>\n"
        f"⏱️ <b>Ritmo requerido días restantes:</b> <code>${datos['ritmo_diario']:,.2f} USD/día</code>\n"
        f"{bloque_cerebro}"
        f"<i>Sincronizado con {html.escape(datos['fuente_datos'])} y {ARCHIVO_EXCEL} • {datos['hora_art']}</i>"
    )

    url = f"{TELEGRAM_API_BASE}{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": texto,
        "parse_mode": "HTML"
    }
    if topic_id:
        payload["message_thread_id"] = int(topic_id)

    r = requests.post(url, json=payload, timeout=20).json()
    if r.get("ok"):
        print("✅ Resumen semanal enviado correctamente a Telegram.")
    else:
        print(f"⚠️ Error enviando resumen: {r}")


if __name__ == "__main__":
    tid = obtener_o_crear_topic_resumen()
    info = extraer_datos_semanales()
    enviar_mensaje_resumen(info, tid)
