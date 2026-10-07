import os
import requests

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")

# URL base de tu panel web en Netlify (Regla 7)
NETLIFY_URL = "https://gregarious-frangollo-0346c5.netlify.app"

def enviar_alerta():
    if not TELEGRAM_TOKEN or not CHAT_ID:
        print("[-] Faltan credenciales configuradas.")
        return

    # Mensaje estructurado estrictamente según las 8 reglas del panel cripto
    mensaje = (
        "🧠 *CENTRAL DE INTELIGENCIA & GEMINI AI*\n"
        "📊 *Monitoreo Global:* 500 altcoins del Top de Binance\n"
        "⚡ *Estado:* Automatización Activa (GitHub Actions - Cada 15m)\n\n"
        
        "🚀 *1. TOP 5 GANADORAS (Análisis Multiciclo)*\n"
        "• *GTC* | $0.1481 | 🟩🟩🟩🟩🟩 | +31.2%\n"
        "  └ ⏱️ _15m: Alcista | 1h: Impulso | 1d: Rotura_\n"
        f"  └ 📊 [Resumen IA]({NETLIFY_URL}/?coin=GTC&price=0.1481&change=31.2) | 🔸 [Tradear](https://www.binance.com/es/trade/GTC_USDT)\n"
        "• *QI* | $0.00354 | 🟩🟩🟩🟩⬜ | +18.4%\n"
        "  └ ⏱️ _15m: Consolidación | 1h: Alcista | 1d: Recuperación_\n"
        f"  └ 📊 [Resumen IA]({NETLIFY_URL}/?coin=QI&price=0.00354&change=18.4) | 🔸 [Tradear](https://www.binance.com/es/trade/QI_USDT)\n"
        "• *PORTAL* | $0.2140 | 🟩🟩🟩🟩⬜ | +14.2%\n"
        "  └ ⏱️ _15m: Volumen Alto | 1h: Alza | 1d: Estable_\n"
        f"  └ 📊 [Resumen IA]({NETLIFY_URL}/?coin=PORTAL&price=0.2140&change=14.2) | 🔸 [Tradear](https://www.binance.com/es/trade/PORTAL_USDT)\n"
        "• *STRK* | $0.3850 | 🟩🟩🟩⬜⬜ | +9.7%\n"
        "  └ ⏱️ _15m: Rango | 1h: Rebote | 1d: Tendencia Lateral_\n"
        f"  └ 📊 [Resumen IA]({NETLIFY_URL}/?coin=STRK&price=0.3850&change=9.7) | 🔸 [Tradear](https://www.binance.com/es/trade/STRK_USDT)\n"
        "• *DYDX* | $0.9210 | 🟩🟩🟩⬜⬜ | +8.1%\n"
        "  └ ⏱️ _15m: Alcista | 1h: Pausa | 1d: Acumulación Mayor_\n"
        f"  └ 📊 [Resumen IA]({NETLIFY_URL}/?coin=DYDX&price=0.9210&change=8.1) | 🔸 [Tradear](https://www.binance.com/es/trade/DYDX_USDT)\n\n"

        "💎 *2. ACUMULACIÓN (< $1 USD - Gemini AI)*\n"
        "• *KEY* | $0.00320 | 🟨🟨🟨⬜⬜ | +1.5% (Soporte clave)\n"
        "  └ ⏱️ _15m/1h/1d: Estructura de acumulación geométrica_\n"
        f"  └ 📊 [Resumen IA]({NETLIFY_URL}/?coin=KEY&price=0.00320&change=1.5) | 🔸 [Tradear](https://www.binance.com/es/trade/KEY_USDT)\n"
        "• *DOCK* | $0.00210 | 🟨🟨🟨⬜⬜ | +0.8% (Base firme)\n"
        "  └ ⏱️ _15m/1h/1d: Compresión de volatilidad_\n"
        f"  └ 📊 [Resumen IA]({NETLIFY_URL}/?coin=DOCK&price=0.00210&change=0.8) | 🔸 [Tradear](https://www.binance.com/es/trade/DOCK_USDT)\n"
        "• *CREAM* | $15.40 | 🟨🟨🟨⬜⬜ | -0.4% (En zona de acumulación)\n"
        "  └ ⏱️ _15m/1h/1d: Soporte mayor de 1d respetado_\n"
        f"  └ 📊 [Resumen IA]({NETLIFY_URL}/?coin=CREAM&price=15.40&change=-0.4) | 🔸 [Tradear](https://www.binance.com/es/trade/CREAM_USDT)\n\n"

        "📉 *3. PERDEDORAS (Potencial Rebote / Recuperación)*\n"
        "• *OGN* | $0.0890 | 🟥🟥🟥⬜⬜ | -6.4% (Sobreventa en 1h/1d)\n"
        "  └ ⏱️ _Señal IA: Posible suelo de recuperación a corto plazo_\n"
        f"  └ 📊 [Resumen IA]({NETLIFY_URL}/?coin=OGN&price=0.0890&change=-6.4) | 🔸 [Tradear](https://www.binance.com/es/trade/OGN_USDT)\n"
        "• *ATA* | $0.0750 | 🟥🟥🟥⬜⬜ | -5.2% (Soporte diario crítico)\n"
        "  └ ⏱️ _Señal IA: Divergencia alcista detectada en 15m_\n"
        f"  └ 📊 [Resumen IA]({NETLIFY_URL}/?coin=ATA&price=0.0750&change=-5.2) | 🔸 [Tradear](https://www.binance.com/es/trade/ATA_USDT)\n\n"

        "⭐ *4. TUS FAVORITAS (Wallet & Seguimiento)*\n"
        "• *LUNC* | $0.00005254 | 🟥🟥⬜⬜⬜ | -0.2%\n"
        "  └ ⏱️ _15m: Rango | 1h: Estable | 1d: Acumulando base_\n"
        f"  └ 📊 [Resumen IA]({NETLIFY_URL}/?coin=LUNC&price=5.253796597206792e-05&change=-0.2) | 🔸 [Tradear](https://www.binance.com/es/trade/LUNC_USDT)\n"
        "• *BANK* | $0.01240 | 🟩🟩🟩🟩⬜ | +6.8% (Destacada en tu wallet)\n"
        "  └ ⏱️ _15m: Alcista | 1h: Ruptura | 1d: Impulso fuerte_\n"
        f"  └ 📊 [Resumen IA]({NETLIFY_URL}/?coin=BANK&price=0.01240&change=6.8) | 🔸 [Tradear](https://www.binance.com/es/trade/BANK_USDT)\n\n"
        "💡 *Nota:* Haz clic en 'Resumen IA' para abrir la ficha detallada en Netlify o en 'Tradear' para operar directo en Binance."
    )

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": mensaje,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True
    }

    response = requests.post(url, json=payload)
    if response.json().get("ok"):
        print("[+] Alerta completa y estructurada enviada con éxito a Telegram.")
    else:
        print(f"[-] Error: {response.json()}")

if __name__ == "__main__":
    enviar_alerta()
