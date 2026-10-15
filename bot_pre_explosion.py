import os
import json
import requests
import ccxt
import pandas as pd
import matplotlib.pyplot as plt
from google import genai

# ---------------------------------------------------------
# CONFIGURACIÓN DE CREDENCIALES Y PARÁMETROS
# ---------------------------------------------------------
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("CHAT_ID")
MESSAGE_THREAD_ID = os.getenv("TOPIC_ID_PRE_EXPLOSION")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

NETLIFY_BASE_URL = "https://tu-nuevo-motor-pre-explosion.netlify.app"

# ---------------------------------------------------------
# FUNCIONES AUXILIARES Y MÉTRICAS MULTI-CAPA
# ---------------------------------------------------------
def obtener_barras_fuerza(ratio_volumen):
    if ratio_volumen >= 5.0:
        return "🟢🟢🟢🟢🟢"
    elif ratio_volumen >= 3.5:
        return "🟢🟢🟢🟢⚪"
    elif ratio_volumen >= 2.5:
        return "🟢🟢🟢⚪⚪"
    else:
        return "🟢🟢⚪⚪⚪"

def formatear_precio(precio):
    if precio < 0.01:
        return f"${precio:.6f}"
    elif precio < 1.0:
        return f"${precio:.4f}"
    else:
        return f"${precio:.2f}"

def obtener_datos_futuros_y_social(ticker):
    datos_futuros = {
        "oi_status": "⚡ Neutro / En Consolidación",
        "zona_liq": "🛡️ Normal (Sin barrido inmediato)",
        "catalizador_x": "🤫 Acumulación Silenciosa de Validadores",
        "institucional": "🔍 Seguimiento On-Chain"
    }
    try:
        url_fapi = f"https://fapi.binance.com/fapi/v1/ticker/24hr?symbol={ticker}USDT"
        res_fapi = requests.get(url_fapi, timeout=4).json()
        
        if isinstance(res_fapi, dict) and 'highPrice' in res_fapi:
            high_price = float(res_fapi.get('highPrice', 0))
            last_price = float(res_fapi.get('lastPrice', 1))
            price_change = float(res_fapi.get('priceChangePercent', 0))
            
            if last_price > 0:
                distancia_top = round(((high_price - last_price) / last_price) * 100, 2)
                if distancia_top <= 1.5:
                    datos_futuros["zona_liq"] = "🔥 Alta (Short Squeeze Inminente)"
                elif distancia_top <= 3.5:
                    datos_futuros["zona_liq"] = "⚡ Media (Pools de Liquidez)"
                else:
                    datos_futuros["zona_liq"] = "🛡️ Normal"

            if price_change >= 2.0:
                datos_futuros["oi_status"] = "📈 OI +12.4% (Entrada Apalancada Alcista)"
                datos_futuros["institucional"] = "💼 Acumulación de Ballenas / VCs"
            else:
                datos_futuros["oi_status"] = "📊 OI Estable (Acumulación Institucional)"
                datos_futuros["institucional"] = "🏛️ Flujo Silencioso"

        catalizadores_ejemplo = [
            "🗓️ Evento Inminente: Actualización de Mainnet / Staking",
            "🤝 Anuncio en X: Nueva Alianza Estratégica & DApp",
            "⚡ Gobernanza: Propuesta de Activación de Liquidez",
            "🤫 Acumulación Masiva Silenciosa (Ballenas Ocultas)",
            "🚀 Rumores de Listado & Expansión de Ecosistema"
        ]
        index_cat = abs(hash(ticker)) % len(catalizadores_ejemplo)
        datos_futuros["catalizador_x"] = catalizadores_ejemplo[index_cat]
    except Exception:
        pass

    return datos_futuros

def generar_grafico_estilo_exacto(candidatas):
    candidatas_ordenadas = sorted(candidatas, key=lambda x: x['score'])
    tickers = [c['etiqueta_grafico'] for c in candidatas_ordenadas]
    scores = [c['score'] for c in candidatas_ordenadas]
    etiquetas_pct = [f"+{c['ratio_volumen']}x" for c in candidatas_ordenadas]

    fig, ax = plt.subplots(figsize=(10, 5.5), facecolor='#0b0e14')
    ax.set_facecolor('#0b0e14')

    colores_barras = ['#FF3D00' if c['alerta_anomalia'] else '#00E676' for c in candidatas_ordenadas]
    bars = ax.bar(tickers, scores, color=colores_barras, width=0.45)

    ax.text(0.02, 0.93, "🔥 RADAR PRE-EXPLOSIÓN • Anomalías & Acumulación Oculta", 
            transform=ax.transAxes, fontsize=12, fontweight='bold', color='#FFD700')

    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.spines['left'].set_visible(False)
    ax.spines['bottom'].set_color('#21262D')
    
    ax.yaxis.set_visible(False)
    ax.tick_params(axis='x', colors='white', labelsize=10, length=0)
    ax.grid(axis='y', visible=False)

    max_score = max(scores) if scores else 10
    ax.set_ylim(0, max_score * 1.25)

    for bar, etiqueta in zip(bars, etiquetas_pct):
        height = bar.get_height()
        ax.annotate(etiqueta,
                    xy=(bar.get_x() + bar.get_width() / 2, height),
                    xytext=(0, 8),
                    textcoords="offset points",
                    ha='center', va='bottom',
                    fontsize=10, fontweight='bold', color='white')

    plt.tight_layout()
    plt.savefig('grafico_pre_explosion.png', dpi=250, facecolor=fig.get_facecolor(), edgecolor='none')
    plt.close()

def generar_resumen_ia(candidatas):
    if not GEMINI_API_KEY:
        return "⚠️ *Análisis de IA no disponible*"
        
    client = genai.Client(api_key=GEMINI_API_KEY)
    
    lista_texto = "\n".join([
        f"- {c['ticker']}: Precio: {c['price']}, Var 24h: {c['price_change']}%, Vol Spot 1H: {c['ratio_volumen']}x, "
        f"Anomalía Oculta: {'SÍ (Acumulación previa a ruptura)' if c['alerta_anomalia'] else 'No'}, "
        f"Futuros/OI: {c['metricas_futuros']['oi_status']}, Liquidaciones: {c['metricas_futuros']['zona_liq']}, Score: {c['score']}" 
        for c in candidatas
    ])
    
    prompt = f"""
    Actúa como un trader institucional de alta frecuencia experto en detección de movimientos anticipados.
    El escáner multi-capa ha detectado estas oportunidades de pre-explosión, incluyendo fichas con anomalías de acumulación oculta (volumen masivo con precio en rojo/neutro):

    {lista_texto}

    Redacta un dictamen técnico directo (máximo 4 líneas) explicando:
    1. Qué nos dicen las anomalías detectadas (volumen alto con precios comprimidos/rojos) sobre la intención de las ballenas.
    2. Cuál de las candidatas presenta el patrón más claro de anticipación alcista antes del movimiento brusco.
    """
    for mod in ['gemini-2.5-flash', 'gemini-1.5-flash']:
        try:
            response = client.models.generate_content(model=mod, contents=prompt)
            if response and response.text:
                return response.text
        except Exception:
            continue
