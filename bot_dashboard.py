import json
import os
import urllib.request
from datetime import datetime

DB_FILE = "database_ecosistema.json"

def obtener_precios_binance():
    """Consulta los precios Spot actuales desde la API pública de Binance."""
    url = "https://api.binance.com/api/v3/ticker/price"
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req) as response:
            data = json.loads(response.read().decode())
            return {item['symbol']: float(item['price']) for item in data}
    except Exception as e:
        print(f"Error al consultar Binance: {e}")
        return {}

def procesar_dashboard():
    print("🤖 Iniciando actualización del Bot Dashboard y Auditoría...")
    precios_actuales = obtener_precios_binance()

    # 1. Intentar leer los datos recientes del Pre-Explosión si existen
    pre_explosion_data = []
    if os.path.exists("datos_pre_explosion_ia.json"):
        try:
            with open("datos_pre_explosion_ia.json", "r", encoding="utf-8") as f:
                pre_explosion_data = json.load(f)
        except Exception:
            pass

    # 2. Cargar base de datos existente o inicializar estructura
    db = {
        "ultima_actualizacion": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "sentimiento_mercado": "VERDE",
        "incubadora_cazador": [],
        "alertas_pre_explosion": pre_explosion_data,
        "ganadoras_dia": []
    }

    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r", encoding="utf-8") as f:
                old_db = json.load(f)
                db["incubadora_cazador"] = old_db.get("incubadora_cazador", [])
        except Exception:
            pass

    # (Ejemplo de simulación de adición desde el Cazador Táctico si se ejecuta)
    # Si quieres añadir tokens base de prueba o conectar con tus listas:
    tokens_ejemplo = [
        {"symbol": "TRXUSDT", "precio_inicial": 0.3324},
        {"symbol": "RSRUSDT", "precio_inicial": 0.00196},
        {"symbol": "AVAUSDT", "precio_inicial": 0.2819},
        {"symbol": "STXUSDT", "precio_inicial": 0.4260}
    ]

    existentes = {item["symbol"] for item in db["incubadora_cazador"]}
    for t in tokens_ejemplo:
        if t["symbol"] not in existentes:
            db["incubadora_cazador"].append({
                "symbol": t["symbol"],
                "fecha_ingreso": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "precio_inicial": t["precio_inicial"],
                "precio_actual": t["precio_inicial"],
                "pnl_pct": 0.0,
                "fase_actual": "🟢 INCUBACIÓN",
                "es_ganadora": False
            })

    # 3. Reevaluar precios actuales y calcular rendimiento (% PnL)
    ganadoras = []
    for item in db["incubadora_cazador"]:
        sym = item["symbol"]
        p_actual = precios_actuales.get(sym, item["precio_actual"])
        item["precio_actual"] = p_actual
        
        if item["precio_inicial"] > 0:
            pnl = ((p_actual - item["precio_inicial"]) / item["precio_inicial"]) * 100
            item["pnl_pct"] = round(pnl, 2)
        
        # Asignar fase según comportamiento de mercado
        if item["pnl_pct"] >= 15.0:
            item["fase_actual"] = "🏆 GANADORA"
            item["es_ganadora"] = True
            ganadoras.append(item)
        elif item["pnl_pct"] >= 5.0:
            item["fase_actual"] = "🔴 FASE ROJA (Explotando)"
        elif item["pnl_pct"] >= 1.0:
            item["fase_actual"] = "🟡 FASE AMARILLA (Acumulando)"
        else:
            item["fase_actual"] = "🟢 FASE VERDE (Vigilancia)"

    db["ganadoras_dia"] = ganadoras

    # 4. Guardar archivo consolidado para la web
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(db, f, indent=4, ensure_ascii=False)
    
    print("✅ Base de datos del dashboard actualizada correctamente.")

if __name__ == "__main__":
    procesar_dashboard()
