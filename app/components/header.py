from nicegui import ui

from app.config import HEADER_BG


def app_header():
    """Header con el branding de FacturaBot y sello Powered by PayPal."""
    with ui.header().classes('items-center justify-between px-6 py-2 fb-header').style(
        f'background:{HEADER_BG}; border-bottom: 1px solid #1E293B; height: 56px;'
    ):
        # Branding izquierdo
        with ui.row().classes('items-center gap-2 no-wrap'):
            ui.html(
                '<span class="brand" style="font-size:21px;font-weight:700;color:#F8FAFC;letter-spacing:-0.3px;">'
                'Factura<span style="color:#2563EB">Bot</span></span>'
            )
            ui.html(
                '<span class="bot-avatar-header" title="Agente IA Activo">🤖</span>'
            )

        # Leyenda derecha + Powered by PayPal
        with ui.row().classes('items-center gap-4 no-wrap'):
            ui.label('Cobranza inteligente con IA (Invoicing API)').classes(
                'text-slate-300 text-xs sm:text-sm font-medium'
            )
            ui.html('<div style="width:1px;height:28px;background:#334155;"></div>')
            ui.html(
                '<div style="display:flex;flex-direction:column;align-items:flex-start;line-height:1.05;">'
                '<span style="font-size:10px;color:#94A3B8;font-weight:500;">Powered by</span>'
                '<span style="font-size:17px;font-weight:800;color:#FFFFFF;font-family:\'Space Grotesk\',sans-serif;letter-spacing:-0.4px;">PayPal</span>'
                '</div>'
            )
