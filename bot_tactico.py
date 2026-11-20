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
    """
    Calcula la Probabilidad de Despegue/Inversión (0 a 100%) en monedas ocultas.
    No mide si ya subió mucho; mide si está acumulando fuerza antes de explotar.
    """
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

                # Puntuación de Probabilidad de Despegue (0 - 100%)
                prob = 20.0

                # 1. Entrada de volumen silencioso (máx +32 pts)
                if vol_surge >= 2.2: prob += 32
                elif vol_surge >= 1.6: prob += 25
                elif vol_surge >= 1.25: prob += 18
                elif vol_surge >= 1.05: prob += 10

                # 2. Estructura de EMAs en 1h (máx +25 pts)
                if close_1h > ema7 > ema21:
                    ema_estado = "Alcista (P>EMA7>EMA21)"
                    prob += 25
                elif close_1h > ema7:
                    ema_estado = "Cruce Inicial (>EMA7)"
                    prob += 15
                else:
                    ema_estado = "Acumulando Base"
                    prob += 5

                # 3. Salud de RSI 1h sin sobrecompra (máx +18 pts)
                if 50.0 <= rsi_1h <= 66.0:
                    prob += 18
                elif 42.0 <= rsi_1h < 50.0:
                    prob += 13
                elif 66.0 < rsi_1h <= 74.0:
                    prob += 8

                # 4. Impulso controlado en 15m/1h sin FOMO (máx +15 pts)
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
        return "ROJO", "#ff1744", "🔴"      # Probabilidad Máxima (Gatillo listo)
    elif prob_pct >= 52:
        return "AMARILLO", "#ffd600", "🟡"  # Probabilidad Alta (Estructura armada)
    else:
        return "VERDE", "#00e676", "🟢"     # Probabilidad Inicial (Acumulación silenciosa)

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
    """
    Evalúa la evolución de probabilidad en monedas nacidas con ⭐ en VERDE:
    - Probabilidad sube a AMARILLO (>=52%) -> ⭐⭐ + alerta independiente.
    - Probabilidad sube a ROJO (>=72%) -> ⭐⭐⭐ + alerta independiente + pasa a graduadas_pre_explosion.
    """
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

        # EVOLUCIÓN 1: ⭐ VERDE -> ⭐⭐ AMARILLO
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

        # EVOLUCIÓN 2: ⭐⭐ -> ⭐⭐⭐ ROJO (CONFIRMACIÓN MÁXIMA)
        elif cat_actual == "ROJO" and estrellas_previas < 3 and not info.get("alerta_3_estrellas_enviada", False):
            info["estrellas"] = 3
            info["estado_actual"] = "ROJO"
            info["alerta_2_estrellas_enviada"] = True
            info["alerta_3_estrellas_enviada"] = True
            graduadas[sym] = {
                "symbol": sym, "base": sym.replace("USDT", ""), "estrellas": 3,
                "probabilidad_pct": prob_actual, "precio_ref": precio_actual,
                "fecha_iso": ahora_art().strftime('%Y-%m-%d'),
                "fecha_corta": ahora_art().strftime('%d/%m'),
                "origen": "Confirmación Máxima Cazador Táctico (⭐⭐⭐)"
            }
            alertas_independientes.append({
                "symbol": sym, "base": sym.replace("USDT", ""), "nivel_estrellas": 3,
                "prob_actual": prob_actual, "fecha_corta": info.get("fecha_corta", ""),
                "precio_inicial": precio_inicial, "precio_actual": precio_actual,
                "var_desde_deteccion": var_desde_deteccion, "mkt": mkt, "tec": tec
            })

        info["ultimo_precio"] = precio_actual
        info["ultimo_estado"] = cat_actual
        info["ultima_probabilidad"] = prob_actual
        seguimiento[sym] = info

    historial["seguimiento_verde"] = seguimiento
    historial["graduadas_pre_explosion"] = graduadas
    return alertas_independientes

def motor_ia_seleccion_tactica(session, tickers, simbolos_activos, historial):
    EXCLUIDOS = {
        'USDT','USDC','FDUSD','DAI','TUSD','USDP','EUR','BUSD','USD1','AEUR','EURI','USDE','RLUSD','RWUSD','XUSD','BFUSD','U','USDG','USDS','PYUSD','PAXG','XAUT',
        'BTC','ETH','SOL','ADA','XRP','DOGE','TRX','SHIB','AVAX','LINK','BNB','DOT','NEAR','SUI','PEPE','GBP','TRY','BRL','ARS'
    }

    mencionadas = historial.get("mencionadas", {})
    for sym in list(mencionadas.keys()):
        mencionadas[sym] -= 1
        if mencionadas[sym] <= 0:
            del mencionadas[sym]

    candidatas_silenciosas = []
    mapa_mercado = {}

    for t in tickers:
        sym = t.get('symbol', '')
        if not sym.endswith('USDT') or sym not in simbolos_activos:
            continue
        base = sym[:-4]
        if base in EXCLUIDOS or not re.match(r'^[A-Z0-9]+$', base) or base.endswith('B'):
            continue
        if any(x in base for x in ['UP', 'DOWN', 'BULL', 'BEAR']):
            continue

        try:
            precio = float(t.get('lastPrice', 0))
            cambio_24h = float(t.get('priceChangePercent', 0))
            vol_usdt = float(t.get('quoteVolume', 0))
            high = float(t.get('highPrice', 0))
            low = float(t.get('lowPrice', 0))
            if precio <= 0: continue

            base_24h = (precio / (1.0 + (cambio_24h / 100.0))) if cambio_24h > -99.9 else float(t.get('openPrice', precio))
            rango = high - low
            pct_rango = (rango / precio) * 100 if precio > 0 else 1.0
            presion_24h = (vol_usdt / 1_000_000) / max(pct_rango, 1.0)

            item = {
                'symbol': sym, 'base': base, 'base_24h_f': base_24h, 'precio_f': precio,
                'cambio_f': cambio_24h, 'vol_f': vol_usdt, 'high_f': high, 'low_f': low,
                'presion_24h': presion_24h
            }
            mapa_mercado[sym] = item

            en_seg = int(historial.get("seguimiento_verde", {}).get(sym, {}).get("estrellas", 0)) >= 1
            if sym in mencionadas and not en_seg:
                continue

            # FILTRO FUERA DEL RADAR: monedas que nadie está mirando todavía (-2.5% a +5.8%)
            if not (0.000001 <= precio < 5.00 and 600_000 <= vol_usdt <= 45_000_000 and -2.5 <= cambio_24h <= 5.8):
                continue

            candidatas_silenciosas.append(item)
        except Exception:
            continue

    alertas_independientes = evaluar_evolucion_estrellas(session, mapa_mercado, historial)

    # Analizar las 36 con mayor presión de acumulación silenciosa
    top_pre = sorted(candidatas_silenciosas, key=lambda x: x['presion_24h'], reverse=True)[:36]
    rojas_ok, amarillas_ok, verdes_ok = [], [], []
    total_analizadas = len(candidatas_silenciosas)

    for it in top_pre:
        tec = calcular_probabilidad_inversion(session, it['symbol'], it['cambio_f'], it['vol_f'])
        if not tec["ok"] or tec["probabilidad_pct"] < 35:
            continue
        it.update(tec)
        cat, color_hex, emoji = clasificar_probabilidad_semaforo(tec["probabilidad_pct"])
        it['categoria'] = cat
        it['color_hex'] = color_hex
        it['emoji_semaforo'] = emoji

        if cat == "ROJO": rojas_ok.append(it)
        elif cat == "AMARILLO": amarillas_ok.append(it)
        else: verdes_ok.append(it)

    rojas_ok.sort(key=lambda x: x['probabilidad_pct'], reverse=True)
    amarillas_ok.sort(key=lambda x: x['probabilidad_pct'], reverse=True)
    verdes_ok.sort(key=lambda x: x['probabilidad_pct'], reverse=True)

    matriz_21, tops_ia, dictamen_ia = curar_con_gemini(rojas_ok, amarillas_ok, verdes_ok)
    top_symbols = {tops_ia[k]["symbol"] for k in tops_ia if tops_ia[k].get("symbol")}

    seguimiento = historial.get("seguimiento_verde", {})
    graduadas = historial.get("graduadas_pre_explosion", {})
    fecha_iso = ahora_art().strftime('%Y-%m-%d')
    fecha_corta = ahora_art().strftime('%d/%m')

    for item in matriz_21:
        sym = item['symbol']
        base = item['base']
        es_elegida = base in top_symbols
        estrellas_seg = int(seguimiento.get(sym, {}).get("estrellas", 0))

        # Si nace como #1 en VERDE -> registra con 1 estrella (⭐) para seguimiento evolutivo
        if item['categoria'] == "VERDE" and es_elegida:
            if sym not in seguimiento or estrellas_seg < 1:
                seguimiento[sym] = {
                    "fecha_iso": fecha_iso, "fecha_corta": fecha_corta,
                    "precio_deteccion": item['precio_f'], "estrellas": 1,
                    "estado_actual": "VERDE", "ultimo_estado": "VERDE",
                    "ultima_probabilidad": item['probabilidad_pct'],
                    "alerta_2_estrellas_enviada": False, "alerta_3_estrellas_enviada": False
                }
                estrellas_seg = 1

        if estrellas_seg >= 2:
            item['estrellas'] = estrellas_seg
        elif es_elegida:
            item['estrellas'] = max(estrellas_seg, 1)
        else:
            item['estrellas'] = 0

        item['es_top_ia'] = item['estrellas'] >= 1

        # Si es #1 en ROJO o AMARILLO (o tiene >=2 estrellas), pasa a graduadas_pre_explosion para que Pre-Explosión la cruce
        if (item['categoria'] in ["ROJO", "AMARILLO"] and es_elegida) or item['estrellas'] >= 2:
            graduadas[sym] = {
                "symbol": sym, "base": base, "estrellas": item['estrellas'],
                "probabilidad_pct": item['probabilidad_pct'], "precio_ref": item['precio_f'],
                "fecha_iso": fecha_iso, "fecha_corta": fecha_corta,
                "origen": f"Cazador Táctico ({item['categoria']} {'⭐'*item['estrellas']})"
            }

        mencionadas[sym] = 1
        if sym not in historial["resumen_dia"]:
            historial["resumen_dia"].append(sym)

    historial["mencionadas"] = mencionadas
    historial["seguimiento_verde"] = seguimiento
    historial["graduadas_pre_explosion"] = graduadas
    guardar_historial(historial)
    return matriz_21, total_analizadas, historial, tops_ia, dictamen_ia, alertas_independientes

def generar_grafico_matriz(lista_items, filename="grafico_cazador_21.png"):
    simbolos = []
    for item in lista_items:
        est = item.get('estrellas', 0)
        pref = ("★" * est) if est > 0 else ""
        simbolos.append(f"{pref}{item['base']}")

    probs = [item['probabilidad_pct'] for item in lista_items]
    colores = [item['color_hex'] for item in lista_items]
    estrellas_list = [item.get('estrellas', 0) for item in lista_items]

    fig, ax = plt.subplots(figsize=(15, 5.8), facecolor='#0b132b')
    ax.set_facecolor('#0b132b')
    bars = ax.bar(simbolos, probs, color=colores, width=0.58, zorder=3)
    ax.grid(True, color='#1e293b', linestyle='-', linewidth=0.8, zorder=1)
    ax.set_axisbelow(True)
    ax.set_ylim(0, 122)
    for spine in ['top', 'right', 'left', 'bottom']:
        ax.spines[spine].set_visible(False)
    ax.tick_params(left=False, labelleft=False, bottom=False)
    ax.tick_params(axis='x', colors='white', labelsize=8, rotation=32)

    for bar, item, pr, color, est in zip(bars, lista_items, probs, colores, estrellas_list):
        yv = bar.get_height()
        xval = bar.get_x() + bar.get_width() / 2.0
        if est > 0:
            borde = '#ffd700' if est >= 2 else '#ffffff'
            bar.set_edgecolor(borde)
            bar.set_linewidth(2.4 if est == 3 else 1.8)
            marca = "★" * est
            ax.text(xval, yv + 3.0, f"{marca}\n{pr}%", ha='center', va='bottom', color='#ffd700' if est >= 2 else '#ffffff', fontweight='bold', fontsize=8)
        else:
            ax.text(xval, yv + 2.5, f"{pr}%", ha='center', va='bottom', color=color, fontweight='bold', fontsize=8)

        ax.plot(xval, max(yv / 2.0, 14), marker='o', markersize=15, markerfacecolor='#0f172a',
                markeredgecolor='#ffd700' if est >= 2 else ('#ffffff' if est == 1 else color), markeredgewidth=2.0 if est > 0 else 1.5, zorder=4)
        ax.text(xval, max(yv / 2.0, 14), item['base'][:5], ha='center', va='center', color='white', fontsize=5.8, fontweight='bold', zorder=5)

    fecha_str = ahora_art().strftime('%Y-%m-%d %H:%M ART')
    plt.title(f"🔥 CAZADOR TÁCTICO • PROBABILIDAD DE EXPLOSIÓN (MONEDAS OCULTAS)", loc='left', color='#ffab00', fontsize=11.5, fontweight='bold', pad=12)
    ax.text(0.0, 1.02, f"Fecha: {fecha_str} | ★=Inicio | ★★=Evolución | ★★★=Confirmada para Pre-Explosión", transform=ax.transAxes, color='#94a3b8', fontsize=8.5)
    plt.tight_layout()
    plt.savefig(filename, dpi=300, facecolor=fig.get_facecolor())
    plt.close()
    return filename

def enviar_texto_telegram(texto):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID: return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    tid = int(TELEGRAM_TOPIC_ID) if TELEGRAM_TOPIC_ID.isdigit() else None
    partes = [texto[i:i+3900] for i in range(0, len(texto), 3900)]
    for parte in partes:
        payload = {"chat_id": TELEGRAM_CHAT_ID, "text": parte, "parse_mode": "HTML", "disable_web_page_preview": True}
        if tid: payload["message_thread_id"] = tid
        try:
            r = requests.post(url, json=payload, timeout=15).json()
            if not r.get("ok") and "thread not found" in str(r.get("description", "")).lower():
                payload.pop("message_thread_id", None)
                requests.post(url, json=payload, timeout=15)
        except Exception as e:
            print(f"⚠️ Error texto Telegram: {e}")
        time.sleep(1)

def enviar_alerta_evolucion_independiente(al):
    sim = al['base']
    mkt = al['mkt']
    tec = al['tec']
    nivel = al['nivel_estrellas']
    uid = int(time.time() * 1000) + random.randint(1, 9999)
    u_ia = f"{BASE_URL_NETLIFY}/?coin={sim}&price={mkt['precio_f']}&change={mkt['cambio_f']}&high={mkt['high_f']}&low={mkt['low_f']}&v={sim}_{uid}"
    u_tr = f"https://www.binance.com/es/trade/{sim}_USDT"
    fecha_ahora = ahora_art().strftime('%Y-%m-%d %H:%M ART')

    if nivel == 2:
        msg = (
            f"🚨 <b>ALERTA DE EVOLUCIÓN DE PROBABILIDAD • ⭐⭐ (2 ESTRELLAS)</b>\n"
            f"📅 <code>{fecha_ahora}</code>\n\n"
            f"⚡ La moneda oculta <b>*{sim}*</b> (cazada con ⭐ en 🟢 <b>VERDE</b> el <code>{al['fecha_corta']}</code> a <code>{formatear_precio(al['precio_inicial'])}</code>) "
            f"subió su probabilidad de despegue a <b>{al['prob_actual']}%</b> (🟡 <b>AMARILLO</b>).\n\n"
            f"• <b>Precio Inicial (⭐):</b> <code>{formatear_precio(al['precio_inicial'])}</code>\n"
            f"• <b>Precio Actual (⭐⭐):</b> <code>{formatear_precio(al['precio_actual'])}</code> (<b>{al['var_desde_deteccion']:+.2f}%</b>)\n"
            f"• <b>Estructura:</b> <code>1h: {tec['var_1h']:+.2f}% | RSI(1h): {tec['rsi_1h']} | {tec['ema_estado']} | Vol: x{tec['vol_surge']}</code>\n\n"
            f"🎯 <i>Estado: Armando estructura alcista; próxima parada 🔴 ROJO (⭐⭐⭐) y cruce en Pre-Explosión.</i>\n"
            f"└ <a href=\"{html.escape(u_ia)}\">📊 Ver Resumen IA</a> | <a href=\"{html.escape(u_tr)}\">🔶 Abrir en Binance</a>"
        )
    else:
        msg = (
            f"🏆 <b>CONFIRMACIÓN MÁXIMA DE INVERSIÓN • ⭐⭐⭐ (3 ESTRELLAS)</b>\n"
            f"📅 <code>{fecha_ahora}</code>\n\n"
            f"🚀 La moneda <b>*{sim}*</b> completó la evolución desde 🟢 <b>VERDE</b> (<code>{al['fecha_corta']}</code> a <code>{formatear_precio(al['precio_inicial'])}</code>) "
            f"hasta <b>{al['prob_actual']}% de probabilidad</b> (🔴 <b>ROJO</b>) y alcanza las <b>3 ESTRELLAS (⭐⭐⭐)</b>.\n\n"
            f"• <b>Precio Origen (⭐):</b> <code>{formatear_precio(al['precio_inicial'])}</code>\n"
            f"• <b>Precio Confirmado (⭐⭐⭐):</b> <code>{formatear_precio(al['precio_actual'])}</code> (<b>{al['var_desde_deteccion']:+.2f}%</b>)\n"
            f"• <b>Estructura:</b> <code>1h: {tec['var_1h']:+.2f}% | RSI(1h): {tec['rsi_1h']} | {tec['ema_estado']} | Vol: x{tec['vol_surge']}</code>\n\n"
            f"✅ <i>Dictamen IA: Graduada con éxito. Vigilar su entrada en 🟢 VERDE dentro del bot Pre-Explosión.</i>\n"
            f"└ <a href=\"{html.escape(u_ia)}\">📊 Ver Resumen IA</a> | <a href=\"{html.escape(u_tr)}\">🔶 Tradear en Binance</a>"
        )

    enviar_texto_telegram(msg)

def enviar_telegram_blindado(image_path, texto):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    url_base = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"
    tid = int(TELEGRAM_TOPIC_ID) if TELEGRAM_TOPIC_ID.isdigit() else None
    cabe_en_caption = len(texto) <= 1020

    for intento in range(3):
        try:
            pf = {"chat_id": TELEGRAM_CHAT_ID}
            if tid: pf["message_thread_id"] = tid
            if cabe_en_caption:
                pf.update({"caption": texto, "parse_mode": "HTML"})

            with open(image_path, 'rb') as ph:
                res = requests.post(f"{url_base}/sendPhoto", data=pf, files={"photo": ph}, timeout=25).json()
                if not res.get("ok") and "thread not found" in str(res.get("description", "")).lower():
                    pf.pop("message_thread_id", None)
                    ph.seek(0)
                    res = requests.post(f"{url_base}/sendPhoto", data=pf, files={"photo": ph}, timeout=25).json()

            if res.get("ok"):
                if not cabe_en_caption:
                    enviar_texto_telegram(texto)
                print("✅ Cazador Táctico entregado correctamente en Telegram.")
                return
        except Exception as e:
            print(f"⚠️ Error envío Telegram (intento {intento+1}): {e}")
        time.sleep(3)

if __name__ == "__main__":
    print(f"🔥 INICIANDO CAZADOR TÁCTICO DE PROBABILIDAD ({ahora_art().strftime('%H:%M:%S')} ART)...")
    s = crear_sesion_binance()
    activos = obtener_simbolos_spot_activos(s)
    datos = obtener_datos_binance(s)

    if datos and activos:
        historial = cargar_historial()
        matriz, total_analizadas, historial, tops_ia, dictamen_ia, alertas_independientes = motor_ia_seleccion_tactica(s, datos, activos, historial)

        for al in alertas_independientes:
            enviar_alerta_evolucion_independiente(al)
            time.sleep(1.5)

        if matriz:
            fname = generar_grafico_matriz(matriz)
            fecha_str = ahora_art().strftime('%Y-%m-%d %H:%M ART')
            msg = (
                f"🔥 <b>CAZADOR TÁCTICO • PROBABILIDAD DE EXPLOSIÓN ({len(matriz)} OCULTAS)</b>\n"
                f"📅 <code>{fecha_str}</code> | Monedas fuera de foco: {total_analizadas}\n"
                f"🧠 <i>{html.escape(dictamen_ia)}</i>\n\n"
            )

            categorias = [
                ("ROJO", "🔴 <b>PROBABILIDAD MÁXIMA (Gatillo Listo • 72%–98%)</b>"),
                ("AMARILLO", "🟡 <b>PROBABILIDAD ALTA (Estructura Armada • 52%–71%)</b>"),
                ("VERDE", "🟢 <b>PROBABILIDAD INICIAL (Acumulación Silenciosa • 35%–51%)</b>")
            ]

            seg_activo = historial.get("seguimiento_verde", {})

            for cat_key, cat_title in categorias:
                items_cat = [i for i in matriz if i['categoria'] == cat_key]
                if not items_cat: continue
                top_info = tops_ia.get(cat_key, {})
                msg += f"{cat_title}\n"
                for it in items_cat:
                    sim = it['base']
                    sym = it['symbol']
                    est = it.get('estrellas', 0)
                    uid = int(time.time() * 1000) + random.randint(1, 9999)
                    u_ia = f"{BASE_URL_NETLIFY}/?coin={sim}&price={it['precio_f']}&change={it['cambio_f']}&high={it['high_f']}&low={it['low_f']}&v={sim}_{uid}"
                    u_tr = f"https://www.binance.com/es/trade/{sim}_USDT"
                    tag_seg = f" <i>[👁️ Seg. {seg_activo[sym]['fecha_corta']}]</i>" if sym in seg_activo else ""

                    if est > 0:
                        estrellas_txt = "⭐" * est
                        etiqueta_nivel = (
                            "CONFIRMADA PRE-EXPLOSIÓN (3/3)" if est == 3 else
                            ("EVOLUCIÓN ACTIVA (2/3)" if est == 2 else "MEJOR OPCIÓN IA (1/3)")
                        )
                        motivo = html.escape(top_info.get("motivo", ""))
                        msg += (
                            f"{estrellas_txt} <b>*{sim}* [{etiqueta_nivel} • Prob: {it['probabilidad_pct']}%]</b> | Base (0%): <code>{formatear_precio(it['base_24h_f'])}</code> ➔ Actual: <code>{formatear_precio(it['precio_f'])}</code> | <b>{it['cambio_f']:+.2f}%</b>\n"
                            f"   📐 <code>1h: {it['var_1h']:+.2f}% | 15m: {it['var_15m']:+.2f}% | RSI(1h): {it['rsi_1h']} | Vol: x{it['vol_surge']}</code>{tag_seg}\n"
                        )
                        if motivo:
                            msg += f"   💡 <i>{motivo}</i>\n"
                        msg += f"   └ <a href=\"{html.escape(u_ia)}\">📊 Resumen IA</a> | <a href=\"{html.escape(u_tr)}\">🔶 Tradear</a>\n"
                    else:
                        msg += (
                            f"• <b>{sim}</b> (Prob: <b>{it['probabilidad_pct']}%</b>) | Base (0%): <code>{formatear_precio(it['base_24h_f'])}</code> ➔ Actual: <code>{formatear_precio(it['precio_f'])}</code> | <b>{it['cambio_f']:+.2f}%</b>{tag_seg}\n"
                            f"  └ <a href=\"{html.escape(u_ia)}\">📊 Resumen IA</a> | <a href=\"{html.escape(u_tr)}\">🔶 Tradear</a>\n"
                        )
                msg += "\n"

            enviar_telegram_blindado(fname, msg.strip())

            if ahora_art().hour >= 21 and not historial.get("resumen_enviado_hoy", False):
                monedas_dia = [sym.replace('USDT', '') for sym in historial.get("resumen_dia", [])]
                en_radar = [
                    f"{'⭐'*int(d.get('estrellas',1))} {s.replace('USDT','')} ({d['fecha_corta']} ➔ Prob {d.get('ultima_probabilidad',0)}%)"
                    for s, d in seg_activo.items() if int(d.get('estrellas', 0)) >= 1
                ]
                if monedas_dia or en_radar:
                    resumen = (
                        f"📋 <b>RESUMEN DIARIO • CAZADOR TÁCTICO (21:00 ART)</b>\n"
                        f"📅 <code>{ahora_art().strftime('%Y-%m-%d')}</code>\n\n"
                        f"Monedas ocultas detectadas hoy:\n<code>{', '.join(monedas_dia) or 'Ninguna'}</code>\n\n"
                        f"👁️ Radar de Estrellas activo:\n<code>{', '.join(en_radar) or 'Sin activos con estrella en seguimiento'}</code>"
                    )
                    enviar_texto_telegram(resumen)
                    historial["resumen_enviado_hoy"] = True
                    guardar_historial(historial)
        else:
            print("⚠️ Ninguna moneda oculta alcanzó el umbral mínimo de probabilidad en este ciclo.")
    else:
        print("❌ ERROR: Sin datos de Binance.")

# FIN BOT TACTICO
