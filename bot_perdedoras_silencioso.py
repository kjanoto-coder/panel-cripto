import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import requests

# =====================================================================
# 1. CONFIGURACIÓN TELEGRAM Y CONTROL DE EJECUCIÓN
# =====================================================================
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "TU_BOT_TOKEN_AQUI")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "TU_CHAT_ID_AQUI")

COOLDOWN_MINUTES = int(os.getenv("COOLDOWN_MINUTES", "180"))
STATE_FILE = Path(os.getenv("STATE_FILE", "spot_audit_state.json"))
ALERT_ON_DISCARDED_NEW_LOW = False  # True solo si querés avisos informativos de nuevos mínimos en descartadas

BINANCE_ENDPOINTS = [
    "https://api.binance.com",
    "https://api1.binance.com",
    "https://api2.binance.com",
    "https://api3.binance.com",
]

# =====================================================================
# 2. BASE DE CONOCIMIENTO DEFINITIVA (60 ACTIVOS AUDITADOS EN SPOT)
# =====================================================================
ASSETS_DB: Dict[str, dict] = {
    # =================================================================
    # GRUPO 1: TOP 5 FAVORITOS ESTRUCTURALES (20% - 35%)
    # =================================================================
    "JSTUSDT": {
        "group": "ESTRUCTURAL",
        "allocation": "30% - 35%",
        "profile": "Tendencia alcista sólida",
        "dip_targets": [0.1430, 0.1425],
        "min_drop_pct": 4.0,
        "tech": "Estructura 1d constructiva y soporte defensivo en 0,1425–0,1430.",
        "risk": "Toma de ganancias tras tramos extendidos o pérdida de 0,1425.",
    },
    "MAGICUSDT": {
        "group": "ESTRUCTURAL",
        "allocation": "25% - 30%",
        "profile": "Rebote con flujo spot positivo",
        "dip_targets": [0.0659, 0.0640],
        "min_drop_pct": 5.0,
        "tech": "Reacción técnica apoyada cerca de MA(99) (0,0659) y sin desbloqueos inminentes.",
        "risk": "Que el rebote pierda volumen y vuelva a testear la zona de MA(99).",
    },
    "BNBUSDT": {
        "group": "ESTRUCTURAL",
        "allocation": "20% - 25%",
        "profile": "Alta liquidez y soporte defendido",
        "dip_targets": [510.0, 503.75],
        "min_drop_pct": 4.5,
        "tech": "Alta liquidez (80,7M USDT/d) y rebote desde RSI < 8 sobre soporte $503,75–510.",
        "risk": "Resistencia $538–550 y salidas puntuales de grandes tenedores.",
    },
    "PLUMEUSDT": {
        "group": "ESTRUCTURAL",
        "allocation": "20% - 25%",
        "profile": "Rebote fuerte con desbloqueo próximo",
        "dip_targets": [0.0104, 0.0102],
        "min_drop_pct": 5.5,
        "tech": "Rebote sólido desde 0,01020 con entradas de +$290K.",
        "risk": "Desbloqueo de $2,3–3M a fin de noviembre.",
    },
    "RSRUSDT": {
        "group": "ESTRUCTURAL",
        "allocation": "20% - 25%",
        "profile": "Rebote limpio sujeto a agenda",
        "dip_targets": [0.00122, 0.00118],
        "min_drop_pct": 5.5,
        "tech": "Estructura limpia en 15m tras reacción de corto plazo y resistencia relativa.",
        "risk": "Desbloqueos/eventos programados el 21/11 y 27–28/11.",
    },

    # =================================================================
    # GRUPO 2: TÁCTICAS DESTACADAS / PUENTE (15% - 20%)
    # =================================================================
    "ZECUSDT": {
        "group": "TACTICA_PUENTE",
        "allocation": "15% - 20%",
        "profile": "Alta liquidez en rebote desde sobreventa",
        "dip_targets": [778.0, 764.0],
        "min_drop_pct": 6.0,
        "tech": "Liquidez sobresaliente (360,40M USDT) y buen rebote desde 679,48.",
        "risk": "Vigilar retroceso a 764–778 por RSI(6) alto (87,88) en 15m y EMA-99 diaria ($845,93).",
    },
    "ZAMAUSDT": {
        "group": "TACTICA_PUENTE",
        "allocation": "15% - 20%",
        "profile": "Fortaleza relativa y narrativa FHE (solo retroceso)",
        "dip_targets": [0.0585, 0.0576],
        "min_drop_pct": 5.5,
        "tech": "Buena fortaleza relativa y narrativa FHE; vigilar retroceso a 0,0576–0,0585.",
        "risk": "Condicionada por 71,6% bloqueado (~4,06M/día) y alta concentración en pools (~97,3%).",
    },
    "MMTUSDT": {
        "group": "TACTICA_PUENTE",
        "allocation": "15% - 20%",
        "profile": "Sobrecomprado (solo en retroceso)",
        "dip_targets": [],
        "min_drop_pct": 8.0,
        "tech": "Impulso explosivo ya ejecutado; conviene esperar retroceso.",
        "risk": "Sobrecompra (RSI 82,2) y 71% de suministro bloqueado.",
    },
    "ASTERUSDT": {
        "group": "TACTICA_PUENTE",
        "allocation": "15% - 20%",
        "profile": "Rebote con recompras y fricción",
        "dip_targets": [],
        "min_drop_pct": 6.5,
        "tech": "Reacción apoyada en recompras, pero con presión vendedora en spot.",
        "risk": "Salidas spot y riesgos operativos/de plataforma.",
    },
    "ONDOUSDT": {
        "group": "TACTICA_PUENTE",
        "allocation": "15% - 20%",
        "profile": "Alta liquidez con flujo vendedor",
        "dip_targets": [],
        "min_drop_pct": 6.0,
        "tech": "Gran liquidez (84,2M USDT/d), pero con distribución de corto plazo.",
        "risk": "Salidas institucionales >$4M en 24h y 51,3% bloqueado.",
    },
    "ADAUSDT": {
        "group": "TACTICA_PUENTE",
        "allocation": "15% - 20%",
        "profile": "Rebote desde sobreventa extrema",
        "dip_targets": [0.1410, 0.1400],
        "min_drop_pct": 5.5,
        "tech": "Fuerte liquidez y reacción desde RSI 9,2, pero con quiebre previo de nivel.",
        "risk": "Perforación de 0,1400, salidas de -$1,54M y cierre de DJED/SHEN.",
    },
    "HBARUSDT": {
        "group": "TACTICA_PUENTE",
        "allocation": "15% - 20%",
        "profile": "Rebote técnico en tendencia débil",
        "dip_targets": [0.0505, 0.0495],
        "min_drop_pct": 6.0,
        "tech": "Rebote desde sobreventa con +$450K en 0,0505.",
        "risk": "Tendencia bajista de fondo y fricción de red (v0.79.2).",
    },
    "PENGUUSDT": {
        "group": "TACTICA_PUENTE",
        "allocation": "15% - 20%",
        "profile": "Rebote técnico en mínimos anuales",
        "dip_targets": [0.00415, 0.004141],
        "min_drop_pct": 6.5,
        "tech": "Reacción desde RSI 12,65 con buena liquidez de mercado.",
        "risk": "Cotizando en mínimos anuales (0,004141) y rotación fuera de memes.",
    },
    "GRTUSDT": {
        "group": "TACTICA_PUENTE",
        "allocation": "15% - 20%",
        "profile": "Acumulación leve sin desbloqueos",
        "dip_targets": [],
        "min_drop_pct": 6.0,
        "tech": "Entradas de +$57,8K en mínimo local y sin desbloqueos inminentes.",
        "risk": "Baja concentración (~0,015) y precio todavía debajo de MA(99).",
    },
    "RESOLVUSDT": {
        "group": "TACTICA_PUENTE",
        "allocation": "15% - 20%",
        "profile": "Reacción en mínimos con evento cerca",
        "dip_targets": [],
        "min_drop_pct": 7.0,
        "tech": "Rebote de corto plazo en zona baja, pero con liquidez acotada.",
        "risk": "Liquidez baja y desbloqueo previsto el 27/11.",
    },

    # =================================================================
    # GRUPO 3: TÁCTICAS / OBSERVACIÓN (5% - 15%)
    # =================================================================
    "HOTUSDT": {
        "group": "CAZA_REBOTE",
        "allocation": "10% - 15%",
        "profile": "Rebote con flujo spot y narrativa HoloFuel",
        "dip_targets": [0.000339, 0.000331],
        "min_drop_pct": 8.0,
        "tech": "Entradas spot >+$310K y cruce sobre EMA 7/25/99 en 15m.",
        "risk": "Concentración baja (~0,035) e incertidumbre en despliegue de HoloFuel.",
    },
    "JUPUSDT": {
        "group": "CAZA_REBOTE",
        "allocation": "10% - 15%",
        "profile": "Ingresos activos con desbloqueo cercano",
        "dip_targets": [0.2065, 0.2000],
        "min_drop_pct": 7.5,
        "tech": "Ingresos de protocolo ($313K/d) y rebote desde 0,2065.",
        "risk": ">50,6% bloqueado, MACD negativo y alerta de 53,47M tokens (~23/11).",
    },
    "ALGOUSDT": {
        "group": "CAZA_REBOTE",
        "allocation": "10% - 15%",
        "profile": "Rebote corto en estructura bajista",
        "dip_targets": [0.0715, 0.0712],
        "min_drop_pct": 7.0,
        "tech": "Reacción desde 0,0712, pero sin revertir la tendencia diaria.",
        "risk": "Tendencia 1d bajista y TVL cayendo -27% en 30 días ($24M).",
    },
    "LUMIAUSDT": {
        "group": "CAZA_REBOTE",
        "allocation": "10% - 15%",
        "profile": "Rebote técnico con baja liquidez",
        "dip_targets": [],
        "min_drop_pct": 8.0,
        "tech": "Rebote tras reapertura de retiros en la red.",
        "risk": "Liquidez muy baja y fricción comunitaria / exigencias KYC.",
    },
    "HYPEUSDT": {
        "group": "CAZA_REBOTE",
        "allocation": "5% - 10%",
        "profile": "Alta liquidez con salidas y ruido regulatorio",
        "dip_targets": [56.0, 55.80],
        "min_drop_pct": 8.0,
        "tech": "Rebote técnico desde 55,80 (RSI < 10) con alta liquidez.",
        "risk": "Salidas netas >-$25M, corrección diaria y fricción regulatoria (CFTC/HK).",
    },
    "RIFUSDT": {
        "group": "CAZA_REBOTE",
        "allocation": "5% - 10%",
        "profile": "Rebote técnico con bajo volumen",
        "dip_targets": [0.0450, 0.0449],
        "min_drop_pct": 8.5,
        "tech": "Rebote desde RSI_6 = 6,38 y piso 0,0449.",
        "risk": "Volumen horario <$10K USDT, salidas netas y bajo MA(99) en 15m (0,0472).",
    },
    "PUMPUSDT": {
        "group": "CAZA_REBOTE",
        "allocation": "5% - 10%",
        "profile": "Rebote corto con salidas fuertes",
        "dip_targets": [],
        "min_drop_pct": 9.0,
        "tech": "Rebote de corto plazo desde RSI < 15.",
        "risk": "Salidas horarias >-$460K/h, >21,9% bloqueado y ruido reputacional.",
    },
    "LUNCUSDT": {
        "group": "CAZA_REBOTE",
        "allocation": "5% - 10%",
        "profile": "Operativa táctica puntual",
        "dip_targets": [],
        "min_drop_pct": 9.0,
        "tech": "Solo reacción táctica de corto plazo.",
        "risk": "Fuera de favoritos estructurales; alta volatilidad especulativa.",
    },
    "EDENUSDT": {
        "group": "CAZA_REBOTE",
        "allocation": "5% - 10%",
        "profile": "Rebote frágil con presión vendedora",
        "dip_targets": [],
        "min_drop_pct": 8.5,
        "tech": "Rebote desde RSI 13,2 hacia 0,03973 con +$9,6K en 2h.",
        "risk": "Concentración ~0,04, ~30% bloqueado, salidas pico -$73,5K y MACD negativo.",
    },

    # =================================================================
    # GRUPO 4: DESCARTADAS PARA LIMPIAR FAVORITOS (0% - 5%)
    # =================================================================
    "MANTRAUSDT": {"group": "DESCARTADA", "allocation": "0% - 5%", "profile": "No apta / Mínimos y dilución", "risk": "Mínimos históricos (~0,00172), salida -$430,6K, concentración 0,06 y ~1,83M/día desbloqueados."},
    "TNSRUSDT":   {"group": "DESCARTADA", "allocation": "0% - 5%", "profile": "No apta / Mínimos récord", "risk": "Mínimos récord (~0,0178), caída -11,57% y concentración <0,08."},
    "MITOUSDT":   {"group": "DESCARTADA", "allocation": "0% - 5%", "profile": "No apta / Etiqueta En observación", "risk": "Etiqueta En observación (20/11), mínimos 0,00487, salidas >$400K y desbloqueo 15,65M el 28/11."},
    "OPENUSDT":   {"group": "DESCARTADA", "allocation": "0% - 5%", "profile": "No apta / Mínimos y >58% bloqueado", "risk": "Mínimos históricos (~0,0718–0,0728), >58% bloqueado y concentración <0,10."},
    "ALLOUSDT":   {"group": "DESCARTADA", "allocation": "0% - 5%", "profile": "No apta / Salidas y baja liquidez", "risk": "Caída -12,4% a 0,1173, salidas >-$65K, 48,1% bloqueado y vol/h <$50K."},
    "BICOUSDT":   {"group": "DESCARTADA", "allocation": "0% - 5%", "profile": "No apta / Ruptura de mínimos", "risk": "Ruptura bajo 0,010 a mínimos (~0,00943–0,00968), salidas spot y concentración 0,076."},
    "KAITOUSDT":  {"group": "DESCARTADA", "allocation": "0% - 5%", "profile": "No apta / Mínimos y oferta bloqueada", "risk": "Caída a mínimos (~0,1464–0,1477), 48,2% bloqueado, concentración 0,068 y MACD negativo."},
    "BONKUSDT":   {"group": "DESCARTADA", "allocation": "0% - 5%", "profile": "No apta / Mínimos anuales", "risk": "Mínimos anuales (~0,00000195), salidas -$266K y concentración ~0,024."},
    "TUTUSDT":    {"group": "DESCARTADA", "allocation": "0% - 5%", "profile": "No apta / Debilidad técnica", "risk": "Caída -11,4%, salida -$78,7K, bajo MA(99) y concentración ~0,13–0,14."},
    "ACEUSDT":    {"group": "DESCARTADA", "allocation": "0% - 5%", "profile": "No apta / Salidas y dilución", "risk": "Caída -8,5%, salidas >$180K, 21,8% bloqueado y MACD negativo."},
    "GIGGLEUSDT": {"group": "DESCARTADA", "allocation": "0% - 5%", "profile": "No apta / Salidas pico", "risk": "Caída -8,7%, salida pico -157,7K USDT, bajo MA(99) y concentración ~0,14."},
    "OGUSDT":     {"group": "DESCARTADA", "allocation": "0% - 5%", "profile": "No apta / Desbloqueo y micro-cap", "risk": "Desbloqueo ~1,16 mUSD el 22/11, cap <$10M y 1d en mínimos."},
    "MOVRUSDT":   {"group": "DESCARTADA", "allocation": "0% - 5%", "profile": "No apta / Liquidez deprimida", "risk": "Caída -6,4%, salidas >$30K y concentración <0,1."},
    "APEUSDT":    {"group": "DESCARTADA", "allocation": "0% - 5%", "profile": "No apta / Nuevos mínimos", "risk": "Nuevos mínimos (0,0678–0,0683), salidas pico -$104,7K y vol/h <$50K."},
    "HEIUSDT":    {"group": "DESCARTADA", "allocation": "0% - 5%", "profile": "No apta / Etiqueta En supervisión", "risk": "Etiqueta En supervisión, cap ~$6,8M, vol/h <$50K y salidas -$37,5K."},
    "NEIROUSDT":  {"group": "DESCARTADA", "allocation": "0% - 5%", "profile": "No apta / Rebote débil bajo medias", "risk": "Caída -6,72% en 24h, salidas pico -$110,3K, concentración ~0,08 y MACD negativo."},
    "COTIUSDT":   {"group": "DESCARTADA", "allocation": "0% - 5%", "profile": "No apta / Golpe fundamental", "risk": "Caída -7,1% por liquidación de DJED/SHEN al 31/12, salidas >$54K y concentración <0,1."},
    "SAGAUSDT":   {"group": "DESCARTADA", "allocation": "0% - 5%", "profile": "No apta / Cerca de mínimo histórico", "risk": "Ruptura bajo 0,0130 con $321K, salidas tras reabrir retiros y piso histórico en 0,01170."},
    "OPNUSDT":    {"group": "DESCARTADA", "allocation": "0% - 5%", "profile": "No apta / Alta oferta bloqueada", "risk": ">56,8% bloqueado, concentración ~0,08, salida -$31,3K y cerca de mínimo histórico (0,0280–0,0283)."},
    "SLPUSDT":    {"group": "DESCARTADA", "allocation": "0% - 5%", "profile": "No apta / Inflación ilimitada", "risk": "Suministro ilimitado inflacionario, salidas -$36,2K/-$19,6K, concentración <0,1 y mínimo 0,000388."},
    "GNSUSDT":    {"group": "DESCARTADA", "allocation": "0% - 5%", "profile": "No apta / Riesgo de delisting", "risk": "Etiqueta de monitoreo con riesgo de delisting, volumen <$10K/h y salidas >$70K."},
    "HUMAUSDT":   {"group": "DESCARTADA", "allocation": "0% - 5%", "profile": "No apta / Desbloqueo inminente", "risk": "Desbloqueo de 465,3M tokens (4,65%) el 25/11, salidas -$367K tras pico y MACD negativo."},
    "BEAMXUSDT":  {"group": "DESCARTADA", "allocation": "0% - 5%", "profile": "No apta / Salidas persistentes", "risk": "Caída -6,9% en 24h, salidas pico >-$139K, MACD negativo y baja generación de comisiones on-chain."},
    "TLMUSDT":    {"group": "DESCARTADA", "allocation": "0% - 5%", "profile": "No apta / Cerca de mínimo histórico", "risk": "Caída -7,0% en 24h, salidas spot pico -$70,5K, concentración <0,10 y soporte histórico en $0,000817."},
    "WLFIUSDT":   {"group": "DESCARTADA", "allocation": "0% - 5%", "profile": "No apta / Salidas fuertes", "risk": "Salidas netas >-$400K/h y presión de desbloqueos cerca de mínimos históricos (0,0435)."},
    "LSKUSDT":    {"group": "DESCARTADA", "allocation": "0% - 5%", "profile": "No apta / Dilución y fricción", "risk": "Migración/quema de tokens, concentración ~0,04 y desbloqueos diarios de ~75K LSK."},
    "HOMEUSDT":   {"group": "DESCARTADA", "allocation": "0% - 5%", "profile": "No apta / Desbloqueo y mínimos", "risk": "Desbloqueo de ~195,28M HOME el 28/11, mínimos históricos (0,00382) y volumen <$30K/h."},
    "HEMIUSDT":   {"group": "DESCARTADA", "allocation": "0% - 5%", "profile": "No apta / Desbloqueo y estructura débil", "risk": "Desbloqueo de ~58,7M tokens el 28/11, >61% bloqueado y salidas spot."},
    "ALTUSDT":    {"group": "DESCARTADA", "allocation": "0% - 5%", "profile": "No apta / Front-running por unlock", "risk": "Anticipación a desbloqueo de ~195,3M ALT a fin de noviembre cerca de mínimos (0,00417)."},
    "GALAUSDT":   {"group": "DESCARTADA", "allocation": "0% - 5%", "profile": "No apta / Salidas continuas", "risk": "Salidas netas persistentes (-$59,6K / -$34,9K) en mínimos anuales (0,001225)."},
    "TUSDT":      {"group": "DESCARTADA", "allocation": "0% - 5%", "profile": "No apta / Tendencia 1d bajista", "risk": "Liquidez <$10K/h y salidas netas persistentes deslizándose en 1d hacia 0,00315."},
    "QIUSDT":     {"group": "DESCARTADA", "allocation": "0% - 5%", "profile": "No apta / Riesgo de plataforma", "risk": "Etiqueta de monitoreo (Monitoring Tag) y liquidez <$15K/h."},
    "XAIUSDT":    {"group": "DESCARTADA", "allocation": "0% - 5%", "profile": "No apta / Emisión lineal y mínimos", "risk": "Emisión lineal diaria (456,7K tokens), mínimos históricos (0,00474) y volumen ~$12K/h."},
    "JASMYUSDT":  {"group": "DESCARTADA", "allocation": "0% - 5%", "profile": "No apta / Presión por delisting", "risk": "Liquidaciones por delisting regional en mínimos anuales (0,00295)."},
    "TOWNSUSDT":  {"group": "DESCARTADA", "allocation": "0% - 5%", "profile": "No apta / Mínimo histórico y lock", "risk": "69,6% de la oferta bloqueada y presión vendedora sostenida en mínimo histórico (0,000884)."},
    "DGBUSDT":    {"group": "DESCARTADA", "allocation": "0% - 5%", "profile": "No apta / Iliquidez severa", "risk": "Liquidez <5.000 USDT/h y salidas persistentes sin rebote en 15m."},
}


# =====================================================================
# 3. CONSULTAS DE MERCADO E INDICADORES
# =====================================================================
def binance_get(path: str, params: Optional[dict] = None) -> Optional[dict | list]:
    for base in BINANCE_ENDPOINTS:
        try:
            resp = requests.get(f"{base}{path}", params=params, timeout=10)
            if resp.status_code == 200:
                return resp.json()
        except requests.RequestException:
            continue
    return None


def calc_ema(values: List[float], period: int) -> Optional[float]:
    if len(values) < period:
        return None
    k = 2.0 / (period + 1)
    val = sum(values[:period]) / period
    for p in values[period:]:
        val = p * k + val * (1.0 - k)
    return val


def calc_rsi(values: List[float], period: int = 6) -> Optional[float]:
    if len(values) <= period:
        return None
    gains, losses = [], []
    for i in range(1, len(values)):
        diff = values[i] - values[i - 1]
        gains.append(max(diff, 0.0))
        losses.append(max(-diff, 0.0))
    avg_g = sum(gains[:period]) / period
    avg_l = sum(losses[:period]) / period
    for i in range(period, len(gains)):
        avg_g = (avg_g * (period - 1) + gains[i]) / period
        avg_l = (avg_l * (period - 1) + losses[i]) / period
    if avg_l == 0:
        return 100.0
    return 100.0 - (100.0 / (1.0 + (avg_g / avg_l)))


def get_klines(symbol: str, interval: str, limit: int = 120) -> List[dict]:
    raw = binance_get("/api/v3/klines", {"symbol": symbol, "interval": interval, "limit": limit})
    if not isinstance(raw, list):
        return []
    return [
        {
            "open": float(k[1]),
            "high": float(k[2]),
            "low": float(k[3]),
            "close": float(k[4]),
            "quote_vol": float(k[7]),
        }
        for k in raw
    ]


def get_24h_tickers() -> Dict[str, dict]:
    raw = binance_get("/api/v3/ticker/24hr")
    if not isinstance(raw, list):
        return {}
    return {item["symbol"]: item for item in raw if "symbol" in item}


def fmt(p: float) -> str:
    if p >= 100:
        return f"{p:,.2f}"
    if p >= 1:
        return f"{p:.4f}"
    if p >= 0.01:
        return f"{p:.5f}"
    if p >= 0.0001:
        return f"{p:.6f}"
    return f"{p:.8f}"


# =====================================================================
# 4. EVALUACIÓN DE OPORTUNIDAD EN CAÍDA SEGÚN EL RANKING
# =====================================================================
def evaluate_symbol(symbol: str, cfg: dict, ticker: dict) -> Optional[Tuple[str, str]]:
    group = cfg["group"]
    price = float(ticker["lastPrice"])
    pct_24h = float(ticker["priceChangePercent"])
    vol_24h = float(ticker["quoteVolume"])

    k15 = get_klines(symbol, "15m", limit=120)
    k1d = get_klines(symbol, "1d", limit=100)
    if len(k15) < 30 or len(k1d) < 20:
        return None

    c15 = [x["close"] for x in k15]
    h15_12h = [x["high"] for x in k15[-48:]]
    l15_12h = [x["low"] for x in k15[-48:]]
    l1d_60d = [x["low"] for x in k1d[-60:]]
    c1d = [x["close"] for x in k1d]

    ema25_15 = calc_ema(c15, 25)
    ema99_15 = calc_ema(c15, 99)
    rsi6_15 = calc_rsi(c15, 6)
    ema99_1d = calc_ema(c1d, 99)

    if group == "DESCARTADA":
        floor_60d = min(l1d_60d) if l1d_60d else price
        if ALERT_ON_DISCARDED_NEW_LOW and price <= floor_60d * 1.005:
            msg = (
                f"🗑️ *DESCARTADA EN NUEVO MÍNIMO* — `{symbol}` (`{cfg['allocation']}`)\n"
                f"• Precio: *{fmt(price)}* | 24h: `{pct_24h:+.2f}%` | Mín 60d: `{fmt(floor_60d)}`\n"
                f"• Perfil: _{cfg['profile']}_\n"
                f"• Riesgo: _{cfg['risk']}_"
            )
            return ("DISCARDED_NEW_LOW", msg)
        return None

    recent_high = max(h15_12h) if h15_12h else price
    drop_from_12h_high = ((recent_high - price) / recent_high * 100.0) if recent_high > 0 else 0.0

    targets: List[float] = list(cfg.get("dip_targets", []))
    if not targets and ema99_15 is not None:
        targets = [round(ema99_15, 8)]

    min_drop = float(cfg.get("min_drop_pct", 6.0))
    matched_target = min([t for t in targets if price <= t * 1.005], default=None)

    hit_target = matched_target is not None
    hit_drop = drop_from_12h_high >= min_drop and pct_24h <= -1.5

    if not (hit_target or hit_drop):
        return None

    if rsi6_15 is not None and rsi6_15 > 80 and not hit_target:
        return None

    badge = {
        "ESTRUCTURAL": "⭐ FAVORITO ESTRUCTURAL",
        "TACTICA_PUENTE": "🎯 TÁCTICA PUENTE",
        "CAZA_REBOTE": "⚡ CAZA DE REBOTE",
    }.get(group, group)

    kind = "TARGET_HIT" if hit_target else "DIP_DROP"
    targets_txt = " / ".join(fmt(t) for t in targets) if targets else "Dinámico"
    rsi_txt = f"{rsi6_15:.1f}" if rsi6_15 is not None else "N/A"
    ema99_15_txt = fmt(ema99_15) if ema99_15 is not None else "N/A"
    ema99_1d_txt = fmt(ema99_1d) if ema99_1d is not None else "N/A"

    msg = (
        f"{badge} — *`{symbol}`* (`{cfg['allocation']}`)\n"
        f"• Catálogo: *{cfg['profile']}*\n"
        f"• Precio: *{fmt(price)}* | 24h: `{pct_24h:+.2f}%` | Retroceso 12h: `-{drop_from_12h_high:.2f}%`\n"
        f"• Zonas límite: `{targets_txt}` | Mín 12h: `{fmt(min(l15_12h))}`\n"
        f"• 15m: `RSI(6)={rsi_txt}` | `EMA25={fmt(ema25_15) if ema25_15 else 'N/A'}` | `EMA99={ema99_15_txt}`\n"
        f"• 1D EMA99: `{ema99_1d_txt}` | Vol 24h: `${vol_24h:,.0f}`\n"
        f"• Lectura: _{cfg.get('tech', '')}_\n"
        f"• Riesgo a vigilar: _{cfg.get('risk', '')}_"
    )
    return (kind, msg)


# =====================================================================
# 5. PERSISTENCIA Y NOTIFICACIÓN TELEGRAM
# =====================================================================
def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def save_state(state: dict) -> None:
    STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")


def send_telegram(text: str) -> bool:
    if "TU_BOT_TOKEN_AQUI" in TELEGRAM_BOT_TOKEN or "TU_CHAT_ID_AQUI" in TELEGRAM_CHAT_ID:
        print("[MODO PRUEBA SIN TOKEN] Alerta generada:")
        print(text)
        print("-" * 55)
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        r = requests.post(
            url,
            json={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": text,
                "parse_mode": "Markdown",
                "disable_web_page_preview": True,
            },
            timeout=10,
        )
        return r.status_code == 200
    except requests.RequestException as exc:
        print(f"[ERROR TELEGRAM] {exc}")
        return False


def main() -> None:
    now = time.time()
    cooldown_sec = COOLDOWN_MINUTES * 60
    state = load_state()

    tickers = get_24h_tickers()
    if not tickers:
        print("[ERROR] No se pudieron obtener los tickers 24h de Binance.")
        return

    alerts_sent = 0
    for symbol, cfg in ASSETS_DB.items():
        ticker = tickers.get(symbol)
        if not ticker:
            continue
        result = evaluate_symbol(symbol, cfg, ticker)
        if not result:
            continue

        kind, msg = result
        key = f"{symbol}:{kind}"
        last_ts = float(state.get(key, 0.0))

        if now - last_ts >= cooldown_sec:
            if send_telegram(msg) or "TU_BOT_TOKEN_AQUI" in TELEGRAM_BOT_TOKEN:
                state[key] = now
                alerts_sent += 1

    save_state(state)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    print(f"[{ts}] Auditoría ejecutada sobre {len(ASSETS_DB)} activos. Alertas emitidas: {alerts_sent}")


if __name__ == "__main__":
    main()
