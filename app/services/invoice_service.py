import json

from app.config import INVOICES_FILE


def load_invoices():
    """Carga las facturas.
    TODO: reemplazar el JSON de prueba por una llamada al backend (GET /api/invoices)."""
    with open(INVOICES_FILE, encoding='utf-8') as f:
        return json.load(f)
