import os
import re
import sys
import json
import time
import random
import html
import subprocess
from datetime import datetime, timezone, timedelta

# Auto-instalación blindada de todas las dependencias necesarias
for mod, pkg in [
    ("requests", "requests"),
    ("matplotlib", "matplotlib"),
    ("openpyxl", "openpyxl"),
    ("google.genai", "google-genai")
]:
    try:
        __import__(mod)
    except ImportError:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", pkg])

import requests
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from google import genai

# --- CONFIGURACIÓN DE ENTORNO BLINDADA ---
TZ_ART = timezone(timedelta(hours=-3))
TELEGRAM_BOT_TOKEN = (os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("TELEGRAM_TOKEN") or "").strip()
TELEGRAM_CHAT_ID = (os.getenv("TELEGRAM_CHAT_ID") or os.getenv("CHAT_ID") or "").strip()
TELEGRAM_TOPIC_ID = (
    os.getenv("TOPIC_ID_GANADORAS")
    or os.getenv("TELEGRAM_MESSAGE_THREAD_ID")
    or os.getenv("TOPIC_ID_CENTRAL")
    or ""
).strip()
GEMINI_API_KEY = (os.getenv("GEMINI_API_KEY") or "").strip()
BASE_URL_NETLIFY = "https://gregarious-frangollo-0346c5.netlify.app"

HISTORIAL_GANADORAS_FILE = "historial_ganadoras.json"
HISTORIAL_PERLAS_FILE = "historial_perlas.json"
EXCEL_AUDITORIA_FILE = "AUDITORIA_VERDE_GANADORAS.xlsx"
DIAS_RETENCION = 62
MODELOS_GEMINI_GANADORAS = ["gemini-2.5-flash", "gemini-2.5-flash-lite"]

MESES_ES = {
    1: "ENERO", 2: "FEBRERO", 3: "MARZO", 4: "ABRIL",
    5: "MAYO", 6: "JUNIO", 7: "JULIO", 8: "AGOSTO",
    9: "SEPTIEMBRE", 10: "OCTUBRE", 11: "NOVIEMBRE", 12: "DICIEMBRE"
}
DIAS_SEMANA_ES = {
    0: "LUNES", 1: "MARTES", 2: "MIERCOLES", 3: "JUEVES",
    4: "VIERNES", 5: "SABADO", 6: "DOMINGO"
}

EXCL_BASE = {
    'USDT', 'USDC', 'FDUSD', 'DAI', 'TUSD', 'USDP', 'EUR', 'GBP', 'AUD', 'BRL', 'ARS', 'TRY', 'BUSD',
    'USD1', 'AEUR', 'EURI', 'USDE', 'RLUSD', 'RWUSD', 'XUSD', 'BFUSD', 'U', 'USDG', 'USDS', 'PYUSD',
    'BTC', 'ETH', 'SOL', 'ADA', 'XRP', 'DOGE', 'TRX', 'SHIB', 'AVAX', 'LINK', 'BNB', 'DOT', 'NEAR', 'SUI', 'PEPE'
}


def ahora_art():
    return datetime.now(TZ_ART)


def es_simbolo_valido(base):
    if not base or base in EXCL_BASE:
        return False
    if not re.match(r'^[A-Z0-9]+$', base):
        return False
    if base.endswith('B'):
        return False
    if any(x in base for x in ['UP', 'DOWN', 'BULL', 'BEAR']):
        return False
    return True


def formatear_precio(precio):
    if precio is None or precio <= 0:
        return "$0.00"
    if precio >= 100:
        return f"${precio:,.2f}"
    if precio >= 1.0:
        return f"${precio:.4f}"
    if precio >= 0.01:
        return f"${precio:.5f}"
    if precio >= 0.0001:
        return f"${precio:.6f}"
    return f"${precio:.8f}"


def calcular_precio_base_0(precio_actual, cambio_pct, precio_base_guardado=0.0):
    """Obtiene el precio base (0%) desde openPrice o lo reconstruye desde precio_actual y % subida."""
    p_base = float(precio_base_guardado or 0.0)
    if p_base > 0:
        return round(p_base, 8)
    p_act = float(precio_actual or 0.0)
    factor = 1.0 + (float(cambio_pct or 0.0) / 100.0)
    if p_act > 0 and factor > 0:
        return round(p_act / factor, 8)
    return p_act


def cargar_historial_ganadoras():
    base = {
        "ultima_actualizacion": "",
        "dias": {},
        "ultimo_reporte_semanal": "",
        "ultimo_envio_excel": "",
        "registro_verdes": {}
    }
    if os.path.exists(HISTORIAL_GANADORAS_FILE):
        try:
            with open(HISTORIAL_GANADORAS_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if isinstance(data, dict):
                dias_limpios = {}
                hoy = ahora_art().date()
                for f_str, lista in (data.get("dias") or {}).items():
                    try:
                        f_dt = datetime.strptime(f_str, '%Y-%m-%d').date()
                        if (hoy - f_dt).days <= DIAS_RETENCION:
                            dias_limpios[f_str] = lista
                    except Exception:
                        continue
                base["dias"] = dias_limpios
                base["ultima_actualizacion"] = data.get("ultima_actualizacion", "")
                base["ultimo_reporte_semanal"] = data.get("ultimo_reporte_semanal", "")
                base["ultimo_envio_excel"] = data.get("ultimo_envio_excel", "")
                base["registro_verdes"] = data.get("registro_verdes", {}) if isinstance(data.get("registro_verdes"), dict) else {}
        except Exception as e:
            print(f"⚠️ Error cargando {HISTORIAL_GANADORAS_FILE}: {e}")
    return base


def guardar_historial_ganadoras(historial):
    try:
        with open(HISTORIAL_GANADORAS_FILE, 'w', encoding='utf-8') as f:
            json.dump(historial, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"⚠️ Error guardando {HISTORIAL_GANADORAS_FILE}: {e}")


def absorber_verdes_desde_pre_explosion(historial, mapa_actual):
    if not os.path.exists(HISTORIAL_PERLAS_FILE):
        return
    try:
        with open(HISTORIAL_PERLAS_FILE, 'r', encoding='utf-8') as f:
            perlas = json.load(f)
        if not isinstance(perlas, dict):
            return

        fecha_perlas = perlas.get("fecha") or ahora_art().strftime('%Y-%m-%d')
        verdes = set(perlas.get("verdes_hoy", []))
        oros = set(perlas.get("oro_hoy", []))
        reg = historial.setdefault("registro_verdes", {})

        for sym in (verdes | oros):
            base = sym[:-4] if sym.endswith("USDT") else sym
            if not es_simbolo_valido(base):
                continue
            es_oro = sym in oros
            if sym not in reg:
                precio_in = mapa_actual.get(sym, {}).get("precio", 0.0)
                reg[sym] = {
                    "symbol": sym,
                    "ticker": base,
                    "fecha_verde": fecha_perlas,
                    "ts_verde": ahora_art().strftime('%Y-%m-%d %H:%M'),
                    "precio_verde": precio_in,
                    "es_oro": es_oro,
                    "estado": "PENDIENTE",
                    "fecha_ganadora": "",
                    "precio_ganadora": 0.0,
                    "subida_real_pct": 0.0,
                    "subida_24h_dia_pct": 0.0,
                    "dias_demora": None
                }
            elif es_oro and not reg[sym].get("es_oro"):
                reg[sym]["es_oro"] = True
    except Exception as e:
        print(f"⚠️ Error leyendo {HISTORIAL_PERLAS_FILE}: {e}")


def sincronizar_con_radar_pre_explosion(segunda_ola):
    if not os.path.exists(HISTORIAL_PERLAS_FILE):
        return
    try:
        with open(HISTORIAL_PERLAS_FILE, 'r', encoding='utf-8') as f:
            perlas = json.load(f)
        if not isinstance(perlas, dict):
            return

        hoy_str = ahora_art().strftime('%Y-%m-%d')
        corta_str = ahora_art().strftime('%d/%m')
        grad = perlas.get("graduadas_pre_explosion")
        if not isinstance(grad, dict):
            grad = {}

        for item in segunda_ola[:5]:
            sym = item["symbol"]
            if sym not in grad:
                grad[sym] = {
                    "symbol": sym,
                    "base": item["ticker"],
                    "estrellas": 3,
                    "probabilidad_pct": 80,
                    "precio_ref": item["precio_actual"],
                    "fecha_iso": hoy_str,
                    "fecha_corta": corta_str,
                    "origen": "SEGUNDA_OLA_GANADORAS"
                }

        perlas["graduadas_pre_explosion"] = grad
        with open(HISTORIAL_PERLAS_FILE, 'w', encoding='utf-8') as f:
            json.dump(perlas, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"⚠️ No se pudo sincronizar con {HISTORIAL_PERLAS_FILE}: {e}")


def crear_sesion_binance():
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json",
        "Cache-Control": "no-cache"
    })
    return session


def obtener_simbolos_spot_activos(session):
    urls = [
        "https://api.binance.com/api/v3/exchangeInfo",
        "https://data-api.binance.vision/api/v3/exchangeInfo"
    ]
    for url in urls:
        try:
            res = session.get(url, timeout=12)
            if res.status_code == 200:
                data = res.json()
                activos = {
                    s.get('symbol')
                    for s in data.get('symbols', [])
                    if s.get('status') == 'TRADING'
                    and s.get('isSpotTradingAllowed', True)
                    and s.get('quoteAsset') == 'USDT'
                }
                if activos:
                    return activos
        except Exception as e:
            print(f"⚠️ Error exchangeInfo {url}: {e}")
    return set()


def obtener_datos_binance(session):
    urls = [
        "https://api.binance.com/api/v3/ticker/24hr",
        "https://data-api.binance.vision/api/v3/ticker/24hr"
    ]
    for url in urls:
        try:
            res = session.get(url, timeout=15)
            if res.status_code == 200:
                data = res.json()
                if isinstance(data, list) and len(data) > 0:
                    return data
        except Exception as e:
            print(f"⚠️ Error ticker 24hr {url}: {e}")
    return []


# ==============================================================================
# ETAPA 1: CAPTURA DIARIA DE MONEDAS GANADORAS (24H)
# ==============================================================================
def ejecutar_etapa_1_diaria(tickers, simbolos_activos, historial):
    ahora_dt = ahora_art()
    hoy_str = ahora_dt.strftime('%Y-%m-%d')
    ayer_str = (ahora_dt - timedelta(days=1)).strftime('%Y-%m-%d')
    candidatas = []
    mapa_actual = {}

    for t in tickers:
        sym = t.get('symbol', '')
        if sym not in simbolos_activos or not sym.endswith('USDT'):
            continue
        base = sym[:-4]
        if not es_simbolo_valido(base):
            continue
        try:
            precio = float(t.get('lastPrice', 0))
            cambio_24h = float(t.get('priceChangePercent', 0))
            open_price = float(t.get('openPrice', 0))
            vol_usdt = float(t.get('quoteVolume', 0))
            high = float(t.get('highPrice', 0))
            low = float(t.get('lowPrice', 0))
            if precio <= 0:
                continue

            precio_base = calcular_precio_base_0(precio, cambio_24h, open_price)
            pos_rango = round(((precio - low) / (high - low)) * 100, 1) if high > low else 50.0
            info_ticker = {
                "symbol": sym,
                "ticker": base,
                "precio_base": precio_base,
                "precio": precio,
                "cambio_24h": round(cambio_24h, 2),
                "vol_usdt": round(vol_usdt, 2),
                "high": high,
                "low": low,
                "pos_rango": pos_rango
            }
            mapa_actual[sym] = info_ticker

            if vol_usdt >= 1_000_000 and cambio_24h >= 3.0:
                candidatas.append(info_ticker)
        except (ValueError, TypeError):
            continue

    candidatas.sort(key=lambda x: x["cambio_24h"], reverse=True)
    top_20_dia = candidatas[:20]

    for idx, item in enumerate(top_20_dia, start=1):
        item["rank"] = idx

    if ahora_dt.hour <= 2 and ayer_str not in historial["dias"]:
        historial["dias"][ayer_str] = [dict(x) for x in top_20_dia]

    historial["dias"][hoy_str] = top_20_dia
    historial["ultima_actualizacion"] = ahora_dt.strftime('%Y-%m-%d %H:%M:%S ART')
    guardar_historial_ganadoras(historial)

    return top_20_dia[:10], mapa_actual


# ==============================================================================
# ETAPA 2: CONSOLIDACIÓN SEMANAL + DETECTOR DE SEGUNDA OLA (7 DÍAS)
# ==============================================================================
def ejecutar_etapa_2_semanal(historial, mapa_actual):
    hoy_dt = ahora_art().date()
    dias_dict = historial.get("dias", {})

    fechas_7d = []
    for f_str in sorted(dias_dict.keys()):
        try:
            f_dt = datetime.strptime(f_str, '%Y-%m-%d').date()
            if 0 <= (hoy_dt - f_dt).days <= 7:
                fechas_7d.append(f_str)
        except Exception:
            continue

    acumulado = {}
    for f_str in fechas_7d:
        for item in dias_dict.get(f_str, []):
            sym = item["symbol"]
            if sym not in acumulado:
                acumulado[sym] = {
                    "symbol": sym,
                    "ticker": item["ticker"],
                    "veces": 0,
                    "dias": [],
                    "gains": [],
                    "precio_pico": item["high"] if item.get("high") else item["precio"],
                    "ultimo_precio_win": item["precio"]
                }
            acumulado[sym]["veces"] += 1
            if f_str not in acumulado[sym]["dias"]:
                acumulado[sym]["dias"].append(f_str)
            acumulado[sym]["gains"].append(item["cambio_24h"])
            pico_cand = item["high"] if item.get("high") else item["precio"]
            if pico_cand > acumulado[sym]["precio_pico"]:
                acumulado[sym]["precio_pico"] = pico_cand
            acumulado[sym]["ultimo_precio_win"] = item["precio"]

    reinas_semanales = []
    segunda_ola = []

    for sym, info in acumulado.items():
        gain_max = round(max(info["gains"]), 2)
        gain_prom = round(sum(info["gains"]) / len(info["gains"]), 2)
        actual = mapa_actual.get(sym)
        precio_actual = actual["precio"] if actual else info["ultimo_precio_win"]
        cambio_hoy = actual["cambio_24h"] if actual else 0.0
        pos_rango_hoy = actual["pos_rango"] if actual else 50.0
        vol_hoy = actual["vol_usdt"] if actual else 0.0

        retroceso_desde_pico = 0.0
        if info["precio_pico"] > 0:
            retroceso_desde_pico = round(((precio_actual - info["precio_pico"]) / info["precio_pico"]) * 100, 2)

        resumen_coin = {
            "symbol": sym,
            "ticker": info["ticker"],
            "veces": info["veces"],
            "dias_str": ", ".join([d[5:] for d in info["dias"]]),
            "gain_max": gain_max,
            "gain_prom": gain_prom,
            "precio_pico": info["precio_pico"],
            "precio_actual": precio_actual,
            "cambio_hoy": cambio_hoy,
            "pos_rango_hoy": pos_rango_hoy,
            "retroceso_pct": retroceso_desde_pico,
            "vol_hoy": vol_hoy
        }
        reinas_semanales.append(resumen_coin)

        if (
            actual
            and vol_hoy >= 1_000_000
            and (-22.0 <= retroceso_desde_pico <= -6.0)
            and (pos_rango_hoy <= 38.0)
            and (-3.0 <= cambio_hoy <= 4.0)
        ):
            segunda_ola.append(resumen_coin)

    reinas_semanales.sort(key=lambda x: (x["veces"], x["gain_max"]), reverse=True)
    segunda_ola.sort(key=lambda x: (x["veces"], -x["pos_rango_hoy"]), reverse=True)

    return reinas_semanales[:10], segunda_ola[:5], len(fechas_7d)


# ==============================================================================
# ETAPA 3: AUDITORÍA REALIDAD (VERDE PRE-EXPLOSIÓN -> MONEDA GANADORA)
# ==============================================================================
def ejecutar_etapa_3_auditoria_verde(historial, mapa_actual):
    absorber_verdes_desde_pre_explosion(historial, mapa_actual)
    reg = historial.get("registro_verdes", {})
    dias_dict = historial.get("dias", {})
    hoy_dt = ahora_art().date()

    fechas_ordenadas = sorted(dias_dict.keys())
    aciertos = []
    pendientes = []

    for sym, info in reg.items():
        f_verde_str = info.get("fecha_verde", "")
        if not f_verde_str:
            continue
        try:
            f_verde_dt = datetime.strptime(f_verde_str, '%Y-%m-%d').date()
        except Exception:
            continue

        if info.get("estado") != "ACIERTO":
            for f_win_str in fechas_ordenadas:
                if f_win_str < f_verde_str:
                    continue
                ganadoras_dia = dias_dict.get(f_win_str, [])
                match = next((g for g in ganadoras_dia if g["symbol"] == sym), None)
                if match:
                    f_win_dt = datetime.strptime(f_win_str, '%Y-%m-%d').date()
                    dias_demora = (f_win_dt - f_verde_dt).days
                    p_verde = float(info.get("precio_verde") or 0.0)
                    p_win = float(match.get("precio") or 0.0)
                    subida_real = round(((p_win - p_verde) / p_verde) * 100, 2) if p_verde > 0 else float(match.get("cambio_24h", 0.0))

                    info["estado"] = "ACIERTO"
                    info["fecha_ganadora"] = f_win_str
                    info["precio_ganadora"] = p_win
                    info["subida_real_pct"] = subida_real
                    info["subida_24h_dia_pct"] = float(match.get("cambio_24h", 0.0))
                    info["dias_demora"] = dias_demora
                    break

        if info.get("estado") == "ACIERTO":
            aciertos.append(info)
        else:
            dias_espera = (hoy_dt - f_verde_dt).days
            info["dias_esperando"] = dias_espera
            if dias_espera > 10:
                info["estado"] = "EXPIRADA (>10d)"
            pendientes.append(info)

    guardar_historial_ganadoras(historial)

    total_evaluadas = len(aciertos) + len([p for p in pendientes if p.get("estado") == "EXPIRADA (>10d)"])
    tasa_acierto = round((len(aciertos) / total_evaluadas) * 100, 1) if total_evaluadas > 0 else 0.0
    demoras = [a["dias_demora"] for a in aciertos if a.get("dias_demora") is not None]
    subidas = [a["subida_24h_dia_pct"] for a in aciertos if a.get("subida_24h_dia_pct")]

    demora_prom = round(sum(demoras) / len(demoras), 1) if demoras else None
    demora_mediana = sorted(demoras)[len(demoras) // 2] if demoras else None
    subida_prom = round(sum(subidas) / len(subidas), 1) if subidas else 0.0

    stats = {
        "total_registradas": len(reg),
        "total_aciertos": len(aciertos),
        "total_pendientes": len([p for p in pendientes if p.get("estado") == "PENDIENTE"]),
        "tasa_acierto_pct": tasa_acierto,
        "demora_prom_dias": demora_prom,
        "demora_mediana_dias": demora_mediana,
        "subida_prom_pct": subida_prom
    }

    generar_excel_auditoria(aciertos, pendientes, stats, mapa_actual, historial)
    return aciertos, pendientes, stats


def construir_hoja_mensual_ganadoras(wb, anio, mes, dias_dict, reg_verdes):
    nombre_mes = MESES_ES[mes]
    ws = wb.create_sheet(f"{nombre_mes} {anio}")
    ws.views.sheetView[0].showGridLines = True

    fill_titulo = PatternFill(start_color="0F172A", end_color="0F172A", fill_type="solid")
    fill_dia_hdr = PatternFill(start_color="E2E8F0", end_color="E2E8F0", fill_type="solid")
    fill_res_hdr = PatternFill(start_color="FEF3C7", end_color="FEF3C7", fill_type="solid")
    fill_col_hdr = PatternFill(start_color="1E293B", end_color="1E293B", fill_type="solid")
    fill_res_col = PatternFill(start_color="78350F", end_color="78350F", fill_type="solid")
    fill_verde = PatternFill(start_color="DCFCE7", end_color="DCFCE7", fill_type="solid")

    borde_suave = Border(
        left=Side(style='thin', color='CBD5E1'),
        right=Side(style='thin', color='CBD5E1'),
        top=Side(style='thin', color='CBD5E1'),
        bottom=Side(style='thin', color='CBD5E1')
    )

    ws["A1"] = f"MONEDAS GANADORAS • {nombre_mes} {anio} (CIERRES DIARIOS: BASE 0% VS ACTUAL + RESUMEN SEMANAL)"
    ws["A1"].font = Font(name="Arial", size=12, bold=True, color="FFFFFF")
    ws["A1"].fill = fill_titulo
    ws.merge_cells("A1:AU1")
    ws.row_dimensions[1].height = 26

    fechas_mes = []
    for f_str in sorted(dias_dict.keys()):
        try:
            d = datetime.strptime(f_str, '%Y-%m-%d').date()
            if d.year == anio and d.month == mes:
                fechas_mes.append(d)
        except Exception:
            continue

    semanas_map = {}
    for d in fechas_mes:
        lunes = d - timedelta(days=d.weekday())
        semanas_map.setdefault(lunes, {})[d.weekday()] = d

    fila_base = 3
    sub_hdrs = ["N°", "NOMBRE", "Base 0%", "$ Actual", "% subida"]

    for lunes in sorted(semanas_map.keys()):
        max_filas_bloque = 20

        for w_idx in range(7):
            col_ini = 1 + (w_idx * 6)
            dia_dt = lunes + timedelta(days=w_idx)
            f_str = dia_dt.strftime('%Y-%m-%d')
            lista_dia = dias_dict.get(f_str, []) if dia_dt.month == mes else []

            ws.cell(fila_base, col_ini, dia_dt.day)
            ws.cell(fila_base, col_ini + 1, f"{MESES_ES[dia_dt.month]} - {DIAS_SEMANA_ES[w_idx]}")
            ws.merge_cells(start_row=fila_base, start_column=col_ini + 1, end_row=fila_base, end_column=col_ini + 4)

            for cc in range(col_ini, col_ini + 5):
                cell_h = ws.cell(fila_base, cc)
                cell_h.fill = fill_dia_hdr
                cell_h.font = Font(name="Arial", size=9.5, bold=True, color="0F172A")
                cell_h.border = borde_suave
                cell_h.alignment = Alignment(horizontal="center" if cc == col_ini else "left", vertical="center")

            for off, h_txt in enumerate(sub_hdrs):
                ch = ws.cell(fila_base + 1, col_ini + off, h_txt)
                ch.fill = fill_col_hdr
                ch.font = Font(name="Arial", size=9, bold=True, color="FFFFFF")
                ch.alignment = Alignment(horizontal="center", vertical="center")
                ch.border = borde_suave

            for r_off in range(max_filas_bloque):
                fila_actual = fila_base + 2 + r_off
                if r_off < len(lista_dia):
                    item = lista_dia[r_off]
                    sym = item.get("symbol", "")
                    es_verde = sym in reg_verdes
                    p_act = float(item.get("precio", 0.0))
                    gain_pct = float(item.get("cambio_24h", 0.0))
                    p_base = calcular_precio_base_0(p_act, gain_pct, item.get("precio_base", 0.0))

                    c1 = ws.cell(fila_actual, col_ini, item.get("rank", r_off + 1))
                    c2 = ws.cell(fila_actual, col_ini + 1, item.get("ticker", ""))
                    c3 = ws.cell(fila_actual, col_ini + 2, p_base)
                    c4 = ws.cell(fila_actual, col_ini + 3, p_act)
                    c5 = ws.cell(fila_actual, col_ini + 4, round(gain_pct / 100.0, 4))

                    c1.alignment = Alignment(horizontal="center")
                    c2.alignment = Alignment(horizontal="left")
                    c3.alignment = Alignment(horizontal="right")
                    c4.alignment = Alignment(horizontal="right")
                    c5.alignment = Alignment(horizontal="right")
                    c5.number_format = "0.0%"

                    for cx in (c1, c2, c3, c4, c5):
                        cx.font = Font(name="Arial", size=9, bold=es_verde)
                        cx.border = borde_suave
                        if es_verde:
                            cx.fill = fill_verde
                else:
                    for off in range(5):
                        ce = ws.cell(fila_actual, col_ini + off, "")
                        ce.border = borde_suave

        col_res = 1 + (7 * 6)
        ws.cell(fila_base, col_res, "RESUMEN SEMANAL")
        ws.merge_cells(start_row=fila_base, start_column=col_res, end_row=fila_base, end_column=col_res + 4)
        for cc in range(col_res, col_res + 5):
            cr = ws.cell(fila_base, cc)
            cr.fill = fill_res_hdr
            cr.font = Font(name="Arial", size=9.5, bold=True, color="78350F")
            cr.alignment = Alignment(horizontal="center", vertical="center")
            cr.border = borde_suave

        for off, h_txt in enumerate(sub_hdrs):
            ch = ws.cell(fila_base + 1, col_res + off, h_txt)
            ch.fill = fill_res_col
            ch.font = Font(name="Arial", size=9, bold=True, color="FFFFFF")
            ch.alignment = Alignment(horizontal="center", vertical="center")
            ch.border = borde_suave

        consolidado_sem = {}
        for w_idx in range(7):
            dia_dt = lunes + timedelta(days=w_idx)
            if dia_dt.month != mes:
                continue
            f_str = dia_dt.strftime('%Y-%m-%d')
            for item in dias_dict.get(f_str, []):
                sym = item.get("symbol", "")
                gain = float(item.get("cambio_24h", 0.0))
                p_act = float(item.get("precio", 0.0))
                p_base = calcular_precio_base_0(p_act, gain, item.get("precio_base", 0.0))
                if sym not in consolidado_sem or gain > consolidado_sem[sym]["gain"]:
                    consolidado_sem[sym] = {
                        "symbol": sym,
                        "ticker": item.get("ticker", ""),
                        "precio_base": p_base,
                        "precio": p_act,
                        "gain": gain
                    }

        ranking_sem = sorted(consolidado_sem.values(), key=lambda x: x["gain"], reverse=True)[:max_filas_bloque]
        for r_off in range(max_filas_bloque):
            fila_actual = fila_base + 2 + r_off
            if r_off < len(ranking_sem):
                it = ranking_sem[r_off]
                es_verde = it["symbol"] in reg_verdes
                c1 = ws.cell(fila_actual, col_res, r_off + 1)
                c2 = ws.cell(fila_actual, col_res + 1, it["ticker"])
                c3 = ws.cell(fila_actual, col_res + 2, it["precio_base"])
                c4 = ws.cell(fila_actual, col_res + 3, it["precio"])
                c5 = ws.cell(fila_actual, col_res + 4, round(it["gain"] / 100.0, 4))

                c1.alignment = Alignment(horizontal="center")
                c2.alignment = Alignment(horizontal="left")
                c3.alignment = Alignment(horizontal="right")
                c4.alignment = Alignment(horizontal="right")
                c5.alignment = Alignment(horizontal="right")
                c5.number_format = "0.0%"

                for cx in (c1, c2, c3, c4, c5):
                    cx.font = Font(name="Arial", size=9, bold=es_verde)
                    cx.border = borde_suave
                    if es_verde:
                        cx.fill = fill_verde
            else:
                for off in range(5):
                    ce = ws.cell(fila_actual, col_res + off, "")
                    ce.border = borde_suave

        ws.row_dimensions[fila_base].height = 20
        ws.row_dimensions[fila_base + 1].height = 19
        fila_base += max_filas_bloque + 4

    for b_idx in range(8):
        c_start = 1 + (b_idx * 6)
        ws.column_dimensions[openpyxl.utils.get_column_letter(c_start)].width = 4.5
        ws.column_dimensions[openpyxl.utils.get_column_letter(c_start + 1)].width = 11.5
        ws.column_dimensions[openpyxl.utils.get_column_letter(c_start + 2)].width = 11.0
        ws.column_dimensions[openpyxl.utils.get_column_letter(c_start + 3)].width = 11.0
        ws.column_dimensions[openpyxl.utils.get_column_letter(c_start + 4)].width = 9.5
        if b_idx < 7:
            ws.column_dimensions[openpyxl.utils.get_column_letter(c_start + 5)].width = 2.5


def generar_excel_auditoria(aciertos, pendientes, stats, mapa_actual, historial):
    wb = openpyxl.Workbook()
    wb.remove(wb.active)

    header_fill = PatternFill(start_color="0B132B", end_color="0B132B", fill_type="solid")
    sub_fill = PatternFill(start_color="1E293B", end_color="1E293B", fill_type="solid")
    gold_fill = PatternFill(start_color="FEF3C7", end_color="FEF3C7", fill_type="solid")
    green_fill = PatternFill(start_color="DCFCE7", end_color="DCFCE7", fill_type="solid")
    thin_border = Border(
        left=Side(style='thin', color='CBD5E1'),
        right=Side(style='thin', color='CBD5E1'),
        top=Side(style='thin', color='CBD5E1'),
        bottom=Side(style='thin', color='CBD5E1')
    )

    dias_dict = historial.get("dias", {})
    reg_verdes = historial.get("registro_verdes", {})

    meses_presentes = set()
    for f_str in dias_dict.keys():
        try:
            d = datetime.strptime(f_str, '%Y-%m-%d').date()
            meses_presentes.add((d.year, d.month))
        except Exception:
            continue

    if not meses_presentes:
        hoy = ahora_art().date()
        meses_presentes.add((hoy.year, hoy.month))

    for anio, mes in sorted(meses_presentes):
        construir_hoja_mensual_ganadoras(wb, anio, mes, dias_dict, reg_verdes)

    ws_res = wb.create_sheet("PARAMETROS_RADAR")
    ws_res["A1"] = "AUDITORÍA REALIDAD: COMPRA EN VERDE (PRE-EXPLOSIÓN) -> MONEDA GANADORA"
    ws_res["A1"].font = Font(name="Arial", size=13, bold=True, color="FFFFFF")
    ws_res["A1"].fill = header_fill
    ws_res.merge_cells("A1:C1")
    ws_res.row_dimensions[1].height = 28

    ws_res["A2"] = f"Actualizado: {ahora_art().strftime('%Y-%m-%d %H:%M ART')}"
    ws_res["A2"].font = Font(name="Arial", size=9, italic=True, color="475569")

    kpis = [
        ("Parámetro Evaluado", "Valor Real", "Interpretación Táctica"),
        ("Total Monedas Detectadas en Verde", stats["total_registradas"], "Universo auditado desde Pre-Explosión"),
        ("Aciertos Confirmados (Llegaron a Ganadoras)", stats["total_aciertos"], "Monedas que entraron al Top Ganadoras 24h"),
        ("En Seguimiento Activo (<= 10 días)", stats["total_pendientes"], "Aún dentro de la ventana de maduración"),
        ("Efectividad Real (Aciertos / Cerradas)", f"{stats['tasa_acierto_pct']}%", "Porcentaje de conversión real a ganadora"),
        ("TIEMPO PROMEDIO DE DEMORA (Verde -> Ganadora)", f"{stats['demora_prom_dias']} días" if stats['demora_prom_dias'] is not None else "En acumulación", "Parámetro clave de paciencia en Spot"),
        ("MEDIANA DE DEMORA (Tiempo Típico)", f"{stats['demora_mediana_dias']} días" if stats['demora_mediana_dias'] is not None else "En acumulación", "Tiempo más frecuente hasta el pump"),
        ("Subida Promedio al Convertirse en Ganadora", f"+{stats['subida_prom_pct']}%", "Rendimiento promedio en el día de explosión")
    ]

    for idx, (k, v, desc) in enumerate(kpis, start=4):
        c1, c2, c3 = ws_res.cell(idx, 1, k), ws_res.cell(idx, 2, v), ws_res.cell(idx, 3, desc)
        for c in (c1, c2, c3):
            c.border = thin_border
            c.font = Font(name="Arial", size=10, bold=(idx in (4, 9, 10)))
            if idx == 4:
                c.fill = sub_fill
                c.font = Font(name="Arial", size=10, bold=True, color="FFFFFF")
            elif idx in (9, 10):
                c.fill = gold_fill

    ws_res.column_dimensions["A"].width = 48
    ws_res.column_dimensions["B"].width = 24
    ws_res.column_dimensions["C"].width = 50

    ws_det = wb.create_sheet("DETALLE_OPERACIONES")
    headers_det = [
        "MONEDA", "CATEGORÍA", "FECHA VERDE", "PRECIO VERDE",
        "ESTADO", "FECHA GANADORA", "PRECIO GANADORA",
        "SUBIDA DESDE VERDE %", "SUBIDA DÍA GANADORA %", "DÍAS DEMORA (VERDE -> WIN)"
    ]
    ws_det.append(headers_det)
    ws_det.row_dimensions[1].height = 24
    for col_idx in range(1, len(headers_det) + 1):
        cell = ws_det.cell(1, col_idx)
        cell.font = Font(name="Arial", size=10, bold=True, color="FFFFFF")
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center", vertical="center")

    todas = sorted(aciertos, key=lambda x: x.get("fecha_ganadora", ""), reverse=True) + sorted(pendientes, key=lambda x: x.get("fecha_verde", ""), reverse=True)
    for r_idx, item in enumerate(todas, start=2):
        es_acierto = (item.get("estado") == "ACIERTO")
        actual_p = mapa_actual.get(item["symbol"], {}).get("precio", 0.0)
        p_verde = float(item.get("precio_verde") or 0.0)
        var_actual = round(((actual_p - p_verde) / p_verde) * 100, 2) if (p_verde > 0 and actual_p > 0) else 0.0

        row_vals = [
            item.get("ticker"),
            "🏆 TOP ORO" if item.get("es_oro") else "🟢 VERDE",
            item.get("fecha_verde"),
            p_verde,
            item.get("estado"),
            item.get("fecha_ganadora") if es_acierto else f"Esperando ({item.get('dias_esperando', 0)}d)",
            item.get("precio_ganadora") if es_acierto else actual_p,
            item.get("subida_real_pct") if es_acierto else var_actual,
            item.get("subida_24h_dia_pct") if es_acierto else 0.0,
            item.get("dias_demora") if es_acierto else item.get("dias_esperando", 0)
        ]
        ws_det.append(row_vals)
        for c_i in range(1, len(headers_det) + 1):
            cell = ws_det.cell(r_idx, c_i)
            cell.border = thin_border
            cell.font = Font(name="Arial", size=9.5)
            if es_acierto:
                cell.fill = green_fill

    widths_det = [14, 15, 15, 16, 19, 20, 18, 22, 23, 27]
    for i, w in enumerate(widths_det, start=1):
        ws_det.column_dimensions[openpyxl.utils.get_column_letter(i)].width = w

    wb.save(EXCEL_AUDITORIA_FILE)


# ==============================================================================
# VISUALIZACIÓN Y TELEGRAM
# ==============================================================================
def generar_grafico_diario(top_10, fecha_str, filename="ganadoras_24h.png"):
    if not top_10:
        return None
    tickers = [x["ticker"] for x in top_10][::-1]
    gains = [x["cambio_24h"] for x in top_10][::-1]
    colores = ["#00e676" if g >= 15 else ("#29b6f6" if g >= 8 else "#ffd600") for g in gains]

    fig, ax = plt.subplots(figsize=(8.5, 4.6), facecolor='#0b132b')
    ax.set_facecolor('#0b132b')

    bars = ax.barh(tickers, gains, color=colores, height=0.58, zorder=3)
    ax.grid(True, axis='x', color='#1e293b', linestyle='--', linewidth=0.8, zorder=1)
    ax.set_axisbelow(True)

    max_g = max(gains) if gains else 10
    ax.set_xlim(0, max_g * 1.25)

    for spine in ['top', 'right', 'bottom']:
        ax.spines[spine].set_visible(False)
    ax.spines['left'].set_color('#334155')

    ax.tick_params(axis='y', colors='white', labelsize=9.5)
    ax.tick_params(axis='x', colors='#94a3b8', labelsize=8.5)

    for bar, g in zip(bars, gains):
        w = bar.get_width()
        y = bar.get_y() + bar.get_height() / 2.0
        ax.text(w + (max_g * 0.02), y, f"+{g:.1f}%", va='center', ha='left', color='white', fontweight='bold', fontsize=9)

    plt.title("TOP 10 MONEDAS GANADORAS (24H) • BINANCE SPOT", loc='left', color='#00e676', fontsize=11, fontweight='bold', pad=14)
    ax.text(0.0, 1.02, f"Cierre: {fecha_str} | Filtro: Spot Activo & Vol >= $1M USDT", transform=ax.transAxes, color='#94a3b8', fontsize=8)

    plt.tight_layout()
    plt.savefig(filename, dpi=300, facecolor=fig.get_facecolor(), edgecolor='none')
    plt.close()
    return filename


def generar_grafico_semanal(reinas, dias_count, filename="ganadoras_semanal.png"):
    if not reinas:
        return None
    top_8 = reinas[:8][::-1]
    labels = [f"{x['ticker']} ({x['veces']}d)" for x in top_8]
    max_gains = [x["gain_max"] for x in top_8]
    colores = ["#ffd700" if x["veces"] >= 3 else ("#00e676" if x["veces"] == 2 else "#38bdf8") for x in top_8]

    fig, ax = plt.subplots(figsize=(8.5, 4.5), facecolor='#0b132b')
    ax.set_facecolor('#0b132b')

    bars = ax.barh(labels, max_gains, color=colores, height=0.56, zorder=3)
    ax.grid(True, axis='x', color='#1e293b', linestyle='--', linewidth=0.8, zorder=1)
    ax.set_axisbelow(True)

    max_v = max(max_gains) if max_gains else 10
    ax.set_xlim(0, max_v * 1.28)

    for spine in ['top', 'right', 'bottom']:
        ax.spines[spine].set_visible(False)
    ax.spines['left'].set_color('#334155')

    ax.tick_params(axis='y', colors='white', labelsize=9.5)
    ax.tick_params(axis='x', colors='#94a3b8', labelsize=8.5)

    for bar, item in zip(bars, top_8):
        w = bar.get_width()
        y = bar.get_y() + bar.get_height() / 2.0
        ax.text(
            w + (max_v * 0.02),
            y,
            f"Máx +{item['gain_max']:.1f}% | {item['veces']}x",
            va='center',
            ha='left',
            color='white',
            fontweight='bold',
            fontsize=8.5
        )

    plt.title(f"CONSOLIDADO SEMANAL GANADORAS ({dias_count} DÍAS)", loc='left', color='#ffd700', fontsize=11, fontweight='bold', pad=14)
    ax.text(0.0, 1.02, "Dorado = 3+ días en Top | Verde = 2 días | Celeste = 1 día", transform=ax.transAxes, color='#94a3b8', fontsize=8)

    plt.tight_layout()
    plt.savefig(filename, dpi=300, facecolor=fig.get_facecolor(), edgecolor='none')
    plt.close()
    return filename


def generar_dictamen_ia(modo, lista_items):
    if not lista_items:
        return ""
    if not GEMINI_API_KEY:
        if modo == "DIARIO":
            return "Lectura 24h: lideran las altcoins con mayor entrada de volumen Spot; vigilar retrocesos limpios en las próximas 48-72h."
        return "Lectura Semanal: las monedas recurrentes concentran la rotación de liquidez Spot; buscar entradas en piso tras corrección."

    client = genai.Client(api_key=GEMINI_API_KEY)
    if modo == "DIARIO":
        resumen = "\n".join([f"- #{x['rank']} {x['ticker']}: +{x['cambio_24h']}% (Vol: ${x['vol_usdt']/1e6:.1f}M)" for x in lista_items[:6]])
        prompt = f"Analista Spot Binance. Dá un dictamen breve (máximo 2 líneas) sobre las Top Ganadoras 24h de hoy:\n{resumen}"
    else:
        resumen = "\n".join([f"- {x['ticker']}: {x['veces']} días ganando, pico +{x['gain_max']}%, retroceso actual {x['retroceso_pct']}%" for x in lista_items[:6]])
        prompt = f"Analista Spot Binance. Dá un dictamen breve (máximo 2 líneas) sobre las ganadoras recurrentes de la semana y oportunidades de rebote:\n{resumen}"

    for mod in MODELOS_GEMINI_GANADORAS:
        try:
            resp = client.models.generate_content(model=mod, contents=prompt)
            if resp and resp.text:
                return resp.text.strip()
        except Exception:
            continue
    return "Lectura Spot: foco en continuidad de volumen y retrocesos ordenados hacia soportes."


def enviar_telegram_foto(image_path, caption_text):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "caption": caption_text[:1020], "parse_mode": "HTML"}
    if TELEGRAM_TOPIC_ID.isdigit():
        payload["message_thread_id"] = int(TELEGRAM_TOPIC_ID)
    try:
        with open(image_path, 'rb') as photo:
            res = requests.post(url, data=payload, files={"photo": photo}, timeout=45).json()
            if not res.get("ok") and "thread not found" in str(res.get("description", "")).lower():
                payload.pop("message_thread_id", None)
                photo.seek(0)
                requests.post(url, data=payload, files={"photo": photo}, timeout=45)
    except Exception as e:
        print(f"❌ Error enviando foto Telegram: {e}")


def enviar_telegram_documento(doc_path, caption_text):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID or not os.path.exists(doc_path):
        return False
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendDocument"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "caption": caption_text[:1020], "parse_mode": "HTML"}
    if TELEGRAM_TOPIC_ID.isdigit():
        payload["message_thread_id"] = int(TELEGRAM_TOPIC_ID)
    try:
        with open(doc_path, 'rb') as doc:
            res = requests.post(url, data=payload, files={"document": doc}, timeout=45).json()
            if not res.get("ok") and "thread not found" in str(res.get("description", "")).lower():
                payload.pop("message_thread_id", None)
                doc.seek(0)
                res = requests.post(url, data=payload, files={"document": doc}, timeout=45).json()
            return bool(res.get("ok"))
    except Exception as e:
        print(f"❌ Error enviando documento Telegram: {e}")
        return False


def enviar_texto_telegram(texto):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    tid = int(TELEGRAM_TOPIC_ID) if TELEGRAM_TOPIC_ID.isdigit() else None
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": texto.strip(), "parse_mode": "HTML", "disable_web_page_preview": True}
    if tid:
        payload["message_thread_id"] = tid
    try:
        res = requests.post(url, json=payload, timeout=30).json()
        if not res.get("ok") and "thread not found" in str(res.get("description", "")).lower():
            payload.pop("message_thread_id", None)
            requests.post(url, json=payload, timeout=30)
    except Exception as e:
        print(f"⚠️ Error enviando texto Telegram: {e}")


def publicar_reporte_diario(top_10, total_dias_guardados):
    fecha_str = ahora_art().strftime('%Y-%m-%d %H:%M ART')
    if not top_10:
        enviar_texto_telegram(f"🏆 <b>MONEDAS GANADORAS (24H)</b>\n📅 <code>{fecha_str}</code>\n\n⏳ <i>Sin monedas con subida >= +3% y liquidez suficiente hoy.</i>")
        return

    fname = generar_grafico_diario(top_10, fecha_str)
    dictamen = generar_dictamen_ia("DIARIO", top_10)

    caption = (
        f"🏆 <b>ETAPA 1 • MONEDAS GANADORAS (24H)</b>\n"
        f"📅 <code>{fecha_str}</code>\n"
        f"💾 <i>Base acumulada: {total_dias_guardados} días registrados</i>"
    )
    if fname:
        enviar_telegram_foto(fname, caption)
        time.sleep(1)

    cuerpo = f"💡 <i>{html.escape(dictamen)}</i>\n\n"
    for item in top_10:
        sim = item["ticker"]
        precio_str = formatear_precio(item["precio"])
        vol_m = item["vol_usdt"] / 1_000_000
        uid = int(time.time() * 1000) + random.randint(1, 9999)
        url_ia = f"{BASE_URL_NETLIFY}/?coin={sim}&price={item['precio']}&change={item['cambio_24h']}&high={item['high']}&low={item['low']}&v={sim}_{uid}"
        url_trade = f"https://www.binance.com/es/trade/{sim}_USDT"

        medalla = "🥇" if item["rank"] == 1 else ("🥈" if item["rank"] == 2 else ("🥉" if item["rank"] == 3 else f"#{item['rank']}"))
        cuerpo += (
            f"{medalla} <b>{sim}</b> (<b>+{item['cambio_24h']:.1f}%</b>) | <code>{precio_str}</code> | Vol: ${vol_m:.1f}M\n"
            f"   └ <a href=\"{html.escape(url_ia)}\">📊 Resumen IA</a> | <a href=\"{html.escape(url_trade)}\">🔶 Tradear</a>\n\n"
        )

    enviar_texto_telegram(cuerpo)


def publicar_excel_diario(stats, fecha_cierre_str):
    """Envía diariamente la planilla Excel actualizada al cierre de cada jornada."""
    caption = (
        f"📊 <b>Planilla Excel Diaria Actualizada (Cierre {fecha_cierre_str}):</b> "
        f"Bloques Diarios (Base 0% vs Actual) + Resumen Semanal + Auditoría Verde ➔ Ganadoras ({stats['total_aciertos']} aciertos)."
    )
    return enviar_telegram_documento(EXCEL_AUDITORIA_FILE, caption)


def publicar_reporte_semanal_y_auditoria(reinas, segunda_ola, dias_count, aciertos, stats):
    fecha_str = ahora_art().strftime('%Y-%m-%d %H:%M ART')
    if reinas:
        fname = generar_grafico_semanal(reinas, dias_count)
        dictamen = generar_dictamen_ia("SEMANAL", reinas)

        caption = (
            f"👑 <b>ETAPA 2 • CONSOLIDADO SEMANAL GANADORAS</b>\n"
            f"📅 <code>{fecha_str}</code> | Ventana: <b>{dias_count} días</b>"
        )
        if fname:
            enviar_telegram_foto(fname, caption)
            time.sleep(1)

        cuerpo = f"💡 <i>{html.escape(dictamen)}</i>\n\n"
        cuerpo += "📊 <b>RANKING DE RECURRENCIA SEMANAL:</b>\n"
        for idx, item in enumerate(reinas[:8], start=1):
            sim = item["ticker"]
            precio_str = formatear_precio(item["precio_actual"])
            cuerpo += (
                f"{idx}. <b>{sim}</b> — <b>{item['veces']}x</b> en Top | Máx: <b>+{item['gain_max']:.1f}%</b> | Actual: <code>{precio_str}</code> ({item['retroceso_pct']:+.1f}% vs pico)\n"
            )

        cuerpo += "\n🎯 <b>OPORTUNIDADES SEGUNDA OLA (Ganadora Semanal en Retroceso):</b>\n"
        if segunda_ola:
            for item in segunda_ola:
                sim = item["ticker"]
                precio_str = formatear_precio(item["precio_actual"])
                url_trade = f"https://www.binance.com/es/trade/{sim}_USDT"
                cuerpo += (
                    f"• <b>{sim}</b> ({item['veces']}d en Top) | Retroceso: <b>{item['retroceso_pct']:.1f}%</b> | Rango hoy: {item['pos_rango_hoy']:.0f}% | <code>{precio_str}</code> "
                    f"(<a href=\"{html.escape(url_trade)}\">🔶 Tradear</a>)\n"
                )
        else:
            cuerpo += "<i>Sin ganadoras semanales en zona óptima de retroceso (-6% a -22% en piso) hoy.</i>\n"

        enviar_texto_telegram(cuerpo)
        time.sleep(1.5)

    demora_txt = f"{stats['demora_prom_dias']} días (Mediana: {stats['demora_mediana_dias']}d)" if stats["demora_prom_dias"] is not None else "En acumulación de datos"
    msg_auditoria = (
        f"📐 <b>ETAPA 3 • AUDITORÍA REALIDAD (VERDE ➔ GANADORA)</b>\n"
        f"📅 <code>{fecha_str}</code>\n\n"
        f"• Monedas rastreadas desde Verde: <b>{stats['total_registradas']}</b>\n"
        f"• Convertidas en Ganadoras (Aciertos): <b>{stats['total_aciertos']}</b>\n"
        f"• En ventana de espera activa: <b>{stats['total_pendientes']}</b>\n"
        f"• ⏱️ <b>Parámetro de demora Verde ➔ Ganadora:</b> <code>{demora_txt}</code>\n"
        f"• 📈 <b>Subida promedio al ganar:</b> <code>+{stats['subida_prom_pct']}%</code>\n\n"
    )
    if aciertos:
        msg_auditoria += "✅ <b>Últimos aciertos confirmados (Verde ➔ Top Ganadoras):</b>\n"
        for a in sorted(aciertos, key=lambda x: x.get("fecha_ganadora", ""), reverse=True)[:6]:
            tag = "🏆" if a.get("es_oro") else "🟢"
            msg_auditoria += (
                f"{tag} <b>{a['ticker']}</b>: Verde <code>{a['fecha_verde'][5:]}</code> ➔ Ganó <code>{a['fecha_ganadora'][5:]}</code> "
                f"(<b>{a['dias_demora']}d</b> | <b>+{a['subida_24h_dia_pct']:.1f}%</b>)\n"
            )
    enviar_texto_telegram(msg_auditoria)
    time.sleep(1)
    enviar_telegram_documento(
        EXCEL_AUDITORIA_FILE,
        f"📊 <b>Planilla Excel Actualizada:</b> Bloques Diarios (Base 0% vs Actual) + Resumen Semanal + Auditoría Verde ➔ Ganadoras ({stats['total_aciertos']} aciertos)."
    )


if __name__ == "__main__":
    print(f"🏆 EJECUTANDO BOT MONEDAS GANADORAS + AUDITORÍA VERDE (3 ETAPAS) - {ahora_art().strftime('%Y-%m-%d %H:%M:%S')} ART")
    session = crear_sesion_binance()
    simbolos_activos = obtener_simbolos_spot_activos(session)
    datos = obtener_datos_binance(session)

    if datos and simbolos_activos:
        historial = cargar_historial_ganadoras()

        top_10_dia, mapa_actual = ejecutar_etapa_1_diaria(datos, simbolos_activos, historial)
        total_dias = len(historial.get("dias", {}))
        publicar_reporte_diario(top_10_dia, total_dias)

        aciertos, pendientes, stats = ejecutar_etapa_3_auditoria_verde(historial, mapa_actual)

        hoy = ahora_art()
        hoy_str = hoy.strftime('%Y-%m-%d')
        ayer_str = (hoy - timedelta(days=1)).strftime('%Y-%m-%d')
        forzar_semanal = os.getenv("FORZAR_SEMANAL", "").strip() == "1"
        es_ejecucion_manual = (os.getenv("GITHUB_EVENT_NAME") == "workflow_dispatch")
        es_domingo = (hoy.weekday() == 6)

        reinas, segunda_ola, dias_count = ejecutar_etapa_2_semanal(historial, mapa_actual)
        sincronizar_con_radar_pre_explosion(segunda_ola)

        excel_ya_enviado_en_ciclo = False
        if (es_domingo or forzar_semanal or total_dias % 7 == 0) and historial.get("ultimo_reporte_semanal") != hoy_str and dias_count >= 1:
            time.sleep(2)
            publicar_reporte_semanal_y_auditoria(reinas, segunda_ola, dias_count, aciertos, stats)
            historial["ultimo_reporte_semanal"] = hoy_str
            historial["ultimo_envio_excel"] = hoy_str
            guardar_historial_ganadoras(historial)
            excel_ya_enviado_en_ciclo = True

        if not excel_ya_enviado_en_ciclo:
            ultimo_excel = historial.get("ultimo_envio_excel", "")
            es_cierre_diario = (hoy.hour == 23 and hoy.minute >= 30 and ultimo_excel != hoy_str)
            es_cierre_recuperado = (hoy.hour <= 2 and ultimo_excel != ayer_str)

            if es_cierre_diario or es_cierre_recuperado or es_ejecucion_manual:
                fecha_cierre_label = ayer_str if (es_cierre_recuperado and not es_cierre_diario) else hoy_str
                time.sleep(1.5)
                if publicar_excel_diario(stats, fecha_cierre_label):
                    if not es_ejecucion_manual:
                        historial["ultimo_envio_excel"] = fecha_cierre_label
                    guardar_historial_ganadoras(historial)
    else:
        print("❌ ERROR: Sin datos o sin símbolos activos de Binance.")

# FIN BOT MONEDAS GANADORAS V2
