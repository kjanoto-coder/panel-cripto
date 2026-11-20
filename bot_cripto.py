import os
import re
import json
import time
import random
import requests
import html
from datetime import datetime, timezone, timedelta
import numpy as np
import matplotlib.pyplot as plt
from google import genai

TZ_ART = timezone(timedelta(hours=-3))

TELEGRAM_BOT_TOKEN = (os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("TELEGRAM_TOKEN") or "").strip()
TELEGRAM_CHAT_ID = (os.getenv("TELEGRAM_CHAT_ID") or os.getenv("CHAT_ID") or "").strip()
TELEGRAM_TOPIC_ID = (os.getenv("TOPIC_ID_CENTRAL") or "1").strip()
GEMINI_API_KEY = (os.getenv("GEMINI_API_KEY") or "").strip()
BASE_URL_NETLIFY = "https://gregarious-frangollo-0346c5.netlify.app"

ARCHIVO_MEMORIA = "ultimas_perlas.json"
PRECIO_MAX_SILENCIOSA = 5.00

def ahora_art():
    return datetime.now(TZ_ART)

def cargar_memoria_perlas():
    if os.path.exists(ARCHIVO_MEMORIA):
        try:
            with open(ARCHIVO_MEMORIA, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return []
    return []

def guardar_memoria_perlas(historial_reportes):
    try:
        with open(ARCHIVO_MEMORIA, 'w', encoding='utf-8') as f:
            json.dump(historial_reportes[-2:], f, indent=2)
    except Exception as e:
        print(f"Error guardando memoria: {e}")

def crear_sesion_binance():
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json"
    })
    return session

def obtener_simbolos_spot_activos(session):
    urls = [
        "https://data-api.binance.vision/api/v3/exchangeInfo",
        "https://api.binance.com/api/v3/exchangeInfo",
        "https://api1.binance.com/api/v3/exchangeInfo"
    ]
    for url in urls:
        try:
            res = session.get(url, timeout=12)
            if res.status_code == 200:
                simbolos_activos = set()
                for s in res.json().get('symbols', []):
                    if (s.get('status') == 'TRADING' and
                        s.get('isSpotTradingAllowed', True) and
                        s.get('quoteAsset') == 'USDT'):
                        simbolos_activos.add(s.get('symbol'))
                if simbolos_activos:
                    return simbolos_activos
        except Exception:
            continue
    return set()

def obtener_datos_binance(session):
    urls = [
        "https://data-api.binance.vision/api/v3/ticker/24hr",
        "https://api.binance.com/api/v3/ticker/24hr",
        "https://api1.binance.com/api/v3/ticker/24hr"
    ]
    for url in urls:
        try:
            response = session.get(url, timeout=15)
            if response.status_code == 200 and isinstance(response.json(), list):
                data = response.json()
                if data:
                    return data
        except Exception:
            continue
    return []

def formatear_precio(precio):
    if precio is None or precio <= 0:
        return "$0.00"
    elif precio >= 100:
        return f"${precio:,.2f}"
    elif precio >= 1.0:
        return f"${precio:.4f}"
    elif precio >= 0.01:
        return f"${precio:.5f}"
    elif precio >= 0.0001:
        return f"${precio:.6f}"
    else:
        return f"${precio:.8f}"

def generar_barra_progreso(cambio, tipo_bloque=""):
    if tipo_bloque == "acumulacion_24h":
        return "🟨🟨🟨⬜⬜"
    elif tipo_bloque == "silenciosa":
        return "💎💎💎💎⬜"
    if cambio >= 50:
        return "🟢🟢🟢🟢🟢"
    elif cambio >= 25:
        return "🟢🟢🟢🟢⬜"
    elif cambio >= 15:
        return "🟢🟢🟢⬜⬜"
    elif cambio >= 5:
        return "🟢🟢⬜⬜⬜"
    elif cambio > 0:
        return "🟢⬜⬜⬜⬜"
    elif cambio > -5:
        return "🟥🟥⬜⬜⬜"
    elif cambio > -12:
        return "🟥🟥🟥⬜⬜"
    elif cambio > -20:
        return "🟥🟥🟥🟥⬜"
    else:
        return "🟥🟥🟥🟥🟥"

def seleccionar_silenciosas_con_gemini(candidatas, historial_previo):
    simbolos_bloqueados = {item for reporte in historial_previo for item in reporte}
    pool = [c for c in candidatas if c['symbol'] not in simbolos_bloqueados]
    if len(pool) < 7:
        pool = candidatas

    pool_ordenado = sorted(
        pool,
        key=lambda x: (x
