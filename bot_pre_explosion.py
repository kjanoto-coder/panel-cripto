#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
BOT PRE-EXPLOSIÓN (AUDITORÍA MAESTRA UNIFICADA + TRAZABILIDAD DE PATRONES + CRUCE GANADORAS + TELEGRAM TOPICS)
Versión: 2026-11-28.2 (6 pestañas: incluye $ Mínimo, secuencia multi-día de colores, lateralización, prob. rebote y cruce con AUDITORIA_VERDE_GANADORAS.xlsx)
"""

import os
import re
import glob
import json
import time
import logging
from datetime import datetime, timedelta, timezone

import requests
import openpyxl
from openpyxl.styles import Font, PatternFill, Border, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.chart import BarChart, Reference

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("bot_pre_explosion")

# ==============================================================================
# 1. CONFIGURACIÓN GENERAL Y VARIABLES DE ENTORNO
# ==============================================================================
TELEGRAM_TOKEN = (
    os.getenv("TELEGRAM_TOKEN", "").strip()
    or os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
)
TELEGRAM_CHAT_ID = (
    os.getenv("TELEGRAM_CHAT_ID", "").strip()
    or os.getenv("CHAT_ID", "").strip()
)
TOPIC_ID_PRE_EXPLOSION = (
    os.getenv("TOPIC_ID_PRE_EXPLOSION", "").strip()
    or os.getenv("TELEGRAM_MESSAGE_THREAD_ID", "").strip()
)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()

ARCHIVO_EXCEL_MAESTRO = "AUDITORIA_PRE_EXPLOSION.xlsx"
ARCHIVO_EXCEL_CAZADOR = "HISTORICO_CAZADOR_TACTICO.xlsx"
ARCHIVO_EXCEL_GANADORAS = "AUDITORIA_VERDE_GANADORAS.xlsx"
ARCHIVO_ESTADO_JSON = "estado_pre_explosion.json"

TZ_ART = timezone(timedelta(hours=-3))

EXCL_BASE = {
    "USDT", "USDC", "FDUSD", "DAI", "TUSD", "USDP", "EUR", "GBP", "AUD", "BRL", "ARS", "TRY", "BUSD",
    "USD1", "AEUR", "EURI", "USDE", "RLUSD", "RWUSD", "XUSD", "BFUSD", "U", "USDG", "USDS", "PYUSD",
    "BTC", "ETH", "SOL", "ADA", "XRP", "DOGE", "TRX", "SHIB", "AVAX", "LINK", "BNB", "DOT", "NEAR", "SUI", "PEPE"
}

PRIORIDAD_COLOR = {"VERDE": 1, "AMARILLO": 2, "ROJO": 3}

BINANCE_BASES = [
    "https://api.binance.com",
    "https://api1.binance.com",
    "https://api2.binance.com",
    "https://api3.binance.com",
    "https://data-api.binance.vision"
]


# ==============================================================================
# 2. UTILIDADES DE PARSEO Y NORMALIZACIÓN
# ==============================================================================
def ahora_art() -> datetime:
    return datetime.now(TZ_ART)


def es_simbolo_valido(base: str) -> bool:
    if not base or base in EXCL_BASE:
        return False
    if not re.match(r"^[A-Z0-9]{2,12}$", base):
        return False
    if base.endswith("B"):
        return False
    return not any(x in base for x in ("UP", "DOWN", "BULL", "BEAR"))


def norm_sem(val) -> str:
    s = str(val or "").upper()
    if "ORO" in s:
        return "🏆 TOP ORO"
    if "ROJ" in s:
        return "🔴 ROJO"
    if "AMAR" in s:
        return "🟡 AMARILLO"
    return "🟢 VERDE"


def sem_cod(et) -> str:
    s = str(et or "").upper()
    if "ROJ" in s:
        return "ROJO"
    if "AMAR" in s:
        return "AMARILLO"
    return "VERDE"


def sem_emoji_corto(et) -> str:
    s = str(et or "").upper()
    if "ORO" in s:
        return "🏆"
    if "ROJ" in s:
        return "🔴"
    if "AMAR" in s:
        return "🟡"
    return "🟢"


def parse_ia(val):
    s = str(val or "").replace("%", "").strip()
    if s in ("", "-", "None", "nan"):
        return None
    try:
        v = float(s)
        return round(v / 100.0, 4) if v > 1.0 else round(v, 4)
    except Exception:
        return None


def parse_ba(val):
    s = str(val or "").replace("x", "").strip()
    if s in ("", "-", "None", "nan"):
        return None
    try:
        return round(float(s), 2)
    except Exception:
        return None


def fmt_precio(p: float) -> str:
    if p <= 0:
        return "$0.00"
    if p >= 10:
        return f"${p:,.2f}"
    if p >= 1:
        return f"${p:,.4f}"
    if p >= 0.01:
        return f"${p:,.5f}"
    return f"${p:,.8f}".rstrip("0").rstrip(".")


def buscar_archivo_repo(nombre_archivo: str) -> str:
    if os.path.exists(nombre_archivo):
        return nombre_archivo
    encontrados = glob.glob(f"**/{nombre_archivo}", recursive=True)
    return encontrados[0] if encontrados else ""


# ==============================================================================
# 3. CONEXIÓN RESILIENTE A BINANCE SPOT (SIN APALANCAMIENTO)
# ==============================================================================
def binance_get(path: str, params=None, timeout: int = 12):
    for base in BINANCE_BASES:
        try:
            r = requests.get(f"{base}{path}", params=params, timeout=timeout)
            if r.status_code == 200:
                return r.json()
        except Exception:
            continue
    return None


def obtener_tickers_24h() -> dict:
    data = binance_get("/api/v3/ticker/24hr")
    out = {}
    if not isinstance(data, list):
        return out
    for t in data:
        sym = t.get("symbol", "")
        if not sym.endswith("USDT"):
            continue
        base = sym[:-4]
        if not es_simbolo_valido(base):
            continue
        try:
            price = float(t.get("lastPrice", 0))
            high = float(t.get("highPrice", 0))
            low = float(t.get("lowPrice", 0))
            pct = float(t.get("priceChangePercent", 0))
            qvol = float(t.get("quoteVolume", 0))
            if price > 0 and qvol >= 100_000:
                out[base] = {
                    "symbol": sym,
                    "base": base,
                    "price": price,
                    "high": high,
                    "low": low,
                    "pct_24h": pct,
                    "quote_vol": qvol,
                }
        except Exception:
            continue
    return out


def obtener_klines_1h(symbol: str, limit: int = 48):
    data = binance_get("/api/v3/klines", params={"symbol": symbol, "interval": "1h", "limit": limit})
    return data if isinstance(data, list) else []


def obtener_orderbook_ratio(symbol: str, limit: int = 20):
    ob = binance_get("/api/v3/depth", params={"symbol": symbol, "limit": limit})
    if not isinstance(ob, dict):
        return None
    try:
        bids = sum(float(p) * float(q) for p, q in ob.get("bids", []))
        asks = sum(float(p) * float(q) for p, q in ob.get("asks", []))
        if asks > 0:
            return round(bids / asks, 2)
    except Exception:
        pass
    return None


def calcular_metricas_tecnicas(symbol: str, ticker: dict) -> dict:
    kl = obtener_klines_1h(symbol, limit=48)
    if len(kl) < 12:
        return {}
    closes = [float(k[4]) for k in kl]
    highs = [float(k[2]) for k in kl]
    lows = [float(k[3]) for k in kl]
    vols = [float(k[7]) for k in kl]

    p_act = closes[-1]
    p_1h = closes[-2] if len(closes) >= 2 else p_act
    p_4h = closes[-5] if len(closes) >= 5 else closes[0]

    var_1h = ((p_act - p_1h) / p_1h) * 100.0 if p_1h > 0 else 0.0
    var_4h = ((p_act - p_4h) / p_4h) * 100.0 if p_4h > 0 else 0.0

    vol_prom = sum(vols[:-1]) / max(1, len(vols) - 1)
    vol_ratio = round(vols[-1] / vol_prom, 2) if vol_prom > 0 else 1.0

    hi_48 = max(highs)
    lo_48 = min(lows)
    fib_pos = round((hi_48 - p_act) / (hi_48 - lo_48), 2) if hi_48 > lo_48 else 0.5
    fib_1618 = round(hi_48 + 0.618 * (hi_48 - lo_48), 6) if hi_48 > lo_48 else p_act

    # Amplitud de lateralización en últimas 12 horas
    hi_12 = max(highs[-12:])
    lo_12 = min(lows[-12:])
    rango_12h_pct = round(((hi_12 - lo_12) / lo_12) * 100.0, 2) if lo_12 > 0 else 0.0

    ba_ratio = obtener_orderbook_ratio(symbol, limit=20)

    return {
        "var_1h": round(var_1h, 2),
        "var_4h": round(var_4h, 2),
        "vol_ratio": vol_ratio,
        "fib_pos": fib_pos,
        "fib_1618": fib_1618,
        "ba_ratio": ba_ratio,
        "hi_48": hi_48,
        "lo_48": lo_48,
        "rango_12h_pct": rango_12h_pct,
    }


# ==============================================================================
# 4. MOTOR DE HIDRATACIÓN HISTÓRICA + CRUCE GANADORAS + TRAZABILIDAD
# ==============================================================================
class RegistroMaestro:
    def __init__(self):
        self.eventos = {}  # clave: "YYYY-MM-DD|MONEDA"

    def upsert(self, ev: dict):
        fecha = str(ev.get("Fecha") or "")[:10]
        mon = str(ev.get("Moneda") or "").strip().upper()
        if mon.endswith("USDT"):
            mon = mon[:-4]
        if not fecha or not es_simbolo_valido(mon):
            return

        key = f"{fecha}|{mon}"
        hora = str(ev.get("Hora") or "S/H").strip()
        if hora in ("", "00:00", "None", "nan"):
            hora = "S/H"

        s_ini = norm_sem(ev.get("Semaforo_Ini"))
        s_max = norm_sem(ev.get("Semaforo_Max") or s_ini)
        p_ent = float(ev.get("Precio_Entrada") or 0.0)
        p_pico = max(float(ev.get("Precio_Pico") or 0.0), p_ent)
        p_min_raw = float(ev.get("Precio_Min") or 0.0)
        p_min = p_min_raw if p_min_raw > 0 else p_ent

        if key not in self.eventos:
            self.eventos[key] = {
                "Fecha": fecha,
                "Hora": hora,
                "Moneda": mon,
                "Semaforo_Ini": s_ini,
                "Semaforo_Max": s_max,
                "Escalada": str(ev.get("Escalada") or ("Directo 🔴" if "ROJO" in s_ini else "-")).strip(),
                "IA_Pct": ev.get("IA_Pct"),
                "Fib_Zona": ev.get("Fib_Zona"),
                "Bids_Asks": ev.get("Bids_Asks"),
                "Precio_Entrada": p_ent,
                "Precio_Min": p_min,
                "Precio_Pico": p_pico,
                "Estado": str(ev.get("Estado") or "⏳ EN SEGUIMIENTO").strip(),
                "Fecha_Ganadora": str(ev.get("Fecha_Ganadora") or "-").strip(),
                "Precio_Final": float(ev.get("Precio_Final") or p_ent),
                "Tiempo_Ganadora_Txt": str(ev.get("Tiempo_Ganadora_Txt") or "En seguimiento").strip(),
                "Dias_Dec": ev.get("Dias_Dec"),
                "Fib_1618": str(ev.get("Fib_1618") or "-").strip(),
                "Confluencia": str(ev.get("Confluencia") or "Solo Pre-Explosión").strip(),
                "Origen": str(ev.get("Origen") or "Bot Pre-Explosión").strip(),
            }
        else:
            cur = self.eventos[key]
            if hora != "S/H" and (cur["Hora"] in ("", "S/H", "00:00") or hora < cur["Hora"]):
                cur["Hora"] = hora

            c_old = sem_cod(cur["Semaforo_Max"])
            c_new = sem_cod(s_max)
            if PRIORIDAD_COLOR[c_new] > PRIORIDAD_COLOR[c_old]:
                cur["Semaforo_Max"] = s_max
                if cur["Escalada"] in ("-", ""):
                    cur["Escalada"] = f"{cur['Semaforo_Ini'][:2]}➔{s_max[:2]}"

            if "ORO" in s_ini:
                cur["Semaforo_Ini"] = "🏆 TOP ORO"

            if ev.get("Escalada") not in (None, "", "-") and cur["Escalada"] in ("-", ""):
                cur["Escalada"] = str(ev["Escalada"]).strip()

            if ev.get("IA_Pct") is not None and (cur["IA_Pct"] is None or ev["IA_Pct"] > float(cur["IA_Pct"])):
                cur["IA_Pct"] = ev["IA_Pct"]

            if ev.get("Fib_Zona") is not None and cur["Fib_Zona"] is None:
                cur["Fib_Zona"] = ev["Fib_Zona"]

            if ev.get("Bids_Asks") is not None:
                cur["Bids_Asks"] = ev["Bids_Asks"]

            if cur["Precio_Entrada"] <= 0 and p_ent > 0:
                cur["Precio_Entrada"] = p_ent

            if p_min > 0 and (cur.get("Precio_Min", 0) <= 0 or p_min < cur["Precio_Min"]):
                cur["Precio_Min"] = p_min

            if p_pico > cur["Precio_Pico"]:
                cur["Precio_Pico"] = p_pico

            if "GANADORA" in str(ev.get("Estado", "")).upper():
                cur["Estado"] = "🏆 GANADORA"
                if ev.get("Fecha_Ganadora") not in (None, "", "-"):
                    cur["Fecha_Ganadora"] = str(ev["Fecha_Ganadora"])[:10]
                if float(ev.get("Precio_Final") or 0) > 0:
                    cur["Precio_Final"] = float(ev["Precio_Final"])
                if ev.get("Tiempo_Ganadora_Txt") not in (None, "", "-", "En seguimiento"):
                    cur["Tiempo_Ganadora_Txt"] = str(ev["Tiempo_Ganadora_Txt"])
                if ev.get("Dias_Dec") is not None:
                    cur["Dias_Dec"] = ev["Dias_Dec"]
            elif cur["Estado"] != "🏆 GANADORA" and float(ev.get("Precio_Final") or 0) > 0:
                cur["Precio_Final"] = float(ev["Precio_Final"])

            if ev.get("Fib_1618") not in (None, "", "-") and cur["Fib_1618"] in ("-", ""):
                cur["Fib_1618"] = str(ev["Fib_1618"]).strip()

            if "SÍ" in str(ev.get("Confluencia", "")):
                cur["Confluencia"] = "SÍ (Cazador + Pre-Exp)"
                cur["Origen"] = "Cazador + Pre-Explosión"

    def hidratar_desde_excel_maestro(self, filepath: str):
        path = buscar_archivo_repo(filepath)
        if not path:
            log.warning(f"No se encontró {filepath}; se iniciará desde cero si no hay respaldo.")
            return
        try:
            wb = openpyxl.load_workbook(path, data_only=True)
            if "3_REGISTRO_MAESTRO" not in wb.sheetnames:
                return
            ws = wb["3_REGISTRO_MAESTRO"]
            cargadas = 0
            for r in range(5, ws.max_row + 1):
                f = str(ws.cell(r, 2).value or "")[:10]
                m = str(ws.cell(r, 6).value or "").strip().upper()
                if not f or not m:
                    continue
                p_ent = float(ws.cell(r, 14).value or 0.0) if isinstance(ws.cell(r, 14).value, (int, float)) else 0.0
                p_pico = float(ws.cell(r, 15).value or 0.0) if isinstance(ws.cell(r, 15).value, (int, float)) else 0.0
                p_fin = float(ws.cell(r, 19).value or 0.0) if isinstance(ws.cell(r, 19).value, (int, float)) else 0.0
                p_min_est = min([x for x in (p_ent, p_fin) if x > 0], default=p_ent)

                self.upsert({
                    "Fecha": f,
                    "Hora": ws.cell(r, 5).value,
                    "Moneda": m,
                    "Semaforo_Ini": ws.cell(r, 7).value,
                    "Semaforo_Max": ws.cell(r, 8).value,
                    "Escalada": ws.cell(r, 9).value,
                    "IA_Pct": parse_ia(ws.cell(r, 11).value),
                    "Fib_Zona": float(ws.cell(r, 12).value) if isinstance(ws.cell(r, 12).value, (int, float)) else None,
                    "Bids_Asks": parse_ba(ws.cell(r, 13).value),
                    "Precio_Entrada": p_ent,
                    "Precio_Min": p_min_est,
                    "Precio_Pico": p_pico,
                    "Estado": ws.cell(r, 17).value,
                    "Fecha_Ganadora": ws.cell(r, 18).value,
                    "Precio_Final": p_fin,
                    "Tiempo_Ganadora_Txt": ws.cell(r, 21).value,
                    "Dias_Dec": float(ws.cell(r, 22).value) if isinstance(ws.cell(r, 22).value, (int, float)) else None,
                    "Fib_1618": ws.cell(r, 23).value,
                    "Confluencia": ws.cell(r, 24).value,
                    "Origen": ws.cell(r, 25).value,
                })
                cargadas += 1
            log.info(f"Hidratado desde {path}: {cargadas} filas leídas (total acumulado: {len(self.eventos)}).")
        except Exception as e:
            log.error(f"Error hidratando {path}: {e}")

    def hidratar_desde_json_estado(self, filepath: str):
        if not os.path.exists(filepath):
            return
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                for ev in data.values():
                    if isinstance(ev, dict):
                        self.upsert(ev)
        except Exception as e:
            log.error(f"Error leyendo {filepath}: {e}")

    def guardar_json_estado(self, filepath: str):
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(self.eventos, f, ensure_ascii=False, indent=2)
        except Exception as e:
            log.error(f"Error guardando {filepath}: {e}")

    def leer_cazador_activo(self) -> set:
        activos = set()
        path = buscar_archivo_repo(ARCHIVO_EXCEL_CAZADOR)
        if not path:
            return activos
        try:
            wb = openpyxl.load_workbook(path, data_only=True)
            if "3_REGISTRO_MAESTRO" not in wb.sheetnames:
                return activos
            ws = wb["3_REGISTRO_MAESTRO"]
            hoy_str = ahora_art().strftime("%Y-%m-%d")
            ayer_str = (ahora_art() - timedelta(days=1)).strftime("%Y-%m-%d")
            for r in range(5, ws.max_row + 1):
                f_c = str(ws.cell(r, 2).value or "")[:10]
                m_c = str(ws.cell(r, 6).value or "").strip().upper()
                if m_c and f_c in (hoy_str, ayer_str):
                    activos.add(m_c)
        except Exception:
            pass
        return activos

    def leer_ganadoras_otro_bot(self) -> dict:
        """
        Lee AUDITORIA_VERDE_GANADORAS.xlsx (del bot de Monedas Ganadoras) para cruzar
        qué monedas de nuestro radar terminaron en el ranking de ganadoras diarias y en qué fechas.
        """
        ganadoras_map = {}  # mon -> {"veces": int, "fechas": sorted_list, "mejor_subida": float}
        path = buscar_archivo_repo(ARCHIVO_EXCEL_GANADORAS)
        if not path:
            log.info(f"No se encontró {ARCHIVO_EXCEL_GANADORAS} en el repo; cruce de ganadoras omitido.")
            return ganadoras_map
        try:
            wb = openpyxl.load_workbook(path, data_only=True)
            for sname in wb.sheetnames:
                ws = wb[sname]
                col_mon, col_fec, col_pct = None, None, None
                header_row = None
                for r in range(1, min(10, ws.max_row + 1)):
                    for c in range(1, ws.max_column + 1):
                        val = str(ws.cell(r, c).value or "").strip().upper()
                        if val in ("MONEDA", "SYMBOL", "PAR", "TICKER"):
                            col_mon = c
                            header_row = r
                        elif val in ("FECHA", "DATE", "DÍA", "DIA"):
                            col_fec = c
                        elif any(k in val for k in ("SUBIDA", "GANANCIA", "VAR", "PICO", "%")):
                            if col_pct is None:
                                col_pct = c
                    if col_mon and header_row:
                        break
                if not col_mon or not header_row:
                    continue

                for r in range(header_row + 1, ws.max_row + 1):
                    raw_m = str(ws.cell(r, col_mon).value or "").strip().upper()
                    if raw_m.endswith("USDT"):
                        raw_m = raw_m[:-4]
                    if not es_simbolo_valido(raw_m):
                        continue
                    f_val = str(ws.cell(r, col_fec).value or "")[:10] if col_fec else ""
                    pct_val = 0.0
                    if col_pct and isinstance(ws.cell(r, col_pct).value, (int, float)):
                        pct_val = float(ws.cell(r, col_pct).value)

                    info = ganadoras_map.setdefault(raw_m, {"veces": 0, "fechas": set(), "mejor_subida": 0.0})
                    info["veces"] += 1
                    if f_val and len(f_val) == 10:
                        info["fechas"].add(f_val)
                    if pct_val > info["mejor_subida"]:
                        info["mejor_subida"] = pct_val
                if ganadoras_map:
                    break
            for info in ganadoras_map.values():
                info["fechas"] = sorted(info["fechas"])
            log.info(f"Cruce con {path}: {len(ganadoras_map)} monedas ganadoras cargadas.")
        except Exception as e:
            log.warning(f"No se pudo leer {path}: {e}")
        return ganadoras_map

    def actualizar_precios_y_ganadoras(self, tickers: dict, fecha_hoy: str):
        """
        Actualiza Precio_Final, Precio_Pico y Precio_Min de señales activas y marca 🏆 GANADORA
        cuando una moneda supera +12% desde su Precio_Entrada dentro de una ventana de 7 días.
        """
        for r in self.eventos.values():
            mon = r["Moneda"]
            if mon not in tickers:
                continue
            p_live = tickers[mon]["price"]
            p_high = max(p_live, tickers[mon]["high"])
            p_low = min(p_live, tickers[mon]["low"]) if tickers[mon]["low"] > 0 else p_live
            p_ent = float(r.get("Precio_Entrada") or 0.0)

            if p_ent <= 0:
                r["Precio_Entrada"] = p_live
                p_ent = p_live

            if p_high > float(r.get("Precio_Pico") or 0.0):
                r["Precio_Pico"] = p_high

            cur_min = float(r.get("Precio_Min") or 0.0)
            if cur_min <= 0 or p_low < cur_min:
                r["Precio_Min"] = p_low

            if r["Estado"] != "🏆 GANADORA":
                r["Precio_Final"] = p_live
                try:
                    d_diff = (datetime.strptime(fecha_hoy, "%Y-%m-%d") - datetime.strptime(r["Fecha"], "%Y-%m-%d")).days
                except Exception:
                    d_diff = 0
                if 0 <= d_diff <= 7 and p_ent > 0:
                    gain_pico = (r["Precio_Pico"] - p_ent) / p_ent
                    if gain_pico >= 0.12:
                        r["Estado"] = "🏆 GANADORA"
                        r["Fecha_Ganadora"] = fecha_hoy
                        r["Precio_Final"] = max(p_live, r["Precio_Pico"])
                        r["Dias_Dec"] = float(d_diff)
                        r["Tiempo_Ganadora_Txt"] = "Mismo día" if d_diff == 0 else f"{d_diff}d"

    def construir_trazabilidad_monedas(self, tickers: dict, ganadoras_ext: dict) -> list:
        """
        Construye el perfil longitudinal completo de cada moneda única que pasó por el radar:
        - Secuencia cronológica de colores (ej. 🟢 ➔ 🟡 ➔ 🔴) y si escaló hacia explosión
        - Precio Base (1ra aparición), Precio Mínimo, Precio Máximo y Precio Actual
        - Detección de Lateralización, Posición en Rango y Probabilidad de Nueva Subida (%)
        - Cruce con el bot de Monedas Ganadoras y días de anticipación
        """
        por_moneda = {}
        for ev in sorted(self.eventos.values(), key=lambda x: (x["Fecha"], x["Hora"])):
            por_moneda.setdefault(ev["Moneda"], []).append(ev)

        resumen_monedas = []
        for mon, lista in por_moneda.items():
            primera = lista[0]
            ultima = lista[-1]

            # Secuencia deduplicada de semáforos
            seq_emojis = []
            seq_cods = []
            fecha_verde = None
            fecha_rojo = None
            for item in lista:
                em = sem_emoji_corto(item["Semaforo_Ini"])
                cd = sem_cod(item["Semaforo_Ini"])
                if not seq_emojis or seq_emojis[-1] != em:
                    seq_emojis.append(em)
                    seq_cods.append(cd)
                if cd == "VERDE" and fecha_verde is None:
                    fecha_verde = item["Fecha"]
                if cd == "ROJO" and fecha_rojo is None:
                    fecha_rojo = item["Fecha"]
                if sem_cod(item["Semaforo_Max"]) == "ROJO" and fecha_rojo is None:
                    fecha_rojo = item["Fecha"]

            secuencia_txt = " ➔ ".join(seq_emojis)
            cambio_color = "SÍ" if len(seq_emojis) > 1 else "NO"

            # Detectar si cumplió escalada ascendente (Verde->Amarillo, Amarillo->Rojo, Verde->Rojo)
            escalo_alcista = False
            for i in range(len(seq_cods) - 1):
                if PRIORIDAD_COLOR[seq_cods[i + 1]] > PRIORIDAD_COLOR[seq_cods[i]]:
                    escalo_alcista = True
                    break

            dias_a_rojo = "-"
            if fecha_verde and fecha_rojo and fecha_rojo >= fecha_verde:
                try:
                    d_vr = (datetime.strptime(fecha_rojo, "%Y-%m-%d") - datetime.strptime(fecha_verde, "%Y-%m-%d")).days
                    dias_a_rojo = f"{d_vr}d"
                except Exception:
                    pass

            p_base = float(primera.get("Precio_Entrada") or 0.0)
            p_max = max(float(x.get("Precio_Pico") or 0.0) for x in lista)
            mins_validos = [float(x.get("Precio_Min") or x.get("Precio_Entrada") or 0.0) for x in lista if float(x.get("Precio_Min") or x.get("Precio_Entrada") or 0.0) > 0]
            p_min = min(mins_validos) if mins_validos else p_base

            p_actual = tickers[mon]["price"] if mon in tickers else float(ultima.get("Precio_Final") or p_base)
            if p_actual > p_max:
                p_max = p_actual
            if p_actual > 0 and (p_min <= 0 or p_actual < p_min):
                p_min = p_actual

            subida_max_pct = ((p_max - p_base) / p_base) if p_base > 0 else 0.0
            caida_min_pct = ((p_min - p_base) / p_base) if p_base > 0 else 0.0
            var_actual_base = ((p_actual - p_base) / p_base) if p_base > 0 else 0.0

            rango_total = p_max - p_min
            pos_rango = ((p_actual - p_min) / rango_total) if rango_total > 0 else 0.5
            pos_rango = max(0.0, min(1.0, pos_rango))

            # Precio estimado de lateralización (promedio entre último cierre, última entrada y punto medio reciente)
            p_lat = round((p_actual + float(ultima.get("Precio_Entrada") or p_actual)) / 2.0, 6)

            # Diagnóstico de estructura y probabilidad de nueva subida
            ba_ult = float(ultima.get("Bids_Asks") or 1.0)
            pct_24h_live = tickers[mon]["pct_24h"] if mon in tickers else 0.0
            wins_internas = sum(1 for x in lista if x["Estado"] == "🏆 GANADORA")

            prob_rebote = 0.40
            if pos_rango <= 0.28 and abs(pct_24h_live) <= 4.5:
                estructura = "🔄 LATERALIZANDO EN PISO"
                prob_rebote += 0.25
            elif 0.28 < pos_rango <= 0.55 and p_actual >= p_base * 0.96 and abs(pct_24h_live) <= 5.0:
                estructura = "🧱 ACUMULANDO SOBRE BASE"
                prob_rebote += 0.22
            elif pos_rango >= 0.78 and pct_24h_live > 4.0:
                estructura = "🚀 EN EXPANSIÓN ALCISTA"
                prob_rebote += 0.15
            elif subida_max_pct >= 0.25 and pos_rango < 0.35 and pct_24h_live < -3.0:
                estructura = "⚠️ AGOTADA TRAS PICO"
                prob_rebote -= 0.12
            else:
                estructura = "📊 RANGO INTERMEDIO"
                prob_rebote += 0.08

            if ba_ult >= 1.5:
                prob_rebote += 0.14
            elif ba_ult >= 1.2:
                prob_rebote += 0.07
            if escalo_alcista:
                prob_rebote += 0.08
            if wins_internas > 0:
                prob_rebote += 0.06

            prob_rebote = round(max(0.10, min(0.96, prob_rebote)), 2)

            # Cruce con bot de Monedas Ganadoras
            g_ext = ganadoras_ext.get(mon)
            if g_ext:
                cruce_txt = f"🏆 SÍ ({g_ext['veces']}x)"
                dias_ant = "-"
                for fg in g_ext["fechas"]:
                    if fg >= primera["Fecha"]:
                        try:
                            d_ant = (datetime.strptime(fg, "%Y-%m-%d") - datetime.strptime(primera["Fecha"], "%Y-%m-%d")).days
                            dias_ant = f"{d_ant}d antes" if d_ant > 0 else "Mismo día"
                            break
                        except Exception:
                            pass
            else:
                cruce_txt = "🏆 SÍ (Radar)" if wins_internas > 0 else "⏳ Pendiente"
                dias_ant = "-"

            resumen_monedas.append({
                "Moneda": mon,
                "Apariciones": len(lista),
                "Dias_Radar": len({x["Fecha"] for x in lista}),
                "Fecha_Ini": primera["Fecha"],
                "Fecha_Ult": ultima["Fecha"],
                "Color_Ini": primera["Semaforo_Ini"],
                "Secuencia": secuencia_txt,
                "Color_Actual": ultima["Semaforo_Max"],
                "Escalo_Color": "🚀 SÍ" if escalo_alcista else ("🔄 MIX" if cambio_color == "SÍ" else "➖ NO"),
                "Tiempo_a_Rojo": dias_a_rojo,
                "Precio_Base": p_base,
                "Precio_Min": p_min,
                "Precio_Max": p_max,
                "Precio_Lat": p_lat,
                "Precio_Actual": p_actual,
                "Subida_Max_Pct": round(subida_max_pct, 4),
                "Caida_Min_Pct": round(caida_min_pct, 4),
                "Var_Actual_Base": round(var_actual_base, 4),
                "Pos_Rango": round(pos_rango, 3),
                "Estructura": estructura,
                "Prob_Subida": prob_rebote,
                "Ganadora_Bot": cruce_txt,
                "Anticipacion": dias_ant,
            })

        resumen_monedas.sort(key=lambda x: (-x["Prob_Subida"], -x["Apariciones"], x["Moneda"]))
        return resumen_monedas


# ==============================================================================
# 5. ESCÁNER PRE-EXPLOSIÓN Y GENERADOR DE EXCEL MAESTRO (6 PESTAÑAS)
# ==============================================================================
def clasificar_candidatas(tickers: dict, cazador_set: set) -> list:
    candidatas = []
    pre = sorted(
        [t for t in tickers.values() if -6.0 <= t["pct_24h"] <= 18.0],
        key=lambda x: x["quote_vol"],
        reverse=True,
    )[:50]

    for t in pre:
        mon = t["base"]
        met = calcular_metricas_tecnicas(t["symbol"], t)
        if not met:
            continue

        vol_r = met["vol_ratio"]
        v1 = met["var_1h"]
        v4 = met["var_4h"]
        fib = met["fib_pos"]
        ba = met["ba_ratio"] or 1.0
        en_caz = mon in cazador_set

        score = 0.55
        if vol_r >= 2.0:
            score += 0.12
        elif vol_r >= 1.4:
            score += 0.06
        if 0.30 <= fib <= 0.85:
            score += 0.08
        if ba >= 1.5:
            score += 0.08
        if v1 > 0.5:
            score += 0.05
        if en_caz:
            score += 0.10
        blindaje = round(min(0.99, score), 2)

        if (vol_r >= 2.2 and v1 >= 1.5 and ba >= 1.4) or (en_caz and v1 >= 1.2 and blindaje >= 0.85):
            sem = "🔴 ROJO"
        elif (vol_r >= 1.5 and v4 >= 0.5) or (en_caz and blindaje >= 0.80):
            sem = "🟡 AMARILLO"
        elif vol_r >= 1.25 and 0.35 <= fib <= 0.85 and blindaje >= 0.76:
            sem = "🏆 TOP ORO" if blindaje >= 0.88 else "🟢 VERDE"
        else:
            continue

        candidatas.append({
            "Moneda": mon,
            "Semaforo": sem,
            "Blindaje": blindaje,
            "Precio": t["price"],
            "Low24h": t["low"],
            "High24h": t["high"],
            "Var1h": v1,
            "Var4h": v4,
            "Var24h": round(t["pct_24h"], 2),
            "VolRatio": vol_r,
            "Fib": fib,
            "Fib1618": met["fib_1618"],
            "BidsAsks": ba,
            "EnCazador": en_caz,
        })

    candidatas.sort(key=lambda x: (PRIORIDAD_COLOR[sem_cod(x["Semaforo"])], x["Blindaje"], x["VolRatio"]), reverse=True)
    return candidatas[:18]


def generar_excel_pre_explosion(
    reg: RegistroMaestro,
    candidatas: list,
    trazabilidad: list,
    filepath: str = ARCHIVO_EXCEL_MAESTRO
):
    """
    Genera AUDITORIA_PRE_EXPLOSION.xlsx con 6 pestañas:
    1_RESUMEN_MENSUAL_IA
    2_RADAR_ACTIVO_IA
    3_REGISTRO_MAESTRO
    4_RANKING_MONEDAS
    5_AUDITORIA_SETUPS
    6_TRAZABILIDAD_Y_PATRONES (secuencia de colores, base, mínimo, máximo, lateralización, rebote y cruce ganadoras)
    """
    wb = openpyxl.Workbook()
    wb.remove(wb.active)

    f_navy = PatternFill(start_color="0F172A", end_color="0F172A", fill_type="solid")
    f_slate = PatternFill(start_color="1E293B", end_color="1E293B", fill_type="solid")
    f_sub = PatternFill(start_color="F1F5F9", end_color="F1F5F9", fill_type="solid")
    f_zeb = PatternFill(start_color="F8FAFC", end_color="F8FAFC", fill_type="solid")
    f_grn = PatternFill(start_color="DCFCE7", end_color="DCFCE7", fill_type="solid")
    f_amb = PatternFill(start_color="FEF9C3", end_color="FEF9C3", fill_type="solid")
    f_red = PatternFill(start_color="FEE2E2", end_color="FEE2E2", fill_type="solid")
    f_blu = PatternFill(start_color="DBEAFE", end_color="DBEAFE", fill_type="solid")
    f_gld = PatternFill(start_color="FEF3C7", end_color="FEF3C7", fill_type="solid")

    side = Side(style="thin", color="CBD5E1")
    borde = Border(left=side, right=side, top=side, bottom=side)
    sem_fills = {"🔴 ROJO": f_red, "🟡 AMARILLO": f_amb, "🟢 VERDE": f_grn, "🏆 TOP ORO": f_gld}

    filas_ord = sorted(reg.eventos.values(), key=lambda x: (x["Fecha"], x["Hora"], x["Moneda"]))
    END_ROW = 4 + max(1, len(filas_ord))
    fechas_ord = sorted({r["Fecha"] for r in filas_ord}) or [ahora_art().strftime("%Y-%m-%d")]
    periodos_ord = sorted({r["Fecha"][:7] for r in filas_ord}) or [ahora_art().strftime("%Y-%m")]
    f_ini_fmt = datetime.strptime(fechas_ord[0], "%Y-%m-%d").strftime("%d/%m/%Y")
    f_fin_fmt = datetime.strptime(fechas_ord[-1], "%Y-%m-%d").strftime("%d/%m/%Y")

    coin_agg = {}
    sem_wins = {"ROJO": [0, 0], "AMARILLO": [0, 0], "VERDE": [0, 0]}
    for r in filas_ord:
        sc = sem_cod(r["Semaforo_Ini"])
        sem_wins[sc][0] += 1
        if r["Estado"] == "🏆 GANADORA":
            sem_wins[sc][1] += 1

        st = coin_agg.setdefault(r["Moneda"], {
            "rep": 0, "wins": 0, "first_dt": r["Fecha"], "last_dt": r["Fecha"], "best_peak": 0.0
        })
        st["rep"] += 1
        if r["Estado"] == "🏆 GANADORA":
            st["wins"] += 1
        if r["Fecha"] < st["first_dt"]:
            st["first_dt"] = r["Fecha"]
        if r["Fecha"] > st["last_dt"]:
            st["last_dt"] = r["Fecha"]
        p0, p1 = float(r.get("Precio_Entrada") or 0.0), float(r.get("Precio_Pico") or 0.0)
        if p0 > 0 and p1 > 0:
            st["best_peak"] = max(st["best_peak"], round((p1 - p0) / p0, 4))

    coin_stats = sorted(coin_agg.items(), key=lambda kv: (-kv[1]["rep"], -kv[1]["wins"], -kv[1]["best_peak"], kv[0]))
    N_COINS = len(coin_stats)
    wins_tot = sum(1 for r in filas_ord if r["Estado"] == "🏆 GANADORA")
    tasa_tot = round((wins_tot / max(1, len(filas_ord))) * 100, 1)
    dias_win_all = [float(r["Dias_Dec"]) for r in filas_ord if r["Estado"] == "🏆 GANADORA" and isinstance(r.get("Dias_Dec"), (int, float))]
    med_dias = round(sorted(dias_win_all)[len(dias_win_all) // 2], 1) if dias_win_all else 2.0
    med_horas = round(med_dias * 24.0, 1)

    # --------------------------------------------------------------------------
    # PESTAÑA 1: 1_RESUMEN_MENSUAL_IA
    # --------------------------------------------------------------------------
    ws1 = wb.create_sheet("1_RESUMEN_MENSUAL_IA")
    ws1["A1"] = f"PRE-EXPLOSIÓN • PANEL EJECUTIVO & RESUMEN MENSUAL IA ({f_ini_fmt} AL {f_fin_fmt})"
    ws1["A1"].font, ws1["A1"].fill = Font(name="Arial", size=12, bold=True, color="FFFFFF"), f_navy
    ws1.merge_cells("A1:P1")
    ws1["A2"] = f"Consolidación completa de {len(filas_ord)} señales históricas ({N_COINS} monedas únicas • {len(fechas_ord)} días). Cambiá B4 ({', '.join(periodos_ord)} o TODOS)."
    ws1.merge_cells("A2:P2")

    ws1["A4"], ws1["B4"] = "MES SELECCIONADO:", periodos_ord[-1]
    ws1["B4"].fill, ws1["B4"].font, ws1["B4"].border = f_gld, Font(name="Arial", size=11, bold=True), borde
    dv = DataValidation(type="list", formula1=f'"{",".join(periodos_ord + ["TODOS"])}"', allow_blank=False)
    ws1.add_data_validation(dv)
    dv.add(ws1["B4"])

    kpis = [
        ("A", "B", "SEÑALES DEL PERÍODO", f'=IF($B$4="TODOS",COUNTA(\'3_REGISTRO_MAESTRO\'!$F$5:$F${END_ROW}),COUNTIF(\'3_REGISTRO_MAESTRO\'!$C$5:$C${END_ROW},$B$4))', "#,##0", f_sub),
        ("C", "D", "GANADORAS CONFIRMADAS", f'=IF($B$4="TODOS",COUNTIF(\'3_REGISTRO_MAESTRO\'!$Q$5:$Q${END_ROW},"🏆 GANADORA"),COUNTIFS(\'3_REGISTRO_MAESTRO\'!$C$5:$C${END_ROW},$B$4,\'3_REGISTRO_MAESTRO\'!$Q$5:$Q${END_ROW},"🏆 GANADORA"))', "#,##0", f_blu),
        ("E", "F", "CONVERSIÓN %", '=IF(A7>0,C7/A7,0)', "0.0%", f_grn),
        ("G", "H", "SUBIDA PICO PROM. %", f'=IFERROR(IF($B$4="TODOS",AVERAGEIF(\'3_REGISTRO_MAESTRO\'!$P$5:$P${END_ROW},">0"),AVERAGEIFS(\'3_REGISTRO_MAESTRO\'!$P$5:$P${END_ROW},\'3_REGISTRO_MAESTRO\'!$C$5:$C${END_ROW},$B$4,\'3_REGISTRO_MAESTRO\'!$P$5:$P${END_ROW},">0")),0)', "+0.0%;-0.0%;0.0%", f_grn),
        ("I", "J", "TIEMPO MEDIO (DÍAS)", f'=IFERROR(IF($B$4="TODOS",AVERAGEIFS(\'3_REGISTRO_MAESTRO\'!$V$5:$V${END_ROW},\'3_REGISTRO_MAESTRO\'!$Q$5:$Q${END_ROW},"🏆 GANADORA"),AVERAGEIFS(\'3_REGISTRO_MAESTRO\'!$V$5:$V${END_ROW},\'3_REGISTRO_MAESTRO\'!$C$5:$C${END_ROW},$B$4,\'3_REGISTRO_MAESTRO\'!$Q$5:$Q${END_ROW},"🏆 GANADORA")),0)', "0.00", f_amb),
        ("K", "L", "CONFLUENCIA CAZADOR", f'=IF($B$4="TODOS",COUNTIF(\'3_REGISTRO_MAESTRO\'!$X$5:$X${END_ROW},"SÍ*"),COUNTIFS(\'3_REGISTRO_MAESTRO\'!$C$5:$C${END_ROW},$B$4,\'3_REGISTRO_MAESTRO\'!$X$5:$X${END_ROW},"SÍ*"))', "#,##0", f_sub),
    ]
    for cs, ce, tit, form, fmt, fl in kpis:
        ws1[f"{cs}6"], ws1[f"{cs}6"].font, ws1[f"{cs}6"].fill = tit, Font(name="Arial", size=8.5, bold=True, color="FFFFFF"), f_slate
        ws1.merge_cells(f"{cs}6:{ce}6")
        ws1[f"{cs}7"], ws1[f"{cs}7"].font, ws1[f"{cs}7"].fill, ws1[f"{cs}7"].number_format = form, Font(name="Arial", size=14, bold=True), fl, fmt
        ws1.merge_cells(f"{cs}7:{ce}7")

    for ci, h in enumerate(["Semáforo", "Señales", "Ganadoras", "Seguimiento", "Conv. %", "Pico Prom.", "Var. Cierre", "Tiempo (d)"], 1):
        c = ws1.cell(10, ci, h)
        c.font, c.fill, c.border = Font(name="Arial", size=9, bold=True, color="FFFFFF"), f_slate, borde

    for off, (slbl, sfl) in enumerate([("🔴 ROJO", f_red), ("🟡 AMARILLO", f_amb), ("🟢 VERDE", f_grn), ("🏆 TOP ORO", f_gld)]):
        rn = 11 + off
        ws1.cell(rn, 1, slbl).fill = sfl
        ws1.cell(rn, 2, f'=IF($B$4="TODOS",COUNTIF(\'3_REGISTRO_MAESTRO\'!$G$5:$G${END_ROW},$A{rn}),COUNTIFS(\'3_REGISTRO_MAESTRO\'!$C$5:$C${END_ROW},$B$4,\'3_REGISTRO_MAESTRO\'!$G$5:$G${END_ROW},$A{rn}))')
        ws1.cell(rn, 3, f'=IF($B$4="TODOS",COUNTIFS(\'3_REGISTRO_MAESTRO\'!$G$5:$G${END_ROW},$A{rn},\'3_REGISTRO_MAESTRO\'!$Q$5:$Q${END_ROW},"🏆 GANADORA"),COUNTIFS(\'3_REGISTRO_MAESTRO\'!$C$5:$C${END_ROW},$B$4,\'3_REGISTRO_MAESTRO\'!$G$5:$G${END_ROW},$A{rn},\'3_REGISTRO_MAESTRO\'!$Q$5:$Q${END_ROW},"🏆 GANADORA"))')
        ws1.cell(rn, 4, f'=B{rn}-C{rn}')
        ws1.cell(rn, 5, f'=IF(B{rn}>0,C{rn}/B{rn},0)').number_format = "0.0%"
        ws1.cell(rn, 6, f'=IFERROR(IF($B$4="TODOS",AVERAGEIFS(\'3_REGISTRO_MAESTRO\'!$P$5:$P${END_ROW},\'3_REGISTRO_MAESTRO\'!$G$5:$G${END_ROW},$A{rn},\'3_REGISTRO_MAESTRO\'!$P$5:$P${END_ROW},">0"),AVERAGEIFS(\'3_REGISTRO_MAESTRO\'!$P$5:$P${END_ROW},\'3_REGISTRO_MAESTRO\'!$C$5:$C${END_ROW},$B$4,\'3_REGISTRO_MAESTRO\'!$G$5:$G${END_ROW},$A{rn},\'3_REGISTRO_MAESTRO\'!$P$5:$P${END_ROW},">0")),0)').number_format = "+0.0%;-0.0%;0.0%"
        ws1.cell(rn, 7, f'=IFERROR(IF($B$4="TODOS",AVERAGEIFS(\'3_REGISTRO_MAESTRO\'!$T$5:$T${END_ROW},\'3_REGISTRO_MAESTRO\'!$G$5:$G${END_ROW},$A{rn},\'3_REGISTRO_MAESTRO\'!$Q$5:$Q${END_ROW},"🏆 GANADORA"),AVERAGEIFS(\'3_REGISTRO_MAESTRO\'!$T$5:$T${END_ROW},\'3_REGISTRO_MAESTRO\'!$C$5:$C${END_ROW},$B$4,\'3_REGISTRO_MAESTRO\'!$G$5:$G${END_ROW},$A{rn},\'3_REGISTRO_MAESTRO\'!$Q$5:$Q${END_ROW},"🏆 GANADORA")),0)').number_format = "+0.0%;-0.0%;0.0%"
        ws1.cell(rn, 8, f'=IFERROR(IF($B$4="TODOS",AVERAGEIFS(\'3_REGISTRO_MAESTRO\'!$V$5:$V${END_ROW},\'3_REGISTRO_MAESTRO\'!$G$5:$G${END_ROW},$A{rn},\'3_REGISTRO_MAESTRO\'!$Q$5:$Q${END_ROW},"🏆 GANADORA"),AVERAGEIFS(\'3_REGISTRO_MAESTRO\'!$V$5:$V${END_ROW},\'3_REGISTRO_MAESTRO\'!$C$5:$C${END_ROW},$B$4,\'3_REGISTRO_MAESTRO\'!$G$5:$G${END_ROW},$A{rn},\'3_REGISTRO_MAESTRO\'!$Q$5:$Q${END_ROW},"🏆 GANADORA")),0)').number_format = "0.00"
        for ci in range(1, 9):
            ws1.cell(rn, ci).border = borde

    chart = BarChart()
    chart.title = "Señales vs Ganadoras por Semáforo"
    chart.add_data(Reference(ws1, min_col=2, max_col=3, min_row=10, max_row=14), titles_from_data=True)
    chart.set_categories(Reference(ws1, min_col=1, min_row=11, max_row=14))
    ws1.add_chart(chart, "J9")

    # --------------------------------------------------------------------------
    # PESTAÑA 2: 2_RADAR_ACTIVO_IA
    # --------------------------------------------------------------------------
    ws2 = wb.create_sheet("2_RADAR_ACTIVO_IA")
    ws2["A1"] = "ASISTENTE IA • CANDIDATAS ACTIVAS PRE-EXPLOSIÓN"
    ws2["A1"].font, ws2["A1"].fill = Font(name="Arial", size=12, bold=True, color="FFFFFF"), f_navy
    ws2.merge_cells("A1:K1")
    ws2["A2"] = f"Universo unificado de {len(filas_ord)} señales ({N_COINS} monedas • conversión global: {tasa_tot}%). Maduración mediana: {med_dias}d ({int(med_horas)}h)."
    ws2.merge_cells("A2:K2")
    for ci, h in enumerate(["MONEDA", "SEMÁFORO", "CERTIFICADA", "BLINDAJE", "PRECIO", "EFECTIVIDAD", "MADURACIÓN", "FIBONACCI", "BIDS/ASKS", "ACCIÓN", "DICTAMEN IA"], 1):
        c = ws2.cell(4, ci, h)
        c.font, c.fill, c.border = Font(name="Arial", size=9, bold=True, color="FFFFFF"), f_slate, borde

    for idx_c, cand in enumerate(candidatas[:12]):
        rn = 5 + idx_c
        sc = sem_cod(cand["Semaforo"])
        tot_s, win_s = sem_wins[sc]
        ef_hist = round(win_s / max(1, tot_s), 3)
        horiz = "0.5d" if sc == "ROJO" else ("2.0d" if sc == "AMARILLO" else "3.0d")
        fib_v = cand["Fib"]
        fib_txt = f"Pullback Sano Fib ({fib_v:.2f})" if fib_v <= 0.65 else f"Piso Profundo Fib ({fib_v:.2f})"
        ba_txt = f"{cand['BidsAsks']:.2f}x"
        accion = "COMPRA_CONFIRMADA_MADURACION" if cand["Blindaje"] >= 0.85 else "OBSERVACION_ESCALADA"
        dictamen = f"Señal {sc} (blindaje {int(cand['Blindaje']*100)}%); horizonte típico {horiz}."

        vals2 = [
            cand["Moneda"], sc, "🛡️ SÍ" if cand["Blindaje"] >= 0.80 else "⚠️ OBS",
            cand["Blindaje"], cand["Precio"], ef_hist, horiz, fib_txt, ba_txt, accion, dictamen
        ]
        for ci, v in enumerate(vals2, 1):
            c = ws2.cell(rn, ci, v)
            c.border = borde
            if ci in (4, 6):
                c.number_format = "0.0%"

    # --------------------------------------------------------------------------
    # PESTAÑA 3: 3_REGISTRO_MAESTRO
    # --------------------------------------------------------------------------
    ws3 = wb.create_sheet("3_REGISTRO_MAESTRO")
    ws3["A1"] = f"PRE-EXPLOSIÓN • REGISTRO MAESTRO UNIFICADO ({f_ini_fmt} AL {f_fin_fmt})"
    ws3["A1"].font, ws3["A1"].fill = Font(name="Arial", size=12, bold=True, color="FFFFFF"), f_navy
    ws3.merge_cells("A1:Y1")
    headers_ws3 = [
        "ID", "Fecha", "Período", "Mes", "Hora", "Moneda", "Semáforo Ini", "Semáforo Máx",
        "Escalada", "Veces", "IA %", "Fib", "Bids/Asks", "$ Entrada", "$ Pico", "Subida %",
        "Estado", "Fecha Win", "$ Actual/Win", "Var Real %", "Tiempo Win", "Días", "Fib 1.618",
        "Confluencia", "Origen"
    ]
    for ci, h in enumerate(headers_ws3, 1):
        c = ws3.cell(4, ci, h)
        c.font, c.fill, c.border = Font(name="Arial", size=9, bold=True, color="FFFFFF"), f_slate, borde

    for idx, row in enumerate(filas_ord):
        rn = 5 + idx
        is_win = (row["Estado"] == "🏆 GANADORA")
        p_ent = float(row["Precio_Entrada"] or 0.0)
        p_pico = max(float(row["Precio_Pico"] or 0.0), p_ent)
        p_fin = float(row["Precio_Final"] or p_ent)
        vals = [
            idx + 1, row["Fecha"], f"=LEFT(B{rn},7)",
            f'=C{rn}&" • "&CHOOSE(VALUE(RIGHT(C{rn},2)),"Enero","Febrero","Marzo","Abril","Mayo","Junio","Julio","Agosto","Septiembre","Octubre","Noviembre","Diciembre")',
            row["Hora"], row["Moneda"], row["Semaforo_Ini"], row["Semaforo_Max"], row["Escalada"],
            f"=COUNTIF($F$5:$F${END_ROW},F{rn})",
            row["IA_Pct"] if isinstance(row.get("IA_Pct"), (int, float)) else "-",
            row["Fib_Zona"] if isinstance(row.get("Fib_Zona"), (int, float)) else "-",
            row["Bids_Asks"] if isinstance(row.get("Bids_Asks"), (int, float)) else "-",
            p_ent, p_pico, f"=IF(AND(N{rn}>0,O{rn}>0),(O{rn}-N{rn})/N{rn},0)",
            row["Estado"], row["Fecha_Ganadora"], p_fin, f"=IF(AND(N{rn}>0,S{rn}>0),(S{rn}-N{rn})/N{rn},0)",
            row["Tiempo_Ganadora_Txt"], float(row["Dias_Dec"]) if isinstance(row.get("Dias_Dec"), (int, float)) else "-",
            row["Fib_1618"], row["Confluencia"], row["Origen"]
        ]
        for ci, val in enumerate(vals, 1):
            c = ws3.cell(rn, ci, val)
            c.border = borde
            if ci == 11 and isinstance(val, float):
                c.number_format = "0.0%"
            elif ci in (16, 20):
                c.number_format = "+0.00%;-0.00%;0.00%"
            if ci in (7, 8):
                c.fill = sem_fills.get(str(val), f_grn)
            elif is_win:
                c.fill = f_blu
            elif idx % 2 == 1:
                c.fill = f_zeb
    ws3.freeze_panes = "A5"
    ws3.auto_filter.ref = f"A4:Y{END_ROW}"

    # --------------------------------------------------------------------------
    # PESTAÑA 4: 4_RANKING_MONEDAS (100% libre de #NAME?)
    # --------------------------------------------------------------------------
    ws4 = wb.create_sheet("4_RANKING_MONEDAS")
    ws4["A1"] = f"RANKING DE MONEDAS ÚNICAS ({N_COINS} ACTIVOS • {f_ini_fmt} AL {f_fin_fmt})"
    ws4["A1"].font, ws4["A1"].fill = Font(name="Arial", size=12, bold=True, color="FFFFFF"), f_navy
    ws4.merge_cells("A1:K1")
    for ci, h in enumerate(["N°", "Moneda", "Repeticiones", "Rojas", "Amarillas", "Verdes", "Ganadoras", "Conv %", "1ª Fecha", "Última Fecha", "Mejor Pico %"], 1):
        c = ws4.cell(4, ci, h)
        c.font, c.fill, c.border = Font(name="Arial", size=9, bold=True, color="FFFFFF"), f_slate, borde

    for idx_c, (mon, st) in enumerate(coin_stats):
        rn = 5 + idx_c
        vals = [
            idx_c + 1, mon,
            f"=COUNTIF('3_REGISTRO_MAESTRO'!$F$5:$F${END_ROW},B{rn})",
            f"=COUNTIFS('3_REGISTRO_MAESTRO'!$F$5:$F${END_ROW},B{rn},'3_REGISTRO_MAESTRO'!$G$5:$G${END_ROW},\"🔴 ROJO\")",
            f"=COUNTIFS('3_REGISTRO_MAESTRO'!$F$5:$F${END_ROW},B{rn},'3_REGISTRO_MAESTRO'!$G$5:$G${END_ROW},\"🟡 AMARILLO\")",
            f"=COUNTIFS('3_REGISTRO_MAESTRO'!$F$5:$F${END_ROW},B{rn},'3_REGISTRO_MAESTRO'!$G$5:$G${END_ROW},\"🟢 VERDE\")+COUNTIFS('3_REGISTRO_MAESTRO'!$F$5:$F${END_ROW},B{rn},'3_REGISTRO_MAESTRO'!$G$5:$G${END_ROW},\"🏆 TOP ORO\")",
            f"=COUNTIFS('3_REGISTRO_MAESTRO'!$F$5:$F${END_ROW},B{rn},'3_REGISTRO_MAESTRO'!$Q$5:$Q${END_ROW},\"🏆 GANADORA\")",
            f"=IF(C{rn}>0,G{rn}/C{rn},0)",
            st["first_dt"], st["last_dt"], st["best_peak"]
        ]
        for ci, v in enumerate(vals, 1):
            c = ws4.cell(rn, ci, v)
            c.border = borde
            if ci == 8:
                c.number_format = "0.0%"
            elif ci == 11:
                c.number_format = "+0.0%;-0.0%;0.0%"

    # --------------------------------------------------------------------------
    # PESTAÑA 5: 5_AUDITORIA_SETUPS
    # --------------------------------------------------------------------------
    ws5 = wb.create_sheet("5_AUDITORIA_SETUPS")
    ws5["A1"] = "AUDITORÍA POR SEMÁFORO Y CONFLUENCIA"
    ws5["A1"].font, ws5["A1"].fill = Font(name="Arial", size=12, bold=True, color="FFFFFF"), f_navy
    ws5.merge_cells("A1:E1")
    for ci, h in enumerate(["Setup", "Señales", "Ganadoras", "Efectividad %", "Subida Pico Prom %"], 1):
        c = ws5.cell(4, ci, h)
        c.font, c.fill, c.border = Font(name="Arial", size=9, bold=True, color="FFFFFF"), f_slate, borde

    setups = [
        ("🔴 ROJO", "G", "🔴 ROJO"),
        ("🟡 AMARILLO", "G", "🟡 AMARILLO"),
        ("🟢 VERDE", "G", "🟢 VERDE"),
        ("🏆 TOP ORO", "G", "🏆 TOP ORO"),
        ("🛡️ Confluencia Cazador+Pre", "X", "SÍ (Cazador + Pre-Exp)"),
        ("📡 Solo Pre-Explosión", "X", "Solo Pre-Explosión"),
    ]
    for idx_s, (lbl, col_l, crit) in enumerate(setups):
        rn = 5 + idx_s
        ws5.cell(rn, 1, lbl).border = borde
        ws5.cell(rn, 2, f"=COUNTIF('3_REGISTRO_MAESTRO'!${col_l}$5:${col_l}${END_ROW},\"{crit}\")").border = borde
        ws5.cell(rn, 3, f"=COUNTIFS('3_REGISTRO_MAESTRO'!${col_l}$5:${col_l}${END_ROW},\"{crit}\",'3_REGISTRO_MAESTRO'!$Q$5:$Q${END_ROW},\"🏆 GANADORA\")").border = borde
        c4 = ws5.cell(rn, 4, f"=IF(B{rn}>0,C{rn}/B{rn},0)")
        c4.border, c4.number_format = borde, "0.0%"
        c5 = ws5.cell(rn, 5, f"=IFERROR(AVERAGEIFS('3_REGISTRO_MAESTRO'!$P$5:$P${END_ROW},'3_REGISTRO_MAESTRO'!${col_l}$5:${col_l}${END_ROW},\"{crit}\",'3_REGISTRO_MAESTRO'!$P$5:$P${END_ROW},\">0\"),0)")
        c5.border, c5.number_format = borde, "+0.0%;-0.0%;0.0%"

    # --------------------------------------------------------------------------
    # PESTAÑA 6: 6_TRAZABILIDAD_Y_PATRONES (1 fila por moneda: colores, precios, lateralización y cruce)
    # --------------------------------------------------------------------------
    ws6 = wb.create_sheet("6_TRAZABILIDAD_Y_PATRONES")
    tot_escalaron = sum(1 for x in trazabilidad if "SÍ" in x["Escalo_Color"])
    tot_lat = sum(1 for x in trazabilidad if "LATERALIZANDO" in x["Estructura"] or "ACUMULANDO" in x["Estructura"])
    ws6["A1"] = f"MAPA DE PATRONES Y TRAZABILIDAD POR MONEDA ({len(trazabilidad)} MONEDAS • {tot_escalaron} ESCALARON COLOR • {tot_lat} EN BASE/PISO)"
    ws6["A1"].font, ws6["A1"].fill = Font(name="Arial", size=12, bold=True, color="FFFFFF"), f_navy
    ws6.merge_cells("A1:W1")
    ws6["A2"] = "Ordenado por Probabilidad de Nueva Subida %. Muestra secuencia histórica de colores, $ Base, $ Mínimo, $ Máximo, $ Lateralización y cruce con Bot Ganadoras."
    ws6.merge_cells("A2:W2")

    headers_ws6 = [
        "N°", "Moneda", "Apariciones", "Días Radar", "1ª Fecha", "Última Fecha",
        "Color Ini", "Secuencia Colores", "Color Actual", "Escaló Color", "Tiempo a Rojo",
        "$ Base Radar", "$ Mínimo", "$ Máximo", "$ Lateraliz.", "$ Actual",
        "Subida Máx %", "Caída Mín %", "Pos. Rango %", "Estructura Actual",
        "Prob. Rebote %", "Bot Ganadoras", "Anticipación"
    ]
    for ci, h in enumerate(headers_ws6, 1):
        c = ws6.cell(4, ci, h)
        c.font, c.fill, c.border = Font(name="Arial", size=9, bold=True, color="FFFFFF"), f_slate, borde

    for idx_t, item in enumerate(trazabilidad):
        rn = 5 + idx_t
        vals6 = [
            idx_t + 1, item["Moneda"], item["Apariciones"], item["Dias_Radar"],
            item["Fecha_Ini"], item["Fecha_Ult"], item["Color_Ini"], item["Secuencia"],
            item["Color_Actual"], item["Escalo_Color"], item["Tiempo_a_Rojo"],
            item["Precio_Base"], item["Precio_Min"], item["Precio_Max"],
            item["Precio_Lat"], item["Precio_Actual"], item["Subida_Max_Pct"],
            item["Caida_Min_Pct"], item["Pos_Rango"], item["Estructura"],
            item["Prob_Subida"], item["Ganadora_Bot"], item["Anticipacion"]
        ]
        for ci, v in enumerate(vals6, 1):
            c = ws6.cell(rn, ci, v)
            c.border = borde
            if ci in (17, 18):
                c.number_format = "+0.0%;-0.0%;0.0%"
            elif ci in (19, 21):
                c.number_format = "0.0%"

            if ci in (7, 9):
                c.fill = sem_fills.get(str(v), f_grn)
            elif ci == 10 and "SÍ" in str(v):
                c.fill = f_gld
            elif ci == 20 and ("LATERALIZANDO" in str(v) or "ACUMULANDO" in str(v)):
                c.fill = f_grn
            elif ci == 22 and "SÍ" in str(v):
                c.fill = f_blu
            elif idx_t % 2 == 1:
                c.fill = f_zeb

    ws6.freeze_panes = "C5"
    ws6.auto_filter.ref = f"A4:W{4 + max(1, len(trazabilidad))}"

    # Ajuste automático de anchos de columna
    for ws in wb.worksheets:
        for col in ws.columns:
            max_len = 0
            col_letter = get_column_letter(col[0].column)
            for cell in col:
                if cell.row >= 4 and cell.value is not None and not str(cell.value).startswith("="):
                    max_len = max(max_len, len(str(cell.value)))
            ws.column_dimensions[col_letter].width = min(max(max_len + 4, 12), 46)

    wb.save(filepath)
    log.info(f"Excel maestro guardado: {filepath} ({len(filas_ord)} registros, {N_COINS} monedas, {wins_tot} ganadoras, 6 pestañas).")


# ==============================================================================
# 6. ENVÍO A TELEGRAM CON SOPORTE DE HILOS (TOPICS) Y LOGS DE RESPUESTA
# ==============================================================================
def enviar_telegram_mensaje(texto: str):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        log.warning("Faltan TELEGRAM_TOKEN o TELEGRAM_CHAT_ID.")
        return
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": texto,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    if TOPIC_ID_PRE_EXPLOSION:
        try:
            payload["message_thread_id"] = int(TOPIC_ID_PRE_EXPLOSION)
        except ValueError:
            log.warning(f"TOPIC_ID_PRE_EXPLOSION inválido: {TOPIC_ID_PRE_EXPLOSION}")
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json=payload,
            timeout=15,
        )
        if r.status_code != 200:
            log.error(f"Telegram rechazó sendMessage ({r.status_code}): {r.text}")
        else:
            log.info(f"Mensaje enviado correctamente a Telegram (topic={TOPIC_ID_PRE_EXPLOSION or 'General'}).")
    except Exception as e:
        log.error(f"Error enviando mensaje Telegram: {e}")


def enviar_telegram_excel(filepath: str, caption: str):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID or not os.path.exists(filepath):
        log.warning("Faltan credenciales de Telegram o no existe el Excel.")
        return
    data = {
        "chat_id": TELEGRAM_CHAT_ID,
        "caption": caption[:1000],
    }
    if TOPIC_ID_PRE_EXPLOSION:
        try:
            data["message_thread_id"] = int(TOPIC_ID_PRE_EXPLOSION)
        except ValueError:
            pass
    try:
        with open(filepath, "rb") as f:
            r = requests.post(
                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendDocument",
                data=data,
                files={"document": (os.path.basename(filepath), f)},
                timeout=30,
            )
        if r.status_code != 200:
            log.error(f"Telegram rechazó sendDocument ({r.status_code}): {r.text}")
        else:
            log.info(f"Excel enviado correctamente a Telegram (topic={TOPIC_ID_PRE_EXPLOSION or 'General'}).")
    except Exception as e:
        log.error(f"Error enviando Excel a Telegram: {e}")


def publicar_reporte_telegram(candidatas: list, reg: RegistroMaestro, trazabilidad: list, dt_art: datetime):
    fecha_txt = dt_art.strftime("%Y-%m-%d %H:%M ART")
    bloques = [
        ("🔴 1. EXPLOSIÓN INMINENTE (ROJO)", [c for c in candidatas if "ROJO" in c["Semaforo"]]),
        ("🟡 2. CONFIRMACIÓN TÁCTICA (AMARILLO)", [c for c in candidatas if "AMARILLO" in c["Semaforo"]]),
        ("🟢 3. COMPRA TEMPRANA • TOP ORO (VERDE)", [c for c in candidatas if "VERDE" in c["Semaforo"] or "ORO" in c["Semaforo"]]),
    ]
    for idx, (titulo, items) in enumerate(bloques, 1):
        lineas = [f"🔥 <b>PRE-EXPLOSIÓN ({idx}/3)</b>", f"<b>{titulo}</b>", f"📅 {fecha_txt}", ""]
        if not items:
            lineas.append("⏳ Sin monedas en este bloque en este ciclo.")
        else:
            for it in items[:6]:
                tag_caz = " ⭐⭐⭐ [Cazador]" if it["EnCazador"] else ""
                tag_oro = " 🏆 ORO" if "ORO" in it["Semaforo"] else ""
                lineas.append(
                    f"• <b>{it['Moneda']}</b>{tag_oro}{tag_caz} | {fmt_precio(it['Precio'])} "
                    f"(1h: {it['Var1h']:+.1f}% | 4h: {it['Var4h']:+.1f}% | Vol: {it['VolRatio']:.1f}x) "
                    f"| CERTIFICADA IA ({int(it['Blindaje']*100)}%)"
                )
        enviar_telegram_mensaje("\n".join(lineas))
        time.sleep(0.8)

    tot_reg = len(reg.eventos)
    tot_wins = sum(1 for r in reg.eventos.values() if r["Estado"] == "🏆 GANADORA")
    tot_esc = sum(1 for x in trazabilidad if "SÍ" in x["Escalo_Color"])
    top_rebote = [x["Moneda"] for x in trazabilidad[:4]]

    caption = (
        f"📊 AUDITORÍA MAESTRA PRE-EXPLOSIÓN ({fecha_txt})\n"
        f"• Histórico acumulado: {tot_reg} señales ({len(trazabilidad)} monedas únicas)\n"
        f"• Ganadoras confirmadas: {tot_wins} ({round(tot_wins/max(1,tot_reg)*100,1)}%)\n"
        f"• Escaladas de color (🟢➔🟡➔🔴): {tot_esc} monedas\n"
        f"• Top acumulación/rebote: {', '.join(top_rebote)}\n"
        f"• Pestaña 6: Trazabilidad, Mínimos, Lateralización y Cruce Ganadoras"
    )
    enviar_telegram_excel(ARCHIVO_EXCEL_MAESTRO, caption)


# ==============================================================================
# 7. EJECUCIÓN PRINCIPAL
# ==============================================================================
def main():
    dt_art = ahora_art()
    fecha_hoy = dt_art.strftime("%Y-%m-%d")
    hora_hoy = dt_art.strftime("%H:%M")

    log.info(f"Iniciando ciclo bot_pre_explosion ({fecha_hoy} {hora_hoy} ART)...")
    log.info(f"Configuración Telegram -> Chat: {'OK' if TELEGRAM_CHAT_ID else 'FALTA'} | Topic: {TOPIC_ID_PRE_EXPLOSION or 'General'}")

    reg = RegistroMaestro()
    reg.hidratar_desde_excel_maestro(ARCHIVO_EXCEL_MAESTRO)
    reg.hidratar_desde_json_estado(ARCHIVO_ESTADO_JSON)

    tickers = obtener_tickers_24h()
    log.info(f"Pares Spot válidos obtenidos en Binance: {len(tickers)}")

    if tickers:
        reg.actualizar_precios_y_ganadoras(tickers, fecha_hoy)

    cazador_set = reg.leer_cazador_activo()
    ganadoras_ext = reg.leer_ganadoras_otro_bot()
    candidatas = clasificar_candidatas(tickers, cazador_set) if tickers else []
    log.info(f"Candidatas detectadas en este ciclo: {len(candidatas)}")

    for cand in candidatas:
        reg.upsert({
            "Fecha": fecha_hoy,
            "Hora": hora_hoy,
            "Moneda": cand["Moneda"],
            "Semaforo_Ini": cand["Semaforo"],
            "Semaforo_Max": cand["Semaforo"],
            "IA_Pct": cand["Blindaje"],
            "Fib_Zona": cand["Fib"],
            "Bids_Asks": cand["BidsAsks"],
            "Precio_Entrada": cand["Precio"],
            "Precio_Min": cand.get("Low24h") or cand["Precio"],
            "Precio_Pico": max(cand["Precio"], cand.get("High24h") or cand["Precio"]),
            "Precio_Final": cand["Precio"],
            "Fib_1618": str(cand["Fib1618"]),
            "Confluencia": "SÍ (Cazador + Pre-Exp)" if cand["EnCazador"] else "Solo Pre-Explosión",
            "Origen": "Cazador + Pre-Explosión" if cand["EnCazador"] else "Bot Pre-Explosión",
        })

    trazabilidad = reg.construir_trazabilidad_monedas(tickers, ganadoras_ext)
    reg.guardar_json_estado(ARCHIVO_ESTADO_JSON)
    generar_excel_pre_explosion(reg, candidatas, trazabilidad, ARCHIVO_EXCEL_MAESTRO)
    publicar_reporte_telegram(candidatas, reg, trazabilidad, dt_art)

    log.info("Ciclo finalizado correctamente.")


if __name__ == "__main__":
    main()
