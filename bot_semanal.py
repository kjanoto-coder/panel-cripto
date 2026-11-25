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

# Parámetros operativos: Estructura Blindada 3 Niveles + Gestión Institucional
CAPITAL_INICIAL_PRUEBA = 3500.0
META_SEMANAL_USD = 600.0
MAX_MONEDAS_SEMANA = 4              # Cada cupo usa SIEMPRE 1/4 (25%) del capital disponible
CUPOS_MODO_DEFENSIVO = 2            # Reduce de 4 a 2 cupos simultáneos cuando el mercado general está débil
MAX_ENTRADAS_POR_CORRIDA = 2        # Entrada escalonada: máximo 2 compras nuevas por ejecución
TOP_ALTERNATIVAS_MOSTRAR = 8
FACTIBILIDAD_MINIMA_JEFE = 75       # Puntaje mínimo exigido por el Jefe Supervisor para aprobar una entrada

# Parámetros de Riesgo, Liquidez Real y Circuit Breaker Diario
COMISION_SPOT_TOTAL_PCT = 0.20      # 0.10% compra + 0.10% venta en Binance Spot (PnL Neto Real)
STOP_LOSS_FIJO_PCT = -2.20          # Margen técnico uniforme (-2.20% neto)
MAX_PERDIDA_USD = 20.0              # Tope duro máximo en dólares por cupo de 25%
PREALERTA_PERDIDA_USD = 12.0        # Pre-alerta temprana
TP1_ASEGURAR_PCT = 4.8              # Vende 50% al tocar +4.8% neto para asegurar ganancia real en caja
TRAILING_DESDE_MAX_PCT = 2.2        # Trailing Stop para la 2ª mitad corredora
HORAS_MAX_SIN_ARRANQUE = 8.0        # Rotación rápida (8h) si no arranca
COOLDOWN_PANICO_BTC_MIN = 60        # Antispam de 60 minutos para alerta de pánico BTC 1H

MIN_LIQUIDEZ_TOP_ASK_USD = 2500.0   # Liquidez mínima en USD dentro del 0.15% del mejor Ask
MAX_SLIPPAGE_EST_PCT = 0.25         # Deslizamiento máximo estimado para ejecutar un cupo real (~$875)
MAX_PERDIDA_DIARIA_USD = 50.0       # Circuit Breaker diario: pérdida máxima realizada en un mismo día
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
# NIVEL 1: ASISTENTE DE INTELIGENCIA (ECOSISTEMA + AUTOPSIA POST-CIERRE 24H)
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
    """
    MEJORA 1 (AUTOPSIA POST-CIERRE 24H):
    El Asistente sigue auditando durante 24 horas el precio de las monedas recién cerradas
    para medir si los stops fueron prematuros o salvadores y retroalimentar al Jefe Supervisor.
    """
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
                if var_max_post >= 10.0:
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
            f"Autopsia 24h semana: {stops_salvadores_sem} stops salvadores | "
            f"{stops_prematuros_sem} stops prematuros | {cosechas_optimas_sem} cosechas óptimas"
        )
    }

def ejecutar_asistente_inteligencia(mapa_mkt, plan):
    """
    NIVEL 1 (ASISTENTE): Escanea todos los JSON y Excel del ecosistema,
    depura contradicciones, ejecuta la autopsia post-cierre 24h y arma el Boletín de Inteligencia.
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

    if graduadas or posta:
        fuentes_leidas.append(f"Pre-Explosión/Cazador ({len(graduadas)}G/{len(posta)}P)")
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
    """Arma el Dossier individual de cada moneda cruzando todos los bots y cierres de la semana."""
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

    reincidente_stop_semana = False
    if plan:
        for c in plan.get("historial_cierres", []):
            if c.get("semana_id") == plan.get("semana_id") and c.get("symbol") == sym and float(c.get("pnl_usd", 0)) < 0:
                reincidente_stop_semana = True
                break

    confluencia_multi_bot = sum([
        1 if ("VERDE" in semaforo or cert_e1 or cert_e2) else 0,
        1 if en_ganadoras_activo else 0,
        1 if sym in eco["notas_extra"] else 0
    ])

    tiene_respaldo_bots = (
        not en_lista_perdedoras
        and not reincidente_stop_semana
        and (
            ("VERDE" in semaforo)
            or (cert_e1 and cert_e2)
            or en_ganadoras_activo
            or (etapa >= 2 and blindaje >= 78)
        )
    )

    if en_lista_perdedoras:
        dictamen_asistente = "⛔ BLOQUEADA POR ASISTENTE: Detectada en lista negra / Bot Perdedoras."
    elif reincidente_stop_semana:
        dictamen_asistente = "⛔ BLOQUEADA POR ASISTENTE: Ya cerró con pérdida esta semana (anti-reincidencia)."
    elif not tiene_respaldo_bots:
        dictamen_asistente = f"⚠️ DESCARTADA POR ASISTENTE: Sin respaldo suficiente (Semáforo {semaforo}, Etapa {etapa})."
    else:
        dictamen_asistente = (
            f"✅ DOSSIER VALIDADO ({confluencia_multi_bot} fuentes): Semáforo {semaforo} | E{etapa} | "
            f"Radar {var_desde_radar:+.1f}% | HistVerdes Máx {max_hist_verde:+.1f}%"
        )

    resumen_corto = (
        f"Semáforo:{semaforo} | E{etapa} | DesdeRadar:{var_desde_radar:+.1f}% | "
        f"HistVerdes:{estado_hist_verde} (Máx {max_hist_verde:+.1f}%)"
    )
    if tesis_textos:
        resumen_corto += f" | Tesis: {tesis_textos[0][:85]}"

    return {
        "semaforo_radar": semaforo,
        "etapa_cazador": etapa,
        "blindaje_pct": blindaje,
        "doble_certificada": (cert_e1 and cert_e2),
        "en_ganadoras_activo": en_ganadoras_activo,
        "confluencia_multi_bot": confluencia_multi_bot,
        "reincidente_stop_semana": reincidente_stop_semana,
        "tiene_respaldo_bots": tiene_respaldo_bots,
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
# HERRAMIENTAS TÉCNICAS Y LIQUIDEZ REAL PARA EL EMPLEADO (TRADER IA)
# ==============================================================================

def auditar_order_book_semanal(session, symbol, monto_orden_usd=875.0):
    """
    MEJORA 3 (AUDITORÍA DE SLIPPAGE Y LIQUIDEZ REAL):
    Verifica profundidad ±2.5%, muros vendedores, dólares disponibles dentro del 0.15% del mejor Ask
    y calcula el slippage VWAP estimado para ejecutar un cupo real en Spot.
    """
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

                # Liquidez inmediata dentro del 0.15% del mejor Ask
                liq_ask_015 = sum(float(x[0]) * float(x[1]) for x in asks if float(x[0]) <= a0 * 1.0015)

                # Cálculo de slippage VWAP para comprar monto_orden_usd
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
    """
    MEJORA 4 (CIRCUIT BREAKER DIARIO / ANTI-PICADORA DE CARNE):
    Si en el mismo día se dan 3 cierres negativos seguidos o -$50 USD de pérdida realizada diaria,
    congela compras nuevas durante 8 horas.
    """
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
        "modo": "BLINDADO_3_NIVELES_AUTOPSIA_LIQUIDEZ_CB",
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
# NIVEL 2: EMPLEADO (TRADER IA — FILTRO ANTI-FOMO 15M + LIQUIDEZ REAL + TÉCNICOS)
# ==============================================================================

def empleado_evaluar_palanca_emergencia(pos, v1m, v15, v1h, fib, ob, pnl_pct, max_pnl_pct, retroceso_desde_max, dossier_asistente):
    """El Empleado (Trader IA) detecta anomalías en vivo y eleva solicitud de cierre al Jefe."""
    p_act = float(pos.get("precio_actual", 0))
    perdio_fib_618 = False
    if fib.get("ok"):
        perdio_fib_618 = (p_act < float(fib["fib_618"]) and float(fib["ratio"]) > 0.65)

    if dossier_asistente.get("alertada_en_perdedoras") and pnl_pct <= -0.80:
        return True, (
            f"🚨 SOLICITUD EMPLEADO (Alerta Asistente/Perdedoras): marcada en baja en ecosistema previo y en {pnl_pct:+.2f}% neto."
        )

    if v1m.get("ok"):
        if (v1m["var_3velas"] <= -1.40 and v1m["vol_ratio"] >= 1.8) or (v1m["var_ultima"] <= -1.15 and v1m["vol_ratio"] >= 2.0):
            return True, (
                f"🚨 SOLICITUD EMPLEADO 1M (Desplome en Vivo): caída {v1m['var_3velas']:+.2f}% en 3m "
                f"(vol {v1m['vol_ratio']}x) en {pnl_pct:+.2f}% neto."
            )

    if max_pnl_pct >= 2.4 and retroceso_desde_max <= -1.4:
        giro_1m = v1m.get("ok") and (v1m["velas_rojas_seg"] >= 2 and v1m["var_3velas"] <= -0.85)
        giro_15m = v15.get("ok") and (v15.get("rechazo_techo") or v15.get("var_ultima", 0) <= -0.90)
        if giro_1m or giro_15m:
            return True, (
                f"🚨 SOLICITUD EMPLEADO (Giro en Vivo 1m/15m): subió hasta +{max_pnl_pct:.1f}% y retrocedió "
                f"{retroceso_desde_max:.1f}% en {pnl_pct:+.2f}% neto."
            )

    p_ref_radar = float(dossier_asistente.get("precio_referencia_radar", 0))
    bajo_precio_radar = (p_ref_radar > 0 and p_act < p_ref_radar * 0.980)
    if pnl_pct <= -1.75 and (perdio_fib_618 or bajo_precio_radar):
        return True, (
            f"🚨 SOLICITUD EMPLEADO (Tesis Invalidada): rompió Fib 0.618 / base del radar en {pnl_pct:+.2f}% neto."
        )

    if pnl_pct <= -1.80 and v15.get("ok") and v15.get("velas_rojas_seg", 0) >= 3:
        return True, (
            f"🚨 SOLICITUD EMPLEADO (3 Velas Rojas 15m): presión vendedora sostenida en {pnl_pct:+.2f}% neto."
        )

    return False, ""

def empleado_evaluar_candidatas(session, mapa_mkt, excluidas, eco, plan):
    """
    NIVEL 2 (EMPLEADO TRADER IA): Recibe los Dossiers validados por el Asistente,
    aplica Filtro Anti-FOMO 15m, audita gráficos 1h/4h, Fibonacci, Liquidez Real (Slippage) y Order Book.
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
        mom_1h = analizar_velas_tf(session, sym, "1h", 36)
        mom_4h = analizar_velas_tf(session, sym, "4h", 48)
        mom_15m = analizar_velas_tf(session, sym, "15m", 24) if dossier["tiene_respaldo_bots"] else {"ok": False, "rsi": 50.0, "var_ultima": 0.0, "var_3velas": 0.0}
        fib_4h = mom_4h.get("fib", {})
        ob = auditar_order_book_semanal(session, sym, cupo_est_usd)

        var_radar = dossier["var_desde_deteccion_radar_pct"]
        prob = dossier["blindaje_pct"]
        cert_doble = dossier["doble_certificada"]
        etapa = dossier["etapa_cazador"]
        semaforo = dossier["semaforo_radar"]

        # MEJORA 2: Filtro Anti-FOMO en 15m (evita comprar el pico de un velón vertical)
        fomo_15m = bool(mom_15m.get("ok")) and (
            float(mom_15m.get("rsi", 50.0)) > 75.0
            or float(mom_15m.get("var_ultima", 0.0)) > 3.5
            or float(mom_15m.get("var_3velas", 0.0)) > 5.5
        )

        fib_sano = (not fib_4h.get("ok")) or (not fib_4h.get("en_soporte_profundo", False))
        impulso_verde = (
            var_radar >= -0.5
            and 0.8 <= mkt["cambio_24h"] <= 25.0
            and (mom_1h["var_3velas"] > 0.0 or mom_1h["var_ultima"] > 0.0)
            and mom_1h["vol_ratio"] >= 1.05
        )

        bono_semaforo = 12 if "VERDE" in semaforo else (6 if "AMARILLO" in semaforo else 0)
        bono_cert = 22 if cert_doble else (14 if dossier["en_ganadoras_activo"] else (10 if (sym in graduadas) else -12))
        bono_confluencia = dossier["confluencia_multi_bot"] * 5
        bono_fib = 14 if fib_4h.get("en_zona_dorada") else (8 if fib_4h.get("en_tramo_alcista") else (-25 if not fib_sano else -4))
        bono_ob = 12 if ob.get("ratio_ba", 0) >= 1.40 and ob.get("sano") else (6 if ob.get("sano") else -25)
        bono_verde = 12 if impulso_verde else -18
        bono_fomo = -20 if fomo_15m else 4
        bono_hist = -45 if (dossier["alertada_en_perdedoras"] or dossier["reincidente_stop_semana"]) else (14 if "GANADORA" in dossier["estado_historial_ganadoras"] else 0)

        score = prob + bono_semaforo + bono_cert + bono_confluencia + bono_ob + bono_fib + bono_verde + bono_fomo + bono_hist + (5 if mom_1h["vol_ratio"] >= 1.25 else 0)

        propuesta_empleado = (
            dossier["tiene_respaldo_bots"]
            and impulso_verde
            and not fomo_15m
            and var_radar <= 14.0
            and fib_sano
            and mom_1h["rsi"] <= 74.0
            and ob.get("sano", False)
            and (sym not in excluidas)
        )

        if cert_doble:
            sello_txt = "🛡️🛡️ DOBLE CERT. IA"
        elif dossier["en_ganadoras_activo"] and semaforo == "N/D":
            sello_txt = "🏆 GANADORAS RADAR"
        elif semaforo != "N/D":
            sello_txt = f"🛡️ Semáforo {semaforo} (E{etapa})"
        else:
            sello_txt = f"Cazador Etapa {etapa}"

        fib_tag = f" | {fib_4h.get('zona_txt', 'Fib N/D')}" if fib_4h.get("ok") else ""
        muro_tag = " [⚠️MURO]" if ob.get("muro_vendedor") else ""
        liq_tag = f" | Liq0.15%: ${int(ob.get('liq_ask_015_usd', 0)):,}" if ob.get("ok") else ""
        fomo_tag = f" | ⏳ Anti-FOMO 15m (RSI {mom_15m.get('rsi')}, {mom_15m.get('var_ultima'):+.1f}%)" if fomo_15m else ""
        motivo_tecnico = (
            f"{sello_txt} ({var_radar:+.1f}% radar | 1h: {mom_1h['var_3velas']:+.1f}%) | "
            f"OB: {ob['ratio_ba']}x{muro_tag}{liq_tag} | RSI 1h: {mom_1h['rsi']}{fib_tag}{fomo_tag}"
        )
        candidatos.append({
            "symbol": sym,
            "base": sym[:-4],
            "precio_entrada": mkt["precio"],
            "origen": sello_txt,
            "probabilidad": prob,
            "score": score,
            "certificada_doble": cert_doble,
            "asistente_validado": dossier["tiene_respaldo_bots"],
            "asistente_dictamen": dossier["dictamen_asistente"],
            "fomo_15m": fomo_15m,
            "propuesta_trader_ia": propuesta_empleado,
            "en_zona": False,
            "jefe_veredicto": (
                dossier["dictamen_asistente"]
                if not dossier["tiene_respaldo_bots"]
                else (
                    f"⏳ Empleado espera retroceso 15m (Anti-FOMO RSI {mom_15m.get('rsi')})"
                    if fomo_15m
                    else ("⏳ Sin propuesta técnica del Empleado" if not propuesta_empleado else "⏳ Pendiente revisión del Jefe")
                )
            ),
            "jefe_factibilidad_pct": 0,
            "ya_en_cartera": sym in excluidas,
            "motivo_tecnico": motivo_tecnico,
            "expediente_previo": dossier,
            "ob": ob,
            "mom": mom_1h,
            "mom_15m": mom_15m,
            "fib_4h": fib_4h
        })

    candidatos.sort(key=lambda x: (x["propuesta_trader_ia"], x["asistente_validado"], x["certificada_doble"], x["score"]), reverse=True)
    return candidatos[:TOP_ALTERNATIVAS_MOSTRAR]

def ejecutar_empleado_trader_ia(session, mapa_mkt, plan, clima_btc_txt, lecturas_tecnicas, boletin_asistente, eco):
    """NIVEL 2 (EMPLEADO TRADER IA): Evalúa cartera abierta apoyado en los Dossiers del Asistente."""
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
        obj_pct = float(p.get("subida_necesaria_pct", 17.14))
        stop_act = float(p.get("stop_actual_pct", STOP_LOSS_FIJO_PCT))

        fib_resumen = "Fib N/D"
        cerca_techo_fib = False
        perdio_fib_618 = False
        if fib.get("ok"):
            fib_resumen = f"{fib['zona_txt']} | Sop 0.618: {formatear_precio(fib['fib_618'])} | Ext 1.618: {formatear_precio(fib['ext_1618'])}"
            cerca_techo_fib = fib.get("cerca_ext_1618", False)
            perdio_fib_618 = (p_act < float(fib["fib_618"]) and float(fib["ratio"]) > 0.65)
        p["fib_lectura"] = fib_resumen

        es_ruido_1m = (abs(v1m["var_3velas"]) < 0.60 and v1m["vol_ratio"] < 1.5)
        pulso_1m_txt = f"1m: {v1m['var_3velas']:+.2f}% (3m) | RSI 1m: {v1m['rsi']} | Vol: {v1m['vol_ratio']}x"
        if es_ruido_1m:
            pulso_1m_txt += " [Ruido normal]"

        var_radar = dossier["var_desde_deteccion_radar_pct"]
        tesis_viva = (not perdio_fib_618) and (not dossier["alertada_en_perdedoras"])

        if dossier["alertada_en_perdedoras"]:
            orden_def = "🚨 SOLICITUD VENTA (Alerta Asistente)"
            razon_def = f"Asistente detectó inclusión en Bot Perdedoras ({dossier['estado_historial_ganadoras']})."
        elif (pnl_pct >= obj_pct or cerca_techo_fib or var_radar >= 24.0) and (v1m["rsi"] >= 78 or v15["rsi"] >= 72 or v15["rechazo_techo"] or retroceso_max <= -1.8):
            orden_def = "🚨 SOLICITUD VENTA (Techo 1m/Fib)"
            razon_def = f"Acumula {var_radar:+.1f}% desde radar y muestra agotamiento (RSI 1m={v1m['rsi']}, 15m={v15['rsi']})."
        elif not p.get("tp1_ejecutado", False) and pnl_pct >= TP1_ASEGURAR_PCT * 0.85:
            orden_def = f"🟡 CERCA TP1 (+{TP1_ASEGURAR_PCT}% Neto)"
            razon_def = f"Tesis {dossier['semaforo_radar']} confirmada (+{pnl_pct:.1f}% neto): próximo a asegurar 50%."
        elif pnl_pct <= -1.55 or pnl_usd <= -PREALERTA_PERDIDA_USD or (pnl_pct <= -1.20 and not tesis_viva):
            orden_def = "⚠️ ALERTA PALANCA / TESIS EN RIESGO"
            razon_def = f"PnL Neto {pnl_pct:+.2f}% (${pnl_usd:+.2f} USD | Stop {STOP_LOSS_FIJO_PCT}%) | {pulso_1m_txt}."
        else:
            proteccion_txt = f"Trailing BE +{stop_act:.2f}% neto" if stop_act > 0 else f"Stop {STOP_LOSS_FIJO_PCT:.2f}%"
            orden_def = "🟢 MANTENER / TESIS VIVA"
            razon_def = f"Dossier {dossier['semaforo_radar']} activo ({var_radar:+.1f}% radar) | {pulso_1m_txt} | {proteccion_txt}."

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
        "diagnostico_24h": f"Blindado 3 Niveles (Asistente -> Empleado -> Jefe | Cupo 25%): {resumen_emb_txt}. {clima_btc_txt}. Avance: {progreso_pct}%.",
        "recomendacion_auditor": f"Flujo estricto: Dossier Asistente + Anti-FOMO 15m + Liq Real + Aprobación Jefe (>= {FACTIBILIDAD_MINIMA_JEFE}%).",
        "veredicto_final_semana": plan.get("auditoria_ia", {}).get("veredicto_final_semana", "En seguimiento activo...")
    }

    if GEMINI_API_KEY and datos_posiciones:
        try:
            client = genai.Client(api_key=GEMINI_API_KEY)
            prompt = (
                "Eres el EMPLEADO (Trader IA) de una mesa Spot en Binance (PnL descontando 0.20% fees).\n"
                "Recibes los Dossiers auditados por el ASISTENTE de inteligencia y debes formular tu propuesta técnica para el JEFE SUPERVISOR:\n"
                f"BOLETÍN ASISTENTE: {boletin_asistente.get('resumen_ejecutivo', '')} | Macro: {macro_bots_txt}\n"
                f"CLIMA MERCADO: {clima_btc_txt}\n"
                f"AVANCE SEMANAL NETO: ${real + flot:+.2f} / ${meta:.0f} USD ({progreso_pct}%)\n"
                f"POSICIONES:\n{json.dumps(datos_posiciones, ensure_ascii=False)}\n\n"
                "Responde ÚNICAMENTE en JSON válido sin bloques markdown:\n"
                '{"semaforo_meta":"🟢 FACTIBLE | 🟡 EN OBSERVACIÓN | 🔴 RIESGO","factibilidad_pct":80,'
                '"diagnostico_24h":"análisis técnico breve en 1 oración",'
                '"recomendacion_auditor":"recomendación operativa para el Jefe",'
                '"ordenes":{"MONEDA":{"orden":"🟢 MANTENER / TESIS VIVA | 🟡 ASEGURAR 50% (TP1) | 🚨 SOLICITUD VENTA | ⚠️ ALERTA PALANCA","razon":"motivo técnico citando dossier del asistente y pulso 1m/15m"}}}'
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
            print(f"⚠️ Fallback Empleado Trader IA: {e}")

    plan["auditoria_ia"] = auditoria_res
    return auditoria_res

# ==============================================================================
# NIVEL 3: JEFE SUPERVISOR IA (AUDITA TODO + AUTOPSIA 24H + VEREDICTO FINAL)
# ==============================================================================

def ejecutar_jefe_supervisor_ia(plan, alternativas, posiciones_revisar, boletin_asistente, clima_btc_txt):
    """
    NIVEL 3 (JEFE SUPERVISOR CON ACCESO TOTAL):
    Revisa los Dossiers del Asistente, la Autopsia Post-Cierre 24h y las propuestas del Empleado,
    verifica por qué tomó cada decisión y emite el veredicto final antes de ejecutar.
    """
    propuestas_compra = [a for a in alternativas if a.get("propuesta_trader_ia")]
    cierres_sem = [c for c in plan.get("historial_cierres", []) if c.get("semana_id") == plan["semana_id"]]
    real = float(plan.get("ganancia_realizada_usd", 0.0))
    flot = sum(float(p.get("pnl_usd", 0.0)) for p in plan.get("posiciones", []))
    balance_neto = round(real + flot, 2)
    meta = float(plan.get("meta_semanal_usd", META_SEMANAL_USD))

    autopsia_info = boletin_asistente.get("autopsia_24h", {})
    stops_prematuros_sem = int(autopsia_info.get("stops_prematuros_semana", 0))

    # 1. Filtro ejecutivo determinista del Jefe Supervisor
    for alt in propuestas_compra:
        dossier = alt.get("expediente_previo", {})
        ob = alt.get("ob", {})
        mom = alt.get("mom", {})
        fib = alt.get("fib_4h", {})

        fact = 60
        if dossier.get("doble_certificada"):
            fact += 16
        elif dossier.get("en_ganadoras_activo") or "VERDE" in dossier.get("semaforo_radar", ""):
            fact += 12
        fact += int(dossier.get("confluencia_multi_bot", 0)) * 3
        if float(ob.get("ratio_ba", 1.0)) >= 1.25 and ob.get("liquidez_real_ok") and not ob.get("muro_vendedor"):
            fact += 8
        if fib.get("en_zona_dorada") or fib.get("en_tramo_alcista"):
            fact += 6
        if float(mom.get("vol_ratio", 1.0)) >= 1.25:
            fact += 5
        if balance_neto < -250.0 and not (dossier.get("doble_certificada") or dossier.get("en_ganadoras_activo")):
            fact -= 15
        if float(mom.get("rsi", 50.0)) > 68.0:
            fact -= 8

        fact = max(35, min(95, fact))
        aprob = (fact >= FACTIBILIDAD_MINIMA_JEFE)
        alt["jefe_factibilidad_pct"] = fact
        alt["en_zona"] = aprob
        if aprob:
            alt["jefe_veredicto"] = (
                f"✅ APROBADA POR JEFE ({fact}% factible): Dossier + OB {ob.get('ratio_ba', 1.0)}x "
                f"(Slip {ob.get('slippage_est_pct', 0.05)}%) validados."
            )
        else:
            alt["jefe_veredicto"] = f"⛔ VETADA POR JEFE ({fact}% < {FACTIBILIDAD_MINIMA_JEFE}%): exige mayor confirmación con balance ${balance_neto:+.0f}."

    for item_pos in posiciones_revisar:
        pos = item_pos["pos"]
        if item_pos.get("propuesta_cierre_palanca"):
            tesis_viva = item_pos.get("tesis_viva", True)
            pnl_p = float(pos.get("pnl_pct", 0.0))
            # Si hubo >=2 stops prematuros en la semana, el Jefe es aún más estricto contra ventas en pánico
            umbral_veto_jefe = -1.90 if stops_prematuros_sem >= 2 else -1.65
            if tesis_viva and pnl_p > umbral_veto_jefe:
                item_pos["cierre_aprobado_jefe"] = False
                pos["jefe_orden"] = "🛡️ VETO JEFE: MANTENER TESIS"
                pos["jefe_razon"] = (
                    f"Jefe veta salida anticipada en {pnl_p:+.2f}% (Autopsia: {stops_prematuros_sem} stops prematuros sem): "
                    f"tesis del Asistente intacta."
                )
            else:
                item_pos["cierre_aprobado_jefe"] = True
                pos["jefe_orden"] = "✅ CIERRE APROBADO POR JEFE"
                pos["jefe_razon"] = f"Jefe confirma salida preventiva en {pnl_p:+.2f}%: tesis invalidada."
        else:
            pos["jefe_orden"] = "✅ SEGUIMIENTO APROBADO"
            pos["jefe_razon"] = f"Jefe valida plan del Empleado (Cupo 25% | TP1 +{TP1_ASEGURAR_PCT}% | Stop {STOP_LOSS_FIJO_PCT}%)."

    # 2. Auditoría cognitiva final con Gemini IA actuando como Jefe Supervisor con Acceso Total
    if GEMINI_API_KEY and (propuestas_compra or posiciones_revisar):
        try:
            client = genai.Client(api_key=GEMINI_API_KEY)
            resumen_propuestas = [
                {
                    "moneda": a["base"],
                    "score_empleado": a["score"],
                    "propuesta_tecnica_empleado": a["motivo_tecnico"],
                    "dossier_completo_asistente": a["expediente_previo"],
                    "order_book_y_slippage": a["ob"],
                    "velas_1h": a["mom"],
                    "velas_15m": a["mom_15m"]
                }
                for a in propuestas_compra
            ]
            resumen_cartera = [
                {
                    "moneda": it["pos"]["base"],
                    "pnl_neto_pct": it["pos"]["pnl_pct"],
                    "pnl_neto_usd": it["pos"]["pnl_usd"],
                    "propuesta_empleado": it["pos"].get("trader_ia_orden", ""),
                    "razon_empleado": it["pos"].get("trader_ia_razon", ""),
                    "pide_cierre_anticipado": bool(it.get("propuesta_cierre_palanca")),
                    "motivo_cierre_empleado": it["motivo_palanca"],
                    "tesis_viva": it["tesis_viva"],
                    "dossier_completo_asistente": it["exp_previo"]
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
                "Eres el JEFE SUPERVISOR DE INVERSIONES Y RIESGO en una estructura blindada de 3 niveles:\n"
                "1) ASISTENTE: recolectó toda la data de los bots + ejecutó la AUTOPSIA POST-CIERRE 24H.\n"
                "2) EMPLEADO (Trader IA): aplicó Anti-FOMO 15m + Liquidez/Slippage y te eleva sus propuestas.\n"
                "3) JEFE SUPERVISOR (TÚ): tienes acceso total a ambos reportes, a la autopsia de 24h y al balance semanal. "
                "Audita por qué el Empleado decidió cada propuesta, verifica su factibilidad y emite el VEREDICTO FINAL:\n"
                "REGLAS:\n"
                "- En COMPRAS: Aprueba ('aprobada': true, 'factibilidad_pct' >= 75) SOLO si el Dossier del Asistente, la liquidez real y los técnicos son sólidos.\n"
                "- En CARTERA ABIERTA: Si el Empleado pide cierre anticipado ('pide_cierre_anticipado': true) y la autopsia muestra 'stops_prematuros_semana' >= 1, VETA salidas por ruido menor ('aprobar_cierre': false) salvo invalidación real de tesis.\n\n"
                f"BOLETÍN Y AUTOPSIA ASISTENTE: {json.dumps(boletin_asistente, ensure_ascii=False)}\n"
                f"ESTADO SEMANA {plan['semana_id']}: Balance Neto ${balance_neto:+.2f} / Meta ${meta:.0f} USD | {clima_btc_txt}\n"
                f"ÚLTIMOS CIERRES Y AUTOPSIA 24H: {json.dumps(ultimos_cierres, ensure_ascii=False)}\n"
                f"PROPUESTAS DE COMPRA DEL EMPLEADO:\n{json.dumps(resumen_propuestas, ensure_ascii=False)}\n"
                f"REVISIÓN CARTERA ACTIVA:\n{json.dumps(resumen_cartera, ensure_ascii=False)}\n\n"
                "Responde ÚNICAMENTE en JSON válido sin bloques markdown:\n"
                '{"compras":{"MONEDA":{"aprobada":true,"factibilidad_pct":84,"veredicto":"✅ APROBADA POR JEFE (84%): motivo concreto"}},'
                '"cartera":{"MONEDA":{"aprobar_cierre":false,"orden_jefe":"🛡️ VETO JEFE: MANTENER | ✅ APROBADO POR JEFE","razon_jefe":"dictamen concreto del Jefe cruzando Asistente + Autopsia + Empleado"}}}'
            )

            raw_jefe = llamar_gemini_con_reintento(client, prompt_jefe)
            if raw_jefe:
                j_json = limpiar_json_ia(raw_jefe)
                compras_j = j_json.get("compras", {})
                for alt in propuestas_compra:
                    dec = compras_j.get(alt["base"])
                    if isinstance(dec, dict) and "aprobada" in dec:
                        fact_ia = int(dec.get("factibilidad_pct", alt["jefe_factibilidad_pct"]))
                        aprob_ia = bool(dec["aprobada"]) and (fact_ia >= FACTIBILIDAD_MINIMA_JEFE)
                        alt["jefe_factibilidad_pct"] = fact_ia
                        alt["en_zona"] = aprob_ia
                        prefijo = f"✅ APROBADA POR JEFE ({fact_ia}%)" if aprob_ia else f"⛔ VETADA POR JEFE ({fact_ia}%)"
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
        f"✅ <b>VEREDICTO: META LOGRADA — ESTRUCTURA 3 NIVELES + LIQUIDEZ REAL FACTIBLE</b>\n"
        f"• Se alcanzaron <b>${total_usd:,.2f} USD netos</b> (Meta: ${meta_usd:,.0f} USD) con <b>{win_rate}% de acierto</b> "
        f"({len(ganadoras)} ganadoras / {len(perdedoras)} cerradas en protección)."
    )

    if GEMINI_API_KEY and cierres:
        try:
            client = genai.Client(api_key=GEMINI_API_KEY)
            prompt = (
                "Eres el Jefe Supervisor de una mesa Spot en Binance operada con estructura de 3 niveles (Asistente + Autopsia 24h -> Empleado Anti-FOMO/Liquidez -> Jefe). "
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
        ax2.axhline(TP1_ASEGURAR_PCT, color="#00e676", linestyle="--", linewidth=1.2, label=f"TP1 50% (+{TP1_ASEGURAR_PCT}%)")
        ax2.axhline(stop_ref_pct, color="#ff1744", linestyle=":", linewidth=1.3, label=f"Stop ({stop_ref_pct}%)")
        max_y = max(max(objs + [20]) * 1.28, 24)
        min_y = min(min(pnls + [stop_ref_pct]) * 1.45, -4.5)
        ax2.set_ylim(min_y, max_y)
        ax2.set_xticks(list(x))
        ax2.set_xticklabels(nombres, color="white", fontweight="bold", fontsize=9.5)
        ax2.tick_params(axis="y", colors="white", labelsize=8.5)
        ax2.grid(True, axis="y", color="#1e293b", linewidth=0.7, zorder=1)
        ax2.legend(loc="upper right", facecolor="#0b132b", edgecolor="#334155", labelcolor="white", fontsize=7.2)

        for b, v, obj in zip(bars_act, pnls, objs):
            yv = b.get_height()
            ax2.text(b.get_x() + b.get_width() / 2.0, yv + (0.8 if yv >= 0 else -1.0), f"{v:+.2f}%\n(TP1 +{TP1_ASEGURAR_PCT}%)", ha="center", va="bottom" if yv >= 0 else "top", color="white", fontweight="bold", fontsize=7.8)
    else:
        ax2.text(0.5, 0.5, "Sin posiciones abiertas\n(Esperando clima BTC / aprobación Jefe IA)", ha="center", va="center", color="#94a3b8", fontsize=10, transform=ax2.transAxes)
        ax2.tick_params(left=False, labelleft=False, bottom=False, labelbottom=False)

    aud = plan.get("auditoria_ia", {})
    fact_txt = f" | Jefe IA: {aud.get('factibilidad_pct', 80)}% Factible" if aud else ""
    ax2.set_title(f"CARTERA 3 NIVELES ({len(posiciones)}/{MAX_MONEDAS_SEMANA} • CUPO 25%) • TP1 +{TP1_ASEGURAR_PCT}% | STOP {STOP_LOSS_FIJO_PCT}%", color="#00e676", fontsize=9.0, fontweight="bold", pad=10)
    fig.suptitle(f"ETAPA 4 • ASISTENTE ➔ EMPLEADO ➔ JEFE ({plan['semana_id']}){fact_txt} | {ahora_art().strftime('%d/%m %H:%M ART')}", color="white", fontsize=9.8, fontweight="bold", y=0.98)
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
    ws.title = "1_CARTERA_Y_TRADER_IA"
    headers = [
        "Semana", "Fecha Entrada", "Moneda", "Certificación y Motivo", "Dossier Asistente (Ecosistema)", "Capital ($)",
        "Precio Entrada", "Precio Objetivo", "Subida Esperada (%)",
        "Precio Actual", "Máximo Alcanzado", "Max Drawdown (%)", "Rend. Neto (%)",
        "PnL Neto ($)", "Lectura Fibonacci 4H", "Propuesta Empleado (Trader IA)", "Veredicto Jefe Supervisor", "Estado"
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
        ver_jefe = pos.get("jefe_veredicto_entrada") or f"{pos.get('jefe_orden', '✅ APROBADA')} — {pos.get('jefe_razon', '')}".strip(" —")
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

    ws_alt = wb.create_sheet(title="2_ALTERNATIVAS_RADAR")
    headers_alt = ["Ranking", "Moneda", "Sello Certificación", "Score Empleado", "Factibilidad Jefe (%)", "Precio Actual", "Decisión 3 Niveles", "Auditoría: Asistente ➔ Empleado ➔ Jefe"]
    ws_alt.append(headers_alt)
    for col_idx in range(1, len(headers_alt) + 1):
        c = ws_alt.cell(row=1, column=col_idx)
        c.fill = fill_hdr
        c.font = font_hdr
        c.alignment = Alignment(horizontal="center")

    activas_syms = {p["symbol"] for p in plan.get("posiciones", [])}
    for idx, alt in enumerate(plan.get("alternativas_evaluadas", []), start=1):
        if alt["symbol"] in activas_syms:
            estado_alt = "✅ ELEGIDA (Asistente+Empleado+Jefe)"
        elif alt.get("en_zona"):
            estado_alt = "🟢 APROBADA POR JEFE (En Reserva)"
        elif alt.get("propuesta_trader_ia"):
            estado_alt = "⛔ VETADA POR JEFE SUPERVISOR"
        elif alt.get("fomo_15m"):
            estado_alt = "⏳ ESPERANDO RETROCESO 15M (Anti-FOMO)"
        elif not alt.get("asistente_validado", True):
            estado_alt = "🚫 BLOQUEADA POR ASISTENTE"
        else:
            estado_alt = "⚪ FUERA FILTRO TÉCNICO EMPLEADO"

        detalle_alt = f"{alt.get('jefe_veredicto', '')} | {alt.get('motivo_tecnico', '')}"
        ws_alt.append([
            idx, alt.get("base", ""), alt.get("origen", ""), alt.get("score", 0),
            alt.get("jefe_factibilidad_pct", 0), float(alt.get("precio_entrada", 0)), estado_alt, detalle_alt
        ])

    ws_aud = wb.create_sheet(title="3_AUDITORIA_IA_24H")
    headers_aud = ["Fecha Auditoría", "Semana", "Semáforo Meta", "Factibilidad (%)", "Diagnóstico 3 Niveles", "Recomendación Jefe Supervisor", "Veredicto Final Semana"]
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

    # Pestaña 5: Autopsia Post-Cierre 24h
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
        f"🔍 <b>GESTOR SEMANAL • BLOQUE 1/3: CADENA BLINDADA (ASISTENTE ➔ EMPLEADO ➔ JEFE)</b>\n"
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
        if a["symbol"] in activas_syms:
            marca = "✅ <b>[APROBADA Y COMPRADA]</b>"
        elif a.get("en_zona"):
            marca = "🟢 <b>[APROBADA POR JEFE]</b>"
        elif a.get("propuesta_trader_ia"):
            marca = "⛔ <b>[VETADA POR JEFE]</b>"
        elif a.get("fomo_15m"):
            marca = "⏳ <i>[ANTI-FOMO 15M]</i>"
        elif not a.get("asistente_validado", True):
            marca = "🚫 <i>[BLOQUEADA ASISTENTE]</i>"
        else:
            marca = "⚪ <i>[FUERA FILTRO EMPLEADO]</i>"

        linea_jefe = f"\n   └ 👔 <i>{html.escape(a.get('jefe_veredicto', ''))}</i>" if (a.get("propuesta_trader_ia") or a.get("fomo_15m") or not a.get("asistente_validado", True)) else ""
        msg += (
            f"<b>{idx}. {a['base']}</b> (Score: <b>{a['score']}</b>) — {marca}\n"
            f"   • Precio: <code>{formatear_precio(a['precio_entrada'])}</code> | {html.escape(a['motivo_tecnico'])}{linea_jefe}\n"
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
        f"🏆 <b>GESTOR BLINDADO 3 NIVELES (NETO FEES 0.20%) • BLOQUE 2/3</b>\n"
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
        msg += "⏳ <i>Sin posiciones abiertas en este momento (esperando clima BTC / aprobación del Jefe Supervisor).</i>\n"
    else:
        for idx, p in enumerate(plan["posiciones"], start=1):
            uid = int(time.time() * 1000) + random.randint(1, 999)
            u_ia = f"{BASE_URL_NETLIFY}/?coin={p['base']}&price={p['precio_actual']}&v={p['base']}_{uid}"
            u_tr = f"{BINANCE_TRADE_BASE}{p['base']}_USDT"
            exp_res = html.escape(p.get("asistente_dictamen") or p.get("expediente_previo_resumen", p.get("origen", "")))
            fib_l = html.escape(p.get("fib_lectura", "Fib N/D"))
            orden_tr = html.escape(p.get("trader_ia_orden", "🟢 MANTENER"))
            razon_tr = html.escape(p.get("trader_ia_razon", ""))
            orden_jf = html.escape(p.get("jefe_orden", "✅ APROBADA"))
            razon_jf = html.escape(p.get("jefe_razon", p.get("jefe_veredicto_entrada", "")))
            stop_act = float(p.get("stop_actual_pct", STOP_LOSS_FIJO_PCT))
            stop_label = f"🛡️ Trailing BE: <code>+{stop_act:.2f}%</code>" if stop_act > 0 else f"Stop: <code>{stop_act:.2f}%</code>"
            tp1_tag = "✅ TP1 50% cobrado" if p.get("tp1_ejecutado") else f"TP1 50%: <code>+{TP1_ASEGURAR_PCT}%</code>"
            dd_val = float(p.get("max_drawdown_pct", 0.0))

            msg += (
                f"🟢 <b>{idx}. {p['base']}</b> — Cupo 25%: <code>${p['capital_usd']:,.2f} USD</code>\n"
                f"• <b>Entrada:</b> <code>{formatear_precio(p['precio_entrada'])}</code> ➔ <b>Actual:</b> <code>{formatear_precio(p['precio_actual'])}</code> (<b>{p['pnl_pct']:+.2f}% neto</b> | <code>${p['pnl_usd']:+.2f}</code> | MaxDD: <code>{dd_val:.2f}%</code>)\n"
                f"• <b>Cosecha:</b> {tp1_tag} | {stop_label} | <code>{fib_l}</code>\n"
                f"• <b>🗂️ 1. Asistente (Ecosistema):</b> <i>{exp_res}</i>\n"
                f"• <b>🤖 2. Empleado (Trader IA):</b> <b>{orden_tr}</b> — <i>{razon_tr}</i>\n"
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

    # PASO 1 (NIVEL 1): EL ASISTENTE RECOLECTA ECOSISTEMA + EJECUTA AUTOPSIA POST-CIERRE 24H
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
            if float(p_prot.get("pnl_pct", 0.0)) >= 0.60:
                p_prot["forzar_be_panico_btc"] = True
        if cooldown_panico_cumplido(plan.get("ultimo_panico_btc_iso", "")):
            plan["ultimo_panico_btc_iso"] = ahora_dt.isoformat()
            enviar_telegram_texto(
                f"🚨 <b>INTERRUPTOR PÁNICO MACRO BTC (-1.0% EN 1H)</b>\n"
                f"📅 <code>{ahora_str}</code>\n\n"
                f"⚠️ {html.escape(msg_btc)}\n"
                f"🛡️ <i>Compras pausadas y Stops elevados automáticamente a Break-Even neto (+0.25%) en posiciones en verde.</i>"
            )

    # PASO 2 (NIVEL 1 -> NIVEL 2): DOSSIERS DEL ASISTENTE + LECTURA EN VIVO DEL EMPLEADO
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
        if pos.get("tp1_ejecutado", False):
            stop_dinamico_pct = 2.0
        elif max_pnl_pct >= 8.0:
            stop_dinamico_pct = 4.0
        elif max_pnl_pct >= 3.5:
            stop_dinamico_pct = 1.5
        elif max_pnl_pct >= 2.2:
            stop_dinamico_pct = 0.35
        elif pos.get("forzar_be_panico_btc", False):
            stop_dinamico_pct = 0.25

        pos["precio_actual"] = p_act
        pos["precio_maximo"] = p_max
        pos["max_drawdown_pct"] = max_dd_pct
        pos["pnl_pct"] = round(pnl_pct, 2)
        pos["pnl_usd"] = round(pnl_usd, 2)
        pos["stop_actual_pct"] = stop_dinamico_pct
        pos["expediente_previo_resumen"] = dossier_asistente["resumen_corto"]
        pos["asistente_dictamen"] = dossier_asistente["dictamen_asistente"]
        pos.setdefault("motivo_eleccion", pos.get("origen", "🛡️ Certificada IA"))

        if not pos.get("tp1_ejecutado", False) and pnl_pct >= TP1_ASEGURAR_PCT:
            cap_vendido = round(cap * 0.5, 2)
            ganancia_tp1 = round(cap_vendido * (pnl_pct / 100.0), 2)
            pos["capital_usd"] = round(cap - cap_vendido, 2)
            pos["tp1_ejecutado"] = True
            pos["stop_actual_pct"] = 2.0
            stop_dinamico_pct = 2.0
            pos["pnl_usd"] = round(pos["capital_usd"] * (pnl_pct / 100.0), 2)
            plan["ganancia_realizada_usd"] = round(float(plan["ganancia_realizada_usd"]) + ganancia_tp1, 2)
            alertas_parciales.append({
                "base": pos["base"],
                "pnl_pct": round(pnl_pct, 2),
                "ganancia_tp1": ganancia_tp1,
                "precio_actual": p_act,
                "capital_restante": pos["capital_usd"]
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

    # PASO 3 (NIVEL 2): EL EMPLEADO FORMULA PROPUESTAS SOBRE CARTERA Y RADAR (ANTI-FOMO 15M + LIQUIDEZ REAL)
    aud_actual = ejecutar_empleado_trader_ia(s, mapa_mkt, plan, msg_btc, lecturas_tecnicas, boletin_asistente, eco)

    excluidas = {p["symbol"] for p in plan["posiciones"]} | {c["symbol"] for c in plan["historial_cierres"] if c.get("semana_id") == plan["semana_id"]}
    alternativas = empleado_evaluar_candidatas(s, mapa_mkt, excluidas, eco, plan)

    # PASO 4 (NIVEL 3): EL JEFE SUPERVISOR AUDITA TODO (INCLUYENDO AUTOPSIA 24H) Y DA EL VEREDICTO FINAL
    ejecutar_jefe_supervisor_ia(plan, alternativas, [x for x in posiciones_evaluadas if not x.get("sin_datos")], boletin_asistente, msg_btc)
    plan["alternativas_evaluadas"] = alternativas

    # PASO 5: EJECUCIÓN BLINDADA
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

        motivo_cierre = None
        if pos.get("tp1_ejecutado", False) and retroceso_desde_max <= -TRAILING_DESDE_MAX_PCT:
            motivo_cierre = f"🎯 CIERRE 2ª MITAD (Trailing Stop): tocó máx +{max_pnl_pct:.1f}% y retrocedió {retroceso_desde_max:.1f}%."
        elif not pos.get("tp1_ejecutado", False) and pnl_pct >= 18.0 and retroceso_desde_max <= -2.0:
            motivo_cierre = f"🚀 EXPLOSIÓN CAPTURADA: +{pnl_pct:.1f}% neto asegurado antes de corrección."
        elif pnl_pct <= STOP_LOSS_FIJO_PCT or pnl_usd <= -MAX_PERDIDA_USD:
            motivo_cierre = f"🛑 STOP LOSS ({pnl_pct:.2f}% neto | ${pnl_usd:+.2f} USD): corta pérdida controlada y libera cupo."
        elif stop_dinamico_pct > 0 and pnl_pct <= stop_dinamico_pct:
            motivo_cierre = f"🛡️ TRAILING BREAK-EVEN (+{stop_dinamico_pct:.2f}% neto): subió hasta +{max_pnl_pct:.1f}% y aseguró ganancia en {pnl_pct:+.2f}%."
        elif not pos.get("tp1_ejecutado", False) and item["propuesta_cierre_palanca"] and item["cierre_aprobado_jefe"]:
            motivo_cierre = f"👔 CIERRE APROBADO POR JEFE: {item['motivo_palanca']}"
        elif not pos.get("tp1_ejecutado", False) and horas_abierta >= HORAS_MAX_SIN_ARRANQUE and pnl_pct < 1.5:
            motivo_cierre = f"⏳ ROTACIÓN RÁPIDA ({int(horas_abierta)}h lateral en {pnl_pct:+.1f}% neto): libera cupo para moneda en verde."

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
            if (pnl_pct <= -1.55 or pnl_usd <= -PREALERTA_PERDIDA_USD) and not pos.get("prealerta_palanca_enviada", False):
                pos["prealerta_palanca_enviada"] = True
                prealertas_palanca.append(pos)
            elif pnl_pct > -0.80:
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

    # MEJORA 4: Circuit Breaker Diario + Entrada Escalonada (máx 2 por corrida)
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
            elegidas = [a for a in alternativas if a.get("en_zona")][:cupos]

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
                        "motivo_eleccion": el["motivo_tecnico"],
                        "expediente_previo_resumen": dossier_el.get("resumen_corto", ""),
                        "asistente_dictamen": dossier_el.get("dictamen_asistente", ""),
                        "jefe_veredicto_entrada": el.get("jefe_veredicto", "✅ APROBADA POR JEFE"),
                        "jefe_orden": "✅ ENTRADA APROBADA",
                        "jefe_razon": el.get("jefe_veredicto", ""),
                        "trader_ia_orden": "🟢 PROPUESTA COMPRA",
                        "trader_ia_razon": el["motivo_tecnico"],
                        "fecha_entrada": ahora_str,
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
            f"• <b>Rendimiento flotante neto:</b> <b>{pre['pnl_pct']:+.2f}%</b> (<b>${pre['pnl_usd']:+.2f} USD</b>) — <i>Stop técnico: {STOP_LOSS_FIJO_PCT}%</i>\n"
            f"• <b>🗂️ Asistente:</b> <i>{html.escape(pre.get('asistente_dictamen', ''))}</i>\n"
            f"• <b>🤖 Empleado:</b> <i>{html.escape(pre.get('trader_ia_razon', ''))}</i>\n"
            f"• <b>👔 Jefe:</b> <i>{html.escape(pre.get('jefe_razon', ''))}</i>"
        )

    for parc in alertas_parciales:
        enviar_telegram_texto(
            f"💰 <b>COSECHA PARCIAL TP1 (+{TP1_ASEGURAR_PCT}% NETO) • {parc['base']}</b>\n"
            f"📅 <code>{ahora_str}</code>\n\n"
            f"• <b>Rendimiento neto alcanzado:</b> <b>+{parc['pnl_pct']:.2f}%</b> en <code>{formatear_precio(parc['precio_actual'])}</code>\n"
            f"• <b>Ganancia neta en caja:</b> <b>+${parc['ganancia_tp1']:.2f} USD</b> (50% vendido)\n"
            f"• <b>Saldo restante corriendo:</b> <code>${parc['capital_restante']:,.2f} USD</code> blindado en <b>+2.0%</b> con Trailing Stop."
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
            titulo_ev = f"🔄 <b>ROTACIÓN BLINDADA 3 NIVELES / STOP {STOP_LOSS_FIJO_PCT}%</b>"
        elif nuevas_entradas:
            titulo_ev = "🆕 <b>NUEVA COMPRA APROBADA (ASISTENTE ➔ EMPLEADO ➔ JEFE)</b>"
        elif alertas_venta or alertas_parciales:
            titulo_ev = f"💰 <b>COSECHA DE GANANCIAS TP1 (+{TP1_ASEGURAR_PCT}% NETO) / CIERRE</b>"
        else:
            titulo_ev = "📡 <b>RADAR CONTINUO • ESTRUCTURA BLINDADA (ASISTENTE ➔ EMPLEADO ➔ JEFE)</b>"

        caption = construir_bloque_2_cartera(plan, titulo_ev)
        ok2 = enviar_foto_telegram(img, caption)
        time.sleep(1.5)

        ok3 = enviar_excel_telegram(
            f"📎 <b>GESTOR Y RADAR SEMANAL • BLOQUE 3/3: PLANILLA EXCEL</b>\n"
            f"📊 Registro en 5 pestañas con Estructura Blindada de 3 Niveles, Autopsia 24h, Liquidez Real y PnL Neto (<code>{EXCEL_SEMANAL_FILE}</code>)."
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
    print(f"🧪 INICIANDO GESTOR SEMANAL BLINDADO 3 NIVELES + AUTOPSIA + LIQUIDEZ REAL ({ahora_art().strftime('%H:%M:%S')} ART)...")
    ejecutar_gestor_semanal()
