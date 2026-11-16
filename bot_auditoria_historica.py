import os
import json
import requests
from datetime import datetime, timezone, timedelta

TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
TOPIC_ID_AUDITORIA = os.getenv('TOPIC_ID_AUDITORIA') or os.getenv('TOPIC_ID_CENTRAL')

HISTORIAL_FILE = "datos_pre_explosion_ia.json"

print("📊 INICIANDO AUDITORÍA GLOBAL DE 'datos_pre_explosion_ia.json'...")

def obtener_precios_actuales():
    urls = [
        "https://api.binance.com/api/v3/ticker/24hr",
        "https://data-api.binance.vision/api/v3/ticker/24hr"
    ]
    for url in urls:
        try:
            res = requests.get(url, timeout=15)
            if res.status_code == 200:
                data = res.json()
                precios = {}
                for t in data:
                    sym = t.get('symbol')
                    if sym and sym.endswith('USDT'):
                        precios[sym] = float(t.get('lastPrice', 0))
                if precios:
                    return precios
        except Exception:
            continue
    return {}

def formatear_precio(precio):
    if precio >= 1.0:
        return f"${precio:.2f}"
    elif precio >= 0.01:
        return f"${precio:.4f}"
    elif precio >= 0.0001:
        return f"${precio:.6f}"
    else:
        return f"${precio:.8f}"

def enviar_telegram(mensaje):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("⚠️ Faltan credenciales de Telegram.")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        'chat_id': TELEGRAM_CHAT_ID,
        'text': mensaje,
        'parse_mode': 'Markdown',
        'disable_web_page_preview': True
    }
    if TOPIC_ID_AUDITORIA:
        try:
            payload['message_thread_id'] = int(TOPIC_ID_AUDITORIA)
        except ValueError:
            pass
    try:
        requests.post(url, json=payload, timeout=15)
        print("✅ Auditoría histórica enviada a Telegram con éxito.")
    except Exception as e:
        print(f"❌ Error enviando a Telegram: {e}")

def main():
    if not os.path.exists(HISTORIAL_FILE) or os.path.getsize(HISTORIAL_FILE) == 0:
        print("⚠️ El archivo 'datos_pre_explosion_ia.json' no existe o está vacío actualmente.")
        enviar_telegram("⚠️ *Auditoría Global:* El archivo `datos_pre_explosion_ia.json` está vacío en este momento. Esperando la próxima ejecución del bot principal para recopilar datos.")
        return

    try:
        with open(HISTORIAL_FILE, 'r', encoding='utf-8') as f:
            contenido = json.load(f)
    except Exception as e:
        print(f"❌ Error al leer el JSON: {e}")
        return

    registros = []
    if isinstance(contenido, dict):
        registros = contenido.get("top_candidatas", [])
    elif isinstance(contenido, list):
        registros = contenido

    if not registros:
        print("⚠️ El archivo JSON no contiene registros en 'top_candidatas'.")
        return

    precios_actuales = obtener_precios_actuales()
    if not precios_actuales:
        print("❌ No se pudieron obtener precios actuales de Binance.")
        return

    tz_arg = timezone(timedelta(hours=-3))
    hoy_str = datetime.now(tz_arg).strftime('%Y-%m-%d')
    hoy_dt = datetime.strptime(hoy_str, '%Y-%m-%d')

    timestamp_archivo = contenido.get("timestamp", hoy_str) if isinstance(contenido, dict) else hoy_str
    try:
        fecha_orig_str = timestamp_archivo.split('T')[0]
        fecha_orig_dt = datetime.strptime(fecha_orig_str, '%Y-%m-%d')
    except Exception:
        fecha_orig_dt = hoy_dt
        fecha_orig_str = hoy_str

    dias_transcurridos = max((hoy_dt - fecha_orig_dt).days, 0)

    resultados_por_color = {
        "ROJO": {"total": 0, "ganadoras": 0, "gemas": []},
        "AMARILLO": {"total": 0, "ganadoras": 0, "gemas": []},
        "VERDE": {"total": 0, "ganadoras": 0, "gemas": []}
    }

    for item in registros:
        ticker = item.get('ticker', '')
        sym = item.get('symbol', f"{ticker}USDT")
        precio_orig = float(item.get('price', 0))
        fase_raw = str(item.get('fase', 'VERDE')).upper()
        
        if "ROJO" in fase_raw:
            color = "ROJO"
        elif "AMARILLO" in fase_raw:
            color = "AMARILLO"
        else:
            color = "VERDE"

        if sym in precios_actuales and precio_orig > 0:
            precio_actual = precios_actuales[sym]
            rendimiento = ((precio_actual - precio_orig) / precio_orig) * 100
            es_ganadora = rendimiento >= 15.0

            item_info = {
                "ticker": ticker,
                "precio_orig": precio_orig,
                "precio_actual": precio_actual,
                "rendimiento": rendimiento
            }

            resultados_por_color[color]["total"] += 1
            if es_ganadora:
                resultados_por_color[color]["ganadoras"] += 1
            resultados_por_color[color]["gemas"].append(item_info)

    mensaje = f"📈 **AUDITORÍA DE PRE-EXPLOSIÓN (BACKTESTING)**\n"
    mensaje += f"📅 *Fecha de Origen:* `{fecha_orig_str}` (`{dias_transcurridos} días atrás`)\n"
    mensaje += f"📅 *Fecha de Corte:* `{hoy_str}`\n\n"

    etiquetas_color = {
        "ROJO": "🔴 *Fase Roja (Explosión Inminente)*",
        "AMARILLO": "🟡 *Fase Amarilla (Compresión)*",
        "VERDE": "🟢 *Fase Verde (Acumulación Silenciosa)*"
    }

    for color, datos_col in resultados_por_color.items():
        total = datos_col["total"]
        if total == 0:
            continue
        ganadoras = datos_col["ganadoras"]
        tasa_exito = (ganadoras / total * 100) if total > 0 else 0
        
        mensaje += f"{etiquetas_color[color]}\n"
        mensaje += f"📊 Registradas: `{total}` | Ganadoras (>15%): `{ganadoras}` (`{tasa_exito:.1f}%`)\n"
        
        if datos_col["gemas"]:
            mejores = sorted(datos_col["gemas"], key=lambda x: x['rendimiento'], reverse=True)[:3]
            mensaje += f"🏆 *Top Rendimiento Actual:*\n"
            for g in mejores:
                simbolo_res = "🚀" if g['rendimiento'] > 0 else "📉"
                mensaje += f"  • **{g['ticker']}**: `{formatear_precio(g['precio_orig'])}` ➔ `{formatear_precio(g['precio_actual'])}` | **{g['rendimiento']:+.1f}%** {simbolo_res}\n"
        mensaje += "\n"

    enviar_telegram(mensaje)

if __name__ == "__main__":
    main()
