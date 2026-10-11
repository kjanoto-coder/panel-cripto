import os
import time
import random
import requests
import html
from datetime import datetime
import matplotlib.pyplot as plt

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("CHAT_ID")
TELEGRAM_TOPIC_ID = os.getenv("TOPIC_ID_TACTICO")
BASE_URL_NETLIFY = "https://gregarious-frangollo-0346c5.netlify.app"

# Lista negra para descartar tokens deslistados o problemáticos
LISTA_NEGRA = ['PNTUSDT', 'VGXUSDT', 'BNCUSDT']

def obtener_datos_binance():
    url = "https://data-api.binance.vision/api/v3/ticker/24hr"
    print("Conectando con la API de Binance...")
    try:
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        datos = response.json()
        print(f"¡Conexión exitosa! Se obtuvieron {len(datos)} pares.")
        return datos
    except Exception as e:
        print(f"Error crítico al conectar con Binance: {e}")
        raise e

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

def generar_barra_progreso(cambio, tipo_bloque=""):
    if tipo_bloque == "acumulacion_24h":
        return "🟨🟨🟨⬜⬜"
    elif tipo_bloque == "silenciosa":
        return "💎💎⬜⬜⬜"
    
    if cambio > 20:
        return "🟢🟢🟢🟢🟢"
    elif cambio > 10:
        return "🟢🟢🟢🟢⬜"
    elif cambio > 5:
        return "🟢🟢🟢⬜⬜"
    elif cambio > 0:
        return "🟢🟢⬜⬜⬜"
    elif cambio > -5:
        return "🟥🟥⬜⬜⬜"
    else:
        return "🟥🟥🟥🟥🟥"

def preparar_datos(tickers):
    usdt_pairs = []
    
    # Exclusión estricta de stablecoins, monedas fiat sintéticas y megacapitalizaciones masivas
    EXCLUIDOS = [
        'FDUSD', 'USDT', 'USDC', 'DAI', 'TUSD', 'USDP', 'EUR', 'BUSD',
        'DOGE', 'TRX', 'SHIB', 'WLD', 'SOL', 'BTC', 'ETH', 'XRP', 'ADA', 
        'BNB', 'AVAX', 'LINK', 'SUI', 'PEPE', 'NEAR', 'APT', 'ICP'
    ]
    
    for t in tickers:
        symbol = t.get('symbol', '')
        base_name = symbol.replace('USDT', '')
        
        if (symbol.endswith('USDT') and 
            base_name not in EXCLUIDOS and 
            not any(x in symbol for x in ['UP', 'DOWN', 'BULL', 'BEAR']) and 
            symbol not in LISTA_NEGRA):
            try:
                t['lastPrice_f'] = float(t.get('lastPrice', 0))
                t['priceChangePercent_f'] = float(t.get('priceChangePercent', 0))
                t['quoteVolume_f'] = float(t.get('quoteVolume', 0))
                t['highPrice_f'] = float(t.get('highPrice', 0))
                t['lowPrice_f'] = float(t.get('lowPrice', 0))
                
                # Cálculo de métricas estructurales avanzadas (Matriz de Inteligencia Táctica)
                high = t['highPrice_f']
                low = t['lowPrice_f']
                last = t['lastPrice_f']
                
                # Evitar división por cero
                if high > low and low > 0:
                    # Amplitud del rango diario en porcentaje
                    t['rango_amplitud'] = ((high - low) / low) * 100
                    # Posición relativa del precio actual dentro del rango diario (0 = en el mínimo, 1 = en el máximo)
                    t['posicion_en_rango'] = (last - low) / (high - low)
                else:
                    t['rango_amplitud'] = 0.0
                    t['posicion_en_rango'] = 0.5

                usdt_pairs.append(t)
            except (ValueError, TypeError):
                continue

    print(f"Pares USDT estructurales válidos filtrados: {len(usdt_pairs)}")
    
    # 1. Top 7 Ganadoras
    ganadoras = sorted(usdt_pairs, key=lambda x: x['priceChangePercent_f'], reverse=True)[:7]
    
    # 2. Top 7 Acumulación 24h (Volumen general < $1)
    acumulacion_pool_24h = [t for t in usdt_pairs if t['lastPrice_f'] < 1.0]
    acumulacion_24h = sorted(acumulacion_pool_24h, key=lambda x: x['quoteVolume_f'], reverse=True)[:7]
    
    # 3. Top 7 Acumulación Silenciosa / Inteligente (El Resorte Estructural)
    # Criterios de IA: 
    # - Precio nominal menor a $1 USD (alta accesibilidad y margen de subida).
    # - Variación diaria contenida (-1.0% a +2.5%) para evitar activos en pleno escape alcista.
    # - Volumen de liquidez institucional/sana ($800,000 a $45,000,000 USD) para descartar tokens sin movimiento y megagigantes.
    # - Compresión de rango y defensa de posición (el precio se mantiene firme en la mitad superior de su rango diario).
    silenciosa_pool = []
    for t in usdt_pairs:
        if (t['lastPrice_f'] < 1.0 and 
            -1.0 <= t['priceChangePercent_f'] <= 2.5 and 
            800_000 <= t['quoteVolume_f'] <= 45_000_000):
            
            # Puntuación inteligente de compresión y acumulación (Score de Resorte)
            # Premia a los tokens que tienen buena liquidez pero cuya amplitud diaria muestra compresión 
            # y que defienden la parte alta de su micro-rango.
            score_resorte = t['quoteVolume_f'] * (1.0 - min(t['rango_amplitud'] / 20.0, 1.0)) * t['posicion_en_rango']
            t['score_resorte'] = score_resorte
            silenciosa_pool.append(t)

    # Ordenamos el pool utilizando el puntaje inteligente de compresión y volumen estructurado
    acumulacion_silenciosa = sorted(silenciosa_pool, key=lambda x: x['score_resorte'], reverse=True)[:7]
    
    # Si por alta volatilidad del mercado el filtro estricto devuelve menos de 7, respaldamos con un filtro dinámico secundario
    if len(acumulacion_silenciosa) < 7:
        fallback_pool = [
            t for t in usdt_pairs 
            if t['lastPrice_f'] < 1.0 
            and -2.0 <= t['priceChangePercent_f'] <= 3.0
            and t['quoteVolume_f'] >= 500_000
            and t not in acumulacion_silenciosa
        ]
        fallback_ordenado = sorted(fallback_pool, key=lambda x: x['quoteVolume_f'], reverse=True)
        acumulacion_silenciosa.extend(fallback_ordenado[:7 - len(acumulacion_silenciosa)])

    # 4. Top 7 Perdedoras
    perdedoras = sorted(usdt_pairs, key=lambda x: x['priceChangePercent_f'])[:7]
    
    # 5. Tus 5 favoritas
    favoritas_simbolos = ['QI', 'TUT', 'NEIRO', 'LUNC', 'BANK']
    favoritas = []
    for sim in favoritas_simbolos:
        match = next((t for t in usdt_pairs if t['symbol'] == f"{sim}USDT"), None)
        if match:
            favoritas.append(match)
            
    return ganadoras, acumulacion_24h, acumulacion_silenciosa, perdedoras, favoritas

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
        if res.status_code != 200:
            print(f"❌ Error al enviar a Telegram ({res.status_code}): {res.text}")
        return res

def procesar_y_enviar_bloque_unificado(num_bloque, titulo_bloque, icono, lista_items, color_grafico, filename_grafico, tipo_bloque=""):
    if not lista_items:
        print(f"⚠️ Advertencia: No hay items para el bloque {num_bloque}")
        return
    
    print(f"Generando gráfico y unificando mensaje para Bloque {num_bloque}/5: {titulo_bloque}...")
    generar_grafico_tema(lista_items, f"{icono} {titulo_bloque.upper()} • Ranking 24h", color_grafico, filename_grafico)
    
    titulo_seguro = html.escape(titulo_bloque.upper())
    
    caption = f"🧠 <b>CENTRAL DE INTELIGENCIA DE MERCADO ({num_bloque}/5)</b>\n"
    caption += f"{icono} <b>{num_bloque}. {titulo_seguro} (Detalle)</b>\n\n"
    
    for item in lista_items:
        sim = item['symbol'].replace('USDT', '')
        precio = item['lastPrice_f']
        precio_str = formatear_precio(precio)
        cambio = item['priceChangePercent_f']
        high = item['highPrice_f']
        low = item['lowPrice_f']
        
        barra = generar_barra_progreso(cambio, tipo_bloque=tipo_bloque)
        unique_id = int(time.time() * 1000) + random.randint(1, 99999)
        
        url_ia = f"{BASE_URL_NETLIFY}/?coin={sim}&price={precio}&change={cambio}&high={high}&low={low}&v={sim}_{unique_id}"
        url_trade = f"https://www.binance.com/es/trade/{sim}_USDT"
        
        cambio_fmt = f"+{cambio:.1f}%" if cambio >= 0 else f"{cambio:.1f}%"
        
        caption += (
            f"• <b>{sim}</b> | {precio_str} | {barra} | {cambio_fmt}\n"
            f"  └ <a href=\"{html.escape(url_ia)}\">📊 Resumen IA</a> | <a href=\"{html.escape(url_trade)}\">🔶 Tradear</a>\n"
        )
    
    res = enviar_foto_con_detalle_telegram(filename_grafico, caption)
    print(f"Bloque {num_bloque}/5 unificado status: {res.status_code}")
    time.sleep(3)

if __name__ == "__main__":
    print("Iniciando análisis de mercado inteligente (5 bloques)...")
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        raise ValueError("Faltan las credenciales de Telegram.")
        
    datos = obtener_datos_binance()
    if datos:
        ganadoras, acumulacion_24h, acumulacion_silenciosa, perdedoras, favoritas = preparar_datos(datos)
        
        # Tema 1: Ganadoras
        procesar_y_enviar_bloque_unificado(1, "TOP 7 GANADORAS", "🚀", ganadoras, "#00c853", "grafico_ganadoras.png")
        
        # Tema 2: Acumulación 24h
        procesar_y_enviar_bloque_unificado(2, "TOP 7 ACUMULACIÓN 24H (< $1 USD)", "💎", acumulacion_24h, "#ffab00", "grafico_acumulacion_24h.png", tipo_bloque="acumulacion_24h")
        
        # Tema 3: Acumulación Silenciosa (El Resorte Estructural)
        procesar_y_enviar_bloque_unificado(3, "TOP 7 ACUMULACIÓN SILENCIOSA (EL RESORTE)", "🕵️‍♂️", acumulacion_silenciosa, "#00bcd4", "grafico_silenciosa.png", tipo_bloque="silenciosa")
        
        # Tema 4: Perdedoras
        procesar_y_enviar_bloque_unificado(4, "TOP 7 PERDEDORAS", "📉", perdedoras, "#f6465d", "grafico_perdedoras.png")
        
        # Tema 5: Favoritas
        procesar_y_enviar_bloque_unificado(5, "TUS 5 FAVORITAS", "⭐", favoritas, "#3861fb", "grafico_favoritas.png")
        
        print("¡Los 5 bloques de inteligencia estructural avanzada se enviaron con éxito!")
    else:
        raise Exception("No se pudieron obtener datos de la API de Binance.")
