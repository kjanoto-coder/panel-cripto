import html
import io
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import requests

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    HAS_MATPLOTLIB = True
except ImportError:
    HAS_MATPLOTLIB = False

# =====================================================================
# 1. CONFIGURACIÓN AISLADA (EXCLUSIVO PARA TOPIC_ID_PERDEDORAS)
# =====================================================================
TELEGRAM_BOT_TOKEN = (
    os.getenv("TELEGRAM_BOT_TOKEN")
    or os.getenv("TELEGRAM_TOKEN")
    or "TU_BOT_TOKEN_AQUI"
).strip()

CHAT_ID_GROUP = os.getenv("CHAT_ID", "").strip()
CHAT_ID_FALLBACK = os.getenv("TELEGRAM_CHAT_ID", "").strip()
TOPIC_ID_PERDEDORAS = os.getenv("TOPIC_ID_PERDEDORAS", "").strip()

COOLDOWN_MINUTES = int(os.getenv("COOLDOWN_MINUTES", "180"))
STATE_FILE = Path(os.getenv("STATE_FILE", "spot_audit_state.json"))
ALERT_ON_RECHAZO = os.getenv("ALERT_ON_RECHAZO", "true").lower() == "true"

BINANCE_ENDPOINTS = [
    "https://data-api.binance.vision",
    "https://api.binance.com",
    "https://api1.binance.com",
    "https://api2.binance.com",
    "https://api3.binance.com",
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
}

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
    "MANTRAUSDT": {"group": "DESCARTADA", "allocation": "0% - 5%", "profile": "No apta / Mínimos y dilución", "tech": "Estructura bajista extendida sin soporte confirmado.", "risk": "Mínimos históricos (~0,00172), salida -$430,6K, concentración 0,06 y ~1,83M/día desbloqueados."},
    "TNSRUSDT":   {"group": "DESCARTADA", "allocation": "0% - 5%", "profile": "No apta / Mínimos récord", "tech": "Sin demanda compradora sostenida en 15m/1d.", "risk": "Mínimos récord (~0,0178), caída -11,57% y concentración <0,08."},
    "MITOUSDT":   {"group": "DESCARTADA", "allocation": "0% - 5%", "profile": "No apta / Etiqueta En observación", "tech": "Presión vendedora activa bajo medias móviles.", "risk": "Etiqueta En observación (20/11), mínimos 0,00487, salidas >$400K y desbloqueo 15,65M el 28/11."},
    "OPENUSDT":   {"group": "DESCARTADA", "allocation": "0% - 5%", "profile": "No apta / Mínimos y >58% bloqueado", "tech": "Debilidad estructural en mínimos históricos.", "risk": "Mínimos históricos (~0,0718–0,0728), >58% bloqueado y concentración <0,10."},
    "ALLOUSDT":   {"group": "DESCARTADA", "allocation": "0% - 5%", "profile": "No apta / Salidas y baja liquidez", "tech": "Rebotes débiles absorbidos por oferta.", "risk": "Caída -12,4% a 0,1173, salidas >-$65K, 48,1% bloqueado y vol/h <$50K."},
    "BICOUSDT":   {"group": "DESCARTADA", "allocation": "0% - 5%", "profile": "No apta / Ruptura de mínimos", "tech": "Perforación de piso técnico sin recuperación.", "risk": "Ruptura bajo 0,010 a mínimos (~0,00943–0,00968), salidas spot y concentración 0,076."},
    "KAITOUSDT":  {"group": "DESCARTADA", "allocation": "0% - 5%", "profile": "No apta / Mínimos y oferta bloqueada", "tech": "Momentum negativo en gráficos intradía y diario.", "risk": "Caída a mínimos (~0,1464–0,1477), 48,2% bloqueado, concentración 0,068 y MACD negativo."},
    "BONKUSDT":   {"group": "DESCARTADA", "allocation": "0% - 5%", "profile": "No apta / Mínimos anuales", "tech": "Rotación vendedora persistente sobre soportes.", "risk": "Mínimos anuales (~0,00000195), salidas -$266K y concentración ~0,024."},
    "TUTUSDT":    {"group": "DESCARTADA", "allocation": "0% - 5%", "profile": "No apta / Debilidad técnica", "tech": "Cotizando por debajo de MA(99) sin flujo.", "risk": "Caída -11,4%, salida -$78,7K, bajo MA(99) y concentración ~0,13–0,14."},
    "ACEUSDT":    {"group": "DESCARTADA", "allocation": "0% - 5%", "profile": "No apta / Salidas y dilución", "tech": "MACD negativo y distribución constante.", "risk": "Caída -8,5%, salidas >$180K, 21,8% bloqueado y MACD negativo."},
    "GIGGLEUSDT": {"group": "DESCARTADA", "allocation": "0% - 5%", "profile": "No apta / Salidas pico", "tech": "Rechazo bajo MA(99) con salida de capital.", "risk": "Caída -8,7%, salida pico -157,7K USDT, bajo MA(99) y concentración ~0,14."},
    "OGUSDT":     {"group": "DESCARTADA", "allocation": "0% - 5%", "profile": "No apta / Desbloqueo y micro-cap", "tech": "Presión previa a desbloqueo en mínimos diarios.", "risk": "Desbloqueo ~1,16 mUSD el 22/11, cap <$10M y 1d en mínimos."},
    "MOVRUSDT":   {"group": "DESCARTADA", "allocation": "0% - 5%", "profile": "No apta / Liquidez deprimida", "tech": "Bajo interés comprador y goteo bajista.", "risk": "Caída -6,4%, salidas >$30K y concentración <0,1."},
    "APEUSDT":    {"group": "DESCARTADA", "allocation": "0% - 5%", "profile": "No apta / Nuevos mínimos", "tech": "Ruptura de soportes con bajo volumen horario.", "risk": "Nuevos mínimos (0,0678–0,0683), salidas pico -$104,7K y vol/h <$50K."},
    "HEIUSDT":    {"group": "DESCARTADA", "allocation": "0% - 5%", "profile": "No apta / Etiqueta En supervisión", "tech": "Riesgo operativo y falta de profundidad.", "risk": "Etiqueta En supervisión, cap ~$6,8M, vol/h <$50K y salidas -$37,5K."},
    "NEIROUSDT":  {"group": "DESCARTADA", "allocation": "0% - 5%", "profile": "No apta / Rebote débil bajo medias", "tech": "Sin fuerza para recuperar medias clave.", "risk": "Caída -6,72% en 24h, salidas pico -$110,3K, concentración ~0,08 y MACD negativo."},
    "COTIUSDT":   {"group": "DESCARTADA", "allocation": "0% - 5%", "profile": "No apta / Golpe fundamental", "tech": "Deterioro estructural por noticias del ecosistema.", "risk": "Caída -7,1% por liquidación de DJED/SHEN al 31/12, salidas >$54K y concentración <0,1."},
    "SAGAUSDT":   {"group": "DESCARTADA", "allocation": "0% - 5%", "profile": "No apta / Cerca de mínimo histórico", "tech": "Pérdida de nivel clave 0,0130 con presión vendedora.", "risk": "Ruptura bajo 0,0130 con $321K, salidas tras reabrir retiros y piso histórico en 0,01170."},
    "OPNUSDT":    {"group": "DESCARTADA", "allocation": "0% - 5%", "profile": "No apta / Alta oferta bloqueada", "tech": "Presión de oferta bloqueada sobre mínimos.", "risk": ">56,8% bloqueado, concentración ~0,08, salida -$31,3K y cerca de mínimo histórico (0,0280–0,0283)."},
    "SLPUSDT":    {"group": "DESCARTADA", "allocation": "0% - 5%", "profile": "No apta / Inflación ilimitada", "tech": "Tendencia secular bajista sin piso firme.", "risk": "Suministro ilimitado inflacionario, salidas -$36,2K/-$19,6K, concentración <0,1 y mínimo 0,000388."},
    "GNSUSDT":    {"group": "DESCARTADA", "allocation": "0% - 5%", "profile": "No apta / Riesgo de delisting", "tech": "Iliquidez y riesgo regulatorio/de listado.", "risk": "Etiqueta de monitoreo con riesgo de delisting, volumen <$10K/h y salidas >$70K."},
    "HUMAUSDT":   {"group": "DESCARTADA", "allocation": "0% - 5%", "profile": "No apta / Desbloqueo inminente", "tech": "Salidas fuertes anticipando desbloqueo masivo.", "risk": "Desbloqueo de 465,3M tokens (4,65%) el 25/11, salidas -$367K tras pico y MACD negativo."},
    "BEAMXUSDT":  {"group": "DESCARTADA", "allocation": "0% - 5%", "profile": "No apta / Salidas persistentes", "tech": "MACD negativo y flujo neto vendedor.", "risk": "Caída -6,9% en 24h, salidas pico >-$139K, MACD negativo y baja generación de comisiones on-chain."},
    "TLMUSDT":    {"group": "DESCARTADA", "allocation": "0% - 5%", "profile": "No apta / Cerca de mínimo histórico", "tech": "Deslizamiento continuo hacia soporte histórico.", "risk": "Caída -7,0% en 24h, salidas spot pico -$70,5K, concentración <0,10 y soporte histórico en $0,000817."},
    "WLFIUSDT":   {"group": "DESCARTADA", "allocation": "0% - 5%", "profile": "No apta / Salidas fuertes", "tech": "Distribución agresiva cerca de mínimos.", "risk": "Salidas netas >-$400K/h y presión de desbloqueos cerca de mínimos históricos (0,0435)."},
    "LSKUSDT":    {"group": "DESCARTADA", "allocation": "0% - 5%", "profile": "No apta / Dilución y fricción", "tech": "Fricción por migración y goteo diario de oferta.", "risk": "Migración/quema de tokens, concentración ~0,04 y desbloqueos diarios de ~75K LSK."},
    "HOMEUSDT":   {"group": "DESCARTADA", "allocation": "0% - 5%", "profile": "No apta / Desbloqueo y mínimos", "tech": "Baja liquidez ante desbloqueo de fin de mes.", "risk": "Desbloqueo de ~195,28M HOME el 28/11, mínimos históricos (0,00382) y volumen <$30K/h."},
    "HEMIUSDT":   {"group": "DESCARTADA", "allocation": "0% - 5%", "profile": "No apta / Desbloqueo y estructura débil", "tech": "Estructura bajista con >61% bloqueado.", "risk": "Desbloqueo de ~58,7M tokens el 28/11, >61% bloqueado y salidas spot."},
    "ALTUSDT":    {"group": "DESCARTADA", "allocation": "0% - 5%", "profile": "No apta / Front-running por unlock", "tech": "Ventas anticipadas frente a desbloqueo.", "risk": "Anticipación a desbloqueo de ~195,3M ALT a fin de noviembre cerca de mínimos (0,00417)."},
    "GALAUSDT":   {"group": "DESCARTADA", "allocation": "0% - 5%", "profile": "No apta / Salidas continuas", "tech": "Goteo en mínimos anuales sin catalizador.", "risk": "Salidas netas persistentes (-$59,6K / -$34,9K) en mínimos anuales (0,001225)."},
    "TUSDT":      {"group": "DESCARTADA", "allocation": "0% - 5%", "profile": "No apta / Tendencia 1d bajista", "tech": "Baja liquidez y pendiente diaria negativa.", "risk": "Liquidez <$10K/h y salidas netas persistentes deslizándose en 1d hacia 0,00315."},
    "QIUSDT":     {"group": "DESCARTADA", "allocation": "0% - 5%", "profile": "No apta / Riesgo de plataforma", "tech": "Monitoreo activo y escasa profundidad.", "risk": "Etiqueta de monitoreo (Monitoring Tag) y liquidez <$15K/h."},
    "XAIUSDT":    {"group": "DESCARTADA", "allocation": "0% - 5%", "profile": "No apta / Emisión lineal y mínimos", "tech": "Dilución diaria en mínimos históricos.", "risk": "Emisión lineal diaria (456,7K tokens), mínimos históricos (0,00474) y volumen ~$12K/h."},
    "JASMYUSDT":  {"group": "DESCARTADA", "allocation": "0% - 5%", "profile": "No apta / Presión por delisting", "tech": "Ventas forzadas en mínimos anuales.", "risk": "Liquidaciones por delisting regional en mínimos anuales (0,00295)."},
    "TOWNSUSDT":  {"group": "DESCARTADA", "allocation": "0% - 5%", "profile": "No apta / Mínimo histórico y lock", "tech": "Oferta bloqueada alta y debilidad extrema.", "risk": "69,6% de la oferta bloqueada y presión vendedora sostenida en mínimo histórico (0,000884)."},
    "DGBUSDT":    {"group": "DESCARTADA", "allocation": "0% - 5%", "profile": "No apta / Iliquidez severa", "tech": "Sin volumen ni reacción técnica en 15m.", "risk": "Liquidez <5.000 USDT/h y salidas persistentes sin rebote en 15m."},
}


# =====================================================================
# 3. CONSULTAS DE MERCADO E INDICADORES
# =====================================================================
def fetch_json_debug(url: str, params: Optional[dict] = None) -> Tuple[Optional[dict | list], Optional[str]]:
    try:
        resp = requests.get(url, params=params, headers=HEADERS, timeout=12)
        if resp.status_code == 200:
            return resp.json(), None
        return None, f"HTTP {resp.status_code}: {resp.text[:140]}"
    except requests.RequestException as exc:
        return None, f"EXC {type(exc).__name__}: {exc}"


def get_24h_tickers() -> Tuple[Dict[str, dict], str]:
    for base in BINANCE_ENDPOINTS:
        data, _ = fetch_json_debug(f"{base}/api/v3/ticker/24hr")
        if isinstance(data, list) and len(data) > 0:
            print(f"[OK] Tickers 24h obtenidos desde {base} ({len(data)} pares).")
            return ({item["symbol"]: item for item in data if "symbol" in item}, "BINANCE")

    normalized: Dict[str, dict] = {}
    for page in (1, 2):
        cg_data, _ = fetch_json_debug(
            "https://api.coingecko.com/api/v3/coins/markets",
            params={
                "vs_currency": "usd",
                "order": "market_cap_desc",
                "per_page": 250,
                "page": page,
                "price_change_percentage": "24h",
            },
        )
        if isinstance(cg_data, list) and len(cg_data) > 0:
            for coin in cg_data:
                sym = f"{coin.get('symbol', '').upper()}USDT"
                price = coin.get("current_price")
                pct = coin.get("price_change_percentage_24h")
                vol = coin.get("total_volume")
                if sym != "USDT" and price is not None and sym not in normalized:
                    normalized[sym] = {
                        "symbol": sym,
                        "lastPrice": str(price),
                        "priceChangePercent": str(pct if pct is not None else 0.0),
                        "quoteVolume": str(vol if vol is not None else 0.0),
                    }
        if page == 1:
            time.sleep(1.0)

    if normalized:
        print(f"[OK] Respaldo CoinGecko cargado ({len(normalized)} pares).")
        return normalized, "COINGECKO"

    return {}, "NONE"


def get_klines(symbol: str, interval: str, limit: int = 120) -> List[dict]:
    for base in BINANCE_ENDPOINTS:
        raw, _ = fetch_json_debug(
            f"{base}/api/v3/klines",
            params={"symbol": symbol, "interval": interval, "limit": limit},
        )
        if isinstance(raw, list) and len(raw) > 0:
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
    return []


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
# 4. CÁLCULO DE SENTIMIENTO DE COMPRA Y PROBABILIDAD DE REBOTE (%)
# =====================================================================
def compute_rebound_scoring(
    group: str,
    price: float,
    vol_24h: float,
    rsi6_15: Optional[float],
    ema99_1d: Optional[float],
    hit_target: bool,
) -> Tuple[str, str, int, int, str]:
    """
    Devuelve: (veredicto, emoji_semaforo, color_order, probabilidad_pct, barra_5_bloques)
    color_order: 0 = Rojo (RECHAZO), 1 = Amarillo (PRECAUCIÓN), 2 = Verde (COMPRA)
    """
    base_map = {
        "ESTRUCTURAL": 62,
        "TACTICA_PUENTE": 48,
        "CAZA_REBOTE": 36,
        "DESCARTADA": 12,
    }
    score = base_map.get(group, 30)

    if rsi6_15 is not None:
        if rsi6_15 < 15:
            score += 16
        elif rsi6_15 < 30:
            score += 11
        elif rsi6_15 < 45:
            score += 5
        elif rsi6_15 > 75:
            score -= 12

    if hit_target:
        score += 10

    if ema99_1d is not None and ema99_1d > 0:
        dist_1d = (price - ema99_1d) / ema99_1d
        if dist_1d >= -0.03:
            score += 6
        elif dist_1d < -0.25:
            score -= 5

    if vol_24h >= 10_000_000:
        score += 5
    elif vol_24h < 500_000:
        score -= 6

    if group == "DESCARTADA":
        prob = max(5, min(28, score))
    else:
        prob = max(20, min(92, score))

    if group == "DESCARTADA" or prob < 35:
        verdict = "RECHAZO"
        light = "🔴"
        color_order = 0
        block = "🟥"
    elif prob >= 65:
        verdict = "COMPRA"
        light = "🟢"
        color_order = 2
        block = "🟩"
    else:
        verdict = "PRECAUCIÓN"
        light = "🟡"
        color_order = 1
        block = "🟨"

    filled = max(1, min(5, round(prob / 20)))
    bar = (block * filled) + ("⬜" * (5 - filled))
    return verdict, light, color_order, prob, bar


# =====================================================================
# 5. EVALUACIÓN DE MONEDA Y CONSTRUCCIÓN DE DATOS
# =====================================================================
def evaluate_symbol(symbol: str, cfg: dict, ticker: dict, source: str) -> Optional[dict]:
    group = cfg["group"]
    base_coin = symbol.replace("USDT", "")
    price = float(ticker["lastPrice"])
    pct_24h = float(ticker["priceChangePercent"])
    vol_24h = float(ticker["quoteVolume"])

    k15 = get_klines(symbol, "15m", limit=120) if source == "BINANCE" else []
    k1d = get_klines(symbol, "1d", limit=100) if source == "BINANCE" else []
    has_klines = len(k15) >= 30 and len(k1d) >= 20

    c15 = [x["close"] for x in k15] if has_klines else []
    h15_12h = [x["high"] for x in k15[-48:]] if has_klines else []
    l15_12h = [x["low"] for x in k15[-48:]] if has_klines else []
    c1d = [x["close"] for x in k1d] if has_klines else []

    ema25_15 = calc_ema(c15, 25) if has_klines else None
    ema99_15 = calc_ema(c15, 99) if has_klines else None
    rsi6_15 = calc_rsi(c15, 6) if has_klines else None
    ema99_1d = calc_ema(c1d, 99) if has_klines else None

    recent_high = max(h15_12h) if h15_12h else price
    drop_from_12h_high = ((recent_high - price) / recent_high * 100.0) if (has_klines and recent_high > 0) else 0.0

    targets: List[float] = list(cfg.get("dip_targets", []))
    if not targets and ema99_15 is not None:
        targets = [round(ema99_15, 8)]

    min_drop = float(cfg.get("min_drop_pct", 6.0))
    matched_target = min([t for t in targets if price <= t * 1.005], default=None)

    hit_target = matched_target is not None
    hit_drop_12h = has_klines and drop_from_12h_high >= min_drop and pct_24h <= -1.5
    hit_drop_24h = (not has_klines) and (pct_24h <= -min_drop)

    if group == "DESCARTADA":
        if not ALERT_ON_RECHAZO:
            return None
        if not ((has_klines and drop_from_12h_high >= 7.0) or pct_24h <= -7.0):
            return None
    else:
        if not (hit_target or hit_drop_12h or hit_drop_24h):
            return None
        if rsi6_15 is not None and rsi6_15 > 80 and not hit_target:
            return None

    verdict, light, color_order, prob, bar = compute_rebound_scoring(
        group=group,
        price=price,
        vol_24h=vol_24h,
        rsi6_15=rsi6_15,
        ema99_1d=ema99_1d,
        hit_target=hit_target,
    )

    badge = {
        "ESTRUCTURAL": "⭐ FAVORITO ESTRUCTURAL",
        "TACTICA_PUENTE": "🎯 TÁCTICA PUENTE",
        "CAZA_REBOTE": "⚡ CAZA DE REBOTE",
        "DESCARTADA": "🚫 DESCARTADA / EVITAR",
    }.get(group, group)

    kind = "RECHAZO" if group == "DESCARTADA" else ("TARGET_HIT" if hit_target else "DIP_DROP")
    targets_txt = " / ".join(fmt(t) for t in targets) if targets else "Dinámico"

    url_ia = f"https://www.binance.com/es/price/{base_coin.lower()}"
    url_trade = f"https://www.binance.com/es/trade/{base_coin}_USDT?type=spot"

    if has_klines:
        rsi_txt = f"{rsi6_15:.1f}" if rsi6_15 is not None else "N/A"
        ema25_txt = fmt(ema25_15) if ema25_15 is not None else "N/A"
        ema99_15_txt = fmt(ema99_15) if ema99_15 is not None else "N/A"
        ema99_1d_txt = fmt(ema99_1d) if ema99_1d is not None else "N/A"
        tech_block = (
            f"• Zonas límite: <code>{targets_txt}</code> | Mín 12h: <code>{fmt(min(l15_12h))}</code> | Retroceso 12h: <code>-{drop_from_12h_high:.2f}%</code>\n"
            f"• 15m: <code>RSI(6)={rsi_txt}</code> | <code>EMA25={ema25_txt}</code> | <code>EMA99={ema99_15_txt}</code>\n"
            f"• 1D EMA99: <code>{ema99_1d_txt}</code> | Vol 24h: <code>${vol_24h:,.0f}</code>\n"
        )
    else:
        tech_block = (
            f"• Zonas límite: <code>{targets_txt}</code> | Vol 24h: <code>${vol_24h:,.0f}</code>\n"
        )

    card_msg = (
        f"• <b>{html.escape(base_coin)}</b> | Base (12h): <code>${fmt(recent_high)}</code> → Actual: <code>${fmt(price)}</code> | <b>{pct_24h:+.2f}%</b>\n"
        f"{bar}  (Rebote: <b>{prob}%</b>)\n"
        f"└ <a href=\"{url_ia}\">📊 Resumen IA</a> | <a href=\"{url_trade}\">🔶 Tradear</a>\n\n"
        f"{badge} — <code>{html.escape(symbol)}</code> (<b>{html.escape(cfg['allocation'])}</b>)\n"
        f"• Catálogo: <b>{html.escape(cfg['profile'])}</b>\n"
        f"{tech_block}"
        f"• Lectura: <i>{html.escape(cfg.get('tech', ''))}</i>\n"
        f"• Riesgo a vigilar: <i>{html.escape(cfg.get('risk', ''))}</i>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"{light} <b>SENTIMIENTO DE COMPRA : {verdict}</b>\n"
        f"📈 <b>PROBABILIDAD DE REBOTE : {prob}%</b>"
    )

    return {
        "symbol": symbol,
        "coin": base_coin,
        "kind": kind,
        "verdict": verdict,
        "light": light,
        "color_order": color_order,
        "prob": prob,
        "pct_24h": pct_24h,
        "price": price,
        "card_msg": card_msg,
    }


# =====================================================================
# 6. GENERADOR DE RESUMEN DE MONEDAS (TEXTO + GRÁFICO DE BARRAS PNG)
# =====================================================================
def build_summary_text(sorted_items: List[dict]) -> str:
    sections = [
        (0, "🔴", "RECHAZO"),
        (1, "🟡", "PRECAUCIÓN"),
        (2, "🟢", "COMPRA"),
    ]
    lines = ["📊 <b>RESUMEN DE MONEDAS</b>"]
    for c_order, emoji, label in sections:
        group_items = [x for x in sorted_items if x["color_order"] == c_order]
        if not group_items:
            continue
        lines.append(f"\n{emoji} <b>{label} (menor a mayor):</b>")
        for it in group_items:
            lines.append(
                f"• <b>{html.escape(it['coin'])}</b>: <code>{it['prob']}%</code> (<code>{it['pct_24h']:+.2f}%</code>)"
            )
    return "\n".join(lines)


def build_summary_chart_png(sorted_items: List[dict]) -> Optional[bytes]:
    if not HAS_MATPLOTLIB or not sorted_items:
        return None

    n = len(sorted_items)
    fig_w = max(8.0, min(16.0, n * 0.85 + 2.0))
    fig, ax = plt.subplots(figsize=(fig_w, 4.6), dpi=160)

    bg_color = "#0b0f1c"
    grid_color = "#1b2438"
    fig.patch.set_facecolor(bg_color)
    ax.set_facecolor(bg_color)

    ax.grid(True, axis="y", color=grid_color, linestyle="-", linewidth=0.7, zorder=0)
    ax.grid(True, axis="x", color=grid_color, linestyle="-", linewidth=0.5, alpha=0.5, zorder=0)

    fill_map = {0: "#ff1744", 1: "#ffd600", 2: "#00e676"}
    edge_map = {0: "#ffd600", 1: "#ffd600", 2: "#00e676"}
    txt_map = {0: "#ff1744", 1: "#ffd600", 2: "#00e676"}

    x_pos = list(range(n))
    probs = [it["prob"] for it in sorted_items]
    coins = [it["coin"] for it in sorted_items]
    fills = [fill_map[it["color_order"]] for it in sorted_items]
    edges = [edge_map[it["color_order"]] for it in sorted_items]

    bars = ax.bar(x_pos, probs, width=0.52, color=fills, edgecolor=edges, linewidth=1.6, zorder=3)

    for idx, (bar, it) in enumerate(zip(bars, sorted_items)):
        p = it["prob"]
        c_txt = txt_map[it["color_order"]]
        # Porcentaje arriba de la barra
        ax.text(
            bar.get_x() + bar.get_width() / 2.0,
            p + 2.5,
            f"{p}%",
            ha="center",
            va="bottom",
            color=c_txt,
            fontsize=9.5,
            fontweight="bold",
            zorder=5,
        )
        # Badge circular con el nombre de la moneda
        y_badge = max(p * 0.52, 8.0)
        ax.text(
            bar.get_x() + bar.get_width() / 2.0,
            y_badge,
            it["coin"],
            ha="center",
            va="center",
            color="#ffffff",
            fontsize=6.5,
            fontweight="bold",
            bbox=dict(boxstyle="circle,pad=0.35", facecolor="#0b0f1c", edgecolor=c_txt, linewidth=1.1),
            zorder=6,
        )

    ax.set_title("RESUMEN DE MONEDAS", color="#ffffff", fontsize=13, fontweight="bold", pad=16)
    ax.set_ylim(0, 108)
    ax.set_xticks(x_pos)
    ax.set_xticklabels(coins, rotation=42, ha="right", color="#cbd5e1", fontsize=8.5, fontweight="bold")
    ax.tick_params(axis="y", left=False, labelleft=False)
    for spine in ("top", "right", "left"):
        ax.spines[spine].set_visible(False)
    ax.spines["bottom"].set_color("#27324a")

    plt.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", facecolor=bg_color)
    plt.close(fig)
    buf.seek(0)
    return buf.read()


# =====================================================================
# 7. PERSISTENCIA Y ENVÍO ESTRICTO A TOPIC_ID_PERDEDORAS
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


def _get_telegram_target() -> Optional[Tuple[int, List[str]]]:
    if not TOPIC_ID_PERDEDORAS.isdigit() or int(TOPIC_ID_PERDEDORAS) <= 1:
        print("[ERROR CONFIG] TOPIC_ID_PERDEDORAS no está configurado o es inválido. Envío cancelado.")
        return None
    candidates = []
    for cid in (CHAT_ID_GROUP, CHAT_ID_FALLBACK):
        if cid and cid not in candidates:
            candidates.append(cid)
    if not candidates or "TU_BOT_TOKEN_AQUI" in TELEGRAM_BOT_TOKEN:
        print("[ERROR CONFIG] Faltan credenciales de Telegram o CHAT_ID.")
        return None
    return int(TOPIC_ID_PERDEDORAS), candidates


def send_to_perdedoras_topic(text: str) -> bool:
    """Envía mensaje HTML exclusivamente al tópico TOPIC_ID_PERDEDORAS."""
    target = _get_telegram_target()
    if not target:
        return False
    thread_id, candidates = target
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"

    last_err = ""
    for cid in candidates:
        payload = {
            "chat_id": cid,
            "message_thread_id": thread_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
        try:
            r = requests.post(url, json=payload, timeout=12)
            if r.status_code == 200:
                return True
            last_err = f"chat_id={cid} -> HTTP {r.status_code}: {r.text[:180]}"
        except requests.RequestException as exc:
            last_err = f"chat_id={cid} -> EXC {exc}"

    print(f"[ERROR TELEGRAM TOPIC_ID_PERDEDORAS={thread_id}] {last_err}")
    return False


def send_photo_to_perdedoras_topic(png_bytes: bytes, caption: str) -> bool:
    """Envía gráfico PNG + caption exclusivamente al tópico TOPIC_ID_PERDEDORAS."""
    target = _get_telegram_target()
    if not target:
        return False
    thread_id, candidates = target
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"

    last_err = ""
    for cid in candidates:
        try:
            files = {"photo": ("resumen_monedas.png", png_bytes, "image/png")}
            data = {
                "chat_id": cid,
                "message_thread_id": str(thread_id),
                "caption": caption,
                "parse_mode": "HTML",
            }
            r = requests.post(url, data=data, files=files, timeout=20)
            if r.status_code == 200:
                return True
            last_err = f"chat_id={cid} -> HTTP {r.status_code}: {r.text[:180]}"
        except requests.RequestException as exc:
            last_err = f"chat_id={cid} -> EXC {exc}"

    print(f"[ERROR TELEGRAM PHOTO TOPIC_ID_PERDEDORAS={thread_id}] {last_err}")
    return False


def main() -> None:
    now = time.time()
    cooldown_sec = COOLDOWN_MINUTES * 60
    state = load_state()

    tickers, source = get_24h_tickers()
    if not tickers:
        print("[ERROR] No se pudieron obtener los tickers 24h ni de Binance ni del respaldo.")
        return

    triggered: List[dict] = []
    for symbol, cfg in ASSETS_DB.items():
        ticker = tickers.get(symbol)
        if not ticker:
            continue
        item = evaluate_symbol(symbol, cfg, ticker, source)
        if not item:
            continue

        key = f"v4:{symbol}:{item['kind']}"
        last_ts = float(state.get(key, 0.0))
        if now - last_ts >= cooldown_sec:
            item["state_key"] = key
            triggered.append(item)

    if not triggered:
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        print(f"[{ts}] Auditoría completada ({len(ASSETS_DB)} activos | Fuente: {source}). Sin alertas nuevas.")
        return

    # Ordenar por color (0=Rojo, 1=Amarillo, 2=Verde) y probabilidad de MENOR a MAYOR dentro de cada color
    triggered.sort(key=lambda x: (x["color_order"], x["prob"], x["coin"]))

    # 1) Enviar RESUMEN DE MONEDAS al inicio (gráfico PNG + texto ordenado)
    summary_text = build_summary_text(triggered)
    chart_png = build_summary_chart_png(triggered)

    if chart_png:
        if len(summary_text) <= 1000:
            send_photo_to_perdedoras_topic(chart_png, summary_text)
        else:
            send_photo_to_perdedoras_topic(chart_png, "📊 <b>RESUMEN DE MONEDAS</b>")
            send_to_perdedoras_topic(summary_text)
    else:
        send_to_perdedoras_topic(summary_text)

    time.sleep(0.5)

    # 2) Enviar fichas detalladas en el mismo orden
    alerts_sent = 0
    for item in triggered:
        if send_to_perdedoras_topic(item["card_msg"]):
            state[item["state_key"]] = now
            alerts_sent += 1
            time.sleep(0.35)

    save_state(state)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    print(f"[{ts}] Auditoría completada ({len(ASSETS_DB)} activos | Fuente: {source}). Fichas emitidas en Monedas perdedoras: {alerts_sent}")


if __name__ == "__main__":
    main()
