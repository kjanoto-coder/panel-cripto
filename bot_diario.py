import os
import csv
import requests
from datetime import datetime, timezone, timedelta

TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
TOPIC_ID_GANADORAS = os.getenv('TOPIC_ID_GANADORAS')

HISTORIAL_CSV = "historico_alertas.csv"

print("📊 Procesando reporte diario desde el historial del bot de ganadoras...")

def enviar_telegram(mensaje):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("❌ Faltan credenciales de Telegram.")
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
        except ValueError:
            pass
            
    try:
        response = requests.post(url, json=payload, timeout=15)
        if response.status_code == 200:
            print("✅ Reporte diario enviado con éxito al bot/tópico de ganadoras.")
        else:
            print(f"❌ Error de Telegram ({response.status_code}): {response.text}")
    except Exception as e:
        print(f"❌ Excepción conectando a Telegram: {e}")

def main():
    if not os.path.exists(HISTORIAL_CSV) or os.path.getsize(HISTORIAL_CSV) == 0:
        print("⚠️ El archivo 'historico_alertas.csv' está vacío o no existe.")
        return

    monedas_dia = {}
    tz_arg = timezone(timedelta(hours=-3))
    # Toma el día anterior completo como período del reporte
    ayer_str = (datetime.now(tz_arg) - timedelta(days=1)).strftime('%Y-%m-%d')

    try:
        with open(HISTORIAL_CSV, mode='r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                fecha_hora = row.get('fecha_hora', '')
                # Filtramos estrictamente lo registrado durante el día anterior
                if ayer_str in fecha_hora:
                    ticker = row.get('ticker', '').upper()
                    precio = float(row.get('precio', 0))
                    rendimiento = float(row.get('rendimiento', 0))
                    
                    # Nos quedamos con el pico más alto registrado por el bot para cada moneda en el día
                    if ticker not in monedas_dia or rendimiento > monedas_dia[ticker]['rendimiento']:
                        monedas_dia[ticker] = {
                            "ticker": ticker,
                            "precio": precio,
                            "rendimiento": rendimiento
                        }
    except Exception as e:
        print(f"❌ Error leyendo el archivo CSV: {e}")
        return

    if not monedas_dia:
        print(f"⚠️ No se encontraron registros para la fecha {ayer_str}.")
        return

    # Ordenar estrictamente de mayor a menor rendimiento (% subida)
    lista_ganadoras = sorted(list(monedas_dia.values()), key=lambda x: x['rendimiento'], reverse=True)

    # Construir el mensaje con el formato de tabla exacto
    mensaje = f"🏆 **REPORTE DIARIO DE MONEDAS GANADORAS**\n"
    mensaje += f"📅 *Fecha:* `{ayer_str}`\n\n"
    mensaje += f"` N°  | NOMBRE   | $ valor    | % subida `\n"
    mensaje += f"`----------------------------------`\n"

    for idx, g in enumerate(lista_ganadoras, 1):
        precio_str = f"${g['precio']:.4f}" if g['precio'] < 1.0 else f"${g['precio']:.2f}"
        mensaje += f"` {idx:<3} | {g['ticker']:<8} | {precio_str:<10} | +{g['rendimiento']:.2f}% `\n"

    enviar_telegram(mensaje)

if __name__ == "__main__":
    main()
