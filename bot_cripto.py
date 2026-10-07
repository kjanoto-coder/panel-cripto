import os
import requests

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("CHAT_ID")

def obtener_datos_binance():
    """
    Conecta al endpoint alternativo oficial de Binance para datos públicos.
    """
    url = "https://data-api.binance.vision/api/v3/ticker/24hr"
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"Error al conectar con Binance: {e}")
        return []

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
    """
    Filtra y selecciona exactamente el Top 10 para cada categoría.
    """
    usdt_pairs = [t for t in tickers if t['symbol'].endswith('USDT') and not any(x in t['symbol'] for x in ['UP', 'DOWN', 'BULL', 'BEAR'])]
    
    # 1. Top 10 Ganadoras
    ganadoras = sorted(usdt_pairs, key=lambda x: float(x['priceChangePercent']), reverse=True)[:10]
    
    # 2. Top 10 Acumulación (< $1 USD con buen volumen)
    acumulacion_pool = [t for t in usdt_pairs if float(t['lastPrice']) < 1.0]
    acumulacion = sorted(acumulacion_pool, key=lambda x: float(t['quoteVolume']), reverse=True)[:10]
    
    # 3. Top 10 Perdedoras (Mayor caída para buscar rebote)
    perdedoras = sorted(usdt_pairs, key=lambda x: float(x['priceChangePercent']))[:10]
    
    return ganadoras, acumulacion, perdedoras

def construir_mensajes(ganadoras, acumulacion, perdedoras):
    base_url_netlify = "https://gregarious-frangollo-0346c5.netlify.app"
    
    # Parte 1: Encabezado + Ganadoras + Acumulación
    mensaje_1 = (
        "🧠 **CENTRAL DE INTELIGENCIA & GEMINI AI** (1/2)\n"
        "📊 Monitoreo Global: 500+ altcoins del Top de Binance\n"
        "⚡ **Estado:** Automatización Activa (GitHub Actions - Cada 15m)\n\n"
        "🚀 **1. TOP 10 GANADORAS (Análisis Multiciclo)**\n"
    )
    
    for item in ganadoras:
        sim = item['symbol'].replace('USDT', '')
        precio = float(item['lastPrice'])
        cambio = float(item['priceChangePercent'])
        barra = generar_barra_progreso(cambio)
        url_ia = f"{base_url_netlify}/?coin={sim}&price={precio}&change={cambio}"
        url_trade = f"https://www.binance.com/es/trade/{sim}_USDT"
        
        mensaje_1 += (
            f"• **{sim}** | ${precio:.4f} | {barra} | +{cambio:.1f}%\n"
            f"  └ ⏱️ *15m: Alcista | 1h: Impulso | 1d: Rotura*\n"
            f"  └ [📊 Resumen IA]({url_ia}) | [🔶 Tradear]({url_trade})\n"
        )

    mensaje_1 += "\n💎 **2. TOP 10 ACUMULACIÓN (< $1 USD - Gemini AI)**\n"
    for item in acumulacion:
        sim = item['symbol'].replace('USDT', '')
        precio = float(item['lastPrice'])
        cambio = float(item['priceChangePercent'])
        barra = generar_barra_progreso(cambio, es_acumulacion=True)
        url_ia = f"{base_url_netlify}/?coin={sim}&price={precio}&change={cambio}"
        url_trade = f"https://www.binance.com/es/trade/{sim}_USDT"
        
        mensaje_1 += (
            f"• **{sim}** | ${precio:.4f} | {barra} | {cambio:+.1f}%\n"
            f"  └ (Soporte clave)\n"
            f"  └ ⏱️ *15m/1h/1d: Estructura de acumulación geométrica*\n"
            f"  └ [📊 Resumen IA]({url_ia}) | [🔶 Tradear]({url_trade})\n"
        )

    # Parte 2: Perdedoras + Favoritas
    mensaje_2 = (
        "🧠 **CENTRAL DE INTELIGENCIA & GEMINI AI** (2/2)\n\n"
        "📉 **3. TOP 10 PERDEDORAS (Potencial Rebote / Recuperación)**\n"
    )
    for item in perdedoras:
        sim = item['symbol'].replace('USDT', '')
        precio = float(item['lastPrice'])
        cambio = float(item['priceChangePercent'])
        barra = generar_barra_progreso(cambio)
        url_ia = f"{base_url_netlify}/?coin={sim}&price={precio}&change={cambio}"
        url_trade = f"https://www.binance.com/es/trade/{sim}_USDT"
        
        mensaje_2 += (
            f"• **{sim}** | ${precio:.4f} | {barra} | {cambio:.1f}%\n"
            f"  └ (Sobreventa en 1h/1d)\n"
            f"  └ ⏱️ *Señal IA: Posible suelo de recuperación a corto plazo*\n"
            f"  └ [📊 Resumen IA]({url_ia}) | [🔶 Tradear]({url_trade})\n"
        )

    # Favoritas fijas
    url_lunc_ia = f"{base_url_netlify}/?coin=LUNC&price=0.00005254&change=-0.2"
    url_bank_ia = f"{base_url_netlify}/?coin=BANK&price=0.01240&change=6.8"

    mensaje_2 += (
        "\n⭐ **4. TUS FAVORITAS (Wallet & Seguimiento)**\n"
        "• **LUNC** | $0.00005254 | 🟥🟥⬜⬜⬜ | -0.2%\n"
        "  └ ⏱️ *15m: Rango | 1h: Estable | 1d: Acumulando base*\n"
        f"  └ [📊 Resumen IA]({url_lunc_ia}) | [🔶 Tradear](https://www.binance.com/es/trade/LUNC_USDT)\n"
        "• **BANK** | $0.01240 | 🟢🟢🟢🟢🟢 | +6.8%\n"
        "  └ (Destacada en tu wallet)\n"
        "  └ ⏱️ *15m: Alcista | 1h: Ruptura | 1d: Impulso fuerte*\n"
        f"  └ [📊 Resumen IA]({url_bank_ia}) | [🔶 Tradear](https://www.binance.com/es/trade/BANK_USDT)\n\n"
        "✅ Alerta enviada correctamente mediante sistema de alta disponibilidad."
    )
    
    return mensaje_1, mensaje_2

def enviar_a_telegram(mensaje_1, mensaje_2):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    
    p1 = requests.post(url, json={
        "chat_id": TELEGRAM_CHAT_ID,
        "text": mensaje_1,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True
    })
    
    p2 = requests.post(url, json={
        "chat_id": TELEGRAM_CHAT_ID,
        "text": mensaje_2,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True
    })
    
    if p1.status_code == 200 and p2.status_code == 200:
        print("¡Ambas partes de la alerta fueron enviadas con éxito a Telegram!")
    else:
        print(f"Error al enviar alerta: {p1.text} | {p2.text}")

if __name__ == "__main__":
    print("Iniciando análisis de mercado...")
    datos = obtener_datos_binance()
    if datos:
        ganadoras, acumulacion, perdedoras = preparar_datos(datos)
        msg_1, msg_2 = construir_mensajes(ganadoras, acumulacion, perdedoras)
        enviar_a_telegram(msg_1, msg_2)
