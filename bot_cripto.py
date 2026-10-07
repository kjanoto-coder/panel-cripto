import os
import sys
import json
import urllib.request

# Forzar salida inmediata en consola
sys.stdout.reconfigure(line_buffering=True) if hasattr(sys.stdout, 'reconfigure') else None

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")

NETLIFY_URL = "https://gregarious-frangollo-0346c5.netlify.app"

FAVORITAS_SYMBOLS = [
    "SYNUSDT", "SNXXBUSDT", "MOVRUSDT", "JSTUSDT", "QIUSDT", 
    "BEAMXUSDT", "HEMIUSDT", "BANKUSDT", "LUNCUSDT"
]

def obtener_datos_mercado():
    url = "https://api.coincap.io/v2/assets?limit=2000"
    req = urllib.request.Request(
        url, 
        headers={"User-Agent": "Mozilla/5.0"}
    )
    try:
        print("[+] Conectando con la API pública de CoinCap...")
        with urllib.request.urlopen(req, timeout=15) as response:
            if response.status == 200:
                data = json.loads(response.read().decode('utf-8'))
                items = data.get("data", [])
                print(f"[+] Datos obtenidos correctamente ({len(items)} activos).")
                return items
            else:
                print(f"[-] Error HTTP: {response.status}")
    except Exception as e:
        print(f"[-] Excepción al conectar con la API: {e}")
    return None

def enviar_alerta():
    print("[+] Iniciando ejecución del bot...")
    if not TELEGRAM_TOKEN or not CHAT_ID:
        print("[-] Faltan credenciales configuradas (TELEGRAM_TOKEN o CHAT_ID).")
        return

    raw_data = obtener_datos_mercado()
    if not raw_data:
        print("[-] No se pudieron obtener datos del mercado.")
        return

    # Procesar datos adaptados al formato del bot
    df_usdt = []
    for item in raw_data:
        try:
            coin = item.get("symbol", "").upper()
            symbol = f"{coin}USDT"
            lastPrice = float(item.get("priceUsd", 0))
            priceChangePercent = float(item.get("changePercent24Hr", 0))
            volume = float(item.get("volumeUsd24Hr", 0))
            
            df_usdt.append({
                "symbol": symbol,
                "coin": coin,
                "lastPrice": lastPrice,
                "priceChangePercent": priceChangePercent,
                "volume": volume
            })
        except (ValueError, TypeError):
            continue

    if not df_usdt:
        print("[-] No hay datos procesados.")
        return

    # 1. Top 10 Ganadoras
    top_ganadoras = sorted(df_usdt, key=lambda x: x['priceChangePercent'], reverse=True)[:10]

    # 2. Top 10 Perdedoras
    top_perdedoras = sorted(df_usdt, key=lambda x: x['priceChangePercent'])[:10]

    # 3. Top 10 Acumulación Silenciosa (< $1)
    acumulacion_raw = [
        x for x in df_usdt 
        if x['lastPrice'] < 1.0 and -1.5 <= x['priceChangePercent'] <= 3.5
    ]
    acumulacion = sorted(acumulacion_raw, key=lambda x: x['volume'], reverse=True)[:10]

    # 4. Favoritas ordenadas (extranciendo la moneda base sin USDT)
    favs_coins = [s.replace('USDT', '') for s in FAVORITAS_SYMBOLS]
    favs_raw = [x for x in df_usdt if x['coin'] in favs_coins]
    df_favs = sorted(favs_raw, key=lambda x: x['priceChangePercent'], reverse=True)

    mayor_ganadora = top_ganadoras[0] if top_ganadoras else None
    mayor_perdedora = top_perdedoras[0] if top_perdedoras else None

    # Construcción del mensaje
    mensaje = (
        "🧠 *CENTRAL DE INTELIGENCIA (GEMINI AI AUTÓNOMA)*\n"
        "📊 *Monitoreo Dinámico:* Análisis en vivo\n"
        "⚡ *Estado:* Automatización Activa (GitHub Actions)\n\n"
    )

    if mayor_ganadora and mayor_perdedora:
        mensaje += (
            "📈 *RESUMEN EJECUTIVO DE MERCADO*\n"
            f"• 🏆 *Mayor Ganadora:* {mayor_ganadora['coin']} (+{mayor_ganadora['priceChangePercent']:.2f}%)\n"
            f"• 🩸 *Mayor Perdedora:* {mayor_perdedora['coin']} ({mayor_perdedora['priceChangePercent']:.2f}%)\n"
            f"• ⭐ *Mejor Rendimiento:* {mayor_ganadora['coin']} (+{mayor_ganadora['priceChangePercent']:.2f}%)\n\n"
        )

    # Ganadoras
    mensaje += "🚀 *1. TOP 10 GANADORAS (Dinámico - Mercado Real)*\n"
    for i, row in enumerate(top_ganadoras, 1):
        precio_str = f"{row['lastPrice']:.8f}" if row['lastPrice'] < 0.01 else f"{row['lastPrice']:.4f}"
        mensaje += (
            f"{i}. *{row['coin']}* | ${precio_str} | +{row['priceChangePercent']:.2f}%\n"
            f"   └ 📊 [Resumen IA]({NETLIFY_URL}/?coin={row['coin']}&price={row['lastPrice']}&change={row['priceChangePercent']}) | 🔸 [Tradear](https://www.binance.com/es/trade/{row['coin']}_USDT)\n"
        )

    # Acumulación
    mensaje += "\n💎 *2. TOP 10 ACUMULACIÓN SILENCIOSA (Escaneo IA < $1)*\n"
    for i, row in enumerate(acumulacion, 1):
        precio_str = f"{row['lastPrice']:.8f}" if row['lastPrice'] < 0.01 else f"{row['lastPrice']:.4f}"
        signo = "+" if row['priceChangePercent'] > 0 else ""
        mensaje += (
            f"{i}. *{row['coin']}* | ${precio_str} | {signo}{row['priceChangePercent']:.2f}% (Compresión sorda)\n"
            f"   └ 📊 [Resumen IA]({NETLIFY_URL}/?coin={row['coin']}&price={row['lastPrice']}&change={row['priceChangePercent']}) | 🔸 [Tradear](https://www.binance.com/es/trade/{row['coin']}_USDT)\n"
        )

    # Perdedoras
    mensaje += "\n📉 *3. TOP 10 PERDEDORAS (Oportunidades de Rebote Táctico)*\n"
    for i, row in enumerate(top_perdedoras, 1):
        precio_str = f"{row['lastPrice']:.8f}" if row['lastPrice'] < 0.01 else f"{row['lastPrice']:.4f}"
        mensaje += (
            f"{i}. *{row['coin']}* | ${precio_str} | {row['priceChangePercent']:.2f}%\n"
            f"   └ 📊 [Resumen IA]({NETLIFY_URL}/?coin={row['coin']}&price={row['lastPrice']}&change={row['priceChangePercent']}) | 🔸 [Tradear](https://www.binance.com/es/trade/{row['coin']}_USDT)\n"
        )

    # Favoritas
    mensaje += "\n⭐ *4. TUS FAVORITAS (Ordenadas de Mayor a Menor Rendimiento)*\n"
    for i, row in enumerate(df_favs, 1):
        precio_str = f"{row['lastPrice']:.8f}" if row['lastPrice'] < 0.01 else f"{row['lastPrice']:.4f}"
        signo = "+" if row['priceChangePercent'] > 0 else ""
        mensaje += (
            f"{i}. *{row['coin']}* | ${precio_str} | {signo}{row['priceChangePercent']:.2f}%\n"
            f"   └ 📊 [Resumen IA]({NETLIFY_URL}/?coin={row['coin']}&price={row['lastPrice']}&change={row['priceChangePercent']}) | 🔸 [Tradear](https://www.binance.com/es/trade/{row['coin']}_USDT)\n"
        )

    mensaje += "\n💡 *Nota:* Datos analizados y procesados autónomamente en tiempo real."

    # Envío a Telegram
    url_tg = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": mensaje,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True
    }

    print("[+] Enviando mensaje a Telegram...")
    req_tg = urllib.request.Request(
        url_tg,
        data=json.dumps(payload).encode('utf-8'),
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    
    try:
        with urllib.request.urlopen(req_tg, timeout=15) as response_tg:
            res_body = response_tg.read().decode('utf-8')
            res_json = json.loads(res_body)
            print(f"[DEBUG] Telegram Response: {res_json}")
            if res_json.get("ok"):
                print("[+] ¡Alerta enviada con éxito a Telegram!")
            else:
                print(f"[-] Telegram rechazó el mensaje: {res_json}")
    except Exception as e:
        print(f"[-] Error al enviar mensaje a Telegram: {e}")

if __name__ == "__main__":
    enviar_alerta()
