import os
import json
import requests
from datetime import datetime

# Archivos de la base de datos
DB_ECOSISTEMA = "database_ecosistema.json"
PRE_EXPLOSION_FILE = "datos_pre_explosion_ia.json"

# Configuración Telegram
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "-1003937091631")
TELEGRAM_THREAD_ID = os.getenv("TELEGRAM_MESSAGE_THREAD_ID", "2711")

def obtener_precio_binance(symbol):
    try:
        url = f"https://api.binance.com/api/v3/ticker/price?symbol={symbol.upper()}"
        res = requests.get(url, timeout=5)
        if res.status_code == 200:
            return float(res.json()['price'])
    except Exception as e:
        print(f"Error consultando precio para {symbol}: {e}")
    return None

def cargar_json(filepath):
    if os.path.exists(filepath):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"Error cargando {filepath}: {e}")
    return {}

def guardar_json(filepath, data):
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

def procesar_ecosistema():
    # Cargar o inicializar la base de datos unificada
    data_eco = cargar_json(DB_ECOSISTEMA)
    if not data_eco:
        data_eco = {
            "sentimiento_mercado": "VERDE",
            "ultima_actualizacion": "",
            "incubadora_cazador": [],
            "ganadoras_dia": [],
            "alertas_pre_explosion": []
        }

    # Cargar datos de Pre-Explosión si existen
    pre_data = cargar_json(PRE_EXPLOSION_FILE)
    if pre_data and "alertas" in pre_data:
        data_eco["alertas_pre_explosion"] = pre_data["alertas"]

    # Sincronizar y actualizar precios de la Incubadora
    incubadora_actualizada = []
    ganadoras = data_eco.get("ganadoras_dia", [])

    for item in data_eco.get("incubadora_cazador", []):
        symbol = item["symbol"]
        precio_init = float(item["precio_inicial"])
        precio_actual = obtener_precio_binance(symbol) or float(item.get("precio_actual", precio_init))
        
        # Calcular PnL %
        pnl = round(((precio_actual - precio_init) / precio_init) * 100, 2)
        
        # Definir Fase según PnL
        fase = "FASE VERDE 🟢 (En rango)"
        if pnl <= -5:
            fase = "FASE ROJA 🔴 (Stop Loss/Alerta)"
        elif pnl >= 15:
            fase = "FASE DORADA 🏆 (Ganadora Confirmada)"
            # Mover a ganadoras si no está registrada
            if not any(g['symbol'] == symbol for g in ganadoras):
                ganadoras.append({
                    "symbol": symbol,
                    "precio_inicial": precio_init,
                    "pnl_pct": pnl
                })

        item["precio_actual"] = precio_actual
        item["pnl_pct"] = pnl
        item["fase_actual"] = fase
        incubadora_actualizada.append(item)

    data_eco["incubadora_cazador"] = incubadora_actualizada
    data_eco["ganadoras_dia"] = ganadoras
    data_eco["ultima_actualizacion"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Guardar base de datos consolidada
    guardar_json(DB_ECOSISTEMA, data_eco)
    print("✅ Base de datos del ecosistema actualizada.")
    
    # Notificar a Telegram
    enviar_telegram(data_eco)

def enviar_telegram(data):
    if not TELEGRAM_BOT_TOKEN:
        print("⚠️ TELEGRAM_BOT_TOKEN no configurado. Omitiendo notificación.")
        return

    url_netlify = "https://musical-entremet-ebb9ad.netlify.app"
    mensaje = (
        "🧠 **CENTRAL DE INTELIGENCIA Y AUDITORÍA ACTUALIZADA**\n\n"
        f"📊 **Mercado:** {data.get('sentimiento_mercado', 'VERDE')}\n"
        f"🎯 **Monedas en Incubadora:** {len(data.get('incubadora_cazador', []))}\n"
        f"🏆 **Ganadoras Confirmadas:** {len(data.get('ganadoras_dia', []))}\n\n"
        f"🌐 **Ver Dashboard en vivo:** {url_netlify}"
    )

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "message_thread_id": TELEGRAM_THREAD_ID,
        "text": mensaje,
        "parse_mode": "Markdown"
    }

    try:
        res = requests.post(url, json=payload, timeout=10)
        if res.status_code == 200:
            print("✅ Reporte publicado en Telegram correctamente.")
        else:
            print(f"⚠️ Respuesta de Telegram: {res.text}")
    except Exception as e:
        print(f"❌ Error conectando con Telegram: {e}")

if __name__ == "__main__":
    procesar_ecosistema()
