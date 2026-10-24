import os
import json
import csv
from datetime import datetime
import requests
from google import genai
import gspread
from google.oauth2.service_account import Credentials

SCOPES = ['https://www.googleapis.com/auth/spreadsheets']

def cargar_json(nombre_archivo):
    try:
        with open(nombre_archivo, 'r', encoding='utf-8') as f:
            data = json.load(f)
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
        return "⚠️ Dictamen IA no disponible."
    
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
        return "Sincronización completada."
    except Exception:
        return f"Actualizado a las {datetime.now().strftime('%H:%M:%S')}."

def enviar_telegram(mensaje):
    token = os.environ.get('TELEGRAM_BOT_TOKEN')
    chat_id = os.environ.get('TELEGRAM_CHAT_ID')
    if token and chat_id:
        try:
            url = f"https://api.telegram.org/bot{token}/sendMessage"
            requests.post(url, json={"chat_id": chat_id, "text": mensaje, "parse_mode": "Markdown"}, timeout=10)
        except Exception:
            pass

def actualizar_google_sheets(pre_data, tactico_data, dictamen):
    """Rellena de forma inteligente las tablas estructuradas de tu Google Sheets."""
    try:
        service_account_info = json.loads(os.environ.get('GCP_SERVICE_ACCOUNT_KEY'))
        credentials = Credentials.from_service_account_info(service_account_info, scopes=SCOPES)
        client = gspread.authorize(credentials)
        
        spreadsheet_id = "1n6VesCq65Nplbj_sUSfouVAHfleVEyS3u7H-e7m2a8M"
        sheet = client.open_by_key(spreadsheet_id)
        worksheet = sheet.get_worksheet(0)
        
        # 1. Rellenar sección "cazador tactico" (Columnas F y G, filas 4 a 6 en base a tu diseño)
        for i in range(3):
            row = 4 + i
            if tactico_data and i < len(tactico_data):
                item = tactico_data[i]
                worksheet.update_cell(row, 6, item.get('moneda', ''))  # Columna F
                worksheet.update_cell(row, 7, str(item.get('subida', ''))) # Columna G
            else:
                worksheet.update_cell(row, 6, "")
                worksheet.update_cell(row, 7, "")

        # 2. Rellenar sección "Pre explosion" (Columnas K y L, filas 4 a 6)
        for i in range(3):
            row = 4 + i
            if pre_data and i < len(pre_data):
                item = pre_data[i]
                worksheet.update_cell(row, 11, item.get('moneda', '')) # Columna K
                worksheet.update_cell(row, 12, str(item.get('subida', ''))) # Columna L
            else:
                worksheet.update_cell(row, 11, "")
                worksheet.update_cell(row, 12, "")

        print("[+] Google Sheets actualizado respetando tu diseño de tablas.")
    except Exception as e:
        print(f"[!] Error al actualizar Google Sheets: {e}")

def actualizar_dashboard():
    print("[*] Iniciando procesamiento de datos...")
    
    pre_data = cargar_json('datos_pre_explosion_ia.json')
    tactico_data = cargar_json('datos_tactico.json')
    dictamen = generar_dictamen_ia(pre_data, tactico_data)
    fecha_actual = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    # 1. Actualizar Markdown en GitHub
    md_content = f"# 🚀 Dashboard Cripto Automatizado\n**Última actualización:** `{fecha_actual} UTC`\n\n"
    md_content += f"### 🧠 Dictamen Institucional (IA)\n> {dictamen}\n\n"
    
    md_content += "### ⚡ Radar Pre-Explosión\n"
    if pre_data and isinstance(pre_data, list):
        md_content += "| Moneda | % Subida |\n| --- | --- |\n"
        for item in pre_data[:7]:
            if isinstance(item, dict):
                md_content += f"| **{item.get('moneda', 'N/A')}** | {item.get('subida', 'N/A')} |\n"
    
    md_content += "\n### 🎯 Cazador Táctico\n"
    if tactico_data and isinstance(tactico_data, list):
        md_content += "| Moneda | % Subida |\n| --- | --- |\n"
        for item in tactico_data[:7]:
            if isinstance(item, dict):
                md_content += f"| **{item.get('moneda', 'N/A')}** | {item.get('subida', 'N/A')} |\n"

    with open("DASHBOARD_CRIPTO.md", "w", encoding="utf-8") as f:
        f.write(md_content)

    # 2. Guardar en histórico CSV local
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

    # 3. Sincronizar con tu Google Sheets
    actualizar_google_sheets(pre_data, tactico_data, dictamen)

    # 4. Telegram
    enviar_telegram(f"📊 *DASHBOARD ACTUALIZADO* (`{fecha_actual}`)\n\n🧠 *Dictamen:* {dictamen}")

if __name__ == '__main__':
    actualizar_dashboard()
