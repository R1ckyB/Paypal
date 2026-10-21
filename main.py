from nicegui import ui
from components.grid import invoice_grid, set_status, first_with_status
from components.client_inbox import ClientInbox

# Tipografías y estilos de FacturaBot (shared=True: se aplica a todas las páginas)
ui.add_head_html("""
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600&family=Space+Grotesk:wght@600;700&display=swap" rel="stylesheet">
<style>
  body { font-family: 'Inter', sans-serif; background: #F8FAFC; }
  .brand { font-family: 'Space Grotesk', sans-serif; }
</style>
""", shared=True)


@ui.page('/')
def index():
    ui.colors(primary='#2563EB', positive='#10B981', warning='#F59E0B', negative='#EF4444')

    # Header con branding
    with ui.header().classes('items-center justify-between').style('background:#0F172A'):
        ui.html('<span class="brand" style="font-size:22px;font-weight:700;color:white">'
                'Factura<span style="color:#2563EB">Bot</span> 🤖</span>')
        ui.label('Cobranza inteligente con IA').classes('text-slate-300 text-sm')

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


ui.run(title='FacturaBot', port=8080)