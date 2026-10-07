import os
import requests

def enviar_a_telegram(mensaje):
    token = os.environ.get("TELEGRAM_TOKEN")
    # Busca 'CHAT_ID' tal como figura en tus GitHub Actions (o 'TELEGRAM_CHAT_ID' por si acaso)
    chat_id = os.environ.get("CHAT_ID") or os.environ.get("TELEGRAM_CHAT_ID")
    
    if not token or not chat_id:
        print("❌ Error: Faltan las variables de entorno TELEGRAM_TOKEN o CHAT_ID.")
        return

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": mensaje,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }
    
    response = requests.post(url, json=payload)
    if response.status_code == 200:
        print("✅ ¡Mensaje enviado a Telegram con éxito!")
    else:
        print(f"❌ Error al enviar a Telegram: {response.text}")
