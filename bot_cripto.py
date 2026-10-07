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
    """Se conecta a múltiples nodos oficiales de Binance para esquivar bloqueos en la nube"""
    endpoints = [
        "https://api1.binance.com/api/v3/ticker/24hr",
        "https://api2.binance.com/api/v3/ticker/24hr",
        "https://api3.binance.com/api/v3/ticker/24hr",
        "https://api.binance.com/api/v3/ticker/24hr"
    ]
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    
    for url in endpoints:
        try:
            response = requests.get(url, headers=headers, timeout=10)
            if response.status_code == 200:
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
                
                if altcoins:
                    ganadoras = sorted(altcoins, key=lambda x: x['change'], reverse=True)[:5]
                    for g in ganadoras:
                        g['barra'] = '🟩🟩🟩🟩🟩'
                        
                    perdedoras = sorted(altcoins, key=lambda x: x['change'])[:5]
                    for p in perdedoras:
                        p['barra'] = '🟥🟥🟥🟥🟥'
                        
                    acumulacion = sorted(altcoins, key=lambda x: x['volume'], reverse=True)[:5]
                    for a in acumulacion:
                        a['vol_fmt'] = f"{a['volume']:,.0f}"

                    print(f"✅ Conexión exitosa a nodo de Binance. Altcoins analizadas: {len(altcoins)}")
                    return {
                        'total_analizadas': len(altcoins),
                        'top_ganadoras': ganadoras,
                        'top_acumulacion': acumulacion,
                        'top_perdedoras': perdedoras
                    }
        except Exception as e:
            continue
            
    print("❌ Error crítico: Ningún nodo de Binance respondió a la petición.")
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
    mensaje += "💎
