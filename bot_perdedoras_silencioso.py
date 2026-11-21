import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import requests

# ==========================================
# 1. CONFIGURACIÓN TELEGRAM Y CONTROL
# ==========================================
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "TU_BOT_TOKEN_AQUI")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "TU_CHAT_ID_AQUI")

COOLDOWN_MINUTES = int(os.getenv("COOLDOWN_MINUTES", "180"))  # Evita repetir la misma alerta cada corrida
STATE_FILE = Path(os.getenv("STATE_FILE", "alert_state.json"))
ALERT_ON_DISCARDED_NEW_LOW = False  # True solo si querés avisos de nuevos mínimos en descartadas

BINANCE_SPOT_ENDPOINTS = [
    "https://api.binance.com",
    "https://api1.binance.com",
    "https://api2.binance.com",
    "https://api3.binance.com",
]

# ==========================================
# 2. UNIVERSO AUDITADO Y ZONAS DE COMPRA
#    Ajustá los precios de referencia y escalones
#    a los valores exactos que quieras operar.
# ==========================================
ASSETS: Dict[str, dict] = {
    # --- FAVORITOS ESTRUCTURALES (20% - 35%) ---
    "JSTUSDT": {
        "tier": "ESTRUCTURAL",
        "weight": "30-35%",
        "ref_high": 0.1500,
        "buy_zones": [0.1440, 0.1425],  # Soporte defendido 0.1425-0.1430
        "min_drop_pct": 4.0,
        "note": "Estructura 1d alcista; priorizar soporte 0.1425-0.1430",
    },
    "MAGICUSDT": {
        "tier": "ESTRUCTURAL",
        "weight": "25-30%",
        "ref_high": 0.0680,
        "buy_zones": [0.0659, 0.0640],  # Apoyo cerca de MA(99)
        "min_drop_pct": 5.0,
        "note": "Rebote con flujo spot positivo; vigilar zona MA(99) ~0.0659",
    },
    "BNBUSDT": {
        "tier": "ESTRUCTURAL",
        "weight": "20-25%",
        "ref_high": 555.0,
        "buy_zones": [520.0, 505.0],    # Soporte clave 503.75-510
        "min_drop_pct": 4.5,
        "note": "Alta liquidez; evitar comprar resistencia 538-550",
    },
    "PLUMEUSDT": {
        "tier": "ESTRUCTURAL",
        "weight": "20-25%",
        "ref_high": 0.0112,
        "buy_zones": [0.0105, 0.0102],  # Piso de rebote 0.01020
        "min_drop_pct": 6.0,
        "note": "Entradas previas +$290K; moderar tamaño cerca de desbloqueos fin de mes",
    },
    "RSRUSDT": {
        "tier": "ESTRUCTURAL",
        "weight": "20-25%",
        "ref_high": 0.00130,
        "buy_zones": [0.00122, 0.00118],
        "min_drop_pct": 5.5,
        "note": "Rebote limpio; vigilar eventos/quema de fin de noviembre",
    },

    # --- TÁCTICAS DESTACADAS / PUENTE (15% - 20%) ---
    "ZECUSDT": {
        "tier": "TACTICA_PUENTE",
        "weight": "15-20%",
        "ref_high": 824.40,
        "buy_zones": [778.0, 764.0],    # Retroceso sano hacia EMA25/EMA99 en 15m
        "min_drop_pct": 6.0,
        "note": "Alta liquidez; esperar enfriamiento de RSI(6) en 15m",
    },
    "ZAMAUSDT": {
        "tier": "TACTICA_PUENTE",
        "weight": "15-20%",
        "ref_high": 0.06106,
        "buy_zones": [0.0586, 0.05765], # EMA25/Supertrend y EMA99 en 15m
        "min_drop_pct": 5.5,
        "note": "Narrativa FHE; cautela por 71.6% bloqueado (~4.06M/día) y concentración",
    },

    # --- CAZA TÁCTICA DE REBOTES / OBSERVACIÓN (5% - 15%) ---
    "HOTUSDT": {
        "tier": "CAZA_REBOTE",
        "weight": "10-15%",
        "ref_high": 0.000392,
        "buy_zones": [0.000339, 0.000331],
        "min_drop_pct": 8.0,
        "note": "Solo retrocesos con porción chica; baja concentración (~0.035)",
    },
    "JUPUSDT": {
        "tier": "CAZA_REBOTE",
        "weight": "10-15%",
        "ref_high": 0.2250,
        "buy_zones": [0.2080, 0.2020],
        "min_drop_pct": 8.0,
        "note": "Vigilar >50.6% bloqueado y evento/alerta de tokens",
    },
    "HYPEUSDT": {
        "tier": "CAZA_REBOTE",
        "weight": "5-10%",
        "ref_high": 62.0,
        "buy_zones": [56.5, 55.0],
        "min_drop_pct": 8.0,
        "note": "Alta volatilidad y salidas previas; solo táctica estrecha",
    },
    "RIFUSDT": {
        "tier": "CAZA_REBOTE",
        "weight": "5-10%",
        "ref_high": 0.0490,
        "buy_zones": [0.0452, 0.0445],
        "min_drop_pct": 8.0,
        "note": "Volúmenes horarios bajos; operar solo con límite",
    },
    "PUMPUSDT": {
        "tier": "CAZA_REBOTE",
        "weight": "5-10%",
        "ref_high": 0.0040,
        "buy_zones": [0.0034, 0.0032],
        "min_drop_pct": 9.0,
        "note": "Salidas fuertes previas y >21.9% bloqueado; porción mínima",
    },
    "LUNCUSDT": {
        "tier": "CAZA_REBOTE",
        "weight": "5-10%",
        "ref_high": 0.000050,
        "buy_zones": [0.000042, 0.000039],
        "min_drop_pct": 9.0,
        "note": "Exclusivamente rebote táctico de corto plazo",
    },

    # --- DESCARTADAS (0% - 5%) -> EXCLUIDAS DE COMPRAS POR DEFECTO ---
    "MANTRAUSDT": {"tier": "DESCARTADA", "weight": "0-5%"},
    "TNSRUSDT":   {"tier": "DESCARTADA", "weight": "0-5%"},
    "MITOUSDT":   {"tier": "DESCARTADA", "weight": "0-5%"},
    "OPENUSDT":   {"tier": "DESCARTADA", "weight": "0-5%"},
    "ALLOUSDT":   {"tier": "DESCARTADA", "weight": "0-5%"},
    "BICOUSDT":   {"tier": "DESCARTADA", "weight": "0-5%"},
    "KAITOUSDT":  {"tier": "DESCARTADA", "weight": "0-5%"},
    "BONKUSDT":   {"tier": "DESCARTADA", "weight": "0-5%"},
    "TUTUSDT":    {"tier": "DESCARTADA", "weight": "0-5%"},
    "ACEUSDT":    {"tier": "DESCARTADA", "weight": "0-5%"},
    "GIGGLEUSDT": {"tier": "DESCARTADA", "weight": "0-5%"},
    "OGUSDT":     {"tier": "DESCARTADA", "weight": "0-5%"},
    "MOVRUSDT":   {"tier": "DESCARTADA", "weight": "0-5%"},
    "APEUSDT":    {"tier": "DESCARTADA", "weight": "0-5%"},
    "HEIUSDT":    {"tier": "DESCARTADA", "weight": "0-5%"},
}


# ==========================================
# 3. FUNCIONES DE DATOS E INDICADORES
# ==========================================
def binance_get(path: str, params: Optional[dict] = None) -> Optional[dict | list]:
    for base in BINANCE_SPOT_ENDPOINTS:
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
    ema = sum(values[:period]) / period
    for price in values[period:]:
        ema = price * k + ema * (1.0 - k)
    return ema


def calc_rsi(values: List[float], period: int = 6) -> Optional[float]:
    if len(values) <= period:
        return None
    gains, losses = [], []
    for i in range(1, len(values)):
        diff = values[i] - values[i - 1]
        gains.append(max(diff, 0.0))
        losses.append(max(-diff, 0.0))
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def get_klines(symbol: str, interval: str, limit: int = 120) -> List[dict]:
    raw = binance_get("/api/v3/klines", {"symbol": symbol, "interval": interval, "limit": limit})
    if not isinstance(raw, list):
        return []
    out = []
    for k in raw:
        out.append({
            "open": float(k[1]),
            "high": float(k[2]),
            "low": float(k[3]),
            "close": float(k[4]),
            "quote_vol": float(k[7]),
        })
    return out


def get_24h_ticker(symbol: str) -> Optional[dict]:
    data = binance_get("/api/v3/ticker/24hr", {"symbol": symbol})
    return data if isinstance(data, dict) and "lastPrice" in data else None


def fmt_price(p: float) -> str:
    if p >= 100:
        return f"{p:,.2f}"
    if p >= 1:
        return f"{p:.4f}"
    if p >= 0.01:
        return f"{p:.5f}"
    if p >= 0.0001:
        return f"{p:.6f}"
    return f"{p:.8f}"


# ==========================================
# 4. EVALUACIÓN DE CAÍDA Y REGLAS SPOT
# ==========================================
def evaluate_asset(symbol: str, cfg: dict) -> Optional[Tuple[str, str]]:
    tier = cfg["tier"]
    ticker = get_24h_ticker(symbol)
    klines_15m = get_klines(symbol, "15m", limit=120)
    klines_1d = get_klines(symbol, "1d", limit=120)

    if not ticker or len(klines_15m) < 30 or len(klines_1d) < 20:
        return None

    last_price = float(ticker["lastPrice"])
    pct_24h = float(ticker["priceChangePercent"])
    quote_vol_24h = float(ticker["quoteVolume"])

    closes_15m = [c["close"] for c in klines_15m]
    highs_15m = [c["high"] for c in klines_15m[-48:]]  # Últimas 12h en 15m
    lows_15m = [c["low"] for c in klines_15m[-48:]]
    lows_1d = [c["low"] for c in klines_1d[-60:]]

    ema7_15m = calc_ema(closes_15m, 7)
    ema25_15m = calc_ema(closes_15m, 25)
    ema99_15m = calc_ema(closes_15m, 99)
    rsi6_15m = calc_rsi(closes_15m, 6)

    closes_1d = [c["close"] for c in klines_1d]
    ema7_1d = calc_ema(closes_1d, 7)
    ema99_1d = calc_ema(closes_1d, 99)

    recent_high_15m = max(highs_15m) if highs_15m else last_price
    ref_high = max(cfg.get("ref_high", recent_high_15m), recent_high_15m)
    drop_from_high_pct = ((ref_high - last_price) / ref_high * 100.0) if ref_high > 0 else 0.0

    # Si está descartada, solo alertar si se habilita explícitamente un nuevo mínimo de 60d
    if tier == "DESCARTADA":
        min_60d = min(lows_1d) if lows_1d else last_price
        if ALERT_ON_DISCARDED_NEW_LOW and last_price <= min_60d * 1.005:
            msg = (
                f"🗑️ *DESCARTADA EN NUEVO MÍNIMO* — `{symbol}`\n"
                f"• Precio: *{fmt_price(last_price)}* (24h: `{pct_24h:+.2f}%`)\n"
                f"• Mínimo 60d: `{fmt_price(min_60d)}` | Vol 24h: `${quote_vol_24h:,.0f}`\n"
                f"• Regla: *Evitar cazar caída (alta dilución/baja concentración/riesgo estructural)*"
            )
            return ("NEW_LOW_DISCARDED", msg)
        return None

    buy_zones: List[float] = cfg.get("buy_zones", [])
    min_drop = float(cfg.get("min_drop_pct", 6.0))
    zone_hit = min([z for z in buy_zones if last_price <= z * 1.005], default=None)

    # Condiciones de caída relevante para compra escalonada en Spot
    is_zone_dip = zone_hit is not None
    is_percent_dip = drop_from_high_pct >= min_drop and pct_24h <= -2.0

    if not (is_zone_dip or is_percent_dip):
        return None

    # Evitar alertar "compra" si está en rebote vertical con RSI(6) en 15m muy sobrecomprado (>82)
    if rsi6_15m is not None and rsi6_15m > 82 and not is_zone_dip:
        return None

    above_ema99_15m = (ema99_15m is not None and last_price >= ema99_15m)
    below_ema99_1d = (ema99_1d is not None and last_price < ema99_1d)

    tag_map = {
        "ESTRUCTURAL": "⭐ FAVORITO ESTRUCTURAL",
        "TACTICA_PUENTE": "🎯 TÁCTICA PUENTE",
        "CAZA_REBOTE": "⚡ CAZA DE REBOTE",
    }

    alert_type = "ZONE_HIT" if is_zone_dip else "PERCENT_DIP"
    zones_str = " / ".join(fmt_price(z) for z in buy_zones) if buy_zones else "N/A"
    rsi_str = f"{rsi6_15m:.1f}" if rsi6_15m is not None else "N/A"
    ema99_15m_str = fmt_price(ema99_15m) if ema99_15m is not None else "N/A"
    floor_15m_str = fmt_price(min(lows_15m)) if lows_15m else "N/A"

    msg = (
        f"{tag_map.get(tier, tier)} — *`{symbol}`* (`{cfg.get('weight', '')}`)\n"
        f"• Precio: *{fmt_price(last_price)}* | 24h: `{pct_24h:+.2f}%` | Caída vs ref: `-{drop_from_high_pct:.2f}%`\n"
        f"• Zonas límite: `{zones_str}` | Mín 12h: `{floor_15m_str}`\n"
        f"• 15m: `RSI(6)={rsi_str}` | `EMA99={ema99_15m_str}` ({'encima' if above_ema99_15m else 'debajo'})\n"
        f"• Estructura 1D: `{'bajo EMA99' if below_ema99_1d else 'sobre/cerca EMA99'}` | Vol 24h: `${quote_vol_24h:,.0f}`\n"
        f"• Nota: _{cfg.get('note', '')}_"
    )
    return (alert_type, msg)


# ==========================================
# 5. ESTADO, COOLDOWN Y ENVÍO A TELEGRAM
# ==========================================
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
        print("[AVISO] Configurá TELEGRAM_BOT_TOKEN y TELEGRAM_CHAT_ID. Mensaje:")
        print(text)
        print("-" * 45)
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True,
    }
    try:
        r = requests.post(url, json=payload, timeout=10)
        return r.status_code == 200
    except requests.RequestException as exc:
        print(f"[ERROR TELEGRAM] {exc}")
        return False


def run_monitor() -> None:
    now_ts = time.time()
    cooldown_sec = COOLDOWN_MINUTES * 60
    state = load_state()
    alerts_sent = 0

    for symbol, cfg in ASSETS.items():
        result = evaluate_asset(symbol, cfg)
        if not result:
            continue
        alert_type, message = result
        state_key = f"{symbol}:{alert_type}"
        last_sent = float(state.get(state_key, 0.0))

        if now_ts - last_sent >= cooldown_sec:
            if send_telegram(message) or "TU_BOT_TOKEN_AQUI" in TELEGRAM_BOT_TOKEN:
                state[state_key] = now_ts
                alerts_sent += 1

    save_state(state)
    utc_now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    print(f"[{utc_now}] Revisión completada. Alertas disparadas: {alerts_sent}")


if __name__ == "__main__":
    run_monitor()
