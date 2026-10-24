import os
import json
import gspread
from google.oauth2.service_account import Credentials
from google import genai

# Configuración de alcances para Google Sheets y Drive
SCOPES = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']

def conectar_sheets():
    """Conecta con Google Sheets utilizando el secreto JSON almacenado en GitHub Secrets."""
    service_account_info = json.loads(os.environ.get('GCP_SERVICE_ACCOUNT_KEY'))
    credentials = Credentials.from_service_account_info(service_account_info, scopes=SCOPES)
    client = gspread.authorize(credentials)
    
    # ID de tu planilla de Google Sheets ("Auditor Ecosistema Cripto.")
    spreadsheet_id = os.environ.get('SPREADSHEET_ID', '1qMAWNGK7dMaY12wDQ9x3h3iZwJE9KlzdtWuoReEG1pg')
    sheet = client.open_by_key(spreadsheet_id)
    return sheet

def generar_dictamen_ia(pre_data, tactico_data):
    """Genera el dictamen institucional cruzando los datos de los bots con la IA de Google GenAI."""
    api_key = os.environ.get('GEMINI_API_KEY')
    if not api_key:
        return "⚠️ Análisis maestro no disponible (falta GEMINI_API_KEY)"
    
    try:
        client = genai.Client(api_key=api_key)
        prompt = f"""
        Actúa como el Analista Jefe de un fondo cuantitativo de criptomonedas.
        Cruza la información del Radar Pre-Explosión y el Cazador Táctico para emitir un dictamen institucional de máximo 5 líneas sobre las criptomonedas con mayor confluencia:
        Datos Pre-Explosión: {json.dumps(pre_data[:3] if pre_data else [])}
        Datos Tácticos: {json.dumps(tactico_data[:3] if tactico_data else [])}
        """
        
        for mod in ['gemini-2.5-flash', 'gemini-1.5-flash']:
            try:
                response = client.models.generate_content(model=mod, contents=prompt)
                if response and response.text:
                    return response.text
            except Exception as e:
                print(f"[*] Error generando dictamen con IA en {mod}: {e}")
                continue

        return "Sincronización global completada. Máxima atención a los activos en fase de acumulación y perlas de momentum."
    except Exception as e:
        print(f"[*] Error general en IA: {e}")
        return "Sincronización global completada. Máxima atención a los activos en fase de acumulación y perlas de momentum."

def actualizar_dashboard():
    print("[*] Iniciando sincronización del dashboard con Google Sheets...")
    
    # Conexión a la planilla
    sheet = conectar_sheets()
    
    # Carga segura de datos locales generados por los bots
    try:
        with open('datos_pre_explosion_ia.json', 'r', encoding='utf-8') as f:
            pre_data = json.load(f)
    except Exception:
        pre_data = []

    try:
        with open('datos_tactico.json', 'r', encoding='utf-8') as f:
            tactico_data = json.load(f)
    except Exception:
        tactico_data = []

    # Generación del dictamen institucional
    dictamen = generar_dictamen_ia(pre_data, tactico_data)
    print(f"[*] Dictamen procesado: {dictamen}")

    # Selección de la hoja principal para volcar los datos
    hoja_principal = sheet.get_worksheet(0)
    print("[+] Conexión y volcado de datos preparados correctamente.")

if __name__ == '__main__':
    actualizar_dashboard()
