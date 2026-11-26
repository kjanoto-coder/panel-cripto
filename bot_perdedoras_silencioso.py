import html
import io
import json
import os
import re
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

BASE_URL_NETLIFY = os.getenv(
    "BASE_URL_NETLIFY",
    "https://gregarious-frangollo-0346c5.netlify.app",
).strip()

CAPITAL_REFERENCIA_USD = float(os.getenv("CAPITAL_REFERENCIA_USD", "2000.0"))
COOLDOWN_MINUTES = int(os.getenv("COOLDOWN_MINUTES", "15"))
LIVE_STEP_DROP_PCT = float(os.getenv("LIVE_STEP_DROP_PCT", "1.0"))
LIVE_TICK_DROP_PCT = float(os.getenv("LIVE_TICK_DROP_PCT", "0.7"))
STATE_FILE = Path(os.getenv("STATE_FILE", "spot_audit_state.json"))
ALERT_ON_RECHAZO = os.getenv("ALERT_ON_RECHAZO", "false").lower() == "true"

# Parámetros del Bloque 1: Caída en tiempo real Binance
TOP_MKT_LOSERS = int(os.getenv("TOP_MKT_LOSERS", "10"))
MIN_VOL_MKT_LOSERS = float(os.getenv("MIN_VOL_MKT_LOSERS", "1000000"))

EXCL_BASE = {
    "USDT", "USDC", "FDUSD", "DAI", "TUSD", "USDP", "EUR", "GBP", "AUD",
    "BRL", "ARS", "TRY", "BUSD", "USD1", "AEUR", "EURI", "USDE", "RLUSD",
    "RWUSD", "XUSD", "BFUSD", "U", "USDG", "USDS", "PYUSD",
}

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
# 2. BASE DE CONOCIMIENTO (FAVORITAS AUDITADAS EN SPOT)
# =====================================================================
ASSETS_DB: Dict[str, dict] = {
    # GRUPO 1: TOP 5 FAVORITOS ESTRUCTURALES (20% - 35%)
    "JSTUSDT": {
        "group": "ESTRUCTURAL",
        "allocation": "30% - 35%",
        "profile": "Tendencia alcista sólida",
        "dip_targets": [0.1430, 0.1425],
        "min_drop_pct": 3.0,
        "tech": "Estructura 1d constructiva y soporte defensivo en 0,1425–0,1430.",
        "risk": "Toma de ganancias tras tramos extendidos o pérdida de 0,1425.",
    },
    "MAGICUSDT": {
        "group": "ESTRUCTURAL",
        "allocation": "25% - 30%",
        "profile": "Rebote con flujo spot positivo",
        "dip_targets": [0.0659, 0.0640],
        "min_drop_pct": 3.5,
        "tech": "Reacción técnica apoyada cerca de MA(99) (0,0659) y sin desbloqueos inminentes.",
        "risk": "Que el rebote pierda volumen y vuelva a testear la zona de MA(99).",
    },
    "BNBUSDT": {
        "group": "ESTRUCTURAL",
        "allocation": "20% - 25%",
        "profile": "Alta liquidez y soporte defendido",
        "dip_targets": [510.0, 503.75],
        "min_drop_pct": 3.0,
        "tech": "Alta liquidez y rebote desde sobreventa sobre soporte estructural.",
        "risk": "Resistencia superior y salidas puntuales de grandes tenedores.",
    },
    "PLUMEUSDT": {
        "group": "ESTRUCTURAL",
        "allocation": "20% - 25%",
        "profile": "Rebote fuerte con desbloqueo próximo",
        "dip_targets": [0.0104, 0.0102],
        "min_drop_pct": 4.0,
        "tech": "Rebote sólido desde soporte con entradas spot.",
        "risk": "Presión por agenda de desbloqueos.",
    },
    "RSRUSDT": {
        "group": "ESTRUCTURAL",
        "allocation": "20% - 25%",
        "profile": "Rebote limpio sujeto a agenda",
        "dip_targets": [0.00122, 0.00118],
        "min_drop_pct": 4.0,
        "tech": "Estructura limpia en 15m tras reacción de corto plazo.",
        "risk": "Eventos o desbloqueos programados.",
    },

    # GRUPO 2: TÁCTICAS DESTACADAS / PUENTE (15% - 20%)
    "ZECUSDT": {
        "group": "TACTICA_PUENTE",
        "allocation": "15% - 20%",
        "profile": "Alta liquidez en rebote desde sobreventa",
        "dip_targets": [778.0, 764.0],
        "min_drop_pct": 4.0,
        "tech": "Liquidez alta y reacción desde zona de sobreventa.",
        "risk": "Vigilar retrocesos por RSI alto en temporalidades cortas.",
    },
    "ZAMAUSDT": {
        "group": "TACTICA_PUENTE",
        "allocation": "15% - 20%",
        "profile": "Fortaleza relativa y narrativa FHE (solo retroceso)",
        "dip_targets": [0.0585, 0.0576],
        "min_drop_pct": 4.0,
        "tech": "Buena fortaleza relativa; vigilar retroceso a soportes.",
        "risk": "Oferta bloqueada y alta concentración en pools.",
    },
    "MMTUSDT": {
        "group": "TACTICA_PUENTE",
        "allocation": "15% - 20%",
        "profile": "Alta volatilidad / retroceso en observación",
        "dip_targets": [],
        "min_drop_pct": 5.0,
        "tech": "Movimiento amplio; buscar piso claro antes de entrar.",
        "risk": "Alta volatilidad y oferta bloqueada.",
    },
    "ASTERUSDT": {
        "group": "TACTICA_PUENTE",
        "allocation": "15% - 20%",
        "profile": "Rebote con recompras y fricción",
        "dip_targets": [],
        "min_drop_pct": 4.5,
        "tech": "Reacción apoyada en recompras con presión vendedora intermitente.",
        "risk": "Salidas spot y riesgos operativos.",
    },
    "ONDOUSDT": {
        "group": "TACTICA_PUENTE",
        "allocation": "15% - 20%",
        "profile": "Alta liquidez con flujo vendedor",
        "dip_targets": [],
        "min_drop_pct": 4.0,
        "tech": "Gran liquidez spot; esperar freno de ventas en soporte.",
        "risk": "Salidas de corto plazo y oferta bloqueada.",
    },
    "ADAUSDT": {
        "group": "TACTICA_PUENTE",
        "allocation": "15% - 20%",
        "profile": "Rebote desde sobreventa extrema",
        "dip_targets": [0.1410, 0.1400],
        "min_drop_pct": 4.0,
        "tech": "Fuerte liquidez y reacción desde zonas de sobreventa.",
        "risk": "Pérdida de soporte clave con salidas netas.",
    },
    "HBARUSDT": {
        "group": "TACTICA_PUENTE",
        "allocation": "15% - 20%",
        "profile": "Rebote técnico en tendencia débil",
        "dip_targets": [0.0505, 0.0495],
        "min_drop_pct": 4.5,
        "tech": "Rebote técnico sobre piso de corto plazo.",
        "risk": "Estructura de fondo frágil si pierde soporte.",
    },
    "PENGUUSDT": {
        "group": "TACTICA_PUENTE",
        "allocation": "15% - 20%",
        "profile": "Rebote técnico en zona baja",
        "dip_targets": [0.00415, 0.004141],
        "min_drop_pct": 4.5,
        "tech": "Reacción desde sobreventa en zona baja.",
        "risk": "Rotación de liquidez fuera de memes.",
    },
    "GRTUSDT": {
        "group": "TACTICA_PUENTE",
        "allocation": "15% - 20%",
        "profile": "Acumulación leve sin desbloqueos",
        "dip_targets": [],
        "min_drop_pct": 4.5,
        "tech": "Acumulación moderada cerca de mínimos locales.",
        "risk": "Precio todavía bajo medias superiores.",
    },
    "RESOLVUSDT": {
        "group": "TACTICA_PUENTE",
        "allocation": "15% - 20%",
        "profile": "Reacción en mínimos con evento cerca",
        "dip_targets": [],
        "min_drop_pct": 5.0,
        "tech": "Rebote de corto plazo en zona baja.",
        "risk": "Liquidez acotada y agenda de desbloqueos.",
    },

    # GRUPO 3: TÁCTICAS / CAZA DE REBOTE (5% - 15%)
    "HOTUSDT": {
        "group": "CAZA_REBOTE",
        "allocation": "10% - 15%",
        "profile": "Rebote con flujo spot",
        "dip_targets": [0.000339, 0.000331],
        "min_drop_pct": 5.0,
        "tech": "Reacción sobre medias intradía con entradas spot.",
        "risk": "Concentración moderada.",
    },
    "JUPUSDT": {
        "group": "CAZA_REBOTE",
        "allocation": "10% - 15%",
        "profile": "Ingresos activos con desbloqueo cercano",
        "dip_targets": [0.2065, 0.2000],
        "min_drop_pct": 5.0,
        "tech": "Rebote desde zona de soporte con ingresos activos.",
        "risk": "Oferta bloqueada y desbloqueos programados.",
    },
    "ALGOUSDT": {
        "group": "CAZA_REBOTE",
        "allocation": "10% - 15%",
        "profile": "Rebote corto en estructura bajista",
        "dip_targets": [0.0715, 0.0712],
        "min_drop_pct": 5.0,
        "tech": "Reacción técnica de corto plazo en piso.",
        "risk": "Tendencia diaria aún débil.",
    },
    "LUMIAUSDT": {
        "group": "CAZA_REBOTE",
        "allocation": "10% - 15%",
        "profile": "Rebote técnico con liquidez moderada",
        "dip_targets": [],
        "min_drop_pct": 5.5,
        "tech": "Rebote técnico tras movimientos previos.",
        "risk": "Profundidad de mercado acotada.",
    },
    "HYPEUSDT": {
        "group": "CAZA_REBOTE",
        "allocation": "5% - 10%",
        "profile": "Alta liquidez con corrección activa",
        "dip_targets": [56.0, 55.80],
        "min_drop_pct": 5.0,
        "tech": "Rebote técnico desde zona de sobreventa con alta liquidez.",
        "risk": "Salidas de capital y ruido regulatorio.",
    },
    "RIFUSDT": {
        "group": "CAZA_REBOTE",
        "allocation": "5% - 10%",
        "profile": "Rebote técnico de corto plazo",
        "dip_targets": [0.0450, 0.0449],
        "min_drop_pct": 5.5,
        "tech": "Rebote desde RSI bajo en zona de soporte.",
        "risk": "Volumen horario moderado.",
    },
    "PUMPUSDT": {
        "group": "CAZA_REBOTE",
        "allocation": "5% - 10%",
        "profile": "Rebote corto de alta volatilidad",
        "dip_targets": [],
        "min_drop_pct": 6.0,
        "tech": "Rebote rápido desde sobreventa.",
        "risk": "Alta volatilidad y salidas vendedoras.",
    },
    "LUNCUSDT": {
        "group": "CAZA_REBOTE",
        "allocation": "5% - 10%",
        "profile": "Operativa táctica puntual",
        "dip_targets": [],
        "min_drop_pct": 6.0,
        "tech": "Reacción táctica de corto plazo.",
        "risk": "Alta volatilidad especulativa.",
    },
    "EDENUSDT": {
        "group": "CAZA_REBOTE",
        "allocation": "5% - 10%",
        "profile": "Rebote frágil en observación",
        "dip_targets": [],
        "min_drop_pct": 5.5,
        "tech": "Reacción corta desde sobreventa.",
        "risk": "Presión vendedora y oferta bloqueada.",
    },

    # GRUPO 4: DESCARTADAS / ALTO RIESGO
    "MANTRAUSDT": {"group": "DESCARTADA", "allocation": "0% - 5%", "profile": "No apta / Mínimos y dilución", "tech": "Estructura bajista extendida.", "risk": "Mínimos bajos, salidas y dilución."},
    "TNSRUSDT":   {"group": "DESCARTADA", "allocation": "0% - 5%", "profile": "No apta / Mínimos", "tech": "Sin demanda sostenida.", "risk": "Caída pronunciada y baja concentración."},
    "MITOUSDT":   {"group": "DESCARTADA", "allocation": "0% - 5%", "profile": "No apta / En observación", "tech": "Presión vendedora bajo medias.", "risk": "Etiqueta de observación y desbloqueos."},
    "OPENUSDT":   {"group": "DESCARTADA", "allocation": "0% - 5%", "profile": "No apta / Mínimos y bloqueo", "tech": "Debilidad en zona baja.", "risk": "Alta oferta bloqueada."},
    "ALLOUSDT":   {"group": "DESCARTADA", "allocation": "0% - 5%", "profile": "No apta / Salidas y baja liquidez", "tech": "Rebotes débiles.", "risk": "Salidas y baja liquidez."},
    "BICOUSDT":   {"group": "DESCARTADA", "allocation": "0% - 5%", "profile": "No apta / Ruptura de mínimos", "tech": "Sin recuperación confirmada.", "risk": "Pérdida de piso."},
    "KAITOUSDT":  {"group": "DESCARTADA", "allocation": "0% - 5%", "profile": "No apta / Mínimos y bloqueo", "tech": "Momentum negativo.", "risk": "Oferta bloqueada y salidas."},
    "BONKUSDT":   {"group": "DESCARTADA", "allocation": "0% - 5%", "profile": "No apta / Mínimos", "tech": "Presión vendedora persistente.", "risk": "Salidas netas."},
    "TUTUSDT":    {"group": "DESCARTADA", "allocation": "0% - 5%", "profile": "No apta / Debilidad técnica", "tech": "Bajo medias móviles.", "risk": "Salidas de flujo."},
    "ACEUSDT":    {"group": "DESCARTADA", "allocation": "0% - 5%", "profile": "No apta / Salidas y dilución", "tech": "Distribución continua.", "risk": "Salidas y dilución."},
    "GIGGLEUSDT": {"group": "DESCARTADA", "allocation": "0% - 5%", "profile": "No apta / Salidas pico", "tech": "Rechazo bajo MA(99).", "risk": "Salidas de capital."},
    "OGUSDT":     {"group": "DESCARTADA", "allocation": "0% - 5%", "profile": "No apta / Desbloqueo", "tech": "Presión cerca de mínimos.", "risk": "Desbloqueo y baja capitalización."},
    "MOVRUSDT":   {"group": "DESCARTADA", "allocation": "0% - 5%", "profile": "No apta / Liquidez deprimida", "tech": "Goteo bajista.", "risk": "Baja liquidez."},
    "APEUSDT":    {"group": "DESCARTADA", "allocation": "0% - 5%", "profile": "No apta / Nuevos mínimos", "tech": "Ruptura de soportes.", "risk": "Bajo volumen."},
    "HEIUSDT":    {"group": "DESCARTADA", "allocation": "0% - 5%", "profile": "No apta / En supervisión", "tech": "Poca profundidad.", "risk": "Etiqueta de supervisión."},
    "NEIROUSDT":  {"group": "DESCARTADA", "allocation": "0% - 5%", "profile": "No apta / Rebote débil", "tech": "Sin fuerza sobre medias.", "risk": "Salidas y momentum débil."},
    "COTIUSDT":   {"group": "DESCARTADA", "allocation": "0% - 5%", "profile": "No apta / Golpe fundamental", "tech": "Deterioro por noticias.", "risk": "Salidas de flujo."},
    "SAGAUSDT":   {"group": "DESCARTADA", "allocation": "0% - 5%", "profile": "No apta / Cerca de mínimos", "tech": "Pérdida de nivel clave.", "risk": "Presión vendedora."},
    "OPNUSDT":    {"group": "DESCARTADA", "allocation": "0% - 5%", "profile": "No apta / Oferta bloqueada", "tech": "Cerca de mínimos.", "risk": "Alta oferta bloqueada."},
    "SLPUSDT":    {"group": "DESCARTADA", "allocation": "0% - 5%", "profile": "No apta / Inflación", "tech": "Tendencia bajista de fondo.", "risk": "Emisión inflacionaria."},
    "GNSUSDT":    {"group": "DESCARTADA", "allocation": "0% - 5%", "profile": "No apta / Riesgo de listado", "tech": "Baja liquidez.", "risk": "Riesgo de monitoreo/listado."},
    "HUMAUSDT":   {"group": "DESCARTADA", "allocation": "0% - 5%", "profile": "No apta / Desbloqueo", "tech": "Salidas previas a unlock.", "risk": "Desbloqueo relevante."},
    "BEAMXUSDT":  {"group": "DESCARTADA", "allocation": "0% - 5%", "profile": "No apta / Salidas persistentes", "tech": "Flujo neto vendedor.", "risk": "Presión vendedora."},
    "TLMUSDT":    {"group": "DESCARTADA", "allocation": "0% - 5%", "profile": "No apta / Cerca de mínimos", "tech": "Deslizamiento bajista.", "risk": "Soporte débil."},
    "WLFIUSDT":   {"group": "DESCARTADA", "allocation": "0% - 5%", "profile": "No apta / Salidas fuertes", "tech": "Distribución en zona baja.", "risk": "Salidas y desbloqueos."},
    "LSKUSDT":    {"group": "DESCARTADA", "allocation": "0% - 5%", "profile": "No apta / Dilución", "tech": "Goteo de oferta.", "risk": "Fricción y desbloqueos."},
    "HOMEUSDT":   {"group": "DESCARTADA", "allocation": "0% - 5%", "profile": "No apta / Desbloqueo y mínimos", "tech": "Liquidez baja.", "risk": "Desbloqueo cercano."},
    "HEMIUSDT":   {"group": "DESCARTADA", "allocation": "0% - 5%", "profile": "No apta / Desbloqueo", "tech": "Estructura débil.", "risk": "Oferta bloqueada y unlock."},
    "ALTUSDT":    {"group": "DESCARTADA", "allocation": "0% - 5%", "profile": "No apta / Unlock", "tech": "Ventas anticipadas.", "risk": "Desbloqueo cercano."},
    "GALAUSDT":   {"group": "DESCARTADA", "allocation": "0% - 5%", "profile": "No apta / Salidas continuas", "tech": "Goteo en mínimos.", "risk": "Salidas netas."},
    "TUSDT":      {"group": "DESCARTADA", "allocation": "0% - 5%", "profile": "No apta / Tendencia 1d bajista", "tech": "Baja liquidez.", "risk": "Pendiente diaria negativa."},
    "QIUSDT":     {"group": "DESCARTADA", "allocation": "0% - 5%", "profile": "No apta / Riesgo de plataforma", "tech": "Poca profundidad.", "risk": "Etiqueta de monitoreo."},
    "XAIUSDT":    {"group": "DESCARTADA", "allocation": "0% - 5%", "profile": "No apta / Emisión lineal", "tech": "Dilución diaria.", "risk": "Mínimos y bajo volumen."},
    "JASMYUSDT":  {"group": "DESCARTADA", "allocation": "0% - 5%", "profile": "No apta / Presión por listado", "tech": "Ventas en zona baja.", "risk": "Fricción de listado."},
    "TOWNSUSDT":  {"group": "DESCARTADA", "allocation": "0% - 5%", "profile": "No apta / Mínimos y bloqueo", "tech": "Debilidad técnica.", "risk": "Alta oferta bloqueada."},
    "DGBUSDT":    {"group": "DESCARTADA", "allocation": "0% - 5%", "profile": "No apta / Iliquidez", "tech": "Sin reacción en 15m.", "risk": "Liquidez muy baja."},
}


# =====================================================================
# 3. CONSULTAS DE MERCADO, FIBONACCI E INDICADORES
# =====================================================================
def es_par_spot_limpio(symbol: str) -> bool:
    if not symbol.endswith("USDT"):
        return False
    base = symbol[:-4]
    if not base or base in EXCL_BASE:
        return False
    if not re.match(r"^[A-Z0-9]+$", base):
        return False
    if base.endswith("B"):
        return False
    if any(tag in base for tag in ("UP", "DOWN", "BULL", "BEAR")):
        return False
    return True


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
                        "openPrice": str(price),
                        "priceChangePercent": str(pct if pct is not None else 0.0),
                        "quoteVolume": str(vol if vol is not None else 0.0),
                    }
        if page == 1:
            time.sleep(1.0)

    if normalized:
        print(f"[OK] Respaldo CoinGecko cargado ({len(normalized)} pares).")
        return normalized, "COINGECKO"

    return {}, "NONE"


def seleccionar_perdedoras_binance_en_vivo(tickers: Dict[str, dict]) -> Dict[str, dict]:
    """Bloque 1: Selecciona las mayores caídas en vivo de Binance Spot (excluyendo favoritas ya cargadas)."""
    candidatos = []
    for sym, t in tickers.items():
        if sym in ASSETS_DB or not es_par_spot_limpio(sym):
            continue
        try:
            precio = float(t.get("lastPrice", 0))
            pct_24h = float(t.get("priceChangePercent", 0))
            vol_24h = float(t.get("quoteVolume", 0))
            if precio > 0 and pct_24h <= -3.0 and vol_24h >= MIN_VOL_MKT_LOSERS:
                candidatos.append((sym, pct_24h, vol_24h))
        except Exception:
            continue

    candidatos.sort(key=lambda x: x[1])
    bloque_binance: Dict[str, dict] = {}
    for sym, pct_24h, vol_24h in candidatos[:TOP_MKT_LOSERS]:
        bloque_binance[sym] = {
            "group": "RADAR_BINANCE",
            "allocation": "10% - 15%",
            "profile": f"Caída Binance Spot ({pct_24h:+.1f}% | Vol ${vol_24h/1e6:.1f}M)",
            "dip_targets": [],
            "min_drop_pct": 3.0,
            "tech": "Caída activa en radar Binance Spot; evaluando piso Fibonacci y rebote técnico.",
            "risk": "Validar soporte Fibonacci 0.618/0.786 y volumen antes de entrar.",
        }
    return bloque_binance


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


def calc_fibonacci_rebote(k4h: List[dict], price: float) -> dict:
    """Calcula niveles de Fibonacci sobre el swing de 4H para detectar pisos y objetivos de rebote."""
    if len(k4h) < 15:
        return {"ok": False}
    highs = [x["high"] for x in k4h]
    lows = [x["low"] for x in k4h]
    swing_high = max(highs)
    swing_low = min(lows)
    rango = swing_high - swing_low
    if rango <= 0 or price <= 0:
        return {"ok": False}

    ratio = (swing_high - price) / rango
    fib_382 = swing_high - (rango * 0.382)
    fib_500 = swing_high - (rango * 0.500)
    fib_618 = swing_high - (rango * 0.618)
    fib_786 = swing_high - (rango * 0.786)

    en_piso_dorado = (0.58 <= ratio <= 0.66)
    en_soporte_profundo = (0.74 <= ratio <= 0.83)
    perforo_swing = (ratio > 0.96)

    if en_piso_dorado:
        estado_fib = f"🟢 Piso Dorado Fib 0.618 ({ratio:.2f})"
    elif en_soporte_profundo:
        estado_fib = f"🟢 Soporte Profundo Fib 0.786 ({ratio:.2f})"
    elif perforo_swing:
        estado_fib = f"🔴 Perforando Mínimo Fib ({ratio:.2f})"
    else:
        estado_fib = f"🟡 Retroceso Intermedio Fib ({ratio:.2f})"

    return {
        "ok": True,
        "ratio": round(ratio, 3),
        "estado_fib": estado_fib,
        "en_piso_dorado": en_piso_dorado,
        "en_soporte_profundo": en_soporte_profundo,
        "perforo_swing": perforo_swing,
        "fib_382": fib_382,
        "fib_500": fib_500,
        "fib_618": fib_618,
        "fib_786": fib_786,
    }


def estimar_ganancia_rebote_usd(
    price: float,
    open_price: float,
    recent_high: float,
    fib_info: dict,
    prob: int,
    capital_usd: float = CAPITAL_REFERENCIA_USD,
) -> Tuple[float, float, str]:
    """Estima % de rebote objetivo y ganancia en USD sobre $2,000 en Spot."""
    if price <= 0:
        return 0.0, 0.0, "N/A"

    objetivo_precio = None
    etiqueta_obj = "Rebote Técnico"

    if fib_info.get("ok") and fib_info.get("fib_382", 0) > price * 1.015:
        objetivo_precio = float(fib_info["fib_382"])
        etiqueta_obj = "Fib 0.382"
    elif open_price > price * 1.015:
        objetivo_precio = float(open_price)
        etiqueta_obj = "Base 0%"
    elif recent_high > price * 1.015:
        # Rebote conservador del 45% del retroceso desde el máximo de 12h
        objetivo_precio = price + ((recent_high - price) * 0.45)
        etiqueta_obj = "45% Pico 12h"

    if objetivo_precio and objetivo_precio > price:
        rebote_pct = ((objetivo_precio - price) / price) * 100.0
        # Acotamos el objetivo de rebote táctico a un rango realista de 2.5% a 25%
        rebote_pct = max(2.5, min(25.0, rebote_pct))
    else:
        rebote_pct = round(4.0 + (prob / 20.0), 2)

    ganancia_usd = capital_usd * (rebote_pct / 100.0)
    return round(rebote_pct, 2), round(ganancia_usd, 2), etiqueta_obj


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
# 4. CÁLCULO DE SENTIMIENTO DE COMPRA Y PROBABILIDAD DE REBOTE (+ FIB)
# =====================================================================
def compute_rebound_scoring(
    group: str,
    price: float,
    vol_24h: float,
    rsi6_15: Optional[float],
    ema99_1d: Optional[float],
    hit_target: bool,
    fib_info: dict,
    drop_live_pct: float,
) -> Tuple[str, str, int, int, str]:
    base_map = {
        "ESTRUCTURAL": 64,
        "TACTICA_PUENTE": 50,
        "RADAR_BINANCE": 48,
        "CAZA_REBOTE": 40,
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

    if drop_live_pct >= 1.5 and group != "DESCARTADA":
        score += 4

    if fib_info.get("ok"):
        if fib_info.get("en_piso_dorado"):
            score += 12
        elif fib_info.get("en_soporte_profundo"):
            score += 10
        elif fib_info.get("perforo_swing"):
            score -= 8

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
        prob = max(20, min(95, score))

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
# 5. EVALUACIÓN DE MONEDA EN VIVO + REFERENCIA $2,000 USD
# =====================================================================
def evaluate_symbol(
    symbol: str,
    cfg: dict,
    ticker: dict,
    source: str,
    prev_entry: dict,
    bloque_nombre: str,
) -> Optional[dict]:
    group = cfg["group"]
    base_coin = symbol.replace("USDT", "")
    price = float(ticker["lastPrice"])
    open_price = float(ticker.get("openPrice") or price)
    pct_24h = float(ticker["priceChangePercent"])
    vol_24h = float(ticker["quoteVolume"])

    prev_price = float(prev_entry.get("last_price") or 0.0)
    last_alert_price = float(prev_entry.get("last_alert_price") or 0.0)

    drop_live_pct = ((prev_price - price) / prev_price * 100.0) if prev_price > 0 and price < prev_price else 0.0
    drop_since_alert_pct = (
        ((last_alert_price - price) / last_alert_price * 100.0)
        if last_alert_price > 0 and price < last_alert_price
        else 0.0
    )

    k15 = get_klines(symbol, "15m", limit=120) if source == "BINANCE" else []
    k4h = get_klines(symbol, "4h", limit=48) if source == "BINANCE" else []
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
    fib_info = calc_fibonacci_rebote(k4h, price) if len(k4h) >= 15 else {"ok": False}

    recent_high = max(h15_12h) if h15_12h else price
    drop_from_12h_high = ((recent_high - price) / recent_high * 100.0) if (has_klines and recent_high > 0) else 0.0

    last_15m_chg = 0.0
    if len(k15) >= 2 and k15[-1]["open"] > 0:
        last_15m_chg = ((price - k15[-1]["open"]) / k15[-1]["open"]) * 100.0

    targets: List[float] = list(cfg.get("dip_targets", []))
    if not targets and fib_info.get("ok"):
        targets = [round(fib_info["fib_618"], 8), round(fib_info["fib_786"], 8)]
    elif not targets and ema99_15 is not None:
        targets = [round(ema99_15, 8)]

    min_drop = float(cfg.get("min_drop_pct", 3.5))
    matched_target = min([t for t in targets if price <= t * 1.008], default=None)

    hit_target = matched_target is not None or fib_info.get("en_piso_dorado", False) or fib_info.get("en_soporte_profundo", False)
    hit_drop_12h = has_klines and drop_from_12h_high >= min_drop
    hit_drop_24h = pct_24h <= -min_drop
    hit_live_drop = (drop_live_pct >= LIVE_TICK_DROP_PCT) or (last_15m_chg <= -1.0 and pct_24h <= -0.8)

    if group == "DESCARTADA":
        if not ALERT_ON_RECHAZO:
            return None
        if not ((has_klines and drop_from_12h_high >= 5.5) or pct_24h <= -5.5 or drop_live_pct >= 1.5):
            return None
    else:
        if not (hit_target or hit_drop_12h or hit_drop_24h or hit_live_drop):
            return None

    verdict, light, color_order, prob, bar = compute_rebound_scoring(
        group=group,
        price=price,
        vol_24h=vol_24h,
        rsi6_15=rsi6_15,
        ema99_1d=ema99_1d,
        hit_target=hit_target,
        fib_info=fib_info,
        drop_live_pct=drop_live_pct,
    )

    rebote_pct, ganancia_2k_usd, obj_label = estimar_ganancia_rebote_usd(
        price=price,
        open_price=open_price,
        recent_high=recent_high,
        fib_info=fib_info,
        prob=prob,
        capital_usd=CAPITAL_REFERENCIA_USD,
    )

    if group == "DESCARTADA":
        caza_tag = "⚠️ SANGRÍA / EVITAR"
        kind = "RECHAZO"
    elif hit_target and prob >= 60:
        caza_tag = "🎯 CAZA EN SOPORTE"
        kind = "CAZA_SOPORTE"
    elif hit_live_drop:
        caza_tag = "🔥 CAÍDA EN VIVO"
        kind = "CAIDA_VIVO"
    else:
        caza_tag = "📉 OPORTUNIDAD EN CAÍDA"
        kind = "DIP_DROP"

    badge = {
        "ESTRUCTURAL": "⭐ FAVORITO ESTRUCTURAL",
        "TACTICA_PUENTE": "🎯 TÁCTICA PUENTE",
        "RADAR_BINANCE": "🌐 CAÍDA TIEMPO REAL BINANCE",
        "CAZA_REBOTE": "⚡ CAZA DE REBOTE",
        "DESCARTADA": "🚫 DESCARTADA / EVITAR",
    }.get(group, group)

    targets_txt = " / ".join(fmt(t) for t in targets) if targets else "Dinámico"
    ts_ms = int(time.time() * 1000)
    url_ia = (
        f"{BASE_URL_NETLIFY}/?coin={base_coin}&price={price}&change={pct_24h}"
        f"&high={recent_high}&low={min(l15_12h) if l15_12h else price}&v={base_coin}_{ts_ms}"
    )
    url_trade = f"https://www.binance.com/es/trade/{base_coin}_USDT?type=spot"

    live_line = (
        f"• Pulso en vivo: <code>15m={last_15m_chg:+.2f}%</code> | "
        f"Vs lectura ant: <code>-{drop_live_pct:.2f}%</code> | "
        f"Vs último aviso: <code>-{drop_since_alert_pct:.2f}%</code>\n"
    )

    fib_line = ""
    if fib_info.get("ok"):
        fib_line = (
            f"• Geometría Fib (4H): <b>{fib_info['estado_fib']}</b> | "
            f"Sop 0.618: <code>{fmt(fib_info['fib_618'])}</code> | Obj Rebote 0.382: <code>{fmt(fib_info['fib_382'])}</code>\n"
        )

    rsi_txt = f"{rsi6_15:.1f}" if rsi6_15 is not None else "N/A"
    ema25_txt = fmt(ema25_15) if ema25_15 is not None else "N/A"
    ema99_15_txt = fmt(ema99_15) if ema99_15 is not None else "N/A"
    ema99_1d_txt = fmt(ema99_1d) if ema99_1d is not None else "N/A"

    tech_block = (
        f"{live_line}"
        f"• Base (0%): <code>${fmt(open_price)}</code> → Actual: <code>${fmt(price)}</code> | 24h: <b>{pct_24h:+.2f}%</b>\n"
        f"• Zonas límite: <code>{targets_txt}</code> | Mín 12h: <code>${fmt(min(l15_12h) if l15_12h else price)}</code> | Retroceso 12h: <code>-{drop_from_12h_high:.2f}%</code>\n"
        f"{fib_line}"
        f"• 15m: <code>RSI(6)={rsi_txt}</code> | <code>EMA25={ema25_txt}</code> | <code>EMA99={ema99_15_txt}</code>\n"
        f"• 1D EMA99: <code>{ema99_1d_txt}</code> | Vol 24h: <code>${vol_24h:,.0f}</code>\n"
    )

    card_msg = (
        f"{caza_tag} • <b>{html.escape(base_coin)}</b> | Actual: <code>${fmt(price)}</code> | <b>{pct_24h:+.2f}%</b>\n"
        f"{bar}  (Rebote: <b>{prob}%</b>)\n"
        f"💰 <b>Ref. ${CAPITAL_REFERENCIA_USD:,.0f} USD:</b> rebote est. <code>+{rebote_pct:.2f}%</code> ({html.escape(obj_label)}) → <b>+${ganancia_2k_usd:,.2f} USD</b>\n"
        f"└ <a href=\"{html.escape(url_ia)}\">📊 Resumen IA</a> | <a href=\"{html.escape(url_trade)}\">🔶 Tradear</a>\n\n"
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
        "bloque": bloque_nombre,
        "symbol": symbol,
        "coin": base_coin,
        "kind": kind,
        "caza_tag": caza_tag,
        "verdict": verdict,
        "light": light,
        "color_order": color_order,
        "prob": prob,
        "pct_24h": pct_24h,
        "price": price,
        "drop_live_pct": drop_live_pct,
        "drop_since_alert_pct": drop_since_alert_pct,
        "rebote_pct": rebote_pct,
        "ganancia_2k_usd": ganancia_2k_usd,
        "obj_label": obj_label,
        "card_msg": card_msg,
    }


# =====================================================================
# 6. RANKINGS POR BLOQUE + GRÁFICO COMPARATIVO + ENVÍO TELEGRAM
# =====================================================================
def rankear_potencial_rebote(items: List[dict]) -> List[dict]:
    """Ordena de mayor a menor potencial de rebote (probabilidad + ganancia estimada)."""
    return sorted(
        items,
        key=lambda x: (x["prob"], x["ganancia_2k_usd"], -abs(x["pct_24h"])),
        reverse=True,
    )


def build_two_blocks_ranking_text(
    bloque_binance_items: List[dict],
    bloque_favoritas_items: List[dict],
) -> str:
    rank_bin = rankear_potencial_rebote(bloque_binance_items)
    rank_fav = rankear_potencial_rebote(bloque_favoritas_items)

    lines = [
        f"⚡ <b>CAZA EN VIVO EN CAÍDAS • RANKING DE REBOTE (REF. ${CAPITAL_REFERENCIA_USD:,.0f} USD)</b>",
        "",
        "🌐 <b>BLOQUE 1 • CAÍDA TIEMPO REAL BINANCE (Ranking Rebote):</b>",
    ]
    if rank_bin:
        for idx, it in enumerate(rank_bin[:7], start=1):
            lines.append(
                f"{idx}. {it['light']} <b>{html.escape(it['coin'])}</b> — Rebote <code>{it['prob']}%</code> "
                f"(<code>{it['pct_24h']:+.1f}%</code> | Obj <code>+{it['rebote_pct']:.1f}%</code> → <b>+${it['ganancia_2k_usd']:,.0f}</b>)"
            )
    else:
        lines.append("<i>Sin caídas en vivo con señal activa en el radar general de Binance.</i>")

    lines.append("")
    lines.append("⭐ <b>BLOQUE 2 • CAÍDA DE MIS FAVORITAS (Ranking Rebote):</b>")
    if rank_fav:
        for idx, it in enumerate(rank_fav[:7], start=1):
            lines.append(
                f"{idx}. {it['light']} <b>{html.escape(it['coin'])}</b> — Rebote <code>{it['prob']}%</code> "
                f"(<code>{it['pct_24h']:+.1f}%</code> | Obj <code>+{it['rebote_pct']:.1f}%</code> → <b>+${it['ganancia_2k_usd']:,.0f}</b>)"
            )
    else:
        lines.append("<i>Sin favoritas en caída activa o zona de rebote en esta pasada.</i>")

    return "\n".join(lines)


def build_summary_chart_png(sorted_items: List[dict]) -> Optional[bytes]:
    if not HAS_MATPLOTLIB or not sorted_items:
        return None

    top_items = sorted_items[:12]
    n = len(top_items)
    fig_w = max(8.0, min(15.0, n * 0.95 + 2.0))
    fig, ax = plt.subplots(figsize=(fig_w, 4.6), dpi=160)

    bg_color = "#0b0f1c"
    grid_color = "#1b2438"
    fig.patch.set_facecolor(bg_color)
    ax.set_facecolor(bg_color)

    ax.grid(True, axis="y", color=grid_color, linestyle="-", linewidth=0.7, zorder=0)

    fill_map = {0: "#ff1744", 1: "#ffd600", 2: "#00e676"}
    edge_map = {0: "#ffd600", 1: "#ffd600", 2: "#00e676"}
    txt_map = {0: "#ff1744", 1: "#ffd600", 2: "#00e676"}

    x_pos = list(range(n))
    probs = [it["prob"] for it in top_items]
    labels = [f"{it['coin']}\n(+${it['ganancia_2k_usd']:.0f})" for it in top_items]
    fills = [fill_map[it["color_order"]] for it in top_items]
    edges = [edge_map[it["color_order"]] for it in top_items]

    bars = ax.bar(x_pos, probs, width=0.52, color=fills, edgecolor=edges, linewidth=1.6, zorder=3)

    for bar, it in zip(bars, top_items):
        p = it["prob"]
        c_txt = txt_map[it["color_order"]]
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

    ax.set_title(
        f"RANKING POTENCIAL DE REBOTE • GANANCIA EST. SOBRE ${CAPITAL_REFERENCIA_USD:,.0f} USD",
        color="#ffffff",
        fontsize=11.5,
        fontweight="bold",
        pad=14,
    )
    ax.set_ylim(0, 108)
    ax.set_xticks(x_pos)
    ax.set_xticklabels(labels, rotation=32, ha="right", color="#cbd5e1", fontsize=8.5, fontweight="bold")
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
    target = _get_telegram_target()
    if not target:
        return False
    thread_id, candidates = target
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"

    last_err = ""
    for cid in candidates:
        try:
            files = {"photo": ("ranking_rebote_2000usd.png", png_bytes, "image/png")}
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


def debe_disparar_en_vivo(prev_entry: dict, item: dict, now: float, cooldown_sec: float) -> bool:
    last_ts = float(prev_entry.get("last_alert_ts") or 0.0)
    last_verdict = prev_entry.get("last_verdict", "")
    last_kind = prev_entry.get("last_kind", "")

    if last_verdict and last_verdict != item["verdict"]:
        return True
    if last_kind and last_kind != item["kind"] and item["kind"] in ("CAZA_SOPORTE", "CAIDA_VIVO"):
        return True
    if item.get("drop_since_alert_pct", 0.0) >= LIVE_STEP_DROP_PCT:
        return True
    if item.get("drop_live_pct", 0.0) >= (LIVE_STEP_DROP_PCT * 1.25):
        return True
    return (now - last_ts) >= cooldown_sec


def main() -> None:
    now = time.time()
    cooldown_sec = COOLDOWN_MINUTES * 60
    state = load_state()
    coins_state = state.setdefault("coins", {})

    tickers, source = get_24h_tickers()
    if not tickers:
        print("[ERROR] No se pudieron obtener los tickers 24h ni de Binance ni del respaldo.")
        return

    bloque_binance_cfg = seleccionar_perdedoras_binance_en_vivo(tickers)
    bloque_favoritas_cfg = dict(ASSETS_DB)

    triggered_binance: List[dict] = []
    triggered_favoritas: List[dict] = []

    def procesar_bloque(cfg_map: Dict[str, dict], nombre_bloque: str, destino: List[dict]) -> None:
        for symbol, cfg in cfg_map.items():
            ticker = tickers.get(symbol)
            if not ticker:
                continue
            prev_entry = coins_state.get(symbol, {}) if isinstance(coins_state.get(symbol), dict) else {}
            item = evaluate_symbol(symbol, cfg, ticker, source, prev_entry, nombre_bloque)

            try:
                curr_p = float(ticker["lastPrice"])
                prev_entry["last_price"] = curr_p
                prev_entry["last_seen_ts"] = now
                coins_state[symbol] = prev_entry
            except Exception:
                pass

            if item and debe_disparar_en_vivo(prev_entry, item, now, cooldown_sec):
                destino.append(item)

    procesar_bloque(bloque_binance_cfg, "BINANCE_VIVO", triggered_binance)
    procesar_bloque(bloque_favoritas_cfg, "FAVORITAS", triggered_favoritas)

    all_triggered = triggered_binance + triggered_favoritas
    if not all_triggered:
        save_state(state)
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        print(
            f"[{ts}] Caza en vivo completada (Binance={len(bloque_binance_cfg)} | Favoritas={len(bloque_favoritas_cfg)} | Fuente={source}). "
            f"Sin alertas nuevas."
        )
        return

    ranking_combinado = rankear_potencial_rebote(all_triggered)
    summary_text = build_two_blocks_ranking_text(triggered_binance, triggered_favoritas)
    chart_png = build_summary_chart_png(ranking_combinado)

    if chart_png:
        if len(summary_text) <= 1000:
            send_photo_to_perdedoras_topic(chart_png, summary_text)
        else:
            send_photo_to_perdedoras_topic(
                chart_png,
                f"⚡ <b>RANKING DE REBOTE (REF. ${CAPITAL_REFERENCIA_USD:,.0f} USD)</b>",
            )
            send_to_perdedoras_topic(summary_text)
    else:
        send_to_perdedoras_topic(summary_text)

    time.sleep(0.5)

    alerts_sent = 0
    for item in ranking_combinado:
        if send_to_perdedoras_topic(item["card_msg"]):
            sym = item["symbol"]
            entry = coins_state.setdefault(sym, {})
            entry["last_alert_ts"] = now
            entry["last_alert_price"] = item["price"]
            entry["last_verdict"] = item["verdict"]
            entry["last_kind"] = item["kind"]
            alerts_sent += 1
            time.sleep(0.35)

    save_state(state)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    print(
        f"[{ts}] Caza en vivo completada (Bloque 1 Binance={len(triggered_binance)} | Bloque 2 Favoritas={len(triggered_favoritas)}). "
        f"Fichas emitidas: {alerts_sent}"
    )


if __name__ == "__main__":
    main()
