BASE_URL = "https://gregarious-frangollo-0346c5.netlify.app"

def generar_mensaje_cripto(coin_data, favoritas_data):
    try:
        mensaje = "🧠 <b>CENTRAL DE INTELIGENCIA (GEMINI AI)</b>\n"
        total_analizadas = coin_data.get('total_analizadas', 399) if coin_data else 399
        mensaje += f"📊 Analizadas: {total_analizadas} altcoins de Binance (< $1 USD)\n\n"
        
        # Función auxiliar blindada contra símbolos y errores
        def fmt_price(p):
            if p is None:
                return "0.00"
            try:
                # Limpiar signos de peso, espacios o comas por si vienen sucios
                p_limpio = str(p).replace('$', '').replace(',', '').strip()
                p_float = float(p_limpio)
                if p_float < 1:
                    return f"{p_float:.8f}".rstrip('0').rstrip('.')
                return f"{p_float:.2f}"
            except Exception:
                return str(p)

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
