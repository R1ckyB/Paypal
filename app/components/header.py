from nicegui import ui

from app.config import HEADER_BG
import InvoicingAPI as paypal_api
from app.services.agent_service import get_active_ai_provider


def app_header(lang: str = 'es', on_toggle_lang=None, on_toggle_grid_mode=None):
    """Header con el branding de FacturaBot, controles de idioma/AG Grid y sello Powered by PayPal."""
    subtitle_txt = (
        'Intelligent AI Collections (PayPal Invoicing v2 API)'
        if lang == 'en'
        else 'Cobranza inteligente con IA (Invoicing API)'
    )
    pp_mode = 'Sandbox Live' if paypal_api.is_configured() else 'Sandbox Ready'
    ai_provider = get_active_ai_provider()

    with ui.header().classes('items-center justify-between px-6 py-2 fb-header').style(
        f'background:{HEADER_BG}; border-bottom: 1px solid #1E293B; height: 56px;'
    ):
        # Branding izquierdo
        with ui.row().classes('items-center gap-2.5 no-wrap'):
            ui.html(
                '<span class="brand" style="font-size:21px;font-weight:700;color:#F8FAFC;letter-spacing:-0.3px;">'
                'Factura<span style="color:#2563EB">Bot</span></span>'
            )
            ui.html(
                f'<span class="bot-avatar-header" title="AI Engine: {ai_provider} | PayPal: {pp_mode}">🤖</span>'
            )
            ui.html(
                f'<span style="font-size:10.5px;padding:2px 8px;border-radius:999px;'
                f'background:rgba(16,185,129,0.14);color:#34D399;border:1px solid rgba(16,185,129,0.3);'
                f'font-weight:600;">{pp_mode}</span>'
            )

        # Leyenda derecha + Controles + Powered by PayPal
        with ui.row().classes('items-center gap-3 no-wrap'):
            subtitle_label = ui.label(subtitle_txt).classes(
                'text-slate-300 text-xs sm:text-sm font-medium'
            )

            if on_toggle_grid_mode:
                grid_btn = (
                    ui.button('AG Grid: ON', on_click=on_toggle_grid_mode)
                    .props('unelevated dense no-caps')
                    .classes('fb-view-toggle-btn')
                    .tooltip('Alternar entre AG Grid (Sponsor) y Tabla Clásica')
                )
            else:
                grid_btn = None

            if on_toggle_lang:
                lang_btn = (
                    ui.button('EN / ES', on_click=on_toggle_lang)
                    .props('unelevated dense no-caps')
                    .classes('fb-view-toggle-btn')
                    .tooltip('Switch Language (English / Español)')
                )
            else:
                lang_btn = None

            ui.html('<div style="width:1px;height:28px;background:#334155;"></div>')
            ui.html(
                '<div style="display:flex;flex-direction:column;align-items:flex-start;line-height:1.05;">'
                '<span style="font-size:10px;color:#94A3B8;font-weight:500;">Powered by</span>'
                '<span style="font-size:17px;font-weight:800;color:#FFFFFF;font-family:\'Space Grotesk\',sans-serif;letter-spacing:-0.4px;">PayPal</span>'
                '</div>'
            )

    return {'subtitle_label': subtitle_label, 'grid_btn': grid_btn, 'lang_btn': lang_btn}
