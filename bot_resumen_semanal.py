import os
import json
import requests
from datetime import datetime, timezone, timedelta
import openpyxl

TZ_ART = timezone(timedelta(hours=-3))
TELEGRAM_BOT_TOKEN = (os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("TELEGRAM_TOKEN") or "").strip()
TELEGRAM_CHAT_ID = (os.getenv("TELEGRAM_CHAT_ID") or os.getenv("CHAT_ID") or "").strip()
TOPIC_ID_RESUMEN_ENV = (os.getenv("TOPIC_ID_RESUMEN") or "").strip()

TELEGRAM_API_BASE = "https://" + "api.telegram.org/bot"
ARCHIVO_EXCEL = "AUDITORIA_SEMANAL_PRUEBA.xlsx"
CONFIG_TOPIC_FILE = "resumen_topic_config.json"
META_DEFAULT_USD = 600.0


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

    # Intenta crear automáticamente el tema "Resumen" en el supergrupo
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


def extraer_datos_excel():
    """Lee el Excel semanal sin modificarlo y calcula ganancias, pérdidas y avance."""
    ahora = datetime.now(TZ_ART)
    iso_y, iso_w, iso_wd = ahora.isocalendar()  # iso_wd: 1=Lunes ... 7=Domingo
    semana_actual = f"{iso_y}-W{iso_w:02d}"

    meta_usd = META_DEFAULT_USD
    ganancia_cerrada_neta = 0.0
    ganancia_flotante_neta = 0.0

    ganancia_positiva_usd = 0.0
    perdida_negativa_usd = 0.0
    ops_ganadoras = 0
    ops_perdedoras = 0
    dias_con_ops = set()

    if os.path.exists(ARCHIVO_EXCEL):
        wb = openpyxl.load_workbook(ARCHIVO_EXCEL, data_only=True)

        # 1. Leer resumen de cuota
        if "4_RESUMEN_CUOTA" in wb.sheetnames:
            ws_res = wb["4_RESUMEN_CUOTA"]
            headers_res = [str(ws_res.cell(row=1, column=c).value or "").strip() for c in range(1, ws_res.max_column + 1)]
            for r in range(2, ws_res.max_row + 1):
                sem_val = str(ws_res.cell(row=r, column=1).value or "").strip()
                if not sem_val:
                    continue
                semana_actual = sem_val
                for c_idx, h_name in enumerate(headers_res, start=1):
                    val = ws_res.cell(row=r, column=c_idx).value
                    if val is None:
                        continue
                    if "Meta Semanal" in h_name:
                        meta_usd = float(val)
                    elif "Ganancia Cerrada" in h_name:
                        ganancia_cerrada_neta = float(val)
                    elif "Ganancia Flotante" in h_name:
                        ganancia_flotante_neta = float(val)

        # 2. Leer detalle de operaciones para separar ganancias vs pérdidas
        if "1_CARTERA_Y_TRADER_IA" in wb.sheetnames:
            ws_ops = wb["1_CARTERA_Y_TRADER_IA"]
            headers_ops = [str(ws_ops.cell(row=1, column=c).value or "").strip() for c in range(1, ws_ops.max_column + 1)]
            col_pnl = next((i + 1 for i, h in enumerate(headers_ops) if "PnL Neto" in h), None)
            col_fecha = next((i + 1 for i, h in enumerate(headers_ops) if "Fecha Entrada" in h), None)

            if col_pnl:
                for r in range(2, ws_ops.max_row + 1):
                    pnl_val = ws_ops.cell(row=r, column=col_pnl).value
                    if pnl_val is None:
                        continue
                    try:
                        pnl = float(pnl_val)
                    except Exception:
                        continue

                    if col_fecha:
                        f_txt = str(ws_ops.cell(row=r, column=col_fecha).value or "").strip()
                        if len(f_txt) >= 10:
                            dias_con_ops.add(f_txt[:10])

                    if pnl > 0:
                        ganancia_positiva_usd += pnl
                        ops_ganadoras += 1
                    elif pnl < 0:
                        perdida_negativa_usd += pnl  # ya viene con signo negativo
                        ops_perdedoras += 1

    # Fallback: si el Excel no está en el repo, busca en archivos JSON semanales
    if ops_ganadoras == 0 and ops_perdedoras == 0 and ganancia_cerrada_neta == 0.0:
        ignorar = {"package.json", "historial_perlas.json", "historial_ganadoras.json", CONFIG_TOPIC_FILE}
        for fname in os.listdir("."):
            if not fname.endswith(".json") or fname in ignorar:
                continue
            try:
                with open(fname, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if not isinstance(data, dict):
                    continue
                if "meta_semanal" in data:
                    meta_usd = float(data["meta_semanal"])
                cierres = data.get("historial_cierres") or data.get("cerradas") or []
                if isinstance(cierres, list) and cierres:
                    for op in cierres:
                        if not isinstance(op, dict):
                            continue
                        pnl = float(op.get("pnl_neto") or op.get("pnl") or 0.0)
                        f_op = str(op.get("fecha_entrada") or op.get("fecha") or "")
                        if len(f_op) >= 10:
                            dias_con_ops.add(f_op[:10])
                        if pnl > 0:
                            ganancia_positiva_usd += pnl
                            ops_ganadoras += 1
                        elif pnl < 0:
                            perdida_negativa_usd += pnl
                            ops_perdedoras += 1
                    ganancia_cerrada_neta = round(ganancia_positiva_usd + perdida_negativa_usd, 2)
                    break
            except Exception:
                continue

    balance_neto = round(ganancia_cerrada_neta + ganancia_flotante_neta, 2)
    if balance_neto == 0.0 and (ganancia_positiva_usd != 0.0 or perdida_negativa_usd != 0.0):
        balance_neto = round(ganancia_positiva_usd + perdida_negativa_usd, 2)

    dias_transcurridos = iso_wd
    dias_restantes = max(0, 7 - iso_wd)
    dias_operados = len(dias_con_ops)

    # Cálculos porcentuales contra la meta ($600 USD)
    pct_avance_neto = round((balance_neto / meta_usd) * 100.0, 1) if meta_usd > 0 else 0.0
    usd_falta_neto = round(max(0.0, meta_usd - balance_neto), 2)
    pct_falta_neto = round((usd_falta_neto / meta_usd) * 100.0, 1) if meta_usd > 0 else 0.0

    # Ganancia bruta/neta positiva
    pct_ganancia_meta = round((ganancia_positiva_usd / meta_usd) * 100.0, 1) if meta_usd > 0 else 0.0
    usd_falta_desde_ganancia = round(max(0.0, meta_usd - ganancia_positiva_usd), 2)
    pct_falta_desde_ganancia = round((usd_falta_desde_ganancia / meta_usd) * 100.0, 1) if meta_usd > 0 else 0.0

    # Pérdida acumulada
    pct_perdida_meta = round((perdida_negativa_usd / meta_usd) * 100.0, 1) if meta_usd > 0 else 0.0

    ritmo_diario_necesario = round(usd_falta_neto / dias_restantes, 2) if dias_restantes > 0 else usd_falta_neto

    return {
        "hora_art": ahora.strftime("%Y-%m-%d %H:%M ART"),
        "semana": semana_actual,
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
        "balance_neto": balance_neto,
        "ritmo_diario": ritmo_diario_necesario
    }


def enviar_mensaje_resumen(datos, topic_id):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("⚠️ Faltan credenciales de Telegram.")
        return

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
        f"⚖️ <b>Balance Neto Semanal:</b> <b>${datos['balance_neto']:+,.2f} USD</b> (<b>{datos['pct_avance_neto']:+.1f}%</b>)\n"
        f"⏱️ <b>Ritmo requerido días restantes:</b> <code>${datos['ritmo_diario']:,.2f} USD/día</code>\n"
        f"<i>Actualizado: {datos['hora_art']}</i>"
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
    info = extraer_datos_excel()
    enviar_mensaje_resumen(info, tid)
