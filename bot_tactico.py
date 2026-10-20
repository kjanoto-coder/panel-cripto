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

def escanear_mercado_cazador_9_monedas(tickers, simbolos_activos):
    STABLECOINS_Y_FIAT = ['USDT', 'USDC', 'FDUSD', 'DAI', 'TUSD', 'USDP', 'EUR', 'BUSD', 'USD1', 'AEUR', 'EURI']
    MEGA_CAPS = ['BTC', 'ETH', 'SOL', 'ADA', 'XRP', 'DOGE', 'TRX', 'SHIB', 'AVAX', 'LINK', 'BNB', 'DOT', 'NEAR', 'SUI', 'PEPE']
    EXCLUIDOS_TOTALES = set(STABLECOINS_Y_FIAT + MEGA_CAPS)
    
    rojas = []
    amarillas = []
    verdes = []
    total_analizadas = 0
    
    for t in tickers:
        symbol = t.get('symbol', '')
        base = symbol.replace('USDT', '')
        
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
                
                # CRITERIO PERLA ESCONDIDA (Liquidez + Precio Sub-$1.00 USD)
                if (0.000001 <= precio < 1.00 and 
                    350_000 <= vol_usdt <= 25_000_000 and 
                    -5.0 <= cambio_24h <= 8.0):
                    
                    total_analizadas += 1
                    
                    pos_liquidez_pct = ((precio - low) / (high - low)) * 100 if high > low else 50.0
                    pos_liquidez_pct = round(pos_liquidez_pct, 1)
                    
                    categoria, estado_texto, color_hex, emoji_semaforo = evaluar_estado_semaforo(pos_liquidez_pct)
                    
                    rango = high - low
                    pct_rango = (rango / precio) * 100 if precio > 0 else 1
                    factor_spike = (vol_usdt / 1_000_000) / (pct_rango if pct_rango > 0 else 1)
                    score_potencial = factor_spike * (1.0 + (pos_liquidez_pct / 100.0))
                    
                    item = {
                        'symbol': symbol,
                        'precio_f': precio,
                        'cambio_f': cambio_24h,
                        'vol_f': vol_usdt,
                        'high_f': high,
                        'low_f': low,
                        'pos_liquidez_pct': pos_liquidez_pct,
                        'categoria': categoria,
                        'estado_texto': estado_texto,
                        'color_hex': color_hex,
                        'emoji_semaforo': emoji_semaforo,
                        'factor_spike': round(factor_spike, 2),
                        'score_potencial': score_potencial
                    }
                    
                    if categoria == "ROJO":
                        rojas.append(item)
                    elif categoria == "AMARILLO":
                        amarillas.append(item)
                    else:
                        verdes.append(item)
            except (ValueError, TypeError):
                continue
                
    # Seleccionar las mejores 3 de cada categoría
    top_rojas = sorted(rojas, key=lambda x: x['score_potencial'], reverse=True)[:3]
    top_amarillas = sorted(amarillas, key=lambda x: x['score_potencial'], reverse=True)[:3]
    top_verdes = sorted(verdes, key=lambda x: x['score_potencial'], reverse=True)[:3]
    
    # Unir la lista final ordenada: 3 Rojas, 3 Amarillas, 3 Verdes
    top_9_perlas = top_rojas + top_amarillas + top_verdes
    return top_9_perlas, total_analizadas

def generar_grafico_cazador_9_monedas(lista_items, filename="grafico_cazador_9.png"):
    simbolos = [item['symbol'].replace('USDT', '') for item in lista_items]
    posiciones = [item['pos_liquidez_pct'] for item in lista_items]
    colores = [item['color_hex'] for item in lista_items]
    
    fig, ax = plt.subplots(figsize=(10, 5), facecolor='#0b132b')
    ax.set_facecolor('#0b132b')
    
    bars = ax.bar(simbolos, posiciones, color=colores, width=0.55, zorder=3)
    ax.grid(True, color='#1e293b', linestyle='-', linewidth=0.8, zorder=1)
    ax.set_axisbelow(True)
    
    ax.set_ylim(0, 115)
    for spine in ['top', 'right', 'left', 'bottom']:
        ax.spines[spine].set_visible(False)
        
    ax.tick_params(left=False, labelleft=False, bottom=False)
    ax.tick_params(axis='x', colors='white', labelsize=9)
    
    for bar, sim, pos, color in zip(bars, simbolos, posiciones, colores):
        yval = bar.get_height()
        xval = bar.get_x() + bar.get_width() / 2.0
        
        ax.text(xval, yval + 3.0, f"{pos:.0f}%", 
                ha='center', va='bottom', color=color, fontweight='bold', fontsize=9)
        
        ax.plot(xval, max(yval / 2.0, 12), marker='o', markersize=16, markerfacecolor='#0f172a', markeredgecolor=color, markeredgewidth=2.0, zorder=4)
        ax.text(xval, max(yval / 2.0, 12), sim, ha='center', va='center', color='white', fontsize=6.5, fontweight='bold', zorder=5)

    fecha_str = datetime.now().strftime('%Y-%m-%d')
    plt.title("🔥 CAZADOR TÁCTICO • RADAR 9 PERLAS (3 ROJAS | 3 AMARILLAS | 3 VERDES)", loc='left', color='#ffab00', fontsize=11, fontweight='bold', pad=12)
    ax.text(0.0, 1.02, f"Fecha: {fecha_str}", transform=ax.transAxes, color='#94a3b8', fontsize=8)
    
    plt.tight_layout()
    plt.savefig(filename, dpi=300, facecolor=fig.get_facecolor(), edgecolor='none')
    plt.close()
    return filename

def enviar_telegram(image_path, caption_text):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("⚠️ Faltan credenciales de Telegram.")
        return
        
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "caption": caption_text,
        "parse_mode": "HTML"
    }
    if TELEGRAM_TOPIC_ID:
        try:
            payload["message_thread_id"] = int(TELEGRAM_TOPIC_ID)
        except ValueError:
            pass

    with open(image_path, 'rb') as photo:
        res = requests.post(url, data=payload, files={"photo": photo})
        print(f"Respuesta Telegram: {res.status_code}")

if __name__ == "__main__":
    print("🔥 INICIANDO ESCÁNER DE CAZADOR TÁCTICO (MATRIZ 3x3)...")
    session = crear_sesion_binance()
    simbolos_activos = obtener_simbolos_spot_activos(session)
    datos = obtener_datos_binance(session)
    
    if datos and len(simbolos_activos) > 0:
        top_9_perlas, total_analizadas = escanear_mercado_cazador_9_monedas(datos, simbolos_activos)
        
        if len(top_9_perlas) > 0:
            filename = generar_grafico_cazador_9_monedas(top_9_perlas)
            
            caption = f"🔥 <b>CAZADOR TÁCTICO • RADAR 9 PERLAS</b>\n"
            caption += f"🛰️ <i>Selección 3x3 de Potenciales Ganadoras en Binance Spot</i>\n\n"
            caption += f"<b>UNIVERSO DE FILTRADO:</b> {total_analizadas} altcoins sub-$1.00 USD analizadas.\n\n"
            
            caption += f"🔴 <b>INMINENTE EXPLOSIÓN (PRÓXIMAS TOP GAINERS)</b>\n"
            for item in top_9_perlas:
                if item['categoria'] == "ROJO":
                    sim = item['symbol'].replace('USDT', '')
                    precio_str = formatear_precio(item['precio_f'])
                    vol_m = item['vol_f'] / 1_000_000
                    unique_id = int(time.time() * 1000) + random.randint(1, 9999)
                    url_ia = f"{BASE_URL_NETLIFY}/?coin={sim}&price={item['precio_f']}&change={item['cambio_f']}&high={item['high_f']}&low={item['low_f']}&v={sim}_{unique_id}"
                    url_trade = f"https://www.binance.com/es/trade/{sim}_USDT"
                    caption += (
                        f"• 🔴 <b>{sim}</b> ({item['cambio_f']:+.1f}%) — {precio_str}\n"
                        f"  <i>[Presión Vol: x{item['factor_spike']} | Vol 24h: ${vol_m:.2f}M]</i>\n"
                        f"  └ <a href=\"{html.escape(url_ia)}\">📊 Resumen IA</a> | <a href=\"{html.escape(url_trade)}\">🔶 Tradear</a>\n"
                    )
            
            caption += f"\n🟡 <b>CONFIRMACIÓN TÁCTICA MEDIA</b>\n"
            for item in top_9_perlas:
                if item['categoria'] == "AMARILLO":
                    sim = item['symbol'].replace('USDT', '')
                    precio_str = formatear_precio(item['precio_f'])
                    vol_m = item['vol_f'] / 1_000_000
                    unique_id = int(time.time() * 1000) + random.randint(1, 9999)
                    url_ia = f"{BASE_URL_NETLIFY}/?coin={sim}&price={item['precio_f']}&change={item['cambio_f']}&high={item['high_f']}&low={item['low_f']}&v={sim}_{unique_id}"
                    url_trade = f"https://www.binance.com/es/trade/{sim}_USDT"
                    caption += (
                        f"• 🟡 <b>{sim}</b> ({item['cambio_f']:+.1f}%) — {precio_str}\n"
                        f"  <i>[Presión Vol: x{item['factor_spike']} | Vol 24h: ${vol_m:.2f}M]</i>\n"
                        f"  └ <a href=\"{html.escape(url_ia)}\">📊 Resumen IA</a> | <a href=\"{html.escape(url_trade)}\">🔶 Tradear</a>\n"
                    )
                    
            caption += f"\n🟢 <b>CAZADAS EN INICIOS (ACUMULACIÓN DE PISO)</b>\n"
            for item in top_9_perlas:
                if item['categoria'] == "VERDE":
                    sim = item['symbol'].replace('USDT', '')
                    precio_str = formatear_precio(item['precio_f'])
                    vol_m = item['vol_f'] / 1_000_000
                    unique_id = int(time.time() * 1000) + random.randint(1, 9999)
                    url_ia = f"{BASE_URL_NETLIFY}/?coin={sim}&price={item['precio_f']}&change={item['cambio_f']}&high={item['high_f']}&low={item['low_f']}&v={sim}_{unique_id}"
                    url_trade = f"https://www.binance.com/es/trade/{sim}_USDT"
                    caption += (
                        f"• 🟢 <b>{sim}</b> ({item['cambio_f']:+.1f}%) — {precio_str}\n"
                        f"  <i>[Presión Vol: x{item['factor_spike']} | Vol 24h: ${vol_m:.2f}M]</i>\n"
                        f"  └ <a href=\"{html.escape(url_ia)}\">📊 Resumen IA</a> | <a href=\"{html.escape(url_trade)}\">🔶 Tradear</a>\n"
                    )
                
            enviar_telegram(filename, caption)
            print("✅ Reporte Matriz 3x3 enviado exitosamente a Telegram.")
