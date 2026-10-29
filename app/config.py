"""Configuración central de FacturaBot (rutas, servidor y paleta de colores)."""
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
APP_TITLE = 'FacturaBot'
APP_PORT = int(os.getenv('PORT', 8080))

# Paleta de la marca
COLORS = {
    'primary': '#2563EB',
    'positive': '#10B981',
    'warning': '#F59E0B',
    'negative': '#EF4444',
}
HEADER_BG = '#0F172A'
