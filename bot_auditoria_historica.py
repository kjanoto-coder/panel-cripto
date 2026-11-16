import os
import json
import requests
from datetime import datetime, timezone, timedelta

TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
TOPIC_ID_AUDITORIA = os.getenv('TOPIC_ID_AUDITORIA') or os.getenv('TOPIC_ID_CENTRAL')

HISTORIAL_FILE = "historial_perlas.json"

print("📊 INICIANDO AUDITORÍA HISTÓRICA GLOBAL DE PUNTA A PUNTA...")

def cargar_historial():
    if os.path.exists(HISTORIAL_FILE):
        try:
            with open(HISTORIAL_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"⚠️ Error al leer historial: {e}")
    return {}

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
        print("✅ Auditoría histórica global enviada a Telegram con éxito.")
    except Exception as e:
        print(f"❌ Error enviando a Telegram: {e}")

def main():
    historial = cargar_historial()
    registro_historico = historial.get("registro_historico", {})
    
    if not registro_historico:
        print("⚠️ El historial de perlas está vacío todavía.")
        return

    precios_actuales = obtener_precios_actuales()
    if not precios_actuales:
        print("❌ No se pudieron obtener precios actuales de Binance.")
        return

    tz_arg = timezone(timedelta(hours=-3))
    hoy_str = datetime.now(tz_arg).strftime('%Y-%m-%d')
    hoy_dt = datetime.strptime(hoy_str, '%Y-%m-%d')

    # Estructura para clasificar por color inicial
    resultados_por_color = {
        "ROJO": {"total": 0, "ganadoras": 0, "gemas": []},
        "AMARILLO": {"total": 0, "ganadoras": 0, "gemas": []},
        "VERDE": {"total": 0, "ganadoras": 0, "gemas": []}
    }

    for sym, data in registro_historico.items():
        ticker = sym.replace('USDT', '')
        fecha_orig_str = data.get("fecha_origen", hoy_str)
        precio_orig = data.get("precio_origen", 0)
        categoria_orig = data.get("categoria_origen", "VERDE")

        if sym in precios_actuales and precio_orig > 0:
            precio_actual = precios_actuales[sym]
            rendimiento = ((precio_actual - precio_orig) / precio_orig) * 100
            
            try:
                dias = (hoy_dt - datetime.strptime(fecha_orig_str, '%Y-%m-%d')).days
            except Exception:
                dias = 0
            dias = max(dias, 0)

            item_info = {
                "ticker": ticker,
                "dias": dias,
                "fecha": fecha_orig_str,
                "precio_orig": precio_orig,
                "precio_actual": precio_actual,
                "rendimiento": rendimiento,
                "es_ganadora": rendimiento >= 15.0 # Consideramos ganadora si supera el 15% de ROI histórico
            }

            if categoria_orig in resultados_por_color:
                resultados_por_color[categoria_orig]["total"] += 1
                if item_info["es_ganadora"]:
                    resultados_por_color[categoria_orig]["ganadoras"] += 1
                resultados_por_color[categoria_orig]["gemas"].append(item_info)

    # Construir el mensaje global para Telegram
    mensaje = f"📈 **BACKTESTING GLOBAL • HISTORIAL DE PUNTA A PUNTA**\n"
    mensaje += f"📅 *Fecha de Corte:* `{hoy_str}`\n"
    mensaje += f"🔬 *Auditoría científica de efectividad por color y tiempo de maduración*\n\n"

    etiquetas_color = {
        "ROJO": "🔴 *Fase Roja (Explosión Inminente)*",
        "AMARILLO": "🟡 *Fase Amarilla (Compresión)*",
        "VERDE": "🟢 *Fase Verde (Acumulación Silenciosa)*"
    }

    for color, datos_col in resultados_por_color.items():
        total = datos_col["total"]
        ganadoras = datos_col["ganadoras"]
        tasa_exito = (ganadoras / total * 100) if total > 0 else 0
        
        mensaje += f"{etiquetas_color[color]}\n"
        mensaje += f"📊 Total Registradas: `{total}` | Conversión a Ganadoras (>15%): `{ganadoras}` (`{tasa_exito:.1f}%`)\n"
        
        if datos_col["gemas"]:
            # Ordenar las mejores gemas de este color por rendimiento histórico
            mejores = sorted(datos_col["gemas"], key=lambda x: x['rendimiento'], reverse=True)[:3]
            mensaje += f"🏆 *Top Rendimiento Histórico:*\n"
            for g in mejores:
                simbolo_res = "🚀" if g['rendimiento'] > 0 else "📉"
                mensaje += f"  • **{g['ticker']}** ({g['dias']} días atrás | `{g['fecha']}`)\n"
                mensaje += f"    Or: `{formatear_precio(g['precio_orig'])}` ➔ Act: `{formatear_precio(g['precio_actual'])}` | **{g['rendimiento']:+.1f}%** {simbolo_res}\n"
        mensaje += "\n"

    mensaje += f"_💡 El sistema evalúa todo el ciclo de vida desde el primer registro guardado en el JSON._"
    enviar_telegram(mensaje)

if __name__ == "__main__":
    main()
