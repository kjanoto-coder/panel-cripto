def generar_mensaje_cripto(coin_data, favoritas_data):
    mensaje = "🧠 <b>CENTRAL DE INTELIGENCIA (GEMINI AI)</b>\n"
    mensaje += f"📊 Analizadas: {coin_data.get('total_analizadas', 399)} altcoins de Binance (< $1 USD)\n\n"
    
    # 1. TOP 5 GANADORAS
    mensaje += "🚀 <b>TOP 5 GANADORAS</b>\n"
    ganadoras = coin_data.get('top_ganadoras', [])[:5]  # Limita estrictamente a 5
    for coin in ganadoras:
        mensaje += (
            f"• <b>{coin.get('symbol')}</b> | ${coin.get('price')} | {coin.get('barra', '🟩🟩🟩🟩🟩')} | +{coin.get('change')}%\n"
            f"  └ 📊 <a href='{coin.get('url_ia', '#')}'>Resumen IA</a> | 🔶 <a href='{coin.get('url_trade', '#')}'>Tradear</a>\n"
        )
    mensaje += "\n"

    # 2. TOP 5 GEMAS EN ACUMULACIÓN
    mensaje += "💎 <b>TOP 5 GEMAS EN ACUMULACIÓN (< $1.00 USD)</b>\n"
    acumulacion = coin_data.get('top_acumulacion', [])[:5]  # Limita estrictamente a 5
    for coin in acumulacion:
        mensaje += (
            f"• 🟢 <b>{coin.get('symbol')}</b> | ${coin.get('price')} | Cambio: {coin.get('change')}% | Vol: ${coin.get('vol_fmt')}\n"
            f"  └ 📊 <a href='{coin.get('url_ia', '#')}'>Resumen IA</a> | 🔶 <a href='{coin.get('url_trade', '#')}'>Tradear</a>\n"
        )
    mensaje += "\n"

    # 3. TOP 5 PERDEDORAS
    mensaje += "📉 <b>TOP 5 PERDEDORAS (Zonas de Rebote)</b>\n"
    perdedoras = coin_data.get('top_perdedoras', [])[:5]  # Limita estrictamente a 5
    for coin in perdedoras:
        mensaje += (
            f"• <b>{coin.get('symbol')}</b> | ${coin.get('price')} | {coin.get('barra', '🟥🟥🟥🟥🟥')} | {coin.get('change')}%\n"
            f"  └ 📊 <a href='{coin.get('url_ia', '#')}'>Resumen IA</a> | 🔶 <a href='{coin.get('url_trade', '#')}'>Tradear</a>\n"
        )
    mensaje += "\n"

    # 4. ESTADO DE TUS FAVORITAS (Hasta 5)
    mensaje += "⭐ <b>ESTADO DE TUS FAVORITAS</b>\n"
    favoritas = favoritas_data[:5] if favoritas_data else []  # Limita estrictamente a 5
    for fav in favoritas:
        change = fav.get('change', 0)
        icono = "🟢" if change >= 0 else "🔴"
        mensaje += (
            f"• {icono} <b>{fav.get('symbol')}</b> | ${fav.get('price')} ({change}%)\n"
            f"  └ 📊 <a href='{fav.get('url_ia', '#')}'>Resumen IA</a> | 🔶 <a href='{fav.get('url_trade', '#')}'>Tradear</a>\n"
        )

    return mensaje
