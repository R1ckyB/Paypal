from nicegui import ui

from app.config import COLORS
from app.components import app_header, invoice_grid, set_status, first_with_status, ClientInbox


@ui.page('/')
def dashboard_page():
    ui.colors(**COLORS)
    app_header()

    # Vista dividida: dashboard | bandeja del cliente
    with ui.splitter(value=62).classes('w-full').style('height:calc(100vh - 80px)') as sp:
        with sp.before:
            with ui.row().classes('w-full items-center justify-between p-3'):
                ui.label('Dashboard de Facturas').classes('text-lg font-semibold')
                ui.button('Simular recordatorio', icon='send',
                          on_click=lambda: simulate()).props('color=primary')
            grid = invoice_grid()

        with sp.after:
            inbox = ClientInbox(on_status_change=lambda c, s: set_status(grid, c, s))

    def simulate():
        row = first_with_status(grid, 'Overdue')
        if not row:
            ui.notify('No hay facturas vencidas', type='info')
            return
        inbox.send_reminder(row['client'], row['amount'], row['due_date'])
