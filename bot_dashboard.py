import os
import requests

# Configuración de Telegram limpiando posibles espacios vacíos
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "-1003937091631").strip()
TELEGRAM_THREAD_ID = os.getenv("TELEGRAM_MESSAGE_THREAD_ID", "2711").strip()

def enviar_reporte_telegram(mensaje):
    if not TELEGRAM_BOT_TOKEN:
        print("⚠️ No se encontró el TELEGRAM_BOT_TOKEN en las variables de entorno.")
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "message_thread_id": int(TELEGRAM_THREAD_ID) if TELEGRAM_THREAD_ID else None,
        "text": mensaje,
        "parse_mode": "Markdown"
    }

    try:
        response = requests.post(url, json=payload)
        resultado = response.json()
        if resultado.get("ok"):
            print("✅ Reporte publicado en Telegram correctamente.")
        else:
            print(f"⚠️ Respuesta de Telegram: {resultado}")
    except Exception as e:
        print(f"❌ Error al conectar con la API de Telegram: {e}")

def main():
    print("🔹 Base de datos del ecosistema actualizada.")
    
    # Mensaje de prueba / reporte para el bot
    mensaje = (
        "🚀 **Actualización del Ecosistema Cripto**\n\n"
        "📊 El panel y la auditoría web se han sincronizado correctamente.\n"
        "🌐 Ya puedes ver los cambios reflejados en línea."
    )
    
    enviar_reporte_telegram(mensaje)

if __name__ == "__main__":
    main()
