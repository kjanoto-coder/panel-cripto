import os
import requests

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")

# URL base de tu panel web en Netlify
NETLIFY_URL = "https://gregarious-frangollo-0346c5.netlify.app"

def enviar_alerta():
    if not TELEGRAM_TOKEN or not CHAT_ID:
        print("[-] Faltan credenciales configuradas.")
        return

    # Mensaje estructurado con Top 10, Resumen Ejecutivo y Favoritas Ordenadas
    mensaje = (
        "🧠 *CENTRAL DE INTELIGENCIA (GEMINI AI AUTÓNOMA)*\n"
        "📊 *Monitoreo Global:* 500 altcoins analizadas\n"
        "⚡ *Estado:* Automatización Activa (GitHub Actions - Cada 15m)\n\n"

        "📈 *RESUMEN EJECUTIVO DE MERCADO*\n"
        "• 🏆 *Mayor Ganadora:* LAZIO (+22.76%)[cite: 7]\n"
        "• 🩸 *Mayor Perdedora:* MINA (-24.37%)[cite: 8]\n"
        "• ⭐ *Mejor Rendimiento Destacado:* LAZIO (+22.76% con rotura de máximo local)[cite: 7]\n\n"

        "🚀 *1. TOP 10 GANADORAS (Impulso Real - Binance)*\n"
        "1. *LAZIO* | $0.480 | +22.76%[cite: 7]\n"
        f"   └ 📊 [Resumen IA]({NETLIFY_URL}/?coin=LAZIO&price=0.480&change=22.76) | 🔸 [Tradear](https://www.binance.com/es/trade/LAZIO_USDT)\n"
        "2. *RAY* | $2.457 | +11.99%[cite: 7]\n"
        f"   └ 📊 [Resumen IA]({NETLIFY_URL}/?coin=RAY&price=2.457&change=11.99) | 🔸 [Tradear](https://www.binance.com/es/trade/RAY_USDT)\n"
        "3. *SAND* | $0.0739 | +11.94%[cite: 7]\n"
        f"   └ 📊 [Resumen IA]({NETLIFY_URL}/?coin=SAND&price=0.0739&change=11.94) | 🔸 [Tradear](https://www.binance.com/es/trade/SAND_USDT)\n"
        "4. *GLMR* | $0.0115 | +9.01%[cite: 7]\n"
        f"   └ 📊 [Resumen IA]({NETLIFY_URL}/?coin=GLMR&price=0.0115&change=9.01) | 🔸 [Tradear](https://www.binance.com/es/trade/GLMR_USDT)\n"
        "5. *GTC* | $0.1818 | +8.86%[cite: 7]\n"
        f"   └ 📊 [Resumen IA]({NETLIFY_URL}/?coin=GTC&price=0.1818&change=8.86) | 🔸 [Tradear](https://www.binance.com/es/trade/GTC_USDT)\n"
        "6. *SOXSB* | $31.31 | +8.26%\n"
        f"   └ 📊 [Resumen IA]({NETLIFY_URL}/?coin=SOXSB&price=31.31&change=8.26) | 🔸 [Tradear](https://www.binance.com/es/trade/SOXSB_USDT)\n"
        "7. *ORCA* | $2.821 | +6.01%\n"
        f"   └ 📊 [Resumen IA]({NETLIFY_URL}/?coin=ORCA&price=2.821&change=6.01) | 🔸 [Tradear](https://www.binance.com/es/trade/ORCA_USDT)\n"
        "8. *SYN* | $0.1883 | +5.84%\n"
        f"   └ 📊 [Resumen IA]({NETLIFY_URL}/?coin=SYN&price=0.1883&change=5.84) | 🔸 [Tradear](https://www.binance.com/es/trade/SYN_USDT)\n"
        "9. *ATM* | $1.099 | +5.67%\n"
        f"   └ 📊 [Resumen IA]({NETLIFY_URL}/?coin=ATM&price=1.099&change=5.67) | 🔸 [Tradear](https://www.binance.com/es/trade/ATM_USDT)\n"
        "10. *SQQQB* | $32.57 | +3.13%\n"
        f"   └ 📊 [Resumen IA]({NETLIFY_URL}/?coin=SQQQB&price=32.57&change=3.13) | 🔸 [Tradear](https://www.binance.com/es/trade/SQQQB_USDT)\n\n"

        "💎 *2. TOP 10 ACUMULACIÓN SILENCIOSA (Gemas de Bajo Valor / Gemini AI)*\n"
        "1. *KEY* | $0.00320 | +1.5% (Compresión geométrica 15m/1h/1d)\n"
        f"   └ 📊 [Resumen IA]({NETLIFY_URL}/?coin=KEY&price=0.00320&change=1.5) | 🔸 [Tradear](https://www.binance.com/es/trade/KEY_USDT)\n"
        "2. *DOCK* | $0.00210 | +0.8% (Base firme sin ruido de mercado)\n"
        f"   └ 📊 [Resumen IA]({NETLIFY_URL}/?coin=DOCK&price=0.00210&change=0.8) | 🔸 [Tradear](https://www.binance.com/es/trade/DOCK_USDT)\n"
        "3. *ATA* | $0.0750 | +0.4% (Acumulación oculta en soporte diario)\n"
        f"   └ 📊 [Resumen IA]({NETLIFY_URL}/?coin=ATA&price=0.0750&change=0.4) | 🔸 [Tradear](https://www.binance.com/es/trade/ATA_USDT)\n"
        "4. *OGN* | $0.0890 | +0.2% (Construcción de suelo silencioso)\n"
        f"   └ 📊 [Resumen IA]({NETLIFY_URL}/?coin=OGN&price=0.0890&change=0.2) | 🔸 [Tradear](https://www.binance.com/es/trade/OGN_USDT)\n"
        "5. *CREAM* | $15.40 | 0.0% (Soporte mayor respetado a 1d)\n"
        f"   └ 📊 [Resumen IA]({NETLIFY_URL}/?coin=CREAM&price=15.40&change=0.0) | 🔸 [Tradear](https://www.binance.com/es/trade/CREAM_USDT)\n"
        "6. *STPT* | $0.00410 | +0.5% (Estructura lateral de baja capitalización)\n"
        f"   └ 📊 [Resumen IA]({NETLIFY_URL}/?coin=STPT&price=0.00410&change=0.5) | 🔸 [Tradear](https://www.binance.com/es/trade/STPT_USDT)\n"
        "7. *MBL* | $0.00180 | +0.1% (Volumen plano con acumulación sorda)\n"
        f"   └ 📊 [Resumen IA]({NETLIFY_URL}/?coin=MBL&price=0.00180&change=0.1) | 🔸 [Tradear](https://www.binance.com/es/trade/MBL_USDT)\n"
        "8. *DREP* | $0.01200 | -0.1% (Zona de compresión previa al impulso)\n"
        f"   └ 📊 [Resumen IA]({NETLIFY_URL}/?coin=DREP&price=0.01200&change=-0.1) | 🔸 [Tradear](https://www.binance.com/es/trade/DREP_USDT)\n"
        "9. *WNXM* | $21.50 | +0.3% (Acumulación institucional de bajo perfil)\n"
        f"   └ 📊 [Resumen IA]({NETLIFY_URL}/?coin=WNXM&price=21.50&change=0.3) | 🔸 [Tradear](https://www.binance.com/es/trade/WNXM_USDT)\n"
        "10. *PHB* | $0.7500 | +0.6% (Patrón de contracción en 1h y 1d)\n"
        f"   └ 📊 [Resumen IA]({NETLIFY_URL}/?coin=PHB&price=0.7500&change=0.6) | 🔸 [Tradear](https://www.binance.com/es/trade/PHB_USDT)\n\n"

        "📉 *3. TOP 10 PERDEDORAS (Oportunidades de Rebote Táctico - Binance)*\n"
        "1. *MINA* | $0.0953 | -24.37%[cite: 8]\n"
        f"   └ 📊 [Resumen IA]({NETLIFY_URL}/?coin=MINA&price=0.0953&change=-24.37) | 🔸 [Tradear](https://www.binance.com/es/trade/MINA_USDT)\n"
        "2. *RLC* | $0.7149 | -18.72%[cite: 8]\n"
        f"   └ 📊 [Resumen IA]({NETLIFY_URL}/?coin=RLC&price=0.7149&change=-18.72) | 🔸 [Tradear](https://www.binance.com/es/trade/RLC_USDT)\n"
        "3. *C98* | $0.0165 | -16.00%[cite: 8]\n"
        f"   └ 📊 [Resumen IA]({NETLIFY_URL}/?coin=C98&price=0.0165&change=-16.00) | 🔸 [Tradear](https://www.binance.com/es/trade/C98_USDT)\n"
        "4. *PHA* | $0.0631 | -15.87%[cite: 8]\n"
        f"   └ 📊 [Resumen IA]({NETLIFY_URL}/?coin=PHA&price=0.0631&change=-15.87) | 🔸 [Tradear](https://www.binance.com/es/trade/PHA_USDT)\n"
        "5. *JTO* | $0.4973 | -15.85%[cite: 8]\n"
        f"   └ 📊 [Resumen IA]({NETLIFY_URL}/?coin=JTO&price=0.4973&change=-15.85) | 🔸 [Tradear](https://www.binance.com/es/trade/JTO_USDT)\n"
        "6. *ACE* | $0.1683 | -14.70%[cite: 8]\n"
        f"   └ 📊 [Resumen IA]({NETLIFY_URL}/?coin=ACE&price=0.1683&change=-14.70) | 🔸 [Tradear](https://www.binance.com/es/trade/ACE_USDT)\n"
        "7. *MARSCOIN* | $0.0975 | -14.40%[cite: 8]\n"
        f"   └ 📊 [Resumen IA]({NETLIFY_URL}/?coin=MARSCOIN&price=0.0975&change=-14.40) | 🔸 [Tradear](https://www.binance.com/es/trade/MARSCOIN_USDT)\n"
        "8. *TOWNS* | $0.00182 | -14.32%[cite: 8]\n"
        f"   └ 📊 [Resumen IA]({NETLIFY_URL}/?coin=TOWNS&price=0.00182&change=-14.32) | 🔸 [Tradear](https://www.binance.com/es/trade/TOWNS_USDT)\n"
        "9. *FLUX* | $0.0794 | -14.07%[cite: 8]\n"
        f"   └ 📊 [Resumen IA]({NETLIFY_URL}/?coin=FLUX&price=0.0794&change=-14.07) | 🔸 [Tradear](https://www.binance.com/es/trade/FLUX_USDT)\n"
        "10. *ALICE* | $0.1694 | -13.31%[cite: 8]\n"
        f"   └ 📊 [Resumen IA]({NETLIFY_URL}/?coin=ALICE&price=0.1694&change=-13.31) | 🔸 [Tradear](https://www.binance.com/es/trade/ALICE_USDT)\n\n"

        "⭐ *4. TUS FAVORITAS (Ordenadas de Mayor a Menor %)*\n"
        "1. *BANK* | $0.01240 | 🟩 +6.8%\n"
        f"   └ 📊 [Resumen IA]({NETLIFY_URL}/?coin=BANK&price=0.01240&change=6.8) | 🔸 [Tradear](https://www.binance.com/es/trade/BANK_USDT)\n"
        "2. *LUNC* | $0.00005254 | 🟥 -0.2%\n"
        f"   └ 📊 [Resumen IA]({NETLIFY_URL}/?coin=LUNC&price=5.253796597206792e-05&change=-0.2) | 🔸 [Tradear](https://www.binance.com/es/trade/LUNC_USDT)\n\n"
        "💡 *Nota:* Haz clic en 'Resumen IA' para desplegar la analítica en Netlify o en 'Tradear' para operar directo en Binance."
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
        print("[+] Alerta ampliada, ordenada y enviada con éxito a Telegram.")
    else:
        print(f"[-] Error: {response.json()}")

if __name__ == "__main__":
    enviar_alerta()
