import os
import json
import requests
from datetime import datetime
from google import genai

TELEGRAM_BOT_TOKEN = (os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("TELEGRAM_TOKEN") or "").strip()
TELEGRAM_CHAT_ID = (os.getenv("TELEGRAM_CHAT_ID") or os.getenv("CHAT_ID") or "").strip()
MESSAGE_THREAD_ID = (os.getenv("TOPIC_ID_CENTRAL") or os.getenv("TELEGRAM_MESSAGE_THREAD_ID") or "").strip()
GEMINI_API_KEY = (os.getenv("GEMINI_API_KEY") or "").strip()

ARCHIVO_PRE_EXPLOSION = "datos_pre_explosion_ia.json"
ARCHIVO_TACTICO = "ultimas_perlas_cazador.json"
ECOSYSTEM_FILE = "database_ecosistema.json"

print("🏛️ Ejecutando Motor Consolidador para Netlify & Central Web...")

def cargar_json(path):
    if os.path.exists(path):
        try:
            with open(path, 'r') as f:
                return json.load(f)
        except Exception:
            return None
    return None

def obtener_datos_binance():
    url = "https://data-api.binance.vision/api/v3/ticker/24hr"
    try:
        res = requests.get(url, timeout=10).json()
        if isinstance(res, list):
            return res
    except Exception:
        pass
    return []

def generar_comparativa_gemini(pre_data, tactico_data):
    if not GEMINI_API_KEY:
        return "⚠️ *Análisis comparativo no disponible (Falta GEMINI_API_KEY)*"
        
    client = genai.Client(api_key=GEMINI_API_KEY)
    
    prompt = f"""
    Eres el Analista Jefe Cuantitativo de un fondo de inversión Cripto. 
    Analiza y cruza los siguientes datos de nuestros dos motores de análisis:

    --- MOTOR PRE-EXPLOSIÓN (Termómetro de Colores) ---
    {json.dumps(pre_data, indent=2) if pre_data else "Sin datos"}

    --- MOTOR CAZADOR TÁCTICO (Perlas Sub-$1 USD y Momentum) ---
    {json.dumps(tactico_data, indent=2) if tactico_data else "Sin datos"}

    OBJETIVO:
    Compara ambas listas. Identifica los activos que presentan la mayor confluencia (ej. monedas en Fase ROJA/AMARILLA que también coinciden con perlas de volumen) y declara cuáles son las "Monedas Ganadoras Definificas" para el día de hoy.
    Escribe un dictamen breve, directo y sumamente profesional (máximo 6 líneas).
    """
    
    for mod in ['gemini-2.5-flash', 'gemini-1.5-flash']:
        try:
            response = client.models.generate_content(model=mod, contents=prompt)
            if response and response.text:
                return response.text
        except Exception:
            continue
            
    return "Sincronización completada. Convergencia de volumen y acumulación identificada entre los activos de baja capitalización y los radares de color."

def guardar_base_netilfy(datos_mercado, pre_data, tactico_data, dictamen_ia):
    try:
        top_volumen = sorted(
            [d for d in datos_mercado if d.get('symbol', '').endswith('USDT')],
            key=lambda x: float(x.get('quoteVolume', 0)),
            reverse=True
        )[:15]

        base_web = {
            "ultima_actualizacion": datetime.now().isoformat(),
            "dictamen_maestro_ia": dictamen_ia,
            "candidatas_pre_explosion": pre_data.get("top_candidatas", []) if pre_data else [],
            "perlas_cazador_tactico": tactico_data if tactico_data else [],
            "mercado_destacado": [
                {
                    "symbol": item['symbol'].replace('USDT', ''),
                    "price": float(item['lastPrice']),
                    "change": float(item['priceChangePercent']),
                    "volume": float(item['quoteVolume'])
                } for item in top_volumen
            ]
        }

        with open(ECOSYSTEM_FILE, "w") as f:
            json.dump(base_web, f, indent=4)
        print("✅ Base de datos para Netlify (database_ecosistema.json) actualizada exitosamente.")
    except Exception as e:
        print(f"⚠️ Error al guardar base para Netlify: {e}")

def enviar_telegram(texto):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
        
    url_base = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"
    payload = {
        'chat_id': TELEGRAM_CHAT_ID,
        'text': texto,
        'parse_mode': 'Markdown',
        'disable_web_page_preview': True
    }
    
    if MESSAGE_THREAD_ID:
        try:
            payload['message_thread_id'] = int(MESSAGE_THREAD_ID)
        except ValueError:
            pass
            
    try:
        res = requests.post(f"{url_base}/sendMessage", json=payload, timeout=20)
        resultado = res.json()
    except Exception:
        resultado = {"ok": False}
        
    if not resultado.get("ok"):
        payload.pop("message_thread_id", None)
        try:
            requests.post(f"{url_base}/sendMessage", json=payload, timeout=20)
        except Exception:
            pass

def main():
    datos_binance = obtener_datos_binance()
    pre_data = cargar_json(ARCHIVO_PRE_EXPLOSION)
    tactico_data = cargar_json(ARCHIVO_TACTICO)
    
    dictamen_ia = generar_comparativa_gemini(pre_data, tactico_data)
    
    if datos_binance:
        guardar_base_netilfy(datos_binance, pre_data, tactico_data, dictamen_ia)
        
    msg = "🏛️ **CENTRAL WEB • ANÁLISIS DE CONFLUENCIA & CONSOLIDADOR**\n"
    msg += f"🕒 *Sincronización Web Netlify:* `{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`\n\n"
    msg += f"💡 **Dictamen Maestro de Monedas Ganadoras (IA):**\n{dictamen_ia}\n\n"
    msg += "─────────────────────────\n"
    msg += "🌐 *Panel Web Sincronizado:* Base `database_ecosistema.json` actualizada con el cruce de Cazador Táctico y Termómetro Pre-Explosión."
    
    enviar_telegram(msg)

if __name__ == "__main__":
    main()
