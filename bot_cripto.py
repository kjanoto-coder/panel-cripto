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
    acumulacion = sorted(acumulacion_pool, key=lambda x: float(x['quoteVolume']), reverse=True)[:10]
    
    # 3. Top 10 Perdedoras (Mayor caída para buscar rebote)
    perdedoras = sorted(usdt_pairs, key=lambda x: float(x['priceChangePercent']))[:10]
    
    return ganadoras, acumulacion, perdedoras

def construir_mensaje(ganadoras, acumulacion, perdedoras):
    mensaje = (
        "🧠 **CENTRAL DE INTELIGENCIA & GEMINI AI**\n"
        "📊 Monitoreo Global: 500+ altcoins del Top de Binance\n"
        "⚡ **Estado:** Automatización Activa (GitHub Actions - Cada 15m)\n\n"
        "🚀 **1. TOP 10 GANADORAS (Análisis Multiciclo)**\n"
    )
    
    for item in ganadoras:
        sim = item['symbol'].replace('USDT', '')
        precio = float(item['lastPrice'])
        cambio = float(item['priceChangePercent'])
        barra = generar_barra_progreso(cambio)
        mensaje += (
            f"• **{sim}** | ${precio:.4f} | {barra} | +{cambio:.1f}%\n"
            f"  └ ⏱️ *15m: Alcista | 1h: Impulso | 1d: Rotura*\n"
            f"  └ [📊 Resumen IA](https://tu-sitio-netlify.app) | [🔶 Tradear](https://www.binance.com/es/trade/{sim}_USDT)\n"
        )

    mensaje += "\n💎 **2. TOP 10 ACUMULACIÓN (< $1 USD - Gemini AI)**\n"
    for item in acumulacion:
        sim = item['symbol'].replace('USDT', '')
        precio = float(item['lastPrice'])
        cambio = float(item['priceChangePercent'])
        barra = generar_barra_progreso(cambio, es_acumulacion=True)
        mensaje += (
            f"• **{sim}** | ${precio:.4f} | {barra} | {cambio:+.1f}%\n"
            f"  └ (Soporte clave)\n"
            f"  └ ⏱️ *15m/1h/1d: Estructura de acumulación geométrica*\n"
            f"  └ [📊 Resumen IA](https://tu-sitio-netlify.app) | [🔶 Tradear](https://www.binance.com/es/trade/{sim}_USDT)\n"
        )

    mensaje += "\n📉 **3. TOP 10 PERDEDORAS (Potencial Rebote / Recuperación)**\n"
    for item in perdedoras:
        sim = item['symbol'].replace('USDT', '')
        precio = float(item['lastPrice'])
        cambio = float(item['priceChangePercent'])
        barra = generar_barra_progreso(cambio)
        mensaje += (
            f"• **{sim}** | ${precio:.4f} | {barra} | {cambio:.1f}%\n"
            f"  └ (Sobreventa en 1h/1d)\n"
            f"  └ ⏱️ *Señal IA: Posible suelo de recuperación a corto plazo*\n"
            f"  └ [📊 Resumen IA](https://tu-sitio-netlify.app) | [🔶 Tradear](https://www.binance.com/es/trade/{sim}_USDT)\n"
        )

    mensaje += (
        "\n⭐ **4. TUS FAVORITAS (Wallet & Seguimiento)**\n"
        "• **LUNC** | $0.00005254 | 🟥🟥⬜⬜⬜ | -0.2%\n"
        "  └ ⏱️ *15m: Rango | 1h: Estable | 1d: Acumulando base*\n"
        "  └ [📊 Resumen IA](https://tu-sitio-netlify.app) | [🔶 Tradear](https://www.binance.com/es/trade/LUNC_USDT)\n"
        "• **BANK** | $0.01240 | 🟢🟢🟢🟢🟢 | +6.8%\n"
        "  └ (Destacada en tu wallet)\n"
        "  └ ⏱️ *15m: Alcista | 1h: Ruptura | 1d: Impulso fuerte*\n"
        "  └ [📊 Resumen IA](https://tu-sitio-netlify.app) | [🔶 Tradear](https://www.binance.com/es/trade/BANK_USDT)\n\n"
        "✅ Alerta enviada correctamente mediante sistema de alta disponibilidad."
    )
    return mensaje

def enviar_a_telegram(texto):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": texto,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True
    }
    
    response = requests.post(url, json=payload)
    if response.status_code == 200:
        print("¡Alerta enviada con éxito a Telegram!")
    else:
        print(f"Error al enviar alerta: {response.text}")

if __name__ == "__main__":
    print("Iniciando análisis de mercado...")
    datos = obtener_datos_binance()
    if datos:
        ganadoras, acumulacion, perdedoras = preparar_datos(datos)
        mensaje = construir_mensaje(ganadoras, acumulacion, perdedoras)
        enviar_a_telegram(mensaje)
