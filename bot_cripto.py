import os
import requests

def enviar_a_telegram(mensaje):
    # Toma las credenciales directamente de las variables de entorno de GitHub Secrets
    token = os.environ.get("TELEGRAM_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    
    if not token or not chat_id:
        print("❌ Error: Faltan las variables de entorno TELEGRAM_TOKEN o TELEGRAM_CHAT_ID.")
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

# --- EJEMPLO DE LLAMADA AL FINAL DE TU SCRIPT ---
if __name__ == "__main__":
    # 1. Aquí obtienes tus datos de Binance y tus favoritas
    # coin_data = ... 
    # favoritas_data = ...
    
    # 2. Generas el texto completo con la función que armamos antes
    texto_final = generar_mensaje_cripto(coin_data, favoritas_data)
    
    # 3. Envías el resultado a Telegram
    enviar_a_telegram(texto_final)
