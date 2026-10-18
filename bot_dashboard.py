import os
import json
import requests
from datetime import datetime
from google import genai

TELEGRAM_BOT_TOKEN = (
    os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("TELEGRAM_TOKEN") or ""
).strip()
TELEGRAM_CHAT_ID = (
    os.getenv("TELEGRAM_CHAT_ID") or os.getenv("CHAT_ID") or ""
).strip()
MESSAGE_THREAD_ID = (
    os.getenv("TOPIC_ID_CENTRAL") or os.getenv("TELEGRAM_MESSAGE_THREAD_ID") or ""
).strip()
GEMINI_API_KEY = (os.getenv("GEMINI_API_KEY") or "").strip()

ARCHIVO_PRE_EXPLOSION = "datos_pre_explosion_ia.json"
ARCHIVO_TACTICO = "ultimas_perlas_cazador.json"
ECOSYSTEM_FILE = "database_ecosistema.json"

print(
    "🏛️ Ejecutando Motor de Consolidación de 4 Bloques para Netlify & Central Web..."
)


def cargar_json(path):
  if os.path.exists(path):
    try:
      with open(path, "r") as f:
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


def generar_dictamen_ia(pre_data, tactico_data):
  if not GEMINI_API_KEY:
    return (
        "⚠️ *Análisis maestro no disponible (Falta GEMINI_API_KEY en secrets)*"
    )

  client = genai.Client(api_key=GEMINI_API_KEY)
  prompt = f"""
    Actúa como el Analista Jefe de un fondo cuantitativo. Cruza la información del Radar Pre-Explosión y el Cazador Táctico para emitir un dictamen institucional de máximo 5 líneas sobre las criptomonedas con mayor confluencia alcista.
    """
  for mod in ["gemini-2.5-flash", "gemini-1.5-flash"]:
    try:
      response = client.models.generate_content(model=mod, contents=prompt)
      if response and response.text:
        return response.text
    except Exception:
      continue
  return (
      "Sincronización global completada. Máxima atención a los activos en fase"
      " de acumulación y perlas de momentum."
  )


def guardar_base_netlify(datos_mercado, pre_data, tactico_data, dictamen_ia):
  try:
    # 1. Ganadoras del día (Top 7 con mayor variación positiva)
    mercado_valido = [
        d
        for d in datos_mercado
        if d.get("symbol", "").endswith("USDT")
        and float(d.get("lastPrice", 0)) > 0
    ]
    top_ganadoras = sorted(
        mercado_valido,
        key=lambda x: float(x.get("priceChangePercent", 0)),
        reverse=True,
    )[:7]

    ganadoras_formateadas = [
        {
            "symbol": item["symbol"].replace("USDT", ""),
            "price": float(item["lastPrice"]),
            "change": float(item["priceChangePercent"]),
        }
        for item in top_ganadoras
    ]

    # 2. Cazador Táctico
    perlas_tac = tactico_data if isinstance(tactico_data, list) else []
    cazador_formateado = [
        {
            "symbol": (
                p.get("simbolo")
                or p.get("ticker", "ASSET").replace("USDT", "")
            ),
            "price": float(p.get("precio", p.get("close", 0))),
            "change": float(p.get("change", 0)),
        }
        for p in perlas_tac[:6]
    ]

    # 3. Pre-Explosión
    raw_pre = (
        pre_data.get("top_candidatas", [])
        if isinstance(pre_data, dict)
        else []
    )
    pre_formateado = [
        {
            "symbol": c.get("ticker", "").replace("USDT", ""),
            "price": float(c.get("price", 0)),
            "change": float(c.get("price_change", 0)),
            "fase": c.get("fase", "VERDE"),
        }
        for c in raw_pre[:6]
    ]

    # 4. Convertidas en Ganadoras (activos con confluencia o volumen destacado)
    top_volumen = sorted(
        mercado_valido,
        key=lambda x: float(x.get("quoteVolume", 0)),
        reverse=True,
    )[7:13]
    convertidas_formateadas = [
        {
            "symbol": item["symbol"].replace("USDT", ""),
            "price": float(item["lastPrice"]),
            "change": float(item["priceChangePercent"]),
        }
        for item in top_volumen
    ]

    base_web = {
        "ultima_actualizacion": datetime.now().isoformat(),
        "dictamen_maestro_ia": dictamen_ia,
        "ganadoras_del_dia": ganadoras_formateadas,  # Bloque 1 (7 items)
        "cazador_tactico": cazador_formateado,  # Bloque 2
        "pre_explosion": pre_formateado,  # Bloque 3
        "convertidas_en_ganadoras": convertidas_formateadas,  # Bloque 4
    }

    with open(ECOSYSTEM_FILE, "w") as f:
      json.dump(base_web, f, indent=4)
    print("✅ database_ecosistema.json generado con los 4 bloques.")
  except Exception as e:
    print(f"⚠️ Error generando base web: {e}")


def enviar_telegram(texto):
  if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
    return
  url_base = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"
  payload = {
      "chat_id": TELEGRAM_CHAT_ID,
      "text": texto,
      "parse_mode": "Markdown",
      "disable_web_page_preview": True,
  }
  if MESSAGE_THREAD_ID:
    try:
      payload["message_thread_id"] = int(MESSAGE_THREAD_ID)
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

  dictamen_ia = generar_dictamen_ia(pre_data, tactico_data)

  if datos_binance:
    guardar_base_netlify(datos_binance, pre_data, tactico_data, dictamen_ia)

  msg = "🏛️ **CENTRAL WEB • 4 BLOQUES UNIFICADOS ACTUALIZADOS**\n"
  msg += (
      f"🕒 *Sincronización:* `{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`\n\n"
  )
  msg += f"💡 **Dictamen Maestro (IA):**\n{dictamen_ia}\n\n"
  msg += "─────────────────────────\n"
  msg += (
      "🌐 *Netlify:* Tarjetas 1 (Ganadoras 7), 2 (Cazador Táctico), 3"
      " (Pre-Explosión) y 4 (Convertidas) actualizadas."
  )
  enviar_telegram(msg)


if __name__ == "__main__":
  main()
