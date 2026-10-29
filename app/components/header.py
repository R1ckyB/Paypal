from nicegui import ui

from app.config import HEADER_BG


def app_header():
    """Header con el branding de FacturaBot."""
    with ui.header().classes('items-center justify-between').style(f'background:{HEADER_BG}'):
        ui.html('<span class="brand" style="font-size:22px;font-weight:700;color:white">'
                'Factura<span style="color:#2563EB">Bot</span> 🤖</span>')
        ui.label('Cobranza inteligente con IA').classes('text-slate-300 text-sm')
