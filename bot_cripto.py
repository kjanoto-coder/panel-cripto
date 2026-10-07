BASE_URL = "https://gregarious-frangollo-0346c5.netlify.app"

def generar_mensaje_cripto(coin_data, favoritas_data):
    mensaje = "🧠 <b>CENTRAL DE INTELIGENCIA (GEMINI AI)</b>\n"
    mensaje += f"📊 Analizadas: {coin_data.get('total_analizadas', 399)} altcoins de Binance (< $1 USD)\n\n"
    
    # Función auxiliar para limpiar ceros y evitar notación científica en precios muy chicos
    def fmt_price(p):
        try:
            p_float = float(p)
            if p_float < 1:
                return f"{p_float:.8f}".rstrip('0').rstrip('.')
            return f"{p_float:.2f}"
        except:
            return str(p)

    # 1. TOP 5 GANADORAS
    mensaje += "🚀 <b>TOP 5 GANADORAS</b>\n"
    ganadoras = coin_data.get('top_ganadoras', [])[:5]  # Estrictamente 5
    for coin in ganadoras:
        sym = coin.get('symbol')
        prc = coin.get('price')
        chg = coin.get('change')
        prc_str = fmt_price(prc)
        url_ia = f"{BASE_URL}/?coin={sym}&price={prc_str}&change={chg}"
        
        mensaje += (
            f"• <b>{sym}</b> | ${prc_str} | {coin.get('barra', '🟩🟩🟩🟩🟩')} | +{chg}%\n"
            f"  └ 📊 <a href='{url_ia}'>Resumen IA</a> | 🔶 <a href='{coin.get('url_trade', '#')}'>Tradear</a>\n"
        )
    mensaje += "\n"

    # 2. TOP 5 GEMAS EN ACUMULACIÓN
    mensaje += "💎 <b>TOP 5 GEMAS EN ACUMULACIÓN (< $1.00 USD)</b>\n"
    acumulacion = coin_data.get('top_acumulacion', [])[:5]  # Estrictamente 5
    for coin in acumulacion:
        sym = coin.get('symbol')
        prc = coin.get('price')
        chg = coin.get('change')
        prc_str = fmt_price(prc)
        url_ia = f"{BASE_URL}/?coin={sym}&price={prc_str}&change={chg}"
        
        mensaje += (
            f"• 🟢 <b>{sym}</b> | ${prc_str} | Cambio: {chg}% | Vol: ${coin.get('vol_fmt')}\n"
            f"  └ 📊 <a href='{url_ia}'>Resumen IA</a> | 🔶 <a href='{coin.get('url_trade', '#')}'>Tradear</a>\n"
        )
    mensaje += "\n"

    # 3. TOP 5 PERDEDORAS
    mensaje += "📉 <b>TOP 5 PERDEDORAS (Zonas de Rebote)</b>\n"
    perdedoras = coin_data.get('top_perdedoras', [])[:5]  # Estrictamente 5
    for coin in perdedoras:
        sym = coin.get('symbol')
        prc = coin.get('price')
        chg = coin.get('change')
        prc_str = fmt_price(prc)
        url_ia = f"{BASE_URL}/?coin={sym}&price={prc_str}&change={chg}"
        
        mensaje += (
            f"• <b>{sym}</b> | ${prc_str} | {coin.get('barra', '🟥🟥🟥🟥🟥')} | {chg}%\n"
            f"  └ 📊 <a href='{url_ia}'>Resumen IA</a> | 🔶 <a href='{coin.get('url_trade', '#')}'>Tradear</a>\n"
        )
    mensaje += "\n"

    # 4. ESTADO DE TUS FAVORITAS (Hasta 5)
    mensaje += "⭐ <b>ESTADO DE TUS FAVORITAS</b>\n"
    favoritas = favoritas_data[:5] if favoritas_data else []  # Estrictamente 5
    for fav in favoritas:
        sym = fav.get('symbol')
        prc = fav.get('price')
        chg = fav.get('change', 0)
        prc_str = fmt_price(prc)
        url_ia = f"{BASE_URL}/?coin={sym}&price={prc_str}&change={chg}"
        icono = "🟢" if float(chg) >= 0 else "🔴"
        
        mensaje += (
            f"• {icono} <b>{sym}</b> | ${prc_str} ({chg}%)\n"
            f"  └ 📊 <a href='{url_ia}'>Resumen IA</a> | 🔶 <a href='{fav.get('url_trade', '#')}'>Tradear</a>\n"
        )

    return mensaje
