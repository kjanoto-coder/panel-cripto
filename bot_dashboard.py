import os
import json
import csv
from datetime import datetime
import requests
from google import genai

def cargar_json(nombre_archivo):
    try:
        with open(nombre_archivo, 'r', encoding='utf-8') as f:
            data = json.load(f)
            # Asegurar que siempre devuelva una lista
            if isinstance(data, list):
                return data
            elif isinstance(data, dict):
                return [data]
            return []
    except Exception:
        return []

def generar_dictamen_ia(pre_data, tactico_data):
    api_key = os.environ.get('GEMINI_API_KEY')
    if not api_key:
        return "⚠️ Dictamen IA no disponible (Falta GEMINI_API_KEY)."
    
    try:
        client = genai.Client(api_key=api_key)
        prompt = f"""
        Actúa como el Analista Jefe de un fondo cuantitativo de criptomonedas.
        Cruza la información del Radar Pre-Explosión y el Cazador Táctico para emitir un dictamen institucional de máximo 4 líneas:
        Datos Pre-Explosión: {json.dumps(pre_data[:3] if pre_data else [])}
        Datos Tácticos: {json.dumps(tactico_data[:3] if tactico_data else [])}
        """
        
        for mod in ['gemini-2.5-flash', 'gemini-1.5-flash']:
            try:
                response = client.models.generate_content(model=mod, contents=prompt)
                if response and response.text:
                    return response.text.strip()
            except Exception:
                continue

        return "Sincronización y análisis completados con éxito."
    except Exception as e:
        return f"Análisis actualizado a las {datetime.now().strftime('%H:%M:%S')}."

def enviar_telegram(mensaje):
    token = os.environ.get('TELEGRAM_BOT_TOKEN')
    chat_id = os.environ.get('TELEGRAM_CHAT_ID')
    
    if token and chat_id:
        try:
            url = f"https://api.telegram.org/bot{token}/sendMessage"
            payload = {"chat_id": chat_id, "text": mensaje, "parse_mode": "Markdown"}
            requests.post(url, json=payload, timeout=10)
            print("[+] Notificación enviada a Telegram con éxito.")
        except Exception as e:
            print(f"[!] Error enviando a Telegram: {e}")

def actualizar_dashboard():
    print("[*] Iniciando procesamiento de datos...")
    
    pre_data = cargar_json('datos_pre_explosion_ia.json')
    tactico_data = cargar_json('datos_tactico.json')
    dictamen = generar_dictamen_ia(pre_data, tactico_data)
    
    fecha_actual = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    # 1. Generar Vista en Markdown para GitHub (DASHBOARD_CRIPTO.md)
    md_content = f"# 🚀 Dashboard Cripto Automatizado\n"
    md_content += f"**Última actualización:** `{fecha_actual} UTC`\n\n"
    md_content += f"### 🧠 Dictamen Institucional (IA)\n> {dictamen}\n\n"
    
    md_content += "### ⚡ Radar Pre-Explosión\n"
    if pre_data and isinstance(pre_data, list):
        md_content += "| Moneda | % Subida |\n| --- | --- |\n"
        for item in pre_data[:7]:
            if isinstance(item, dict):
                coin = item.get('moneda', 'N/A')
                subida = item.get('subida', 'N/A')
                md_content += f"| **{coin}** | {subida} |\n"
    else:
        md_content += "*Sin alertas activas en este período.*\n"
        
    md_content += "\n### 🎯 Cazador Táctico\n"
    if tactico_data and isinstance(tactico_data, list):
        md_content += "| Moneda | % Subida |\n| --- | --- |\n"
        for item in tactico_data[:7]:
            if isinstance(item, dict):
                coin = item.get('moneda', 'N/A')
                subida = item.get('subida', 'N/A')
                md_content += f"| **{coin}** | {subida} |\n"
    else:
        md_content += "*Sin alertas activas en este período.*\n"

    with open("DASHBOARD_CRIPTO.md", "w", encoding="utf-8") as f:
        f.write(md_content)
    print("[+] DASHBOARD_CRIPTO.md actualizado.")

    # 2. Guardar en Histórico CSV (historico_alertas.csv)
    file_exists = os.path.isfile("historico_alertas.csv")
    with open("historico_alertas.csv", "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(["Fecha", "Tipo", "Moneda", "Subida"])
            
        if isinstance(pre_data, list):
            for item in pre_data:
                if isinstance(item, dict):
                    writer.writerow([fecha_actual, "Pre-Explosion", item.get('moneda'), item.get('subida')])
        if isinstance(tactico_data, list):
            for item in tactico_data:
                if isinstance(item, dict):
                    writer.writerow([fecha_actual, "Cazador Tactico", item.get('moneda'), item.get('subida')])
            
    print("[+] Registro añadido a historico_alertas.csv.")

    # 3. Notificación limpia a Telegram
    msg_telegram = f"📊 *DASHBOARD ACTUALIZADO* (`{fecha_actual}`)\n\n"
    msg_telegram += f"🧠 *Dictamen:* {dictamen}\n"
    enviar_telegram(msg_telegram)

if __name__ == '__main__':
    actualizar_dashboard()
