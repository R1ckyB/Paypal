from nicegui import ui

from app.services.invoice_service import load_invoices, update_invoice_status_in_db


STATUS_STYLES = {
    'Overdue': (
        'background:rgba(153,27,27,0.38);color:#F87171;'
        'border:1px solid rgba(239,68,68,0.32);'
    ),
    'Paid': (
        'background:rgba(6,95,70,0.42);color:#34D399;'
        'border:1px solid rgba(16,185,129,0.32);'
    ),
    'Pending': (
        'background:rgba(146,64,14,0.38);color:#FBBF24;'
        'border:1px solid rgba(245,158,11,0.32);'
    ),
    'Partial Plan': (
        'background:rgba(30,64,175,0.42);color:#60A5FA;'
        'border:1px solid rgba(59,130,246,0.38);'
    ),
    'Cancelled': (
        'background:rgba(71,85,105,0.42);color:#94A3B8;'
        'border:1px solid rgba(100,116,139,0.38);'
    ),
}


class InvoiceTable:
    """Tabla interactiva de facturas con tema oscuro idéntico al diseño de FacturaBot."""

    def __init__(self, on_send_reminder=None, on_select_client=None, on_data_change=None):
        self.rows = load_invoices()
        self.sort_asc = True
        self.selected_client = 'Globex'
        self.on_send_reminder = on_send_reminder
        self.on_select_client = on_select_client
        self.on_data_change = on_data_change

        # Compatibilidad con la estructura anterior (grid.options['rowData'])
        self.options = {'rowData': self.rows}

        with ui.column().classes('w-full flex-grow fb-table-card no-wrap gap-0') as self.card:
            # Encabezado de la tabla con CSS Grid de 6 columnas alineadas
            with ui.element('div').classes('w-full fb-table-grid fb-table-header'):
                ui.label('ID Factura').classes('fb-th')
                ui.label('Cliente').classes('fb-th fb-th-divider')
                ui.label('Monto').classes('fb-th fb-th-divider')
                with ui.row().classes('items-center gap-1 cursor-pointer no-wrap fb-th fb-th-divider').on(
                    'click', self.toggle_sort
                ):
                    self.sort_label = ui.html('<span style="user-select:none;">Vencimiento &uarr;</span>')
                ui.label('Estado').classes('fb-th fb-th-divider')
                ui.label('Acciones').classes('fb-th fb-th-divider')

            # Cuerpo de la tabla
            self.body = ui.column().classes('w-full flex-grow overflow-auto gap-0')
            self._render_rows()

    def toggle_sort(self):
        self.sort_asc = not self.sort_asc
        arrow = '&uarr;' if self.sort_asc else '&darr;'
        self.sort_label.content = f'<span style="user-select:none;">Vencimiento {arrow}</span>'
        self.rows.sort(key=lambda r: r.get('due_date', ''), reverse=not self.sort_asc)
        self._render_rows()

    def _render_rows(self):
        self.body.clear()
        with self.body:
            for row in self.rows:
                self._render_single_row(row)

    def _render_single_row(self, row: dict):
        client = row['client']
        status = row['status']
        amount = float(row['amount'])
        inv_id = row.get('id', 'INV-2026-000')
        due_date = row.get('due_date', '')
        is_selected = client == self.selected_client
        row_cls = 'fb-tr fb-tr-selected' if is_selected else 'fb-tr'

        with ui.element('div').classes(f'w-full fb-table-grid {row_cls}').on(
            'click', lambda _, r=row: self._handle_row_click(r)
        ):
            ui.label(inv_id).classes('fb-td text-slate-300')
            ui.label(client).classes('fb-td fb-td-pad text-slate-100 font-medium')
            ui.label(f'${amount:,.2f}').classes('fb-td fb-td-pad text-slate-100')
            ui.label(due_date).classes('fb-td fb-td-pad text-slate-300')

            badge_style = STATUS_STYLES.get(status, STATUS_STYLES['Pending'])
            ui.html(
                f'<span class="fb-status-pill" style="{badge_style}">{status}</span>'
            ).classes('fb-td fb-td-pad')

            with ui.row().classes('items-center no-wrap fb-td-pad'):
                if status in ('Overdue', 'Partial Plan'):
                    ui.button(
                        'ENVIAR RECORDATORIO',
                        on_click=lambda _, r=row: self._trigger_reminder(r),
                    ).props('unelevated dense no-caps').classes('fb-reminder-btn')
                else:
                    ui.label('-').classes('text-slate-500 pl-1')

    def _handle_row_click(self, row: dict):
        self.selected_client = row['client']
        if self.on_select_client:
            with self.card:
                self.on_select_client(row)
        self._render_rows()

    def _trigger_reminder(self, row: dict):
        self.selected_client = row['client']
        # Ejecutar primero el callback dentro de un contenedor persistente antes de limpiar las filas
        if self.on_send_reminder:
            with self.card:
                self.on_send_reminder(row)
        self._render_rows()

    def update(self):
        self._render_rows()
        if self.on_data_change:
            self.on_data_change()


def invoice_grid(on_send_reminder=None, on_select_client=None, on_data_change=None):
    return InvoiceTable(
        on_send_reminder=on_send_reminder,
        on_select_client=on_select_client,
        on_data_change=on_data_change,
    )


def set_status(grid, client, status, new_amount=None):
    """Cambia el estado en BD y memoria, y refresca la tabla."""
    update_invoice_status_in_db(client, status, new_amount)
    for row in grid.options['rowData']:
        if row['client'] == client:
            row['status'] = status
            if new_amount is not None:
                row['amount'] = new_amount
    grid.update()


def first_with_status(grid, status):
    for row in grid.options['rowData']:
        if row['status'] == status:
            return row
    return None
