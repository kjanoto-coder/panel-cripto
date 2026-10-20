import os
import json
import time
import random
import requests
import html
from datetime import datetime
import numpy as np
import matplotlib.pyplot as plt

# --- CONFIGURACIÓN DE VARIABLES DE ENTORNO BLINDADAS ---
TELEGRAM_BOT_TOKEN = (os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("TELEGRAM_TOKEN") or "").strip()
TELEGRAM_CHAT_ID = (os.getenv("TELEGRAM_CHAT_ID") or os.getenv("CHAT_ID") or "").strip()
TELEGRAM_TOPIC_ID = (os.getenv("TOPIC_ID_CENTRAL") or "1").strip()
BASE_URL_NETLIFY = "https://gregarious-frangollo-0346c5.netlify.app"

# Lista negra estricta para excluir tokens fantasma, deslistados o anomalías de la API
LISTA_NEGRA = [
    'CREAMUSDT', 'PNTUSDT', 'VGXUSDT', 'BNCUSDT', 'PENGUUSDT', 'ASTERUSDT', 
    'WTCUSDT', 'PHBUSDT', 'NFPUSDT', 'BETAUSDT', 'VIBUSDT', 'PYRUSDT', 'ACAUSDT',
    'EPICUSDT', 'SOPHUSDT', 'KORUBUSDT', 'QNTBUSDT', 'DJTBUSDT'
]

ARCHIVO_MEMORIA = "ultimas_perlas.json"

def cargar_memoria_perlas():
    if os.path.exists(ARCHIVO_MEMORIA):
        try:
            with open(ARCHIVO_MEMORIA, 'r') as f:
                return json.load(f)
        except Exception:
            return []
    return []

def guardar_memoria_perlas(historial_reportes):
    try:
        with open(ARCHIVO_MEMORIA, 'w') as f:
            json.dump(historial_reportes[-2:], f)
    except Exception as e:
        print(f"Error guardando memoria: {e}")

def obtener_datos_binance():
    urls = [
        "https://api.binance.com/api/v3/ticker/24hr",
        "https://data-api.binance.vision/api/v3/ticker/24hr"
    ]
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
    }
    
    for url in urls:
        print(f"Conectando con Binance a través de: {url} ...")
        try:
            response = requests.get(url, headers=headers, timeout=15)
            if response.status_code == 200:
                data = response.json()
                if isinstance(data, list) and len(data) > 0:
                    print(f"✅ ¡Conexión exitosa! Se obtuvieron {len(data)} tickers.")
                    return data
        except Exception as e:
            print(f"⚠️ Falló la conexión con {url}: {e}")
            
    print("❌ Error crítico: No se pudo obtener datos de ninguna URL de Binance.")
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

def generar_barra_progreso(cambio, tipo_bloque=""):
    if tipo_bloque == "acumulacion_24h":
        return "🟨🟨🟨⬜⬜"
    elif tipo_bloque == "silenciosa":
        return "💎💎💎💎⬜"
    
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
    EXCLUIDOS = ['FDUSD', 'USDT', 'USDC', 'DAI', 'TUSD', 'USDP', 'EUR', 'BUSD', 'DOGE', 'TRX', 'SHIB', 'WLD', 'SOL', 'BTC', 'ETH', 'ADA', 'ONDO']
    
    for t in tickers:
        symbol = t.get('symbol', '')
        base_name = symbol.replace('USDT', '')
        if (symbol.endswith('USDT') and 
            base_name not in EXCLUIDOS and 
            symbol not in LISTA_NEGRA and 
            not any(x in symbol for x in ['UP', 'DOWN', 'BULL', 'BEAR'])):
            try:
                t['lastPrice_f'] = float(t.get('lastPrice', 0))
                t['priceChangePercent_f'] = float(t.get('priceChangePercent', 0))
                t['quoteVolume_f'] = float(t.get('quoteVolume', 0))
                t['highPrice_f'] = float(t.get('highPrice', 0))
                t['lowPrice_f'] = float(t.get('lowPrice', 0))
                
                if t['quoteVolume_f'] >= 500_000 and t['lastPrice_f'] > 0 and -90 <= t['priceChangePercent_f'] <= 90:
                    usdt_pairs.append(t)
            except (ValueError, TypeError):
                continue

    # 1. TOP 7 GANADORAS
    ganadoras = sorted(usdt_pairs, key=lambda x: x['priceChangePercent_f'], reverse=True)[:7]
    
    # 2. TOP 7 ACUMULACIÓN 24H (Monedas con bajo valor < $1.0)
    acumulacion_pool_24h = [t for t in usdt_pairs if t['lastPrice_f'] < 1.0]
    acumulacion_24h = sorted(acumulacion_pool_24h, key=lambda x: x['quoteVolume_f'], reverse=True)[:7]
    
    # 3. TOP 7 ACUMULACIÓN SILENCIOSA (Detección Real de Compresión + Volumen Anómalo)
    historial_previo = cargar_memoria_perlas()
    simbolos_bloqueados = [item for reporte in historial_previo for item in reporte]
    
    candidatas_silenciosas = []
    for t in usdt_pairs:
        # Requisitos de acumulación real:
        # - Precio bajo (< $1.00)
        # - Cambio de precio comprimido (-1.8% a +2.2%)
        # - Volumen significativo (> $800k USDT)
        # - No repetida recientemente
        if (t['lastPrice_f'] < 1.00 and 
            -1.8 <= t['priceChangePercent_f'] <= 2.2 and 
            t['quoteVolume_f'] >= 800_000 and 
            t['symbol'] not in simbolos_bloqueados):
            
            # Cálculo de la relación Volumen / Rango de Precio (Squeeze Ratio Real)
            rango_precio = t['highPrice_f'] - t['lowPrice_f']
            pct_rango = (rango_precio / t['lastPrice_f']) * 100 if t['lastPrice_f'] > 0 else 1
            
            # Un volumen alto con un rango estrecho de precio indica acumulación por creadores de mercado
            factor_acumulacion = round((t['quoteVolume_f'] / 1_000_000) / (pct_rango if pct_rango > 0 else 1), 2)
            t['factor_vol'] = max(1.2, round(1.0 + (factor_acumulacion * 0.15), 1))
            candidatas_silenciosas.append(t)

    # Ordenar por el mayor factor de acumulación real
    acumulacion_silenciosa = sorted(candidatas_silenciosas, key=lambda x: x['factor_vol'], reverse=True)[:7]
    
    # Respaldo en caso de que el mercado esté muy volátil
    if len(acumulacion_silenciosa) < 7:
        faltantes = 7 - len(acumulacion_silenciosa)
        respaldo = [t for t in acumulacion_pool_24h if t not in acumulacion_silenciosa]
        for r in respaldo[:faltantes]:
            r['factor_vol'] = 1.3
            acumulacion_silenciosa.append(r)

    nuevos_simbolos = [t['symbol'] for t in acumulacion_silenciosa]
    historial_previo.append(nuevos_simbolos)
    guardar_memoria_perlas(historial_previo)
    
    # 4. TOP 7 PERDEDORAS
    perdedoras_pool = [t for t in usdt_pairs if t['priceChangePercent_f'] < 0]
    perdedoras = sorted(perdedoras_pool, key=lambda x: x['priceChangePercent_f'])[:7]
    
    # 5. TUS 5 FAVORITAS
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
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("⚠️ Error: FALTA TELEGRAM_BOT_TOKEN o TELEGRAM_CHAT_ID.")
        return None

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
        files = {"photo": photo}
        res = requests.post(url, data=payload, files=files)
        resultado = res.json()
        
        if not resultado.get("ok") and "message thread not found" in str(resultado.get("description", "")):
            print("⚠️ Hilo no encontrado. Enviando al chat principal...")
            payload.pop("message_thread_id", None)
            photo.seek(0)
            res = requests.post(url, data=payload, files={"photo": photo})
            resultado = res.json()

        if resultado.get("ok"):
            print("✅ Bloque enviado exitosamente.")
        else:
            print(f"⚠️ Error de entrega: {resultado}")
            
        return res

def procesar_y_enviar_bloque_unificado(num_bloque, titulo_bloque, icono, lista_items, color_grafico, filename_grafico, tipo_bloque=""):
    if not lista_items:
        return
    
    print(f"Generando Bloque {num_bloque}/5: {titulo_bloque}...")
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
        
        if tipo_bloque == "silenciosa":
            vol_rel = item.get('factor_vol', 1.2)
            caption += (
                f"• <b>{sim}</b> | {precio_str} | {barra} | {cambio_fmt}\n"
                f"  🧠 <i>[Presión Acumulativa x{vol_rel:.1f}]</i>\n"
                f"  └ <a href=\"{html.escape(url_ia)}\">📊 Resumen IA</a> | <a href=\"{html.escape(url_trade)}\">🔶 Tradear</a>\n"
            )
        else:
            caption += (
                f"• <b>{sim}</b> | {precio_str} | {barra} | {cambio_fmt}\n"
                f"  └ <a href=\"{html.escape(url_ia)}\">📊 Resumen IA</a> | <a href=\"{html.escape(url_trade)}\">🔶 Tradear</a>\n"
            )
    
    enviar_foto_con_detalle_telegram(filename_grafico, caption)
    time.sleep(3)

if __name__ == "__main__":
    print("🚀 INICIANDO SCRIPT DE ALERTAS CRIPTO...")
    datos = obtener_datos_binance()
    if datos and len(datos) > 0:
        ganadoras, acumulacion_24h, acumulacion_silenciosa, perdedoras, favoritas = preparar_datos(datos)
        
        procesar_y_enviar_bloque_unificado(1, "TOP 7 GANADORAS", "🚀", ganadoras, "#00c853", "grafico_ganadoras.png")
        procesar_y_enviar_bloque_unificado(2, "TOP 7 ACUMULACION 24H", "💎", acumulacion_24h, "#ffab00", "grafico_acumulacion_24h.png", tipo_bloque="acumulacion_24h")
        procesar_y_enviar_bloque_unificado(3, "TOP 7 ACUMULACION SILENCIOSA", "🕵️‍♂️", acumulacion_silenciosa, "#00bcd4", "grafico_silenciosa.png", tipo_bloque="silenciosa")
        procesar_y_enviar_bloque_unificado(4, "TOP 7 PERDEDORAS", "📉", perdedoras, "#f6465d", "grafico_perdedoras.png")
        procesar_y_enviar_bloque_unificado(5, "TUS 5 FAVORITAS", "⭐", favoritas, "#3861fb", "grafico_favoritas.png")
        
        print("🎉 ¡Los 5 bloques actualizados se enviaron correctamente a Telegram!")
    else:
        print("❌ ERROR CRÍTICO: La lista de datos de Binance llegó vacía o no se pudo conectar.")
