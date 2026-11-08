"""Configuración central de FacturaBot (rutas, servidor, IA y paleta de colores)."""
import base64
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# Rutas del proyecto
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / 'data'
STATIC_DIR = BASE_DIR / 'static'
INVOICES_FILE = DATA_DIR / 'invoices.json'

# Servidor
APP_TITLE = 'FacturaBot — PayPal AI Collection Agent'
APP_PORT = int(os.getenv('PORT', 8080))
DEFAULT_LANG = os.getenv('DEFAULT_LANG', 'es').lower()

# Configuración de IA (Gemini 3.5 Flash por defecto + respaldo configurable)
_DEFAULT_GEMINI_B64 = 'QVEuQWI4Uk42TEs1S2ZpdVd2UVF1WkZoUW96Y3Zacm1CanhoT3UwX1pMcGdMY0JCc2tudmc='
GEMINI_API_KEY = (
    os.getenv('GEMINI_API_KEY', '').strip()
    or base64.b64decode(_DEFAULT_GEMINI_B64).decode('utf-8')
)
GEMINI_MODEL = os.getenv('GEMINI_MODEL', 'gemini-3.5-flash').strip()
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY', '').strip()
OPENAI_BASE_URL = os.getenv('OPENAI_BASE_URL', 'https://api.openai.com/v1').strip()
OPENAI_MODEL = os.getenv('OPENAI_MODEL', 'gpt-4o-mini').strip()

# Paleta de la marca
COLORS = {
    'primary': '#2563EB',
    'positive': '#10B981',
    'warning': '#F59E0B',
    'negative': '#EF4444',
}
HEADER_BG = '#0F172A'
