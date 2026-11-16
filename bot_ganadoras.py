import os
import json
import requests
from datetime import datetime, timezone, timedelta

TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
# Aseguramos que lea correctamente el secreto del tópico de ganadoras
TOPIC_ID_GANADORAS = os.getenv('TOPIC_ID_GANADORAS')

print("🔍 Iniciando ejecución de bot_ganadoras.py...")

def enviar_telegram(mensaje):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("❌ ERROR CRÍTICO: Faltan TELEGRAM_BOT_TOKEN o TELEGRAM_CHAT_ID en las Secrets de GitHub.")
        return
    
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        'chat_id': TELEGRAM_CHAT_ID,
        'text': mensaje,
        'parse_mode': 'Markdown',
        'disable_web_page_preview': True
    }
    
    if TOPIC_ID_GANADORAS:
        try:
            payload['message_thread_id'] = int(TOPIC_ID_GANADORAS)
            print(f"📌 Enviando al tópico ID: {TOPIC_ID_GANADORAS}")
        except ValueError:
            print("⚠️ El TOPIC_ID_GANADORAS no es un número válido.")
            
    try:
        response = requests.post(url, json=payload, timeout=15)
        if response.status_code == 200:
            print("✅ Reporte enviado a Telegram con éxito.")
        else:
            print(f"❌ Error de Telegram API ({response.status_code}): {response.text}")
    except Exception as e:
        print(f"❌ Excepción al conectar con Telegram: {e}")

def main():
    # Aquí es donde lee tu archivo de datos (ej. datos_pre_explosion_ia.json o el histórico que recopila las monedas)
    archivo_datos = "datos_pre_explosion_ia.json"
    
    if not os.path.exists(archivo_datos):
        print(f"⚠️ No se encontró el archivo {archivo_datos}")
        return

    try:
        with open(archivo_datos, 'r', encoding='utf-8') as f:
            contenido = json.load(f)
    except Exception as e:
        print(f"❌ Error al leer el JSON: {e}")
        return

    # Extraer registros
    registros = []
    if isinstance(contenido, dict):
        registros = contenido.get("top_candidatas", [])
    elif isinstance(contenido, list):
        registros = contenido

    if not registros:
        print("⚠️ El archivo de datos no contiene registros para procesar.")
        return

    print(f"📊 Procesando {len(registros)} registros para el reporte de ganadoras...")

    # Simulación/Cálculo de ejemplo para ordenar de mayor a menor rendimiento
    # (Asegúrate de que esta lógica coincida con tu listado de subidas)
    ganadoras = []
    for item in registros:
        ticker = item.get('ticker', item.get('symbol', 'DESCONOCIDO'))
        precio_base = float(item.get('price', 0))
        # Aquí puedes ajustar cómo calcula el rendimiento actual vs base
        ganadoras.append({
            "ticker": ticker,
            "base": precio_base,
            "rendimiento": 12.5 # Reemplaza por tu cálculo real de subida
        })

    # Ordenar de mayor a menor rendimiento
    ganadoras_ordenadas = sorted(ganadoras, key=lambda x: x['rendimiento'], reverse=True)

    # Construir mensaje
    tz_arg = timezone(timedelta(hours=-3))
    fecha_hoy = datetime.now(tz_arg).strftime('%Y-%m-%d')

    mensaje = f"🏆 **REPORTE DIARIO DE MONEDAS GANADORAS**\n"
    mensaje += f"📅 *Fecha:* `{fecha_hoy}`\n\n"

    for idx, g in enumerate(ganadoras_ordenadas[:10], 1):
        mensaje += f"{idx}. **{g['ticker']}** | Base: `${g['base']:.4f}` | 🚀 `+{g['rendimiento']:.2f}%`\n"

    enviar_telegram(mensaje)

if __name__ == "__main__":
    main()
