import os
import json
import time
import random
import requests
import html
from datetime import datetime
import numpy as np
import matplotlib.pyplot as plt

# --- CONFIGURACIÓN DE ENTORNO BLINDADAS ---
TELEGRAM_BOT_TOKEN = (os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("TELEGRAM_TOKEN") or "").strip()
TELEGRAM_CHAT_ID = (os.getenv("TELEGRAM_CHAT_ID") or os.getenv("CHAT_ID") or "").strip()
# Lee el secret específico para Cazador Táctico o usa '4' por defecto
TELEGRAM_TOPIC_ID = (os.getenv("TOPIC_ID_TACTICO") or os.getenv("TOPIC_ID_CENTRAL") or "4").strip()
BASE_URL_NETLIFY = "https://gregarious-frangollo-0346c5.netlify.app"

def crear_sesion_binance():
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json"
    })
    return session

def obtener_simbolos_spot_activos(session):
    """Garantiza 100% que las monedas existen y operan activamente en Binance Spot (Cero monedas fantasma)"""
    urls = [
        "https://api.binance.com/api/v3/exchangeInfo",
        "https://data-api.binance.vision/api/v3/exchangeInfo"
    ]
    for url in urls:
        try:
            res = session.get(url, timeout=12)
            if res.status_code == 200:
                data = res.json()
                simbolos_activos = set()
                for s in data.get('symbols', []):
                    if (s.get('status') == 'TRADING' and 
                        s.get('isSpotTradingAllowed', True) and 
                        s.get('quoteAsset') == 'USDT'):
                        simbolos_activos.add(s.get('symbol'))
                if len(simbolos_activos) > 0:
                    return simbolos_activos
        except Exception as e:
            print(f"⚠️ Error obteniendo exchangeInfo de {url}: {e}")
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
            print(f"⚠️ Error al conectar con {url}: {e}")
    return []

def formatear_precio(precio):
    if precio >= 1.0:
        return f"${precio:.2f}"
    elif precio >= 0.01:
        return f"${precio:.4f}"
    elif precio >= 0.0001:
        return f"${precio:.6f}"
    else:
        return f"${precio:.8f}"

def evaluar_estado_semaforo(posicion_pct):
    if posicion_pct > 65.0:
        return "ROJO", "🔴 Próxima Ganadora (Explosión Inminente)", "#ff1744", "🔴"
    elif posicion_pct >= 30.0:
        return "AMARILLO", "🟡 Posibilidad Media (Confirmación Táctica)", "#ffd600", "🟡"
    else:
        return "VERDE", "🟢 Cazada en Inicios (Acumulación Fria)", "#00e676", "🟢"

def motor_ia_seleccion_tactica(tickers,
