import os, json, glob, time, random, html, hashlib, requests
from datetime import datetime, timezone, timedelta
import matplotlib
matplotlib.use("Agg")
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
DATOS_PRE_EXPLOSION_FILE = "datos_pre_explosion_ia.json"
EXCEL_GANADORAS_FILE = "AUDITORIA_VERDE_GANADORAS.xlsx"
EXCEL_CAZADOR_FILE = "AUDITORIA_CAZADOR_TACTICO.xlsx"
EXCEL_PRE_EXPLOSION_FILE = "AUDITORIA_PRE_EXPLOSION.xlsx"

# Informes IA generados por los 3 motores principales + Cerebro Central
REPORTE_IA_GANADORAS_FILE = "reporte_ia_ganadoras.json"
REPORTE_IA_TACTICO_FILE = "reporte_ia_tactico.json"
REPORTE_IA_PRE_EXPLOSION_FILE = "reporte_ia_pre_explosion.json"
CEREBRO_FEED_JSON = "cerebro_matriz_central.json"

PLAN_SEMANAL_FILE = "plan_semanal.json"
EXCEL_SEMANAL_FILE = "AUDITORIA_SEMANAL_PRUEBA.xlsx"
CEREBRO_EVOLUTIVO_FILE = "cerebro_evolutivo.json"
BITACORA_TOTAL_FILE = "bitacora_total.jsonl"

# Parámetros operativos: Mesa 6 Asistentes (4 Empresa + 2 Binance) -> 3 Traders Dedicados (1 moneda c/u) -> Jefe Supervisor
CAPITAL_INICIAL_PRUEBA = 3500.0
META_SEMANAL_USD = 600.0
MAX_TRADERS_SEMANA = 3              # 3 Traders independientes: 1 moneda exclusiva por Trader (33.3% capital c/u)
MAX_MONEDAS_SEMANA = MAX_TRADERS_SEMANA
NOMBRES_TRADERS = ["TRADER_1", "TRADER_2", "TRADER_3"]
CUPOS_MODO_DEFENSIVO = 2            # Reduce de 3 a 2 Traders activos cuando el mercado general está débil
MAX_ENTRADAS_POR_CORRIDA = 2        # Entrada escalonada: máximo 2 compras nuevas por ejecución
TOP_ALTERNATIVAS_MOSTRAR = 8
FACTIBILIDAD_MINIMA_JEFE = 75       # Puntaje mínimo exigido por el Jefe Supervisor para aprobar una entrada

# Parámetros base de Riesgo y Cosecha Runner en 3 Tramos (auto-calibrables por el Cerebro Evolutivo)
COMISION_SPOT_TOTAL_PCT = 0.20      # 0.10% compra + 0.10% venta en Binance Spot (PnL Neto Real)
STOP_LOSS_FIJO_PCT = -3.40          # Stop base de despegue (-3.40% neto)
STOP_REBOTE_CORROBORADO_PCT = -3.50 # Stop directo cuando >=2 Asistentes de Etapa corroboran rebote/explosión
TP1_ASEGURAR_PCT = 6.5              # Tramo 1: vende 35% al tocar +6.5% neto y mueve stop a +0.50% BE
TP2_ASEGURAR_PCT = 15.0             # Tramo 2: vende otro 35% al tocar +15.0% neto y mueve stop a +8.0%
TRAILING_RUNNER_PCT = 4.5           # Tramo 3 (30% Runner): trailing holgado de 4.5% desde el máximo para cazar +20% a +70%
HORAS_MAX_SIN_ARRANQUE_VIP = 24.0   # Paciencia de 24h en acumulación para monedas confirmadas por Pre-Explosión
HORAS_MAX_SIN_ARRANQUE_STD = 10.0   # Rotación en 10h para candidatas estándar
MAX_REENTRADAS_SEMANA = 1           # Permite hasta 1 re-entrada semanal si vuelve a romper con volumen fuerte
COOLDOWN_PANICO_BTC_MIN = 60        # Antispam de 60 minutos para alerta de pánico BTC 1H

MIN_LIQUIDEZ_TOP_ASK_USD = 2500.0   # Liquidez mínima en USD dentro del 0.15% del mejor Ask
MAX_SLIPPAGE_EST_PCT = 0.25         # Deslizamiento máximo estimado para ejecutar un cupo real (~$1,166)
MINUTOS_CALIBRACION_SISTEMA = 15    # Tiempo de arranque y calibración tras actualizar el código

# Exclusión de tokens apalancados y sintéticos de acciones/ETFs en Binance Spot
TOKENS_NO_CRIPTO_EXACTOS = {"SOXLB", "SOXSB", "FLNCB", "ASTSB", "TSLAB", "NVDAB", "AAPLB", "COINB"}
SUFIJOS_APALANCADOS = ("UP", "DOWN", "BULL", "BEAR")

MODELOS_GEMINI = ["gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-2.0-flash"]

PARAMETROS_CEREBRO_DEFAULT = {
    "version_ciclo": 1,
    "ultima_actualizacion": "",
    "umbrales": {
        "min_ratio_vol_1h": 1.80,
        "min_ob_ratio": 1.25,
        "max_concentracion_muro_pct": 32.0,
        "min_taker_buy_pct": 55.0,
        "min_whale_buy_pct": 54.0,
        "min_trades_por_min": 12.0,
        "min_pista_libre_pct": 16.0,
        "max_distancia_ma7_15m_pct": 3.20,
        "stop_base_pct": -3.40,
        "tp1_pct": 6.50,
        "tp2_pct": 15.00,
        "objetivo_runner_pct": 20.00
    },
    "pesos_patrones": {
        "CONFLUENCIA_E1_E3_MAS_PREEXPLOSION": {"ops": 0, "ganadas": 0, "runners_20": 0, "bonus": 22.0},
        "REBOTE_EXPLOSION_CORROBORADO_ETAPA": {"ops": 0, "ganadas": 0, "runners_20": 0, "bonus": 20.0},
        "RUPTURA_DIRECTA_BINANCE_A5": {"ops": 0, "ganadas": 0, "runners_20": 0, "bonus": 15.0},
        "DISPARO_PRE_EXPLOSION_E2": {"ops": 0, "ganadas": 0, "runners_20": 0, "bonus": 18.0},
        "ACUMULACION_ASCENDENTE_CAZADOR_E1": {"ops": 0, "ganadas": 0, "runners_20": 0, "bonus": 14.0},
        "ESCALADA_GANADORAS_24H": {"ops": 0, "ganadas": 0, "runners_20": 0, "bonus": 12.0}
    },
    "memoria_monedas": {},
    "pendientes_sombra_24h": [],
    "metricas_globales": {
        "total_operadas": 0,
        "total_ganadas": 0,
        "runners_20_logrados": 0,
        "stops_prematuros": 0,
        "stops_salvadores": 0,
        "vetos_acertados": 0,
        "oportunidades_perdidas_20": 0,
        "ajustes_autocritica_ciclo": 0
    }
}


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


def es_cripto_spot_valida(base_asset: str) -> bool:
    b = str(base_asset or "").upper().strip()
    if not b or b in TOKENS_NO_CRIPTO_EXACTOS:
        return False
    if b.endswith(SUFIJOS_APALANCADOS):
        return False
    return True


def crear_sesion_binance():
    s = requests.Session()
    s.headers.update({"User-Agent": "Mozilla/5.0", "Accept": "application/json", "Cache-Control": "no-cache"})
    return s


def binance_get_json(session, endpoint, params=None, timeout=8):
    params = params or {}
    for base_url in BINANCE_API_BASES:
        try:
            r = session.get(f"{base_url}/api/v3/{endpoint}", params=params, timeout=timeout)
            if r.status_code == 200:
                return r.json()
        except Exception:
            continue
    return None


def obtener_tickers_binance(session):
    data = binance_get_json(session, "ticker/24hr", timeout=15)
    if not isinstance(data, list):
        return {}
    mapa = {}
    for t in data:
        sym = t.get("symbol", "")
        if sym.endswith("USDT"):
            base = sym[:-4]
            if not es_cripto_spot_valida(base):
                continue
            try:
                mapa[sym] = {
                    "symbol": sym,
                    "base": base,
                    "precio": float(t["lastPrice"]),
                    "cambio_24h": float(t["priceChangePercent"]),
                    "vol_24h": float(t["quoteVolume"]),
                    "high": float(t["highPrice"]),
                    "low": float(t["lowPrice"]),
                    "bid": float(t.get("bidPrice") or t["lastPrice"]),
                    "ask": float(t.get("askPrice") or t["lastPrice"])
                }
            except Exception:
                continue
    return mapa


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
# MÓDULO EVOLUTIVO CONTINUO (BITÁCORA TOTAL + AUDITORÍA SOMBRA + AUTO-CALIBRACIÓN)
# ==============================================================================

class CerebroEvolutivo:
    def __init__(self):
        self.data = self._cargar()

    def _cargar(self):
        raw = cargar_json_seguro(CEREBRO_EVOLUTIVO_FILE)
        if isinstance(raw, dict) and "umbrales" in raw:
            for k, v in PARAMETROS_CEREBRO_DEFAULT.items():
                if k not in raw:
                    raw[k] = json.loads(json.dumps(v))
                elif isinstance(v, dict):
                    for sub_k, sub_v in v.items():
                        raw[k].setdefault(sub_k, sub_v)
            return raw
        return json.loads(json.dumps(PARAMETROS_CEREBRO_DEFAULT))

    def guardar(self):
        self.data["version_ciclo"] = int(self.data.get("version_ciclo", 1)) + 1
        self.data["ultima_actualizacion"] = ahora_art().strftime("%Y-%m-%d %H:%M ART")
        try:
            with open(CEREBRO_EVOLUTIVO_FILE, "w", encoding="utf-8") as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"⚠️ Error guardando {CEREBRO_EVOLUTIVO_FILE}: {e}")

    def log_bitacora(self, tipo: str, payload: dict):
        reg = {
            "ts_unix": int(time.time()),
            "fecha_art": ahora_art().strftime("%Y-%m-%d %H:%M:%S ART"),
            "tipo": tipo,
            "datos": payload
        }
        try:
            with open(BITACORA_TOTAL_FILE, "a", encoding="utf-8") as f:
                f.write(json.dumps(reg, ensure_ascii=False) + "\n")
        except Exception:
            pass

    @property
    def umbrales(self) -> dict:
        return self.data["umbrales"]

    def bono_evolutivo(self, symbol: str, patron: str) -> float:
        p_info = self.data["pesos_patrones"].get(patron, {"bonus": 10.0})
        b_patron = float(p_info.get("bonus", 10.0))
        m_info = self.data["memoria_monedas"].get(symbol, {})
        b_coin = float(m_info.get("ajuste_score", 0.0))
        return round(b_patron + b_coin, 1)

    def registrar_veto_sombra(self, symbol: str, precio: float, paso_fallido: str, detalle: str):
        if precio <= 0:
            return
        self.log_bitacora("VETO_MESA_6_ASISTENTES", {
            "symbol": symbol,
            "precio": precio,
            "paso_fallido": paso_fallido,
            "detalle": detalle
        })
        ahora_ts = int(time.time())
        ya_existe = any(
            x.get("symbol") == symbol and (ahora_ts - x.get("ts_unix", 0)) < 21600
            for x in self.data["pendientes_sombra_24h"]
        )
        if not ya_existe:
            self.data["pendientes_sombra_24h"].append({
                "symbol": symbol,
                "ts_unix": ahora_ts,
                "precio_veto": precio,
                "paso_fallido": paso_fallido,
                "detalle": detalle
            })

    def auditar_sombra_y_calibrar(self, session, mapa_mkt: dict):
        """Audita monedas rechazadas entre 6h y 24h atrás: si subieron >= +18%, relaja el filtro exacto que las frenó."""
        ahora_ts = int(time.time())
        restantes = []
        u = self.umbrales
        m = self.data["metricas_globales"]

        for item in self.data.get("pendientes_sombra_24h", []):
            ant_h = (ahora_ts - item.get("ts_unix", ahora_ts)) / 3600.0
            sym = item.get("symbol", "")
            p_veto = float(item.get("precio_veto", 0))
            if not sym or p_veto <= 0:
                continue

            if ant_h < 6.0:
                restantes.append(item)
                continue

            p_vivo = float(mapa_mkt.get(sym, {}).get("precio", p_veto))
            max_post = p_vivo
            min_post = p_vivo
            try:
                lim = min(int(ant_h) + 2, 26)
                k1h = binance_get_json(session, "klines", {"symbol": sym, "interval": "1h", "limit": lim}, timeout=5)
                if isinstance(k1h, list) and k1h:
                    max_post = max(max_post, max(float(x[2]) for x in k1h))
                    min_post = min(min_post, min(float(x[3]) for x in k1h))
            except Exception:
                pass

            sub_max = ((max_post - p_veto) / p_veto) * 100.0
            cai_max = ((min_post - p_veto) / p_veto) * 100.0
            paso = item.get("paso_fallido", "")

            if sub_max >= 18.0:
                m["oportunidades_perdidas_20"] += 1
                if "A4" in paso:
                    u["min_ratio_vol_1h"] = round(max(1.30, u["min_ratio_vol_1h"] - 0.05), 2)
                    u["min_pista_libre_pct"] = round(max(10.0, u["min_pista_libre_pct"] - 0.5), 1)
                elif "A5" in paso:
                    u["min_ob_ratio"] = round(max(1.05, u["min_ob_ratio"] - 0.03), 2)
                    u["max_concentracion_muro_pct"] = round(min(44.0, u["max_concentracion_muro_pct"] + 1.0), 1)
                elif "A6" in paso:
                    u["min_taker_buy_pct"] = round(max(51.0, u["min_taker_buy_pct"] - 0.5), 1)
                    u["min_whale_buy_pct"] = round(max(50.0, u["min_whale_buy_pct"] - 0.5), 1)
                self._actualizar_moneda(sym, exito=True, var_pct=sub_max)
                self.log_bitacora("APRENDIZAJE_FALSO_NEGATIVO_20", {
                    "symbol": sym, "subida_perdida_pct": round(sub_max, 2), "paso": paso, "umbrales": u
                })
            elif cai_max <= -4.0 and sub_max < 6.0:
                m["vetos_acertados"] += 1
                self.log_bitacora("APRENDIZAJE_VETO_ACERTADO", {
                    "symbol": sym, "caida_evitada_pct": round(cai_max, 2), "paso": paso
                })
            elif ant_h < 24.0:
                restantes.append(item)

        self.data["pendientes_sombra_24h"] = restantes[-140:]

    def calibrar_embudo_ciclo(self, conteo_cuellos: dict) -> str:
        """
        Autocrítica inmediata por ciclo: si los Asistentes de Etapa aprobaron >=3 monedas
        pero 0 pasaron a los Traders, detecta el filtro que más bloqueó y lo relaja suavemente.
        """
        if not conteo_cuellos:
            return "Sin cuellos de botella críticos en este ciclo."

        filtro_top, cant_top = max(conteo_cuellos.items(), key=lambda x: x[1])
        u = self.umbrales
        m = self.data["metricas_globales"]
        ajuste_txt = ""

        if filtro_top == "A4_Vol_Pista" and u["min_ratio_vol_1h"] > 1.30:
            u["min_ratio_vol_1h"] = round(max(1.30, u["min_ratio_vol_1h"] - 0.08), 2)
            u["min_pista_libre_pct"] = round(max(10.0, u["min_pista_libre_pct"] - 1.0), 1)
            ajuste_txt = f"Relajado A4 -> Vol1h>={u['min_ratio_vol_1h']}x y Pista>={u['min_pista_libre_pct']}%"
        elif filtro_top == "A5_Libro_Muros" and u["min_ob_ratio"] > 1.05:
            u["min_ob_ratio"] = round(max(1.05, u["min_ob_ratio"] - 0.05), 2)
            u["max_concentracion_muro_pct"] = round(min(44.0, u["max_concentracion_muro_pct"] + 2.0), 1)
            ajuste_txt = f"Relajado A5 -> OB>={u['min_ob_ratio']}x y MuroMax<={u['max_concentracion_muro_pct']}%"
        elif filtro_top == "A6_Cinta_Ballenas" and u["min_taker_buy_pct"] > 51.0:
            u["min_taker_buy_pct"] = round(max(51.0, u["min_taker_buy_pct"] - 0.8), 1)
            u["min_whale_buy_pct"] = round(max(50.0, u["min_whale_buy_pct"] - 0.8), 1)
            ajuste_txt = f"Relajado A6 -> Taker>={u['min_taker_buy_pct']}% y Ballenas>={u['min_whale_buy_pct']}%"
        elif filtro_top == "FOMO_15m" and u["max_distancia_ma7_15m_pct"] < 4.80:
            u["max_distancia_ma7_15m_pct"] = round(min(4.80, u["max_distancia_ma7_15m_pct"] + 0.30), 2)
            ajuste_txt = f"Relajado Timing 15m -> DistMA7<={u['max_distancia_ma7_15m_pct']}%"
        elif filtro_top == "A3_Medias_1D":
            ajuste_txt = "Bypass A3 activo para monedas con >=2 Asistentes de Etapa; solo 1 Asistente sigue exigiendo A3."
        else:
            ajuste_txt = f"Umbrales en piso seguro; {filtro_top} protegió de señales débiles ({cant_top} vetos)."

        m["ajustes_autocritica_ciclo"] = int(m.get("ajustes_autocritica_ciclo", 0)) + 1
        self.log_bitacora("AUTOCRITICA_EMBUDO_CICLO", {
            "cuello_principal": filtro_top,
            "vetos_en_cuello": cant_top,
            "accion": ajuste_txt,
            "umbrales_actuales": u
        })
        return f"Cuello principal: {filtro_top} ({cant_top} frenadas) ➔ {ajuste_txt}"

    def _actualizar_moneda(self, symbol: str, exito: bool, var_pct: float):
        mem = self.data["memoria_monedas"].setdefault(symbol, {
            "eventos": 0, "positivos": 0, "negativos": 0, "ajuste_score": 0.0
        })
        mem["eventos"] += 1
        if exito:
            mem["positivos"] += 1
            mem["ajuste_score"] = round(min(25.0, mem["ajuste_score"] + (4.0 if var_pct >= 18.0 else 2.0)), 1)
        else:
            mem["negativos"] += 1
            mem["ajuste_score"] = round(max(-35.0, mem["ajuste_score"] - 5.0), 1)

    def registrar_cierre_y_aprender(self, pos_cerrada: dict):
        sym = pos_cerrada.get("symbol", "")
        patron = pos_cerrada.get("patron_detectado", "ESCALADA_GANADORAS_24H")
        pnl_pct = float(pos_cerrada.get("pnl_pct", 0.0))
        p_ent = float(pos_cerrada.get("precio_entrada", 0.0))
        p_max = float(pos_cerrada.get("precio_maximo", p_ent))
        max_pct = (((p_max - p_ent) / p_ent) * 100.0 - COMISION_SPOT_TOTAL_PCT) if p_ent > 0 else pnl_pct

        m = self.data["metricas_globales"]
        u = self.umbrales
        m["total_operadas"] += 1
        ganada = pnl_pct > 0.4

        if ganada:
            m["total_ganadas"] += 1
        else:
            u["min_ratio_vol_1h"] = round(min(2.60, u["min_ratio_vol_1h"] + 0.04), 2)
            u["min_ob_ratio"] = round(min(1.65, u["min_ob_ratio"] + 0.02), 2)
            u["min_taker_buy_pct"] = round(min(62.0, u["min_taker_buy_pct"] + 0.4), 1)
            u["min_whale_buy_pct"] = round(min(62.0, u["min_whale_buy_pct"] + 0.4), 1)

        if max_pct >= 20.0:
            m["runners_20_logrados"] += 1

        if patron in self.data["pesos_patrones"]:
            p_data = self.data["pesos_patrones"][patron]
            p_data["ops"] += 1
            if ganada:
                p_data["ganadas"] += 1
                p_data["bonus"] = round(min(35.0, p_data["bonus"] + 1.5), 1)
            else:
                p_data["bonus"] = round(max(-15.0, p_data["bonus"] - 2.0), 1)
            if max_pct >= 20.0:
                p_data["runners_20"] += 1

        self._actualizar_moneda(sym, exito=ganada, var_pct=max_pct)
        self.log_bitacora("CIERRE_OPERACION", {
            "symbol": sym, "trader": pos_cerrada.get("trader_asignado", ""),
            "patron": patron, "pnl_pct": pnl_pct, "max_pct": round(max_pct, 2),
            "motivo": pos_cerrada.get("motivo_cierre", "")
        })

    def calibrar_desde_autopsia(self, symbol: str, veredicto: str, var_max_post: float):
        u = self.umbrales
        m = self.data["metricas_globales"]
        if "STOP_PREMATURO" in veredicto and var_max_post >= 10.0:
            m["stops_prematuros"] += 1
            u["stop_base_pct"] = round(max(-4.50, u["stop_base_pct"] - 0.15), 2)
        elif "STOP_SALVADOR" in veredicto:
            m["stops_salvadores"] += 1
            u["stop_base_pct"] = round(min(-2.40, u["stop_base_pct"] + 0.10), 2)
        self.log_bitacora("AUTOPSIA_24H_CALIBRACION", {
            "symbol": symbol, "veredicto": veredicto, "var_max_post": var_max_post, "stop_base_pct": u["stop_base_pct"]
        })

    def resumen_corto(self) -> str:
        m = self.data["metricas_globales"]
        u = self.umbrales
        tasa = round((m["total_ganadas"] / m["total_operadas"]) * 100, 1) if m["total_operadas"] > 0 else 0.0
        return (
            f"🧬 Cerebro v{self.data.get('version_ciclo', 1)} | Acierto: {tasa}% ({m['total_ganadas']}/{m['total_operadas']}) | "
            f"Runners +20%: {m['runners_20_logrados']} | Vetos OK: {m['vetos_acertados']} | "
            f"Vol1h>={u['min_ratio_vol_1h']}x | Taker>={u['min_taker_buy_pct']}% | Stop:{u['stop_base_pct']}%"
        )


# ==============================================================================
# CÉLULA 1 (EQUIPO EMPRESA): 4 ASISTENTES INTERNOS Y TÉCNICOS (A1, A2, A3, A4)
# ==============================================================================

def _asistente_leer_excel_ganadoras():
    aciertos_excel = {}
    if not os.path.exists(EXCEL_GANADORAS_FILE):
        return aciertos_excel
    try:
        wb = openpyxl.load_workbook(EXCEL_GANADORAS_FILE, data_only=True)
        for sheet_name in ("DETALLE_OPERACIONES", "2_AUDITORIA_EVOLUCION_20"):
            if sheet_name in wb.sheetnames:
                ws = wb[sheet_name]
                for r in range(2, ws.max_row + 1):
                    mon = str(ws.cell(row=r, column=2).value or "").strip().upper()
                    if not mon:
                        continue
                    sym = mon if mon.endswith("USDT") else f"{mon}USDT"
                    col_val = 7 if sheet_name == "DETALLE_OPERACIONES" else 8
                    sub_max = float(ws.cell(row=r, column=col_val).value or 0.0)
                    if sym not in aciertos_excel or sub_max > aciertos_excel[sym]:
                        aciertos_excel[sym] = round(sub_max, 2)
    except Exception:
        pass
    return aciertos_excel


def _extraer_diagnosticos_reporte_ia(ruta_json: str) -> tuple:
    """Lee un reporte_ia_*.json de los motores hijos y extrae resumen global + dictámenes por símbolo."""
    data = cargar_json_seguro(ruta_json)
    if not isinstance(data, dict) or not data:
        return "", {}

    resumen = ""
    for k in ("resumen_ia", "diagnostico_general", "veredicto", "resumen", "conclusion", "analisis_global"):
        val = data.get(k)
        if isinstance(val, str) and val.strip():
            resumen = val.strip()[:200]
            break

    por_moneda = {}
    for k, v in data.items():
        if isinstance(k, str) and k.endswith("USDT") and isinstance(v, dict):
            por_moneda[k] = v
        elif isinstance(v, dict):
            for sub_k, sub_v in v.items():
                if isinstance(sub_k, str) and sub_k.endswith("USDT") and isinstance(sub_v, dict):
                    por_moneda[sub_k] = sub_v
        elif isinstance(v, list):
            for item in v:
                if isinstance(item, dict):
                    s_item = str(item.get("symbol") or item.get("par") or item.get("moneda") or "").upper().strip()
                    if s_item:
                        sym_norm = s_item if s_item.endswith("USDT") else f"{s_item}USDT"
                        por_moneda[sym_norm] = item

    return resumen, por_moneda


def asistente_auditar_post_cierre(mapa_mkt, plan, cerebro: CerebroEvolutivo):
    """Autopsia Post-Cierre 24h: evalúa cada cierre y retroalimenta al Cerebro Evolutivo y al Jefe Supervisor."""
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
                if not c.get("calibrada_en_cerebro", False):
                    c["calibrada_en_cerebro"] = True
                    cerebro.calibrar_desde_autopsia(sym, c["veredicto_autopsia"], var_max_post)

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
            f"Autopsia 24h: {stops_salvadores_sem} salvadores | "
            f"{stops_prematuros_sem} prematuros | {cosechas_optimas_sem} óptimas"
        )
    }


def ejecutar_asistente_inteligencia(mapa_mkt, plan, cerebro: CerebroEvolutivo):
    """
    Recopila toda la inteligencia interna del ecosistema:
    1) Cazador Táctico (E1 + reporte_ia_tactico.json)
    2) Pre-Explosión (E2 + reporte_ia_pre_explosion.json)
    3) Monedas Ganadoras (24h + reporte_ia_ganadoras.json + Excel Verdes)
    4) Órdenes aprobadas del Cerebro Central (cerebro_matriz_central.json)
    """
    perlas = cargar_json_seguro(HISTORIAL_PERLAS_FILE)
    ganadoras = cargar_json_seguro(HISTORIAL_GANADORAS_FILE)
    pre_exp_extra = cargar_json_seguro(DATOS_PRE_EXPLOSION_FILE)
    cerebro_central = cargar_json_seguro(CEREBRO_FEED_JSON)
    aciertos_excel_gan = _asistente_leer_excel_ganadoras()
    stats_autopsia = asistente_auditar_post_cierre(mapa_mkt, plan, cerebro)

    res_ia_gan, ia_gan_map = _extraer_diagnosticos_reporte_ia(REPORTE_IA_GANADORAS_FILE)
    res_ia_tac, ia_tac_map = _extraer_diagnosticos_reporte_ia(REPORTE_IA_TACTICO_FILE)
    res_ia_pre, ia_pre_map = _extraer_diagnosticos_reporte_ia(REPORTE_IA_PRE_EXPLOSION_FILE)

    if isinstance(cerebro_central, dict) and cerebro_central.get("stop_calibrado_pct"):
        try:
            stop_cc = float(cerebro_central["stop_calibrado_pct"])
            if -4.5 <= stop_cc <= -2.4:
                cerebro.umbrales["stop_base_pct"] = stop_cc
        except Exception:
            pass

    ordenes_central_map = {}
    if isinstance(cerebro_central, dict):
        for oc in cerebro_central.get("ordenes_ejecutar", []):
            sym_oc = str(oc.get("symbol", "")).upper().strip()
            if sym_oc:
                ordenes_central_map[sym_oc] = oc

    graduadas = dict(perlas.get("graduadas_pre_explosion", {})) if isinstance(perlas, dict) else {}
    if isinstance(pre_exp_extra, dict):
        for k, v in pre_exp_extra.items():
            if isinstance(k, str) and k.endswith("USDT") and isinstance(v, dict):
                graduadas.setdefault(k, v)
            elif isinstance(v, dict):
                for sub_k, sub_v in v.items():
                    if isinstance(sub_k, str) and sub_k.endswith("USDT") and isinstance(sub_v, dict):
                        graduadas.setdefault(sub_k, sub_v)

    posta = perlas.get("posta", {}) if isinstance(perlas, dict) else {}
    reg_verdes = ganadoras.get("registro_verdes", {}) if isinstance(ganadoras, dict) else {}

    resumen_macro_bots = []
    notas_extra_monedas = {}
    fuentes_leidas = []

    if posta:
        fuentes_leidas.append(f"Cazador E1 ({len(posta)})")
    if graduadas:
        fuentes_leidas.append(f"Pre-Explosión E2 ({len(graduadas)})")
    if reg_verdes:
        fuentes_leidas.append(f"Ganadoras ({len(reg_verdes)})")
    if aciertos_excel_gan:
        fuentes_leidas.append(f"Excel Verdes ({len(aciertos_excel_gan)})")
    if ordenes_central_map:
        fuentes_leidas.append(f"Cerebro Central ({len(ordenes_central_map)} órdenes IA)")
    if ia_tac_map or res_ia_tac:
        fuentes_leidas.append(f"IA Táctico ({len(ia_tac_map)})")
    if ia_pre_map or res_ia_pre:
        fuentes_leidas.append(f"IA Pre-Exp ({len(ia_pre_map)})")
    if ia_gan_map or res_ia_gan:
        fuentes_leidas.append(f"IA Ganadoras ({len(ia_gan_map)})")

    for tag_ia, r_txt in [
        ("IA Ganadoras", res_ia_gan),
        ("IA Táctico", res_ia_tac),
        ("IA Pre-Explosión", res_ia_pre),
    ]:
        if r_txt:
            resumen_macro_bots.append(f"[{tag_ia}] {r_txt[:140]}")

    for tag_ia, mapa_ia in [
        ("IA Ganadoras", ia_gan_map),
        ("IA Táctico", ia_tac_map),
        ("IA Pre-Explosión", ia_pre_map),
    ]:
        for sym_k, info_k in mapa_ia.items():
            txt_k = (
                info_k.get("diagnostico_ia")
                or info_k.get("veredicto_ia")
                or info_k.get("razon_ia")
                or info_k.get("analisis")
                or info_k.get("recomendacion")
                or ""
            )
            if isinstance(txt_k, str) and txt_k.strip():
                notas_extra_monedas.setdefault(sym_k, []).append(f"{tag_ia}: {txt_k.strip()[:120]}")

    archivos_ignorar = {
        PLAN_SEMANAL_FILE, CEREBRO_EVOLUTIVO_FILE, CEREBRO_FEED_JSON, "package.json",
        "package-lock.json", "tsconfig.json", "resumen_topic_config.json", "matriz_topic_config.json",
        HISTORIAL_PERLAS_FILE, HISTORIAL_GANADORAS_FILE, DATOS_PRE_EXPLOSION_FILE,
        REPORTE_IA_GANADORAS_FILE, REPORTE_IA_TACTICO_FILE, REPORTE_IA_PRE_EXPLOSION_FILE
    }
    for ruta in sorted(glob.glob("*.json")):
        if ruta in archivos_ignorar:
            continue
        nombre_l = ruta.lower()
        if "perdedor" in nombre_l or "loser" in nombre_l or "negra" in nombre_l:
            continue
        data = cargar_json_seguro(ruta)
        if not isinstance(data, dict) or not data:
            continue
        fuentes_leidas.append(ruta)

        if any(tag in nombre_l for tag in ("sentimiento", "noticia", "central", "inteligencia", "mercado", "macro", "clima", "sentinel")):
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

    universo_bots = set(graduadas.keys()) | set(posta.keys()) | set(reg_verdes.keys()) | set(ordenes_central_map.keys())
    boletin_asistente = {
        "fuentes_auditadas": fuentes_leidas,
        "total_monedas_rastreadas": len(universo_bots),
        "ordenes_cerebro_central": len(ordenes_central_map),
        "alertas_macro": resumen_macro_bots[:6],
        "reportes_ia_motores": {
            "ganadoras": res_ia_gan or "Activo",
            "tactico": res_ia_tac or "Activo",
            "pre_explosion": res_ia_pre or "Activo"
        },
        "autopsia_24h": stats_autopsia,
        "cerebro_resumen": cerebro.resumen_corto(),
        "autocritica_ciclo": "Pendiente auditoría de embudo",
        "resumen_ejecutivo": (
            f"Mesa 6 Asistentes integró {len(fuentes_leidas)} fuentes ({len(ordenes_central_map)} órdenes Cerebro Central + "
            f"{len(universo_bots)} señales + ~400 pares Binance). {stats_autopsia['resumen_autopsia']}."
        )
    }

    eco = {
        "perlas": perlas,
        "ganadoras": ganadoras,
        "aciertos_excel_ganadoras": aciertos_excel_gan,
        "ordenes_central_map": ordenes_central_map,
        "graduadas": graduadas,
        "posta": posta,
        "reg_verdes": reg_verdes,
        "ia_gan_map": ia_gan_map,
        "ia_tac_map": ia_tac_map,
        "ia_pre_map": ia_pre_map,
        "res_ia_gan": res_ia_gan,
        "res_ia_tac": res_ia_tac,
        "res_ia_pre": res_ia_pre,
        "macro_bots": resumen_macro_bots[:6],
        "notas_extra": notas_extra_monedas,
        "boletin_asistente": boletin_asistente
    }
    return boletin_asistente, eco


def asistente_1_forense_cazador_preexplosion(sym, p_actual, eco, plan=None, es_inyeccion_binance=False):
    """
    ASISTENTE 1 (EQUIPO EMPRESA):
    Audita la tríada principal + Consenso IA del Cerebro Central:
    - Si >= 2 Asistentes de Etapa corroboran la moneda (ej. E1 APTA_ENTRADA_ESCALONADA >=85% + E2 COMPRA_CONFIRMADA_MADURACION),
      la marca como Setup de Rebote/Explosión Corroborado con Bypass de Medias Diarias (A3) y Stop Sugerido de Etapa (-3.5%).
    """
    grad = eco["graduadas"].get(sym, {})
    post = eco["posta"].get(sym, {})
    verd = eco["reg_verdes"].get(sym, {})
    ia_g = eco.get("ia_gan_map", {}).get(sym, {})
    ia_t = eco.get("ia_tac_map", {}).get(sym, {})
    ia_p = eco.get("ia_pre_map", {}).get(sym, {})
    orden_cc = eco.get("ordenes_central_map", {}).get(sym, {})
    sub_excel_gan = float(eco.get("aciertos_excel_ganadoras", {}).get(sym, 0.0))

    p_ref = float(grad.get("precio_ref") or post.get("precio_ref") or verd.get("precio_entrada") or p_actual or 0)
    var_desde_radar = round(((p_actual - p_ref) / p_ref) * 100, 2) if p_ref > 0 and p_actual > 0 else 0.0

    semaforo = str(
        ia_p.get("semaforo") or ia_t.get("semaforo") or grad.get("semaforo") or post.get("semaforo") or ("VERDE" if (verd or ia_g or orden_cc) else "N/D")
    ).upper()
    etapa = int(post.get("etapa", grad.get("etapa", ia_t.get("etapa", 0))) or 0)
    blindaje = int(
        ia_p.get("blindaje_pct") or grad.get("blindaje_pct") or post.get("blindaje_etapa1")
        or grad.get("probabilidad_pct") or (88 if orden_cc else (84 if (verd or ia_g) else 72))
    )
    cert_e1 = bool(grad.get("certificada_etapa1") or post.get("certificada_etapa1") or ia_t.get("certificada_ia"))
    cert_e2 = bool(grad.get("certificada_ia") or ia_p.get("certificada_ia"))

    cazador_en_verde = bool(post) or bool(ia_t) or bool(verd) or ("VERDE" in semaforo)
    confirmada_pre_explosion = (bool(grad) or bool(ia_p) or bool(orden_cc)) and (
        ("VERDE" in semaforo) or cert_e1 or cert_e2 or blindaje >= 75
    )

    tesis_textos = []
    if orden_cc:
        tesis_textos.append(f"Cerebro Central IA {orden_cc.get('votos_ia', 2)}/3 ({orden_cc.get('orden', '')})")
    for fuente in (ia_p, ia_t, ia_g, grad, post, verd):
        for clave in ("diagnostico_ia", "veredicto_ia", "razon_ia", "analisis_ia", "motivo", "razon", "patron", "detalle", "estado"):
            val = fuente.get(clave)
            if isinstance(val, str) and val.strip() and val.strip() not in tesis_textos:
                tesis_textos.append(val.strip())
    if sym in eco["notas_extra"]:
        for n_x in eco["notas_extra"][sym]:
            if n_x not in tesis_textos:
                tesis_textos.append(n_x)

    blob_estados = " ".join(tesis_textos).upper()
    tiene_etiqueta_corroborada = (
        ("APTA_ENTRADA_ESCALONADA" in blob_estados)
        or ("COMPRA_CONFIRMADA_MADURACION" in blob_estados)
        or ("EJECUTAR" in blob_estados)
    )

    estado_hist_verde = str(ia_g.get("estado") or verd.get("estado") or "SIN_REGISTRO").upper()
    max_hist_verde = max(float(verd.get("max_ganancia_pct", verd.get("ganancia_pct", 0.0))), sub_excel_gan)
    en_ganadoras_activo = bool(verd) or bool(ia_g) or (sub_excel_gan >= 5.0)

    stops_previos_semana = 0
    if plan:
        for c in plan.get("historial_cierres", []):
            if c.get("semana_id") == plan.get("semana_id") and c.get("symbol") == sym and float(c.get("pnl_usd", 0)) < 0:
                stops_previos_semana += 1

    bloqueada_por_reincidencia = (stops_previos_semana > MAX_REENTRADAS_SEMANA)
    es_reentrada_habilitada = (1 <= stops_previos_semana <= MAX_REENTRADAS_SEMANA)

    votos_etapa_detectados = max(
        int(orden_cc.get("votos_ia", 0) or 0),
        sum([
            1 if (bool(post) or bool(ia_t)) else 0,
            1 if confirmada_pre_explosion else 0,
            1 if en_ganadoras_activo else 0
        ])
    )
    confluencia_multi_bot = sum([
        1 if (bool(post) or bool(ia_t)) else 0,
        1 if confirmada_pre_explosion else 0,
        1 if en_ganadoras_activo else 0,
        1 if (bool(ia_p) or bool(ia_t) or bool(ia_g) or bool(orden_cc)) else 0
    ])

    corroborada_etapa_2plus = (
        (votos_etapa_detectados >= 2)
        or (tiene_etiqueta_corroborada and blindaje >= 85)
    )

    stop_sugerido_etapa = float(
        orden_cc.get("stop_sugerido_pct")
        or grad.get("stop_sugerido_pct")
        or post.get("stop_sugerido_pct")
        or STOP_REBOTE_CORROBORADO_PCT
    )
    if not (-4.8 <= stop_sugerido_etapa <= -2.0):
        stop_sugerido_etapa = STOP_REBOTE_CORROBORADO_PCT

    if bloqueada_por_reincidencia:
        ok_a1 = False
        patron = "VETADA_REINCIDENCIA"
        dictamen = f"⛔ A1 VETA: Agotó re-entrada semanal ({stops_previos_semana} stops)."
    elif "ROJO" in semaforo and not es_inyeccion_binance and not corroborada_etapa_2plus:
        ok_a1 = False
        patron = "VETADA_SEMAFORO_ROJO"
        dictamen = f"⛔ A1 VETA: Semáforo ROJO en Cazador/Pre-Explosión ({var_desde_radar:+.1f}%)."
    elif (cazador_en_verde or confirmada_pre_explosion) and var_desde_radar < -2.8 and not es_inyeccion_binance and not corroborada_etapa_2plus:
        ok_a1 = False
        patron = "VETADA_ESTANCADA_BAJA"
        dictamen = f"⛔ A1 VETA: Señal E1/E2 retrocediendo ({var_desde_radar:+.1f}% desde radar)."
    elif corroborada_etapa_2plus:
        ok_a1 = True
        patron = "REBOTE_EXPLOSION_CORROBORADO_ETAPA"
        dictamen = (
            f"✅ A1 CORROBORADA ({votos_etapa_detectados} Asist. Etapa | Blindaje {blindaje}%) "
            f"➔ Setup Rebote/Explosión (Bypass A3 + Stop {stop_sugerido_etapa:.1f}%)"
        )
    elif confirmada_pre_explosion:
        ok_a1 = True
        patron = "DISPARO_PRE_EXPLOSION_E2"
        dictamen = f"✅ A1 OK [1 Asist. Etapa: Pre-Explosión E2] | Blindaje:{blindaje}% | Pasa a filtro A3..A6"
    elif cazador_en_verde and (var_desde_radar >= 1.2 or en_ganadoras_activo):
        ok_a1 = True
        patron = "ACUMULACION_ASCENDENTE_CAZADOR_E1"
        dictamen = f"✅ A1 OK [1 Asist. Etapa: Cazador E{etapa}] | Radar:{var_desde_radar:+.1f}% | Pasa a filtro A3..A6"
    elif es_inyeccion_binance:
        ok_a1 = True
        patron = "RUPTURA_DIRECTA_BINANCE_A5"
        dictamen = "✅ A1 OK [Ruptura Directa Binance A5] | Pasa a filtro A3..A6"
    elif en_ganadoras_activo:
        ok_a1 = True
        patron = "ESCALADA_GANADORAS_24H"
        dictamen = f"✅ A1 OK [1 Asist. Etapa: Ganadoras 24h] | HistVerdes:{max_hist_verde:+.1f}% | Pasa a filtro A3..A6"
    else:
        ok_a1 = False
        patron = "INCOMPLETA_E1_E2"
        dictamen = f"⏳ A1 ESPERA: Señal E{etapa} sin despegue ni confirmación Pre-Explosión ({var_desde_radar:+.1f}%)."

    carril_vip = ok_a1 and (-3.0 <= var_desde_radar <= 13.0) and (corroborada_etapa_2plus or confirmada_pre_explosion or es_inyeccion_binance)
    resumen_corto = (
        f"Patrón:{patron} | VotosEtapa:{votos_etapa_detectados} | "
        f"BypassA3:{'SÍ' if corroborada_etapa_2plus else 'NO'} | Radar:{var_desde_radar:+.1f}%"
    )

    return {
        "check_a1": ok_a1,
        "patron_detectado": patron,
        "corroborada_etapa_2plus": corroborada_etapa_2plus,
        "votos_etapa": votos_etapa_detectados,
        "stop_sugerido_etapa": stop_sugerido_etapa,
        "cazador_en_verde": cazador_en_verde,
        "confirmada_pre_explosion": confirmada_pre_explosion,
        "es_inyeccion_binance": es_inyeccion_binance,
        "es_orden_cerebro_central": bool(orden_cc),
        "semaforo_radar": semaforo,
        "etapa_cazador": etapa,
        "blindaje_pct": blindaje,
        "doble_certificada": corroborada_etapa_2plus or (cert_e1 and cert_e2),
        "en_ganadoras_activo": en_ganadoras_activo,
        "carril_vip_radar": carril_vip,
        "es_reentrada_habilitada": es_reentrada_habilitada,
        "stops_previos_semana": stops_previos_semana,
        "confluencia_multi_bot": confluencia_multi_bot,
        "reincidente_stop_semana": bloqueada_por_reincidencia,
        "tiene_respaldo_bots": ok_a1,
        "precio_referencia_radar": p_ref,
        "var_desde_deteccion_radar_pct": var_desde_radar,
        "estado_historial_ganadoras": estado_hist_verde,
        "max_ganancia_historica_pct": max_hist_verde,
        "alertada_en_perdedoras": False,
        "tesis_previa_bots": " | ".join(tesis_textos)[:260] if tesis_textos else "Telemetría directa E1/E2/Ganadoras/Binance",
        "dictamen_asistente": dictamen,
        "resumen_corto": resumen_corto
    }


def asistente_2_confluencia_velocidad(mkt: dict, dossier_a1: dict) -> dict:
    """
    ASISTENTE 2 (EQUIPO EMPRESA):
    Audita velocidad diaria (+0.8% si viene corroborada >=2 Asistentes Etapa para atrapar rebotes tempranos,
    +3.0% si es señal simple) y liquidez base 24h (>= $3.0M).
    """
    cambio_24h = float(mkt.get("cambio_24h", 0.0))
    vol_24h = float(mkt.get("vol_24h", 0.0))
    corroborada_2plus = bool(dossier_a1.get("corroborada_etapa_2plus", False))
    min_chg = 0.8 if corroborada_2plus else 3.0

    if vol_24h < 3_000_000:
        return {"ok": False, "motivo": f"A2 VETA: Liquidez 24h baja (${vol_24h/1e6:.1f}M < $3.0M)"}
    if cambio_24h < min_chg:
        return {"ok": False, "motivo": f"A2 ESPERA: Sin aceleración diaria ({cambio_24h:+.1f}% < +{min_chg:.1f}%)"}
    if cambio_24h > 28.0:
        return {"ok": False, "motivo": f"A2 VETA: Movimiento extendido (+{cambio_24h:.1f}% > +28%)"}

    conf = int(dossier_a1.get("votos_etapa", dossier_a1.get("confluencia_multi_bot", 1)))
    return {
        "ok": True,
        "confluencia": conf,
        "motivo": f"A2 OK: +24h {cambio_24h:+.1f}% | Vol ${vol_24h/1e6:.1f}M | Etapa {conf}/3"
    }


def analizar_velas_tf(session, symbol, interval="1h", limit=105):
    """Analiza medias móviles (MA7, MA25, MA99), RSI, volumen, rechazo de mechas y Fibonacci."""
    k = binance_get_json(session, "klines", {"symbol": symbol, "interval": interval, "limit": limit}, timeout=7)
    if not isinstance(k, list) or len(k) < 15:
        return {
            "ok": False, "rsi": 50.0, "vol_ratio": 1.0, "var_ultima": 0.0,
            "var_3velas": 0.0, "rechazo_techo": False, "escalera_ma": False,
            "ruptura_ma7_25": False, "ma7": 0.0, "ma25": 0.0, "ma99": 0.0, "fib": {"ok": False}
        }

    cierres = [float(x[4]) for x in k]
    aperturas = [float(x[1]) for x in k]
    maximos = [float(x[2]) for x in k]
    minimos = [float(x[3]) for x in k]
    vols = [float(x[7]) for x in k]
    p_act = cierres[-1]

    ma7 = sum(cierres[-7:]) / 7.0
    ma25 = sum(cierres[-min(25, len(cierres)):]) / min(25, len(cierres))
    ma99 = sum(cierres[-min(99, len(cierres)):]) / min(99, len(cierres))

    escalera_ma = (len(cierres) >= 99) and (p_act >= ma7 * 0.992) and (ma7 > ma25 > ma99)
    ruptura_ma7_25 = (p_act > ma7) and (p_act > ma25)

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

    mechas_altas = 0
    for idx_m in range(-3, 0):
        rango_v = maximos[idx_m] - minimos[idx_m]
        mecha_s = maximos[idx_m] - max(cierres[idx_m], aperturas[idx_m])
        if rango_v > 0 and (mecha_s / rango_v) >= 0.45:
            mechas_altas += 1
    rechazo_techo = (mechas_altas >= 2)

    swing_high = max(maximos[-48:])
    swing_low = min(minimos[-48:])
    rango_fib = swing_high - swing_low
    fib_data = {"ok": False}

    if rango_fib > 0:
        ratio_retroceso = round((swing_high - p_act) / rango_fib, 3)
        fib_618 = swing_high - (rango_fib * 0.618)
        ext_1618 = swing_low + (rango_fib * 1.618)
        en_zona_dorada = (0.35 <= ratio_retroceso <= 0.62)
        en_tramo_alcista = (0.08 <= ratio_retroceso < 0.35)
        en_soporte_profundo = (ratio_retroceso > 0.62)

        if en_zona_dorada:
            zona_txt = f"Zona Dorada Fib ({ratio_retroceso:.2f})"
        elif en_soporte_profundo:
            zona_txt = f"Soporte Profundo Fib ({ratio_retroceso:.2f})"
        elif en_tramo_alcista:
            zona_txt = f"Tramo Alcista Fib ({ratio_retroceso:.2f})"
        else:
            zona_txt = f"Punta Impulso Fib ({ratio_retroceso:.2f})"

        fib_data = {
            "ok": True,
            "ratio": ratio_retroceso,
            "zona_txt": zona_txt,
            "en_zona_dorada": en_zona_dorada,
            "en_tramo_alcista": en_tramo_alcista,
            "en_soporte_profundo": en_soporte_profundo,
            "fib_618": fib_618,
            "ext_1618": ext_1618
        }

    return {
        "ok": True,
        "precio": p_act,
        "ma7": ma7,
        "ma25": ma25,
        "ma99": ma99,
        "escalera_ma": escalera_ma,
        "ruptura_ma7_25": ruptura_ma7_25,
        "rsi": rsi,
        "vol_ratio": vol_ratio,
        "var_ultima": var_ultima,
        "var_3velas": var_3velas,
        "rechazo_techo": rechazo_techo,
        "fib": fib_data
    }


def asistente_3_estructura_limpia(v15: dict, v1d: dict, v4h: dict, dossier_a1: dict) -> dict:
    """
    ASISTENTE 3 (EQUIPO EMPRESA):
    - Si >= 2 Asistentes de Etapa corroboraron la moneda: BYPASS automático de medias diarias (A3)
      porque se opera como setup de rebote/explosión corroborado.
    - Si solo 1 Asistente de Etapa la recomienda: exige escalera MA7>MA25>MA99 en 15m + ruptura MA7/MA25 diaria.
    """
    if dossier_a1.get("corroborada_etapa_2plus"):
        return {
            "ok": True,
            "bypass_a3": True,
            "motivo": f"A3 BYPASS: Rebote/Explosión corroborado ({dossier_a1.get('votos_etapa', 2)} Asist. Etapa)"
        }

    if not v15.get("ok") or not v1d.get("ok"):
        return {"ok": False, "bypass_a3": False, "motivo": "A3 VETA: Sin historial suficiente de velas 15m/1D"}
    if not v15.get("escalera_ma"):
        return {"ok": False, "bypass_a3": False, "motivo": "A3 VETA: Sin escalera MA7>MA25>MA99 en 15m"}
    if v15.get("rechazo_techo"):
        return {"ok": False, "bypass_a3": False, "motivo": "A3 VETA: Mechas superiores de rechazo en 15m (latigazo)"}
    if not v1d.get("ruptura_ma7_25"):
        return {"ok": False, "bypass_a3": False, "motivo": "A3 VETA: Aplastada bajo MA7/MA25 diaria"}

    fib_4h = v4h.get("fib", {})
    if fib_4h.get("ok") and fib_4h.get("en_soporte_profundo"):
        return {"ok": False, "bypass_a3": False, "motivo": "A3 VETA: Estructura 4H en retroceso profundo (>0.62 Fib)"}

    return {
        "ok": True,
        "bypass_a3": False,
        "motivo": "A3 OK: Escalera limpia 15m + ruptura MA7/MA25 diaria"
    }


def asistente_4_combustible_pista(precio: float, v1h: dict, v1d: dict, umbrales: dict, dossier_a1: dict) -> dict:
    """
    ASISTENTE 4 (EQUIPO EMPRESA):
    Verifica combustible de volumen horario. Si viene corroborada >=2 Asistentes de Etapa,
    no bloquea por techo MA99 1D (setup de rebote) y exige volumen horario mínimo de arranque (>= 1.25x).
    """
    corroborada_2plus = bool(dossier_a1.get("corroborada_etapa_2plus", False))
    min_vol = 1.25 if corroborada_2plus else float(umbrales.get("min_ratio_vol_1h", 1.80))
    min_pista = float(umbrales.get("min_pista_libre_pct", 16.0))

    vol_1h = float(v1h.get("vol_ratio", 0.0))
    ma99_1d = float(v1d.get("ma99", 0.0))
    pista_libre_pct = round(((ma99_1d - precio) / precio) * 100.0, 1) if ma99_1d > precio > 0 else 35.0

    if vol_1h < min_vol:
        return {"ok": False, "pista_libre_pct": pista_libre_pct, "motivo": f"A4 VETA: Vol 1h {vol_1h:.2f}x < {min_vol:.2f}x"}
    if not corroborada_2plus and pista_libre_pct < min_pista:
        return {"ok": False, "pista_libre_pct": pista_libre_pct, "motivo": f"A4 VETA: Techo MA99 1D cerca (+{pista_libre_pct:.1f}% < +{min_pista:.1f}%)"}

    tag_pista = "Rebote Corroborado" if corroborada_2plus else f"Pista +{pista_libre_pct:.1f}%"
    return {
        "ok": True,
        "pista_libre_pct": pista_libre_pct,
        "motivo": f"A4 OK: Vol 1h {vol_1h:.2f}x | {tag_pista}"
    }


# ==============================================================================
# CÉLULA 2 (ENLACE BINANCE EN VIVO): ASISTENTE 5 (RADAR/LIBRO) Y ASISTENTE 6 (CINTA)
# ==============================================================================

def asistente_5_barrido_global_binance(mapa_mkt: dict, simbolos_bots: set) -> list:
    candidatas_vivas = []
    for sym, mkt in mapa_mkt.items():
        if sym in simbolos_bots:
            continue
        chg = float(mkt.get("cambio_24h", 0.0))
        vol = float(mkt.get("vol_24h", 0.0))
        if 3.8 <= chg <= 22.0 and vol >= 3_500_000:
            candidatas_vivas.append((sym, vol))
    candidatas_vivas.sort(key=lambda x: x[1], reverse=True)
    return [x[0] for x in candidatas_vivas[:15]]


def asistente_5_auditar_order_book(session, symbol: str, monto_orden_usd: float, umbrales: dict) -> dict:
    min_ob = float(umbrales.get("min_ob_ratio", 1.25))
    max_muro_pct = float(umbrales.get("max_concentracion_muro_pct", 32.0))

    d = binance_get_json(session, "depth", {"symbol": symbol, "limit": 25}, timeout=5)
    if not isinstance(d, dict) or not d.get("bids") or not d.get("asks"):
        return {
            "ok": False, "spread_pct": 0.99, "ratio_ba": 0.0, "liq_ask_015_usd": 0.0,
            "slippage_est_pct": 0.99, "liquidez_real_ok": False, "muro_vendedor": True,
            "sano": False, "motivo": "A5 VETA: Sin respuesta Order Book Binance"
        }

    bids, asks = d["bids"], d["asks"]
    b0, a0 = float(bids[0][0]), float(asks[0][0])
    spread = ((a0 - b0) / b0) * 100 if b0 > 0 else 99.0

    bids_usd = [float(x[0]) * float(x[1]) for x in bids]
    asks_usd = [float(x[0]) * float(x[1]) for x in asks]
    vb = sum(bids_usd)
    va = sum(asks_usd)
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
        tokens_acum += qty
        restante_usd -= nivel_usd

    if restante_usd > 0 or tokens_acum <= 0:
        slippage_est_pct = 0.99
    else:
        precio_vwap = monto_orden_usd / tokens_acum
        slippage_est_pct = round(((precio_vwap - a0) / a0) * 100.0, 3)

    concentracion_muro = (max(asks_usd) / va * 100.0) if va > 0 else 100.0
    muro_vendedor = (concentracion_muro > max_muro_pct)
    liquidez_real_ok = (liq_ask_015 >= MIN_LIQUIDEZ_TOP_ASK_USD and slippage_est_pct <= MAX_SLIPPAGE_EST_PCT)

    if spread > 0.35:
        motivo = f"A5 VETA: Spread alto en vivo ({spread:.2f}%)"
        sano = False
    elif ratio < min_ob:
        motivo = f"A5 VETA: Libro vendedor (OB {ratio:.2f}x < {min_ob:.2f}x)"
        sano = False
    elif muro_vendedor:
        motivo = f"A5 VETA: Muro vendedor en Ask ({concentracion_muro:.0f}% del libro)"
        sano = False
    elif not liquidez_real_ok:
        motivo = f"A5 VETA: Liquidez Ask 0.15% baja (${int(liq_ask_015):,}) o slippage {slippage_est_pct}%"
        sano = False
    else:
        motivo = f"A5 OK: OB {ratio:.2f}x | Liq0.15% ${int(liq_ask_015):,} | Sin muros"
        sano = True

    return {
        "ok": True,
        "spread_pct": round(spread, 3),
        "ratio_ba": ratio,
        "liq_ask_015_usd": round(liq_ask_015, 0),
        "slippage_est_pct": slippage_est_pct,
        "liquidez_real_ok": liquidez_real_ok,
        "muro_vendedor": muro_vendedor,
        "sano": sano,
        "motivo": motivo
    }


def asistente_6_cinta_y_ballenas_binance(session, symbol: str, umbrales: dict) -> dict:
    min_taker = float(umbrales.get("min_taker_buy_pct", 55.0))
    min_whale = float(umbrales.get("min_whale_buy_pct", 54.0))
    min_tpm = float(umbrales.get("min_trades_por_min", 12.0))

    trades = binance_get_json(session, "aggTrades", {"symbol": symbol, "limit": 500}, timeout=6)
    if not isinstance(trades, list) or len(trades) < 80:
        return {"ok": False, "taker_buy_pct": 0.0, "whale_buy_pct": 0.0, "motivo": "A6 VETA: Cinta con pocas operaciones (<80 trades)"}

    mitad = len(trades) // 2
    previos = trades[:mitad]
    actuales = trades[mitad:]

    def _stats(lista):
        buy_u, sell_u = 0.0, 0.0
        montos = []
        for tr in lista:
            usd = float(tr["p"]) * float(tr["q"])
            montos.append(usd)
            if not tr["m"]:
                buy_u += usd
            else:
                sell_u += usd
        pct_b = (buy_u / (buy_u + sell_u + 1e-9)) * 100.0
        return pct_b, montos

    pct_prev, _ = _stats(previos)
    pct_act, montos_act = _stats(actuales)

    montos_ord = sorted(montos_act)
    mediana = montos_ord[len(montos_ord) // 2] if montos_ord else 100.0
    umbral_ballena = max(1000.0, mediana * 3.0)

    w_buy, w_sell = 0.0, 0.0
    for tr in actuales:
        usd = float(tr["p"]) * float(tr["q"])
        if usd >= umbral_ballena:
            if not tr["m"]:
                w_buy += usd
            else:
                w_sell += usd
    total_w = w_buy + w_sell
    pct_whale = (w_buy / total_w * 100.0) if total_w > 0 else pct_act

    dur_min = max((trades[-1]["T"] - trades[0]["T"]) / 60000.0, 0.05)
    tpm = len(trades) / dur_min

    if pct_act < min_taker:
        return {"ok": False, "taker_buy_pct": round(pct_act, 1), "whale_buy_pct": round(pct_whale, 1), "motivo": f"A6 VETA: Taker Buy {pct_act:.1f}% < {min_taker:.1f}%"}
    if pct_act < pct_prev - 7.0:
        return {"ok": False, "taker_buy_pct": round(pct_act, 1), "whale_buy_pct": round(pct_whale, 1), "motivo": f"A6 VETA: Cinta desacelerando ({pct_prev:.0f}%->{pct_act:.0f}%)"}
    if pct_whale < min_whale:
        return {"ok": False, "taker_buy_pct": round(pct_act, 1), "whale_buy_pct": round(pct_whale, 1), "motivo": f"A6 VETA: Ballenas vendiendo ({pct_whale:.1f}% < {min_whale:.1f}%)"}
    if tpm < min_tpm:
        return {"ok": False, "taker_buy_pct": round(pct_act, 1), "whale_buy_pct": round(pct_whale, 1), "motivo": f"A6 VETA: Cinta lenta ({tpm:.1f} ops/min)"}

    return {
        "ok": True,
        "taker_buy_pct": round(pct_act, 1),
        "whale_buy_pct": round(pct_whale, 1),
        "trades_min": round(tpm, 1),
        "motivo": f"A6 OK: Cinta {pct_prev:.0f}%->{pct_act:.0f}% Buy | Ballenas {pct_whale:.0f}% | {tpm:.0f} ops/m"
    }


# ==============================================================================
# NIVEL 2: 3 TRADERS INDEPENDIENTES (1 MONEDA EXCLUSIVA POR TRADER)
# ==============================================================================

def asignar_traders_a_cartera(posiciones: list) -> dict:
    escritorios = {tid: None for tid in NOMBRES_TRADERS}
    sin_asignar = []

    for pos in posiciones[:MAX_TRADERS_SEMANA]:
        tid = pos.get("trader_asignado", "")
        if tid in escritorios and escritorios[tid] is None:
            escritorios[tid] = pos
        else:
            sin_asignar.append(pos)

    for pos in sin_asignar:
        for tid in NOMBRES_TRADERS:
            if escritorios[tid] is None:
                pos["trader_asignado"] = tid
                escritorios[tid] = pos
                break

    return escritorios


def empleado_evaluar_palanca_emergencia(pos, v1m, v15, v1h, fib, pnl_pct, dossier_asistente, cinta_a6=None):
    trader_id = pos.get("trader_asignado", "TRADER")
    p_act = float(pos.get("precio_actual", 0))
    perdio_fib_618 = False
    if fib.get("ok"):
        perdio_fib_618 = (p_act < float(fib["fib_618"]) and float(fib["ratio"]) > 0.65)

    if v1m.get("ok"):
        if (v1m["var_3velas"] <= -1.80 and v1m["vol_ratio"] >= 2.0) or (v1m["var_ultima"] <= -1.40 and v1m["vol_ratio"] >= 2.2):
            return True, (
                f"🚨 SOLICITUD {trader_id} (Desplome 1m): caída {v1m['var_3velas']:+.2f}% en 3m "
                f"(vol {v1m['vol_ratio']}x) en {pnl_pct:+.2f}% neto."
            )

    perdio_ma25_15m = v15.get("ok") and (p_act < float(v15.get("ma25", p_act)) * 0.992)
    cinta_debil = isinstance(cinta_a6, dict) and (not cinta_a6.get("ok", True))
    if pnl_pct <= -2.40 and (perdio_fib_618 or (perdio_ma25_15m and cinta_debil)):
        return True, (
            f"🚨 SOLICITUD {trader_id} (Tesis Invalidada): rompió soporte 15m/Fib + cinta débil en {pnl_pct:+.2f}% neto."
        )

    return False, ""


def mesa_asistentes_y_traders_evaluar_candidatas(session, mapa_mkt, excluidas, eco, plan, cerebro: CerebroEvolutivo):
    """
    Evalúa candidatas en la Mesa de 6 Asistentes y devuelve:
    (lista_top_alternativas, estadisticas_embudo_ciclo)
    """
    umbrales = cerebro.umbrales
    graduadas = eco["graduadas"]
    posta_dict = eco["posta"]
    reg_verdes = eco["reg_verdes"]
    ia_pre_map = eco.get("ia_pre_map", {})
    ia_tac_map = eco.get("ia_tac_map", {})
    ia_gan_map = eco.get("ia_gan_map", {})
    ordenes_central_map = eco.get("ordenes_central_map", {})

    simbolos_bots = (
        set(ordenes_central_map.keys())
        | set(graduadas.keys())
        | set(posta_dict.keys())
        | set(reg_verdes.keys())
        | set(ia_pre_map.keys())
        | set(ia_tac_map.keys())
        | set(ia_gan_map.keys())
    )
    inyectadas_binance_a5 = set(asistente_5_barrido_global_binance(mapa_mkt, simbolos_bots))

    universo_syms = list(dict.fromkeys(
        list(ordenes_central_map.keys())
        + list(graduadas.keys())
        + list(posta_dict.keys())
        + list(reg_verdes.keys())
        + list(ia_pre_map.keys())
        + list(ia_tac_map.keys())
        + list(ia_gan_map.keys())
        + list(inyectadas_binance_a5)
    ))

    stats_embudo = {
        "aprobadas_etapa_a1": 0,
        "corroboradas_2plus": 0,
        "aprobadas_mesa_6": 0,
        "listas_trader": 0,
        "cuellos_botella": {}
    }
    if not universo_syms:
        return [], stats_embudo

    cap_base_total = max(500.0, float(plan.get("capital_total_usd", CAPITAL_INICIAL_PRUEBA)) + float(plan.get("ganancia_realizada_usd", 0.0)))
    cupo_est_usd = round(cap_base_total / MAX_TRADERS_SEMANA, 2)
    candidatos = []

    for sym in universo_syms:
        if sym not in mapa_mkt:
            continue
        mkt = mapa_mkt[sym]
        precio = float(mkt["precio"])
        es_iny_a5 = (sym in inyectadas_binance_a5)

        # --- ASISTENTE 1 (Etapa E1/E2/Ganadoras/Cerebro Central) ---
        dossier_a1 = asistente_1_forense_cazador_preexplosion(sym, precio, eco, plan, es_inyeccion_binance=es_iny_a5)
        check_a1 = bool(dossier_a1["check_a1"])
        corroborada_2plus = bool(dossier_a1.get("corroborada_etapa_2plus", False))

        if check_a1 and sym not in excluidas:
            stats_embudo["aprobadas_etapa_a1"] += 1
            if corroborada_2plus:
                stats_embudo["corroboradas_2plus"] += 1

        # --- ASISTENTE 2 (Velocidad 24h & Confluencia) ---
        res_a2 = asistente_2_confluencia_velocidad(mkt, dossier_a1) if check_a1 else {"ok": False, "motivo": dossier_a1["dictamen_asistente"]}
        check_a2 = bool(res_a2["ok"])

        # --- ASISTENTE 3 (Medias Diarias 1D / 15m — con Bypass si >=2 Asistentes de Etapa) ---
        if check_a1 and check_a2:
            v15 = analizar_velas_tf(session, sym, "15m", 105)
            v1d = analizar_velas_tf(session, sym, "1d", 105)
            v1h = analizar_velas_tf(session, sym, "1h", 36)
            v4h = analizar_velas_tf(session, sym, "4h", 48)
            res_a3 = asistente_3_estructura_limpia(v15, v1d, v4h, dossier_a1)
        else:
            v15 = {"ok": False, "rsi": 50.0, "var_ultima": 0.0, "var_3velas": 0.0, "vol_ratio": 1.0, "ma7": precio, "ma25": precio}
            v1d = {"ok": False, "ma99": 0.0}
            v1h = {"ok": False, "rsi": 50.0, "vol_ratio": 1.0, "var_ultima": 0.0, "var_3velas": 0.0}
            v4h = {"ok": False, "fib": {"ok": False}}
            res_a3 = {"ok": False, "bypass_a3": False, "motivo": res_a2["motivo"]}
        check_a3 = bool(res_a3["ok"])

        # --- ASISTENTE 4 (Combustible 1H & Pista) ---
        if check_a1 and check_a2 and check_a3:
            res_a4 = asistente_4_combustible_pista(precio, v1h, v1d, umbrales, dossier_a1)
        else:
            res_a4 = {"ok": False, "pista_libre_pct": 0.0, "motivo": res_a3["motivo"]}
        check_a4 = bool(res_a4["ok"])

        # --- ASISTENTE 5 (Libro en Vivo Binance & Muros) ---
        if check_a1 and check_a2 and check_a3 and check_a4:
            ob_a5 = asistente_5_auditar_order_book(session, sym, cupo_est_usd, umbrales)
        else:
            ob_a5 = {"ok": False, "ratio_ba": 0.0, "liq_ask_015_usd": 0.0, "muro_vendedor": False, "sano": False, "motivo": res_a4["motivo"]}
        check_a5 = bool(ob_a5.get("sano", False))

        # --- ASISTENTE 6 (Cinta 500 aggTrades & Ballenas en Vivo) ---
        if check_a1 and check_a2 and check_a3 and check_a4 and check_a5:
            cinta_a6 = asistente_6_cinta_y_ballenas_binance(session, sym, umbrales)
        else:
            cinta_a6 = {"ok": False, "taker_buy_pct": 0.0, "whale_buy_pct": 0.0, "motivo": ob_a5["motivo"]}
        check_a6 = bool(cinta_a6.get("ok", False))

        asistentes_aprobados = sum([check_a1, check_a2, check_a3, check_a4, check_a5, check_a6])
        mesa_6_de_6_ok = (asistentes_aprobados == 6)

        if mesa_6_de_6_ok and sym not in excluidas:
            stats_embudo["aprobadas_mesa_6"] += 1

        if not mesa_6_de_6_ok and sym not in excluidas:
            if not check_a1:
                paso_veto, det_veto, clave_cuello = "A1-Empresa", dossier_a1["dictamen_asistente"], "A1_Etapa"
            elif not check_a2:
                paso_veto, det_veto, clave_cuello = "A2-Empresa", res_a2["motivo"], "A2_Velocidad"
            elif not check_a3:
                paso_veto, det_veto, clave_cuello = "A3-Empresa", res_a3["motivo"], "A3_Medias_1D"
            elif not check_a4:
                paso_veto, det_veto, clave_cuello = "A4-Empresa", res_a4["motivo"], "A4_Vol_Pista"
            elif not check_a5:
                paso_veto, det_veto, clave_cuello = "A5-Binance", ob_a5["motivo"], "A5_Libro_Muros"
            else:
                paso_veto, det_veto, clave_cuello = "A6-Binance", cinta_a6["motivo"], "A6_Cinta_Ballenas"

            if check_a1:
                stats_embudo["cuellos_botella"][clave_cuello] = stats_embudo["cuellos_botella"].get(clave_cuello, 0) + 1
            if check_a1 and check_a2:
                cerebro.registrar_veto_sombra(sym, precio, paso_veto, det_veto)

        # --- NIVEL 2: TRADER DEDICADO (TIMING DE ENTRADA EN 15M Y STOP ESTRUCTURAL / ETAPA) ---
        ma7_15 = float(v15.get("ma7") or precio)
        ma25_15 = float(v15.get("ma25") or precio)
        dist_ma7_pct = round(((precio - ma7_15) / ma7_15) * 100.0, 2) if ma7_15 > 0 else 0.0
        max_dist_ma7 = 4.20 if corroborada_2plus else float(umbrales.get("max_distancia_ma7_15m_pct", 3.20))

        es_reentrada = dossier_a1["es_reentrada_habilitada"]
        reentrada_ok = (not es_reentrada) or (float(v1h.get("vol_ratio", 1.0)) >= 2.0)
        fomo_15m = (dist_ma7_pct > max_dist_ma7) or (float(v15.get("rsi", 50.0)) > 83.0)

        if mesa_6_de_6_ok and fomo_15m and sym not in excluidas:
            stats_embudo["cuellos_botella"]["FOMO_15m"] = stats_embudo["cuellos_botella"].get("FOMO_15m", 0) + 1

        check_2_trader = (
            mesa_6_de_6_ok
            and not fomo_15m
            and reentrada_ok
            and (sym not in excluidas)
        )
        if check_2_trader:
            stats_embudo["listas_trader"] += 1

        bono_evol = cerebro.bono_evolutivo(sym, dossier_a1["patron_detectado"])
        bono_cc = 10.0 if corroborada_2plus else (6.0 if dossier_a1.get("es_orden_cerebro_central") else 0.0)
        fib_4h = v4h.get("fib", {})
        bono_fib = 10.0 if fib_4h.get("en_zona_dorada") else (6.0 if fib_4h.get("en_tramo_alcista") else 0.0)
        score = round(
            50.0
            + (asistentes_aprobados * 5.0)
            + bono_evol
            + bono_cc
            + bono_fib
            + min(float(v1h.get("vol_ratio", 0)) * 3.0, 10.0)
            + (6.0 if check_2_trader else 0.0),
            1
        )

        # Si >=2 Asistentes de Etapa corroboraron rebote/explosión, usa directo el Stop Sugerido de Etapa (-3.5%)
        if corroborada_2plus:
            stop_trader_pct = round(float(dossier_a1.get("stop_sugerido_etapa", STOP_REBOTE_CORROBORADO_PCT)), 2)
        else:
            stop_base = float(umbrales.get("stop_base_pct", STOP_LOSS_FIJO_PCT))
            stop_ma25 = ((ma25_15 * 0.994 - precio) / precio) * 100.0 if precio > 0 else stop_base
            stop_trader_pct = round(max(stop_base, min(-1.90, stop_ma25)), 2)

        if corroborada_2plus:
            sello_txt = f"⚡🛡️ REBOTE/EXPLOSIÓN CORROBORADO ({dossier_a1.get('votos_etapa', 2)} Asist. Etapa)"
        elif es_iny_a5:
            sello_txt = "🛰️ INYECCIÓN EN VIVO BINANCE (A5)"
        elif dossier_a1["confirmada_pre_explosion"]:
            sello_txt = "⚡ PRE-EXPLOSIÓN E2"
        elif dossier_a1["cazador_en_verde"]:
            sello_txt = f"🟢 CAZADOR E{dossier_a1['etapa_cazador']}"
        else:
            sello_txt = "🏆 GANADORAS 24H"

        motivo_6_asistentes = (
            f"{sello_txt} | Mesa {asistentes_aprobados}/6 | "
            f"{res_a3.get('motivo', '')} | {res_a4.get('motivo', '')} | {ob_a5.get('motivo', '')} | {cinta_a6.get('motivo', '')}"
        )
        plan_trader_txt = (
            f"Entrada {formatear_precio(precio)} (MA7 +{dist_ma7_pct:.1f}%) | "
            f"TP1 +{TP1_ASEGURAR_PCT}% / TP2 +{TP2_ASEGURAR_PCT}% / Runner 30% | Stop {stop_trader_pct}%"
            if check_2_trader
            else f"Espera apoyo MA7 15m (actual +{dist_ma7_pct:.1f}%)"
        )

        if not check_a1:
            jefe_ver_init = dossier_a1["dictamen_asistente"]
        elif not mesa_6_de_6_ok:
            faltan = [
                lbl for lbl, ok_f in [("A2", check_a2), ("A3", check_a3), ("A4", check_a4), ("A5-Book", check_a5), ("A6-Cinta", check_a6)]
                if not ok_f
            ]
            ultimo_mot = next(
                m_txt for ok_f, m_txt in [
                    (check_a2, res_a2["motivo"]), (check_a3, res_a3["motivo"]),
                    (check_a4, res_a4["motivo"]), (check_a5, ob_a5["motivo"]), (check_a6, cinta_a6["motivo"])
                ] if not ok_f
            )
            jefe_ver_init = f"⛔ Mesa {asistentes_aprobados}/6 (Falta {','.join(faltan)}): {ultimo_mot}"
        elif fomo_15m:
            jefe_ver_init = f"⏳ Mesa 6/6 OK, Trader espera apoyo MA7 15m (+{dist_ma7_pct:.1f}% > +{max_dist_ma7}%)"
        elif not check_2_trader:
            jefe_ver_init = "⏳ Trader espera confirmación de volumen para re-entrada"
        else:
            jefe_ver_init = "⏳ Mesa 6/6 OK + Trader Dedicado OK ➔ Pendiente firma Jefe Supervisor"

        candidatos.append({
            "symbol": sym,
            "base": sym[:-4],
            "precio_entrada": precio,
            "origen": sello_txt,
            "patron_detectado": dossier_a1["patron_detectado"],
            "corroborada_etapa_2plus": corroborada_2plus,
            "bypass_a3": bool(res_a3.get("bypass_a3", False)),
            "es_inyeccion_binance": es_iny_a5,
            "probabilidad": dossier_a1["blindaje_pct"],
            "score": score,
            "certificada_doble": dossier_a1["doble_certificada"],
            "carril_vip_radar": dossier_a1["carril_vip_radar"],
            "asistentes_aprobados": asistentes_aprobados,
            "checks_6_asistentes": {
                "A1_Cazador_PreExp": check_a1,
                "A2_Velocidad_Conf": check_a2,
                "A3_Limpia_15m_1D": check_a3,
                "A4_Vol_Pista20": check_a4,
                "A5_Binance_Libro": check_a5,
                "A6_Binance_Cinta": check_a6
            },
            "check_1_asistente": mesa_6_de_6_ok,
            "check_2_trader": check_2_trader,
            "check_3_jefe": False,
            "consenso_3_de_3": False,
            "trader_propuesto": "",
            "stop_trader_pct": stop_trader_pct,
            "asistente_dictamen": f"[{asistentes_aprobados}/6] {dossier_a1['dictamen_asistente']}",
            "plan_trader_entrada": plan_trader_txt,
            "fomo_15m": fomo_15m,
            "en_zona": False,
            "jefe_veredicto": jefe_ver_init,
            "jefe_factibilidad_pct": 0,
            "ya_en_cartera": sym in excluidas,
            "motivo_tecnico": motivo_6_asistentes,
            "expediente_previo": dossier_a1,
            "ob": ob_a5,
            "cinta_a6": cinta_a6,
            "mom": v1h,
            "mom_15m": v15,
            "fib_4h": fib_4h
        })

    candidatos.sort(key=lambda x: (x["check_2_trader"], x["corroborada_etapa_2plus"], x["asistentes_aprobados"], x["score"]), reverse=True)
    return candidatos[:TOP_ALTERNATIVAS_MOSTRAR], stats_embudo


def ejecutar_empleados_3_traders_ia(session, mapa_mkt, plan, clima_btc_txt, lecturas_tecnicas, boletin_asistente, eco):
    posiciones = plan.get("posiciones", [])
    datos_posiciones = []

    for p in posiciones:
        sym = p["symbol"]
        trader_id = p.get("trader_asignado", "TRADER_1")
        tec = lecturas_tecnicas.get(sym, {})
        v1m = tec.get("v1m") or analizar_velas_tf(session, sym, "1m", 30)
        v15 = tec.get("v15") or analizar_velas_tf(session, sym, "15m", 35)
        v1h = tec.get("v1h") or analizar_velas_tf(session, sym, "1h", 36)
        fib = tec.get("fib") or {}
        dossier = tec.get("expediente_previo") or asistente_1_forense_cazador_preexplosion(sym, float(p.get("precio_actual", 0)), eco, plan)

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
        tesis_viva = (not perdio_fib_618)

        if p.get("tp2_ejecutado", False):
            orden_def = f"🚀 {trader_id}: RUNNER 30% ACTIVO"
            razon_def = f"TP1 y TP2 cobrados; 30% corriendo hacia +20%/+70% con trail -{TRAILING_RUNNER_PCT}%."
        elif p.get("tp1_ejecutado", False):
            orden_def = f"🟢 {trader_id}: RUMBO A TP2 (+{TP2_ASEGURAR_PCT}%)"
            razon_def = f"TP1 35% en caja; 65% protegido en BE +{stop_act:.2f}% buscando +{TP2_ASEGURAR_PCT}%."
        elif pnl_pct >= TP1_ASEGURAR_PCT * 0.85:
            orden_def = f"🟡 {trader_id}: CERCA DE TP1 (+{TP1_ASEGURAR_PCT}%)"
            razon_def = f"Impulso +{pnl_pct:.1f}% neto: próximo a asegurar primer 35%."
        elif pnl_pct <= -2.30 or (pnl_pct <= -1.90 and not tesis_viva):
            orden_def = f"⚠️ {trader_id}: VIGILAR SOPORTE 15M"
            razon_def = f"PnL {pnl_pct:+.2f}% (${pnl_usd:+.2f} | Stop {stop_act:.2f}%) | {pulso_1m_txt}."
        else:
            proteccion_txt = f"Stop BE +{stop_act:.2f}%" if stop_act > 0 else f"Stop {stop_act:.2f}%"
            orden_def = f"🟢 {trader_id}: CUSTODIA RUNNER"
            razon_def = f"Estructura 15m/1D sana ({var_radar:+.1f}% radar) | {pulso_1m_txt} | {proteccion_txt}."

        p["trader_ia_orden"] = orden_def
        p["trader_ia_razon"] = razon_def

        datos_posiciones.append({
            "trader_dedicado": trader_id,
            "moneda": p["base"],
            "patron_origen": p.get("patron_detectado", ""),
            "tesis_bots_ia": dossier.get("tesis_previa_bots", ""),
            "tesis_original_sigue_viva": tesis_viva,
            "pnl_neto_pct": pnl_pct,
            "pnl_neto_usd": pnl_usd,
            "max_drawdown_pct": max_dd_pct,
            "tp1_ejecutado": bool(p.get("tp1_ejecutado", False)),
            "tp2_ejecutado": bool(p.get("tp2_ejecutado", False)),
            "stop_proteccion_actual_pct": stop_act,
            "retroceso_desde_max_pct": retroceso_max,
            "rsi_15m": v15["rsi"],
            "rsi_1h": v1h["rsi"],
            "fibonacci_4h": fib_resumen,
            "propuesta_trader": orden_def
        })

    stats_emb = calcular_estadisticas_embudo(mapa_mkt, eco)
    real = float(plan.get("ganancia_realizada_usd", 0.0))
    flot = sum(float(p.get("pnl_usd", 0.0)) for p in posiciones)
    meta = float(plan.get("meta_semanal_usd", META_SEMANAL_USD))
    progreso_pct = round(((real + flot) / meta) * 100, 1) if meta > 0 else 0.0

    auditoria_res = {
        "fecha": ahora_art().strftime("%Y-%m-%d %H:%M ART"),
        "semana_id": plan["semana_id"],
        "semaforo_meta": "🟢 EN CAMINO A META" if (real + flot) >= 0 else "🟡 EN CONSOLIDACIÓN",
        "factibilidad_pct": min(96, max(50, int(70 + (stats_emb["tasa_pct"] * 0.22) + ((real + flot) / 25.0)))),
        "diagnostico_24h": (
            f"Mesa 6 Asistentes (Bypass A3 >=2 Etapa) + 3 Traders ({len(posiciones)}/3 activos) -> Jefe. "
            f"{clima_btc_txt}. Avance: {progreso_pct}%."
        ),
        "recomendacion_auditor": f"Cada Trader opera 1 moneda exclusiva tras consenso 6/6 Asistentes + Jefe (>= {FACTIBILIDAD_MINIMA_JEFE}%).",
        "autocritica_ciclo": boletin_asistente.get("autocritica_ciclo", ""),
        "veredicto_final_semana": plan.get("auditoria_ia", {}).get("veredicto_final_semana", "En seguimiento activo...")
    }

    if GEMINI_API_KEY and datos_posiciones:
        try:
            client = genai.Client(api_key=GEMINI_API_KEY)
            prompt = (
                "Eres el COORDINADOR DE LOS 3 TRADERS INDEPENDIENTES (TRADER_1, TRADER_2, TRADER_3; 1 moneda por Trader) en Binance Spot.\n"
                "Cada Trader busca llevar su moneda hacia +20% en Modo Runner 3 Tramos (TP1 +6.5% 35%, TP2 +15% 35%, Runner 30% trail 4.5%).\n"
                f"BOLETÍN MESA 6 ASISTENTES: {boletin_asistente.get('resumen_ejecutivo', '')}\n"
                f"REPORTES IA MOTORES: {json.dumps(boletin_asistente.get('reportes_ia_motores', {}), ensure_ascii=False)}\n"
                f"CEREBRO EVOLUTIVO: {boletin_asistente.get('cerebro_resumen', '')}\n"
                f"CLIMA MERCADO: {clima_btc_txt} | AVANCE SEMANA: ${real + flot:+.2f} / ${meta:.0f} USD ({progreso_pct}%)\n"
                f"ESCRITORIOS ACTIVOS (1 MONEDA POR TRADER):\n{json.dumps(datos_posiciones, ensure_ascii=False)}\n\n"
                "Responde ÚNICAMENTE en JSON válido sin bloques markdown:\n"
                '{"semaforo_meta":"🟢 FACTIBLE | 🟡 EN OBSERVACIÓN | 🔴 RIESGO","factibilidad_pct":84,'
                '"diagnostico_24h":"resumen técnico breve en 1 oración",'
                '"recomendacion_auditor":"recomendación operativa para el Jefe Supervisor",'
                '"ordenes":{"MONEDA":{"orden":"🟢 TRADER_X: CUSTODIA RUNNER | 🟡 TRADER_X: CERCA TP1/TP2 | 🚨 TRADER_X: SOLICITUD SALIDA","razon":"motivo técnico breve de ese Trader"}}}'
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
                            p["trader_ia_orden"] = str(o_mon["orden"])[:48]
                            p["trader_ia_razon"] = str(o_mon.get("razon", p["trader_ia_razon"]))[:165]
        except Exception as e:
            print(f"⚠️ Fallback 3 Traders IA: {e}")

    plan["auditoria_ia"] = auditoria_res
    return auditoria_res


# ==============================================================================
# NIVEL 3: JEFE SUPERVISOR (AUDITA 6 ASISTENTES + 3 TRADERS + AUTOCRÍTICA CICLO)
# ==============================================================================

def ejecutar_jefe_supervisor_ia(plan, alternativas, posiciones_revisar, boletin_asistente, clima_btc_txt, traders_libres: list, stats_embudo: dict, cerebro: CerebroEvolutivo):
    """
    NIVEL 3 (JEFE SUPERVISOR):
    1) Audita en cada corrida cuántas monedas aprobaron los Asistentes de Etapa vs. cuántas llegaron a los Traders
       y ajusta automáticamente el umbral cuello de botella si el embudo quedó en 0 entradas.
    2) Asigna cada propuesta aprobada a un Trader libre (1 moneda por Trader) y firma la entrada (>= 75%).
    """
    aprob_etapa = int(stats_embudo.get("aprobadas_etapa_a1", 0))
    corrob_2p = int(stats_embudo.get("corroboradas_2plus", 0))
    listas_tr = int(stats_embudo.get("listas_trader", 0))
    cuellos = stats_embudo.get("cuellos_botella", {})

    if aprob_etapa >= 3 and listas_tr == 0 and cuellos:
        diag_auto = cerebro.calibrar_embudo_ciclo(cuellos)
        resumen_autocritica = (
            f"🔄 Autocrítica Ciclo: Asist. Etapa aprobaron {aprob_etapa} ({corrob_2p} corroboradas >=2) "
            f"pero 0 llegaron a Traders ➔ {diag_auto}"
        )
    elif listas_tr > 0:
        resumen_autocritica = (
            f"✅ Autocrítica Ciclo: Embudo sano ({aprob_etapa} aprobadas Etapa | {corrob_2p} corroboradas >=2 | "
            f"{listas_tr} listas para Traders libres)."
        )
    else:
        resumen_autocritica = (
            f"📡 Autocrítica Ciclo: {aprob_etapa} señales Etapa en evaluación ({corrob_2p} corroboradas >=2); sin cuellos anómalos."
        )

    boletin_asistente["autocritica_ciclo"] = resumen_autocritica
    if "auditoria_ia" in plan:
        plan["auditoria_ia"]["autocritica_ciclo"] = resumen_autocritica

    propuestas_compra = [a for a in alternativas if a.get("check_1_asistente") and a.get("check_2_trader")]

    for idx_p, alt in enumerate(propuestas_compra):
        if idx_p < len(traders_libres):
            alt["trader_propuesto"] = traders_libres[idx_p]
        else:
            alt["trader_propuesto"] = "SIN_TRADER_LIBRE"

    real = float(plan.get("ganancia_realizada_usd", 0.0))
    flot = sum(float(p.get("pnl_usd", 0.0)) for p in plan.get("posiciones", []))
    balance_neto = round(real + flot, 2)
    meta = float(plan.get("meta_semanal_usd", META_SEMANAL_USD))

    autopsia_info = boletin_asistente.get("autopsia_24h", {})
    stops_prematuros_sem = int(autopsia_info.get("stops_prematuros_semana", 0))

    for alt in propuestas_compra:
        dossier = alt.get("expediente_previo", {})
        ob = alt.get("ob", {})
        cinta = alt.get("cinta_a6", {})
        mom = alt.get("mom", {})
        fib = alt.get("fib_4h", {})

        fact = 69
        if dossier.get("corroborada_etapa_2plus"):
            fact += 12
        elif dossier.get("es_inyeccion_binance"):
            fact += 7
        if float(ob.get("ratio_ba", 1.0)) >= 1.35 and ob.get("liquidez_real_ok") and not ob.get("muro_vendedor"):
            fact += 6
        if float(cinta.get("taker_buy_pct", 0.0)) >= 56.0:
            fact += 5
        if fib.get("en_zona_dorada") or fib.get("en_tramo_alcista"):
            fact += 4
        if float(mom.get("vol_ratio", 1.0)) >= 1.8:
            fact += 4
        if balance_neto < -250.0 and not dossier.get("carril_vip_radar"):
            fact -= 12

        fact = max(40, min(97, fact))
        tiene_trader = alt.get("trader_propuesto") in NOMBRES_TRADERS
        check_3_jefe = (fact >= FACTIBILIDAD_MINIMA_JEFE) and tiene_trader
        consenso_total = bool(alt.get("check_1_asistente") and alt.get("check_2_trader") and check_3_jefe)

        alt["jefe_factibilidad_pct"] = fact
        alt["check_3_jefe"] = check_3_jefe
        alt["consenso_3_de_3"] = consenso_total
        alt["en_zona"] = consenso_total

        tag_bypass = " [Bypass A3 Rebote]" if alt.get("bypass_a3") else ""
        if consenso_total:
            alt["jefe_veredicto"] = (
                f"✅ CONSENSO TOTAL ({fact}%){tag_bypass} ➔ Asignada a {alt['trader_propuesto']} "
                f"(Stop {alt.get('stop_trader_pct')}% | OB {ob.get('ratio_ba', 1.0)}x | Cinta {cinta.get('taker_buy_pct', 0)}%)"
            )
        elif not tiene_trader:
            alt["jefe_veredicto"] = f"⏳ EN ESPERA ({fact}%): Los 3 Traders tienen su moneda asignada."
        else:
            alt["jefe_veredicto"] = f"⛔ JEFE VETA ({fact}% < {FACTIBILIDAD_MINIMA_JEFE}%): protege margen con balance ${balance_neto:+.0f}."

    for item_pos in posiciones_revisar:
        pos = item_pos["pos"]
        t_id = pos.get("trader_asignado", "TRADER")
        if item_pos.get("propuesta_cierre_palanca"):
            tesis_viva = item_pos.get("tesis_viva", True)
            pnl_p = float(pos.get("pnl_pct", 0.0))
            umbral_veto_jefe = -2.90 if stops_prematuros_sem >= 1 else -2.50
            if tesis_viva and pnl_p > umbral_veto_jefe:
                item_pos["cierre_aprobado_jefe"] = False
                pos["jefe_orden"] = f"🛡️ VETO JEFE ({t_id} MANTIENE)"
                pos["jefe_razon"] = (
                    f"Jefe ordena a {t_id} sostener runner en {pnl_p:+.2f}%: estructura 15m/1D sigue viva."
                )
            else:
                item_pos["cierre_aprobado_jefe"] = True
                pos["jefe_orden"] = f"✅ SALIDA APROBADA ({t_id})"
                pos["jefe_razon"] = f"Jefe coincide con {t_id} en cerrar ({pnl_p:+.2f}%): invalidación confirmada."
        else:
            pos["jefe_orden"] = f"✅ {t_id} SUPERVISADO OK"
            pos["jefe_razon"] = f"Jefe valida gestión exclusiva de {t_id} rumbo a +20% (Stop {pos.get('stop_actual_pct', STOP_LOSS_FIJO_PCT):.2f}%)."

    if GEMINI_API_KEY and (propuestas_compra or posiciones_revisar):
        try:
            client = genai.Client(api_key=GEMINI_API_KEY)
            resumen_propuestas = [
                {
                    "moneda": a["base"],
                    "trader_asignado": a["trader_propuesto"],
                    "corroborada_etapa_2plus": a["corroborada_etapa_2plus"],
                    "bypass_a3": a["bypass_a3"],
                    "stop_sugerido": a["stop_trader_pct"],
                    "score_evolutivo": a["score"],
                    "asistente_1_etapa": a["expediente_previo"]["dictamen_asistente"],
                    "order_book_a5": a["ob"].get("motivo", ""),
                    "cinta_ballenas_a6": a["cinta_a6"].get("motivo", ""),
                    "plan_trader": a["plan_trader_entrada"]
                }
                for a in propuestas_compra if a.get("trader_propuesto") in NOMBRES_TRADERS
            ]
            resumen_cartera = [
                {
                    "trader": it["pos"].get("trader_asignado", ""),
                    "moneda": it["pos"]["base"],
                    "pnl_neto_pct": it["pos"]["pnl_pct"],
                    "pnl_neto_usd": it["pos"]["pnl_usd"],
                    "tp1_ejecutado": bool(it["pos"].get("tp1_ejecutado")),
                    "tp2_ejecutado": bool(it["pos"].get("tp2_ejecutado")),
                    "orden_trader": it["pos"].get("trader_ia_orden", ""),
                    "pide_cierre_anticipado": bool(it.get("propuesta_cierre_palanca")),
                    "motivo_cierre_trader": it["motivo_palanca"],
                    "tesis_viva": it["tesis_viva"]
                }
                for it in posiciones_revisar
            ]

            prompt_jefe = (
                "Eres el JEFE SUPERVISOR DE INVERSIONES de una mesa Spot con:\n"
                "• CORROBORACIÓN CRUZADA: Si >=2 Asistentes de Etapa corroboran una moneda, se hace Bypass de medias diarias A3 y se usa el Stop Sugerido de Etapa (-3.5%).\n"
                "• 3 TRADERS INDEPENDIENTES (TRADER_1, TRADER_2, TRADER_3): cada Trader opera 1 sola moneda exclusiva.\n"
                "• JEFE SUPERVISOR (TÚ): das la firma final ('aprobada': true, 'factibilidad_pct' >= 75) cuando todo coincide.\n"
                f"AUTOCRÍTICA DEL CICLO: {resumen_autocritica}\n"
                f"ESTADO SEMANA {plan['semana_id']}: Balance Neto ${balance_neto:+.2f} / Meta ${meta:.0f} USD | {clima_btc_txt}\n"
                f"CANDIDATAS LISTAS PARA TRADERS LIBRES:\n{json.dumps(resumen_propuestas, ensure_ascii=False)}\n"
                f"CARTERA ACTUAL (1 MONEDA POR TRADER):\n{json.dumps(resumen_cartera, ensure_ascii=False)}\n\n"
                "Responde ÚNICAMENTE en JSON válido sin bloques markdown:\n"
                '{"compras":{"MONEDA":{"aprobada":true,"factibilidad_pct":88,"veredicto":"✅ CONSENSO TOTAL (88%) ➔ TRADER_X: motivo"}},'
                '"cartera":{"MONEDA":{"aprobar_cierre":false,"orden_jefe":"🛡️ VETO JEFE (TRADER_X MANTIENE) | ✅ SALIDA APROBADA","razon_jefe":"dictamen breve del Jefe"}}}'
            )

            raw_jefe = llamar_gemini_con_reintento(client, prompt_jefe)
            if raw_jefe:
                j_json = limpiar_json_ia(raw_jefe)
                compras_j = j_json.get("compras", {})
                for alt in propuestas_compra:
                    dec = compras_j.get(alt["base"])
                    if isinstance(dec, dict) and "aprobada" in dec and alt.get("trader_propuesto") in NOMBRES_TRADERS:
                        fact_ia = int(dec.get("factibilidad_pct", alt["jefe_factibilidad_pct"]))
                        check_3_ia = bool(dec["aprobada"]) and (fact_ia >= FACTIBILIDAD_MINIMA_JEFE)
                        consenso_ia = bool(alt.get("check_1_asistente") and alt.get("check_2_trader") and check_3_ia)
                        alt["jefe_factibilidad_pct"] = fact_ia
                        alt["check_3_jefe"] = check_3_ia
                        alt["consenso_3_de_3"] = consenso_ia
                        alt["en_zona"] = consenso_ia
                        txt_v = str(dec.get("veredicto", "")).strip()
                        if txt_v:
                            alt["jefe_veredicto"] = txt_v[:175]

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


# ==============================================================================
# CLIMA BTC, CALIBRACIÓN DE SISTEMA Y PERSISTENCIA DEL PLAN SEMANAL
# ==============================================================================

def verificar_clima_y_regimen_mercado(session, mapa_mkt):
    btc = mapa_mkt.get("BTCUSDT")
    if not btc:
        return True, False, MAX_TRADERS_SEMANA, "BTC estable | 3 Traders activos (33.3% capital c/u)"

    chg_24h = float(btc["cambio_24h"])
    mom_btc = analizar_velas_tf(session, "BTCUSDT", "1h", 24)
    rsi_btc = float(mom_btc.get("rsi", 50.0))
    var_1h_btc = float(mom_btc.get("var_ultima", 0.0))

    liquidas = [v for k, v in mapa_mkt.items() if k != "BTCUSDT" and v.get("vol_24h", 0) >= 1_500_000]
    verdes_mkt = sum(1 for v in liquidas if v.get("cambio_24h", 0) > 0)
    pct_verdes = round((verdes_mkt / len(liquidas)) * 100, 1) if liquidas else 50.0

    cupos_max = CUPOS_MODO_DEFENSIVO if pct_verdes < 30.0 else MAX_TRADERS_SEMANA
    regimen_txt = f"Amplitud Verde: {pct_verdes}% (máx {cupos_max}/3 Traders activos)"

    panico_1h = (var_1h_btc <= -1.0)
    if panico_1h or chg_24h <= -2.0 or rsi_btc < 35.0:
        motivo = f"BTC en alerta (1h: {var_1h_btc:+.2f}%, 24h: {chg_24h:+.2f}%, RSI 1h: {rsi_btc}) | {regimen_txt}. Compras pausadas."
        return False, panico_1h, cupos_max, motivo

    return True, False, cupos_max, f"BTC estable (1h: {var_1h_btc:+.2f}%, 24h: {chg_24h:+.2f}%, RSI 1h: {rsi_btc}) | {regimen_txt}"


def verificar_circuit_breaker_diario(plan, ahora_dt=None):
    ahora_dt = ahora_dt or ahora_art()
    plan["circuit_breaker_hasta_iso"] = ""

    try:
        with open(__file__, "rb") as f_self:
            hash_actual = hashlib.md5(f_self.read()).hexdigest()
    except Exception:
        hash_actual = ""

    if hash_actual and plan.get("codigo_hash") != hash_actual:
        plan["codigo_hash"] = hash_actual
        dt_listo = ahora_dt + timedelta(minutes=MINUTOS_CALIBRACION_SISTEMA)
        plan["warmup_hasta_iso"] = dt_listo.isoformat()
        return True, True, (
            f"Actualización detectada (Corroboración Cruzada Bypass A3 + Autocrítica Ciclo). "
            f"Calibrando variables durante {MINUTOS_CALIBRACION_SISTEMA} min (compras habilitadas desde las {dt_listo.strftime('%H:%M ART')})."
        )

    warmup_iso = plan.get("warmup_hasta_iso", "")
    if warmup_iso:
        try:
            dt_warmup = datetime.fromisoformat(warmup_iso)
            if dt_warmup.tzinfo is None:
                dt_warmup = dt_warmup.replace(tzinfo=TZ_ART)
            if ahora_dt < dt_warmup:
                mins_rest = max(1, int(round((dt_warmup - ahora_dt).total_seconds() / 60.0)))
                return True, False, f"Sistema en calibración inicial ({mins_rest} min restantes hasta las {dt_warmup.strftime('%H:%M ART')})."
            plan["warmup_hasta_iso"] = ""
        except Exception:
            plan["warmup_hasta_iso"] = ""

    return False, False, ""


def cargar_plan_semanal():
    sem = id_semana_actual()
    base = {
        "semana_id": sem,
        "fecha_inicio": ahora_art().strftime("%Y-%m-%d %H:%M"),
        "modo": "MESA_6_ASISTENTES_3_TRADERS_JEFE_BYPASS_A3",
        "capital_total_usd": CAPITAL_INICIAL_PRUEBA,
        "meta_semanal_usd": META_SEMANAL_USD,
        "ganancia_realizada_usd": 0.0,
        "estado_semana": "ACTIVA",
        "fecha_cierre_meta": "",
        "aviso_btc_enviado": False,
        "ultimo_panico_btc_iso": "",
        "circuit_breaker_hasta_iso": "",
        "codigo_hash": "",
        "warmup_hasta_iso": "",
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
        data.setdefault("codigo_hash", "")
        data.setdefault("warmup_hasta_iso", "")
        data.setdefault("ultimo_reporte_hora", -1)
        data.setdefault("boletin_asistente", {})
        data.setdefault("auditoria_ia", {})
        data.setdefault("historial_auditorias", [])
        data.setdefault("alternativas_evaluadas", [])
        return data
    if data:
        if data.get("historial_cierres"):
            base["historial_cierres"] = data["historial_cierres"][-80:]
        if data.get("historial_auditorias"):
            base["historial_auditorias"] = data["historial_auditorias"][-80:]
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
    ganadas, en_curso, perdidas = 0, 0, 0

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
    tasa_resueltas = round((ganadas / resueltas) * 100, 1) if resueltas > 0 else 80.0
    return {"ganadas": ganadas, "perdidas": perdidas, "en_curso": en_curso, "total": total_senales, "resueltas": resueltas, "tasa_pct": tasa_resueltas}


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


def generar_veredicto_final_ia(plan, cerebro: CerebroEvolutivo):
    cierres = [c for c in plan.get("historial_cierres", []) if c.get("semana_id") == plan["semana_id"]]
    ganadoras = [c for c in cierres if float(c.get("pnl_usd", 0)) > 0]
    perdedoras = [c for c in cierres if float(c.get("pnl_usd", 0)) <= 0]
    win_rate = round((len(ganadoras) / len(cierres)) * 100, 1) if cierres else 100.0
    total_usd = float(plan.get("ganancia_realizada_usd", 0.0))
    meta_usd = float(plan.get("meta_semanal_usd", META_SEMANAL_USD))

    veredicto_base = (
        f"✅ <b>VEREDICTO: META LOGRADA — MESA 6 ASISTENTES + 3 TRADERS + JEFE FACTIBLE</b>\n"
        f"• Se alcanzaron <b>${total_usd:,.2f} USD netos</b> (Meta: ${meta_usd:,.0f} USD) con <b>{win_rate}% de acierto</b> "
        f"({len(ganadoras)} ganadoras / {len(perdedoras)} cerradas en protección).\n"
        f"• {html.escape(cerebro.resumen_corto())}"
    )

    if GEMINI_API_KEY and cierres:
        try:
            client = genai.Client(api_key=GEMINI_API_KEY)
            prompt = (
                "Eres el Jefe Supervisor de una mesa Spot en Binance (Corroboración Cruzada Etapa + 6 Asistentes -> 3 Traders Dedicados -> Jefe). "
                "Cumplimos la meta semanal neta. Da un VEREDICTO FINAL DE FACTIBILIDAD para dinero real en máximo 4 líneas en español.\n"
                f"Capital Base: ${plan.get('capital_total_usd', 3500)} USD | Meta: ${meta_usd} USD | Ganancia Neta Lograda: ${total_usd} USD\n"
                f"Cerebro Evolutivo: {cerebro.resumen_corto()}\n"
                f"Operaciones cerradas: {json.dumps(cierres, ensure_ascii=False)}"
            )
            raw_ver = llamar_gemini_con_reintento(client, prompt)
            if raw_ver:
                return f"👔 <b>DICTAMEN FINAL JEFE SUPERVISOR IA:</b>\n{html.escape(raw_ver.strip())}"
        except Exception:
            pass
    return veredicto_base


# ==============================================================================
# GRÁFICOS, EXCEL AUDITORÍA SEMANAL (7 PESTAÑAS) Y MENSAJES DE TELEGRAM
# ==============================================================================

def generar_tablero_visual(plan, filename="tablero_semanal.png"):
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11.2, 4.7), facecolor="#0b132b", gridspec_kw={"width_ratios": [1.0, 1.55]})
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
        nombres = [f"{p['base']}\n({p.get('trader_asignado', 'T').replace('TRADER_', 'T')})" for p in posiciones]
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
        ax2.set_xticklabels(nombres, color="white", fontweight="bold", fontsize=9.0)
        ax2.tick_params(axis="y", colors="white", labelsize=8.5)
        ax2.grid(True, axis="y", color="#1e293b", linewidth=0.7, zorder=1)
        ax2.legend(loc="upper right", facecolor="#0b132b", edgecolor="#334155", labelcolor="white", fontsize=7.0)

        for b, v, p_obj in zip(bars_act, pnls, posiciones):
            yv = b.get_height()
            etq_tp = "Runner 30%" if p_obj.get("tp2_ejecutado") else (f"TP2 +{TP2_ASEGURAR_PCT}%" if p_obj.get("tp1_ejecutado") else f"TP1 +{TP1_ASEGURAR_PCT}%")
            ax2.text(b.get_x() + b.get_width() / 2.0, yv + (0.8 if yv >= 0 else -1.1), f"{v:+.2f}%\n({etq_tp})", ha="center", va="bottom" if yv >= 0 else "top", color="white", fontweight="bold", fontsize=7.6)
    else:
        ax2.text(0.5, 0.5, "3 Traders Dedicados Libres\n(Esperando Mesa 6/6 Asistentes + Jefe)", ha="center", va="center", color="#94a3b8", fontsize=10, transform=ax2.transAxes)
        ax2.tick_params(left=False, labelleft=False, bottom=False, labelbottom=False)

    aud = plan.get("auditoria_ia", {})
    fact_txt = f" | Jefe IA: {aud.get('factibilidad_pct', 82)}% Factible" if aud else ""
    ax2.set_title(f"3 TRADERS DEDICADOS ({len(posiciones)}/{MAX_TRADERS_SEMANA} • 1 MONEDA C/U) • TP1 +{TP1_ASEGURAR_PCT}% | TP2 +{TP2_ASEGURAR_PCT}%", color="#00e676", fontsize=8.3, fontweight="bold", pad=10)
    fig.suptitle(f"GESTOR 3 TRADERS DEDICADOS ➔ JEFE SUPERVISOR ({plan['semana_id']}){fact_txt} | {ahora_art().strftime('%d/%m %H:%M ART')}", color="white", fontsize=9.2, fontweight="bold", y=0.98)
    plt.tight_layout(rect=[0, 0, 1, 0.93])
    plt.savefig(filename, dpi=260, facecolor=fig.get_facecolor())
    plt.close()
    return filename


def _poblar_hoja_matriz_central(ws, plan, eco, mapa_mkt, fill_hdr, font_hdr, fill_verde, fill_amarillo):
    headers_mc = [
        "Moneda", "Precio Vivo ($)", "Var 24h (%)", "Confluencia Motores",
        "Motor 1: Ganadoras 24h", "Motor 2: Cazador Táctico (E1)", "Motor 3: Pre-Explosión (E2)",
        "Mesa 6 Asistentes", "Estado en Cartera / Trader", "Dictamen Combinado IA"
    ]
    ws.append(headers_mc)
    for col_idx in range(1, len(headers_mc) + 1):
        c = ws.cell(row=1, column=col_idx)
        c.fill = fill_hdr
        c.font = font_hdr
        c.alignment = Alignment(horizontal="center")

    graduadas = eco.get("graduadas", {})
    posta = eco.get("posta", {})
    reg_verdes = eco.get("reg_verdes", {})
    ia_gan = eco.get("ia_gan_map", {})
    ia_tac = eco.get("ia_tac_map", {})
    ia_pre = eco.get("ia_pre_map", {})
    pos_map = {p["symbol"]: p for p in plan.get("posiciones", [])}
    alts_map = {a["symbol"]: a for a in plan.get("alternativas_evaluadas", [])}

    todos_syms = sorted(
        set(graduadas.keys()) | set(posta.keys()) | set(reg_verdes.keys())
        | set(ia_gan.keys()) | set(ia_tac.keys()) | set(ia_pre.keys()) | set(pos_map.keys())
    )

    filas = []
    for sym in todos_syms:
        mkt = mapa_mkt.get(sym, {})
        p_vivo = float(mkt.get("precio", 0.0))
        chg_24 = round(float(mkt.get("cambio_24h", 0.0)), 2)

        en_g = (sym in reg_verdes) or (sym in ia_gan)
        en_t = (sym in posta) or (sym in ia_tac)
        en_p = (sym in graduadas) or (sym in ia_pre)
        conf_cnt = sum([1 if en_g else 0, 1 if en_t else 0, 1 if en_p else 0])

        g_txt = f"✅ {ia_gan.get(sym, {}).get('estado') or reg_verdes.get(sym, {}).get('estado', 'ACTIVA')}" if en_g else "—"
        t_txt = f"✅ E{posta.get(sym, {}).get('etapa', ia_tac.get(sym, {}).get('etapa', 1))}" if en_t else "—"
        p_txt = f"⚡ {graduadas.get(sym, {}).get('semaforo', ia_pre.get(sym, {}).get('semaforo', 'VERDE'))}" if en_p else "—"

        alt_info = alts_map.get(sym)
        mesa_txt = f"{alt_info.get('asistentes_aprobados', 0)}/6" if alt_info else "En Radar"
        if alt_info and alt_info.get("bypass_a3"):
            mesa_txt += " (Bypass A3)"

        if sym in pos_map:
            p_obj = pos_map[sym]
            est_cartera = f"🟢 {p_obj.get('trader_asignado', 'TRADER')} ({p_obj.get('pnl_pct', 0):+.2f}%)"
        elif alt_info and alt_info.get("consenso_3_de_3"):
            est_cartera = f"🟡 LISTA ({alt_info.get('trader_propuesto', 'COLA')})"
        else:
            est_cartera = "OBSERVACIÓN"

        notas = " | ".join(eco.get("notas_extra", {}).get(sym, []))
        if not notas and alt_info:
            notas = alt_info.get("jefe_veredicto", "")

        filas.append((conf_cnt, chg_24, [
            sym[:-4], p_vivo, chg_24, f"{conf_cnt}/3 Motores",
            g_txt, t_txt, p_txt, mesa_txt, est_cartera, notas[:180]
        ]))

    filas.sort(key=lambda x: (x[0], x[1]), reverse=True)
    for row_idx, (conf_cnt, _, fila_vals) in enumerate(filas, start=2):
        ws.append(fila_vals)
        celda_conf = ws.cell(row=row_idx, column=4)
        if conf_cnt >= 2:
            celda_conf.fill = fill_verde
        elif conf_cnt == 1:
            celda_conf.fill = fill_amarillo


def actualizar_excel_semanal(plan, cerebro: CerebroEvolutivo, eco=None, mapa_mkt=None):
    eco = eco or {}
    mapa_mkt = mapa_mkt or {}

    wb = openpyxl.Workbook()
    fill_hdr = PatternFill(start_color="0B132B", end_color="0B132B", fill_type="solid")
    font_hdr = Font(color="FFFFFF", bold=True)
    fill_verde = PatternFill(start_color="D1FAE5", end_color="D1FAE5", fill_type="solid")
    fill_amarillo = PatternFill(start_color="FEF3C7", end_color="FEF3C7", fill_type="solid")
    fill_rojo = PatternFill(start_color="FEE2E2", end_color="FEE2E2", fill_type="solid")

    # Pestaña 0: Radar Cruzado de Operaciones
    ws_mc = wb.active
    ws_mc.title = "0_MATRIZ_CENTRAL_IA"
    _poblar_hoja_matriz_central(ws_mc, plan, eco, mapa_mkt, fill_hdr, font_hdr, fill_verde, fill_amarillo)

    # Pestaña 1: Cartera y 3 Traders Dedicados
    ws = wb.create_sheet(title="1_CARTERA_3_TRADERS")
    headers = [
        "Semana", "Trader Asignado", "Fecha Entrada", "Moneda", "Patrón Origen", "Dictamen 6 Asistentes",
        "Capital ($)", "Precio Entrada", "Precio Objetivo", "Subida Esperada (%)",
        "Precio Actual", "Máximo Alcanzado", "Max Drawdown (%)", "Rend. Neto (%)",
        "PnL Neto ($)", "Lectura Fibonacci 4H", "Operativa Trader Dedicado", "Veredicto Jefe Supervisor", "Estado"
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
        ver_jefe = pos.get("jefe_veredicto_entrada") or f"{pos.get('jefe_orden', '✅ CONSENSO')} — {pos.get('jefe_razon', '')}".strip(" —")
        ws.append([
            pos.get("semana_id", plan["semana_id"]),
            pos.get("trader_asignado", "TRADER_1"),
            pos.get("fecha_entrada", ""),
            pos.get("base", ""),
            pos.get("patron_detectado", pos.get("origen", "")),
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
        celda_pnl = ws.cell(row=row_idx, column=15)
        if pnl_v > 0:
            celda_pnl.fill = fill_verde
        elif pnl_v < 0:
            celda_pnl.fill = fill_rojo

    # Pestaña 2: Mesa de 6 Asistentes + Consenso Total
    ws_alt = wb.create_sheet(title="2_MESA_6_ASISTENTES")
    headers_alt = [
        "Ranking", "Moneda", "A1 E1/E2/Gan", "A2 Vel/Conf", "A3 Medias 1D", "A4 Vol/Pista",
        "A5 Binance Libro", "A6 Binance Cinta", "Trader Asignado", "Jefe Supervisor",
        "Factibilidad (%)", "Precio Actual", "Decisión Final", "Detalle Técnico Completo"
    ]
    ws_alt.append(headers_alt)
    for col_idx in range(1, len(headers_alt) + 1):
        c = ws_alt.cell(row=1, column=col_idx)
        c.fill = fill_hdr
        c.font = font_hdr
        c.alignment = Alignment(horizontal="center")

    pos_map_act = {p["symbol"]: p for p in plan.get("posiciones", [])}
    for idx, alt in enumerate(plan.get("alternativas_evaluadas", []), start=1):
        ch = alt.get("checks_6_asistentes", {})
        c1 = "✅" if ch.get("A1_Cazador_PreExp") else "❌"
        c2 = "✅" if ch.get("A2_Velocidad_Conf") else "❌"
        c3 = "⚡BYPASS" if alt.get("bypass_a3") else ("✅" if ch.get("A3_Limpia_15m_1D") else "❌")
        c4 = "✅" if ch.get("A4_Vol_Pista20") else "❌"
        c5 = "✅" if ch.get("A5_Binance_Libro") else "❌"
        c6 = "✅" if ch.get("A6_Binance_Cinta") else "❌"
        sym_a = alt.get("symbol", "")
        tr_real = pos_map_act[sym_a].get("trader_asignado", "TRADER") if sym_a in pos_map_act else ""
        tr_lbl = tr_real or alt.get("trader_propuesto") or ("✅ OK" if alt.get("check_2_trader") else "⏳")
        c3_j = "✅ OK" if (alt.get("check_3_jefe") or sym_a in pos_map_act) else ("⛔ VETA" if (alt.get("check_1_asistente") and alt.get("check_2_trader")) else "—")

        if sym_a in pos_map_act:
            estado_alt = f"✅ OPERADA POR {tr_real}"
        elif alt.get("consenso_3_de_3"):
            estado_alt = "🟢 CONSENSO TOTAL (En Cola)"
        elif alt.get("check_1_asistente") and alt.get("check_2_trader"):
            estado_alt = "⛔ VETADA POR JEFE / SIN TRADER LIBRE"
        elif alt.get("check_1_asistente"):
            estado_alt = "⏳ MESA 6/6 OK — TRADER ESPERA APOYO 15M"
        else:
            estado_alt = f"🚫 FILTRADA MESA ({alt.get('asistentes_aprobados', 0)}/6)"

        detalle_alt = f"{alt.get('jefe_veredicto', '')} | {alt.get('plan_trader_entrada', '')} | {alt.get('motivo_tecnico', '')}"
        ws_alt.append([
            idx, alt.get("base", ""), c1, c2, c3, c4, c5, c6, tr_lbl, c3_j,
            alt.get("jefe_factibilidad_pct", 0), float(alt.get("precio_entrada", 0)), estado_alt, detalle_alt
        ])

    # Pestaña 3: Auditoría IA 24h + Autocrítica de Ciclo
    ws_aud = wb.create_sheet(title="3_AUDITORIA_IA_24H")
    headers_aud = ["Fecha Auditoría", "Semana", "Semáforo Meta", "Factibilidad (%)", "Diagnóstico Mesa + 3 Traders", "Autocrítica Embudo Ciclo", "Veredicto Final Semana"]
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
            reg.get("factibilidad_pct", 82),
            reg.get("diagnostico_24h", ""),
            reg.get("autocritica_ciclo") or reg.get("recomendacion_auditor", ""),
            reg.get("veredicto_final_semana", "En seguimiento activo...")
        ])

    # Pestaña 4: Resumen Cuota Semanal
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
    headers_aut = ["Semana", "Trader", "Moneda", "Fecha Cierre", "PnL Cierre ($)", "Precio Cierre", "Máx 24h Post", "Mín 24h Post", "Var Máx Post (%)", "Dictamen Autopsia"]
    ws_aut.append(headers_aut)
    for col_idx in range(1, len(headers_aut) + 1):
        c = ws_aut.cell(row=1, column=col_idx)
        c.fill = fill_hdr
        c.font = font_hdr
        c.alignment = Alignment(horizontal="center")

    for c in reversed(plan.get("historial_cierres", [])):
        ws_aut.append([
            c.get("semana_id", ""),
            c.get("trader_asignado", ""),
            c.get("base", ""),
            c.get("fecha_cierre", ""),
            round(float(c.get("pnl_usd", 0.0)), 2),
            float(c.get("precio_actual", 0.0)),
            float(c.get("post_cierre_max", c.get("precio_actual", 0.0))),
            float(c.get("post_cierre_min", c.get("precio_actual", 0.0))),
            round(float(c.get("var_max_post_pct", 0.0)), 2),
            c.get("veredicto_autopsia", "⏳ Pendiente")
        ])

    # Pestaña 6: Cerebro Evolutivo IA
    ws_evo = wb.create_sheet(title="6_EVOLUCION_CEREBRO_IA")
    headers_evo = ["Bloque Evolutivo", "Parámetro / Patrón", "Valor Calibrado / Bonus", "Operaciones / Eventos", "Ganadas / Aciertos", "Runners +20%"]
    ws_evo.append(headers_evo)
    for col_idx in range(1, len(headers_evo) + 1):
        c = ws_evo.cell(row=1, column=col_idx)
        c.fill = fill_hdr
        c.font = font_hdr
        c.alignment = Alignment(horizontal="center")

    for k_u, v_u in cerebro.umbrales.items():
        ws_evo.append(["UMBRAL_CALIBRADO", k_u, v_u, "-", "-", "-"])

    for k_p, v_p in cerebro.data.get("pesos_patrones", {}).items():
        ws_evo.append([
            "PATRON_APRENDIDO", k_p, v_p.get("bonus", 0),
            v_p.get("ops", 0), v_p.get("ganadas", 0), v_p.get("runners_20", 0)
        ])

    mg = cerebro.data.get("metricas_globales", {})
    ws_evo.append(["METRICA_GLOBAL", "TOTAL_OPERADAS_VS_GANADAS", f"Ciclo v{cerebro.data.get('version_ciclo', 1)}", mg.get("total_operadas", 0), mg.get("total_ganadas", 0), mg.get("runners_20_logrados", 0)])
    ws_evo.append(["METRICA_SOMBRA", "VETOS_ACERTADOS_VS_PERDIDAS_20", "-", "-", mg.get("vetos_acertados", 0), mg.get("oportunidades_perdidas_20", 0)])
    ws_evo.append(["METRICA_AUTOCRITICA", "AJUSTES_EMBUDO_CICLO", "-", mg.get("ajustes_autocritica_ciclo", 0), "-", "-"])

    for sheet in (ws_mc, ws, ws_alt, ws_aud, ws2, ws_aut, ws_evo):
        for col in sheet.columns:
            max_len = max(len(str(c.value or "")) for c in col)
            sheet.column_dimensions[col[0].column_letter].width = min(max_len + 4, 54)

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
        print(f"⚠️ Error enviando Excel Auditoría Semanal: {e}")
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
    pos_map_act = {p["symbol"]: p for p in plan.get("posiciones", [])}
    bol = plan.get("boletin_asistente", {})

    msg = (
        f"🔍 <b>MESA 6 ASISTENTES + CORROBORACIÓN CRUZADA • BLOQUE 1/3</b>\n"
        f"📅 <code>{ahora_str}</code> | Semana <code>{plan['semana_id']}</code>\n"
    )
    if bol.get("cerebro_resumen"):
        msg += f"<i>{html.escape(bol['cerebro_resumen'])}</i>\n"
    if bol.get("autocritica_ciclo"):
        msg += f"<i>{html.escape(bol['autocritica_ciclo'])}</i>\n\n"
    else:
        msg += "\n"

    if not alts:
        msg += "⏳ <i>Aún no hay candidatas evaluadas en el radar.</i>"
        return msg.strip()

    for idx, a in enumerate(alts, start=1):
        ch = a.get("checks_6_asistentes", {})
        c1 = "✅" if ch.get("A1_Cazador_PreExp") else "❌"
        c2 = "✅" if ch.get("A2_Velocidad_Conf") else "❌"
        c3 = "⚡" if a.get("bypass_a3") else ("✅" if ch.get("A3_Limpia_15m_1D") else "❌")
        c4 = "✅" if ch.get("A4_Vol_Pista20") else "❌"
        c5 = "✅" if ch.get("A5_Binance_Libro") else "❌"
        c6 = "✅" if ch.get("A6_Binance_Cinta") else "❌"
        sym_a = a.get("symbol", "")
        tr_real = pos_map_act[sym_a].get("trader_asignado", "TRADER") if sym_a in pos_map_act else ""
        tr_tag = tr_real or (a.get("trader_propuesto") if a.get("trader_propuesto") in NOMBRES_TRADERS else ("⏳" if a.get("check_1_asistente") else "—"))
        jf_tag = "✅" if (a.get("check_3_jefe") or sym_a in pos_map_act) else ("⛔" if a.get("check_2_trader") else "—")

        checklist = f"<code>[Emp A1:{c1} A2:{c2} A3:{c3} A4:{c4} | Bin A5:{c5} A6:{c6} | Tr:{tr_tag} | Jf:{jf_tag}]</code>"

        if sym_a in pos_map_act:
            marca = f"✅ <b>[OPERADA POR {html.escape(tr_real)}]</b>"
        elif a.get("consenso_3_de_3"):
            marca = f"🟢 <b>[CONSENSO TOTAL ➔ {html.escape(a.get('trader_propuesto', 'TRADER'))}]</b>"
        elif a.get("check_1_asistente") and a.get("fomo_15m"):
            marca = "⏳ <i>[MESA 6/6 OK • TRADER ESPERA APOYO MA7 15M]</i>"
        elif a.get("check_1_asistente"):
            marca = "⏳ <i>[MESA 6/6 OK • ESPERA TRADER/JEFE]</i>"
        else:
            marca = f"🚫 <i>[MESA {a.get('asistentes_aprobados', 0)}/6]</i>"

        msg += (
            f"<b>{idx}. {a['base']}</b> (Score: <b>{a['score']}</b>) — {marca}\n"
            f"   • {checklist} | Precio: <code>{formatear_precio(a['precio_entrada'])}</code>\n"
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
    escritorios = asignar_traders_a_cartera(plan.get("posiciones", []))

    msg = (
        f"🏆 <b>3 TRADERS INDEPENDIENTES (1 MONEDA C/U • NETO FEES 0.20%) • BLOQUE 2/3</b>\n"
        f"{evento_titulo}\n"
        f"📅 <code>{ahora_str}</code> | Cuota: <code>${meta:,.0f} USD</code> | Progreso Neto: <b>${real + flot:+.2f} USD ({cump}%)</b>\n"
    )
    if aud:
        msg += (
            f"👔 <b>Auditoría Jefe IA:</b> <b>{html.escape(aud.get('semaforo_meta', ''))}</b> ({aud.get('factibilidad_pct', 82)}% factibilidad)\n"
            f"└ <i>{html.escape(aud.get('diagnostico_24h', ''))}</i>\n"
        )
        if aud.get("autocritica_ciclo"):
            msg += f"└ <i>{html.escape(aud.get('autocritica_ciclo', ''))}</i>\n\n"
        else:
            msg += "\n"
    else:
        msg += "\n"

    for tid in NOMBRES_TRADERS:
        p = escritorios.get(tid)
        if p is None:
            msg += f"🖥️ <b>{tid}:</b> <i>LIBRE — Esperando candidata con Consenso 6/6 Asistentes + Jefe Supervisor.</i>\n\n"
            continue

        uid = int(time.time() * 1000) + random.randint(1, 999)
        u_ia = f"{BASE_URL_NETLIFY}/?coin={p['base']}&price={p['precio_actual']}&v={p['base']}_{uid}"
        u_tr = f"{BINANCE_TRADE_BASE}{p['base']}_USDT"
        exp_res = html.escape(p.get("asistente_dictamen") or p.get("expediente_previo_resumen", p.get("origen", "")))
        fib_l = html.escape(p.get("fib_lectura", "Fib N/D"))
        orden_tr = html.escape(p.get("trader_ia_orden", f"🟢 {tid}: CUSTODIA RUNNER"))
        razon_tr = html.escape(p.get("trader_ia_razon", ""))
        orden_jf = html.escape(p.get("jefe_orden", "✅ SUPERVISADO OK"))
        razon_jf = html.escape(p.get("jefe_razon", p.get("jefe_veredicto_entrada", "")))
        stop_act = float(p.get("stop_actual_pct", STOP_LOSS_FIJO_PCT))
        stop_label = f"🛡️ Stop Protegido: <code>+{stop_act:.2f}%</code>" if stop_act > 0 else f"Stop Despegue: <code>{stop_act:.2f}%</code>"

        if p.get("tp2_ejecutado", False):
            tp_tag = f"🚀 TP1+TP2 cobrados (70%) | Runner 30% (Trail -{TRAILING_RUNNER_PCT}%)"
        elif p.get("tp1_ejecutado", False):
            tp_tag = f"✅ TP1 35% cobrado | Busca TP2: <code>+{TP2_ASEGURAR_PCT}%</code>"
        else:
            tp_tag = f"TP1 35%: <code>+{TP1_ASEGURAR_PCT}%</code> | TP2 35%: <code>+{TP2_ASEGURAR_PCT}%</code>"

        dd_val = float(p.get("max_drawdown_pct", 0.0))

        msg += (
            f"🖥️ <b>{tid} ➔ {p['base']}</b> — Cupo Exclusivo: <code>${p['capital_usd']:,.2f} USD</code>\n"
            f"• <b>Entrada:</b> <code>{formatear_precio(p['precio_entrada'])}</code> ➔ <b>Actual:</b> <code>{formatear_precio(p['precio_actual'])}</code> (<b>{p['pnl_pct']:+.2f}% neto</b> | <code>${p['pnl_usd']:+.2f}</code> | MaxDD: <code>{dd_val:.2f}%</code>)\n"
            f"• <b>Plan Salida +20%:</b> {tp_tag} | {stop_label} | <code>{fib_l}</code>\n"
            f"• <b>🗂️ Mesa 6 Asistentes:</b> <i>{exp_res}</i>\n"
            f"• <b>🤖 {tid} (Dedicado):</b> <b>{orden_tr}</b> — <i>{razon_tr}</i>\n"
            f"• <b>👔 Jefe Supervisor:</b> <b>{orden_jf}</b> — <i>{razon_jf}</i>\n"
            f"└ <a href=\"{html.escape(u_ia)}\">📊 Gráfico IA</a> | <a href=\"{html.escape(u_tr)}\">🔶 Tradear Spot</a>\n\n"
        )
    return msg.strip()


# ==============================================================================
# ORQUESTADOR PRINCIPAL DE EJECUCIÓN CONTINUA
# ==============================================================================

def ejecutar_gestor_semanal():
    s = crear_sesion_binance()
    mapa_mkt = obtener_tickers_binance(s)
    if not mapa_mkt:
        print("❌ Sin datos de Binance.")
        return

    cerebro = CerebroEvolutivo()
    plan = cargar_plan_semanal()
    asignar_traders_a_cartera(plan.get("posiciones", []))

    cerebro.auditar_sombra_y_calibrar(s, mapa_mkt)

    # PASO 1: MESA DE 6 ASISTENTES + 3 REPORTES IA + CEREBRO CENTRAL + AUTOPSIA 24H
    boletin_asistente, eco = ejecutar_asistente_inteligencia(mapa_mkt, plan, cerebro)
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
        cerebro.guardar()
        actualizar_excel_semanal(plan, cerebro, eco, mapa_mkt)
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
                f"🛡️ <i>Compras pausadas y Stops elevados automáticamente a Break-Even neto (+0.30%) en los Traders en verde.</i>"
            )

    # PASO 2: CADA TRADER DEDICADO EVALÚA SU MONEDA ASIGNADA EN VIVO
    posiciones_evaluadas = []
    stop_base_cerebro = float(cerebro.umbrales.get("stop_base_pct", STOP_LOSS_FIJO_PCT))

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
        v15 = analizar_velas_tf(s, sym, "15m", 35)
        v1h = analizar_velas_tf(s, sym, "1h", 36)
        v4h = analizar_velas_tf(s, sym, "4h", 48)
        fib = v4h.get("fib", {}) if v4h.get("fib", {}).get("ok") else v1h.get("fib", {})
        dossier_a1 = asistente_1_forense_cazador_preexplosion(
            sym, p_act, eco, plan, es_inyeccion_binance=bool(pos.get("es_inyeccion_binance", False))
        )

        cinta_a6 = asistente_6_cinta_y_ballenas_binance(s, sym, cerebro.umbrales) if pnl_pct <= -1.8 else {"ok": True}

        lecturas_tecnicas[sym] = {
            "v1m": v1m, "v15": v15, "v1h": v1h, "fib": fib,
            "expediente_previo": dossier_a1
        }

        stop_pos_inicial = float(pos.get("stop_inicial_pct", stop_base_cerebro))
        stop_dinamico_pct = stop_pos_inicial
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
        pos["expediente_previo_resumen"] = dossier_a1["resumen_corto"]
        pos["asistente_dictamen"] = dossier_a1["dictamen_asistente"]

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
                "trader": pos.get("trader_asignado", "TRADER"),
                "tramo": "TP1 (35%)",
                "base": pos["base"],
                "pnl_pct": round(pnl_pct, 2),
                "ganancia_tp": ganancia_tp1,
                "precio_actual": p_act,
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
                "trader": pos.get("trader_asignado", "TRADER"),
                "tramo": "TP2 (35%)",
                "base": pos["base"],
                "pnl_pct": round(pnl_pct, 2),
                "ganancia_tp": ganancia_tp2,
                "precio_actual": p_act,
                "detalle_siguiente": f"30% RUNNER final corriendo libre con Trailing Stop de -{TRAILING_RUNNER_PCT}% desde máximos."
            })

        palanca_activada, motivo_palanca = empleado_evaluar_palanca_emergencia(
            pos, v1m, v15, v1h, fib, pnl_pct, dossier_a1, cinta_a6
        )
        perdio_618 = fib.get("ok") and (p_act < float(fib["fib_618"]) and float(fib["ratio"]) > 0.65)
        tesis_viva = (not perdio_618)

        posiciones_evaluadas.append({
            "pos": pos,
            "sin_datos": False,
            "pnl_pct": pnl_pct,
            "pnl_usd": float(pos["pnl_usd"]),
            "max_pnl_pct": max_pnl_pct,
            "retroceso_desde_max": retroceso_desde_max,
            "horas_abierta": horas_abierta,
            "stop_inicial_pct": stop_pos_inicial,
            "stop_dinamico_pct": stop_dinamico_pct,
            "propuesta_cierre_palanca": palanca_activada,
            "motivo_palanca": motivo_palanca,
            "cierre_aprobado_jefe": False,
            "tesis_viva": tesis_viva,
            "exp_previo": dossier_a1
        })

    # PASO 3: COORDINACIÓN IA DE LOS 3 TRADERS DEDICADOS + BARRIDO MESA 6 ASISTENTES
    aud_actual = ejecutar_empleados_3_traders_ia(s, mapa_mkt, plan, msg_btc, lecturas_tecnicas, boletin_asistente, eco)

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
    alternativas, stats_embudo = mesa_asistentes_y_traders_evaluar_candidatas(s, mapa_mkt, excluidas, eco, plan, cerebro)

    escritorios_actuales = asignar_traders_a_cartera(plan["posiciones"])
    traders_libres = [tid for tid in NOMBRES_TRADERS if escritorios_actuales.get(tid) is None]

    # PASO 4: EL JEFE SUPERVISOR REVISA TODO, AUDITA AUTOCRÍTICA Y ASIGNA TRADERS LIBRES
    ejecutar_jefe_supervisor_ia(
        plan, alternativas, [x for x in posiciones_evaluadas if not x.get("sin_datos")],
        boletin_asistente, msg_btc, traders_libres, stats_embudo, cerebro
    )
    plan["alternativas_evaluadas"] = alternativas

    # PASO 5: EJECUCIÓN BLINDADA POR TRADER Y APRENDIZAJE AUTOMÁTICO AL CERRAR
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
        stop_ini_pos = item["stop_inicial_pct"]
        stop_dinamico_pct = item["stop_dinamico_pct"]
        max_perdida_cupo_usd = round(float(pos.get("capital_inicial_usd", 1166.0)) * (abs(stop_ini_pos) / 100.0) * 1.05, 2)
        t_id = pos.get("trader_asignado", "TRADER")

        es_vip_pos = bool(pos.get("carril_vip_radar", False)) or ("CAZADOR" in str(pos.get("origen", "")))
        horas_limite_rotacion = HORAS_MAX_SIN_ARRANQUE_VIP if es_vip_pos else HORAS_MAX_SIN_ARRANQUE_STD

        motivo_cierre = None
        if pos.get("tp2_ejecutado", False) and retroceso_desde_max <= -TRAILING_RUNNER_PCT:
            motivo_cierre = f"🚀 {t_id} CIERRA RUNNER 30% (Trailing -{TRAILING_RUNNER_PCT}%): tocó máx +{max_pnl_pct:.1f}% y cerró en {pnl_pct:+.1f}% neto."
        elif not pos.get("tp2_ejecutado", False) and max_pnl_pct >= 22.0 and retroceso_desde_max <= -TRAILING_RUNNER_PCT:
            motivo_cierre = f"🚀 {t_id} CAPTURA EXPLOSIÓN: tocó +{max_pnl_pct:.1f}% y aseguró +{pnl_pct:.1f}% neto."
        elif pnl_pct <= stop_ini_pos or pnl_usd <= -max_perdida_cupo_usd:
            motivo_cierre = f"🛑 {t_id} STOP DESPEGUE ({pnl_pct:.2f}% neto | ${pnl_usd:+.2f} USD): corta pérdida controlada."
        elif stop_dinamico_pct > 0 and pnl_pct <= stop_dinamico_pct:
            motivo_cierre = f"🛡️ {t_id} STOP PROTEGIDO (+{stop_dinamico_pct:.2f}% neto): subió hasta +{max_pnl_pct:.1f}% y aseguró cierre en {pnl_pct:+.2f}%."
        elif not pos.get("tp1_ejecutado", False) and item["propuesta_cierre_palanca"] and item["cierre_aprobado_jefe"]:
            motivo_cierre = f"👔 SALIDA APROBADA POR JEFE ({t_id}): {item['motivo_palanca']}"
        elif not pos.get("tp1_ejecutado", False) and horas_abierta >= horas_limite_rotacion and pnl_pct < 1.5:
            motivo_cierre = f"⏳ {t_id} ROTACIÓN ({int(horas_abierta)}h/{int(horas_limite_rotacion)}h lateral en {pnl_pct:+.1f}% neto): libera escritorio."

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
            cerebro.registrar_cierre_y_aprender(pos)
        else:
            if pnl_pct <= -2.30 and not pos.get("prealerta_palanca_enviada", False):
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
            pos["motivo_cierre"] = f"🏆 {pos.get('trader_asignado', 'TRADER')} CIERRA POR CUOTA SEMANAL ALCANZADA"
            plan["ganancia_realizada_usd"] = round(float(plan["ganancia_realizada_usd"]) + float(pos["pnl_usd"]), 2)
            plan["historial_cierres"].append(pos)
            alertas_venta.append(pos)
            cerebro.registrar_cierre_y_aprender(pos)
        plan["posiciones"] = []
        plan["estado_semana"] = "META_CUMPLIDA"
        plan["fecha_cierre_meta"] = ahora_str

    cb_activo, cb_recien_activado, msg_cb = verificar_circuit_breaker_diario(plan, ahora_dt)
    if cb_recien_activado:
        enviar_telegram_texto(
            f"⚙️ <b>ARRANQUE Y CALIBRACIÓN DEL SISTEMA ({MINUTOS_CALIBRACION_SISTEMA} MIN)</b>\n"
            f"📅 <code>{ahora_str}</code>\n\n"
            f"🖥️ {html.escape(msg_cb)}"
        )

    # PASO 6: APERTURA DE NUEVAS POSICIONES EN TRADERS LIBRES CON CONSENSO COMPLETO
    escritorios_post_cierre = asignar_traders_a_cartera(plan["posiciones"])
    traders_disponibles_ahora = [tid for tid in NOMBRES_TRADERS if escritorios_post_cierre.get(tid) is None]

    if plan["estado_semana"] == "ACTIVA" and len(plan["posiciones"]) < cupos_max_regimen and traders_disponibles_ahora and not cb_activo:
        if not btc_ok:
            if not plan.get("aviso_btc_enviado", False):
                enviar_telegram_texto(f"🛑 <b>FRENO DE MANO BTC ACTIVADO</b>\n📅 <code>{ahora_str}</code>\n\n⚠️ {html.escape(msg_btc)}")
                plan["aviso_btc_enviado"] = True
        else:
            plan["aviso_btc_enviado"] = False
            cupos = min(cupos_max_regimen - len(plan["posiciones"]), len(traders_disponibles_ahora), MAX_ENTRADAS_POR_CORRIDA)
            elegidas = [a for a in alternativas if a.get("consenso_3_de_3")][:cupos]

            if elegidas:
                cap_base_total = max(500.0, float(plan["capital_total_usd"]) + float(plan["ganancia_realizada_usd"]))
                cap_por_cupo = round(cap_base_total / MAX_TRADERS_SEMANA, 2)
                meta_restante = max(50.0, float(plan["meta_semanal_usd"]) - float(plan["ganancia_realizada_usd"]))
                meta_por_cupo = meta_restante / MAX_TRADERS_SEMANA
                subida_nec_pct = round((meta_por_cupo / cap_por_cupo) * 100.0, 2)

                for idx_el, el in enumerate(elegidas):
                    trader_asignado = el.get("trader_propuesto") if el.get("trader_propuesto") in traders_disponibles_ahora else traders_disponibles_ahora[idx_el]
                    if trader_asignado in traders_disponibles_ahora:
                        traders_disponibles_ahora.remove(trader_asignado)

                    p_ent = float(el["precio_entrada"])
                    p_obj = p_ent * (1.0 + (subida_nec_pct / 100.0))
                    stop_ini = float(el.get("stop_trader_pct", stop_base_cerebro))
                    dossier_el = el.get("expediente_previo", {})
                    pnl_init_pct = -COMISION_SPOT_TOTAL_PCT
                    pnl_init_usd = round(cap_por_cupo * (pnl_init_pct / 100.0), 2)

                    nueva_pos = {
                        "semana_id": plan["semana_id"],
                        "trader_asignado": trader_asignado,
                        "symbol": el["symbol"],
                        "base": el["base"],
                        "origen": el["origen"],
                        "patron_detectado": el.get("patron_detectado", "ESCALADA_GANADORAS_24H"),
                        "es_inyeccion_binance": bool(el.get("es_inyeccion_binance", False)),
                        "carril_vip_radar": bool(el.get("carril_vip_radar", False)),
                        "motivo_eleccion": el["motivo_tecnico"],
                        "expediente_previo_resumen": dossier_el.get("resumen_corto", ""),
                        "asistente_dictamen": el.get("asistente_dictamen", ""),
                        "jefe_veredicto_entrada": el.get("jefe_veredicto", "✅ CONSENSO TOTAL"),
                        "jefe_orden": f"✅ {trader_asignado} APROBADO",
                        "jefe_razon": el.get("jefe_veredicto", ""),
                        "trader_ia_orden": f"🟢 {trader_asignado}: COMPRA EJECUTADA",
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
                        "stop_inicial_pct": stop_ini,
                        "stop_actual_pct": stop_ini,
                        "tp1_ejecutado": False,
                        "tp2_ejecutado": False,
                        "prealerta_palanca_enviada": False,
                        "estado": "ACTIVA"
                    }
                    plan["posiciones"].append(nueva_pos)
                    nuevas_entradas.append(nueva_pos)
                    cerebro.log_bitacora("APERTURA_OPERACION", {
                        "trader": trader_asignado, "symbol": el["symbol"],
                        "patron": nueva_pos["patron_detectado"], "precio": p_ent, "stop": stop_ini
                    })

    veredicto_final_txt = ""
    if plan["estado_semana"] == "META_CUMPLIDA":
        veredicto_final_txt = generar_veredicto_final_ia(plan, cerebro)
        plan["auditoria_ia"]["veredicto_final_semana"] = veredicto_final_txt
        aud_actual["veredicto_final_semana"] = veredicto_final_txt

    for pre in prealertas_palanca:
        enviar_telegram_texto(
            f"⚠️ <b>PRE-ALERTA RIESGO • {pre.get('trader_asignado', 'TRADER')} ({pre['base']})</b>\n"
            f"📅 <code>{ahora_str}</code>\n\n"
            f"• <b>Rendimiento flotante neto:</b> <b>{pre['pnl_pct']:+.2f}%</b> (<b>${pre['pnl_usd']:+.2f} USD</b>) — <i>Stop: {pre.get('stop_actual_pct', STOP_LOSS_FIJO_PCT):.2f}%</i>\n"
            f"• <b>🗂️ Mesa 6 Asistentes:</b> <i>{html.escape(pre.get('asistente_dictamen', ''))}</i>\n"
            f"• <b>🤖 Trader Dedicado:</b> <i>{html.escape(pre.get('trader_ia_razon', ''))}</i>\n"
            f"• <b>👔 Jefe Supervisor:</b> <i>{html.escape(pre.get('jefe_razon', ''))}</i>"
        )

    for parc in alertas_parciales:
        enviar_telegram_texto(
            f"💰 <b>COSECHA PARCIAL {parc['tramo']} • {parc['trader']} ({parc['base']})</b>\n"
            f"📅 <code>{ahora_str}</code>\n\n"
            f"• <b>Rendimiento neto alcanzado:</b> <b>+{parc['pnl_pct']:.2f}%</b> en <code>{formatear_precio(parc['precio_actual'])}</code>\n"
            f"• <b>Ganancia neta en caja:</b> <b>+${parc['ganancia_tp']:.2f} USD</b>\n"
            f"• <b>Siguiente paso:</b> {html.escape(parc['detalle_siguiente'])}"
        )

    es_ejecucion_manual = (os.getenv("GITHUB_EVENT_NAME") == "workflow_dispatch")
    es_corte_horario = (plan.get("ultimo_reporte_hora") != ahora_dt.hour)
    hay_novedades = bool(nuevas_entradas or alertas_parciales or alertas_venta or plan["estado_semana"] == "META_CUMPLIDA" or cb_recien_activado)

    cerebro.guardar()

    if hay_novedades or es_corte_horario or es_ejecucion_manual:
        plan.setdefault("historial_auditorias", []).append(dict(aud_actual))
        plan["historial_auditorias"] = plan["historial_auditorias"][-100:]
        actualizar_excel_semanal(plan, cerebro, eco, mapa_mkt)

        ok1 = enviar_telegram_texto(construir_bloque_1_alternativas(plan))
        time.sleep(1.5)

        img = generar_tablero_visual(plan)
        if plan["estado_semana"] == "META_CUMPLIDA":
            titulo_ev = "🏆 <b>¡CUOTA SEMANAL CUMPLIDA — MODO PROTECCIÓN!</b>"
        elif cb_recien_activado:
            titulo_ev = f"⚙️ <b>ARRANQUE Y CALIBRACIÓN ({MINUTOS_CALIBRACION_SISTEMA} MIN)</b>"
        elif alertas_venta and nuevas_entradas:
            titulo_ev = "🔄 <b>ROTACIÓN DE ESCRITORIO / REASIGNACIÓN DE TRADER</b>"
        elif nuevas_entradas:
            titulo_ev = "🚀 <b>NUEVA COMPRA APROBADA (CORROBORACIÓN ETAPA + TRADER + JEFE)</b>"
        elif alertas_venta or alertas_parciales:
            titulo_ev = "💰 <b>COSECHA RUNNER 3 TRAMOS / CIERRE</b>"
        else:
            titulo_ev = "📡 <b>RADAR CONTINUO • CORROBORACIÓN ETAPA ➔ 3 TRADERS ➔ JEFE</b>"

        caption = construir_bloque_2_cartera(plan, titulo_ev)
        ok2 = enviar_foto_telegram(img, caption)
        time.sleep(1.5)

        ok3 = enviar_excel_telegram(
            f"📎 <b>AUDITORÍA SEMANAL 3 TRADERS • BLOQUE 3/3 (7 PESTAÑAS)</b>\n"
            f"📊 Cartera activa, Bypass A3 Corroborado, Autocrítica Ciclo y Cerebro Evolutivo (<code>{EXCEL_SEMANAL_FILE}</code>)."
        )
        if ok1 and ok2 and ok3:
            plan["ultimo_reporte_hora"] = ahora_dt.hour
    else:
        actualizar_excel_semanal(plan, cerebro, eco, mapa_mkt)

    for v in alertas_venta:
        msg_v = (
            f"🔔 <b>EJECUCIÓN DE CIERRE • {v.get('trader_asignado', 'TRADER')} ({v['base']})</b>\n"
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
    print(f"🧪 INICIANDO GESTOR SEMANAL EVOLUTIVO + CORROBORACIÓN CRUZADA ({ahora_art().strftime('%H:%M:%S')} ART)...")
    ejecutar_gestor_semanal()
