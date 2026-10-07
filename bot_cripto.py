import os
import requests

# Dominio fijo de Netlify
BASE_URL = "https://gregarious-frangollo-0346c5.netlify.app"

def fmt_price(p):
    """Limpia símbolos y evita notación científica en precios muy bajos"""
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

def obtener_datos_binance():
    """Se conecta al endpoint público de Binance para evitar el bloqueo 451 en la nube"""
    url = "https://data-api.binance.vision/api/v3/ticker/24hr"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=15)
        if response.status_code != 200:
            print(f"❌ Error al conectar con Binance: {response.status_code}")
            return None
            
        tickers = response.json()
        altcoins = []
        
        for t in tickers:
            symbol = t.get('symbol', '')
            if symbol.endswith('USDT'):
                try:
                    price = float(t.get('lastPrice', 0))
                    change = float(t.get('priceChangePercent', 0))
                    volume = float(t.get('quoteVolume', 0))
                    
                    if 0 < price < 1.0:
                        altcoins.append({
                            'symbol': symbol.replace('USDT', ''),
                            'price': price,
                            'change': change,
                            'volume': volume,
                            'url_trade': f"https://www.binance.com/en/trade/{symbol}?type=spot"
                        })
                except:
                    continue
        
        if not altcoins:
            print("⚠️ No se encontraron altcoins bajo el filtro.")
            return None
            
        ganadoras = sorted(altcoins, key=lambda x: x['change'], reverse=True)[:5]
        for g in ganadoras:
            g['barra'] = '🟩🟩🟩🟩🟩'
            
        perdedoras = sorted(altcoins, key=lambda x: x['change'])[:5]
        for p in perdedoras:
            p['barra'] = '🟥🟥🟥🟥🟥'
            
        acumulacion = sorted(altcoins, key=lambda x: x['volume'], reverse=True)[:5]
        for a in acumulacion:
            a['vol_fmt'] = f"{a['volume']:,.0f}"

        print(f"✅ Conexión exitosa. Altcoins analizadas: {len(altcoins)}")
        return {
            'total_analizadas': len(altcoins),
            'top_ganadoras': ganadoras,
            'top_acumulacion': acumulacion,
            'top_perdedoras': perdedoras
        }
    except Exception as e:
        print(f"❌ Excepción al conectar con Binance: {e}")
        return None

def generar_mensaje_cripto(coin_data):
    if not coin_data:
        return "⚠️ Error: No se pudieron obtener datos de Binance para generar el reporte."
        
    mensaje = "🧠 <b>CENTRAL DE INTELIGENCIA (GEMINI AI)</b>\n"
    total_analizadas = coin_data.get('total_analizadas', 399)
    mensaje += f"📊 Analizadas: {total_analizadas} altcoins de Binance (< $1 USD)\n\n"
    
    # 1. TOP 5 GANADORAS
    mensaje += "🚀 <b>TOP 5 GANADORAS</b>\n"
    ganadoras = coin_data.get('top_ganadoras', [])
    for coin in ganadoras[:5]:
        sym = coin.get('symbol', 'N/A')
        prc = coin.get('price', 0)
        chg = coin.get('change', 0)
        prc_str = fmt_price(prc)
        url_ia = f"{BASE_URL}/?coin={sym}&price={prc_str}&change={chg}"
        
        mensaje += (
            f"• <b>{sym}</b> | ${prc_str} | {coin.get('barra', '🟩🟩🟩🟩🟩')} | +{chg:.2f}%\n"
            f"  └ 📊 <a href='{url_ia}'>Resumen IA</a> | 🔶 <a href='{coin.get('url_trade', '#')}'>Tradear</a>\n"
        )
    mensaje += "\n"

    # 2. TOP 5 GEMAS EN ACUMULACIÓN
    mensaje += "💎 <b>TOP 5 GEMAS EN ACUMULACIÓN (< $1.00 USD)</b>\n"
    acumulacion = coin_data.get('top_acumulacion', [])
    for coin in acumulacion[:5]:
        sym = coin.get('symbol', 'N/A')
        prc = coin.get('price', 0)
        chg = coin.get('change', 0)
        prc_str = fmt_price(prc)
        url_ia = f"{BASE_URL}/?coin={sym}&price={prc_str}&change={chg}"
        
        mensaje += (
            f"• 🟢 <b>{sym}</b> | ${prc_str} | Cambio: {chg:.2f}% | Vol: ${coin.get('vol_fmt', '0')}\n"
            f"  └ 📊 <a href='{url_ia}'>Resumen IA</a> | 🔶 <a href='{coin.get('url_trade', '#')}'>Tradear</a>\n"
        )
    mensaje += "\n"

    # 3. TOP 5 PERDEDORAS
    mensaje += "📉 <b>TOP 5 PERDEDORAS (Zonas de Rebote)</b>\n"
    perdedoras = coin_data.get('top_perdedoras', [])
    for coin in perdedoras[:5]:
        sym = coin.get('symbol', 'N/A')
        prc = coin.get('price', 0)
        chg = coin.get('change', 0)
        prc_str = fmt_price(prc)
        url_ia = f"{BASE_URL}/?coin={sym}&price={prc_str}&change={chg}"
        
        mensaje += (
            f"• <b>{sym}</b> | ${prc_str} | {coin.get('barra', '🟥🟥🟥🟥🟥')} | {chg:.2f}%\n"
            f"  └ 📊 <a href='{url_ia}'>Resumen IA</a> | 🔶 <a href='{coin.get('url_trade', '#')}'>Tradear</a>\n"
        )
    mensaje += "\n"

    # 4. ESTADO DE FAVORITAS
    mensaje += "⭐ <b>ESTADO DE TUS FAVORITAS</b>\n"
    favoritas_ejemplo = ["LUNC", "TUT", "PEPE", "SHIB", "FLOKI"]
    all_market_coins = {c['symbol']: c for c in (ganadoras + acumulacion + perdedoras)}
    
    for sym in favoritas_ejemplo[:5]:
        if sym in all_market_coins:
            fav = all_market_coins[sym]
            prc_str = fmt_price(fav['price'])
            chg = fav['change']
            url_ia = f"{BASE_URL}/?coin={sym}&price={prc_str}&change={chg}"
            icono = "🟢" if chg >= 0 else "🔴"
            mensaje += (
                f"• {icono} <b>{sym}</b> | ${prc_str} ({chg:.2f}%)\n"
                f"  └ 📊 <a href='{url_ia}'>Resumen IA</a> | 🔶 <a href='{fav.get('url_trade', '#')}'>Tradear</a>\n"
            )
        else:
            url_ia = f"{BASE_URL}/?coin={sym}&price=0.00&change=0"
            mensaje += (
                f"• ⚪ <b>{sym}</b> | Sin datos recientes\n"
                f"  └ 📊 <a href='{url_ia}'>Resumen IA</a> | 🔶 <a href='#'>Tradear</a>\n"
            )

    return mensaje

def enviar_a_telegram(mensaje):
    token = os.environ.get("TELEGRAM_TOKEN")
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

if __name__ == "__main__":
    print("🤖 Iniciando proceso del bot de criptomonedas...")
    datos_mercado = obtener_datos_binance()
    texto_final = generar_mensaje_cripto(datos_mercado)
    enviar_a_telegram(texto_final)
