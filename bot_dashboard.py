import os
import json
import requests
import time
from datetime import datetime

TELEGRAM_BOT_TOKEN = (os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("TELEGRAM_TOKEN") or "").strip()
TELEGRAM_CHAT_ID = (os.getenv("TELEGRAM_CHAT_ID") or os.getenv("CHAT_ID") or "").strip()
MESSAGE_THREAD_ID = (os.getenv("TOPIC_ID_CENTRAL") or os.getenv("TELEGRAM_MESSAGE_THREAD_ID") or "").strip()

ECOSYSTEM_FILE = "database_ecosistema.json"

print("🏛️ Ejecutando Sincronización de Central Web...")

def obtener_datos_binance():
    url = "https://data-api.binance.vision/api/v3/ticker/24hr"
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            return response.json()
    except Exception as e:
        print(f"Error conectando con Binance Vision: {e}")
    return []

def actualizar_base_ecosistema(datos_mercado):
    try:
        top_volumen = sorted(
            [d for d in datos_mercado if d.get('symbol', '').endswith('USDT')],
            key=lambda x: float(x.get('quoteVolume', 0)),
            reverse=True
        )[:10]

        ecosistema = {
            "timestamp": datetime.now().isoformat(),
            "total_Pares": len(datos_mercado),
            "destacados": [
                {
                    "symbol": item['symbol'].replace('USDT', ''),
                    "price": float(item['lastPrice']),
                    "change": float(item['priceChangePercent']),
                    "volume": float(item['quoteVolume'])
                } for item in top_volumen
            ]
        }

        with open(ECOSYSTEM_FILE, "w") as f:
            json.dump(ecosistema, f, indent=4)
        print("✅ Base de datos del ecosistema actualizada con éxito.")
    except Exception as e:
        print(f"⚠️ Error actualizando base de datos del ecosistema: {e}")

def enviar_mensaje_telegram(token, chat_id, thread_id, texto):
    if not token or not chat_id:
        print("⚠️ Faltan credenciales de Telegram para enviar el reporte de Central Web.")
        return
        
    url_base = f"https://api.telegram.org/bot{token}"
    
    payload = {
        'chat_id': chat_id,
        'text': texto,
        'parse_mode': 'Markdown',
        'disable_web_page_preview': True
    }
    
    t_id = None
    if thread_id:
        try:
            t_id = int(thread_id)
            payload['message_thread_id'] = t_id
        except ValueError:
            pass
            
    try:
        res = requests.post(f"{url_base}/sendMessage", json=payload, timeout=20)
        resultado = res.json()
    except Exception:
        resultado = {"ok": False}
        
    # Fallback si falla el hilo específico: reenvía al chat principal
    if not resultado.get("ok"):
        print("⚠️ Reintentando mensaje de Central Web al chat principal...")
        payload.pop("message_thread_id", None)
        try:
            res = requests.post(f"{url_base}/sendMessage", json=payload, timeout=20)
            resultado = res.json()
        except Exception:
            pass
            
    if resultado.get("ok"):
        print("✅ Reporte de Central Web enviado a Telegram correctamente.")
    else:
        print(f"❌ No se pudo enviar el mensaje a Telegram: {resultado}")

def main():
    datos = obtener_datos_binance()
    if datos:
        actualizar_base_ecosistema(datos)
        
        mensaje = "🏛️ **CENTRAL WEB • SINCRONIZACIÓN DEL ECOSYSTEMA**\n"
        mensaje += f"🕒 *Actualización:* `{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`\n\n"
        mensaje += "✅ Se han procesado y actualizado los datos del panel y los registros de mercado para la interfaz web.\n"
        mensaje += "🚀 El ecosistema se encuentra operando de forma sincronizada."
        
        enviar_mensaje_telegram(TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, MESSAGE_THREAD_ID, mensaje)
    else:
        print("❌ No se pudieron obtener datos para el dashboard.")

if __name__ == "__main__":
    main()
