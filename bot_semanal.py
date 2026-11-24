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
PLAN_SEMANAL_FILE = "plan_semanal.json"
EXCEL_SEMANAL_FILE = "AUDITORIA_SEMANAL_PRUEBA.xlsx"

# Parámetros operativos: Motor Siempre en Verde + Cosecha Escalonada + Consenso Multi-Bot
CAPITAL_INICIAL_PRUEBA = 3500.0
META_SEMANAL_USD = 600.0
MAX_MONEDAS_SEMANA = 4
TOP_ALTERNATIVAS_MOSTRAR = 8

MAX_PERDIDA_USD = 16.0          # Tope preventivo en -$16 para evitar deslizamientos > -$20 entre ciclos de 15m
PREALERTA_PERDIDA_USD = 10.0    # Pre-alerta temprana
TP1_ASEGURAR_PCT = 4.8          # Vende 50% al tocar +4.8% para asegurar ganancia real en caja
TRAILING_DESDE_MAX_PCT = 2.2    # Trailing Stop para la 2ª mitad corredora
HORAS_MAX_SIN_ARRANQUE = 8.0    # Rotación rápida (8h) si no arranca

MODELOS_GEMINI = ["gemini-3.5-flash-lite", "gemini-3.8-flash", "gemini-4-hydrogen"]

def ahora_art():
    return datetime.now(TZ_ART)

def id_semana_actual(dt=None):
    dt = dt or ahora_art()
    iso_year, iso_week, _ = dt.isocalendar()
    return f"{iso_year}-W{iso_week:02d}"

def calcular_stop_usd_pct(capital_usd):
    cap = max(float(capital_usd), 1.0)
    return round(-(MAX_PERDIDA_USD / cap) * 100.0, 2)

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

def recopilar_inteligencia_ecosistema():
    """
    INTEGRADOR DE TRABAJO PREVIO DE TODOS LOS BOTS:
    Lee historial_perlas.json, historial_ganadoras.json y escanea automáticamente
    cualquier otro JSON generado por los bots de Sentimiento, Central Inteligencia o Perdedoras
    en el repositorio para construir un expediente unificado por moneda y macro.
    """
    perlas = cargar_json_seguro(HISTORIAL_PERLAS_FILE)
    ganadoras = cargar_json_seguro(HISTORIAL_GANADORAS_FILE)

    graduadas = perlas.get("graduadas_pre_explosion", {}) if isinstance(perlas, dict) else {}
    posta = perlas.get("posta", {}) if isinstance(perlas, dict) else {}
    reg_verdes = ganadoras.get("registro_verdes", {}) if isinstance(ganadoras, dict) else {}

    vetadas_perdedoras = set()
    resumen_macro_bots = []
    notas_extra_monedas = {}

    archivos_ignorar = {PLAN_SEMANAL_FILE, "package.json", "package-lock.json", "tsconfig.json"}
    for ruta in sorted(glob.glob("*.json")):
        if ruta in archivos_ignorar or ruta in (HISTORIAL_PERLAS_FILE, HISTORIAL_GANADORAS_FILE):
            continue
        data = cargar_json_seguro(ruta)
        if not isinstance(data, dict) or not data:
            continue
        nombre_l = ruta.lower()

        # Captura listas de perdedoras si existen en el repo
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

        # Captura diagnósticos de Sentimiento / Central de Inteligencia / Noticias
        if any(tag in nombre_l for tag in ("sentimiento", "noticia", "central", "inteligencia", "mercado", "macro", "clima")):
            for campo in ("resumen", "diagnostico", "sentimiento", "estado_mercado", "veredicto", "alerta", "conclusiones"):
                val = data.get(campo)
                if isinstance(val, str) and val.strip():
                    resumen_macro_bots.append(f"[{ruta}] {val.strip()[:140]}")
                    break

        # Captura cualquier análisis puntual por moneda guardado en otros JSON
        for k, v in data.items():
            if isinstance(k, str) and k.endswith("USDT") and isinstance(v, dict):
                txt_nota = v.get("razon") or v.get("analisis") or v.get("motivo") or v.get("diagnostico") or ""
                if isinstance(txt_nota, str) and txt_nota.strip():
                    notas_extra_monedas.setdefault(k, []).append(f"{ruta}: {txt_nota.strip()[:110]}")

    return {
        "perlas": perlas,
        "ganadoras": ganadoras,
        "graduadas": graduadas,
        "posta": posta,
        "reg_verdes": reg_verdes,
        "vetadas_perdedoras": vetadas_perdedoras,
        "macro_bots": resumen_macro_bots[:4],
        "notas_extra": notas_extra_monedas
    }

def construir_expediente_moneda(sym, p_actual, eco):
    """Construye la ficha completa de inteligencia previa de una moneda para el Trader IA."""
    grad = eco["graduadas"].get(sym, {})
    post = eco["posta"].get(sym, {})
    verd = eco["reg_verdes"].get(sym, {})

    p_ref = float(grad.get("precio_ref") or post.get("precio_ref") or verd.get("precio_entrada") or p_actual or 0)
    var_desde_radar = round(((p_actual - p_ref) / p_ref) * 100, 2) if p_ref > 0 and p_actual > 0 else 0.0

    semaforo = str(grad.get("semaforo") or post.get("semaforo") or ("VERDE" if verd else "N/D")).upper()
    etapa = int(post.get("etapa", grad.get("etapa", 0)))
    blindaje = int(grad.get("blindaje_pct") or post.get("blindaje_etapa1") or grad.get("probabilidad_pct") or 70)
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
    max_hist_verde = float(verd.get("max_ganancia_pct", verd.get("ganancia_pct", 0.0)))
    en_lista_perdedoras = (sym in eco["vetadas_perdedoras"]) or ("PERDEDORA" in estado_hist_verde) or ("STOP" in estado_hist_verde)

    resumen_corto = (
        f"Semáforo:{semaforo} | Etapa:{etapa} | DesdeRadar:{var_desde_radar:+.1f}% | "
        f"HistVerdes:{estado_hist_verde} (Máx {max_hist_verde:+.1f}%)"
    )
    if tesis_textos:
        resumen_corto += f" | Tesis: {tesis_textos[0][:90]}"

    return {
        "semaforo_radar": semaforo,
        "etapa_cazador": etapa,
        "blindaje_pct": blindaje,
        "doble_certificada": (cert_e1 and cert_e2),
        "precio_referencia_radar": p_ref,
        "var_desde_deteccion_radar_pct": var_desde_radar,
        "estado_historial_ganadoras": estado_hist_verde,
        "max_ganancia_historica_pct": max_hist_verde,
        "alertada_en_perdedoras": en_lista_perdedoras,
        "tesis_previa_bots": " | ".join(tesis_textos)[:260] if tesis_textos else "Sin nota textual adicional en JSON",
        "resumen_corto": resumen_corto
    }

def auditar_order_book_semanal(session, symbol):
    """Verificación estricta del libro de órdenes en tiempo real (exige presión compradora >= 1.15x)."""
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
                vb = sum(float(x[0]) * float(x[1]) for x in bids)
                va = sum(float(x[0]) * float(x[1]) for x in asks)
                ratio = round(vb / va, 2) if va > 0 else 1.0
                return {
                    "ok": True,
                    "spread_pct": round(spread, 3),
                    "ratio_ba": ratio,
                    "sano": (spread <= 0.40 and ratio >= 1.15)
                }
        except Exception:
            continue
    return {"ok": False, "spread_pct": 0.1, "ratio_ba": 1.0, "sano": False}

def analizar_velas_tf(session, symbol, interval="1h", limit=48):
    """Analiza RSI, Volumen, impulso en 3 velas, rachas, rechazo de mecha y Fibonacci."""
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
                rechazo_techo = (rango_vela > 0 and (mecha_sup / rango_vela) >= 0.55)

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

def evaluar_palanca_emergencia(pos, v1m, v15, v1h, fib, ob, pnl_pct, max_pnl_pct, retroceso_desde_max, exp_previo):
    """
    Palanca de Emergencia ('3 pasos adelante') integrada con la tesis previa de los bots:
    Corta caídas reales o invalidación de tesis antes de tocar -$16/-$20 USD.
    """
    p_act = float(pos.get("precio_actual", 0))
    perdio_fib_618 = False
    if fib.get("ok"):
        perdio_fib_618 = (p_act < float(fib["fib_618"]) or float(fib["ratio"]) > 0.62)

    # Sensor 0 (CONSENSO ECOSISTEMA): Si otro bot la marcó como perdedora activa y está en negativo, corta ya
    if exp_previo.get("alertada_en_perdedoras") and pnl_pct <= -0.5:
        return True, (
            f"🚨 PALANCA ECOSISTEMA (Alerta Bot Perdedoras): marcada en baja por radar previo y en {pnl_pct:+.2f}%. "
            f"Corta inmediatamente."
        )

    # Sensor 1 (EN VIVO 1m): Desplome real en 3 minutos o vela violenta con volumen
    if v1m.get("ok"):
        if (v1m["var_3velas"] <= -1.10 and v1m["vol_ratio"] >= 1.5) or (v1m["var_ultima"] <= -0.95 and v1m["vol_ratio"] >= 1.8):
            return True, (
                f"🚨 PALANCA EMERGENCIA 1M (Desplome en Vivo): caída {v1m['var_3velas']:+.2f}% en 3m "
                f"(vol {v1m['vol_ratio']}x). Corta antes de profundizar en {pnl_pct:+.2f}%."
            )

    # Sensor 2 (EN VIVO 1m + 15m): La moneda venía ganando (+2.0% o más) y gira brusco desde el pico
    if max_pnl_pct >= 2.0 and retroceso_desde_max <= -1.2:
        giro_1m = v1m.get("ok") and (v1m["velas_rojas_seg"] >= 2 or v1m["var_3velas"] <= -0.70)
        giro_15m = v15.get("ok") and (v15.get("rechazo_techo") or v15.get("var_ultima", 0) <= -0.75)
        if giro_1m or giro_15m:
            return True, (
                f"🚨 PALANCA EMERGENCIA (Giro en Vivo 1m/15m): subió hasta +{max_pnl_pct:.1f}% y retrocedió "
                f"{retroceso_desde_max:.1f}% ({v1m.get('velas_rojas_seg', 0)} velas rojas 1m). Asegura salida en {pnl_pct:+.2f}%."
            )

    # Sensor 3: Invalidación de tesis previa (perdió Fib 0.618 y cayó bajo precio_ref del radar)
    p_ref_radar = float(exp_previo.get("precio_referencia_radar", 0))
    bajo_precio_radar = (p_ref_radar > 0 and p_act < p_ref_radar * 0.992)
    if pnl_pct <= -0.80 and (perdio_fib_618 or bajo_precio_radar):
        return True, (
            f"🚨 PALANCA TESIS INVALIDADA: rompió Fib 0.618 / precio base del radar en {pnl_pct:+.2f}%. "
            f"Corta antes del tope."
        )

    if pnl_pct <= -1.0 and v15.get("ok") and v15.get("velas_rojas_seg", 0) >= 3:
        return True, (
            f"🚨 PALANCA EMERGENCIA (3 Velas Rojas 15m): presión vendedora sostenida en {pnl_pct:+.2f}%. "
            f"Libera capital."
        )

    return False, ""

def verificar_clima_btc(session, mapa_mkt):
    btc = mapa_mkt.get("BTCUSDT")
    if not btc:
        return True, "BTC estable"
    chg_24h = float(btc["cambio_24h"])
    mom_btc = analizar_velas_tf(session, "BTCUSDT", "1h", 24)
    rsi_btc = float(mom_btc.get("rsi", 50.0))
    if chg_24h <= -2.0 or rsi_btc < 35.0:
        return False, f"BTC en alerta (24h: {chg_24h:+.2f}%, RSI 1h: {rsi_btc}). Compras pausadas."
    return True, f"BTC estable (24h: {chg_24h:+.2f}%, RSI 1h: {rsi_btc})"

def cargar_plan_semanal():
    sem = id_semana_actual()
    base = {
        "semana_id": sem,
        "fecha_inicio": ahora_art().strftime("%Y-%m-%d %H:%M"),
        "modo": "CONSENSO_ECOSISTEMA_SIEMPRE_VERDE_MAX16USD",
        "capital_total_usd": CAPITAL_INICIAL_PRUEBA,
        "meta_semanal_usd": META_SEMANAL_USD,
        "ganancia_realizada_usd": 0.0,
        "estado_semana": "ACTIVA",
        "fecha_cierre_meta": "",
        "aviso_btc_enviado": False,
        "ultimo_reporte_hora": -1,
        "auditoria_ia": {},
        "historial_auditorias": [],
        "alternativas_evaluadas": [],
        "posiciones": [],
        "historial_cierres": []
    }
    data = cargar_json_seguro(PLAN_SEMANAL_FILE)
    if data and data.get("semana_id") == sem:
        data.setdefault("aviso_btc_enviado", False)
        data.setdefault("ultimo_reporte_hora", -1)
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

def evaluar_alternativas_al_horno(session, mapa_mkt, excluidas, eco):
    """
    Selección guiada por el ecosistema completo:
    Cruza Pre-Explosión + Cazador Táctico + Ganadoras + Perdedoras + Order Book + Fib 4H.
    """
    graduadas = eco["graduadas"]
    posta_dict = eco["posta"]
    if not graduadas and not posta_dict:
        return []

    candidatos = []
    universo_syms = list(dict.fromkeys(list(graduadas.keys()) + list(posta_dict.keys())))

    for sym in universo_syms:
        if sym not in mapa_mkt:
            continue
        mkt = mapa_mkt[sym]
        exp = construir_expediente_moneda(sym, mkt["precio"], eco)
        mom_1h = analizar_velas_tf(session, sym, "1h", 36)
        mom_4h = analizar_velas_tf(session, sym, "4h", 48)
        fib_4h = mom_4h.get("fib", {})
        ob = auditar_order_book_semanal(session, sym)

        var_radar = exp["var_desde_deteccion_radar_pct"]
        prob = exp["blindaje_pct"]
        cert_doble = exp["doble_certificada"]
        etapa = exp["etapa_cazador"]
        semaforo = exp["semaforo_radar"]

        fib_sano = (not fib_4h.get("ok")) or (not fib_4h.get("en_soporte_profundo", False))
        impulso_verde = (
            var_radar >= 0.0
            and 0.5 <= mkt["cambio_24h"] <= 12.5
            and (mom_1h["var_3velas"] > 0.0 or mom_1h["var_ultima"] > 0.0)
            and mom_1h["vol_ratio"] >= 1.05
        )

        bono_semaforo = 12 if "VERDE" in semaforo else (6 if "AMARILLO" in semaforo else 0)
        bono_cert = 20 if cert_doble else (10 if (sym in graduadas) else 0)
        bono_fib = 14 if fib_4h.get("en_zona_dorada") else (6 if fib_4h.get("en_tramo_alcista") else (-25 if not fib_sano else -6))
        bono_ob = 10 if ob.get("ratio_ba", 0) >= 1.25 else (5 if ob.get("sano") else -20)
        bono_verde = 12 if impulso_verde else -18
        bono_hist = -35 if exp["alertada_en_perdedoras"] else (12 if "GANADORA" in exp["estado_historial_ganadoras"] else 0)

        score = prob + bono_semaforo + bono_cert + bono_ob + bono_fib + bono_verde + bono_hist + (5 if mom_1h["vol_ratio"] >= 1.25 else 0)

        en_zona = (
            not exp["alertada_en_perdedoras"]
            and impulso_verde
            and var_radar <= 8.5
            and fib_sano
            and mom_1h["rsi"] <= 69.0
            and ob.get("sano", False)
        )

        sello_txt = "🛡️🛡️ DOBLE CERT. IA" if cert_doble else (f"🛡️ Semáforo {semaforo} (E{etapa})" if semaforo != "N/D" else f"Cazador Etapa {etapa}")
        fib_tag = f" | {fib_4h.get('zona_txt', 'Fib N/D')}" if fib_4h.get("ok") else ""
        motivo_tecnico = (
            f"{sello_txt} ({var_radar:+.1f}% radar | 1h: {mom_1h['var_3velas']:+.1f}%) | "
            f"OB: {ob['ratio_ba']}x | RSI 1h: {mom_1h['rsi']}{fib_tag} | Blindaje: {prob}%"
        )
        candidatos.append({
            "symbol": sym,
            "base": sym[:-4],
            "precio_entrada": mkt["precio"],
            "origen": sello_txt,
            "probabilidad": prob,
            "score": score,
            "certificada_doble": cert_doble,
            "en_zona": en_zona and (sym not in excluidas),
            "ya_en_cartera": sym in excluidas,
            "motivo_tecnico": motivo_tecnico,
            "expediente_previo": exp,
            "mom": mom_1h,
            "fib_4h": fib_4h
        })

    candidatos.sort(key=lambda x: (x["en_zona"], x["certificada_doble"], x["score"], x["mom"]["vol_ratio"]), reverse=True)
    return candidatos[:TOP_ALTERNATIVAS_MOSTRAR]

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

def evaluar_copiloto_trader_y_auditor_ia(session, mapa_mkt, plan, clima_btc_txt, lecturas_tecnicas, eco):
    """
    Módulo IA Integrado con MEMORIA COMPLETA DEL ECOSISTEMA:
    Cruza el trabajo previo de Pre-Explosión, Cazador Táctico, Ganadoras, Perdedoras y Sentimiento
    con el pulso en vivo de 1m + 15m + Fibonacci para decidir si la tesis sigue viva o hay que salir.
    """
    posiciones = plan.get("posiciones", [])
    datos_posiciones = []

    for p in posiciones:
        sym = p["symbol"]
        tec = lecturas_tecnicas.get(sym, {})
        v1m = tec.get("v1m") or analizar_velas_tf(session, sym, "1m", 30)
        v15 = tec.get("v15") or analizar_velas_tf(session, sym, "15m", 24)
        v1h = tec.get("v1h") or analizar_velas_tf(session, sym, "1h", 36)
        fib = tec.get("fib") or {}
        exp_previo = tec.get("expediente_previo") or construir_expediente_moneda(sym, float(p.get("precio_actual", 0)), eco)

        p["expediente_previo_resumen"] = exp_previo["resumen_corto"]

        p_ent = float(p.get("precio_entrada", 0))
        p_max = float(p.get("precio_maximo", p_ent))
        p_act = float(p.get("precio_actual", p_ent))
        retroceso_max = round(((p_act - p_max) / p_max) * 100, 2) if p_max > 0 else 0.0

        pnl_pct = float(p.get("pnl_pct", 0.0))
        pnl_usd = float(p.get("pnl_usd", 0.0))
        obj_pct = float(p.get("subida_necesaria_pct", 17.14))
        stop_act = float(p.get("stop_actual_pct", calcular_stop_usd_pct(p.get("capital_usd", 875))))

        fib_resumen = "Fib N/D"
        cerca_techo_fib = False
        perdio_fib_618 = False
        if fib.get("ok"):
            fib_resumen = f"{fib['zona_txt']} | Sop 0.618: {formatear_precio(fib['fib_618'])} | Ext 1.618: {formatear_precio(fib['ext_1618'])}"
            cerca_techo_fib = fib.get("cerca_ext_1618", False)
            perdio_fib_618 = (p_act < float(fib["fib_618"]) or float(fib["ratio"]) > 0.62)
        p["fib_lectura"] = fib_resumen

        es_ruido_1m = (abs(v1m["var_3velas"]) < 0.55 and v1m["vol_ratio"] < 1.5)
        pulso_1m_txt = f"1m: {v1m['var_3velas']:+.2f}% (3m) | RSI 1m: {v1m['rsi']} | Vol: {v1m['vol_ratio']}x"
        if es_ruido_1m:
            pulso_1m_txt += " [Ruido normal]"

        var_radar = exp_previo["var_desde_deteccion_radar_pct"]
        tesis_viva = (not perdio_fib_618) and (not exp_previo["alertada_en_perdedoras"])

        if exp_previo["alertada_en_perdedoras"]:
            orden_def = "🚨 VENDER AHORA (Alerta Bot Perdedoras)"
            razon_def = f"Reportada en baja por ecosistema previo ({exp_previo['estado_historial_ganadoras']}). Proteger capital."
        elif (pnl_pct >= obj_pct or cerca_techo_fib or var_radar >= 22.0) and (v1m["rsi"] >= 78 or v15["rsi"] >= 72 or v15["rechazo_techo"] or retroceso_max <= -1.8):
            orden_def = "🚨 VENDER AHORA (Techo 1m/Fib + Recorrido Radar)"
            razon_def = f"Acumula {var_radar:+.1f}% desde detección radar y muestra agotamiento (RSI 1m={v1m['rsi']}, 15m={v15['rsi']})."
        elif not p.get("tp1_ejecutado", False) and pnl_pct >= TP1_ASEGURAR_PCT * 0.85:
            orden_def = f"🟡 CERCA TP1 (+{TP1_ASEGURAR_PCT}%)"
            razon_def = f"Tesis {exp_previo['semaforo_radar']} confirmada (+{pnl_pct:.1f}%): próximo a asegurar 50% en +{TP1_ASEGURAR_PCT}%."
        elif pnl_usd <= -PREALERTA_PERDIDA_USD or (pnl_pct <= -0.9 and not tesis_viva):
            orden_def = "⚠️ ALERTA PALANCA / TESIS EN RIESGO"
            razon_def = f"PnL ${pnl_usd:+.2f} USD | {pulso_1m_txt} | Vigilar invalidación de soporte Fib 0.618."
        else:
            proteccion_txt = f"Trailing BE +{stop_act:.2f}%" if stop_act > 0 else f"Tope -${MAX_PERDIDA_USD:.0f}"
            orden_def = "🟢 MANTENER / TESIS VIVA"
            razon_def = f"Tesis {exp_previo['semaforo_radar']} activa ({var_radar:+.1f}% radar) | {pulso_1m_txt} | {proteccion_txt}."

        p["trader_ia_orden"] = orden_def
        p["trader_ia_razon"] = razon_def

        datos_posiciones.append({
            "moneda": p["base"],
            "inteligencia_previa_bots": exp_previo,
            "tesis_original_sigue_viva": tesis_viva,
            "pnl_pct": pnl_pct,
            "pnl_usd": pnl_usd,
            "tp1_ejecutado": bool(p.get("tp1_ejecutado", False)),
            "tp1_objetivo_pct": TP1_ASEGURAR_PCT,
            "max_perdida_permitida_usd": -MAX_PERDIDA_USD,
            "stop_proteccion_actual_pct": stop_act,
            "retroceso_desde_max_pct": retroceso_max,
            "pulso_en_vivo_1m": {
                "var_ultima_1m_pct": v1m["var_ultima"],
                "var_3min_pct": v1m["var_3velas"],
                "rsi_1m": v1m["rsi"],
                "vol_1m_ratio": v1m["vol_ratio"],
                "velas_rojas_seguidas_1m": v1m["velas_rojas_seg"],
                "solo_ruido_sin_volumen": es_ruido_1m
            },
            "rsi_15m": v15["rsi"],
            "rechazo_15m": v15["rechazo_techo"],
            "rsi_1h": v1h["rsi"],
            "fibonacci_4h": fib_resumen,
            "perdio_soporte_0618": perdio_fib_618,
            "orden_base": orden_def
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
    macro_bots_txt = " | ".join(eco["macro_bots"]) if eco["macro_bots"] else "Sin alertas externas negativas en JSON"

    auditoria_res = {
        "fecha": ahora_art().strftime("%Y-%m-%d %H:%M ART"),
        "semana_id": plan["semana_id"],
        "semaforo_meta": "🟢 EN CAMINO A META" if (real + flot) >= 0 else "🟡 EN CONSOLIDACIÓN",
        "factibilidad_pct": min(96, max(48, int(68 + (stats_emb["tasa_pct"] * 0.25) + ((real + flot) / 25.0)))),
        "diagnostico_24h": f"Consenso Ecosistema: {resumen_emb_txt}. {clima_btc_txt}. Avance cuota: {progreso_pct}%.",
        "recomendacion_auditor": f"Trader IA integrado con análisis previo (Pre-Explosión + Ganadoras + Fib <= 0.62) y TP1 +{TP1_ASEGURAR_PCT}%.",
        "veredicto_final_semana": plan.get("auditoria_ia", {}).get("veredicto_final_semana", "En seguimiento activo...")
    }

    if GEMINI_API_KEY and datos_posiciones:
        try:
            client = genai.Client(api_key=GEMINI_API_KEY)
            prompt = (
                "Eres el Director de Ejecución y Copiloto Trader IA de un ecosistema multi-bot en Binance Spot.\n"
                "REGLA FUNDAMENTAL: TODO el trabajo previo de análisis de los otros bots ('inteligencia_previa_bots': Pre-Explosión, Cazador Táctico, Ganadoras, Perdedoras y Sentimiento) "
                "DEBE ser la base de tu decisión en vivo:\n"
                "1) Si 'tesis_original_sigue_viva' es true y la moneda recién inicia su recorrido desde 'precio_referencia_radar', NO cierres por ruido menor de 1m; deja madurar hacia TP1 (+4.8%) y el corredor.\n"
                "2) Si ya acumuló mucho recorrido desde 'precio_referencia_radar' (+15% o más) o toca Ext Fib 1.618 con rechazo en 1m/15m, ordena asegurar ganancia.\n"
                "3) Si la tesis previa se invalida (pierde Fib 0.618, cae bajo precio del radar o entra en Perdedoras), corta de inmediato antes de tocar -$16 USD.\n\n"
                f"CLIMA BTC: {clima_btc_txt}\n"
                f"CONTEXTO OTROS BOTS MACRO/NOTICIAS: {macro_bots_txt}\n"
                f"AVANCE SEMANAL: ${real + flot:+.2f} / ${meta:.0f} USD ({progreso_pct}%)\n"
                f"ESTADO EMBUDO PREVIO: {resumen_emb_txt}\n"
                f"POSICIONES CON EXPEDIENTE PREVIO + PULSO EN VIVO:\n{json.dumps(datos_posiciones, ensure_ascii=False)}\n\n"
                "Responde ÚNICAMENTE en JSON válido sin bloques markdown:\n"
                '{"semaforo_meta":"🟢 FACTIBLE | 🟡 EN OBSERVACIÓN | 🔴 RIESGO","factibilidad_pct":80,'
                '"diagnostico_24h":"análisis breve en 1 oración integrando el avance y el contexto de los bots",'
                '"recomendacion_auditor":"consejo técnico concreto considerando la tesis previa y el pulso actual",'
                '"ordenes":{"MONEDA":{"orden":"🟢 MANTENER / TESIS VIVA | 🟡 ASEGURAR 50% (TP1) | 🚨 VENDER AHORA (AGOTAMIENTO) | ⚠️ ALERTA PALANCA / TESIS EN RIESGO","razon":"motivo corto citando el análisis previo (semáforo/recorrido radar/Fib) y el pulso 1m/15m"}}}'
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
            print(f"⚠️ Fallback IA integrada: {e}")

    plan["auditoria_ia"] = auditoria_res
    return auditoria_res

def generar_veredicto_final_ia(plan):
    cierres = [c for c in plan.get("historial_cierres", []) if c.get("semana_id") == plan["semana_id"]]
    ganadoras = [c for c in cierres if float(c.get("pnl_usd", 0)) > 0]
    perdedoras = [c for c in cierres if float(c.get("pnl_usd", 0)) <= 0]
    win_rate = round((len(ganadoras) / len(cierres)) * 100, 1) if cierres else 100.0
    total_usd = float(plan.get("ganancia_realizada_usd", 0.0))
    meta_usd = float(plan.get("meta_semanal_usd", META_SEMANAL_USD))

    veredicto_base = (
        f"✅ <b>VEREDICTO: META LOGRADA — CONSENSO MULTI-BOT FACTIBLE</b>\n"
        f"• Se alcanzaron <b>${total_usd:,.2f} USD</b> (Meta: ${meta_usd:,.0f} USD) con <b>{win_rate}% de acierto</b> "
        f"({len(ganadoras)} ganadoras / {len(perdedoras)} cerradas en protección).\n"
        f"• La integración del análisis previo de todos los bots con el Copiloto en vivo 1m/15m + TP1 +{TP1_ASEGURAR_PCT}% protegió el capital y capturó ganancias."
    )

    if GEMINI_API_KEY and cierres:
        try:
            client = genai.Client(api_key=GEMINI_API_KEY)
            prompt = (
                "Eres el Auditor Jefe de un fondo cuantitativo Spot en Binance. "
                "Cumplimos la meta semanal integrando el análisis previo de todo el ecosistema de bots con el Trader IA en vivo. "
                "Da un VEREDICTO FINAL DE FACTIBILIDAD para pasar a dinero real.\n"
                f"Capital Base: ${plan.get('capital_total_usd', 3500)} USD | Meta: ${meta_usd} USD | Ganancia Lograda: ${total_usd} USD\n"
                f"Operaciones cerradas: {json.dumps(cierres, ensure_ascii=False)}\n\n"
                "Responde en máximo 4 líneas claras en español."
            )
            raw_ver = llamar_gemini_con_reintento(client, prompt)
            if raw_ver:
                return f"🧠 <b>DICTAMEN FINAL AUDITOR IA:</b>\n{html.escape(raw_ver.strip())}"
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

    categorias = ["Cerrada\n(Caja)", "Flotante\n(En curso)", "Total\nSemana"]
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
    ax1.set_title("PROGRESO CUOTA SEMANAL ($ USD)", color="#ffd600", fontsize=10, fontweight="bold", pad=10)
    ax1.legend(loc="upper left", facecolor="#0b132b", edgecolor="#ffd600", labelcolor="white", fontsize=8)

    for b, v in zip(bars1, valores):
        yv = b.get_height()
        offset = 18 if yv >= 0 else -24
        ax1.text(b.get_x() + b.get_width() / 2.0, yv + offset, f"${v:+.1f}", ha="center", va="center", color="white", fontweight="bold", fontsize=8.5)

    posiciones = plan.get("posiciones", [])
    stop_ref_pct = calcular_stop_usd_pct(CAPITAL_INICIAL_PRUEBA / MAX_MONEDAS_SEMANA)
    if posiciones:
        nombres = [p["base"] for p in posiciones]
        pnls = [float(p.get("pnl_pct", 0.0)) for p in posiciones]
        objs = [float(p.get("subida_necesaria_pct", 17.14)) for p in posiciones]
        x = range(len(nombres))

        ax2.bar([i - 0.17 for i in x], objs, width=0.32, color="#334155", edgecolor="#94a3b8", label="Meta Semanal (%)", zorder=2)
        bars_act = ax2.bar([i + 0.17 for i in x], pnls, width=0.32, color=["#00e676" if v >= 0 else "#ff1744" for v in pnls], zorder=3, label="Actual (%)")
        ax2.axhline(0, color="#475569", linewidth=1.0)
        ax2.axhline(TP1_ASEGURAR_PCT, color="#00e676", linestyle="--", linewidth=1.2, label=f"TP1 50% (+{TP1_ASEGURAR_PCT}%)")
        ax2.axhline(stop_ref_pct, color="#ff1744", linestyle=":", linewidth=1.3, label=f"Tope -${MAX_PERDIDA_USD:.0f} ({stop_ref_pct}%)")
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
        ax2.text(0.5, 0.5, "Sin posiciones abiertas\n(Esperando clima BTC estable o señales en Verde)", ha="center", va="center", color="#94a3b8", fontsize=10, transform=ax2.transAxes)
        ax2.tick_params(left=False, labelleft=False, bottom=False, labelbottom=False)

    aud = plan.get("auditoria_ia", {})
    fact_txt = f" | Auditor IA: {aud.get('factibilidad_pct', 80)}% Factible" if aud else ""
    ax2.set_title(f"CARTERA CONSENSO BOTS ({len(posiciones)}/{MAX_MONEDAS_SEMANA}) • TP1 +{TP1_ASEGURAR_PCT}% + TOPE -${MAX_PERDIDA_USD:.0f}", color="#00e676", fontsize=9.6, fontweight="bold", pad=10)
    fig.suptitle(f"ETAPA 4 • GESTOR INTEGRADO CON ECOSISTEMA ({plan['semana_id']}){fact_txt} | {ahora_art().strftime('%d/%m %H:%M ART')}", color="white", fontsize=10.3, fontweight="bold", y=0.98)
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
        "Semana", "Fecha Entrada", "Moneda", "Certificación y Motivo", "Expediente Previo Bots", "Capital ($)",
        "Precio Entrada", "Precio Objetivo", "Subida Esperada (%)",
        "Precio Actual", "Máximo Alcanzado", "Rendimiento (%)",
        "PnL ($)", "Lectura Fibonacci 4H", "Orden Copiloto Trader IA", "Análisis Trader IA (Tesis + 1m/15m)", "Estado"
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
            pos.get("expediente_previo_resumen", "Sin expediente"),
            round(float(pos.get("capital_usd", 0)), 2),
            float(pos.get("precio_entrada", 0)),
            float(pos.get("precio_objetivo", 0)),
            round(float(pos.get("subida_necesaria_pct", 0)), 2),
            float(pos.get("precio_actual", 0)),
            float(pos.get("precio_maximo", 0)),
            round(float(pos.get("pnl_pct", 0)), 2),
            pnl_v,
            pos.get("fib_lectura", "Fib N/D"),
            pos.get("trader_ia_orden", "🟢 MANTENER"),
            pos.get("trader_ia_razon", ""),
            pos.get("estado", "")
        ])
        celda_pnl = ws.cell(row=row_idx, column=13)
        if pnl_v > 0:
            celda_pnl.fill = fill_verde
        elif pnl_v < 0:
            celda_pnl.fill = fill_rojo

    ws_alt = wb.create_sheet(title="2_ALTERNATIVAS_RADAR")
    headers_alt = ["Ranking", "Moneda", "Sello Certificación", "Score Blindaje", "Precio Actual", "Decisión", "Análisis Técnico / OB / Fibonacci"]
    ws_alt.append(headers_alt)
    for col_idx in range(1, len(headers_alt) + 1):
        c = ws_alt.cell(row=1, column=col_idx)
        c.fill = fill_hdr
        c.font = font_hdr
        c.alignment = Alignment(horizontal="center")

    activas_syms = {p["symbol"] for p in plan.get("posiciones", [])}
    for idx, alt in enumerate(plan.get("alternativas_evaluadas", []), start=1):
        estado_alt = "✅ ELEGIDA EN CARTERA" if alt["symbol"] in activas_syms else ("⏳ EN RESERVA (En Verde)" if alt.get("en_zona") else "⚠️ FUERA DE FILTRO VERDE")
        ws_alt.append([
            idx, alt.get("base", ""), alt.get("origen", ""), alt.get("score", 0),
            float(alt.get("precio_entrada", 0)), estado_alt, alt.get("motivo_tecnico", "")
        ])

    ws_aud = wb.create_sheet(title="3_AUDITORIA_IA_24H")
    headers_aud = ["Fecha Auditoría", "Semana", "Semáforo Meta", "Factibilidad (%)", "Diagnóstico IA 24h", "Recomendación Auditor", "Veredicto Final Semana"]
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

    for sheet in (ws, ws_alt, ws_aud, ws2):
        for col in sheet.columns:
            max_len = max(len(str(c.value or "")) for c in col)
            sheet.column_dimensions[col[0].column_letter].width = min(max_len + 4, 48)

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
        f"🔍 <b>GESTOR SEMANAL • BLOQUE 1/3: ALTERNATIVAS CONSENSO BOTS</b>\n"
        f"📅 <code>{ahora_str}</code> | Semana <code>{plan['semana_id']}</code>\n"
        f"<i>Ranking cruzado (Pre-Explosión + Ganadoras + OB &gt;= 1.15x + Fib &lt;= 0.62):</i>\n\n"
    )
    if not alts:
        msg += "⏳ <i>Aún no hay candidatas en verde que superen el filtro de consenso.</i>"
        return msg.strip()

    for idx, a in enumerate(alts, start=1):
        marca = "✅ <b>[ELEGIDA]</b>" if a["symbol"] in activas_syms else ("🟢 <i>[LISTA EN VERDE]</i>" if a.get("en_zona") else "⚪ <i>[FUERA FILTRO]</i>")
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
    aud = plan.get("auditoria_ia", {})

    msg = (
        f"🏆 <b>GESTOR CONSENSO BOTS • BLOQUE 2/3</b>\n"
        f"{evento_titulo}\n"
        f"📅 <code>{ahora_str}</code> | Cuota: <code>${meta:,.0f} USD</code> | Progreso: <b>${real + flot:+.2f} USD ({cump}%)</b>\n"
    )
    if aud:
        msg += (
            f"🧠 <b>Auditor IA 24h:</b> <b>{html.escape(aud.get('semaforo_meta', ''))}</b> ({aud.get('factibilidad_pct', 80)}% factibilidad)\n"
            f"└ <i>{html.escape(aud.get('diagnostico_24h', ''))}</i>\n\n"
        )
    else:
        msg += "\n"

    if not plan["posiciones"]:
        msg += "⏳ <i>Sin posiciones abiertas en este momento (esperando clima BTC / señales en verde).</i>\n"
    else:
        for idx, p in enumerate(plan["posiciones"], start=1):
            uid = int(time.time() * 1000) + random.randint(1, 999)
            u_ia = f"{BASE_URL_NETLIFY}/?coin={p['base']}&price={p['precio_actual']}&v={p['base']}_{uid}"
            u_tr = f"{BINANCE_TRADE_BASE}{p['base']}_USDT"
            exp_res = html.escape(p.get("expediente_previo_resumen", p.get("origen", "")))
            fib_l = html.escape(p.get("fib_lectura", "Fib N/D"))
            orden_tr = html.escape(p.get("trader_ia_orden", "🟢 MANTENER"))
            razon_tr = html.escape(p.get("trader_ia_razon", ""))
            stop_act = float(p.get("stop_actual_pct", calcular_stop_usd_pct(p.get("capital_usd", 875))))
            stop_label = f"🛡️ Trailing BE: <code>+{stop_act:.2f}%</code>" if stop_act > 0 else f"Tope -${MAX_PERDIDA_USD:.0f}: <code>{stop_act:.2f}%</code>"
            tp1_tag = "✅ TP1 50% cobrado" if p.get("tp1_ejecutado") else f"TP1 50%: <code>+{TP1_ASEGURAR_PCT}%</code>"

            msg += (
                f"🟢 <b>{idx}. {p['base']}</b> — Asignado: <code>${p['capital_usd']:,.2f} USD</code>\n"
                f"• <b>Memoria Bots Previos:</b> <i>{exp_res}</i>\n"
                f"• <b>Entrada:</b> <code>{formatear_precio(p['precio_entrada'])}</code> ➔ <b>Actual:</b> <code>{formatear_precio(p['precio_actual'])}</code> (<b>{p['pnl_pct']:+.2f}%</b> | <code>${p['pnl_usd']:+.2f}</code>)\n"
                f"• <b>Cosecha:</b> {tp1_tag} | {stop_label}\n"
                f"• <b>Geometría Fib:</b> <code>{fib_l}</code>\n"
                f"• <b>Copiloto Trader IA (Tesis + 1m/15m):</b> <b>{orden_tr}</b> — <i>{razon_tr}</i>\n"
                f"└ <a href=\"{html.escape(u_ia)}\">📊 Gráfico IA</a> | <a href=\"{html.escape(u_tr)}\">🔶 Tradear Spot</a>\n\n"
            )
    return msg.strip()

def ejecutar_gestor_semanal():
    s = crear_sesion_binance()
    mapa_mkt = obtener_tickers_binance(s)
    if not mapa_mkt:
        print("❌ Sin datos de Binance.")
        return

    # Carga unificada de TODO el trabajo previo de los otros bots
    eco = recopilar_inteligencia_ecosistema()
    plan = cargar_plan_semanal()
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
        max_pnl_pct = ((p_max - p_ent) / p_ent) * 100 if p_ent > 0 else 0.0
        pnl_usd = cap * (pnl_pct / 100.0)
        retroceso_desde_max = ((p_act - p_max) / p_max) * 100 if p_max > 0 else 0.0
        horas_abierta = calcular_horas_abierta(pos.get("fecha_entrada", ""))

        v1m = analizar_velas_tf(s, sym, "1m", 30)
        v15 = analizar_velas_tf(s, sym, "15m", 24)
        v1h = analizar_velas_tf(s, sym, "1h", 36)
        v4h = analizar_velas_tf(s, sym, "4h", 48)
        fib = v4h.get("fib", {}) if v4h.get("fib", {}).get("ok") else v1h.get("fib", {})
        ob = auditar_order_book_semanal(s, sym)
        exp_previo = construir_expediente_moneda(sym, p_act, eco)

        lecturas_tecnicas[sym] = {
            "v1m": v1m, "v15": v15, "v1h": v1h, "fib": fib, "ob": ob,
            "expediente_previo": exp_previo
        }

        stop_base_usd_pct = calcular_stop_usd_pct(cap)
        stop_dinamico_pct = stop_base_usd_pct
        if pos.get("tp1_ejecutado", False):
            stop_dinamico_pct = 2.0
        elif max_pnl_pct >= 8.0:
            stop_dinamico_pct = 4.0
        elif max_pnl_pct >= 3.5:
            stop_dinamico_pct = 1.5
        elif max_pnl_pct >= 2.2:
            stop_dinamico_pct = 0.4

        pos["precio_actual"] = p_act
        pos["precio_maximo"] = p_max
        pos["pnl_pct"] = round(pnl_pct, 2)
        pos["pnl_usd"] = round(pnl_usd, 2)
        pos["stop_actual_pct"] = stop_dinamico_pct
        pos["expediente_previo_resumen"] = exp_previo["resumen_corto"]
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

        palanca_activada, motivo_palanca = evaluar_palanca_emergencia(
            pos, v1m, v15, v1h, fib, ob, pnl_pct, max_pnl_pct, retroceso_desde_max, exp_previo
        )

        motivo_cierre = None
        if pos.get("tp1_ejecutado", False) and retroceso_desde_max <= -TRAILING_DESDE_MAX_PCT:
            motivo_cierre = f"🎯 CIERRE 2ª MITAD (Trailing Stop): tocó máx +{max_pnl_pct:.1f}% y retrocedió {retroceso_desde_max:.1f}%."
        elif not pos.get("tp1_ejecutado", False) and pnl_pct >= 18.0 and retroceso_desde_max <= -2.0:
            motivo_cierre = f"🚀 EXPLOSIÓN CAPTURADA: +{pnl_pct:.1f}% asegurado antes de corrección."
        elif pnl_usd <= -MAX_PERDIDA_USD:
            motivo_cierre = f"🛑 TOPE PREVENTIVO -${MAX_PERDIDA_USD:.0f} USD ({pnl_pct:.2f}% | ${pnl_usd:+.2f}): corta pérdida y libera capital."
        elif stop_dinamico_pct > 0 and pnl_pct <= stop_dinamico_pct:
            motivo_cierre = f"🛡️ TRAILING BREAK-EVEN (+{stop_dinamico_pct:.2f}%): subió hasta +{max_pnl_pct:.1f}% y aseguró ganancia en {pnl_pct:+.2f}%."
        elif not pos.get("tp1_ejecutado", False) and palanca_activada:
            motivo_cierre = motivo_palanca
        elif not pos.get("tp1_ejecutado", False) and horas_abierta >= HORAS_MAX_SIN_ARRANQUE and pnl_pct < 1.5:
            motivo_cierre = f"⏳ ROTACIÓN RÁPIDA ({int(horas_abierta)}h lateral en {pnl_pct:+.1f}%): libera cupo para moneda en verde."

        if motivo_cierre:
            pos["estado"] = "CERRADA"
            pos["fecha_cierre"] = ahora_str
            pos["motivo_cierre"] = motivo_cierre
            plan["ganancia_realizada_usd"] = round(float(plan["ganancia_realizada_usd"]) + float(pos["pnl_usd"]), 2)
            plan["historial_cierres"].append(pos)
            alertas_venta.append(pos)
        else:
            if pnl_usd <= -PREALERTA_PERDIDA_USD and not pos.get("prealerta_palanca_enviada", False):
                pos["prealerta_palanca_enviada"] = True
                prealertas_palanca.append(pos)
            elif pnl_usd > -PREALERTA_PERDIDA_USD * 0.5:
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

    excluidas = {p["symbol"] for p in plan["posiciones"]} | {c["symbol"] for c in plan["historial_cierres"] if c.get("semana_id") == plan["semana_id"]}
    alternativas = evaluar_alternativas_al_horno(s, mapa_mkt, excluidas, eco)
    plan["alternativas_evaluadas"] = alternativas

    btc_ok, msg_btc = verificar_clima_btc(s, mapa_mkt)

    if plan["estado_semana"] == "ACTIVA" and len(plan["posiciones"]) < MAX_MONEDAS_SEMANA:
        if not btc_ok:
            if not plan.get("aviso_btc_enviado", False):
                enviar_telegram_texto(f"🛑 <b>FRENO DE MANO BTC ACTIVADO</b>\n📅 <code>{ahora_str}</code>\n\n⚠️ {html.escape(msg_btc)}")
                plan["aviso_btc_enviado"] = True
        else:
            plan["aviso_btc_enviado"] = False
            cupos = MAX_MONEDAS_SEMANA - len(plan["posiciones"])
            elegidas = [a for a in alternativas if a.get("en_zona")][:cupos]

            if elegidas:
                total_cartera_futura = len(plan["posiciones"]) + len(elegidas)
                cap_base_total = max(500.0, float(plan["capital_total_usd"]) + float(plan["ganancia_realizada_usd"]))
                cap_objetivo_por_moneda = round(cap_base_total / total_cartera_futura, 2)
                meta_restante = max(50.0, float(plan["meta_semanal_usd"]) - float(plan["ganancia_realizada_usd"]))
                meta_por_moneda = meta_restante / total_cartera_futura
                subida_nec_pct = round((meta_por_moneda / cap_objetivo_por_moneda) * 100.0, 2)

                for p_ex in plan["posiciones"]:
                    if not p_ex.get("tp1_ejecutado", False):
                        p_ex["capital_usd"] = cap_objetivo_por_moneda
                        p_ex["pnl_usd"] = round(cap_objetivo_por_moneda * (float(p_ex["pnl_pct"]) / 100.0), 2)
                    p_ex["subida_necesaria_pct"] = subida_nec_pct
                    p_ex["precio_objetivo"] = float(p_ex["precio_entrada"]) * (1.0 + (subida_nec_pct / 100.0))
                    if float(p_ex.get("stop_actual_pct", -1.83)) < 0:
                        p_ex["stop_actual_pct"] = calcular_stop_usd_pct(p_ex["capital_usd"])

                for el in elegidas:
                    p_ent = float(el["precio_entrada"])
                    p_obj = p_ent * (1.0 + (subida_nec_pct / 100.0))
                    exp_el = el.get("expediente_previo", {})
                    nueva_pos = {
                        "semana_id": plan["semana_id"],
                        "symbol": el["symbol"],
                        "base": el["base"],
                        "origen": el["origen"],
                        "motivo_eleccion": el["motivo_tecnico"],
                        "expediente_previo_resumen": exp_el.get("resumen_corto", ""),
                        "fecha_entrada": ahora_str,
                        "capital_usd": cap_objetivo_por_moneda,
                        "precio_entrada": p_ent,
                        "precio_objetivo": p_obj,
                        "subida_necesaria_pct": subida_nec_pct,
                        "precio_actual": p_ent,
                        "precio_maximo": p_ent,
                        "pnl_pct": 0.0,
                        "pnl_usd": 0.0,
                        "stop_actual_pct": calcular_stop_usd_pct(cap_objetivo_por_moneda),
                        "tp1_ejecutado": False,
                        "prealerta_palanca_enviada": False,
                        "estado": "ACTIVA"
                    }
                    plan["posiciones"].append(nueva_pos)
                    nuevas_entradas.append(nueva_pos)

    aud_actual = evaluar_copiloto_trader_y_auditor_ia(s, mapa_mkt, plan, msg_btc, lecturas_tecnicas, eco)

    veredicto_final_txt = ""
    if plan["estado_semana"] == "META_CUMPLIDA":
        veredicto_final_txt = generar_veredicto_final_ia(plan)
        plan["auditoria_ia"]["veredicto_final_semana"] = veredicto_final_txt
        aud_actual["veredicto_final_semana"] = veredicto_final_txt

    for pre in prealertas_palanca:
        enviar_telegram_texto(
            f"⚠️ <b>PRE-ALERTA PALANCA EMERGENCIA (1M/15M) • {pre['base']}</b>\n"
            f"📅 <code>{ahora_str}</code>\n\n"
            f"• <b>Pérdida flotante:</b> <b>${pre['pnl_usd']:+.2f} USD</b> ({pre['pnl_pct']:+.2f}%) — <i>Tope preventivo: -${MAX_PERDIDA_USD:.0f}.00 USD</i>\n"
            f"• <b>Memoria Bots:</b> <code>{html.escape(pre.get('expediente_previo_resumen', ''))}</code>\n"
            f"• <b>Lectura en vivo:</b> <i>{html.escape(pre.get('trader_ia_razon', ''))}</i>"
        )

    for parc in alertas_parciales:
        enviar_telegram_texto(
            f"💰 <b>COSECHA PARCIAL TP1 (+{TP1_ASEGURAR_PCT}%) • {parc['base']}</b>\n"
            f"📅 <code>{ahora_str}</code>\n\n"
            f"• <b>Rendimiento alcanzado:</b> <b>+{parc['pnl_pct']:.2f}%</b> en <code>{formatear_precio(parc['precio_actual'])}</code>\n"
            f"• <b>Ganancia asegurada en caja:</b> <b>+${parc['ganancia_tp1']:.2f} USD</b> (50% vendido)\n"
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
            titulo_ev = f"🔄 <b>ROTACIÓN CONSENSO BOTS / ESCUDO (-${MAX_PERDIDA_USD:.0f} MAX)</b>"
        elif nuevas_entradas:
            titulo_ev = "🆕 <b>NUEVA ENTRADA VALIDADA POR ECOSISTEMA DE BOTS</b>"
        elif alertas_venta or alertas_parciales:
            titulo_ev = f"💰 <b>COSECHA DE GANANCIAS TP1 (+{TP1_ASEGURAR_PCT}%) / CIERRE</b>"
        else:
            titulo_ev = "📡 <b>RADAR CONTINUO • TRADER IA + MEMORIA DE TODOS LOS BOTS</b>"

        caption = construir_bloque_2_cartera(plan, titulo_ev)
        ok2 = enviar_foto_telegram(img, caption)
        time.sleep(1.5)

        ok3 = enviar_excel_telegram(
            f"📎 <b>GESTOR Y RADAR SEMANAL • BLOQUE 3/3: PLANILLA EXCEL</b>\n"
            f"📊 Registro completo en 4 pestañas con Expediente Previo de Bots, TP1 +{TP1_ASEGURAR_PCT}% y Tope -${MAX_PERDIDA_USD:.0f} USD (<code>{EXCEL_SEMANAL_FILE}</code>)."
        )
        if ok1 and ok2 and ok3:
            plan["ultimo_reporte_hora"] = ahora_dt.hour
    else:
        actualizar_excel_semanal(plan)

    for v in alertas_venta:
        msg_v = (
            f"🔔 <b>EJECUCIÓN DE CIERRE • {v['base']}</b>\n"
            f"• Resultado: <b>{v['pnl_pct']:+.2f}%</b> (<b>${v['pnl_usd']:+.2f} USD</b>) | Máx: <code>{formatear_precio(v['precio_maximo'])}</code>\n"
            f"• Motivo: <i>{html.escape(v.get('motivo_cierre', ''))}</i>"
        )
        enviar_telegram_texto(msg_v)

    if plan["estado_semana"] == "META_CUMPLIDA":
        msg_m = (
            f"🏆 <b>¡CUOTA SEMANAL CUMPLIDA EN MODO PRUEBA!</b>\n"
            f"📅 Semana <code>{plan['semana_id']}</code> cerrada el <code>{ahora_str}</code>\n\n"
            f"✅ <b>Ganancia Total Simulada:</b> <code>${plan['ganancia_realizada_usd']:,.2f} USD</code> (Meta: <code>${plan['meta_semanal_usd']:,.2f} USD</code>)\n\n"
            f"{veredicto_final_txt}\n\n"
            f"🛡️ <i>El bot entra en MODO PROTECCIÓN hasta el próximo lunes para asegurar el resultado.</i>"
        )
        enviar_telegram_texto(msg_m)

    guardar_plan_semanal(plan)

if __name__ == "__main__":
    print(f"🧪 INICIANDO GESTOR SEMANAL INTEGRADO CON ECOSISTEMA (TP1 +{TP1_ASEGURAR_PCT}% | MAX -${MAX_PERDIDA_USD:.0f} USD) ({ahora_art().strftime('%H:%M:%S')} ART)...")
    ejecutar_gestor_semanal()
