import os, re, json, time, random, html, requests
from datetime import datetime, timezone, timedelta
import matplotlib.pyplot as plt
from google import genai

TZ_ART = timezone(timedelta(hours=-3))
TELEGRAM_BOT_TOKEN = (os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("TELEGRAM_TOKEN") or "").strip()
TELEGRAM_CHAT_ID = (os.getenv("TELEGRAM_CHAT_ID") or os.getenv("CHAT_ID") or "").strip()
TELEGRAM_TOPIC_ID = (os.getenv("TOPIC_ID_TACTICO") or os.getenv("TOPIC_ID_CENTRAL") or "4").strip()
GEMINI_API_KEY = (os.getenv("GEMINI_API_KEY") or "").strip()
BASE_URL_NETLIFY = "https://gregarious-frangollo-0346c5.netlify.app"
HISTORIAL_FILE = "historial_perlas.json"
DIAS_SEGUIMIENTO_VERDE = 6

def ahora_art():
    return datetime.now(TZ_ART)

def cargar_historial():
    hoy = ahora_art().strftime('%Y-%m-%d')
    base = {
        "fecha": hoy,
        "mencionadas": {},
        "resumen_dia": [],
        "resumen_enviado_hoy": False,
        "seguimiento_verde": {},
        "graduadas_pre_explosion": {}
    }
    if os.path.exists(HISTORIAL_FILE):
        try:
            with open(HISTORIAL_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                for clave in ["seguimiento_verde", "graduadas_pre_explosion"]:
                    dic_limpio = {}
                    for sym, info in data.get(clave, {}).items():
                        try:
                            f_det = datetime.strptime(info.get("fecha_iso", hoy), '%Y-%m-%d').date()
                            if (ahora_art().date() - f_det).days <= DIAS_SEGUIMIENTO_VERDE:
                                dic_limpio[sym] = info
                        except Exception:
                            continue
                    base[clave] = dic_limpio

                if data.get("fecha") == hoy:
                    base["mencionadas"] = data.get("mencionadas", {})
                    base["resumen_dia"] = data.get("resumen_dia", [])
                    base["resumen_enviado_hoy"] = data.get("resumen_enviado_hoy", False)
        except Exception:
            pass
    return base

def guardar_historial(historial):
    try:
        with open(HISTORIAL_FILE, 'w', encoding='utf-8') as f:
            json.dump(historial, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"⚠️ Error guardando historial: {e}")

def crear_sesion_binance():
    s = requests.Session()
    s.headers.update({"User-Agent": "Mozilla/5.0", "Accept": "application/json", "Cache-Control": "no-cache"})
    return s

def obtener_simbolos_spot_activos(session):
    for url in ["https://api.binance.com/api/v3/exchangeInfo", "https://data-api.binance.vision/api/v3/exchangeInfo"]:
        try:
            res = session.get(url, timeout=12)
            if res.status_code == 200:
                activos = {s['symbol'] for s in res.json().get('symbols', []) if s.get('status') == 'TRADING' and s.get('isSpotTradingAllowed', True) and s.get('quoteAsset') == 'USDT'}
                if activos: return activos
        except Exception:
            continue
    return set()

def obtener_datos_binance(session):
    for url in ["https://api.binance.com/api/v3/ticker/24hr", "https://data-api.binance.vision/api/v3/ticker/24hr"]:
        try:
            r = session.get(url, timeout=15)
            if r.status_code == 200 and isinstance(r.json(), list) and r.json():
                return r.json()
        except Exception:
            continue
    return []

def calcular_ema(valores, periodo):
    if not valores: return 0.0
    k = 2 / (periodo + 1)
    ema = valores[0]
    for v in valores[1:]:
        ema = (v * k) + (ema * (1 - k))
    return ema

def calcular_rsi(cierres, periodo=14):
    if len(cierres) <= periodo: return 50.0
    deltas = [cierres[i] - cierres[i - 1] for i in range(1, len(cierres))]
    ganancias = [d if d > 0 else 0.0 for d in deltas]
    perdidas = [-d if d < 0 else 0.0 for d in deltas]
    avg_g = sum(ganancias[:periodo]) / periodo
    avg_p = sum(perdidas[:periodo]) / periodo
    for i in range(periodo, len(ganancias)):
        avg_g = (avg_g * (periodo - 1) + ganancias[i]) / periodo
        avg_p = (avg_p * (periodo - 1) + perdidas[i]) / periodo
    if avg_p == 0: return 100.0
    rs = avg_g / avg_p
    return round(100.0 - (100.0 / (1.0 + rs)), 1)

def calcular_probabilidad_inversion(session, symbol, cambio_24h, vol_24h):
    for base_url in ["https://api.binance.com", "https://data-api.binance.vision"]:
        try:
            r1h = session.get(f"{base_url}/api/v3/klines", params={"symbol": symbol, "interval": "1h", "limit": 25}, timeout=7)
            r15m = session.get(f"{base_url}/api/v3/klines", params={"symbol": symbol, "interval": "15m", "limit": 10}, timeout=7)
            if r1h.status_code == 200 and r15m.status_code == 200:
                k1h, k15m = r1h.json(), r15m.json()
                cierres_1h = [float(x[4]) for x in k1h]
                vols_1h = [float(x[7]) for x in k1h]
                open_1h, close_1h = float(k1h[-1][1]), cierres_1h[-1]
                open_15m, close_15m = float(k15m[-1][1]), float(k15m[-1][4])

                var_1h = round(((close_1h - open_1h) / open_1h) * 100, 2) if open_1h > 0 else 0.0
                var_15m = round(((close_15m - open_15m) / open_15m) * 100, 2) if open_15m > 0 else 0.0
                rsi_1h = calcular_rsi(cierres_1h, 14)
                ema7 = calcular_ema(cierres_1h[-15:], 7)
                ema21 = calcular_ema(cierres_1h, 21)

                vol_reciente = sum(vols_1h[-2:]) / 2.0
                vol_previo = sum(vols_1h[-12:-2]) / 10.0 if len(vols_1h) >= 12 else vol_reciente
                vol_surge = round(vol_reciente / vol_previo, 2) if vol_previo > 0 else 1.0

                prob = 20.0
                if vol_surge >= 2.2: prob += 32
                elif vol_surge >= 1.6: prob += 25
                elif vol_surge >= 1.25: prob += 18
                elif vol_surge >= 1.05: prob += 10

                if close_1h > ema7 > ema21:
                    ema_estado = "Alcista (P>EMA7>EMA21)"
                    prob += 25
                elif close_1h > ema7:
                    ema_estado = "Cruce Inicial (>EMA7)"
                    prob += 15
                else:
                    ema_estado = "Acumulando Base"
                    prob += 5

                if 50.0 <= rsi_1h <= 66.0:
                    prob += 18
                elif 42.0 <= rsi_1h < 50.0:
                    prob += 13
                elif 66.0 < rsi_1h <= 74.0:
                    prob += 8

                if 0.05 <= var_1h <= 2.2 and var_15m >= 0.0:
                    prob += 15
                elif var_1h >= -0.20 and var_15m > 0.05:
                    prob += 9

                prob_final = min(98, max(10, int(round(prob))))
                return {
                    "ok": True,
                    "probabilidad_pct": prob_final,
                    "var_1h": var_1h,
                    "var_15m": var_15m,
                    "rsi_1h": rsi_1h,
                    "ema_estado": ema_estado,
                    "vol_surge": vol_surge
                }
        except Exception:
            continue
    return {"ok": False, "probabilidad_pct": 0}

def clasificar_probabilidad_semaforo(prob_pct):
    if prob_pct >= 72:
        return "ROJO", "#ff1744", "🔴"
    elif prob_pct >= 52:
        return "AMARILLO", "#ffd600", "🟡"
    else:
        return "VERDE", "#00e676", "🟢"

def formatear_precio(p):
    if p is None or p <= 0: return "$0.00"
    if p >= 100: return f"${p:,.2f}"
    if p >= 1.0: return f"${p:.4f}"
    if p >= 0.01: return f"${p:.5f}"
    if p >= 0.0001: return f"${p:.6f}"
    return f"${p:.8f}"

def curar_con_gemini(rojas, amarillas, verdes):
    def default_top(lista, motivo_def):
        if not lista: return {"symbol": "", "motivo": ""}
        mejor = max(lista, key=lambda x: x['probabilidad_pct'])
        return {"symbol": mejor['base'], "motivo": motivo_def}

    fallback_lista = rojas[:7] + amarillas[:7] + verdes[:7]
    tops = {
        "ROJO": default_top(rojas, "Probabilidad máxima: volumen en expansión y medias cruzadas antes de romper."),
        "AMARILLO": default_top(amarillas, "Estructura alcista armándose en 1h con presión compradora sostenida."),
        "VERDE": default_top(verdes, "Detección temprana: absorción silenciosa de volumen con precio aún quieto.")
    }
    dictamen = "Radar de probabilidad Spot en monedas fuera de foco (-2.5% a +5.8%): 1⭐ a 3⭐⭐⭐."

    if not GEMINI_API_KEY or not fallback_lista:
        return fallback_lista, tops, dictamen

    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
        def fmt_pool(lista):
            return "\n".join([
                f"- {i['base']}: prob={i['probabilidad_pct']}%, precio={formatear_precio(i['precio_f'])}, 24h={i['cambio_f']:+.2f}%, "
                f"1h={i['var_1h']:+.2f}%, 15m={i['var_15m']:+.2f}%, RSI_1h={i['rsi_1h']}, EMAs={i['ema_estado']}, VolSurge=x{i['vol_surge']}, vol24h=${i['vol_f']/1e6:.2f}M"
                for i in lista
            ]) or "Sin candidatas"

        prompt = (
            "Eres un analista cuantitativo de Binance Spot especializado en detectar monedas ANTES de que exploten (fuera del radar de ganadoras). "
            "Aquí el semáforo mide PROBABILIDAD DE INVERSIÓN/DESPEGUE (no cuánto subió ya):\n\n"
            f"GRUPO ROJO (Probabilidad Máxima >=72% - Gatillo listo):\n{fmt_pool(rojas)}\n\n"
            f"GRUPO AMARILLO (Probabilidad Alta 52-71% - Estructura armada):\n{fmt_pool(amarillas)}\n\n"
            f"GRUPO VERDE (Probabilidad Inicial 35-51% - Acumulación silenciosa):\n{fmt_pool(verdes)}\n\n"
            "Tareas:\n"
            "1. Ordena las mejores 7 de cada grupo según calidad de acumulación y probabilidad real de ruptura.\n"
            "2. Elige LA MEJOR OPCIÓN (#1) de cada grupo y da su motivo técnico en máximo 95 caracteres.\n"
            "3. Escribe un dictamen táctico global de máximo 130 caracteres.\n"
            "Responde ÚNICAMENTE en JSON válido (sin markdown):\n"
            '{"rojas":["S1","S2","S3","S4","S5","S6","S7"],"amarillas":["S1","S2","S3","S4","S5","S6","S7"],"verdes":["S1","S2","S3","S4","S5","S6","S7"],'
            '"top_roja":{"symbol":"S1","motivo":"..."},"top_amarilla":{"symbol":"S1","motivo":"..."},"top_verde":{"symbol":"S1","motivo":"..."},"dictamen":"..."}'
        )

        for mod in ['gemini-2.5-flash', 'gemini-1.5-flash']:
            try:
                res = client.models.generate_content(model=mod, contents=prompt)
                if res and res.text:
                    txt = re.sub(r'^```json|```$', '', res.text.strip(), flags=re.MULTILINE).strip()
                    data = json.loads(txt)

                    def ordenar_pool(pool, elegidos, top_obj, top_default):
                        mapa = {x['base']: x for x in pool}
                        top_sym = str((top_obj or {}).get("symbol", "")).strip().upper()
                        top_motivo = str((top_obj or {}).get("motivo", "")).strip() or top_default["motivo"]

                        sel = []
                        if top_sym in mapa:
                            sel.append(mapa[top_sym])
                        for s in elegidos:
                            su = str(s).strip().upper()
                            if su in mapa and mapa[su] not in sel:
                                sel.append(mapa[su])
                        for x in pool:
                            if len(sel) >= 7: break
                            if x not in sel: sel.append(x)

                        final_7 = sel[:7]
                        elegida_final = final_7[0]['base'] if final_7 else ""
                        return final_7, {"symbol": elegida_final, "motivo": top_motivo[:110]}

                    r_final, top_r = ordenar_pool(rojas, data.get("rojas", []), data.get("top_roja"), tops["ROJO"])
                    a_final, top_a = ordenar_pool(amarillas, data.get("amarillas", []), data.get("top_amarilla"), tops["AMARILLO"])
                    v_final, top_v = ordenar_pool(verdes, data.get("verdes", []), data.get("top_verde"), tops["VERDE"])

                    tops_actualizados = {"ROJO": top_r, "AMARILLO": top_a, "VERDE": top_v}
                    if data.get("dictamen"):
                        dictamen = str(data["dictamen"])[:150]
                    return r_final + a_final + v_final, tops_actualizados, dictamen
            except Exception:
                continue
    except Exception as e:
        print(f"⚠️ Fallback Gemini Probabilidad: {e}")

    return fallback_lista, tops, dictamen

def evaluar_evolucion_estrellas(session, mapa_mercado, historial):
    seguimiento = historial.get("seguimiento_verde", {})
    graduadas = historial.get("graduadas_pre_explosion", {})
    alertas_independientes = []

    for sym, info in list(seguimiento.items()):
        mkt = mapa_mercado.get(sym)
        if not mkt or int(info.get("estrellas", 0)) < 1:
            continue

        tec = calcular_probabilidad_inversion(session, sym, mkt['cambio_f'], mkt['vol_f'])
        if not tec["ok"]:
            continue

        prob_actual = tec["probabilidad_pct"]
        cat_actual, _, _ = clasificar_probabilidad_semaforo(prob_actual)
        estrellas_previas = int(info.get("estrellas", 1))
        precio_actual = mkt['precio_f']
        precio_inicial = float(info.get("precio_deteccion", precio_actual))
        var_desde_deteccion = ((precio_actual - precio_inicial) / precio_inicial) * 100 if precio_inicial > 0 else 0.0

        if cat_actual == "AMARILLO" and estrellas_previas == 1 and not info.get("alerta_2_estrellas_enviada", False):
            info["estrellas"] = 2
            info["estado_actual"] = "AMARILLO"
            info["alerta_2_estrellas_enviada"] = True
            graduadas[sym] = {
                "symbol": sym, "base": sym.replace("USDT", ""), "estrellas": 2,
                "probabilidad_pct": prob_actual, "precio_ref": precio_actual,
                "fecha_iso": ahora_art().strftime('%Y-%m-%d'),
                "fecha_corta": ahora_art().strftime('%d/%m'),
                "origen": "Evolución Cazador Táctico (⭐⭐)"
            }
            alertas_independientes.append({
                "symbol": sym, "base": sym.replace("USDT", ""), "nivel_estrellas": 2,
                "prob_actual": prob_actual, "fecha_corta": info.get("fecha_corta", ""),
                "precio_inicial": precio_inicial, "precio_actual": precio_actual,
                "var_desde_deteccion": var_desde_deteccion, "mkt": mkt, "tec": tec
            })

        elif cat_actual == "ROJO" and estrellas_previas < 3 and not info.get("alerta_3_estrellas_enviada", False):
            info["estrellas"] = 3
            info["estado_actual"] = "ROJO"
            info["alerta_2_estrellas_enviada"] = True
            info["alerta_3_estrellas_enviada"] = True
            graduadas[sym] = {
                "symbol": sym, "base": sym.
