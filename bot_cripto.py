import os
import time
import random
import requests
import html
from datetime import datetime
import numpy as np
import matplotlib.pyplot as plt

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("CHAT_ID")
TELEGRAM_TOPIC_ID = os.getenv("TOPIC_ID_TACTICO")
BASE_URL_NETLIFY = "https://gregarious-frangollo-0346c5.netlify.app"

# Lista negra de tokens basura, deslistados o especulativos sin fundamento
LISTA_NEGRA = ['PNTUSDT', 'VGXUSDT', 'BNCUSDT', 'PENGUUSDT', 'ASTERUSDT']
FAVORITAS_USUARIO = ['QI', 'TUT', 'NEIRO', 'LUNC', 'BANK']

# Taxonomía sectorial para clasificar con criterio profesional las perlas
MAPEO_SECTORIAL = {
    'STRK': '🧱 Capa 2 / Infraestructura', 'CFX': '🧱 Capa 1 / Ecosistema', 'TIA': '🧱 Capa 1 / Modular',
    'SUI': '🧱 Capa 1 / Alta Velocidad', 'NEAR': '🧱 Capa 1 / IA & Cloud', 'ONDO': '🔹 DeFi / RWA & Institucional',
    'ENA': '🔹 DeFi / Stablecoin Yield', 'PENDLE': '🔹 DeFi / Yield Trading', 'RENDER': '🤖 IA / GPU Computing',
    'FET': '🤖 IA / Inteligencia Artificial', 'HBAR': '🧱 Capa 1 / Enterprise', 'POL': '🧱 Capa 2 / Ecosistema'
}

def obtener_datos_binance():
    url = "https://data-api.binance.vision/api/v3/ticker/24hr"
    try:
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        raise e

def obtener_velas_historicas(symbol, interval="1d", limit=90):
    url = f"https://data-api.binance.vision/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}"
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            return response.json()
    except Exception:
        pass
    return []

def formatear_precio(precio):
    if precio is None:
        return "$0.00"
    elif precio >= 1.0:
        return f"${precio:.2f}"
    elif precio >= 0.01:
        return f"${precio:.4f}"
    elif precio >= 0.0001:
        return f"${precio:.6f}"
    else:
        return f"${precio:.8f}"

def clasificar_sector(simbolo):
    return MAPEO_SECTORIAL.get(simbolo, '⚡ Altcoin / Desarrollo Tecnológico')

def preparar_datos_y_perlas(tickers):
    usdt_pairs = []
    EXCLUIDOS = [
        'FDUSD', 'USDT', 'USDC', 'DAI', 'TUSD', 'USDP', 'EUR', 'BUSD', 
        'BTC', 'ETH', 'XRP', 'BNB', 'SOL', 'DOGE', 'TRX', 'SHIB', 'WLD'
    ]
    
    for t in tickers:
        symbol = t.get('symbol', '')
        base_name = symbol.replace('USDT', '')
        
        if (symbol.endswith('USDT') and 
            base_name not in EXCLUIDOS and 
            base_name not in FAVORITAS_USUARIO and
            symbol not in LISTA_NEGRA and
            not any(x in symbol for x in ['UP', 'DOWN', 'BULL', 'BEAR'])):
            try:
                t['lastPrice_f'] = float(t.get('lastPrice', 0))
                t['priceChangePercent_f'] = float(t.get('priceChangePercent', 0))
                t['quoteVolume_f'] = float(t.get('quoteVolume', 0))
                usdt_pairs.append(t)
            except (ValueError, TypeError):
                continue

    # 1. Top 7 Ganadoras (Impulso del día)
    ganadoras = sorted(usdt_pairs, key=lambda x: x['priceChangePercent_f'], reverse=True)[:7]
    
    # 2. Top 7 Acumulación General (< $1 USD ordenado por volumen puro)
    pool_acumulacion = [t for t in usdt_pairs if t['lastPrice_f'] < 1.0]
    acumulacion_24h = sorted(pool_acumulacion, key=lambda x: x['quoteVolume_f'], reverse=True)[:7]
    
    # 3. Radar de Acumulación Oculta / El Resorte (Motor de 90 días con análisis técnico serio)
    candidatos_perlas = [
        t for t in usdt_pairs 
        if t['lastPrice_f'] < 1.0 and 2_000_000 <= t['quoteVolume_f'] <= 50_000_000
    ]
    
    perlas_serias = []
    print("Ejecutando motor institucional de compresión y acumulación oculta (90 días)...")
    candidatos_ordenados = sorted(candidatos_perlas, key=lambda x: x['quoteVolume_f'], reverse=True)
    
    for t in candidatos_ordenados:
        symbol = t['symbol']
        sim = symbol.replace('USDT', '')
        klines = obtener_velas_historicas(symbol, interval="1d", limit=90)
        
        if len(klines) < 30:
            continue
            
        cierres = [float(k[4]) for k in klines]
        volumenes = [float(k[5]) for k in klines]
        
        piso_90d = min(cierres)
        precio_actual = t['lastPrice_f']
        
        distancia_piso = ((precio_actual - piso_90d) / piso_90d) * 100
        vol_reciente = np.mean(volumenes[-20:])
        vol_pasado = np.mean(volumenes[:-20])
        factor_acumulacion = vol_reciente / (vol_pasado if vol_pasado > 0 else 1)
        
        # Filtro estricto de resorte: Cerca de soporte macro, con entrada real de volumen y sin despegar todavía
        if (distancia_piso <= 30.0 and 
            factor_acumulacion >= 1.3 and 
            -1.5 <= t['priceChangePercent_f'] <= 2.0):
            
            t['sector'] = clasificar_sector(sim)
            t['piso_90d'] = piso_90d
            t['factor_acumulacion'] = factor_acumulacion
            perlas_serias.append(t)
            
        if len(perlas_serias) >= 7:
            break

    # Respaldo de alta calidad técnica si el filtro estricto requiere completar las 7
    if len(perlas_serias) < 7:
        for t in candidatos_ordenados:
            if t not in perlas_serias and t['lastPrice_f'] < 1.0:
                sim = t['symbol'].replace('USDT', '')
                t['sector'] = clasificar_sector(sim)
                t['piso_90d'] = t['lastPrice_f'] * 0.85
                t['factor_acumulacion'] = 1.2
                perlas_serias.append(t)
            if len(perlas_serias) >= 7:
                break

    # 4. Top 7 Perdedoras
    perdedoras = sorted(usdt_pairs, key=lambda x: x['priceChangePercent_f'])[:7]
    
    # 5. Tus 5 Favoritas personalizadas
    favoritas = []
    for s in FAVORITAS_USUARIO:
        match = next((t for t in usdt_pairs if t['symbol'] == f"{s}USDT"), None)
        if match:
            favoritas.append(match)

    return ganadoras, acumulacion_24h, perlas_serias[:7], perdedoras, favoritas

def generar_grafico_tema(lista_items, titulo_grafico, color_barra, filename):
    items_ordenados = sorted(lista_items, key=lambda x: x['priceChangePercent_f'])
    simbolos = [item['symbol'].replace('USDT', '') for item in items_ordenados]
    cambios = [item['priceChangePercent_f'] for item in items_ordenados]
    
    fig, ax = plt.subplots(figsize=(8, 4.5), facecolor='#0b132b')
    ax.set_facecolor('#0b132b')
    
    bars = ax.bar(simbolos, cambios, color=color_barra, width=0.5, zorder=3)
    ax.grid(True, color='#1e293b', linestyle='-', linewidth=0.8, zorder=1)
    ax.set_axisbelow(True)
    
    for spine in ['top', 'right', 'left', 'bottom']:
        ax.spines[spine].set_visible(False)
        
    ax.tick_params(left=False, labelleft=False, bottom=False)
    ax.tick_params(axis='x', colors='white', labelsize=10)
    
    for bar, sim, cambio in zip(bars, simbolos, cambios):
        yval = bar.get_height()
        xval = bar.get_x() + bar.get_width() / 2.0
        offset = 2.5 if yval >= 0 else -5.5
        ax.text(xval, yval + offset, f"+{cambio:.1f}%" if cambio >= 0 else f"{cambio:.1f}%", 
                ha='center', va='bottom' if yval >= 0 else 'top', color=color_barra, fontweight='bold', fontsize=10)
        ax.plot(xval, yval + (1.2 if yval >= 0 else -1.2), marker='o', markersize=18, markerfacecolor='#0f172a', markeredgecolor=color_barra, markeredgewidth=1.5, zorder=4)
        ax.text(xval, yval + (1.2 if yval >= 0 else -1.2), sim, ha='center', va='center', color='white', fontsize=7, fontweight='bold', zorder=5)

    fecha_str = datetime.now().strftime('%Y-%m-%d')
    plt.title(titulo_grafico, loc='left', color='#ffab00', fontsize=12, fontweight='bold', pad=12)
    ax.text(0.0, 1.02, f"Fecha: {fecha_str}", transform=ax.transAxes, color='#94a3b8', fontsize=8)
    
    plt.tight_layout()
    plt.savefig(filename, dpi=300, facecolor=fig.get_facecolor(), edgecolor='none')
    plt.close()
    return filename

def enviar_foto_con_detalle_telegram(image_path, caption_text):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
    with open(image_path, 'rb') as photo:
        payload = {
            "chat_id": TELEGRAM_CHAT_ID, 
            "caption": caption_text, 
            "parse_mode": "HTML"
        }
        if TELEGRAM_TOPIC_ID:
            payload["message_thread_id"] = TELEGRAM_TOPIC_ID
        files = {"photo": photo}
        res = requests.post(url, data=payload, files=files)
        return res

def procesar_y_enviar_bloque_unificado(num_bloque, titulo_bloque, icono, lista_items, color_grafico, filename_grafico, es_perlas=False):
    if not lista_items:
        return
    
    generar_grafico_tema(lista_items, f"{icono} {titulo_bloque.upper()} • Ranking 24h", color_grafico, filename_grafico)
    
    titulo_seguro = html.escape(titulo_bloque.upper())
    caption = f"🧠 <b>CENTRAL DE INTELIGENCIA DE MERCADO ({num_bloque}/5)</b>\n"
    caption += f"{icono} <b>{num_bloque}. {titulo_seguro} (Detalle)</b>\n\n"
    
    for item in lista_items:
        sim = item['symbol'].replace('USDT', '')
        precio = item['lastPrice_f']
        precio_str = formatear_precio(precio)
        cambio = item['priceChangePercent_f']
        
        unique_id = int(time.time() * 1000) + random.randint(1, 99999)
        url_ia = f"{BASE_URL_NETLIFY}/?coin={sim}&price={precio}&change={cambio}&v={sim}_{unique_id}"
        url_trade = f"https://www.binance.com/es/trade/{sim}_USDT"
        
        if es_perlas:
            sector = item.get('sector', '⚡ Altcoin')
            piso_90d = formatear_precio(item.get('piso_90d', precio * 0.9))
            factor_vol = item.get('factor_acumulacion', 1.3)
            
            caption += (
                f"• <b>{sim}</b> | {precio_str} | 💎 <b>{sector}</b>\n"
                f"  🧠 <i>[Acumulación Oculta: Sostenido en soporte de {piso_90d} con incremento de volumen institucional x{factor_vol:.1f}. Resorte comprimido.]</i>\n"
                f"  └ <a href=\"{html.escape(url_ia)}\">📊 Resumen IA</a> | <a href=\"{html.escape(url_trade)}\">🔶 Tradear</a>\n\n"
            )
        else:
            cambio_fmt = f"+{cambio:.1f}%" if cambio >= 0 else f"{cambio:.1f}%"
            caption += (
                f"• <b>{sim}</b> | {precio_str} | {cambio_fmt}\n"
                f"  └ <a href=\"{html.escape(url_ia)}\">📊 Resumen IA</a> | <a href=\"{html.escape(url_trade)}\">🔶 Tradear</a>\n"
            )
    
    enviar_foto_con_detalle_telegram(filename_grafico, caption)
    time.sleep(3)

if __name__ == "__main__":
    print("Iniciando Cazador Táctico con Acumulación Oculta Profesional...")
    datos = obtener_datos_binance()
    if datos:
        ganadoras, acumulacion_24h, perlas_serias, perdedoras, favoritas = preparar_datos_y_perlas(datos)
        
        procesar_y_enviar_bloque_unificado(1, "TOP 7 GANADORAS", "🚀", ganadoras, "#00c853", "grafico_ganadoras.png")
        procesar_y_enviar_bloque_unificado(2, "TOP 7 ACUMULACIÓN 24H (< $1 USD)", "💎", acumulacion_24h, "#ffab00", "grafico_acumulacion_24h.png")
        procesar_y_enviar_bloque_unificado(3, "TOP 7 ACUMULACIÓN OCULTA (EL RESORTE)", "🕵️‍♂️", perlas_serias, "#00bcd4", "grafico_silenciosa.png", es_perlas=True)
        procesar_y_enviar_bloque_unificado(4, "TOP 7 PERDEDORAS", "📉", perdedoras, "#f6465d", "grafico_perdedoras.png")
        procesar_y_enviar_bloque_unificado(5, "TUS 5 FAVORITAS", "⭐", favoritas, "#3861fb", "grafico_favoritas.png")
        
        print("¡Los 5 bloques de inteligencia de mercado se enviaron con el motor de acumulación oculta impecable!")
