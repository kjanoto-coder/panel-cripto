import os
import sys
import requests
import pandas as pd

# Forzar salida inmediata en consola para ver los logs en GitHub Actions
sys.stdout.reconfigure(line_buffering=True) if hasattr(sys.stdout, 'reconfigure') else None

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")

# URL base de tu panel web en Netlify
NETLIFY_URL = "https://gregarious-frangollo-0346c5.netlify.app"

# Lista fija de tus monedas favoritas
FAVORITAS_SYMBOLS = [
    "SYNUSDT", "SNXXBUSDT", "MOVRUSDT", "JSTUSDT", "QIUSDT", 
    "BEAMXUSDT", "HEMIUSDT", "BANKUSDT", "LUNCUSDT"
]

def obtener_datos_binance():
    """Consulta en tiempo real la API pública de Binance con depuración"""
    url = "https://api.binance.com/api/v3/ticker/24hr"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    try:
        print("[+] Conectando con la API de Binance...")
        response = requests.get(url, headers=headers, timeout=15)
        print(f"[DEBUG] Binance Status Code: {response.status_code}")
        
        if response.status_code != 200:
            print(f"[-] Error HTTP de Binance: {response.text}")
            return None
            
        data = response.json()
        if isinstance(data, list):
            df = pd.DataFrame(data)
            df['lastPrice'] = df['lastPrice'].astype(float)
            df['priceChangePercent'] = df['priceChangePercent'].astype(float)
            df['volume'] = df['volume'].astype(float)
            print(f"[+] Datos de Binance obtenidos correctamente ({len(df)} pares encontrados).")
            return df
        else:
            print(f"[-] Binance devolvió un formato no esperado: {data}")
    except Exception as e:
        print(f"[-] Excepción al conectar con Binance API: {e}")
    return None

def enviar_alerta():
    print("[+] Iniciando ejecución del bot...")
    if not TELEGRAM_TOKEN or not CHAT_ID:
        print("[-] Faltan credenciales configuradas (TELEGRAM_TOKEN o CHAT_ID en GitHub Secrets).")
        return

    df = obtener_datos_binance()
    if df is None or df.empty:
        print("[-] No se pudieron obtener datos del mercado.")
        return

    # Filtrar únicamente pares en USDT
    df_usdt = df[df['symbol'].str.endswith('USDT')].copy()
    df_usdt['coin'] = df_usdt['symbol'].str.replace('USDT', '')

    # 1. Top 10 Ganadoras
    top_ganadoras = df_usdt.sort_values(by='priceChangePercent', ascending=False).head(10)

    # 2. Top 10 Perdedoras
    top_perdedoras = df_usdt.sort_values(by='priceChangePercent', ascending=True).head(10)

    # 3. Top 10 Acumulación Silenciosa (< $1)
    acumulacion = df_usdt[
        (df_usdt['lastPrice'] < 1.0) & 
        (df_usdt['priceChangePercent'] >= -1.5) & 
        (df_usdt['priceChangePercent'] <= 3.5)
    ].sort_values(by='volume', ascending=False).head(10)

    # 4. Favoritas ordenadas
    df_favs = df_usdt[df_usdt['symbol'].isin(FAVORITAS_SYMBOLS)].sort_values(by='priceChangePercent', ascending=False)

    mayor_ganadora = top_ganadoras.iloc[0] if not top_ganadoras.empty else None
    mayor_perdedora = top_perdedoras.iloc[0] if not top_perdedoras.empty else None

    # Construcción del mensaje
    mensaje = (
        "🧠 *CENTRAL DE INTELIGENCIA (GEMINI AI AUTÓNOMA)*\n"
        "📊 *Monitoreo Dinámico:* Análisis en vivo conectado a Binance\n"
        "⚡ *Estado:* Automatización Activa (GitHub Actions)\n\n"
    )

    if mayor_ganadora is not None and mayor_perdedora is not None:
        mensaje += (
            "📈 *RESUMEN EJECUTIVO DE MERCADO*\n"
            f"• 🏆 *Mayor Ganadora:* {mayor_ganadora['coin']} (+{mayor_ganadora['priceChangePercent']:.2f}%)\n"
            f"• 🩸 *Mayor Perdedora:* {mayor_perdedora['coin']} ({mayor_perdedora['priceChangePercent']:.2f}%)\n"
            f"• ⭐ *Mejor Rendimiento:* {mayor_ganadora['coin']} (+{mayor_ganadora['priceChangePercent']:.2f}%)\n\n"
        )

    # Ganadoras
    mensaje += "🚀 *1. TOP 10 GANADORAS (Dinámico - Mercado Real)*\n"
    for i, row in enumerate(top_ganadoras.itertuples(), 1):
        precio_str = f"{row.lastPrice:.8f}" if row.lastPrice < 0.01 else f"{row.lastPrice:.4f}"
        mensaje += (
            f"{i}. *{row.coin}* | ${precio_str} | +{row.priceChangePercent:.2f}%\n"
            f"   └ 📊 [Resumen IA]({NETLIFY_URL}/?coin={row.coin}&price={row.lastPrice}&change={row.priceChangePercent}) | 🔸 [Tradear](https://www.binance.com/es/trade/{row.coin}_USDT)\n"
        )

    # Acumulación
    mensaje += "\n💎 *2. TOP 10 ACUMULACIÓN SILENCIOSA (Escaneo IA < $1)*\n"
    for i, row in enumerate(acumulacion.itertuples(), 1):
        precio_str = f"{row.lastPrice:.8f}" if row.lastPrice < 0.01 else f"{row.lastPrice:.4f}"
        signo = "+" if row.priceChangePercent > 0 else ""
        mensaje += (
            f"{i}. *{row.coin}* | ${precio_str} | {signo}{row.priceChangePercent:.2f}% (Compresión sorda)\n"
            f"   └ 📊 [Resumen IA]({NETLIFY_URL}/?coin={row.coin}&price={row.lastPrice}&change={row.priceChangePercent}) | 🔸 [Tradear](https://www.binance.com/es/trade/{row.coin}_USDT)\n"
        )

    # Perdedoras
    mensaje += "\n📉 *3. TOP 10 PERDEDORAS (Oportunidades de Rebote Táctico)*\n"
    for i, row in enumerate(top_perdedoras.itertuples(), 1):
        precio_str = f"{row.lastPrice:.8f}" if row.lastPrice < 0.01 else f"{row.lastPrice:.4f}"
        mensaje += (
            f"{i}. *{row.coin}* | ${precio_str} | {row.priceChangePercent:.2f}%\n"
            f"   └ 📊 [Resumen IA]({NETLIFY_URL}/?coin={row.coin}&price={row.lastPrice}&change={row.priceChangePercent}) | 🔸 [Tradear](https://www.binance.com/es/trade/{row.coin}_USDT)\n"
        )

    # Favoritas
    mensaje += "\n⭐ *4. TUS FAVORITAS (Ordenadas de Mayor a Menor Rendimiento)*\n"
    for i, row in enumerate(df_favs.itertuples(), 1):
        precio_str = f"{row.lastPrice:.8f}" if row.lastPrice < 0.01 else f"{row.lastPrice:.4f}"
        signo = "+" if row.priceChangePercent > 0 else ""
        mensaje += (
            f"{i}. *{row.coin}* | ${precio_str} | {signo}{row.priceChangePercent:.2f}%\n"
            f"   └ 📊 [Resumen IA]({NETLIFY_URL}/?coin={row.coin}&price={row.lastPrice}&change={row.priceChangePercent}) | 🔸 [Tradear](https://www.binance.com/es/trade/{row.coin}_USDT)\n"
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
    response = requests.post(url_tg, json=payload)
    print(f"[DEBUG] Telegram Response Status: {response.status_code}")
    
    try:
        res_json = response.json()
        print(f"[DEBUG] Telegram Response Body: {res_json}")
        if res_json.get("ok"):
            print("[+] ¡Alerta enviada con éxito a Telegram!")
        else:
            print(f"[-] Telegram rechazó el mensaje: {res_json}")
    except Exception as e:
        print(f"[-] Error al leer respuesta de Telegram: {e}, Texto: {response.text}")

if __name__ == "__main__":
    enviar_alerta()
