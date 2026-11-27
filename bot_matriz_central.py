import os, json, html, hashlib, re, requests
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
CEREBRO_FEED_JSON = "cerebro_matriz_central.json"
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
    if raw is None:
        return ""
    s = str(raw).strip().upper().replace("/USDT", "").replace("-USDT", "").replace("USDT", "")
    if not s or len(s) < 2 or len(s) > 14 or not s.isalnum():
        return ""
    if s in {"MONEDA", "NOMBRE", "SYMBOL", "BASE", "TOTAL", "PROMEDIO", "HORA", "ESTADO", "SEMANA"}:
        return ""
    return f"{s}USDT"


def a_float(val, default=None):
    if val is None or isinstance(val, bool):
        return default
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).replace("%", "").replace("+", "").replace("$", "").replace(",", ".").strip()
    m = re.search(r"-?\d+(?:\.\d+)?", s)
    if m:
        try:
            return float(m.group(0))
        except Exception:
            return default
    return default


def es_fecha_valida(val):
    if val is None:
        return False
    if isinstance(val, datetime):
        return True
    s = str(val).strip()
    return bool(re.match(r"^(20\d{2}-\d{2}-\d{2}|\d{2}/\d{2}/20\d{2}|\d{2}-\d{2}-20\d{2})", s))


def limpiar_fecha(val):
    if val is None:
        return ""
    if isinstance(val, datetime):
        return val.strftime("%Y-%m-%d %H:%M")
    s = str(val).strip()
    if es_fecha_valida(s):
        return s[:16]
    return ""


def parsear_fecha_dt(fecha_str):
    if not fecha_str:
        return None
    s = str(fecha_str).strip()
    m = re.search(r"(20\d{2}-\d{2}-\d{2})(?:\s+(\d{2}:\d{2}))?", s)
    if m:
        f_part = m.group(1)
        h_part = m.group(2) or "00:00"
        try:
            return datetime.strptime(f"{f_part} {h_part}", "%Y-%m-%d %H:%M").replace(tzinfo=TZ_ART)
        except Exception:
            pass
    return None


def es_hoy_y_24h(fecha_str, ahora_dt):
    s = str(fecha_str or "").strip()
    hoy_iso = ahora_dt.strftime("%Y-%m-%d")
    ayer_iso = (ahora_dt - timedelta(days=1)).strftime("%Y-%m-%d")
    es_h = hoy_iso in s
    dt = parsear_fecha_dt(s)
    if dt:
        diff_h = (ahora_dt - dt).total_seconds() / 3600.0
        es_24 = es_h or (0 <= diff_h <= 30)
    else:
        es_24 = es_h or (ayer_iso in s)
    return es_h, es_24


def leer_hoja_tabular(ruta_xlsx, nombre_hoja):
    if not os.path.exists(ruta_xlsx):
        return [], []
    wb = openpyxl.load_workbook(ruta_xlsx, data_only=True)
    if nombre_hoja not in wb.sheetnames:
        return [], []
    ws = wb[nombre_hoja]
    filas = [list(r) for r in ws.iter_rows(values_only=True) if any(c is not None and str(c).strip() != "" for c in r)]
    if not filas:
        return [], []

    idx_hdr = 0
    for i in range(min(3, len(filas))):
        fila_up = [str(c or "").upper() for c in filas[i]]
        if any(k in " ".join(fila_up) for k in ("MONEDA", "SYMBOL", "SEMANA", "PARÁMETRO", "PARAMETRO", "SEGMENTO", "BLOQUE", "RANKING", "FECHA AUDITORÍA")):
            idx_hdr = i
            break

    headers = [str(h or f"Col_{j+1}").strip() for j, h in enumerate(filas[idx_hdr])]
    rows = filas[idx_hdr + 1:]
    return headers, rows


def desdoblar_calendario_mensual(ruta_xlsx, nombre_hoja, tipo="E2"):
    if not os.path.exists(ruta_xlsx):
        return []
    wb = openpyxl.load_workbook(ruta_xlsx, data_only=True)
    if nombre_hoja not in wb.sheetnames:
        return []
    ws = wb[nombre_hoja]
    matriz = list(ws.iter_rows(values_only=True))
    registros = []

    for r_idx, row in enumerate(matriz):
        for c_idx, cell in enumerate(row):
            txt = str(cell or "").strip().upper()
            if "NOVIEMBRE" in txt or "OCTUBRE" in txt or "DICIEMBRE" in txt:
                dia_titulo = str(cell).strip()
                sub_r = r_idx + 1
                if sub_r >= len(matriz):
                    continue
                for k in range(sub_r + 1, len(matriz)):
                    fila_k = matriz[k]
                    if c_idx + 4 >= len(fila_k):
                        continue
                    val_0 = str(fila_k[c_idx] or "").upper()
                    if "NOVIEMBRE" in val_0 or "OCTUBRE" in val_0 or "DICIEMBRE" in val_0:
                        break

                    if tipo == "E2":
                        hora = str(fila_k[c_idx] or "").strip()
                        sym = normalizar_symbol(fila_k[c_idx + 1])
                        if not sym:
                            continue
                        sem = str(fila_k[c_idx + 2] or "").strip()
                        ia_pct = a_float(fila_k[c_idx + 3], 0.0)
                        p_ent = a_float(fila_k[c_idx + 4], 0.0)
                        est = str(fila_k[c_idx + 5] or "").strip() if c_idx + 5 < len(fila_k) else ""
                        registros.append({
                            "dia": dia_titulo,
                            "hora": hora,
                            "symbol": sym,
                            "moneda": sym[:-4],
                            "semaforo": sem,
                            "ia_pct": ia_pct,
                            "precio_entrada": p_ent,
                            "estado": est
                        })
                    else:
                        sym = normalizar_symbol(fila_k[c_idx + 1])
                        if not sym:
                            continue
                        p_base = a_float(fila_k[c_idx + 2], 0.0)
                        p_act = a_float(fila_k[c_idx + 3], 0.0)
                        pct_sub = a_float(fila_k[c_idx + 4], 0.0)
                        if pct_sub is not None and abs(pct_sub) < 1.0 and p_base and p_act and abs(((p_act - p_base) / p_base) * 100 - pct_sub * 100) < 1.0:
                            pct_sub = round(pct_sub * 100.0, 2)
                        registros.append({
                            "dia": dia_titulo,
                            "symbol": sym,
                            "moneda": sym[:-4],
                            "precio_base": p_base,
                            "precio_actual": p_act,
                            "subida_pct": pct_sub or 0.0
                        })
    return registros


def construir_matriz_cerebro():
    ahora_dt = ahora_art()
    ahora_str = ahora_dt.strftime("%Y-%m-%d %H:%M ART")
    hoy_iso = ahora_dt.strftime("%Y-%m-%d")

    mapa_mkt = obtener_precios_vivos_binance()
    plan_sem = cargar_json_seguro("plan_semanal.json")
    cerebro = cargar_json_seguro("cerebro_evolutivo.json")
    version_cerebro = cerebro.get("version_ciclo", 1) if isinstance(cerebro, dict) else 1

    # 1. ETAPA 1: CAZADOR TÁCTICO
    _, rows_e1_raw = leer_hoja_tabular("HISTORICO_CAZADOR_TACTICO.xlsx", "HISTORICO_COMPLETO")
    _, rows_e1_ia = leer_hoja_tabular("HISTORICO_CAZADOR_TACTICO.xlsx", "ASISTENTE_IA_TACTICO")
    _, rows_e1_aud = leer_hoja_tabular("HISTORICO_CAZADOR_TACTICO.xlsx", "AUDITORIA_SETUPS")

    ia_e1_map = {}
    for r in rows_e1_ia:
        sym = normalizar_symbol(r[0] if len(r) > 0 else "")
        if sym:
            blind = a_float(r[2], 0.0) if len(r) > 2 else 0.0
            if blind <= 1.0:
                blind = round(blind * 100.0, 1)
            stop_s = a_float(r[8], -3.5) if len(r) > 8 else -3.5
            if abs(stop_s) < 1.0:
                stop_s = round(stop_s * 100.0, 2)
            ia_e1_map[sym] = {
                "blindaje": blind,
                "stop_sugerido": stop_s,
                "accion": str(r[9] or "").strip() if len(r) > 9 else "",
                "dictamen": str(r[10] or "").strip() if len(r) > 10 else ""
            }

    lista_e1 = []
    map_e1_best = {}
    for r in rows_e1_raw:
        sym = normalizar_symbol(r[1] if len(r) > 1 else "")
        if not sym:
            continue
        fecha = limpiar_fecha(r[0])
        etapa_max = str(r[2] or "").strip()
        blindaje = a_float(r[3], 0.0)
        if blindaje <= 1.0:
            blindaje = round(blindaje * 100.0, 1)
        p_ini = a_float(r[4], 0.0)
        p_act_xls = a_float(r[5], 0.0)
        p_vivo = mapa_mkt.get(sym, {}).get("precio", p_act_xls)

        var_act = a_float(r[6], 0.0)
        max_sub = a_float(r[7], 0.0)
        max_dd = a_float(r[8], 0.0)
        if abs(max_sub) < 1.5 and p_ini > 0:
            max_sub = round(max_sub * 100.0, 2)
        if abs(var_act) < 1.5 and p_ini > 0:
            var_act = round(var_act * 100.0, 2)
        if abs(max_dd) < 1.5 and p_ini > 0:
            max_dd = round(max_dd * 100.0, 2)

        est_1d = str(r[11] or "").strip() if len(r) > 11 else ""
        fib = str(r[12] or "").strip() if len(r) > 12 else ""
        rsi_1h = a_float(r[13], 0.0) if len(r) > 13 else 0.0
        res_aud = str(r[14] or "").strip() if len(r) > 14 else ""
        ia_info = ia_e1_map.get(sym, {})

        reg = {
            "symbol": sym,
            "moneda": sym[:-4],
            "fecha": fecha,
            "etapa": etapa_max,
            "blindaje_pct": blindaje,
            "precio_ini": p_ini,
            "precio_vivo": p_vivo,
            "var_act_pct": round(var_act, 2),
            "max_subida_pct": round(max_sub, 2),
            "max_dd_pct": round(max_dd, 2),
            "estructura_1d": est_1d,
            "fibonacci": fib,
            "rsi_1h": rsi_1h,
            "resultado": res_aud,
            "accion_ia": ia_info.get("accion", ""),
            "stop_sugerido": ia_info.get("stop_sugerido", -3.5),
            "dictamen_ia": ia_info.get("dictamen", "")
        }
        lista_e1.append(reg)
        if sym not in map_e1_best or reg["fecha"] >= map_e1_best[sym]["fecha"]:
            map_e1_best[sym] = reg

    lista_e1.sort(key=lambda x: (x["fecha"], x["max_subida_pct"]), reverse=True)

    # 2. ETAPA 2: PRE-EXPLOSIÓN
    _, rows_e2_cruce = leer_hoja_tabular("AUDITORIA_PRE_EXPLOSION.xlsx", "CRUCE_TIEMPOS_GANADORA")
    _, rows_e2_ia = leer_hoja_tabular("AUDITORIA_PRE_EXPLOSION.xlsx", "ASISTENTE_IA_PRE_EXPLOSION")
    _, rows_e2_pat = leer_hoja_tabular("AUDITORIA_PRE_EXPLOSION.xlsx", "ANALISIS_PATRONES")
    cal_e2 = desdoblar_calendario_mensual("AUDITORIA_PRE_EXPLOSION.xlsx", "NOVIEMBRE_2026", tipo="E2")

    ia_e2_map = {}
    for r in rows_e2_ia:
        sym = normalizar_symbol(r[0] if len(r) > 0 else "")
        if sym:
            blind = a_float(r[3], 0.0) if len(r) > 3 else 0.0
            if blind <= 1.0:
                blind = round(blind * 100.0, 1)
            ia_e2_map[sym] = {
                "cert": str(r[2] or "").strip() if len(r) > 2 else "",
                "blindaje": blind,
                "accion": str(r[9] or "").strip() if len(r) > 9 else "",
                "dictamen": str(r[10] or "").strip() if len(r) > 10 else ""
            }

    lista_e2 = []
    map_e2_best = {}
    for r in rows_e2_cruce:
        sym = normalizar_symbol(r[0] if len(r) > 0 else "")
        if not sym:
            continue
        fecha_ap = limpiar_fecha(r[1])
        sem_ini = str(r[2] or "").strip()
        sem_max = str(r[3] or "").strip()
        veces = int(a_float(r[5], 1))
        ia_max = a_float(r[6], 0.0)
        fib = str(r[7] or "").strip()
        ba = str(r[8] or "").strip()
        p_ent = a_float(r[9], 0.0)
        p_pico = a_float(r[10], 0.0)
        sub_pico = a_float(r[11], 0.0)
        estado = str(r[12] or "").strip()
        fecha_gan = limpiar_fecha(r[13])
        p_vivo = mapa_mkt.get(sym, {}).get("precio", a_float(r[14], 0.0))
        var_real = a_float(r[15], 0.0)
        tiempo_gan = str(r[16] or "").strip()
        ia_info = ia_e2_map.get(sym, {})

        reg = {
            "symbol": sym,
            "moneda": sym[:-4],
            "fecha": fecha_ap,
            "semaforo_ini": sem_ini,
            "semaforo_max": sem_max,
            "veces_vista": veces,
            "ia_max_pct": ia_max,
            "fibonacci": fib,
            "bids_asks": ba,
            "precio_ini": p_ent,
            "precio_pico": p_pico,
            "precio_vivo": p_vivo,
            "subida_pico_pct": round(sub_pico, 2),
            "var_real_pct": round(var_real, 2),
            "estado": estado,
            "fecha_ganadora": fecha_gan,
            "tiempo_maduracion": tiempo_gan,
            "accion_ia": ia_info.get("accion", ""),
            "dictamen_ia": ia_info.get("dictamen", "")
        }
        lista_e2.append(reg)
        map_e2_best[sym] = reg

    for c_it in cal_e2:
        sym = c_it["symbol"]
        if sym not in map_e2_best:
            p_vivo = mapa_mkt.get(sym, {}).get("precio", c_it["precio_entrada"])
            p_ent = c_it["precio_entrada"] or p_vivo
            var_r = ((p_vivo - p_ent) / p_ent * 100.0) if p_ent > 0 else 0.0
            ia_info = ia_e2_map.get(sym, {})
            reg = {
                "symbol": sym,
                "moneda": sym[:-4],
                "fecha": c_it["dia"],
                "semaforo_ini": c_it["semaforo"],
                "semaforo_max": c_it["semaforo"],
                "veces_vista": 1,
                "ia_max_pct": c_it["ia_pct"],
                "fibonacci": "-",
                "bids_asks": "-",
                "precio_ini": p_ent,
                "precio_pico": max(p_ent, p_vivo),
                "precio_vivo": p_vivo,
                "subida_pico_pct": round(max(var_r, 0.0), 2),
                "var_real_pct": round(var_r, 2),
                "estado": c_it["estado"],
                "fecha_ganadora": "",
                "tiempo_maduracion": "-",
                "accion_ia": ia_info.get("accion", ""),
                "dictamen_ia": ia_info.get("dictamen", "")
            }
            lista_e2.append(reg)
            map_e2_best[sym] = reg

    lista_e2.sort(key=lambda x: (x["fecha"], x["subida_pico_pct"]), reverse=True)

    # 3. ETAPA 3: MONEDAS GANADORAS
    _, rows_e3_det = leer_hoja_tabular("AUDITORIA_VERDE_GANADORAS.xlsx", "DETALLE_OPERACIONES")
    _, rows_e3_ia = leer_hoja_tabular("AUDITORIA_VERDE_GANADORAS.xlsx", "ASISTENTE_IA_GANADORAS")
    _, rows_e3_par = leer_hoja_tabular("AUDITORIA_VERDE_GANADORAS.xlsx", "PARAMETROS_RADAR")
    cal_e3 = desdoblar_calendario_mensual("AUDITORIA_VERDE_GANADORAS.xlsx", "NOVIEMBRE_2026", tipo="E3")

    ia_e3_map = {}
    for r in rows_e3_ia:
        sym = normalizar_symbol(r[0] if len(r) > 0 else "")
        if sym:
            veces_mes = int(a_float(r[1], 1))
            max_mes = a_float(r[3], 0.0)
            if abs(max_mes) < 1.5:
                max_mes = round(max_mes * 100.0, 2)
            ia_e3_map[sym] = {
                "veces_mes": veces_mes,
                "max_mes_pct": max_mes,
                "estado_tactico": str(r[8] or "").strip() if len(r) > 8 else "",
                "accion": str(r[9] or "").strip() if len(r) > 9 else "",
                "dictamen": str(r[10] or "").strip() if len(r) > 10 else ""
            }

    lista_e3 = []
    map_e3_best = {}
    for r in rows_e3_det:
        sym = normalizar_symbol(r[0] if len(r) > 0 else "")
        if not sym:
            continue
        cat = str(r[1] or "").strip()
        f_verde = limpiar_fecha(r[2])
        p_verde = a_float(r[3], 0.0)
        estado = str(r[4] or "").strip()
        f_gan = limpiar_fecha(r[5])
        p_gan = a_float(r[6], 0.0)
        sub_desde_verde = a_float(r[7], 0.0)
        sub_dia_gan = a_float(r[8], 0.0)
        dias_demora = a_float(r[9], 0.0)
        p_vivo = mapa_mkt.get(sym, {}).get("precio", p_gan)
        ia_info = ia_e3_map.get(sym, {})

        reg = {
            "symbol": sym,
            "moneda": sym[:-4],
            "categoria": cat,
            "fecha": f_verde,
            "precio_ini": p_verde,
            "precio_ganadora": p_gan,
            "precio_vivo": p_vivo,
            "estado": estado,
            "fecha_ganadora": f_gan,
            "subida_desde_verde_pct": round(sub_desde_verde, 2),
            "subida_dia_gan_pct": round(sub_dia_gan, 2),
            "dias_demora": dias_demora,
            "veces_mes": ia_info.get("veces_mes", 1),
            "accion_ia": ia_info.get("accion", ""),
            "dictamen_ia": ia_info.get("dictamen", "")
        }
        lista_e3.append(reg)
        map_e3_best[sym] = reg

    for c_it in cal_e3:
        sym = c_it["symbol"]
        if sym not in map_e3_best:
            p_vivo = mapa_mkt.get(sym, {}).get("precio", c_it["precio_actual"])
            ia_info = ia_e3_map.get(sym, {})
            reg = {
                "symbol": sym,
                "moneda": sym[:-4],
                "categoria": "🏆 TOP GANADORA 24H",
                "fecha": c_it["dia"],
                "precio_ini": c_it["precio_base"],
                "precio_ganadora": c_it["precio_actual"],
                "precio_vivo": p_vivo,
                "estado": ia_info.get("estado_tactico") or "GANADORA_HIST",
                "fecha_ganadora": c_it["dia"],
                "subida_desde_verde_pct": c_it["subida_pct"],
                "subida_dia_gan_pct": c_it["subida_pct"],
                "dias_demora": 0,
                "veces_mes": ia_info.get("veces_mes", 1),
                "accion_ia": ia_info.get("accion", ""),
                "dictamen_ia": ia_info.get("dictamen", "")
            }
            lista_e3.append(reg)
            map_e3_best[sym] = reg

    lista_e3.sort(key=lambda x: (x["fecha"], x["subida_dia_gan_pct"]), reverse=True)

    # 4. GESTOR 3 TRADERS, MESA, AUTOPSIA Y CEREBRO
    h_tr, rows_tr = leer_hoja_tabular("AUDITORIA_SEMANAL_PRUEBA.xlsx", "1_CARTERA_3_TRADERS")
    h_mesa, rows_mesa = leer_hoja_tabular("AUDITORIA_SEMANAL_PRUEBA.xlsx", "2_MESA_6_ASISTENTES")
    h_aud24, rows_aud24 = leer_hoja_tabular("AUDITORIA_SEMANAL_PRUEBA.xlsx", "3_AUDITORIA_IA_24H")
    h_aut, rows_aut = leer_hoja_tabular("AUDITORIA_SEMANAL_PRUEBA.xlsx", "5_AUTOPSIA_POST_CIERRE")
    h_cer, rows_cer = leer_hoja_tabular("AUDITORIA_SEMANAL_PRUEBA.xlsx", "6_EVOLUCION_CEREBRO_IA")

    posiciones = plan_sem.get("posiciones", []) if isinstance(plan_sem, dict) else []
    cierres = plan_sem.get("historial_cierres", []) if isinstance(plan_sem, dict) else []
    alts_eval = plan_sem.get("alternativas_evaluadas", []) if isinstance(plan_sem, dict) else []
    pos_map = {p["symbol"]: p for p in posiciones if p.get("symbol")}
    alts_map = {a["symbol"]: a for a in alts_eval if a.get("symbol")}

    # 5. CONSENSO ACTIVO DE LOS 3 ASISTENTES IA -> ORDEN PARA LOS TRADERS
    todos_syms = sorted(set(map_e1_best.keys()) | set(map_e2_best.keys()) | set(map_e3_best.keys()) | set(pos_map.keys()))
    filas_matriz = []
    ordenes_activas_cerebro = []

    for sym in todos_syms:
        mkt = mapa_mkt.get(sym, {})
        p_vivo = float(mkt.get("precio", 0.0))
        chg_24h = round(float(mkt.get("cambio_24h", 0.0)), 2)
        vol_24m = round(float(mkt.get("vol_24h", 0.0)) / 1e6, 2)

        d1 = map_e1_best.get(sym)
        d2 = map_e2_best.get(sym)
        d3 = map_e3_best.get(sym)
        conf = sum([1 if d1 else 0, 1 if d2 else 0, 1 if d3 else 0])

        # Votos positivos de cada Asistente IA de Etapa
        voto_ia_1 = bool(d1 and ("APTA" in d1.get("accion_ia", "").upper() or d1.get("blindaje_pct", 0) >= 85))
        voto_ia_2 = bool(d2 and ("COMPRA" in d2.get("accion_ia", "").upper() or d2.get("semaforo_max", "").endswith("ROJO")))
        voto_ia_3 = bool(d3 and ("BONUS" in d3.get("accion_ia", "").upper() or d3.get("veces_mes", 0) >= 3))
        votos_ia_total = sum([voto_ia_1, voto_ia_2, voto_ia_3])

        fechas_validas = [x["fecha"] for x in (d1, d2, d3) if x and es_fecha_valida(x.get("fecha"))]
        primera_fecha = min(fechas_validas) if fechas_validas else (d3["fecha"] if d3 else (d2["fecha"] if d2 else ""))

        col_e1 = f"✅ {d1['etapa']} (Máx {d1['max_subida_pct']:+.1f}%)" if d1 else "—"
        col_e2 = f"⚡ {d2['semaforo_max']} (Pico {d2['subida_pico_pct']:+.1f}%)" if d2 else "—"
        col_e3 = f"🟢 {d3['estado']} (Verde {d3['subida_desde_verde_pct']:+.1f}% | Día +{d3['subida_dia_gan_pct']:.1f}% | {d3['veces_mes']}x)" if d3 else "—"

        alt = alts_map.get(sym)
        stop_sug = d1.get("stop_sugerido", -3.5) if d1 else -3.5

        if sym in pos_map:
            po = pos_map[sym]
            tr_nom = po.get("trader_asignado") or po.get("trader") or "TRADER_3"
            mesa_txt = "APROBADA (CARTERA)"
            estado_tr = f"🟢 {tr_nom} ({float(po.get('pnl_pct', 0)):+.2f}%)"
            orden_cerebro = f"CUSTODIAR_EN_{tr_nom}"
        elif votos_ia_total >= 2 and chg_24h < 25.0:
            mesa_txt = f"CONSENSO IA {votos_ia_total}/3"
            estado_tr = "🚀 LISTA PARA TRADER LIBRE"
            orden_cerebro = f"EJECUTAR_TRADER (Stop {stop_sug}%)"
            ordenes_activas_cerebro.append({
                "symbol": sym,
                "moneda": sym[:-4],
                "votos_ia": votos_ia_total,
                "confluencia_etapas": conf,
                "precio_vivo": p_vivo,
                "chg_24h": chg_24h,
                "vol_24m": vol_24m,
                "stop_sugerido_pct": stop_sug,
                "orden": orden_cerebro
            })
        elif alt and alt.get("consenso_3_de_3"):
            mesa_txt = f"{alt.get('asistentes_aprobados', 0)}/6"
            estado_tr = f"🟡 COLA ({alt.get('trader_propuesto', 'LIBRE')})"
            orden_cerebro = "EJECUTAR_TRADER (MESA)"
        else:
            mesa_txt = f"IA {votos_ia_total}/3 | M {alt.get('asistentes_aprobados', 0)}/6" if alt else f"IA {votos_ia_total}/3"
            estado_tr = "OBSERVACIÓN"
            orden_cerebro = "ESPERAR_CONFIRMACION"

        notas = []
        if sym in pos_map:
            po = pos_map[sym]
            notas.append(f"[CARTERA] {po.get('operativa_trader') or po.get('jefe_veredicto_entrada') or 'Posición activa protegida'}")
        if d1 and d1.get("dictamen_ia"):
            notas.append(f"[E1] {d1['dictamen_ia']}")
        if d2 and d2.get("dictamen_ia"):
            notas.append(f"[E2] {d2['dictamen_ia']}")
        if d3 and d3.get("dictamen_ia"):
            notas.append(f"[E3] {d3['dictamen_ia']}")
        if not notas:
            notas.append(f"Confluencia {conf}/3 • Var 24h: {chg_24h:+.2f}% • Vol: ${vol_24m:.2f}M")

        filas_matriz.append({
            "moneda": sym[:-4],
            "primera_fecha": primera_fecha,
            "precio_vivo": p_vivo,
            "chg_24h": chg_24h,
            "vol_24m": vol_24m,
            "confluencia": conf,
            "orden_cerebro": orden_cerebro,
            "col_e1": col_e1,
            "col_e2": col_e2,
            "col_e3": col_e3,
            "mesa_txt": mesa_txt,
            "estado_tr": estado_tr,
            "notas_ia": " | ".join(notas)[:260]
        })

    filas_matriz.sort(key=lambda x: (
        1 if "CUSTODIAR" in x["orden_cerebro"] else (2 if "EJECUTAR" in x["orden_cerebro"] else 0),
        x["confluencia"],
        x["chg_24h"]
    ), reverse=True)

    # 6. MÉTRICAS REALES PARA EL TABLERO EJECUTIVO + AUTOCRÍTICA DE FLUJO
    def _stats_etapa(lista, campo_pct):
        c_hoy, c_24h = 0, 0
        vals = []
        for it in lista:
            h_f, h24_f = es_hoy_y_24h(it["fecha"], ahora_dt)
            if h_f:
                c_hoy += 1
            if h24_f:
                c_24h += 1
            v = it.get(campo_pct, 0.0)
            if v is not None:
                vals.append(float(v))
        prom = round(sum(vals) / max(len(vals), 1), 2)
        return c_hoy, c_24h, prom

    e1_hoy, e1_24h, e1_prom = _stats_etapa(lista_e1, "max_subida_pct")
    e2_hoy, e2_24h, e2_prom = _stats_etapa(lista_e2, "subida_pico_pct")
    e3_hoy, e3_24h, e3_prom = _stats_etapa(lista_e3, "subida_dia_gan_pct")

    e4_hoy, e4_24h = 0, 0
    for op in list(cierres) + list(posiciones):
        h_f, h24_f = es_hoy_y_24h(op.get("fecha_cierre") or op.get("fecha_entrada"), ahora_dt)
        if h_f:
            e4_hoy += 1
        if h24_f:
            e4_24h += 1

    traders_libres = max(0, 3 - len(posiciones))
    pnl_sem_neto = round(float(plan_sem.get("ganancia_realizada_usd", 0.0)) + sum(float(p.get("pnl_usd", 0.0)) for p in posiciones), 2)

    alerta_flujo = (
        f"⚠️ {traders_libres}/3 Traders libres con {len(ordenes_activas_cerebro)} candidatas aprobadas por Consenso IA."
        if traders_libres > 0 and ordenes_activas_cerebro
        else f"Activas: {len(posiciones)}/3 | Órdenes listas en Cerebro: {len(ordenes_activas_cerebro)}"
    )

    resumen_bots = [
        {
            "emoji": "🎯",
            "etapa": "Etapa 1 • Cazador Táctico",
            "fuente": "HISTORICO_CAZADOR_TACTICO.xlsx",
            "hoy": e1_hoy,
            "h24": e1_24h,
            "total": len(lista_e1),
            "metrica": f"Máx Rebote Prom: {e1_prom:+.2f}% | Stop Óptimo: -3.5%",
            "diag_ia": f"Base auditada de {len(lista_e1)} señales tácticas ({e1_hoy} hoy)."
        },
        {
            "emoji": "⚡",
            "etapa": "Etapa 2 • Pre-Explosión",
            "fuente": "AUDITORIA_PRE_EXPLOSION.xlsx",
            "hoy": e2_hoy,
            "h24": e2_24h,
            "total": len(lista_e2),
            "metrica": f"Pico Máx Prom: {e2_prom:+.2f}% | Maduración Típica: 2d 12h",
            "diag_ia": f"{len(lista_e2)} monedas monitoreadas en acumulación previa."
        },
        {
            "emoji": "🟢",
            "etapa": "Etapa 3 • Monedas Ganadoras",
            "fuente": "AUDITORIA_VERDE_GANADORAS.xlsx",
            "hoy": e3_hoy,
            "h24": e3_24h,
            "total": len(lista_e3),
            "metrica": f"Subida Día Ganadora Prom: {e3_prom:+.2f}%",
            "diag_ia": f"{len(lista_e3)} registros históricos de ganadoras y reincidentes."
        },
        {
            "emoji": "🏆",
            "etapa": f"Etapa 4 • Gestor 3 Traders (Cerebro v{version_cerebro})",
            "fuente": "AUDITORIA_SEMANAL_PRUEBA.xlsx",
            "hoy": e4_hoy,
            "h24": e4_24h,
            "total": len(rows_tr),
            "metrica": f"Balance Semanal: ${pnl_sem_neto:+.2f} USD | Activas: {len(posiciones)}/3",
            "diag_ia": alerta_flujo
        }
    ]

    # Guardar feed JSON para que el Gestor de 3 Traders lo consuma directo
    guardar_json_seguro(CEREBRO_FEED_JSON, {
        "actualizado": ahora_str,
        "version_cerebro": version_cerebro,
        "traders_libres": traders_libres,
        "ordenes_ejecutar": ordenes_activas_cerebro[:6],
        "diagnostico_flujo": alerta_flujo
    })

    # 7. GENERAR EXCEL MAESTRO ORDENADO (10 PESTAÑAS)
    wb = openpyxl.Workbook()
    fill_hdr = PatternFill(start_color="0B132B", end_color="0B132B", fill_type="solid")
    fill_sub = PatternFill(start_color="1E293B", end_color="1E293B", fill_type="solid")
    font_hdr = Font(color="FFFFFF", bold=True)
    fill_verde = PatternFill(start_color="D1FAE5", end_color="D1FAE5", fill_type="solid")
    fill_amarillo = PatternFill(start_color="FEF3C7", end_color="FEF3C7", fill_type="solid")
    fill_azul = PatternFill(start_color="DBEAFE", end_color="DBEAFE", fill_type="solid")
    fill_zebra = PatternFill(start_color="F8FAFC", end_color="F8FAFC", fill_type="solid")

    def _preparar_hoja(ws, cols, tab_color_hex):
        ws.sheet_properties.tabColor = tab_color_hex
        ws.append(cols)
        ws.freeze_panes = "A2"
        for idx in range(1, len(cols) + 1):
            c = ws.cell(row=1, column=idx)
            c.fill = fill_hdr
            c.font = font_hdr
            c.alignment = Alignment(horizontal="center", vertical="center")
        ws.row_dimensions[1].height = 24

    ws0 = wb.active
    ws0.title = "0_TABLERO_EJECUTIVO"
    _preparar_hoja(ws0, [
        "Fecha", "Etapa del Embudo", "Archivo Fuente", "Señales Hoy",
        "Señales 24h", "Total Histórico", "Métrica Clave Calibrada", "Diagnóstico IA y Flujo"
    ], "0B132B")
    for rb in resumen_bots:
        ws0.append([
            hoy_iso, rb["etapa"], rb["fuente"], rb["hoy"],
            rb["h24"], rb["total"], rb["metrica"], rb["diag_ia"]
        ])

    ws1 = wb.create_sheet(title="1_MATRIZ_MAESTRA_CRUZADA")
    _preparar_hoja(ws1, [
        "Moneda", "Primera Detección", "Precio Vivo ($)", "Var 24h (%)", "Vol 24h ($M)",
        "Confluencia", "Orden Cerebro -> Traders", "Etapa 1: Cazador Táctico",
        "Etapa 2: Pre-Explosión", "Etapa 3: Monedas Ganadoras", "Consenso IA / Mesa",
        "Estado 3 Traders", "Síntesis IA Combinada", "Actualizado"
    ], "1D4ED8")
    for r_idx, fm in enumerate(filas_matriz, start=2):
        ws1.append([
            fm["moneda"], fm["primera_fecha"], fm["precio_vivo"], fm["chg_24h"], fm["vol_24m"],
            f"{fm['confluencia']}/3 Etapas", fm["orden_cerebro"], fm["col_e1"], fm["col_e2"],
            fm["col_e3"], fm["mesa_txt"], fm["estado_tr"], fm["notas_ia"], ahora_str
        ])
        cel_c = ws1.cell(row=r_idx, column=6)
        cel_o = ws1.cell(row=r_idx, column=7)
        if fm["confluencia"] >= 2:
            cel_c.fill = fill_verde
        elif fm["confluencia"] == 1:
            cel_c.fill = fill_amarillo
        if "EJECUTAR" in fm["orden_cerebro"]:
            cel_o.fill = fill_azul
        elif "CUSTODIAR" in fm["orden_cerebro"]:
            cel_o.fill = fill_verde

    ws2 = wb.create_sheet(title="2_HIST_E1_CAZADOR_291")
    _preparar_hoja(ws2, [
        "Fecha Detección", "Moneda", "Etapa Máxima", "Blindaje IA (%)",
        "Precio Inicio ($)", "Precio Vivo ($)", "Var Actual (%)", "Máx Subida (%)",
        "Máx Caída DD (%)", "Estructura 1D", "Fibonacci", "RSI 1H",
        "Resultado Auditado", "Dictamen Asistente IA"
    ], "D97706")
    for idx_r, it in enumerate(lista_e1, start=2):
        ws2.append([
            it["fecha"], it["moneda"], it["etapa"], it["blindaje_pct"],
            it["precio_ini"], it["precio_vivo"], it["var_act_pct"], it["max_subida_pct"],
            it["max_dd_pct"], it["estructura_1d"], it["fibonacci"], it["rsi_1h"],
            it["resultado"], it["dictamen_ia"]
        ])
        if idx_r % 2 == 0:
            for c_i in range(1, 15):
                ws2.cell(row=idx_r, column=c_i).fill = fill_zebra

    ws3 = wb.create_sheet(title="3_HIST_E2_PRE_EXPLOSION")
    _preparar_hoja(ws3, [
        "1ª Aparición", "Moneda", "Semáforo Inicial", "Semáforo Máx", "Veces Vista",
        "IA Máx (%)", "Fibonacci", "Bids/Asks", "Precio Entrada ($)", "Precio Pico ($)",
        "Precio Vivo ($)", "Máx Subida Pico (%)", "Var Real Actual (%)",
        "Estado", "Fecha Ganadora", "Tiempo Maduración", "Dictamen Asistente IA"
    ], "7C3AED")
    for idx_r, it in enumerate(lista_e2, start=2):
        ws3.append([
            it["fecha"], it["moneda"], it["semaforo_ini"], it["semaforo_max"], it["veces_vista"],
            it["ia_max_pct"], it["fibonacci"], it["bids_asks"], it["precio_ini"], it["precio_pico"],
            it["precio_vivo"], it["subida_pico_pct"], it["var_real_pct"],
            it["estado"], it["fecha_ganadora"], it["tiempo_maduracion"], it["dictamen_ia"]
        ])
        if idx_r % 2 == 0:
            for c_i in range(1, 18):
                ws3.cell(row=idx_r, column=c_i).fill = fill_zebra

    ws4 = wb.create_sheet(title="4_HIST_E3_GANADORAS")
    _preparar_hoja(ws4, [
        "Fecha Verde", "Moneda", "Categoría", "Veces en el Mes", "Precio Verde ($)",
        "Precio Ganadora ($)", "Precio Vivo ($)", "Subida desde Verde (%)",
        "Subida Día Ganadora (%)", "Días Demora", "Estado", "Fecha Ganadora",
        "Dictamen Asistente IA"
    ], "059669")
    for idx_r, it in enumerate(lista_e3, start=2):
        ws4.append([
            it["fecha"], it["moneda"], it["categoria"], it["veces_mes"], it["precio_ini"],
            it["precio_ganadora"], it["precio_vivo"], it["subida_desde_verde_pct"],
            it["subida_dia_gan_pct"], it["dias_demora"], it["estado"], it["fecha_ganadora"],
            it["dictamen_ia"]
        ])
        if idx_r % 2 == 0:
            for c_i in range(1, 14):
                ws4.cell(row=idx_r, column=c_i).fill = fill_zebra

    ws5 = wb.create_sheet(title="5_AUDITORIA_ESTADISTICA")
    _preparar_hoja(ws5, [
        "Etapa", "Segmento / Parámetro", "Columna 1", "Columna 2", "Columna 3", "Columna 4", "Columna 5"
    ], "0284C7")
    for r in rows_e1_aud:
        ws5.append(["Etapa 1 • Táctico"] + list(r[:6]))
    ws5.append(["---", "---", "---", "---", "---", "---", "---"])
    for r in rows_e2_pat:
        if any(r):
            ws5.append(["Etapa 2 • Pre-Explosión"] + list(r[:6]))
    ws5.append(["---", "---", "---", "---", "---", "---", "---"])
    for r in rows_e3_par:
        if any(r):
            ws5.append(["Etapa 3 • Ganadoras"] + list(r[:6]))

    for titulo_e4, hdr_e4, rws_e4, color_e4 in [
        ("6_CARTERA_3_TRADERS", h_tr, rows_tr, "334155"),
        ("7_MESA_6_ASISTENTES", h_mesa, rows_mesa, "475569"),
        ("8_AUTOPSIA_Y_CEREBRO_IA", h_aut, rows_aut, "64748B"),
        ("9_BITACORA_AUDITORIA_24H", h_aud24, rows_aud24, "94A3B8")
    ]:
        ws_e4 = wb.create_sheet(title=titulo_e4)
        if hdr_e4:
            _preparar_hoja(ws_e4, hdr_e4, color_e4)
            for row_d in rws_e4:
                ws_e4.append(row_d)
        if titulo_e4 == "8_AUTOPSIA_Y_CEREBRO_IA" and h_cer:
            ws_e4.append([])
            ws_e4.append(["=== PARÁMETROS Y PATRONES • CEREBRO EVOLUTIVO ==="])
            ws_e4.append(h_cer)
            for c_cell in ws_e4[ws_e4.max_row]:
                c_cell.fill = fill_sub
                c_cell.font = font_hdr
            for row_c in rows_cer:
                ws_e4.append(row_c)

    for sheet in wb.worksheets:
        sheet.auto_filter.ref = sheet.dimensions
        for col in sheet.columns:
            max_len = max(len(str(c.value or "")) for c in col)
            sheet.column_dimensions[col[0].column_letter].width = min(max_len + 4, 48)

    wb.save(EXCEL_MATRIZ_CENTRAL_FILE)
    return ahora_str, hoy_iso, resumen_bots, filas_matriz, ordenes_activas_cerebro, version_cerebro, plan_sem, len(wb.sheetnames)


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


def actualizar_tema_matriz_telegram(ahora_str, hoy_iso, resumen_bots, filas_matriz, ordenes_cerebro, version_cerebro, plan_sem, total_pestanas):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return

    cfg = cargar_json_seguro(MATRIZ_CONFIG_FILE)
    topic_id = asegurar_topic_matriz(cfg)

    sem_id = plan_sem.get("semana_id", "2026") if isinstance(plan_sem, dict) else "2026"
    total_hoy = sum(rb["hoy"] for rb in resumen_bots)
    total_24h = sum(rb["h24"] for rb in resumen_bots)
    en_cartera = [f for f in filas_matriz if "CUSTODIAR" in f["orden_cerebro"]]

    msg = (
        f"🧠 <b>MATRIZ CENTRAL • CEREBRO DE CONSENSO IA</b>\n"
        f"🗓️ <b>Fecha:</b> <code>{hoy_iso}</code> (Semana <code>{sem_id}</code>)\n"
        f"📈 <b>Actividad:</b> <b>{total_hoy} hoy</b> | <b>{total_24h} últimas 24h</b>\n"
        f"📁 <b>Excel Maestro:</b> <code>{EXCEL_MATRIZ_CENTRAL_FILE}</code> (<b>{total_pestanas} pestañas</b>)\n\n"
    )

    for rb in resumen_bots:
        msg += (
            f"{rb['emoji']} <b>{html.escape(rb['etapa'])}:</b> <b>{rb['hoy']} hoy</b> (<code>{rb['h24']} en 24h</code>)\n"
            f"• Total: <b>{rb['total']}</b> | {html.escape(rb['metrica'])}\n"
            f"• <i>{html.escape(rb['diag_ia'][:115])}</i>\n\n"
        )

    msg += "🚀 <b>ÓRDENES DE CONSENSO IA -> TRADERS LIBRES</b>\n"
    if ordenes_cerebro:
        for oc in ordenes_cerebro[:6]:
            msg += (
                f"• <b>{oc['moneda']}</b> (IA <code>{oc['votos_ia']}/3</code> | 24h: <b>{oc['chg_24h']:+.1f}%</b>) ➔ "
                f"<b>{html.escape(oc['orden'])}</b>\n"
            )
    else:
        msg += "• <i>Sin nuevas órdenes 2/3 IA en este corte.</i>\n"

    if en_cartera:
        msg += "\n🖥️ <b>EN CUSTODIA DE TRADERS</b>\n"
        for ec in en_cartera:
            msg += f"• <b>{ec['moneda']}</b>: {html.escape(ec['estado_tr'])}\n"

    msg += (
        f"\n🧬 <i>Cerebro v{version_cerebro} • Universo único: {len(filas_matriz)} monedas</i>\n"
        f"<i>Sincronizado • {ahora_str}</i>"
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
        json.dumps([resumen_bots, [(f["moneda"], f["orden_cerebro"], f["estado_tr"]) for f in filas_matriz]], sort_keys=True).encode()
    ).hexdigest()

    hora_actual = ahora_art().hour
    es_manual = (os.getenv("GITHUB_EVENT_NAME") == "workflow_dispatch")
    if cfg.get("ultimo_hash_excel") != hash_datos or cfg.get("ultima_hora_excel") != hora_actual or es_manual:
        doc_data = {
            "chat_id": TELEGRAM_CHAT_ID,
            "caption": (
                f"📎 <b>{EXCEL_MATRIZ_CENTRAL_FILE}</b> ({total_pestanas} Pestañas • Cerebro Central)\n"
                f"🔄 Sincronizado: <code>{ahora_str}</code> | Órdenes IA listas: <b>{len(ordenes_cerebro)}</b>"
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
    print(f"🧠 ACTUALIZANDO CEREBRO CENTRAL ({ahora_art().strftime('%H:%M:%S')} ART)...")
    ahora_s, hoy_s, res_bots, f_mat, ord_cer, v_cer, pl, tot_p = construir_matriz_cerebro()
    actualizar_tema_matriz_telegram(ahora_s, hoy_s, res_bots, f_mat, ord_cer, v_cer, pl, tot_p)
