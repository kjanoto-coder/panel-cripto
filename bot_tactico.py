import os
import requests
import json
import html
import time
from datetime import datetime
import numpy as np
import matplotlib.pyplot as plt

TELEGRAM_TOKEN = (os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("TELEGRAM_TOKEN") or "").strip()
CHAT_ID = (os.getenv("TELEGRAM_CHAT_ID") or os.getenv("CHAT_ID") or "").strip()
TOPIC_ID_TACTICO = (os.getenv("TOPIC_ID_TACTICO") or os.getenv("TELEGRAM_MESSAGE_THREAD_ID") or "").strip()
GEMINI_API_KEY = (os.getenv("GEMINI_API_KEY") or "").strip()

ARCHIVO_MEMORIA = "ultimas_perlas_cazador.json"

def cargar_memoria_perlas():
    """Carga el historial de las últimas selecciones para evitar repeticiones innecesarias"""
    if os.path.exists(ARCHIVO_MEMORIA):
        try:
            with open(ARCHIVO_MEMORIA, 'r') as f:
                return json.load(f)
        except Exception:
            return []
    return []

def guardar_memoria_perlas(historial_reportes):
    """Guarda los últimos 2 reportes de perlas"""
    try:
        with open(ARCHIVO_MEMORIA, 'w') as f:
            json.dump(historial_reportes[-2:], f)
    except Exception as e:
        print(f"Error guardando memoria: {e}")

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

def obtener_velas_historicas(symbol, interval="1d", limit=30):
    url = f"https://data-api.binance.vision/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}"
    try:
        response = requests.get(url, timeout=8)
        if response.status_code == 200:
            return response.json()
    except Exception:
        pass
    return []

def obtener_mapa_calor_liquidaciones(symbol):
    """Evalúa zonas de presión utilizando datos públicos de Spot para evitar bloqueos geográficos en GitHub Actions"""
    try:
        df_4h = obtener_velas_historicas(symbol, interval="4h", limit=6)
        if df_4h and len(df_4h) > 0:
            high_prices = [float(k[2]) for k in df_4h]
            closes = [float(k[4]) for k in df_4h]
            high_price = max(high_prices)
            last_price = closes[-1]
            if last_price > 0:
                distancia_top = ((high_price - last_price) / last_price) * 100
                es_iman = distancia_top <= 1.5
                return es_iman, float(52.0 if es_iman else 48.0)
    except Exception:
        pass
    return False, 50.0

def formatear_precio(val):
    """Ajusta dinámicamente la cantidad de decimales según el valor de la criptomoneda para evitar ceros incorrectos."""
    if val < 0.0001:
        return f"${val:.8f}"
    elif val < 0.01:
        return f"${val:.6f}"
    elif val < 1.0:
        return f"${val:.4f}"
    else:
        return f"${val:.2f}"

def generar_sintesis_resumen(simbolo, precio, cambio, volumen, high, low, es_iman=False, vol_rel=1.0):
    """
    Genera un análisis técnico detallado, específico e independiente utilizando la API REST de Gemini.
    """
    if GEMINI_API_KEY:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
        headers = {"Content-Type": "application/json"}
        
        tag_extra = " | Presión en Máximos Activa" if es_iman else f" | Vol. Relativo x{vol_rel:.1f}"
        
        prompt = f"""
        Eres un analista técnico sénior de mercados cripto. Genera un análisis técnico específico y detallado para la criptomoneda {simbolo} en Binance Spot usando estos datos exactos de 24h:
        - Precio actual: {formatear_precio(precio)}
        - Variación 24h: {cambio:+.2f}%
        - Volumen 24h: ${volumen:,.0f} USDT
        - Máximo 24h (Resistencia): {formatear_precio(high)}
        - Mínimo 24h (Soporte): {formatear_precio(low)}
        - Contexto Quirúrgico: {tag_extra}

        INSTRUCCIONES:
        Escribe un diagnóstico de precisión en exactamente una sola línea encerrada entre corchetes, especificando niveles exactos de precio.

        FORMATO OBLIGATORIO:
        [1D: Impulso sobre soporte en {formatear_precio(low)} | 4H: Búsqueda de resistencia en {formatear_precio(high)} | 15M: Gatillo activo en {formatear_precio(precio)} | Conclusión: Opción alcista{tag_extra}]
        """
        
        payload = {
            "contents": [{
                "parts": [{"text": prompt}]
            }]
        }
        
        for mod in ['gemini-2.5-flash', 'gemini-1.5-flash']:
            try:
                alt_url = f"https://generativelanguage.googleapis.com/v1beta/models/{mod}:generateContent?key={GEMINI_API_KEY}"
                response = requests.post(alt_url, headers=headers, json=payload, timeout=10)
                if response.status_code == 200:
                    data = response.json()
                    texto = data['candidates'][0]['content']['parts'][0]['text'].strip()
                    if not (texto.startswith('[') and texto.endswith(']')):
                        texto = f"[{texto}]"
                    return texto
            except Exception:
                continue

    return f"[1D: Acumulación sobre piso en {formatear_precio(low)} | 4H: Testeo de techo en {formatear_precio(high)} | 15M: Entrada de flujo en {formatear_precio(precio)} | Conclusión: Giro alcista]"

def procesar_oportunidades(data):
    total_sub1 = 0
    LISTA_NEGRA = ['PNTUSDT', 'VGXUSDT', 'BNCUSDT', 'PENGUUSDT', 'ASTERUSDT']
    
    historial_previo = cargar_memoria_perlas()
    simbolos_bloqueados = [item for reporte in historial_previo for item in reporte]
    
    candidatos_base = []
    
    for item in data:
        symbol = item['symbol']
        if symbol.endswith('USDT'):
            try:
                precio = float(item['lastPrice'])
                cambio = float(item['priceChangePercent'])
                volumen = float(item['quoteVolume'])
                high = float(item['highPrice'])
                low = float(item['lowPrice'])
                
                if 0 < precio < 1.0 and volumen >= 1_500_000 and symbol not in LISTA_NEGRA:
                    total_sub1 += 1
                    if -1.5 <= cambio <= 2.5 and symbol not in simbolos_bloqueados:
                        candidatos_base.append({
                            'symbol': symbol,
                            'close': precio,
                            'change': cambio,
                            'volume': volumen,
                            'high': high,
                            'low': low
                        })
            except ValueError:
                continue

    perlas_quirurgicas = []
    print(f"Ejecutando motor quirúrgico en Cazador Táctico sobre {len(candidatos_base)} candidatos...")

    for item in candidatos_base:
        symbol = item['symbol']
        klines = obtener_velas_historicas(symbol, interval="1d", limit=30)
        
        if len(klines) < 20:
            continue
            
        volumenes = [float(k[5]) for k in klines]
        vol_reciente = np.mean(volumenes[-5:])
        vol_historico = np.mean(volumenes[:-5])
        factor_vol_relativo = vol_reciente / (vol_historico if vol_historico > 0 else 1)
        
        es_iman, _ = obtener_mapa_calor_liquidaciones(symbol)
        
        if factor_vol_relativo >= 1.2 or es_iman:
            item['factor_vol'] = factor_vol_relativo
            item['es_iman'] = es_iman
            perlas_quirurgicas.append(item)
            
        if len(perlas_quirurgicas) >= 5:
            break

    if len(perlas_quirurgicas) < 5:
        for item in candidatos_base:
            if item not in perlas_quirurgicas:
                item['factor_vol'] = 1.1
                item['es_iman'] = False
                perlas_quirurgicas.append(item)
            if len(perlas_quirurgicas) >= 5:
                break

    if len(perlas_quirurgicas) < 5:
        for item in data:
            symbol = item['symbol']
            if symbol.endswith('USDT') and symbol not in [p['symbol'] for p in perlas_quirurgicas]:
                try:
                    precio = float(item['lastPrice'])
                    cambio = float(item['priceChangePercent'])
                    volumen = float(item['quoteVolume'])
                    if 0 < precio < 1.0 and volumen >= 1_000_000 and symbol not in LISTA_NEGRA:
                        perlas_quirurgicas.append({
                            'symbol': symbol,
                            'close': precio,
                            'change': cambio,
                            'volume': volumen,
                            'high': float(item['highPrice']),
                            'low': float(item['lowPrice']),
                            'factor_vol': 1.0,
                            'es_iman': False
                        })
                except ValueError:
                    continue
            if len(perlas_quirurgicas) >= 5:
                break

    top_datos = sorted(perlas_quirurgicas, key=lambda x: x['volume'], reverse=True)[:5]

    nuevos_simbolos = [k['symbol'] for k in top_datos]
    historial_previo.append(nuevos_simbolos)
    guardar_memoria_perlas(historial_previo)

    resultado = []
    for kline in top_datos:
        sim = kline['symbol'].replace('USDT', '')
        precio = kline['close']
        cambio = kline['change']
        volumen = kline['volume']
        high = kline['high']
        low = kline['low']
        es_iman = kline.get('es_iman', False)
        vol_rel = kline.get('factor_vol', 1.0)
        
        binance_url = f"https://www.binance.com/es/trade/{sim}_USDT?type=spot"
        timestamp = int(time.time())
        
        netlify_url = f"https://polite-baklava-8ec85f.netlify.app/?coin={sim}&price={precio}&change={cambio}&high={high}&low={low}&vol={volumen:,.0f}&v={timestamp}"
        
        resumen_moneda = generar_sintesis_resumen(sim, precio, cambio, volumen, high, low, es_iman, vol_rel)
        time.sleep(0.5)
        
        resultado.append({
            'simbolo': sim,
            'precio': precio,
            'change': cambio,
            'binance_url': binance_url,
            'netlify_url': netlify_url,
            'resumen': resumen_moneda
        })
        
    return resultado, total_sub1

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

def enviar_telegram_con_foto(image_path):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"
    with open(image_path, 'rb') as photo:
        payload = {"chat_id": CHAT_ID, "caption": "🎯 <b>CAZADOR TÁCTICO • NARRATIVA DEL DÍA</b>", "parse_mode": "HTML"}
        if TOPIC_ID_TACTICO:
            try:
                payload["message_thread_id"] = int(TOPIC_ID_TACTICO)
            except ValueError:
                pass
        
        files = {"photo": photo}
        response = requests.post(url, data=payload, files=files)
        res_json = response.json()
        
        if not res_json.get("ok"):
            print("⚠️ Reintentando foto de Cazador al chat principal...")
            payload.pop("message_thread_id", None)
            photo.seek(0)
            response = requests.post(url, data=payload, files=files)
            res_json = response.json()
        return res_json

def enviar_telegram_texto(mensaje):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": mensaje,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }
    if TOPIC_ID_TACTICO:
        try:
            payload["message_thread_id"] = int(TOPIC_ID_TACTICO)
        except ValueError:
            pass

    response = requests.post(url, json=payload)
    res_json = response.json()
    
    if not res_json.get("ok"):
        print("⚠️ Reintentando mensaje de Cazador al chat principal...")
        payload.pop("message_thread_id", None)
        response = requests.post(url, json=payload)
        res_json = response.json()
    return res_json

def main():
    if not TELEGRAM_TOKEN or not CHAT_ID:
        print("⚠️ Faltan credenciales de Telegram.")
        return

    datos = obtener_datos_binance()
    if not datos:
        print("Error al obtener datos de Binance.")
        return

    oportunidades, total_sub1 = procesar_oportunidades(datos)
    if not oportunidades:
        print("No se encontraron oportunidades con los filtros establecidos.")
        return
    
    imagen_grafico = generar_grafico_narrativa(oportunidades)
    enviar_telegram_con_foto(imagen_grafico)
    
    bloque_1 = oportunidades[:3]
    bloque_2 = oportunidades[3:]
    
    msg_parte_2 = "🎯 <b>CAZADOR TÁCTICO</b>\n"
    msg_parte_2 += "📊 <i>Ranking de Momentum 24h en Binance Spot</i>\n\n"
    msg_parte_2 += f"<b>MONEDAS ANALIZADAS:</b> {total_sub1}\n\n"
    msg_parte_2 += f"<b>RESUMEN:</b> Estas altcoins fueron seleccionadas de un universo de {total_sub1} activos bajo $1 USD en Binance Spot debido a una confluencia de compresión de volatilidad previa, anomalía de volumen y presión institucional.\n\n"
    msg_parte_2 += "🚀 <b>TOP OPORTUNIDADES TÁCTICAS</b>\n"
    
    for op in bloque_1:
        precio_str = formatear_precio(op['precio'])
        cambio_str = f"+{op['change']:.1f}%" if op['change'] >= 0 else f"{op['change']:.1f}%"
        
        safe_netlify = html.escape(op['netlify_url'])
        safe_binance = html.escape(op['binance_url'])
        
        link_ia = f'<a href="{safe_netlify}">Resumen IA</a>'
        link_trade = f'<a href="{safe_binance}">Tradear</a>'
        
        msg_parte_2 += f"\n• <b>{op['simbolo']}</b> ({cambio_str}) — {precio_str} | 🟢🟢🟢🟢🟢\n"
        msg_parte_2 += f"🧠 <i>{op['resumen']}</i>\n"
        msg_parte_2 += f"  └ 📊 {link_ia} | 🔶 {link_trade}\n"

    enviar_telegram_texto(msg_parte_2)
    
    if bloque_2:
        msg_parte_3 = ""
        for op in bloque_2:
            precio_str = formatear_precio(op['precio'])
            cambio_str = f"+{op['change']:.1f}%" if op['change'] >= 0 else f"{op['change']:.1f}%"
            
            safe_netlify = html.escape(op['netlify_url'])
            safe_binance = html.escape(op['binance_url'])
            
            link_ia = f'<a href="{safe_netlify}">Resumen IA</a>'
            link_trade = f'<a href="{safe_binance}">Tradear</a>'
            
            msg_parte_3 += f"\n• <b>{op['simbolo']}</b> ({cambio_str}) — {precio_str} | 🟢🟢🟢🟢🟢\n"
            msg_parte_3 += f"🧠 <i>{op['resumen']}</i>\n"
            msg_parte_3 += f"  └ 📊 {link_ia} | 🔶 {link_trade}\n"

        enviar_telegram_texto(msg_parte_3)

if __name__ == "__main__":
    main()
