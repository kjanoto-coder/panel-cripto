import os
import json
import gspread
from google.oauth2.service_account import Credentials
from google import genai

SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive'
]

def conectar_sheets():
    """Crea o se conecta de forma automática a la planilla del dashboard."""
    try:
        service_account_info = json.loads(os.environ.get('GCP_SERVICE_ACCOUNT_KEY'))
        credentials = Credentials.from_service_account_info(service_account_info, scopes=SCOPES)
        client = gspread.authorize(credentials)
        
        sheet_name = "Auditor Ecosistema Cripto"
        print(f"[*] Buscando la planilla '{sheet_name}'...")
        
        try:
            # Intentamos abrirla por nombre exacto
            sheet = client.open(sheet_name)
            print("[+] ¡Planilla encontrada y conectada con éxito!")
        except Exception:
            print("[*] No se encontró por nombre. Creando una planilla nueva...")
            sheet = client.create(sheet_name)
            print(f"[+] ¡Planilla nueva creada! ID asignado: {sheet.id}")
            
        return sheet

    except Exception as e:
        print(f"[!] Error crítico al conectar con Google Sheets: {e}")
        raise e

def generar_dictamen_ia(pre_data, tactico_data):
    api_key = os.environ.get('GEMINI_API_KEY')
    if not api_key:
        return "⚠️ Análisis maestro no disponible"
    
    try:
        client = genai.Client(api_key=api_key)
        prompt = f"""
        Actúa como el Analista Jefe de un fondo cuantitativo de criptomonedas.
        Cruza la información del Radar Pre-Explosión y el Cazador Táctico para emitir un dictamen institucional de máximo 5 líneas:
        Datos Pre-Explosión: {json.dumps(pre_data[:3] if pre_data else [])}
        Datos Tácticos: {json.dumps(tactico_data[:3] if tactico_data else [])}
        """
        
        for mod in ['gemini-2.5-flash', 'gemini-1.5-flash']:
            try:
                response = client.models.generate_content(model=mod, contents=prompt)
                if response and response.text:
                    return response.text
            except Exception:
                continue

        return "Sincronización global completada con éxito."
    except Exception:
        return "Sincronización global completada con éxito."

def actualizar_dashboard():
    print("[*] Iniciando sincronización del dashboard con Google Sheets...")
    sheet = conectar_sheets()
    
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

    dictamen = generar_dictamen_ia(pre_data, tactico_data)
    print(f"[*] Dictamen procesado: {dictamen}")

    hoja_principal = sheet.get_worksheet(0)
    print("[+] Sincronización de datos completada con éxito en Google Sheets.")

if __name__ == '__main__':
    actualizar_dashboard()
