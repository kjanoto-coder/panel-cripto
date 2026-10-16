import json
import os
import urllib.request
from datetime import datetime

DB_FILE = "database_ecosistema.json"

def obtener_precios_binance():
    url = "https://api.binance.com/api/v3/ticker/price"
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req) as response:
            data = json.loads(response.read().decode())
            return {item['symbol']: float(item['price']) for item in data}
    except Exception as e:
        print(f"Error al consultar Binance: {e}")
        return {}

def actualizar_ecosistema():
    # Cargar datos previos de pre-explosión si existen
    pre_explosion_data = []
    if os.path.exists("datos_pre_explosion_ia.json"):
        with open("datos_pre_explosion_ia.json", "r", encoding="utf-8") as f:
            try:
                pre_explosion_data = json.load(f)
            except:
                pass

    precios_actuales = obtener_precios_binance()
    
    # Cargar base de datos general existente o crear estructura base
    db = {
        "ultima_actualizacion": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "sentimiento_mercado": "VERDE",
        "incubadora_cazador": [],
        "alertas_pre_explosion": pre_explosion_data,
        "ganadoras_dia": []
    }
    
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r", encoding="utf-8") as f:
            try:
                old_db = json.load(f)
                db["incubadora_cazador"] = old_db.get("incubadora_cazador", [])
            except:
                pass

    # Simular entrada desde el bot táctico (puedes adaptarlo para leer tus otros JSONs)
    # Aquí actualizamos precios y calculamos PnL de la incubadora
    ganadoras = []
    for item in db["incubadora_cazador"]:
        sym = item["symbol"]
        p_actual = precios_actuales.get(sym, item["precio_actual"])
        item["precio_actual"] = p_actual
        if item["precio_inicial"] > 0:
            pnl = ((p_actual - item["precio_inicial"]) / item["precio_inicial"]) * 100
            item["pnl_pct"] = round(pnl, 2)
        
        if item["pnl_pct"] >= 15.0:
            item["fase_actual"] = "🏆 GANADORA"
            item["es_ganadora"] = True
            ganadoras.append(item)
        elif item["pnl_pct"] >= 5.0:
            item["fase_actual"] = "🔴 FASE ROJA"
        elif item["pnl_pct"] >= 1.0:
            item["fase_actual"] = "🟡 FASE AMARILLA"
        else:
            item["fase_actual"] = "🟢 FASE VERDE"

    db["ganadoras_dia"] = ganadoras

    # Guardar la base de datos unificada
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(db, f, indent=4, ensure_ascii=False)
    print("Base de datos del ecosistema actualizada.")

if __name__ == "__main__":
    actualizar_ecosistema()
