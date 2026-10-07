import os
import requests

# Dominio fijo de Netlify que funciona correctamente
BASE_URL = "https://gregarious-frangollo-0346c5.netlify.app"

def fmt_price(p):
    """Función para limpiar símbolos y evitar notación científica en precios muy bajos"""
    if p is None:
        return "0.00"
    try:
        p_limpio = str(p).replace('$', '').replace(',', '').strip()
        p_float = float(p_limpio)
        if p_float < 1:
            return f"{p_float:.8f}".rstrip('0').rstrip('.')
        return f"{p_float:.2f}"
    except Exception:
        return str(p)

def generar_mensaje_cripto(coin_data, favoritas_data):
    try:
        mensaje = "🧠 <b>CENTRAL DE INTELIGENCIA (GEMINI AI)</b>\n"
        total_analizadas = coin_data.get('total_analizadas', 399) if coin_data else 399
        mensaje += f"📊 Analizadas: {total_analizadas} altcoins de Binance (< $1 USD)\n\n"
        
        # 1. TOP 5 GANADORAS
        mensaje += "🚀 <b>TOP 5 GANADORAS</b>\n"
        ganadoras = coin_data.get('top_ganadoras', []) if coin_data else []
        for coin in ganadoras[:5]:
            sym = coin.get('symbol', 'N/A')
            prc = coin.get('price', 0)
            chg = coin.get('change', 0)
            prc_str = fmt_price(prc)
            url_ia = f"{BASE_URL}/?coin={sym}&price={prc_str}&change={chg}"
            
            mensaje += (
                f"• <b>{sym}</b> | ${prc_str} | {coin.get('barra', '🟩🟩🟩🟩🟩')} | +{chg}%\n"
                f"  └ 📊 <a href='{url_ia}'>Resumen IA</a> | 🔶 <a href='{coin.get('url_trade', '#')}'>Tradear</a>\n"
            )
        mensaje += "\n"

        # 2. TOP 5 GEMAS EN ACUMULACIÓN
        mensaje += "💎 <b>TOP 5 GEMAS EN ACUMULACIÓN (< $1.00 USD)</b>\n"
        acumulacion = coin_data.get('top_acumulacion', []) if coin_data else []
        for coin in acumulacion[:5]:
            sym = coin.get('symbol', 'N/A')
            prc = coin.get('price', 0)
            chg = coin.get('change', 0)
            prc_str = fmt_price(prc)
            url_ia = f"{BASE_URL}/?coin={sym}&price={prc_str}&change={chg}"
            
            mensaje += (
                f"• 🟢 <b>{sym}</b> | ${prc_str} | Cambio: {chg}% | Vol: ${coin.get('vol_fmt', '0')}\n"
                f"  └ 📊 <a href='{url_ia}'>Resumen IA</a> | 🔶 <a href='{coin.get('url_trade', '#')}'>Tradear</a>\n"
            )
        mensaje += "\n"

        # 3. TOP 5 PERDEDORAS
        mensaje += "📉 <b>TOP 5 PERDEDORAS (Zonas de Rebote)</b>\n"
        perdedoras = coin_data.get('top_perdedoras', []) if coin_data else []
        for coin in perdedoras[:5]:
            sym = coin.get('symbol', 'N/A')
            prc = coin.get('price', 0)
            chg = coin.get('change', 0)
            prc_str = fmt_price(prc)
            url_ia = f"{BASE_URL}/?coin={sym}&price={prc_str}&change={chg}"
            
            mensaje += (
                f"• <b>{sym}</b> | ${prc_str} | {coin.get('barra', '🟥🟥🟥🟥🟥')} | {chg}%\n"
                f"  └ 📊 <a href='{url_ia}'>Resumen IA</a> | 🔶 <a href='{coin.get('url_trade', '#')}'>Tradear</a>\n"
            )
        mensaje += "\n"

        # 4. ESTADO DE TUS FAVORITAS
        mensaje += "⭐ <b>ESTADO DE TUS FAVORITAS</b>\n"
        favoritas = favoritas_data if favoritas_data else []
        for fav in favoritas[:5]:
            sym = fav.get('symbol', 'N/A')
            prc = fav.get('price', 0)
            chg = fav.get('change', 0)
            prc_str = fmt_price(prc)
            url_ia = f"{BASE_URL}/?coin={sym}&price={prc_str}&change={chg}"
            
            try:
                chg_float = float(str(chg).replace('%', '').strip())
            except:
                chg_float = 0.0
                
            icono = "🟢" if chg_float >= 0 else "🔴"
            
            mensaje += (
                f"• {icono} <b>{sym}</b> | ${prc_str} ({chg}%)\n"
                f"  └ 📊 <a href='{url_ia}'>Resumen IA</a> | 🔶 <a href='{fav.get('url_trade', '#')}'>Tradear</a>\n"
            )

        return mensaje

    except Exception as e:
        print(f"Error generando mensaje del bot: {e}")
        return "⚠️ Error al generar el reporte técnico en este momento."

def enviar_a_telegram(mensaje):
    """Función obligatoria para disparar el mensaje hacia la API de Telegram"""
    token = os.environ.get("TELEGRAM_TOKEN")
    # Toma CHAT_ID que es el nombre configurado en tus secretos de GitHub
    chat_id = os.environ.get("CHAT_ID") or os.environ.get("TELEGRAM_CHAT_ID")
    
    if not token or not chat_id:
        print("❌ Error crítico: Faltan las variables de entorno TELEGRAM_TOKEN o CHAT_ID.")
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

# ==========================================
# BLOQUE DE EJECUCIÓN PRINCIPAL
# ==========================================
if __name__ == "__main__":
    print("🤖 Iniciando proceso del bot de criptomonedas...")
    
    # 1. Aquí se obtienen tus datos reales (Asegurate de mantener tus funciones de Binance/favoritas aquí arriba o abajo según tu estructura)
    # coin_data = obtener_datos_desde_binance() 
    # favoritas_data = obtener_estado_favoritas()
    
    # 2. Se genera el texto consolidado
    texto_final = generar_mensaje_cripto(coin_data, favoritas_data)
    
    # 3. 🚀 SE ENVÍA AUTOMÁTICAMENTE A TELEGRAM
    enviar_a_telegram(texto_final)
