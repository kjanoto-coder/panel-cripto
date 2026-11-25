import os, json, glob, time, random, html, requests
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

# URLs ensambladas para evitar auto-conversión a Markdown al copiar/pegar
TELEGRAM_API_BASE = "https://" + "api.telegram.org/bot"
BASE_URL_NETLIFY = "https://" + "gregarious-frangollo-0346c5.netlify.app"
BINANCE_TRADE_BASE = "https://" + "www.binance.com/es/trade/"
BINANCE_API_BASES = [
    "https://" + "api.binance.com",
    "https://" + "data-api.binance.vision"
]

HISTORIAL_PERLAS_FILE = "historial_perlas.json"
HISTORIAL_GANADORAS_FILE = "historial_ganadoras.json"
EXCEL_GANADORAS_FILE = "AUDITORIA_VERDE_GANADORAS.xlsx"
PLAN_SEMANAL_FILE = "plan_semanal.json"
EXCEL_SEMANAL_FILE = "AUDITORIA_SEMANAL_PRUEBA.xlsx"

# Parámetros operativos: Consenso 3/3 (Asistente [Cazador + Pre-Explosión] -> Trader -> Jefe)
CAPITAL_INICIAL_PRUEBA = 3500.0
META_SEMANAL_USD = 600.0
MAX_MONEDAS_SEMANA = 4              # Cada cupo usa SIEMPRE 1/4 (25%) del capital disponible
CUPOS_MODO_DEFENSIVO = 2            # Reduce de 4 a 2 cupos simultáneos cuando el mercado general está débil
MAX_ENTRADAS_POR_CORRIDA = 2        # Entrada escalonada: máximo 2 compras nuevas por ejecución
TOP_ALTERNATIVAS_MOSTRAR = 8
FACTIBILIDAD_MINIMA_JEFE = 75       # Puntaje mínimo exigido por el Jefe Supervisor para aprobar una entrada

# Parámetros de Riesgo, Cosecha Runner en 3 Tramos, Liquidez Real y Circuit Breaker
COMISION_SPOT_TOTAL_PCT = 0.20      # 0.10% compra + 0.10% venta en Binance Spot (PnL Neto Real)
STOP_LOSS_FIJO_PCT = -3.40          # Margen técnico de despegue (-3.40% neto) para sobrevivir mechazos previos
MAX_PERDIDA_USD = 30.0              # Tope duro en dólares alineado con -3.40% sobre cupo de ~$875
PREALERTA_PERDIDA_USD = 20.0        # Pre-alerta temprana
TP1_ASEGURAR_PCT = 6.5              # Tramo 1: vende 35% al tocar +6.5% neto y mueve stop a +0.50% BE
TP2_ASEGURAR_PCT = 15.0             # Tramo 2: vende otro 35% al tocar +15.0% neto y mueve stop a +8.0%
TRAILING_RUNNER_PCT = 4.5           # Tramo 3 (30% Runner): trailing holgado de 4.5% desde el máximo para cazar +25% a +70%
HORAS_MAX_SIN_ARRANQUE_VIP = 24.0   # Paciencia de 24h en acumulación para monedas confirmadas por Pre-Explosión
HORAS_MAX_SIN_ARRANQUE_STD = 10.0   # Rotación en 10h para candidatas estándar
MAX_REENTRADAS_SEMANA = 1           # Permite hasta 1 re-entrada semanal si vuelve a romper con volumen >= 1.8x
COOLDOWN_PANICO_BTC_MIN = 60        # Antispam de 60 minutos para alerta de pánico BTC 1H

MIN_LIQUIDEZ_TOP_ASK_USD = 2500.0   # Liquidez mínima en USD dentro del 0.15% del mejor Ask
MAX_SLIPPAGE_EST_PCT = 0.25         # Deslizamiento máximo estimado para ejecutar un cupo real (~$875)
MAX_PERDIDA_DIARIA_USD = 65.0       # Circuit Breaker diario: pérdida máxima realizada en un mismo día
MAX_STOPS_SEGUIDOS_DIA = 3          # Circuit Breaker diario: máximo de cierres negativos seguidos en el día
HORAS_CONGELAMIENTO_CB = 8          # Horas que el Jefe congela compras al activarse el Circuit Breaker

MODELOS_GEMINI = ["gemini-3.5-flash-lite", "gemini-3.8-flash", "gemini-4-hydrogen", "gemini-2.5-flash"]

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
    for base_url in BINANCE_API_BASES:
        try:
            r = session.get(f"{base_url}/api/v3/ticker/24hr", timeout=15)
            if r.status_code == 200 and isinstance(r.json(), list):
                mapa = {}
                for t in r.json():
                    sym = t.get("symbol", "")
                    if sym.endswith("USDT"):
                        base = sym[:-4]
                        if base.endswith(("UP", "DOWN", "BULL", "BEAR")):
                            continue
                        try:
                            mapa[sym] = {
                                "symbol": sym,
                                "base": base,
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

def cargar_json_seguro(ruta):
    if not os.path.exists(ruta):
        return {}
    try:
        with open(ruta, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def calcular_horas_entre(fecha_str, dt_ref=None):
    if not fecha_str:
        return 999.0
    try:
        dt_ref = dt_ref or ahora_art()
        limpia = fecha_str.replace(" ART", "").strip()
        dt_ev = datetime.strptime(limpia, "%Y-%m-%d %H:%M").replace(tzinfo=TZ_ART)
        return max(0.0, (dt_ref - dt_ev).total_seconds() / 3600.0)
    except Exception:
        return 999.0

# ==============================================================================
# NIVEL 1: ASISTENTE (TODAS LAS VARIABLES REALES: CAZADOR + CONFIRMACIÓN PRE-EXPLOSIÓN)
# ==============================================================================

def _asistente_leer_excel_ganadoras():
    aciertos_excel = {}
    if not os.path.exists(EXCEL_GANADORAS_FILE):
        return aciertos_excel
    try:
        wb = openpyxl.load_workbook(EXCEL_GANADORAS_FILE, data_only=True)
        if "DETALLE_OPERACIONES" in wb.sheetnames:
            ws = wb["DETALLE_OPERACIONES"]
            for r in range(2, ws.max_row + 1):
                mon = str(ws.cell(row=r, column=2).value or "").strip().upper()
                if not mon:
                    continue
                sym = mon if mon.endswith("USDT") else f"{mon}USDT"
                sub_max = float(ws.cell(row=r, column=7).value or 0.0)
                if sym not in aciertos_excel or sub_max > aciertos_excel[sym]:
                    aciertos_excel[sym] = round(sub_max, 2)
    except Exception:
        pass
    return aciertos_excel

def asistente_auditar_post_cierre(mapa_mkt, plan):
    """Autopsia Post-Cierre 24h: evalúa cada cierre para retroalimentar al Jefe Supervisor."""
    ahora_dt = ahora_art()
    cierres = plan.get("historial_cierres", [])
    stops_prematuros_sem = 0
    stops_salvadores_sem = 0
    cosechas_optimas_sem = 0

    for c in cierres:
        sym = c.get("symbol", "")
        horas_cierre = calcular_horas_entre(c.get("fecha_cierre", ""), ahora_dt)
        p_cierre = float(c.get("precio_actual") or c.get("precio_entrada") or 0.0)
        pnl_cierre = float(c.get("pnl_usd", 0.0))

        if p_cierre <= 0:
            continue

        p_max_post = float(c.get("post_cierre_max", p_cierre))
        p_min_post = float(c.get("post_cierre_min", p_cierre))

        if sym in mapa_mkt and horas_cierre <= 24.0 and not c.get("autopsia_completada", False):
            p_act = float(mapa_mkt[sym]["precio"])
            p_max_post = max(p_max_post, p_act)
            p_min_post = min(p_min_post, p_act)
            c["post_cierre_max"] = p_max_post
            c["post_cierre_min"] = p_min_post

            var_max_post = round(((p_max_post - p_cierre) / p_cierre) * 100.0, 2)
            var_min_post = round(((p_min_post - p_cierre) / p_cierre) * 100.0, 2)
            c["var_max_post_pct"] = var_max_post
            c["var_min_post_pct"] = var_min_post

            if pnl_cierre < 0:
                if var_max_post >= 8.0:
                    c["veredicto_autopsia"] = f"⚠️ STOP_PREMATURO (Subió +{var_max_post:.1f}% tras cerrar)"
                elif var_min_post <= -5.0:
                    c["veredicto_autopsia"] = f"🛡️ STOP_SALVADOR (Siguió cayendo {var_min_post:.1f}%)"
                else:
                    c["veredicto_autopsia"] = f"⏳ EN AUDITORÍA 24H (Max {var_max_post:+.1f}% / Min {var_min_post:+.1f}%)"
            else:
                if var_max_post >= 12.0:
                    c["veredicto_autopsia"] = f"📊 SALIDA_TEMPRANA (Siguió +{var_max_post:.1f}%)"
                else:
                    c["veredicto_autopsia"] = f"✅ COSECHA_OPTIMA (Post Max {var_max_post:+.1f}%)"

            if horas_cierre >= 23.5:
                c["autopsia_completada"] = True

        if c.get("semana_id") == plan.get("semana_id"):
            v_aut = str(c.get("veredicto_autopsia", ""))
            if "STOP_PREMATURO" in v_aut:
                stops_prematuros_sem += 1
            elif "STOP_SALVADOR" in v_aut:
                stops_salvadores_sem += 1
            elif "COSECHA_OPTIMA" in v_aut:
                cosechas_optimas_sem += 1

    return {
        "stops_prematuros_semana": stops_prematuros_sem,
        "stops_salvadores_semana": stops_salvadores_sem,
        "cosechas_optimas_semana": cosechas_optimas_sem,
        "resumen_autopsia": (
            f"Autopsia 24h: {stops_salvadores_sem} stops salvadores | "
            f"{stops_prematuros_sem} stops prematuros | {cosechas_optimas_sem} cosechas óptimas"
        )
    }

def ejecutar_asistente_inteligencia(mapa_mkt, plan):
    """
    NIVEL 1 (ASISTENTE): Reúne TODAS las variables reales del ecosistema:
    1) Cazador Táctico (monedas detectadas en verde)
    2) Pre-Explosión (confirmación de ruptura/graduación)
    3) Historial Ganadoras, Excel Verdes, Bot Perdedoras, Macro y Autopsia 24h.
    """
    perlas = cargar_json_seguro(HISTORIAL_PERLAS_FILE)
    ganadoras = cargar_json_seguro(HISTORIAL_GANADORAS_FILE)
    aciertos_excel_gan = _asistente_leer_excel_ganadoras()
    stats_autopsia = asistente_auditar_post_cierre(mapa_mkt, plan)

    graduadas = perlas.get("graduadas_pre_explosion", {}) if isinstance(perlas, dict) else {}
    posta = perlas.get("posta", {}) if isinstance(perlas, dict) else {}
    reg_verdes = ganadoras.get("registro_verdes", {}) if isinstance(ganadoras, dict) else {}

    vetadas_perdedoras = set()
    resumen_macro_bots = []
    notas_extra_monedas = {}
    fuentes_leidas = []

    if posta:
        fuentes_leidas.append(f"Cazador Táctico ({len(posta)})")
    if graduadas:
        fuentes_leidas.append(f"Pre-Explosión ({len(graduadas)})")
    if reg_verdes:
        fuentes_leidas.append(f"Ganadoras ({len(reg_verdes)})")
    if aciertos_excel_gan:
        fuentes_leidas.append(f"Excel Verdes ({len(aciertos_excel_gan)})")

    archivos_ignorar = {PLAN_SEMANAL_FILE, "package.json", "package-lock.json", "tsconfig.json", "resumen_topic_config.json"}
    for ruta in sorted(glob.glob("*.json")):
        if ruta in archivos_ignorar or ruta in (HISTORIAL_PERLAS_FILE, HISTORIAL_GANADORAS_FILE):
            continue
        data = cargar_json_seguro(ruta)
        if not isinstance(data, dict) or not data:
            continue
        fuentes_leidas.append(ruta)
        nombre_l = ruta.lower()

        if "perdedor" in nombre_l or "loser" in nombre_l or "negra" in nombre_l:
            for k, v in data.items():
                if isinstance(k, str) and k.endswith("USDT"):
                    vetadas_perdedoras.add(k)
                elif isinstance(v, dict):
                    for sub_k in v.keys():
                        if isinstance(sub_k, str) and sub_k.endswith("USDT"):
                            vetadas_perdedoras.add(sub_k)
                elif isinstance(v, list):
                    for item in v:
                        if isinstance(item, str) and item.endswith("USDT"):
                            vetadas_perdedoras.add(item)
                        elif isinstance(item, dict) and str(item.get("symbol", "")).endswith("USDT"):
                            vetadas_perdedoras.add(item["symbol"])

        if any(tag in nombre_l for tag in ("sentimiento", "noticia", "central", "inteligencia", "mercado", "macro", "clima")):
            for campo in ("resumen", "diagnostico", "sentimiento", "estado_mercado", "veredicto", "alerta", "conclusiones"):
                val = data.get(campo)
                if isinstance(val, str) and val.strip():
                    resumen_macro_bots.append(f"[{ruta}] {val.strip()[:140]}")
                    break

        for k, v in data.items():
            if isinstance(k, str) and k.endswith("USDT") and isinstance(v, dict):
                txt_nota = v.get("razon") or v.get("analisis") or v.get("motivo") or v.get("diagnostico") or ""
                if isinstance(txt_nota, str) and txt_nota.strip():
                    notas_extra_monedas.setdefault(k, []).append(f"{ruta}: {txt_nota.strip()[:110]}")

    universo_total = set(graduadas.keys()) | set(posta.keys()) | set(reg_verdes.keys())
    boletin_asistente = {
        "fuentes_auditadas": fuentes_leidas,
        "total_monedas_rastreadas": len(universo_total),
        "total_vetadas_perdedoras": len(vetadas_perdedoras),
        "alertas_macro": resumen_macro_bots[:4],
        "autopsia_24h": stats_autopsia,
        "resumen_ejecutivo": (
            f"Asistente auditó {len(fuentes_leidas)} fuentes ({len(universo_total)} monedas, "
            f"{len(vetadas_perdedoras)} vetadas). {stats_autopsia['resumen_autopsia']}."
        )
    }

    eco = {
        "perlas": perlas,
        "ganadoras": ganadoras,
        "aciertos_excel_ganadoras": aciertos_excel_gan,
        "graduadas": graduadas,
        "posta": posta,
        "reg_verdes": reg_verdes,
        "vetadas_perdedoras": vetadas_perdedoras,
        "macro_bots": resumen_macro_bots[:4],
        "notas_extra": notas_extra_monedas,
        "boletin_asistente": boletin_asistente
    }
    return boletin_asistente, eco

def asistente_construir_dossier(sym, p_actual, eco, plan=None):
    """
    Construye el Dossier de Inteligencia Real verificando la cadena exacta:
    1) CAZADOR TÁCTICO: detecta la moneda en verde.
    2) PRE-EXPLOSIÓN: confirma la graduación/ruptura (sin azar).
    3) VARIABLES EXTRA: historial ganadoras, lista negra, reincidencia.
    """
    grad = eco["graduadas"].get(sym, {})
    post = eco["posta"].get(sym, {})
    verd = eco["reg_verdes"].get(sym, {})
    sub_excel_gan = float(eco.get("aciertos_excel_ganadoras", {}).get(sym, 0.0))

    p_ref = float(grad.get("precio_ref") or post.get("precio_ref") or verd.get("precio_entrada") or p_actual or 0)
    var_desde_radar = round(((p_actual - p_ref) / p_ref) * 100, 2) if p_ref > 0 and p_actual > 0 else 0.0

    semaforo = str(grad.get("semaforo") or post.get("semaforo") or ("VERDE" if verd else "N/D")).upper()
    etapa = int(post.get("etapa", grad.get("etapa", 0)))
    blindaje = int(grad.get("blindaje_pct") or post.get("blindaje_etapa1") or grad.get("probabilidad_pct") or (82 if verd else 70))
    cert_e1 = bool(grad.get("certificada_etapa1") or post.get("certificada_etapa1"))
    cert_e2 = bool(grad.get("certificada_ia"))

    # Pilar 1A: Detección por Cazador Táctico en verde
    cazador_en_verde = bool(post) or bool(verd) or ("VERDE" in semaforo)
    # Pilar 1B: Confirmación por Pre-Explosión (graduadas_pre_explosion o doble certificación/ganadoras activa)
    confirmada_pre_explosion = bool(grad) and (
        ("VERDE" in semaforo) or cert_e1 or cert_e2 or blindaje >= 75
    )

    tesis_textos = []
    for fuente in (grad, post, verd):
        for clave in ("razon_ia", "analisis_ia", "motivo", "razon", "patron", "detalle"):
            val = fuente.get(clave)
            if isinstance(val, str) and val.strip() and val.strip() not in tesis_textos:
                tesis_textos.append(val.strip())
    if sym in eco["notas_extra"]:
        tesis_textos.extend(eco["notas_extra"][sym])

    estado_hist_verde = str(verd.get("estado", "SIN_REGISTRO")).upper()
    max_hist_verde = max(float(verd.get("max_ganancia_pct", verd.get("ganancia_pct", 0.0))), sub_excel_gan)
    en_lista_perdedoras = (sym in eco["vetadas_perdedoras"]) or ("PERDEDORA" in estado_hist_verde) or ("STOP" in estado_hist_verde)
    en_ganadoras_activo = (bool(verd) or sub_excel_gan >= 5.0) and not en_lista_perdedoras

    stops_previos_semana = 0
    if plan:
        for c in plan.get("historial_cierres", []):
            if c.get("semana_id") == plan.get("semana_id") and c.get("symbol") == sym and float(c.get("pnl_usd", 0)) < 0:
                stops_previos_semana += 1

    bloqueada_por_reincidencia = (stops_previos_semana > MAX_REENTRADAS_SEMANA)
    es_reentrada_habilitada = (1 <= stops_previos_semana <= MAX_REENTRADAS_SEMANA)

    confluencia_multi_bot = sum([
        1 if cazador_en_verde else 0,
        1 if confirmada_pre_explosion else 0,
        1 if en_ganadoras_activo else 0,
        1 if sym in eco["notas_extra"] else 0
    ])

    # El Asistente solo da luz verde cuando NO hay alertas negativas y existe respaldo real:
    # Ideal: Cazador en Verde + Confirmación Pre-Explosión (o Ganadoras confirmada con Pre-Explosión)
    check_1_asistente_ok = (
        not en_lista_perdedoras
        and not bloqueada_por_reincidencia
        and (
            (cazador_en_verde and confirmada_pre_explosion)
            or (confirmada_pre_explosion and (cert_e1 or cert_e2))
            or (en_ganadoras_activo and (cazador_en_verde or confirmada_pre_explosion))
        )
    )

    carril_vip_radar = (
        check_1_asistente_ok
        and (-3.5 <= var_desde_radar <= 12.0)
    )

    if en_lista_perdedoras:
        dictamen_asistente = "⛔ BLOQUEADA ASISTENTE: En lista negra / Bot Perdedoras."
    elif bloqueada_por_reincidencia:
        dictamen_asistente = f"⛔ BLOQUEADA ASISTENTE: Agotó re-entrada semanal ({stops_previos_semana} stops)."
    elif cazador_en_verde and not confirmada_pre_explosion and not en_ganadoras_activo:
        dictamen_asistente = f"⏳ EN OBSERVACIÓN ASISTENTE: Detectada por Cazador (E{etapa}), falta confirmación Pre-Explosión."
    elif not check_1_asistente_ok:
        dictamen_asistente = f"⚠️ DESCARTADA ASISTENTE: Sin cadena Cazador + Pre-Explosión (Semáforo {semaforo}, E{etapa})."
    else:
        cadena_lbl = "Cazador Verde + Pre-Explosión OK" if (cazador_en_verde and confirmada_pre_explosion) else "Pre-Explosión + Ganadoras OK"
        reent_tag = " [🔄 RE-ENTRADA]" if es_reentrada_habilitada else ""
        dictamen_asistente = (
            f"✅ ASISTENTE OK [{cadena_lbl}]{reent_tag} | Radar {var_desde_radar:+.1f}% | HistVerdes {max_hist_verde:+.1f}%"
        )

    resumen_corto = (
        f"Cazador:{'SÍ' if cazador_en_verde else 'NO'} | PreExplosión:{'SÍ' if confirmada_pre_explosion else 'NO'} | "
        f"DesdeRadar:{var_desde_radar:+.1f}% | HistVerdes:{max_hist_verde:+.1f}%"
    )
    if tesis_textos:
        resumen_corto += f" | Tesis: {tesis_textos[0][:80]}"

    return {
        "cazador_en_verde": cazador_en_verde,
        "confirmada_pre_explosion": confirmada_pre_explosion,
        "semaforo_radar": semaforo,
        "etapa_cazador": etapa,
        "blindaje_pct": blindaje,
        "doble_certificada": (cert_e1 and cert_e2),
        "en_ganadoras_activo": en_ganadoras_activo,
        "carril_vip_radar": carril_vip_radar,
        "es_reentrada_habilitada": es_reentrada_habilitada,
        "stops_previos_semana": stops_previos_semana,
        "confluencia_multi_bot": confluencia_multi_bot,
        "reincidente_stop_semana": bloqueada_por_reincidencia,
        "tiene_respaldo_bots": check_1_asistente_ok,
        "precio_referencia_radar": p_ref,
        "var_desde_deteccion_radar_pct": var_desde_radar,
        "estado_historial_ganadoras": estado_hist_verde,
        "max_ganancia_historica_pct": max_hist_verde,
        "alertada_en_perdedoras": en_lista_perdedoras,
        "tesis_previa_bots": " | ".join(tesis_textos)[:260] if tesis_textos else "Sin nota textual adicional en JSON",
        "dictamen_asistente": dictamen_asistente,
        "resumen_corto": resumen_corto
    }

# ==============================================================================
# HERRAMIENTAS TÉCNICAS Y LIQUIDEZ REAL PARA EL TRADER (CUÁNDO ENTRAR / SALIR)
# ==============================================================================

def auditar_order_book_semanal(session, symbol, monto_orden_usd=875.0):
    """Audita profundidad ±2.5%, muros vendedores, liquidez en el 0.15% del mejor Ask y slippage VWAP."""
    for base_url in BINANCE_API_BASES:
        try:
            r = session.get(f"{base_url}/api/v3/depth", params={"symbol": symbol, "limit": 20}, timeout=5)
            if r.status_code == 200:
                d = r.json()
                bids, asks = d.get("bids", []), d.get("asks", [])
                if not bids or not asks:
                    continue
                b0, a0 = float(bids[0][0]), float(asks[0][0])
                spread = ((a0 - b0) / b0) * 100 if b0 > 0 else 99.0

                bids_cerca = [float(x[0]) * float(x[1]) for x in bids if float(x[0]) >= b0 * 0.975]
                asks_cerca = [float(x[0]) * float(x[1]) for x in asks if float(x[0]) <= a0 * 1.025]

                vb = sum(bids_cerca) if bids_cerca else sum(float(x[0]) * float(x[1]) for x in bids)
                va = sum(asks_cerca) if asks_cerca else sum(float(x[0]) * float(x[1]) for x in asks)
                ratio = round(vb / va, 2) if va > 0 else 1.0

                liq_ask_015 = sum(float(x[0]) * float(x[1]) for x in asks if float(x[0]) <= a0 * 1.0015)

                restante_usd = monto_orden_usd
                tokens_acum = 0.0
                for px_s, qty_s in asks:
                    px, qty = float(px_s), float(qty_s)
                    nivel_usd = px * qty
                    if nivel_usd >= restante_usd:
                        tokens_acum += restante_usd / px
                        restante_usd = 0.0
                        break
                    else:
                        tokens_acum += qty
                        restante_usd -= nivel_usd

                if restante_usd > 0 or tokens_acum <= 0:
                    slippage_est_pct = 0.99
                else:
                    precio_vwap = monto_orden_usd / tokens_acum
                    slippage_est_pct = round(((precio_vwap - a0) / a0) * 100.0, 3)

                asks_techo = [float(x[0]) * float(x[1]) for x in asks if float(x[0]) <= a0 * 1.035]
                muro_vendedor = False
                if len(asks_techo) >= 4:
                    prom_ask = sum(asks_techo) / len(asks_techo)
                    if prom_ask > 0 and max(asks_techo) >= prom_ask * 4.2:
                        muro_vendedor = True

                liquidez_real_ok = (liq_ask_015 >= MIN_LIQUIDEZ_TOP_ASK_USD and slippage_est_pct <= MAX_SLIPPAGE_EST_PCT)
                sano = (spread <= 0.40 and ratio >= 1.05 and not muro_vendedor and liquidez_real_ok)
                return {
                    "ok": True,
                    "spread_pct": round(spread, 3),
                    "ratio_ba": ratio,
                    "liq_ask_015_usd": round(liq_ask_015, 0),
                    "slippage_est_pct": slippage_est_pct,
                    "liquidez_real_ok": liquidez_real_ok,
                    "muro_vendedor": muro_vendedor,
                    "sano": sano
                }
        except Exception:
            continue
    return {
        "ok": False, "spread_pct": 0.1, "ratio_ba": 1.0, "liq_ask_015_usd": 0.0,
        "slippage_est_pct": 0.99, "liquidez_real_ok": False, "muro_vendedor": False, "sano": False
    }

def analizar_velas_tf(session, symbol, interval="1h", limit=48):
    """Analiza RSI, Volumen, impulso en 3 velas, rachas, rechazo de mecha (>60%) y Fibonacci."""
    for base_url in BINANCE_API_BASES:
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
                var_3velas = round(((cierres[-1] - aperturas[-3]) / aperturas[-3]) * 100, 2) if len(aperturas) >= 3 and aperturas[-3] > 0 else var_ultima

                velas_rojas_seg = 0
                for idx_v in range(len(cierres) - 1, -1, -1):
                    if cierres[idx_v] < aperturas[idx_v]:
                        velas_rojas_seg += 1
                    else:
                        break

                velas_verdes_seg = 0
                for idx_v in range(len(cierres) - 1, -1, -1):
                    if cierres[idx_v] > aperturas[idx_v]:
                        velas_verdes_seg += 1
                    else:
                        break

                rango_vela = maximos[-1] - minimos[-1]
                mecha_sup = maximos[-1] - max(cierres[-1], aperturas[-1])
                rechazo_techo = (rango_vela > 0 and (mecha_sup / rango_vela) >= 0.60)

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

                    en_zona_dorada = (0.35 <= ratio_retroceso <= 0.62)
                    en_tramo_alcista = (0.12 <= ratio_retroceso < 0.35)
                    en_soporte_profundo = (ratio_retroceso > 0.62)
                    en_punta_extendida = (ratio_retroceso < 0.12)
                    cerca_ext_1618 = (p_act >= ext_1618 * 0.985)

                    if en_zona_dorada:
                        zona_txt = f"Zona Dorada Fib ({ratio_retroceso:.2f})"
                    elif en_soporte_profundo:
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
                        "en_tramo_alcista": en_tramo_alcista,
                        "en_soporte_profundo": en_soporte_profundo,
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
                    "var_3velas": var_3velas,
                    "velas_rojas_seg": velas_rojas_seg,
                    "velas_verdes_seg": velas_verdes_seg,
                    "rechazo_techo": rechazo_techo,
                    "fib": fib_data
                }
        except Exception:
            continue
    return {
        "ok": False, "rsi": 50.0, "vol_ratio": 1.0, "var_ultima": 0.0,
        "var_3velas": 0.0, "velas_rojas_seg": 0, "velas_verdes_seg": 0,
        "rechazo_techo": False, "fib": {"ok": False}
    }

def verificar_clima_y_regimen_mercado(session, mapa_mkt):
    """Evalúa clima BTC e Interruptor de Pánico 1H <= -1.0% + amplitud del mercado Spot."""
    btc = mapa_mkt.get("BTCUSDT")
    if not btc:
        return True, False, MAX_MONEDAS_SEMANA, "BTC estable | Régimen normal (hasta 4 cupos de 25%)"

    chg_24h = float(btc["cambio_24h"])
    mom_btc = analizar_velas_tf(session, "BTCUSDT", "1h", 24)
    rsi_btc = float(mom_btc.get("rsi", 50.0))
    var_1h_btc = float(mom_btc.get("var_ultima", 0.0))

    liquidas = [v for k, v in mapa_mkt.items() if k != "BTCUSDT" and v.get("vol_24h", 0) >= 1_500_000]
    verdes_mkt = sum(1 for v in liquidas if v.get("cambio_24h", 0) > 0)
    pct_verdes = round((verdes_mkt / len(liquidas)) * 100, 1) if liquidas else 50.0

    cupos_max = CUPOS_MODO_DEFENSIVO if pct_verdes < 30.0 else MAX_MONEDAS_SEMANA
    regimen_txt = f"Amplitud Verde: {pct_verdes}% (máx {cupos_max} cupos de 25%)"

    panico_1h = (var_1h_btc <= -1.0)
    if panico_1h or chg_24h <= -2.0 or rsi_btc < 35.0:
        motivo = (
            f"BTC en alerta (1h: {var_1h_btc:+.2f}%, 24h: {chg_24h:+.2f}%, RSI 1h: {rsi_btc}) | {regimen_txt}. Compras pausadas."
        )
        return False, panico_1h, cupos_max, motivo

    return True, False, cupos_max, f"BTC estable (1h: {var_1h_btc:+.2f}%, 24h: {chg_24h:+.2f}%, RSI 1h: {rsi_btc}) | {regimen_txt}"

def verificar_circuit_breaker_diario(plan, ahora_dt=None):
    """Congela compras 8h si se acumulan 3 stops seguidos o -$65 USD de pérdida diaria realizada."""
    ahora_dt = ahora_dt or ahora_art()
    cb_hasta_iso = plan.get("circuit_breaker_hasta_iso", "")
    if cb_hasta_iso:
        try:
            dt_cb = datetime.fromisoformat(cb_hasta_iso)
            if ahora_dt < dt_cb:
                restante_h = round((dt_cb - ahora_dt).total_seconds() / 3600.0, 1)
                return True, False, f"Circuit Breaker activo ({restante_h}h restantes hasta {dt_cb.strftime('%H:%M ART')})."
            else:
                plan["circuit_breaker_hasta_iso"] = ""
        except Exception:
            plan["circuit_breaker_hasta_iso"] = ""

    hoy_str = ahora_dt.strftime("%Y-%m-%d")
    cierres_hoy = [c for c in plan.get("historial_cierres", []) if str(c.get("fecha_cierre", "")).startswith(hoy_str)]
    if not cierres_hoy:
        return False, False, ""

    pnl_hoy = round(sum(float(c.get("pnl_usd", 0.0)) for c in cierres_hoy), 2)
    racha_roja = 0
    for c in reversed(cierres_hoy):
        if float(c.get("pnl_usd", 0.0)) < 0:
            racha_roja += 1
        else:
            break

    if pnl_hoy <= -MAX_PERDIDA_DIARIA_USD or racha_roja >= MAX_STOPS_SEGUIDOS_DIA:
        dt_fin = ahora_dt + timedelta(hours=HORAS_CONGELAMIENTO_CB)
        plan["circuit_breaker_hasta_iso"] = dt_fin.isoformat()
        motivo = (
            f"Pérdida diaria ${pnl_hoy:+.2f} USD | Racha {racha_roja} stops seguidos hoy. "
            f"Jefe Supervisor congela compras por {HORAS_CONGELAMIENTO_CB}h (hasta {dt_fin.strftime('%H:%M ART')})."
        )
        return True, True, motivo

    return False, False, ""

def cargar_plan_semanal():
    sem = id_semana_actual()
    base = {
        "semana_id": sem,
        "fecha_inicio": ahora_art().strftime("%Y-%m-%d %H:%M"),
        "modo": "CONSENSO_3_DE_3_ASISTENTE_TRADER_JEFE",
        "capital_total_usd": CAPITAL_INICIAL_PRUEBA,
        "meta_semanal_usd": META_SEMANAL_USD,
        "ganancia_realizada_usd": 0.0,
        "estado_semana": "ACTIVA",
        "fecha_cierre_meta": "",
        "aviso_btc_enviado": False,
        "ultimo_panico_btc_iso": "",
        "circuit_breaker_hasta_iso": "",
        "ultimo_reporte_hora": -1,
        "boletin_asistente": {},
        "auditoria_ia": {},
        "historial_auditorias": [],
        "alternativas_evaluadas": [],
        "posiciones": [],
        "historial_cierres": []
    }
    data = cargar_json_seguro(PLAN_SEMANAL_FILE)
    if data and data.get("semana_id") == sem:
        data.setdefault("aviso_btc_enviado", False)
        data.setdefault("ultimo_panico_btc_iso", "")
        data.setdefault("circuit_breaker_hasta_iso", "")
        data.setdefault("ultimo_reporte_hora", -1)
        data.setdefault("boletin_asistente", {})
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

def calcular_estadisticas_embudo(mapa_mkt, eco):
    reg_verdes = eco["reg_verdes"]
    graduadas = eco["graduadas"]

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

def limpiar_json_ia(raw_text):
    txt = raw_text.strip()
    if txt.startswith("```"):
        txt = txt.strip("`").strip()
        if txt.lower().startswith("json"):
            txt = txt[4:].strip()
    if "{" in txt and "}" in txt:
        txt = txt[txt.find("{"):txt.rfind("}") + 1]
    return json.loads(txt)

def llamar_gemini_con_reintento(client, prompt):
    for mod in MODELOS_GEMINI:
        try:
            res = client.models.generate_content(model=mod, contents=prompt)
            if res and res.text:
                return res.text
        except Exception as e_mod:
            print(f"⚠️ Modelo {mod} sin respuesta: {e_mod}")
            continue
    return None

# ==============================================================================
# NIVEL 2: TRADER (EMPLEADO — QUÉ MONEDAS ELEGIR, CUÁNDO ENTRAR Y CUÁNDO SALIR)
# ==============================================================================

def empleado_evaluar_palanca_emergencia(pos, v1m, v15, v1h, fib, ob, pnl_pct, max_pnl_pct, retroceso_desde_max, dossier_asistente):
    """El Trader evalúa en vivo cuándo pedir salida preventiva por invalidación técnica."""
    p_act = float(pos.get("precio_actual", 0))
    perdio_fib_618 = False
    if fib.get("ok"):
        perdio_fib_618 = (p_act < float(fib["fib_618"]) and float(fib["ratio"]) > 0.65)

    if dossier_asistente.get("alertada_en_perdedoras") and pnl_pct <= -1.0:
        return True, (
            f"🚨 SOLICITUD TRADER (Alerta Asistente/Perdedoras): marcada en baja en ecosistema previo y en {pnl_pct:+.2f}% neto."
        )

    if v1m.get("ok"):
        if (v1m["var_3velas"] <= -1.80 and v1m["vol_ratio"] >= 2.0) or (v1m["var_ultima"] <= -1.40 and v1m["vol_ratio"] >= 2.2):
            return True, (
                f"🚨 SOLICITUD TRADER 1M (Desplome en Vivo): caída {v1m['var_3velas']:+.2f}% en 3m "
                f"(vol {v1m['vol_ratio']}x) en {pnl_pct:+.2f}% neto."
            )

    p_ref_radar = float(dossier_asistente.get("precio_referencia_radar", 0))
    bajo_precio_radar = (p_ref_radar > 0 and p_act < p_ref_radar * 0.965)
    if pnl_pct <= -2.60 and (perdio_fib_618 or bajo_precio_radar):
        return True, (
            f"🚨 SOLICITUD TRADER (Tesis Invalidada): rompió Fib 0.618 / piso del radar en {pnl_pct:+.2f}% neto."
        )

    return False, ""

def empleado_evaluar_candidatas(session, mapa_mkt, excluidas, eco, plan):
    """
    NIVEL 2 (TRADER):
    Recibe el universo auditado por el Asistente (Cazador Táctico + Confirmación Pre-Explosión),
    y se enfoca 100% en operar: qué monedas elegir, cuándo entrar (timing 15m/1h/4h + liquidez real)
    y define el plan de salida (TP1 +6.5% / TP2 +15% / Runner 30% / Stop -3.40%).
    """
    graduadas = eco["graduadas"]
    posta_dict = eco["posta"]
    reg_verdes = eco["reg_verdes"]

    universo_syms = list(dict.fromkeys(list(graduadas.keys()) + list(posta_dict.keys()) + list(reg_verdes.keys())))
    if not universo_syms:
        return []

    cap_base_total = max(500.0, float(plan.get("capital_total_usd", CAPITAL_INICIAL_PRUEBA)) + float(plan.get("ganancia_realizada_usd", 0.0)))
    cupo_est_usd = round(cap_base_total / MAX_MONEDAS_SEMANA, 2)
    candidatos = []

    for sym in universo_syms:
        if sym not in mapa_mkt:
            continue
        mkt = mapa_mkt[sym]
        dossier = asistente_construir_dossier(sym, mkt["precio"], eco, plan)
        check_1_asistente = bool(dossier["tiene_respaldo_bots"])

        mom_1h = analizar_velas_tf(session, sym, "1h", 36)
        mom_4h = analizar_velas_tf(session, sym, "4h", 48)
        mom_15m = analizar_velas_tf(session, sym, "15m", 24) if check_1_asistente else {"ok": False, "rsi": 50.0, "var_ultima": 0.0, "var_3velas": 0.0, "vol_ratio": 1.0}
        fib_4h = mom_4h.get("fib", {})
        ob = auditar_order_book_semanal(session, sym, cupo_est_usd)

        var_radar = dossier["var_desde_deteccion_radar_pct"]
        prob = dossier["blindaje_pct"]
        cert_doble = dossier["doble_certificada"]
        etapa = dossier["etapa_cazador"]
        semaforo = dossier["semaforo_radar"]
        es_vip = dossier["carril_vip_radar"]
        es_reentrada = dossier["es_reentrada_habilitada"]

        lim_vela_15m = 6.5 if es_vip else 3.5
        lim_rsi_15m = 82.0 if es_vip else 75.0
        lim_3velas_15m = 9.5 if es_vip else 5.5

        fomo_15m = bool(mom_15m.get("ok")) and (
            float(mom_15m.get("rsi", 50.0)) > lim_rsi_15m
            or float(mom_15m.get("var_ultima", 0.0)) > lim_vela_15m
            or float(mom_15m.get("var_3velas", 0.0)) > lim_3velas_15m
        )

        reentrada_vol_ok = (not es_reentrada) or (max(float(mom_1h.get("vol_ratio", 1.0)), float(mom_15m.get("vol_ratio", 1.0))) >= 1.8)
        fib_sano = (not fib_4h.get("ok")) or (not fib_4h.get("en_soporte_profundo", False))

        vol_despegue = max(float(mom_1h.get("vol_ratio", 1.0)), float(mom_15m.get("vol_ratio", 1.0)))
        if es_vip:
            impulso_valido = (
                -3.5 <= var_radar <= 15.0
                and -1.2 <= mkt["cambio_24h"] <= 28.0
                and (mom_1h["var_3velas"] > -0.3 or mom_15m.get("var_ultima", 0.0) > 0.4)
                and vol_despegue >= 1.15
            )
        else:
            impulso_valido = (
                var_radar >= -0.5
                and 0.8 <= mkt["cambio_24h"] <= 25.0
                and (mom_1h["var_3velas"] > 0.0 or mom_1h["var_ultima"] > 0.0)
                and mom_1h["vol_ratio"] >= 1.05
            )

        bono_cadena = 18 if (dossier["cazador_en_verde"] and dossier["confirmada_pre_explosion"]) else (10 if check_1_asistente else -20)
        bono_vip = 12 if es_vip else 0
        bono_cert = 16 if cert_doble else (10 if dossier["en_ganadoras_activo"] else 0)
        bono_confluencia = dossier["confluencia_multi_bot"] * 4
        bono_fib = 14 if fib_4h.get("en_zona_dorada") else (8 if fib_4h.get("en_tramo_alcista") else (-25 if not fib_sano else -4))
        bono_ob = 12 if ob.get("ratio_ba", 0) >= 1.40 and ob.get("sano") else (6 if ob.get("sano") else -25)
        bono_verde = 12 if impulso_valido else -18
        bono_fomo = -20 if fomo_15m else 4
        bono_hist = -45 if (dossier["alertada_en_perdedoras"] or dossier["reincidente_stop_semana"]) else (12 if "GANADORA" in dossier["estado_historial_ganadoras"] else 0)

        score = prob + bono_cadena + bono_vip + bono_cert + bono_confluencia + bono_ob + bono_fib + bono_verde + bono_fomo + bono_hist + (6 if vol_despegue >= 1.35 else 0)

        rsi_1h_lim = 78.0 if es_vip else 74.0
        # Pilar 2: El Trader valida timing de entrada y liquidez real
        check_2_trader = (
            check_1_asistente
            and impulso_valido
            and reentrada_vol_ok
            and not fomo_15m
            and var_radar <= 15.0
            and fib_sano
            and mom_1h["rsi"] <= rsi_1h_lim
            and ob.get("sano", False)
            and (sym not in excluidas)
        )

        if dossier["cazador_en_verde"] and dossier["confirmada_pre_explosion"]:
            sello_txt = "🟢⚡ CAZADOR + PRE-EXPLOSIÓN"
        elif es_vip:
            sello_txt = f"🚀 CARRIL VIP ({semaforo})"
        elif cert_doble:
            sello_txt = "🛡️🛡️ DOBLE CERT. IA"
        elif dossier["en_ganadoras_activo"]:
            sello_txt = "🏆 GANADORAS RADAR"
        else:
            sello_txt = f"Cazador E{etapa} (Sin Confirmar)"

        fib_tag = f" | {fib_4h.get('zona_txt', 'Fib N/D')}" if fib_4h.get("ok") else ""
        muro_tag = " [⚠️MURO]" if ob.get("muro_vendedor") else ""
        liq_tag = f" | Liq0.15%: ${int(ob.get('liq_ask_015_usd', 0)):,}" if ob.get("ok") else ""
        fomo_tag = f" | ⏳ Anti-FOMO 15m (RSI {mom_15m.get('rsi')}, {mom_15m.get('var_ultima'):+.1f}%)" if fomo_15m else ""
        reent_tag = " | 🔄 Re-entrada Vol>=1.8x" if es_reentrada else ""

        plan_trader_txt = (
            f"Entrada {formatear_precio(mkt['precio'])} | TP1 +{TP1_ASEGURAR_PCT}% / TP2 +{TP2_ASEGURAR_PCT}% / Trail -{TRAILING_RUNNER_PCT}% | Stop {STOP_LOSS_FIJO_PCT}%"
            if check_2_trader
            else "Espera ventana técnica de entrada"
        )
        motivo_tecnico = (
            f"{sello_txt} ({var_radar:+.1f}% radar | Vol {vol_despegue}x) | "
            f"OB: {ob['ratio_ba']}x{muro_tag}{liq_tag} | RSI 1h: {mom_1h['rsi']}{fib_tag}{fomo_tag}{reent_tag}"
        )

        if not check_1_asistente:
            jefe_ver_init = dossier["dictamen_asistente"]
        elif fomo_15m:
            jefe_ver_init = f"⏳ Trader espera retroceso 15m (Anti-FOMO RSI {mom_15m.get('rsi')})"
        elif es_reentrada and not reentrada_vol_ok:
            jefe_ver_init = f"⏳ Trader exige vol >= 1.8x para re-entrar (actual {vol_despegue}x)"
        elif not check_2_trader:
            jefe_ver_init = "⏳ Trader aún no ve timing óptimo de entrada (volumen / OB / RSI)"
        else:
            jefe_ver_init = "⏳ Asistente OK + Trader OK ➔ Pendiente 3ª firma del Jefe"

        candidatos.append({
            "symbol": sym,
            "base": sym[:-4],
            "precio_entrada": mkt["precio"],
            "origen": sello_txt,
            "probabilidad": prob,
            "score": score,
            "certificada_doble": cert_doble,
            "carril_vip_radar": es_vip,
            "check_1_asistente": check_1_asistente,
            "check_2_trader": check_2_trader,
            "check_3_jefe": False,
            "consenso_3_de_3": False,
            "asistente_validado": check_1_asistente,
            "asistente_dictamen": dossier["dictamen_asistente"],
            "plan_trader_entrada": plan_trader_txt,
            "fomo_15m": fomo_15m,
            "propuesta_trader_ia": check_2_trader,
            "en_zona": False,
            "jefe_veredicto": jefe_ver_init,
            "jefe_factibilidad_pct": 0,
            "ya_en_cartera": sym in excluidas,
            "motivo_tecnico": motivo_tecnico,
            "expediente_previo": dossier,
            "ob": ob,
            "mom": mom_1h,
            "mom_15m": mom_15m,
            "fib_4h": fib_4h
        })

    candidatos.sort(key=lambda x: (x["check_2_trader"], x["check_1_asistente"], x["carril_vip_radar"], x["score"]), reverse=True)
    return candidatos[:TOP_ALTERNATIVAS_MOSTRAR]

def ejecutar_empleado_trader_ia(session, mapa_mkt, plan, clima_btc_txt, lecturas_tecnicas, boletin_asistente, eco):
    """NIVEL 2 (TRADER): Gestiona timing de salida de posiciones abiertas en Modo Runner 3 Tramos."""
    posiciones = plan.get("posiciones", [])
    datos_posiciones = []

    for p in posiciones:
        sym = p["symbol"]
        tec = lecturas_tecnicas.get(sym, {})
        v1m = tec.get("v1m") or analizar_velas_tf(session, sym, "1m", 30)
        v15 = tec.get("v15") or analizar_velas_tf(session, sym, "15m", 24)
        v1h = tec.get("v1h") or analizar_velas_tf(session, sym, "1h", 36)
        fib = tec.get("fib") or {}
        dossier = tec.get("expediente_previo") or asistente_construir_dossier(sym, float(p.get("precio_actual", 0)), eco, plan)

        p["expediente_previo_resumen"] = dossier["resumen_corto"]
        p["asistente_dictamen"] = dossier["dictamen_asistente"]

        p_ent = float(p.get("precio_entrada", 0))
        p_max = float(p.get("precio_maximo", p_ent))
        p_act = float(p.get("precio_actual", p_ent))
        retroceso_max = round(((p_act - p_max) / p_max) * 100, 2) if p_max > 0 else 0.0

        pnl_pct = float(p.get("pnl_pct", 0.0))
        pnl_usd = float(p.get("pnl_usd", 0.0))
        max_dd_pct = float(p.get("max_drawdown_pct", min(0.0, pnl_pct)))
        stop_act = float(p.get("stop_actual_pct", STOP_LOSS_FIJO_PCT))

        fib_resumen = "Fib N/D"
        perdio_fib_618 = False
        if fib.get("ok"):
            fib_resumen = f"{fib['zona_txt']} | Sop 0.618: {formatear_precio(fib['fib_618'])} | Ext 1.618: {formatear_precio(fib['ext_1618'])}"
            perdio_fib_618 = (p_act < float(fib["fib_618"]) and float(fib["ratio"]) > 0.65)
        p["fib_lectura"] = fib_resumen

        es_ruido_1m = (abs(v1m["var_3velas"]) < 0.80 and v1m["vol_ratio"] < 1.6)
        pulso_1m_txt = f"1m: {v1m['var_3velas']:+.2f}% (3m) | RSI 1m: {v1m['rsi']} | Vol: {v1m['vol_ratio']}x"
        if es_ruido_1m:
            pulso_1m_txt += " [Ruido normal]"

        var_radar = dossier["var_desde_deteccion_radar_pct"]
        tesis_viva = (not perdio_fib_618) and (not dossier["alertada_en_perdedoras"])

        if dossier["alertada_en_perdedoras"]:
            orden_def = "🚨 SOLICITUD SALIDA (Alerta Asistente)"
            razon_def = f"Asistente detectó inclusión en Bot Perdedoras ({dossier['estado_historial_ganadoras']})."
        elif p.get("tp2_ejecutado", False):
            orden_def = f"🚀 RUNNER 30% ACTIVO (Trail -{TRAILING_RUNNER_PCT}%)"
            razon_def = f"TP1 (+{TP1_ASEGURAR_PCT}%) y TP2 (+{TP2_ASEGURAR_PCT}%) cobrados; 30% corriendo hacia +25%/+70%."
        elif p.get("tp1_ejecutado", False):
            orden_def = f"🟢 RUMBO A TP2 (+{TP2_ASEGURAR_PCT}% Neto)"
            razon_def = f"TP1 35% en caja; 65% protegido en BE +{stop_act:.2f}% buscando +{TP2_ASEGURAR_PCT}%."
        elif pnl_pct >= TP1_ASEGURAR_PCT * 0.85:
            orden_def = f"🟡 CERCA SALIDA PARCIAL TP1 (+{TP1_ASEGURAR_PCT}%)"
            razon_def = f"Impulso confirmado (+{pnl_pct:.1f}% neto): próximo a asegurar primer 35%."
        elif pnl_pct <= -2.40 or pnl_usd <= -PREALERTA_PERDIDA_USD or (pnl_pct <= -2.00 and not tesis_viva):
            orden_def = "⚠️ VIGILAR SALIDA / TESIS EN RIESGO"
            razon_def = f"PnL Neto {pnl_pct:+.2f}% (${pnl_usd:+.2f} USD | Stop {STOP_LOSS_FIJO_PCT}%) | {pulso_1m_txt}."
        else:
            proteccion_txt = f"Stop BE +{stop_act:.2f}% neto" if stop_act > 0 else f"Stop despegue {STOP_LOSS_FIJO_PCT:.2f}%"
            orden_def = "🟢 MANTENER POSICIÓN (RUNNER)"
            razon_def = f"Cadena OK ({var_radar:+.1f}% radar) | {pulso_1m_txt} | {proteccion_txt}."

        p["trader_ia_orden"] = orden_def
        p["trader_ia_razon"] = razon_def

        datos_posiciones.append({
            "moneda": p["base"],
            "dossier_asistente": dossier,
            "tesis_original_sigue_viva": tesis_viva,
            "pnl_neto_pct": pnl_pct,
            "pnl_neto_usd": pnl_usd,
            "max_drawdown_pct": max_dd_pct,
            "tp1_ejecutado": bool(p.get("tp1_ejecutado", False)),
            "tp2_ejecutado": bool(p.get("tp2_ejecutado", False)),
            "stop_proteccion_actual_pct": stop_act,
            "retroceso_desde_max_pct": retroceso_max,
            "pulso_en_vivo_1m": {
                "var_ultima_1m_pct": v1m["var_ultima"],
                "var_3min_pct": v1m["var_3velas"],
                "rsi_1m": v1m["rsi"],
                "vol_1m_ratio": v1m["vol_ratio"],
                "solo_ruido_sin_volumen": es_ruido_1m
            },
            "rsi_15m": v15["rsi"],
            "rsi_1h": v1h["rsi"],
            "fibonacci_4h": fib_resumen,
            "propuesta_base_empleado": orden_def
        })

    stats_emb = calcular_estadisticas_embudo(mapa_mkt, eco)
    real = float(plan.get("ganancia_realizada_usd", 0.0))
    flot = sum(float(p.get("pnl_usd", 0.0)) for p in posiciones)
    meta = float(plan.get("meta_semanal_usd", META_SEMANAL_USD))
    progreso_pct = round(((real + flot) / meta) * 100, 1) if meta > 0 else 0.0

    resumen_emb_txt = (
        f"{stats_emb['tasa_pct']}% acierto ({stats_emb['ganadas']}/{stats_emb['resueltas']} cerradas)"
        if stats_emb["resueltas"] > 0
        else f"{stats_emb['total']} señales activas en maduración"
    )
    macro_bots_txt = " | ".join(boletin_asistente.get("alertas_macro", [])) or "Sin alertas externas negativas en JSON"

    auditoria_res = {
        "fecha": ahora_art().strftime("%Y-%m-%d %H:%M ART"),
        "semana_id": plan["semana_id"],
        "semaforo_meta": "🟢 EN CAMINO A META" if (real + flot) >= 0 else "🟡 EN CONSOLIDACIÓN",
        "factibilidad_pct": min(96, max(48, int(68 + (stats_emb["tasa_pct"] * 0.25) + ((real + flot) / 25.0)))),
        "diagnostico_24h": f"Consenso 3/3 (Cazador+PreExplosión -> Trader -> Jefe): {resumen_emb_txt}. {clima_btc_txt}. Avance: {progreso_pct}%.",
        "recomendacion_auditor": f"Compra solo si coinciden Asistente + Trader + Jefe (>= {FACTIBILIDAD_MINIMA_JEFE}%).",
        "veredicto_final_semana": plan.get("auditoria_ia", {}).get("veredicto_final_semana", "En seguimiento activo...")
    }

    if GEMINI_API_KEY and datos_posiciones:
        try:
            client = genai.Client(api_key=GEMINI_API_KEY)
            prompt = (
                "Eres el TRADER de una mesa Spot en Binance (PnL descontando 0.20% fees) en MODO RUNNER 3 TRAMOS (TP1 +6.5% 35%, TP2 +15% 35%, Runner 30% trailing 4.5%).\n"
                "Recibes todas las variables reales del ASISTENTE y debes definir el timing de salida para el JEFE SUPERVISOR:\n"
                f"BOLETÍN ASISTENTE: {boletin_asistente.get('resumen_ejecutivo', '')} | Macro: {macro_bots_txt}\n"
                f"CLIMA MERCADO: {clima_btc_txt}\n"
                f"AVANCE SEMANAL NETO: ${real + flot:+.2f} / ${meta:.0f} USD ({progreso_pct}%)\n"
                f"POSICIONES:\n{json.dumps(datos_posiciones, ensure_ascii=False)}\n\n"
                "Responde ÚNICAMENTE en JSON válido sin bloques markdown:\n"
                '{"semaforo_meta":"🟢 FACTIBLE | 🟡 EN OBSERVACIÓN | 🔴 RIESGO","factibilidad_pct":82,'
                '"diagnostico_24h":"análisis técnico breve en 1 oración",'
                '"recomendacion_auditor":"recomendación operativa para el Jefe",'
                '"ordenes":{"MONEDA":{"orden":"🟢 MANTENER POSICIÓN | 🟡 CERCA SALIDA TP1/TP2 | 🚨 SOLICITUD SALIDA | ⚠️ VIGILAR SALIDA","razon":"motivo técnico citando variables del asistente y pulso 1m/15m"}}}'
            )
            raw_ia = llamar_gemini_con_reintento(client, prompt)
            if raw_ia:
                ia_json = limpiar_json_ia(raw_ia)
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
        except Exception as e:
            print(f"⚠️ Fallback Trader IA: {e}")

    plan["auditoria_ia"] = auditoria_res
    return auditoria_res

# ==============================================================================
# NIVEL 3: JEFE SUPERVISOR (REVISA TODO Y EXIGE COINCIDENCIA 3/3 PARA COMPRAR)
# ==============================================================================

def ejecutar_jefe_supervisor_ia(plan, alternativas, posiciones_revisar, boletin_asistente, clima_btc_txt):
    """
    NIVEL 3 (JEFE SUPERVISOR):
    Revisa TODA la información del Asistente (Cazador + Confirmación Pre-Explosión + Autopsia 24h)
    y del Trader (timing de entrada/salida y liquidez).
    Solo habilita compra si las 3 informaciones coinciden (CONSENSO 3/3).
    """
    propuestas_compra = [a for a in alternativas if a.get("check_1_asistente") and a.get("check_2_trader")]
    cierres_sem = [c for c in plan.get("historial_cierres", []) if c.get("semana_id") == plan["semana_id"]]
    real = float(plan.get("ganancia_realizada_usd", 0.0))
    flot = sum(float(p.get("pnl_usd", 0.0)) for p in plan.get("posiciones", []))
    balance_neto = round(real + flot, 2)
    meta = float(plan.get("meta_semanal_usd", META_SEMANAL_USD))

    autopsia_info = boletin_asistente.get("autopsia_24h", {})
    stops_prematuros_sem = int(autopsia_info.get("stops_prematuros_semana", 0))

    for alt in propuestas_compra:
        dossier = alt.get("expediente_previo", {})
        ob = alt.get("ob", {})
        mom = alt.get("mom", {})
        fib = alt.get("fib_4h", {})

        fact = 62
        if dossier.get("cazador_en_verde") and dossier.get("confirmada_pre_explosion"):
            fact += 12
        if dossier.get("doble_certificada"):
            fact += 12
        elif dossier.get("en_ganadoras_activo"):
            fact += 8
        fact += int(dossier.get("confluencia_multi_bot", 0)) * 2
        if float(ob.get("ratio_ba", 1.0)) >= 1.25 and ob.get("liquidez_real_ok") and not ob.get("muro_vendedor"):
            fact += 8
        if fib.get("en_zona_dorada") or fib.get("en_tramo_alcista"):
            fact += 6
        if float(mom.get("vol_ratio", 1.0)) >= 1.25:
            fact += 5
        if balance_neto < -250.0 and not dossier.get("carril_vip_radar"):
            fact -= 15
        if float(mom.get("rsi", 50.0)) > 72.0 and not dossier.get("carril_vip_radar"):
            fact -= 8

        fact = max(35, min(96, fact))
        check_3_jefe = (fact >= FACTIBILIDAD_MINIMA_JEFE)
        consenso_3_3 = bool(alt.get("check_1_asistente") and alt.get("check_2_trader") and check_3_jefe)

        alt["jefe_factibilidad_pct"] = fact
        alt["check_3_jefe"] = check_3_jefe
        alt["consenso_3_de_3"] = consenso_3_3
        alt["en_zona"] = consenso_3_3

        if consenso_3_3:
            alt["jefe_veredicto"] = (
                f"✅ CONSENSO 3/3 ({fact}%): Asistente (Cazador+PreExplosión) + Trader (OB {ob.get('ratio_ba', 1.0)}x) + Jefe coinciden."
            )
        else:
            alt["jefe_veredicto"] = f"⛔ SIN CONSENSO 3/3 — JEFE VETA ({fact}% < {FACTIBILIDAD_MINIMA_JEFE}%): exige mayor margen con balance ${balance_neto:+.0f}."

    for item_pos in posiciones_revisar:
        pos = item_pos["pos"]
        if item_pos.get("propuesta_cierre_palanca"):
            tesis_viva = item_pos.get("tesis_viva", True)
            pnl_p = float(pos.get("pnl_pct", 0.0))
            umbral_veto_jefe = -2.90 if stops_prematuros_sem >= 1 else -2.50
            if tesis_viva and pnl_p > umbral_veto_jefe:
                item_pos["cierre_aprobado_jefe"] = False
                pos["jefe_orden"] = "🛡️ VETO JEFE: MANTENER RUNNER"
                pos["jefe_razon"] = (
                    f"Jefe veta salida anticipada en {pnl_p:+.2f}% (Autopsia: {stops_prematuros_sem} stops prematuros sem): "
                    f"confirmación Pre-Explosión intacta."
                )
            else:
                item_pos["cierre_aprobado_jefe"] = True
                pos["jefe_orden"] = "✅ SALIDA APROBADA POR JEFE"
                pos["jefe_razon"] = f"Jefe coincide con Trader en salida preventiva ({pnl_p:+.2f}%): tesis invalidada."
        else:
            pos["jefe_orden"] = "✅ CONSENSO 3/3 ACTIVO"
            pos["jefe_razon"] = f"Jefe valida gestión del Trader (TP1 +{TP1_ASEGURAR_PCT}% | TP2 +{TP2_ASEGURAR_PCT}% | Stop {STOP_LOSS_FIJO_PCT}%)."

    if GEMINI_API_KEY and (propuestas_compra or posiciones_revisar):
        try:
            client = genai.Client(api_key=GEMINI_API_KEY)
            resumen_propuestas = [
                {
                    "moneda": a["base"],
                    "score_trader": a["score"],
                    "variables_asistente_cazador_preexplosion": a["expediente_previo"],
                    "plan_entrada_salida_trader": a["plan_trader_entrada"],
                    "tecnicos_trader": a["motivo_tecnico"],
                    "order_book_y_slippage": a["ob"]
                }
                for a in propuestas_compra
            ]
            resumen_cartera = [
                {
                    "moneda": it["pos"]["base"],
                    "pnl_neto_pct": it["pos"]["pnl_pct"],
                    "pnl_neto_usd": it["pos"]["pnl_usd"],
                    "tp1_ejecutado": bool(it["pos"].get("tp1_ejecutado")),
                    "tp2_ejecutado": bool(it["pos"].get("tp2_ejecutado")),
                    "orden_trader": it["pos"].get("trader_ia_orden", ""),
                    "razon_trader": it["pos"].get("trader_ia_razon", ""),
                    "pide_cierre_anticipado": bool(it.get("propuesta_cierre_palanca")),
                    "motivo_cierre_trader": it["motivo_palanca"],
                    "tesis_viva": it["tesis_viva"],
                    "variables_asistente": it["exp_previo"]
                }
                for it in posiciones_revisar
            ]
            ultimos_cierres = [
                {
                    "moneda": c.get("base"),
                    "pnl_usd": c.get("pnl_usd"),
                    "autopsia_24h": c.get("veredicto_autopsia", "Sin autopsia"),
                    "motivo": c.get("motivo_cierre", "")[:70]
                }
                for c in cierres_sem[-8:]
            ]

            prompt_jefe = (
                "Eres el JEFE SUPERVISOR DE INVERSIONES en una mesa de 3 niveles con REGLA DE TRIPLE COINCIDENCIA (CONSENSO 3/3):\n"
                "1) ASISTENTE: reúne todas las variables reales (Cazador Táctico detecta en verde -> Pre-Explosión confirma -> filtros históricos + Autopsia 24h).\n"
                "2) TRADER: eligió qué monedas operar de ese grupo y definió cuándo entrar y cuándo salir (timing + liquidez real).\n"
                "3) JEFE SUPERVISOR (TÚ): revisas TODA la información del Asistente y del Trader. Solo apruebas compra ('aprobada': true, 'factibilidad_pct' >= 75) si las 3 informaciones coinciden sin contradicciones.\n"
                "- En CARTERA ABIERTA: Protege el recorrido hacia TP2 (+15%) y Runner (+25%/+70%). Si el Trader pide cierre anticipado ('pide_cierre_anticipado': true) y la tesis sigue viva, VETA salidas por ruido menor ('aprobar_cierre': false).\n\n"
                f"BOLETÍN Y AUTOPSIA ASISTENTE: {json.dumps(boletin_asistente, ensure_ascii=False)}\n"
                f"ESTADO SEMANA {plan['semana_id']}: Balance Neto ${balance_neto:+.2f} / Meta ${meta:.0f} USD | {clima_btc_txt}\n"
                f"ÚLTIMOS CIERRES Y AUTOPSIA 24H: {json.dumps(ultimos_cierres, ensure_ascii=False)}\n"
                f"CANDIDATAS CON ASISTENTE OK + TRADER OK:\n{json.dumps(resumen_propuestas, ensure_ascii=False)}\n"
                f"REVISIÓN CARTERA ACTIVA:\n{json.dumps(resumen_cartera, ensure_ascii=False)}\n\n"
                "Responde ÚNICAMENTE en JSON válido sin bloques markdown:\n"
                '{"compras":{"MONEDA":{"aprobada":true,"factibilidad_pct":86,"veredicto":"✅ CONSENSO 3/3 (86%): motivo concreto"}},'
                '"cartera":{"MONEDA":{"aprobar_cierre":false,"orden_jefe":"🛡️ VETO JEFE: MANTENER RUNNER | ✅ SALIDA APROBADA POR JEFE","razon_jefe":"dictamen concreto del Jefe cruzando Asistente + Trader + Autopsia"}}}'
            )

            raw_jefe = llamar_gemini_con_reintento(client, prompt_jefe)
            if raw_jefe:
                j_json = limpiar_json_ia(raw_jefe)
                compras_j = j_json.get("compras", {})
                for alt in propuestas_compra:
                    dec = compras_j.get(alt["base"])
                    if isinstance(dec, dict) and "aprobada" in dec:
                        fact_ia = int(dec.get("factibilidad_pct", alt["jefe_factibilidad_pct"]))
                        check_3_ia = bool(dec["aprobada"]) and (fact_ia >= FACTIBILIDAD_MINIMA_JEFE)
                        consenso_ia = bool(alt.get("check_1_asistente") and alt.get("check_2_trader") and check_3_ia)
                        alt["jefe_factibilidad_pct"] = fact_ia
                        alt["check_3_jefe"] = check_3_ia
                        alt["consenso_3_de_3"] = consenso_ia
                        alt["en_zona"] = consenso_ia
                        prefijo = f"✅ CONSENSO 3/3 ({fact_ia}%)" if consenso_ia else f"⛔ JEFE VETA ({fact_ia}%)"
                        txt_v = str(dec.get("veredicto", "")).strip()
                        alt["jefe_veredicto"] = txt_v[:175] if txt_v else prefijo

                cartera_j = j_json.get("cartera", {})
                for it in posiciones_revisar:
                    pos = it["pos"]
                    dec_p = cartera_j.get(pos["base"])
                    if isinstance(dec_p, dict):
                        if "aprobar_cierre" in dec_p:
                            it["cierre_aprobado_jefe"] = bool(dec_p["aprobar_cierre"])
                        if dec_p.get("orden_jefe"):
                            pos["jefe_orden"] = str(dec_p["orden_jefe"])[:45]
                        if dec_p.get("razon_jefe"):
                            pos["jefe_razon"] = str(dec_p["razon_jefe"])[:180]
        except Exception as e:
            print(f"⚠️ Fallback Jefe Supervisor IA: {e}")

def generar_veredicto_final_ia(plan):
    cierres = [c for c in plan.get("historial_cierres", []) if c.get("semana_id") == plan["semana_id"]]
    ganadoras = [c for c in cierres if float(c.get("pnl_usd", 0)) > 0]
    perdedoras = [c for c in cierres if float(c.get("pnl_usd", 0)) <= 0]
    win_rate = round((len(ganadoras) / len(cierres)) * 100, 1) if cierres else 100.0
    total_usd = float(plan.get("ganancia_realizada_usd", 0.0))
    meta_usd = float(plan.get("meta_semanal_usd", META_SEMANAL_USD))

    veredicto_base = (
        f"✅ <b>VEREDICTO: META LOGRADA — CONSENSO 3/3 (ASISTENTE + TRADER + JEFE) FACTIBLE</b>\n"
        f"• Se alcanzaron <b>${total_usd:,.2f} USD netos</b> (Meta: ${meta_usd:,.0f} USD) con <b>{win_rate}% de acierto</b> "
        f"({len(ganadoras)} ganadoras / {len(perdedoras)} cerradas en protección)."
    )

    if GEMINI_API_KEY and cierres:
        try:
            client = genai.Client(api_key=GEMINI_API_KEY)
            prompt = (
                "Eres el Jefe Supervisor de una mesa Spot en Binance operada por Consenso 3/3 (Asistente [Cazador+PreExplosión] -> Trader -> Jefe). "
                "Cumplimos la meta semanal neta. Da un VEREDICTO FINAL DE FACTIBILIDAD para pasar a dinero real en máximo 4 líneas en español.\n"
                f"Capital Base: ${plan.get('capital_total_usd', 3500)} USD | Meta: ${meta_usd} USD | Ganancia Neta Lograda: ${total_usd} USD\n"
                f"Operaciones cerradas: {json.dumps(cierres, ensure_ascii=False)}"
            )
            raw_ver = llamar_gemini_con_reintento(client, prompt)
            if raw_ver:
                return f"👔 <b>DICTAMEN FINAL JEFE SUPERVISOR IA:</b>\n{html.escape(raw_ver.strip())}"
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

    categorias = ["Cerrada\n(Caja Neta)", "Flotante\n(Neta)", "Total\nSemana"]
    valores = [realizada, flotante, total_actual]
    colores = ["#00e676" if v >= 0 else "#ff1744" for v in valores]

    bars1 = ax1.bar(categorias, valores, color=colores, width=0.45, zorder=3)
    ax1.axhline(meta, color="#ffd600", linestyle="--", linewidth=1.8, zorder=4, label=f"Meta: ${meta:.0f}")
    ax1.axhline(0, color="#475569", linewidth=1.0, zorder=2)
    lim_sup = max(meta * 1.25, total_actual * 1.25, 150)
    lim_inf = min(-160, total_actual * 1.25)
    ax1.set_ylim(lim_inf, lim_sup)
    ax1.grid(True, axis="y", color="#1e293b", linewidth=0.7, zorder=1)
    ax1.tick_params(colors="white", labelsize=8.5)
    ax1.set_title("PROGRESO CUOTA NETA (-0.20% FEES)", color="#ffd600", fontsize=9.8, fontweight="bold", pad=10)
    ax1.legend(loc="upper left", facecolor="#0b132b", edgecolor="#ffd600", labelcolor="white", fontsize=8)

    for b, v in zip(bars1, valores):
        yv = b.get_height()
        offset = 18 if yv >= 0 else -24
        ax1.text(b.get_x() + b.get_width() / 2.0, yv + offset, f"${v:+.1f}", ha="center", va="center", color="white", fontweight="bold", fontsize=8.5)

    posiciones = plan.get("posiciones", [])
    stop_ref_pct = STOP_LOSS_FIJO_PCT
    if posiciones:
        nombres = [p["base"] for p in posiciones]
        pnls = [float(p.get("pnl_pct", 0.0)) for p in posiciones]
        objs = [float(p.get("subida_necesaria_pct", 17.14)) for p in posiciones]
        x = range(len(nombres))

        ax2.bar([i - 0.17 for i in x], objs, width=0.32, color="#334155", edgecolor="#94a3b8", label="Meta Semanal (%)", zorder=2)
        bars_act = ax2.bar([i + 0.17 for i in x], pnls, width=0.32, color=["#00e676" if v >= 0 else "#ff1744" for v in pnls], zorder=3, label="Actual Neto (%)")
        ax2.axhline(0, color="#475569", linewidth=1.0)
        ax2.axhline(TP1_ASEGURAR_PCT, color="#00e676", linestyle="--", linewidth=1.1, label=f"TP1 (+{TP1_ASEGURAR_PCT}%)")
        ax2.axhline(TP2_ASEGURAR_PCT, color="#38bdf8", linestyle="--", linewidth=1.1, label=f"TP2 (+{TP2_ASEGURAR_PCT}%)")
        ax2.axhline(stop_ref_pct, color="#ff1744", linestyle=":", linewidth=1.3, label=f"Stop ({stop_ref_pct}%)")
        max_y = max(max(objs + [20]) * 1.28, 24)
        min_y = min(min(pnls + [stop_ref_pct]) * 1.45, -5.5)
        ax2.set_ylim(min_y, max_y)
        ax2.set_xticks(list(x))
        ax2.set_xticklabels(nombres, color="white", fontweight="bold", fontsize=9.5)
        ax2.tick_params(axis="y", colors="white", labelsize=8.5)
        ax2.grid(True, axis="y", color="#1e293b", linewidth=0.7, zorder=1)
        ax2.legend(loc="upper right", facecolor="#0b132b", edgecolor="#334155", labelcolor="white", fontsize=7.0)

        for b, v, p_obj in zip(bars_act, pnls, posiciones):
            yv = b.get_height()
            etq_tp = "Runner 30%" if p_obj.get("tp2_ejecutado") else (f"TP2 +{TP2_ASEGURAR_PCT}%" if p_obj.get("tp1_ejecutado") else f"TP1 +{TP1_ASEGURAR_PCT}%")
            ax2.text(b.get_x() + b.get_width() / 2.0, yv + (0.8 if yv >= 0 else -1.1), f"{v:+.2f}%\n({etq_tp})", ha="center", va="bottom" if yv >= 0 else "top", color="white", fontweight="bold", fontsize=7.6)
    else:
        ax2.text(0.5, 0.5, "Sin posiciones abiertas\n(Esperando Consenso 3/3: Asistente + Trader + Jefe)", ha="center", va="center", color="#94a3b8", fontsize=10, transform=ax2.transAxes)
        ax2.tick_params(left=False, labelleft=False, bottom=False, labelbottom=False)

    aud = plan.get("auditoria_ia", {})
    fact_txt = f" | Jefe IA: {aud.get('factibilidad_pct', 80)}% Factible" if aud else ""
    ax2.set_title(f"CONSENSO 3/3 RUNNER ({len(posiciones)}/{MAX_MONEDAS_SEMANA} • CUPO 25%) • TP1 +{TP1_ASEGURAR_PCT}% | TP2 +{TP2_ASEGURAR_PCT}% | STOP {STOP_LOSS_FIJO_PCT}%", color="#00e676", fontsize=8.5, fontweight="bold", pad=10)
    fig.suptitle(f"ETAPA 4 • ASISTENTE (CAZADOR+PREEXP) ➔ TRADER ➔ JEFE ({plan['semana_id']}){fact_txt} | {ahora_art().strftime('%d/%m %H:%M ART')}", color="white", fontsize=9.5, fontweight="bold", y=0.98)
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

    ws = wb.active
    ws.title = "1_CARTERA_Y_CONSENSO_3_3"
    headers = [
        "Semana", "Fecha Entrada", "Moneda", "Cadena Cazador + Pre-Explosión", "Variables Asistente (Ecosistema)", "Capital ($)",
        "Precio Entrada", "Precio Objetivo", "Subida Esperada (%)",
        "Precio Actual", "Máximo Alcanzado", "Max Drawdown (%)", "Rend. Neto (%)",
        "PnL Neto ($)", "Lectura Fibonacci 4H", "Operativa Trader (Entrada/Salida)", "Veredicto Jefe Supervisor", "Estado"
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
        dossier_txt = pos.get("asistente_dictamen") or pos.get("expediente_previo_resumen", "Sin dossier")
        prop_tr = f"{pos.get('trader_ia_orden', '🟢 MANTENER')} — {pos.get('trader_ia_razon', '')}".strip(" —")
        ver_jefe = pos.get("jefe_veredicto_entrada") or f"{pos.get('jefe_orden', '✅ CONSENSO 3/3')} — {pos.get('jefe_razon', '')}".strip(" —")
        ws.append([
            pos.get("semana_id", plan["semana_id"]),
            pos.get("fecha_entrada", ""),
            pos.get("base", ""),
            pos.get("motivo_eleccion", pos.get("origen", "")),
            dossier_txt,
            round(float(pos.get("capital_usd", 0)), 2),
            float(pos.get("precio_entrada", 0)),
            float(pos.get("precio_objetivo", 0)),
            round(float(pos.get("subida_necesaria_pct", 0)), 2),
            float(pos.get("precio_actual", 0)),
            float(pos.get("precio_maximo", 0)),
            round(float(pos.get("max_drawdown_pct", 0)), 2),
            round(float(pos.get("pnl_pct", 0)), 2),
            pnl_v,
            pos.get("fib_lectura", "Fib N/D"),
            prop_tr,
            ver_jefe,
            pos.get("estado", "")
        ])
        celda_pnl = ws.cell(row=row_idx, column=14)
        if pnl_v > 0:
            celda_pnl.fill = fill_verde
        elif pnl_v < 0:
            celda_pnl.fill = fill_rojo

    ws_alt = wb.create_sheet(title="2_ALTERNATIVAS_CONSENSO")
    headers_alt = [
        "Ranking", "Moneda", "1. Asistente (Cazador+PreExp)", "2. Trader (Timing/Liq)",
        "3. Jefe Supervisor", "Factibilidad Jefe (%)", "Precio Actual", "Decisión Final 3/3", "Plan Entrada/Salida y Auditoría"
    ]
    ws_alt.append(headers_alt)
    for col_idx in range(1, len(headers_alt) + 1):
        c = ws_alt.cell(row=1, column=col_idx)
        c.fill = fill_hdr
        c.font = font_hdr
        c.alignment = Alignment(horizontal="center")

    activas_syms = {p["symbol"] for p in plan.get("posiciones", [])}
    for idx, alt in enumerate(plan.get("alternativas_evaluadas", []), start=1):
        c1 = "✅ OK" if alt.get("check_1_asistente") else "⏳ FALTA"
        c2 = "✅ OK" if alt.get("check_2_trader") else "⏳ ESPERA"
        c3 = "✅ OK" if alt.get("check_3_jefe") else ("⛔ VETA" if (alt.get("check_1_asistente") and alt.get("check_2_trader")) else "—")

        if alt["symbol"] in activas_syms:
            estado_alt = "✅ CONSENSO 3/3 — COMPRADA"
        elif alt.get("consenso_3_de_3"):
            estado_alt = "🟢 CONSENSO 3/3 (En Reserva)"
        elif alt.get("check_1_asistente") and alt.get("check_2_trader"):
            estado_alt = "⛔ SIN CONSENSO (Jefe Vetó)"
        elif alt.get("check_1_asistente"):
            estado_alt = "⏳ FALTA TIMING DEL TRADER"
        else:
            estado_alt = "🚫 SIN CONFIRMACIÓN ASISTENTE"

        detalle_alt = f"{alt.get('jefe_veredicto', '')} | {alt.get('plan_trader_entrada', '')} | {alt.get('motivo_tecnico', '')}"
        ws_alt.append([
            idx, alt.get("base", ""), c1, c2, c3,
            alt.get("jefe_factibilidad_pct", 0), float(alt.get("precio_entrada", 0)), estado_alt, detalle_alt
        ])

    ws_aud = wb.create_sheet(title="3_AUDITORIA_IA_24H")
    headers_aud = ["Fecha Auditoría", "Semana", "Semáforo Meta", "Factibilidad (%)", "Diagnóstico Consenso 3/3", "Recomendación Jefe Supervisor", "Veredicto Final Semana"]
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

    ws2 = wb.create_sheet(title="4_RESUMEN_CUOTA")
    headers2 = ["Semana", "Fecha Inicio", "Capital Base ($)", "Meta Semanal ($)", "Ganancia Cerrada Neta ($)", "Ganancia Flotante Neta ($)", "Cumplimiento (%)", "Estado Semana"]
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

    ws_aut = wb.create_sheet(title="5_AUTOPSIA_POST_CIERRE")
    headers_aut = ["Semana", "Moneda", "Fecha Cierre", "PnL Cierre ($)", "Precio Cierre", "Máx 24h Post", "Mín 24h Post", "Var Máx Post (%)", "Dictamen Autopsia Asistente"]
    ws_aut.append(headers_aut)
    for col_idx in range(1, len(headers_aut) + 1):
        c = ws_aut.cell(row=1, column=col_idx)
        c.fill = fill_hdr
        c.font = font_hdr
        c.alignment = Alignment(horizontal="center")

    for c in reversed(plan.get("historial_cierres", [])):
        ws_aut.append([
            c.get("semana_id", ""),
            c.get("base", ""),
            c.get("fecha_cierre", ""),
            round(float(c.get("pnl_usd", 0.0)), 2),
            float(c.get("precio_actual", 0.0)),
            float(c.get("post_cierre_max", c.get("precio_actual", 0.0))),
            float(c.get("post_cierre_min", c.get("precio_actual", 0.0))),
            round(float(c.get("var_max_post_pct", 0.0)), 2),
            c.get("veredicto_autopsia", "⏳ Pendiente")
        ])

    for sheet in (ws, ws_alt, ws_aud, ws2, ws_aut):
        for col in sheet.columns:
            max_len = max(len(str(c.value or "")) for c in col)
            sheet.column_dimensions[col[0].column_letter].width = min(max_len + 4, 52)

    wb.save(EXCEL_SEMANAL_FILE)

def enviar_telegram_texto(texto):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return False
    url = f"{TELEGRAM_API_BASE}{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": texto.strip(), "parse_mode": "HTML", "disable_web_page_preview": True}
    if TELEGRAM_TOPIC_ID.isdigit():
        payload["message_thread_id"] = int(TELEGRAM_TOPIC_ID)
    try:
        r = requests.post(url, json=payload, timeout=15).json()
        if not r.get("ok") and "thread not found" in str(r.get("description", "")).lower():
            payload.pop("message_thread_id", None)
            r = requests.post(url, json=payload, timeout=15).json()
        return bool(r.get("ok"))
    except Exception as e:
        print(f"⚠️ Error Telegram Semanal: {e}")
        return False

def enviar_foto_telegram(imagen_path, caption):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID or not os.path.exists(imagen_path):
        return False
    url = f"{TELEGRAM_API_BASE}{TELEGRAM_BOT_TOKEN}/sendPhoto"
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
        return bool(r.get("ok"))
    except Exception as e:
        print(f"⚠️ Error enviando foto Semanal: {e}")
        return False

def enviar_excel_telegram(caption):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID or not os.path.exists(EXCEL_SEMANAL_FILE):
        return False
    url = f"{TELEGRAM_API_BASE}{TELEGRAM_BOT_TOKEN}/sendDocument"
    data = {"chat_id": TELEGRAM_CHAT_ID, "caption": caption[:1000], "parse_mode": "HTML"}
    if TELEGRAM_TOPIC_ID.isdigit():
        data["message_thread_id"] = int(TELEGRAM_TOPIC_ID)
    try:
        with open(EXCEL_SEMANAL_FILE, "rb") as f:
            r = requests.post(url, data=data, files={"document": f}, timeout=25).json()
            if not r.get("ok") and "thread not found" in str(r.get("description", "")).lower():
                data.pop("message_thread_id", None)
                f.seek(0)
                r = requests.post(url, data=data, files={"document": f}, timeout=25).json()
        return bool(r.get("ok"))
    except Exception as e:
        print(f"⚠️ Error enviando Excel Semanal: {e}")
        return False

def cooldown_panico_cumplido(ultimo_iso):
    if not ultimo_iso:
        return True
    try:
        dt_prev = datetime.fromisoformat(ultimo_iso)
        return (ahora_art() - dt_prev).total_seconds() >= (COOLDOWN_PANICO_BTC_MIN * 60)
    except Exception:
        return True

def construir_bloque_1_alternativas(plan):
    ahora_str = ahora_art().strftime("%Y-%m-%d %H:%M ART")
    alts = plan.get("alternativas_evaluadas", [])
    activas_syms = {p["symbol"] for p in plan.get("posiciones", [])}
    bol = plan.get("boletin_asistente", {})

    msg = (
        f"🔍 <b>GESTOR SEMANAL • BLOQUE 1/3: REGLA DE CONSENSO 3/3</b>\n"
        f"📅 <code>{ahora_str}</code> | Semana <code>{plan['semana_id']}</code>\n"
    )
    if bol.get("resumen_ejecutivo"):
        msg += f"🗂️ <i>{html.escape(bol['resumen_ejecutivo'])}</i>\n\n"
    else:
        msg += "\n"

    if not alts:
        msg += "⏳ <i>Aún no hay candidatas evaluadas en el radar.</i>"
        return msg.strip()

    for idx, a in enumerate(alts, start=1):
        c1 = "✅" if a.get("check_1_asistente") else "⏳"
        c2 = "✅" if a.get("check_2_trader") else "⏳"
        c3 = "✅" if a.get("check_3_jefe") else ("⛔" if (a.get("check_1_asistente") and a.get("check_2_trader")) else "—")
        checklist = f"<code>[1.Asist:{c1} | 2.Trader:{c2} | 3.Jefe:{c3}]</code>"

        if a["symbol"] in activas_syms:
            marca = "✅ <b>[CONSENSO 3/3 • COMPRADA]</b>"
        elif a.get("consenso_3_de_3"):
            marca = "🟢 <b>[CONSENSO 3/3 • EN RESERVA]</b>"
        elif a.get("check_1_asistente") and a.get("check_2_trader"):
            marca = "⛔ <b>[SIN CONSENSO • JEFE VETÓ]</b>"
        elif a.get("fomo_15m"):
            marca = "⏳ <i>[TRADER ESPERA RETROCESO 15M]</i>"
        elif a.get("check_1_asistente"):
            marca = "⏳ <i>[ASISTENTE OK • FALTA TIMING TRADER]</i>"
        else:
            marca = "🚫 <i>[FALTA CONFIRMACIÓN ASISTENTE]</i>"

        msg += (
            f"<b>{idx}. {a['base']}</b> (Score: <b>{a['score']}</b>) — {marca}\n"
            f"   • Consenso: {checklist} | Precio: <code>{formatear_precio(a['precio_entrada'])}</code>\n"
            f"   • {html.escape(a['motivo_tecnico'])}\n"
            f"   └ 👔 <i>{html.escape(a.get('jefe_veredicto', ''))}</i>\n"
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
        f"🏆 <b>GESTOR CONSENSO 3/3 (NETO FEES 0.20%) • BLOQUE 2/3</b>\n"
        f"{evento_titulo}\n"
        f"📅 <code>{ahora_str}</code> | Cuota: <code>${meta:,.0f} USD</code> | Progreso Neto: <b>${real + flot:+.2f} USD ({cump}%)</b>\n"
    )
    if aud:
        msg += (
            f"👔 <b>Auditoría Jefe IA:</b> <b>{html.escape(aud.get('semaforo_meta', ''))}</b> ({aud.get('factibilidad_pct', 80)}% factibilidad)\n"
            f"└ <i>{html.escape(aud.get('diagnostico_24h', ''))}</i>\n\n"
        )
    else:
        msg += "\n"

    if not plan["posiciones"]:
        msg += "⏳ <i>Sin posiciones abiertas en este momento (esperando coincidencia 3/3: Asistente + Trader + Jefe).</i>\n"
    else:
        for idx, p in enumerate(plan["posiciones"], start=1):
            uid = int(time.time() * 1000) + random.randint(1, 999)
            u_ia = f"{BASE_URL_NETLIFY}/?coin={p['base']}&price={p['precio_actual']}&v={p['base']}_{uid}"
            u_tr = f"{BINANCE_TRADE_BASE}{p['base']}_USDT"
            exp_res = html.escape(p.get("asistente_dictamen") or p.get("expediente_previo_resumen", p.get("origen", "")))
            fib_l = html.escape(p.get("fib_lectura", "Fib N/D"))
            orden_tr = html.escape(p.get("trader_ia_orden", "🟢 MANTENER"))
            razon_tr = html.escape(p.get("trader_ia_razon", ""))
            orden_jf = html.escape(p.get("jefe_orden", "✅ CONSENSO 3/3"))
            razon_jf = html.escape(p.get("jefe_razon", p.get("jefe_veredicto_entrada", "")))
            stop_act = float(p.get("stop_actual_pct", STOP_LOSS_FIJO_PCT))
            stop_label = f"🛡️ Stop Protegido: <code>+{stop_act:.2f}%</code>" if stop_act > 0 else f"Stop Despegue: <code>{stop_act:.2f}%</code>"

            if p.get("tp2_ejecutado"):
                tp_tag = f"🚀 TP1+TP2 cobrados (70%) | Runner 30% (Trail -{TRAILING_RUNNER_PCT}%)"
            elif p.get("tp1_ejecutado"):
                tp_tag = f"✅ TP1 35% cobrado | Busca TP2: <code>+{TP2_ASEGURAR_PCT}%</code>"
            else:
                tp_tag = f"TP1 35%: <code>+{TP1_ASEGURAR_PCT}%</code> | TP2 35%: <code>+{TP2_ASEGURAR_PCT}%</code>"

            dd_val = float(p.get("max_drawdown_pct", 0.0))

            msg += (
                f"🟢 <b>{idx}. {p['base']}</b> — Cupo Activo: <code>${p['capital_usd']:,.2f} USD</code>\n"
                f"• <b>Entrada:</b> <code>{formatear_precio(p['precio_entrada'])}</code> ➔ <b>Actual:</b> <code>{formatear_precio(p['precio_actual'])}</code> (<b>{p['pnl_pct']:+.2f}% neto</b> | <code>${p['pnl_usd']:+.2f}</code> | MaxDD: <code>{dd_val:.2f}%</code>)\n"
                f"• <b>Plan Salida Runner:</b> {tp_tag} | {stop_label} | <code>{fib_l}</code>\n"
                f"• <b>🗂️ 1. Asistente (Variables):</b> <i>{exp_res}</i>\n"
                f"• <b>🤖 2. Trader (Operativa):</b> <b>{orden_tr}</b> — <i>{razon_tr}</i>\n"
                f"• <b>👔 3. Jefe Supervisor:</b> <b>{orden_jf}</b> — <i>{razon_jf}</i>\n"
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

    # PASO 1 (NIVEL 1): EL ASISTENTE REÚNE TODAS LAS VARIABLES REALES (CAZADOR + PRE-EXPLOSIÓN + AUTOPSIA 24H)
    boletin_asistente, eco = ejecutar_asistente_inteligencia(mapa_mkt, plan)
    plan["boletin_asistente"] = boletin_asistente

    ahora_dt = ahora_art()
    ahora_str = ahora_dt.strftime("%Y-%m-%d %H:%M ART")
    alertas_venta = []
    alertas_parciales = []
    prealertas_palanca = []
    nuevas_entradas = []
    lecturas_tecnicas = {}

    if plan["estado_semana"] == "META_CUMPLIDA":
        print(f"✅ Semana {plan['semana_id']} ya tiene META CUMPLIDA. Modo protección activo.")
        return

    btc_ok, panico_btc_1h, cupos_max_regimen, msg_btc = verificar_clima_y_regimen_mercado(s, mapa_mkt)

    if panico_btc_1h and plan["posiciones"]:
        for p_prot in plan["posiciones"]:
            if float(p_prot.get("pnl_pct", 0.0)) >= 0.80:
                p_prot["forzar_be_panico_btc"] = True
        if cooldown_panico_cumplido(plan.get("ultimo_panico_btc_iso", "")):
            plan["ultimo_panico_btc_iso"] = ahora_dt.isoformat()
            enviar_telegram_texto(
                f"🚨 <b>INTERRUPTOR PÁNICO MACRO BTC (-1.0% EN 1H)</b>\n"
                f"📅 <code>{ahora_str}</code>\n\n"
                f"⚠️ {html.escape(msg_btc)}\n"
                f"🛡️ <i>Compras pausadas y Stops elevados automáticamente a Break-Even neto (+0.30%) en posiciones en verde.</i>"
            )

    # PASO 2 (NIVEL 1 -> NIVEL 2): EXPEDIENTES DEL ASISTENTE + LECTURA EN VIVO DEL TRADER
    posiciones_evaluadas = []
    for pos in plan["posiciones"]:
        sym = pos["symbol"]
        mkt = mapa_mkt.get(sym)
        if not mkt:
            posiciones_evaluadas.append({"pos": pos, "sin_datos": True})
            continue

        p_act = mkt["precio"]
        p_ent = float(pos["precio_entrada"])
        cap = float(pos["capital_usd"])
        cap_inicial = float(pos.setdefault("capital_inicial_usd", cap))
        p_max = max(float(pos.get("precio_maximo", p_ent)), p_act)

        var_bruta_pct = ((p_act - p_ent) / p_ent) * 100 if p_ent > 0 else 0.0
        max_bruta_pct = ((p_max - p_ent) / p_ent) * 100 if p_ent > 0 else 0.0
        pnl_pct = var_bruta_pct - COMISION_SPOT_TOTAL_PCT
        max_pnl_pct = max_bruta_pct - COMISION_SPOT_TOTAL_PCT
        pnl_usd = cap * (pnl_pct / 100.0)
        retroceso_desde_max = ((p_act - p_max) / p_max) * 100 if p_max > 0 else 0.0
        horas_abierta = calcular_horas_entre(pos.get("fecha_entrada", ""), ahora_dt)

        prev_dd = float(pos.get("max_drawdown_pct", 0.0))
        max_dd_pct = round(min(prev_dd, pnl_pct), 2)

        v1m = analizar_velas_tf(s, sym, "1m", 30)
        v15 = analizar_velas_tf(s, sym, "15m", 24)
        v1h = analizar_velas_tf(s, sym, "1h", 36)
        v4h = analizar_velas_tf(s, sym, "4h", 48)
        fib = v4h.get("fib", {}) if v4h.get("fib", {}).get("ok") else v1h.get("fib", {})
        ob = auditar_order_book_semanal(s, sym, cap)
        dossier_asistente = asistente_construir_dossier(sym, p_act, eco, plan)

        lecturas_tecnicas[sym] = {
            "v1m": v1m, "v15": v15, "v1h": v1h, "fib": fib, "ob": ob,
            "expediente_previo": dossier_asistente
        }

        stop_dinamico_pct = STOP_LOSS_FIJO_PCT
        if pos.get("tp2_ejecutado", False):
            stop_dinamico_pct = 8.0
        elif pos.get("tp1_ejecutado", False):
            stop_dinamico_pct = 4.0 if max_pnl_pct >= 11.0 else 0.50
        elif max_pnl_pct >= 5.0:
            stop_dinamico_pct = 0.40
        elif pos.get("forzar_be_panico_btc", False):
            stop_dinamico_pct = 0.30

        pos["precio_actual"] = p_act
        pos["precio_maximo"] = p_max
        pos["max_drawdown_pct"] = max_dd_pct
        pos["pnl_pct"] = round(pnl_pct, 2)
        pos["pnl_usd"] = round(pnl_usd, 2)
        pos["stop_actual_pct"] = stop_dinamico_pct
        pos["expediente_previo_resumen"] = dossier_asistente["resumen_corto"]
        pos["asistente_dictamen"] = dossier_asistente["dictamen_asistente"]
        pos.setdefault("motivo_eleccion", pos.get("origen", "🟢⚡ Cazador + Pre-Explosión"))

        if not pos.get("tp1_ejecutado", False) and pnl_pct >= TP1_ASEGURAR_PCT:
            cap_vendido_1 = round(min(cap * 0.5, cap_inicial * 0.35), 2)
            ganancia_tp1 = round(cap_vendido_1 * (pnl_pct / 100.0), 2)
            pos["capital_usd"] = round(cap - cap_vendido_1, 2)
            cap = pos["capital_usd"]
            pos["tp1_ejecutado"] = True
            pos["stop_actual_pct"] = 0.50
            stop_dinamico_pct = 0.50
            pos["pnl_usd"] = round(cap * (pnl_pct / 100.0), 2)
            plan["ganancia_realizada_usd"] = round(float(plan["ganancia_realizada_usd"]) + ganancia_tp1, 2)
            alertas_parciales.append({
                "tramo": "TP1 (35%)",
                "base": pos["base"],
                "pnl_pct": round(pnl_pct, 2),
                "ganancia_tp": ganancia_tp1,
                "precio_actual": p_act,
                "capital_restante": cap,
                "detalle_siguiente": f"65% restante protegido en BE (+0.50%) rumbo a TP2 (+{TP2_ASEGURAR_PCT}%)."
            })

        if pos.get("tp1_ejecutado", False) and not pos.get("tp2_ejecutado", False) and pnl_pct >= TP2_ASEGURAR_PCT:
            cap_vendido_2 = round(min(cap * 0.60, cap_inicial * 0.35), 2)
            ganancia_tp2 = round(cap_vendido_2 * (pnl_pct / 100.0), 2)
            pos["capital_usd"] = round(cap - cap_vendido_2, 2)
            cap = pos["capital_usd"]
            pos["tp2_ejecutado"] = True
            pos["stop_actual_pct"] = 8.0
            stop_dinamico_pct = 8.0
            pos["pnl_usd"] = round(cap * (pnl_pct / 100.0), 2)
            plan["ganancia_realizada_usd"] = round(float(plan["ganancia_realizada_usd"]) + ganancia_tp2, 2)
            alertas_parciales.append({
                "tramo": "TP2 (35%)",
                "base": pos["base"],
                "pnl_pct": round(pnl_pct, 2),
                "ganancia_tp": ganancia_tp2,
                "precio_actual": p_act,
                "capital_restante": cap,
                "detalle_siguiente": f"30% RUNNER final corriendo libre con Trailing Stop de -{TRAILING_RUNNER_PCT}% desde máximos."
            })

        palanca_activada, motivo_palanca = empleado_evaluar_palanca_emergencia(
            pos, v1m, v15, v1h, fib, ob, pnl_pct, max_pnl_pct, retroceso_desde_max, dossier_asistente
        )
        perdio_618 = fib.get("ok") and (p_act < float(fib["fib_618"]) and float(fib["ratio"]) > 0.65)
        tesis_viva = (not perdio_618) and (not dossier_asistente["alertada_en_perdedoras"])

        posiciones_evaluadas.append({
            "pos": pos,
            "sin_datos": False,
            "pnl_pct": pnl_pct,
            "pnl_usd": float(pos["pnl_usd"]),
            "max_pnl_pct": max_pnl_pct,
            "retroceso_desde_max": retroceso_desde_max,
            "horas_abierta": horas_abierta,
            "stop_dinamico_pct": stop_dinamico_pct,
            "propuesta_cierre_palanca": palanca_activada,
            "motivo_palanca": motivo_palanca,
            "cierre_aprobado_jefe": False,
            "tesis_viva": tesis_viva,
            "exp_previo": dossier_asistente
        })

    # PASO 3 (NIVEL 2): EL TRADER EVALÚA TIMING DE SALIDA EN CARTERA Y TIMING DE ENTRADA EN RADAR CONFIRMADO
    aud_actual = ejecutar_empleado_trader_ia(s, mapa_mkt, plan, msg_btc, lecturas_tecnicas, boletin_asistente, eco)

    cerradas_conteo = {}
    for c in plan["historial_cierres"]:
        if c.get("semana_id") == plan["semana_id"]:
            sym_c = c.get("symbol", "")
            if float(c.get("pnl_usd", 0.0)) >= 0:
                cerradas_conteo[sym_c] = 99
            else:
                cerradas_conteo[sym_c] = cerradas_conteo.get(sym_c, 0) + 1

    excluidas = {p["symbol"] for p in plan["posiciones"]} | {
        sym_c for sym_c, cnt in cerradas_conteo.items() if cnt > MAX_REENTRADAS_SEMANA
    }
    alternativas = empleado_evaluar_candidatas(s, mapa_mkt, excluidas, eco, plan)

    # PASO 4 (NIVEL 3): EL JEFE SUPERVISOR REVISA TODO (ASISTENTE + TRADER) Y EXIGE CONSENSO 3/3
    ejecutar_jefe_supervisor_ia(plan, alternativas, [x for x in posiciones_evaluadas if not x.get("sin_datos")], boletin_asistente, msg_btc)
    plan["alternativas_evaluadas"] = alternativas

    # PASO 5: EJECUCIÓN BLINDADA (MODO RUNNER 3 TRAMOS)
    ganancia_flotante_total = 0.0
    posiciones_siguen_activas = []

    for item in posiciones_evaluadas:
        pos = item["pos"]
        if item.get("sin_datos"):
            posiciones_siguen_activas.append(pos)
            continue

        pnl_pct = item["pnl_pct"]
        pnl_usd = item["pnl_usd"]
        max_pnl_pct = item["max_pnl_pct"]
        retroceso_desde_max = item["retroceso_desde_max"]
        horas_abierta = item["horas_abierta"]
        stop_dinamico_pct = item["stop_dinamico_pct"]
        es_vip_pos = bool(pos.get("carril_vip_radar", False)) or ("CAZADOR" in str(pos.get("origen", ""))) or ("VIP" in str(pos.get("origen", "")))
        horas_limite_rotacion = HORAS_MAX_SIN_ARRANQUE_VIP if es_vip_pos else HORAS_MAX_SIN_ARRANQUE_STD

        motivo_cierre = None
        if pos.get("tp2_ejecutado", False) and retroceso_desde_max <= -TRAILING_RUNNER_PCT:
            motivo_cierre = f"🚀 CIERRE RUNNER 30% (Trailing -{TRAILING_RUNNER_PCT}%): tocó máx +{max_pnl_pct:.1f}% y cerró en {pnl_pct:+.1f}% neto."
        elif not pos.get("tp2_ejecutado", False) and max_pnl_pct >= 22.0 and retroceso_desde_max <= -TRAILING_RUNNER_PCT:
            motivo_cierre = f"🚀 EXPLOSIÓN CAPTURADA: tocó +{max_pnl_pct:.1f}% y aseguró +{pnl_pct:.1f}% neto."
        elif pnl_pct <= STOP_LOSS_FIJO_PCT or pnl_usd <= -MAX_PERDIDA_USD:
            motivo_cierre = f"🛑 STOP DESPEGUE ({pnl_pct:.2f}% neto | ${pnl_usd:+.2f} USD): corta pérdida controlada."
        elif stop_dinamico_pct > 0 and pnl_pct <= stop_dinamico_pct:
            motivo_cierre = f"🛡️ STOP PROTEGIDO (+{stop_dinamico_pct:.2f}% neto): subió hasta +{max_pnl_pct:.1f}% y aseguró cierre en {pnl_pct:+.2f}%."
        elif not pos.get("tp1_ejecutado", False) and item["propuesta_cierre_palanca"] and item["cierre_aprobado_jefe"]:
            motivo_cierre = f"👔 SALIDA APROBADA POR JEFE: {item['motivo_palanca']}"
        elif not pos.get("tp1_ejecutado", False) and horas_abierta >= horas_limite_rotacion and pnl_pct < 1.5:
            motivo_cierre = f"⏳ ROTACIÓN ({int(horas_abierta)}h/{int(horas_limite_rotacion)}h lateral en {pnl_pct:+.1f}% neto): libera cupo."

        if motivo_cierre:
            pos["estado"] = "CERRADA"
            pos["fecha_cierre"] = ahora_str
            pos["motivo_cierre"] = motivo_cierre
            pos["post_cierre_max"] = float(pos["precio_actual"])
            pos["post_cierre_min"] = float(pos["precio_actual"])
            pos["veredicto_autopsia"] = "⏳ Iniciando seguimiento 24h"
            plan["ganancia_realizada_usd"] = round(float(plan["ganancia_realizada_usd"]) + float(pos["pnl_usd"]), 2)
            plan["historial_cierres"].append(pos)
            alertas_venta.append(pos)
        else:
            if (pnl_pct <= -2.40 or pnl_usd <= -PREALERTA_PERDIDA_USD) and not pos.get("prealerta_palanca_enviada", False):
                pos["prealerta_palanca_enviada"] = True
                prealertas_palanca.append(pos)
            elif pnl_pct > -1.20:
                pos["prealerta_palanca_enviada"] = False

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

    cb_activo, cb_recien_activado, msg_cb = verificar_circuit_breaker_diario(plan, ahora_dt)
    if cb_recien_activado:
        enviar_telegram_texto(
            f"🧊 <b>CIRCUIT BREAKER DIARIO ACTIVADO POR JEFE SUPERVISOR</b>\n"
            f"📅 <code>{ahora_str}</code>\n\n"
            f"⚠️ {html.escape(msg_cb)}"
        )

    if plan["estado_semana"] == "ACTIVA" and len(plan["posiciones"]) < cupos_max_regimen and not cb_activo:
        if not btc_ok:
            if not plan.get("aviso_btc_enviado", False):
                enviar_telegram_texto(f"🛑 <b>FRENO DE MANO BTC ACTIVADO</b>\n📅 <code>{ahora_str}</code>\n\n⚠️ {html.escape(msg_btc)}")
                plan["aviso_btc_enviado"] = True
        else:
            plan["aviso_btc_enviado"] = False
            cupos = min(cupos_max_regimen - len(plan["posiciones"]), MAX_ENTRADAS_POR_CORRIDA)
            # SOLO entran candidatas donde las 3 informaciones coinciden (Consenso 3/3)
            elegidas = [a for a in alternativas if a.get("consenso_3_de_3")][:cupos]

            if elegidas:
                cap_base_total = max(500.0, float(plan["capital_total_usd"]) + float(plan["ganancia_realizada_usd"]))
                cap_por_cupo = round(cap_base_total / MAX_MONEDAS_SEMANA, 2)
                meta_restante = max(50.0, float(plan["meta_semanal_usd"]) - float(plan["ganancia_realizada_usd"]))
                meta_por_cupo = meta_restante / MAX_MONEDAS_SEMANA
                subida_nec_pct = round((meta_por_cupo / cap_por_cupo) * 100.0, 2)

                for el in elegidas:
                    p_ent = float(el["precio_entrada"])
                    p_obj = p_ent * (1.0 + (subida_nec_pct / 100.0))
                    dossier_el = el.get("expediente_previo", {})
                    pnl_init_pct = -COMISION_SPOT_TOTAL_PCT
                    pnl_init_usd = round(cap_por_cupo * (pnl_init_pct / 100.0), 2)
                    nueva_pos = {
                        "semana_id": plan["semana_id"],
                        "symbol": el["symbol"],
                        "base": el["base"],
                        "origen": el["origen"],
                        "carril_vip_radar": bool(el.get("carril_vip_radar", False)),
                        "motivo_eleccion": el["motivo_tecnico"],
                        "expediente_previo_resumen": dossier_el.get("resumen_corto", ""),
                        "asistente_dictamen": dossier_el.get("dictamen_asistente", ""),
                        "jefe_veredicto_entrada": el.get("jefe_veredicto", "✅ CONSENSO 3/3"),
                        "jefe_orden": "✅ CONSENSO 3/3 APROBADO",
                        "jefe_razon": el.get("jefe_veredicto", ""),
                        "trader_ia_orden": "🟢 ENTRADA EJECUTADA",
                        "trader_ia_razon": el.get("plan_trader_entrada", el["motivo_tecnico"]),
                        "fecha_entrada": ahora_str,
                        "capital_inicial_usd": cap_por_cupo,
                        "capital_usd": cap_por_cupo,
                        "precio_entrada": p_ent,
                        "precio_objetivo": p_obj,
                        "subida_necesaria_pct": subida_nec_pct,
                        "precio_actual": p_ent,
                        "precio_maximo": p_ent,
                        "max_drawdown_pct": pnl_init_pct,
                        "pnl_pct": pnl_init_pct,
                        "pnl_usd": pnl_init_usd,
                        "stop_actual_pct": STOP_LOSS_FIJO_PCT,
                        "tp1_ejecutado": False,
                        "tp2_ejecutado": False,
                        "prealerta_palanca_enviada": False,
                        "estado": "ACTIVA"
                    }
                    plan["posiciones"].append(nueva_pos)
                    nuevas_entradas.append(nueva_pos)

    veredicto_final_txt = ""
    if plan["estado_semana"] == "META_CUMPLIDA":
        veredicto_final_txt = generar_veredicto_final_ia(plan)
        plan["auditoria_ia"]["veredicto_final_semana"] = veredicto_final_txt
        aud_actual["veredicto_final_semana"] = veredicto_final_txt

    for pre in prealertas_palanca:
        enviar_telegram_texto(
            f"⚠️ <b>PRE-ALERTA RIESGO (3 NIVELES) • {pre['base']}</b>\n"
            f"📅 <code>{ahora_str}</code>\n\n"
            f"• <b>Rendimiento flotante neto:</b> <b>{pre['pnl_pct']:+.2f}%</b> (<b>${pre['pnl_usd']:+.2f} USD</b>) — <i>Stop despegue: {STOP_LOSS_FIJO_PCT}%</i>\n"
            f"• <b>🗂️ Asistente:</b> <i>{html.escape(pre.get('asistente_dictamen', ''))}</i>\n"
            f"• <b>🤖 Trader:</b> <i>{html.escape(pre.get('trader_ia_razon', ''))}</i>\n"
            f"• <b>👔 Jefe:</b> <i>{html.escape(pre.get('jefe_razon', ''))}</i>"
        )

    for parc in alertas_parciales:
        enviar_telegram_texto(
            f"💰 <b>COSECHA PARCIAL {parc['tramo']} • {parc['base']}</b>\n"
            f"📅 <code>{ahora_str}</code>\n\n"
            f"• <b>Rendimiento neto alcanzado:</b> <b>+{parc['pnl_pct']:.2f}%</b> en <code>{formatear_precio(parc['precio_actual'])}</code>\n"
            f"• <b>Ganancia neta en caja:</b> <b>+${parc['ganancia_tp']:.2f} USD</b>\n"
            f"• <b>Siguiente paso:</b> {html.escape(parc['detalle_siguiente'])}"
        )

    es_ejecucion_manual = (os.getenv("GITHUB_EVENT_NAME") == "workflow_dispatch")
    es_corte_horario = (plan.get("ultimo_reporte_hora") != ahora_dt.hour)
    hay_novedades = bool(nuevas_entradas or alertas_parciales or alertas_venta or plan["estado_semana"] == "META_CUMPLIDA")

    if hay_novedades or es_corte_horario or es_ejecucion_manual:
        plan.setdefault("historial_auditorias", []).append(dict(aud_actual))
        plan["historial_auditorias"] = plan["historial_auditorias"][-100:]
        actualizar_excel_semanal(plan)

        ok1 = enviar_telegram_texto(construir_bloque_1_alternativas(plan))
        time.sleep(1.5)

        img = generar_tablero_visual(plan)
        if plan["estado_semana"] == "META_CUMPLIDA":
            titulo_ev = "🏆 <b>¡CUOTA SEMANAL CUMPLIDA — MODO PROTECCIÓN!</b>"
        elif alertas_venta and nuevas_entradas:
            titulo_ev = f"🔄 <b>ROTACIÓN CONSENSO 3/3 / STOP {STOP_LOSS_FIJO_PCT}%</b>"
        elif nuevas_entradas:
            titulo_ev = "🚀 <b>NUEVA COMPRA POR CONSENSO 3/3 (ASISTENTE + TRADER + JEFE)</b>"
        elif alertas_venta or alertas_parciales:
            titulo_ev = "💰 <b>COSECHA RUNNER 3 TRAMOS / CIERRE</b>"
        else:
            titulo_ev = "📡 <b>RADAR CONTINUO • CONSENSO 3/3 (ASISTENTE ➔ TRADER ➔ JEFE)</b>"

        caption = construir_bloque_2_cartera(plan, titulo_ev)
        ok2 = enviar_foto_telegram(img, caption)
        time.sleep(1.5)

        ok3 = enviar_excel_telegram(
            f"📎 <b>GESTOR Y RADAR SEMANAL • BLOQUE 3/3: PLANILLA EXCEL</b>\n"
            f"📊 Registro en 5 pestañas con Consenso 3/3 (Asistente + Trader + Jefe), Modo Runner, Autopsia 24h y PnL Neto (<code>{EXCEL_SEMANAL_FILE}</code>)."
        )
        if ok1 and ok2 and ok3:
            plan["ultimo_reporte_hora"] = ahora_dt.hour
    else:
        actualizar_excel_semanal(plan)

    for v in alertas_venta:
        msg_v = (
            f"🔔 <b>EJECUCIÓN DE CIERRE • {v['base']}</b>\n"
            f"• Resultado Neto: <b>{v['pnl_pct']:+.2f}%</b> (<b>${v['pnl_usd']:+.2f} USD</b>) | Máx: <code>{formatear_precio(v['precio_maximo'])}</code> | MaxDD: <code>{v.get('max_drawdown_pct', 0.0):.2f}%</code>\n"
            f"• Motivo: <i>{html.escape(v.get('motivo_cierre', ''))}</i>"
        )
        enviar_telegram_texto(msg_v)

    if plan["estado_semana"] == "META_CUMPLIDA":
        msg_m = (
            f"🏆 <b>¡CUOTA SEMANAL CUMPLIDA EN MODO PRUEBA!</b>\n"
            f"📅 Semana <code>{plan['semana_id']}</code> cerrada el <code>{ahora_str}</code>\n\n"
            f"✅ <b>Ganancia Total Neta Simulada:</b> <code>${plan['ganancia_realizada_usd']:,.2f} USD</code> (Meta: <code>${plan['meta_semanal_usd']:,.2f} USD</code>)\n\n"
            f"{veredicto_final_txt}\n\n"
            f"🛡️ <i>El bot entra en MODO PROTECCIÓN hasta el próximo lunes para asegurar el resultado.</i>"
        )
        enviar_telegram_texto(msg_m)

    guardar_plan_semanal(plan)

if __name__ == "__main__":
    print(f"🧪 INICIANDO GESTOR SEMANAL CONSENSO 3/3 ({ahora_art().strftime('%H:%M:%S')} ART)...")
    ejecutar_gestor_semanal()
