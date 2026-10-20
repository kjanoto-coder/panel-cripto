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
TELEGRAM_TOPIC_ID = (os.getenv("TOPIC_ID_CAZADOR") or os.getenv("TOPIC_ID_CENTRAL") or "1").strip()
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

def motor_ia_seleccion_tactica(tickers, simbolos_activos):
    """
    Motor analítico con inteligencia de selección: filtra basuras, stablecoins y mega-caps,
    calcula mapa de calor de liquidez, anomalías de volumen y selecciona con precisión quirúrgica
    las mejores alternativas reales del mercado.
    """
    STABLECOINS_Y_FIAT = ['USDT', 'USDC', 'FDUSD', 'DAI', 'TUSD', 'USDP', 'EUR', 'BUSD', 'USD1', 'AEUR', 'EURI']
    MEGA_CAPS = ['BTC', 'ETH', 'SOL', 'ADA', 'XRP', 'DOGE', 'TRX', 'SHIB', 'AVAX', 'LINK', 'BNB', 'DOT', 'NEAR', 'SUI', 'PEPE']
    EXCLUIDOS_TOTALES = set(STABLECOINS_Y_FIAT + MEGA_CAPS)
    
    candidatas_rojas = []
    candidatas_amarillas = []
    candidatas_verdes = []
    total_analizadas = 0
    
    for t in tickers:
        symbol = t.get('symbol', '')
        base = symbol.replace('USDT', '')
        
        # Validación estricta de existencia real en Spot
        if (symbol in simbolos_activos and 
            symbol.endswith('USDT') and 
            base not in EXCLUIDOS_TOTALES and 
            not any(x in symbol for x in ['UP', 'DOWN', 'BULL', 'BEAR'])):
            
            try:
                precio = float(t.get('lastPrice', 0))
                cambio_24h = float(t.get('priceChangePercent', 0))
                vol_usdt = float(t.get('quoteVolume', 0))
                high = float(t.get('highPrice', 0))
                low = float(t.get('lowPrice', 0))
                
                # Criterio estricto de perla escondida / baja capitalización nominal sub-$1.00 USD
                if (0.000001 <= precio < 1.00 and 
                    350_000 <= vol_usdt <= 25_000_000 and 
                    -5.0 <= cambio_24h <= 8.0):
                    
                    total_analizadas += 1
                    
                    # Mapa de calor de liquidez (Posición porcentual en el rango diario)
                    pos_liquidez_pct = ((precio - low) / (high - low)) * 100 if high > low else 50.0
                    pos_liquidez_pct = round(pos_liquidez_pct, 1)
                    
                    categoria, estado_texto, color_hex, emoji_semaforo = evaluar_estado_semaforo(pos_liquidez_pct)
                    
                    # Anomalía de Volumen (Spike Factor)
                    rango = high - low
                    pct_rango = (rango / precio) * 100 if precio > 0 else 1
                    factor_spike = (vol_usdt / 1_000_000) / (pct_rango if pct_rango > 0 else 1)
                    
                    # Puntuación de Inteligencia Artificial (IA Scoring Táctico)
                    score_ia = factor_spike * (1.0 + (pos_liquidez_pct / 100.0) if categoria != "VERDE" else 1.5 - (pos_liquidez_pct / 100.0))
                    
                    item = {
                        'symbol': symbol,
                        'precio_f': precio,
                        'cambio_f': cambio_24h,
                        'vol_f': vol_usdt,
                        'high_f': high,
                        'low_f': low,
                        'pos_liquidez_pct':
