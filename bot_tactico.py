import os
import requests
import json
import html
from datetime import datetime
import matplotlib.pyplot as plt

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
TOPIC_ID_TACTICO = os.getenv("TOPIC_ID_TACTICO")

def obtener_datos_binance():
    url = "https://data-api.binance.vision/api/v3/ticker/24hr"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            return response.json()
        else:
            print(f"Error HTTP de Binance: {response.status_code}")
    except Exception as e:
        print(f"Excepción al conectar con Binance: {e}")
    return []

def procesar_oportunidades(data):
    filtrados = []
    total_analizadas = 0
    
    for item in data:
        symbol = item['symbol']
        if symbol.endswith('USDT'):
            total_analizadas += 1
            try:
                precio = float(item['lastPrice'])
                cambio = float(item['priceChangePercent'])
                volumen = float(item['quoteVolume'])
                
                if precio < 1.0:
                    filtrados.append({
                        'symbol': symbol,
                        'close': precio,
                        'change': cambio,
                        'volume': volumen
                    })
            except ValueError:
                continue

    top_datos = sorted(filtrados, key=lambda x: x['change'], reverse=True)[:5]

    resultado = []
    for kline in top_datos:
        sim = kline['symbol'].replace('USDT', '')
        precio = kline['close']
        cambio = kline['change']
        
        binance_url = f"https://www.binance.com/es/trade/{sim}_USDT?type=spot"
        netlify_url = f"https://polite-baklava-8ec85f.netlify.app/?coin={sim}&price={precio}&change={cambio}"
        
        resultado.append({
            'simbolo': sim,
            'precio': precio,
            'change': cambio,
            'binance_url': binance_url,
            'netlify_url': netlify_url
        })
        
    return resultado, total_analizadas

def generar_grafico_narrativa(oportunidades):
    ops_ordenadas = sorted(oportunidades, key=lambda x: x['change'])
    
    simbolos = [op['simbolo'] for op in ops_ordenadas]
    cambios = [op['change'] for op in ops_ordenadas]
    
    fig, ax = plt.subplots(figsize=(8, 6), facecolor='#0b132b')
    ax.set_facecolor('#0b132b')
    
    bars = ax.bar(simbolos, cambios, color='#00c853', width=0.5, zorder=3)
    
    ax.grid(True, color='#1e293b', linestyle='-', linewidth=0.8, zorder=1)
    ax.set_axisbelow(True)
    
    for spine in ['top', 'right', 'left', 'bottom']:
        ax.spines[spine].set_visible(False)
        
    ax.tick_params(left=False, labelleft=False, bottom=False)
    ax.tick_params(axis='x', colors='white', labelsize=11)
    
    for bar, sim, cambio in zip(bars, simbolos, cambios):
        yval = bar.get_height()
        xval = bar.get_x() + bar.get_width() / 2.0
        
        ax.text(xval, yval + 4.0, f"+{cambio:.1f}%" if cambio >= 0 else f"{cambio:.1f}%", 
                ha='center', va='bottom', color='#00c853', fontweight='bold', fontsize=11)
        
        ax.plot(xval, yval + 1.5, marker='o', markersize=22, markerfacecolor='#0f172a', markeredgecolor='#00c853', markeredgewidth=1.5, zorder=4)
        ax.text(xval, yval + 1.5, sim, ha='center', va='center', color='white', fontsize=8, fontweight='bold', zorder=5)

    fecha_str = datetime.now().strftime('%Y-%m-%d')
    plt.title("NARRATIVA DEL DÍA\nTOP 5 ALTCOINS SUB-$1 USD\n", loc='left', color='#ffab00', fontsize=15, fontweight='bold', pad=15)
    ax.text(0.0, 1.02, f"Fecha: {fecha_str}", transform=ax.transAxes, color='#94a3b8', fontsize=9)
    ax.text(0.0, -0.12, "Cazador Táctico • Ranking de Momentum 24h en Binance Spot", transform=ax.transAxes, color='#64748b', fontsize=8)
    
    plt.tight_layout()
    image_path = 'narrativa_dia.png'
    plt.savefig(image_path, dpi=300, facecolor=fig.get_facecolor(), edgecolor='none')
    plt.close()
    return image_path

def enviar_telegram_con_foto(image_path, mensaje):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"
    with open(image_path, 'rb') as photo:
        payload = {
            "chat_id": CHAT_ID,
            "caption": mensaje,
            "parse_mode": "HTML"
        }
        if TOPIC_ID_TACTICO:
            payload["message_thread_id"] = TOPIC_ID_TACTICO
        
        files = {"photo": photo}
        response = requests.post(url, data=payload, files=files)
        print("Respuesta de Telegram (Foto):", response.text)
        return response.json()

def main():
    datos = obtener_datos_binance()
    if not datos:
        print("Error al obtener datos de Binance.")
        return

    oportunidades, total_analizadas = procesar_oportunidades(datos)
    if not oportunidades:
        print("No se encontraron oportunidades con los filtros establecidos.")
        return
    
    imagen_grafico = generar_grafico_narrativa(oportunidades)
    
    # Texto optimizado dentro del límite de caracteres de Telegram para captions
    mensaje = f"<b>ANALIZADAS:</b> {total_analizadas} | <b>TOP 5 SUB-$1</b>\n\n"
    mensaje += "🚀 <b>OPORTUNIDADES TÁCTICAS</b>\n"
    
    for op in oportunidades:
        precio_str = f"${op['precio']:.4f}" if op['precio'] < 1 else f"${op['precio']:.2f}"
        cambio_str = f"+{op['change']:.1f}%" if op['change'] >= 0 else f"{op['change']:.1f}%"
        
        safe_netlify = html.escape(op['netlify_url'])
        safe_binance = html.escape(op['binance_url'])
        
        link_ia = f'<a href="{safe_netlify}">Resumen IA</a>'
        link_trade = f'<a href="{safe_binance}">Tradear</a>'
        
        mensaje += f"\n• <b>{op['simbolo']}</b> ({cambio_str}) — {precio_str} | 🟢🟢🟢\n"
        mensaje += f"  └ 📊 {link_ia} | 🔶 {link_trade}\n"

    enviar_telegram_con_foto(imagen_grafico, mensaje)

if __name__ == "__main__":
    main()
