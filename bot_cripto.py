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

# Lista negra para descartar tokens deslistados
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

def generar_barra_progreso(cambio, es_acumulacion=False):
    if es_acumulacion:
        return "🟨🟨🟨⬜⬜"
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
    usdt_pairs = [
        t for t in tickers 
        if t['symbol'].endswith('USDT') 
        and not any(x in t['symbol'] for x in ['UP', 'DOWN', 'BULL', 'BEAR'])
        and t['symbol'] not in LISTA_NEGRA
    ]
    print(f"Pares USDT válidos filtrados: {len(usdt_pairs)}")
    
    # Top 7 Ganadoras
    ganadoras = sorted(usdt_pairs, key=lambda x: float(x['priceChangePercent']), reverse=True)[:7]
    
    # Top 7 Acumulación (< $1 USD)
    acumulacion_pool = [t for t in usdt_pairs if float(t['lastPrice']) < 1.0]
    acumulacion = sorted(acumulacion_pool, key=lambda x: float(x['quoteVolume']), reverse=True)[:7]
    
    # Top 7 Perdedoras
    perdedoras = sorted(usdt_pairs, key=lambda x: float(x['priceChangePercent']))[:7]
    
    # Tus 5 favoritas
    favoritas_simbolos = ['QI', 'TUT', 'NEIRO', 'LUNC', 'BANK']
    favoritas = []
    for sim in favoritas_simbolos:
        match = next((t for t in usdt_pairs if t['symbol'] == f"{sim}USDT"), None)
        if match:
            favoritas.append(match)
            
    return ganadoras, acumulacion, perdedoras, favoritas

def generar_grafico_tema(lista_items, titulo_grafico, color_barra, filename):
    items_ordenados = sorted(lista_items, key=lambda x: float(x['priceChangePercent']))
    
    simbolos = [item['symbol'].replace('USDT', '') for item in items_ordenados]
    cambios = [float(item['priceChangePercent']) for item in items_ordenados]
    
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

def enviar_foto_telegram(image_path, caption=""):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
    with open(image_path, 'rb') as photo:
        payload = {"chat_id": TELEGRAM_CHAT_ID, "caption": caption, "parse_mode": "HTML"}
        if TELEGRAM_TOPIC_ID:
            payload["message_thread_id"] = TELEGRAM_TOPIC_ID
        files = {"photo": photo}
        res = requests.post(url, data=payload, files=files)
        return res

def enviar_texto_telegram(texto):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": texto,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }
    if TELEGRAM_TOPIC_ID:
        payload["message_thread_id"] = TELEGRAM_TOPIC_ID
    res = requests.post(url, json=payload)
    return res

def procesar_y_enviar_bloque(num_bloque, titulo_bloque, icono, lista_items, color_grafico, es_acumulacion=False):
    if not lista_items:
        print(f"Advertencia: No hay items para el bloque {num_bloque}")
        return
    
    filename = f"grafico_tema_{num_bloque}.png"
    generar_grafico_tema(lista_items, f"{icono} {titulo_bloque.upper()} • Ranking 24h", color_grafico, filename)
    
    caption = f"🧠 <b>CENTRAL DE INTELIGENCIA DE MERCADO ({num_bloque}/4)</b>\n{icono} <b>{num_bloque}. {titulo_bloque.upper()}</b>"
    enviar_foto_telegram(filename, caption)
    
    msg = f"{icono} <b>{num_bloque}. {titulo_bloque.upper()} (Detalle)</b>\n\n"
    for item in lista_items:
        sim = item['symbol'].replace('USDT', '')
        precio = float(item['lastPrice'])
        precio_str = formatear_precio(precio)
        cambio = float(item['priceChangePercent'])
        high = float(item['highPrice'])
        low = float(item['lowPrice'])
        
        barra = generar_barra_progreso(cambio, es_acumulacion=es_acumulacion)
        unique_id = int(time.time() * 1000) + random.randint(1, 99999)
        
        url_ia = f"{BASE_URL_NETLIFY}/?coin={sim}&price={precio}&change={cambio}&high={high}&low={low}&v={sim}_{unique_id}"
        url_trade = f"https://www.binance.com/es/trade/{sim}_USDT"
        
        cambio_fmt = f"+{cambio:.1f}%" if cambio >= 0 else f"{cambio:.1f}%"
        
        msg += (
            f"• <b>{sim}</b> | {precio_str} | {barra} | {cambio_fmt}\n"
            f"  └ <a href=\"{html.escape(url_ia)}\">📊 Resumen IA</a> | <a href=\"{html.escape(url_trade)}\">🔶 Tradear</a>\n"
        )
    
    enviar_texto_telegram(msg)
    time.sleep(1.2)

if __name__ == "__main__":
    print("Iniciando análisis de mercado...")
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        raise ValueError("Faltan las credenciales de Telegram.")
        
    datos = obtener_datos_binance()
    if datos:
        ganadoras, acumulacion, perdedoras, favoritas = preparar_datos(datos)
        
        # Bloque 1: Top 7 Ganadoras
        procesar_y_enviar_bloque(1, "TOP 7 GANADORAS", "🚀", ganadoras, "#00c853")
        
        # Bloque 2: Top 7 Acumulación (< $1 USD)
        procesar_y_enviar_bloque(2, "TOP 7 ACUMULACIÓN (< $1 USD)", "💎", acumulacion, "#ffab00", es_acumulacion=True)
        
        # Bloque 3: Top 7 Perdedoras
        procesar_y_enviar_bloque(3, "TOP 7 PERDEDORAS", "📉", perdedoras, "#f6465d")
        
        # Bloque 4: Tus 5 Favoritas
        procesar_y_enviar_bloque(4, "TUS 5 FAVORITAS", "⭐", favoritas, "#3861fb")
        
        print("¡Los 4 bloques con sus infografías completas han sido enviados exitosamente!")
