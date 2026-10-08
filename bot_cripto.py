def preparar_datos(tickers):
    usdt_pairs = [t for t in tickers if t['symbol'].endswith('USDT') and not any(x in t['symbol'] for x in ['UP', 'DOWN', 'BULL', 'BEAR'])]
    
    # Top 7 Ganadoras
    ganadoras = sorted(usdt_pairs, key=lambda x: float(x['priceChangePercent']), reverse=True)[:7]
    
    # Top 7 Acumulación (< $1 USD)
    acumulacion_pool = [t for t in usdt_pairs if float(t['lastPrice']) < 1.0]
    acumulacion = sorted(acumulacion_pool, key=lambda x: float(x['quoteVolume']), reverse=True)[:7]
    
    # Top 7 Perdedoras
    perdedoras = sorted(usdt_pairs, key=lambda x: float(x['priceChangePercent']))[:7]
    
    # Tus 5 favoritas actualizadas con tus capturas (QI, TUT, NEIRO, LUNC, BANK)
    favoritas_simbolos = ['QI', 'TUT', 'NEIRO', 'LUNC', 'BANK']
    favoritas = []
    for sim in favoritas_simbolos:
        match = next((t for t in usdt_pairs if t['symbol'] == f"{sim}USDT"), None)
        if match:
            favoritas.append(match)
            
    return ganadoras, acumulacion, perdedoras, favoritas
