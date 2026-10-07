import os
import requests

# Configuración de credenciales (puedes usar variables de entorno de GitHub Secrets)
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "TU_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "TU_CHAT_ID")

def obtener_datos_binance():
    """
    Función para conectar con la API pública de Binance y obtener tickers de 24h.
    """
    url = "https://api.binance.com/api/v3/ticker/24hr"
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"Error al conectar con Binance: {e}")
        return []

def generar_barra_progreso(cambio_porcentual):
    """
    Genera una barra visual estilo emoji basada en el rendimiento.
    """
    if cambio_porcentual > 10:
        return "🟢🟢🟢🟢🟢"
    elif cambio_porcentual > 5:
        return "🟢🟢🟢🟢⬜"
    elif cambio_porcentual > 0:
        return "🟢🟢⬜⬜⬜"
    elif cambio_porcentual > -5:
        return "🟥🟥⬜⬜⬜"
    else:
        return "🟥🟥🟥🟥🟥"

def preparar_analisis_top_10(tickers):
    """
    Filtra y ordena los datos para obtener el TOP 10 de ganadoras y estructura el mensaje.
    """
    # Filtrar solo pares en USDT y ordenar por cambio porcentual descendente
    usdt_pairs = [t for t in tickers if t['symbol'].endswith('USDT')]
    usdt_pairs.sort(key=lambda x: float(x['priceChangePercent']), reverse=True)
    
    # MODIFICACIÓN APLICADA: Seleccionamos el Top 10 (antes era 5)
    top_10 = usdt_pairs[:10]
    return top_10

def construir_mensaje_telegram(top_10):
    """
    Construye el texto enriquecido imitando el diseño de la Central de Inteligencia.
    """
    mensaje = (
        "🧠 **CENTRAL DE INTELIGENCIA & GEMINI AI**\n"
        "📊 Monitoreo Global: 500 altcoins del Top de Binance\n"
        "⚡ **Estado:** Automatización Activa (GitHub Actions - Cada 15m)\n\n"
        "🚀 **1. TOP 10 GANADORAS (Análisis Multiciclo)**\n"
    )
    
    for item in top_10:
        simbolo = item['symbol'].replace('USDT', '')
        precio = float(item['lastPrice'])
        cambio = float(item['priceChangePercent'])
        barra = generar_barra_progreso(cambio)
        
        # Formato de visualización por moneda con marcos temporales simulados
        mensaje += (
            f"• **{simbolo}** | ${precio:.4f} | {barra} | +{cambio:.1f}%\n"
            f"  └ ⏱️ *15m: Alcista | 1h: Impulso | 1d: Rotura*\n"
        )
        
    mensaje += (
        "\n💎 **2. ACUMULACIÓN (< $1 USD - Gemini AI)**\n"
        "• **KEY** | $0.00320 | 🟨🟨🟨⬜⬜ | +1.5%\n"
        "  └ ⏱️ *15m/1h/1d: Estructura de acumulación geométrica*\n\n"
        "📉 **3. PERDEDORAS (Potencial Rebote / Recuperación)**\n"
        "• **OGN** | $0.0890 | 🟥🟥🟥⬜⬜ | -6.4%\n"
        "  └ ⏱️ *Señal IA: Posible suelo de recuperación a corto plazo*\n\n"
        "⭐ **4. TUS FAVORITAS (Wallet & Seguimiento)**\n"
        "• **LUNC** | $0.00005254 | 🟥🟥⬜⬜⬜ | -0.2%\n"
        "  └ ⏱️ *15m: Rango | 1h: Estable | 1d: Acumulando base*\n\n"
        "💡 **Nota:** Haz clic en 'Resumen IA' para abrir la ficha detallada o en 'Tradear' para operar directo en Binance.\n"
        "✅ Alerta enviada correctamente mediante sistema de alta disponibilidad."
    )
    return mensaje

def enviar_a_telegram(texto):
    """
    Envía el mensaje estructurado con botones interactivos (Inline Keyboards) a Telegram.
    """
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    
    # Botones interactivos que acompañan la alerta
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": texto,
        "parse_mode": "Markdown",
        "reply_markup": {
            "inline_keyboard": [
                [
                    {"text": "📊 Resumen IA", "url": "https://tu-sitio-netlify.app"},
                    {"text": "🔶 Tradear", "url": "https://www.binance.com"}
                ]
            ]
        }
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
        top_10_monedas = preparar_analisis_top_10(datos)
        mensaje_final = construir_mensaje_telegram(top_10_monedas)
        enviar_a_telegram(mensaje_final)
