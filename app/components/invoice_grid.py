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

AGGRID_STATUS_RENDERER = """params => {
  const styles = {
    'Overdue': 'background:rgba(153,27,27,0.38);color:#F87171;border:1px solid rgba(239,68,68,0.32);',
    'Paid': 'background:rgba(6,95,70,0.42);color:#34D399;border:1px solid rgba(16,185,129,0.32);',
    'Pending': 'background:rgba(146,64,14,0.38);color:#FBBF24;border:1px solid rgba(245,158,11,0.32);',
    'Partial Plan': 'background:rgba(30,64,175,0.42);color:#60A5FA;border:1px solid rgba(59,130,246,0.38);',
    'Cancelled': 'background:rgba(71,85,105,0.42);color:#94A3B8;border:1px solid rgba(100,116,139,0.38);'
  };
  const st = styles[params.value] || styles['Pending'];
  return `<span class="fb-status-pill" style="${st}">${params.value}</span>`;
}"""

AGGRID_ACTION_RENDERER = """params => {
  const st = params.data && params.data.status;
  if (st === 'Overdue' || st === 'Partial Plan') {
    const label = window.__fbLang === 'en' ? 'SEND REMINDER' : 'ENVIAR RECORDATORIO';
    return `<button class="fb-ag-reminder-btn">${label}</button>`;
  }
  return '<span style="color:#64748B;padding-left:4px;">-</span>';
}"""


class InvoiceTable:
    """Tabla interactiva de facturas con soporte dual:
    1) AG Grid (Sponsor Track) con filtros, ordenamiento y renderers HTML oscuros.
    2) Vista CSS Grid clásica de FacturaBot.
    """

    def __init__(self, on_send_reminder=None, on_select_client=None, on_data_change=None, lang: str = 'es'):
        self.rows = load_invoices()
        self.sort_asc = True
        self.selected_client = 'Globex'
        self.lang = lang
        self.use_aggrid = False  # Inicia en el diseño exacto FacturaBot y permite activar AG Grid interactivo
        self.on_send_reminder = on_send_reminder
        self.on_select_client = on_select_client
        self.on_data_change = on_data_change

        # Compatibilidad con la estructura anterior (grid.options['rowData'])
        self.options = {'rowData': self.rows}
        self.aggrid_widget = None

        with ui.column().classes('w-full flex-grow fb-table-card no-wrap gap-0') as self.card:
            # Contenedor de la vista CSS Grid clásica (idéntica al diseño de referencia)
            self.custom_container = ui.column().classes('w-full h-full flex-grow no-wrap gap-0')
            with self.custom_container:
                with ui.element('div').classes('w-full fb-table-grid fb-table-header'):
                    self.th_id = ui.label('ID Factura').classes('fb-th')
                    self.th_client = ui.label('Cliente').classes('fb-th fb-th-divider')
                    self.th_amount = ui.label('Monto').classes('fb-th fb-th-divider')
                    with ui.row().classes('items-center gap-1 cursor-pointer no-wrap fb-th fb-th-divider').on(
                        'click', self.toggle_sort
                    ):
                        self.sort_label = ui.html('<span style="user-select:none;">Vencimiento &uarr;</span>')
                    self.th_status = ui.label('Estado').classes('fb-th fb-th-divider')
                    self.th_actions = ui.label('Acciones').classes('fb-th fb-th-divider')

                self.body = ui.column().classes('w-full flex-grow overflow-auto gap-0')

            # Contenedor de AG Grid (Sponsor Track: Best Use of AG Grid)
            self.aggrid_container = ui.column().classes('w-full h-full flex-grow no-wrap gap-0')
            with self.aggrid_container:
                self.aggrid_widget = ui.aggrid(
                    self._build_aggrid_options(),
                    html_columns=[4, 5],
                    theme='quartz',
                ).classes('w-full flex-grow ag-theme-quartz-dark fb-aggrid')
                self.aggrid_widget.on('cellClicked', self._handle_aggrid_cell_click)

            self.aggrid_container.set_visibility(self.use_aggrid)
            self.custom_container.set_visibility(not self.use_aggrid)
            self._render_rows()

    def _build_aggrid_options(self) -> dict:
        is_en = self.lang == 'en'
        return {
            'columnDefs': [
                {'headerName': 'Invoice ID' if is_en else 'ID Factura', 'field': 'id', 'filter': True, 'minWidth': 125},
                {'headerName': 'Client' if is_en else 'Cliente', 'field': 'client', 'filter': True, 'minWidth': 135},
                {
                    'headerName': 'Amount' if is_en else 'Monto',
                    'field': 'amount',
                    'sortable': True,
                    ':valueFormatter': "p => '$' + Number(p.value || 0).toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2})",
                    'minWidth': 110,
                },
                {
                    'headerName': 'Due Date' if is_en else 'Vencimiento',
                    'field': 'due_date',
                    'sort': 'asc',
                    'sortable': True,
                    'filter': True,
                    'minWidth': 120,
                },
                {
                    'headerName': 'Status' if is_en else 'Estado',
                    'field': 'status',
                    'filter': True,
                    ':cellRenderer': AGGRID_STATUS_RENDERER,
                    'minWidth': 115,
                },
                {
                    'headerName': 'Actions' if is_en else 'Acciones',
                    'field': 'status',
                    'colId': 'actions',
                    'sortable': False,
                    'filter': False,
                    ':cellRenderer': AGGRID_ACTION_RENDERER,
                    'minWidth': 170,
                },
            ],
            'rowData': self.rows,
            'defaultColDef': {'flex': 1, 'sortable': True, 'resizable': True},
            'rowSelection': 'single',
            'animateRows': True,
        }

    def _handle_aggrid_cell_click(self, e):
        args = e.args or {}
        row_data = args.get('data')
        if not row_data:
            return
        col_id = args.get('colId', '')
        status = row_data.get('status')
        if col_id == 'actions' and status in ('Overdue', 'Partial Plan'):
            self._trigger_reminder(row_data)
        else:
            self._handle_row_click(row_data)

    def toggle_grid_mode(self) -> bool:
        """Alterna entre la tabla personalizada de FacturaBot y el componente interactivo AG Grid."""
        self.use_aggrid = not self.use_aggrid
        self.aggrid_container.set_visibility(self.use_aggrid)
        self.custom_container.set_visibility(not self.use_aggrid)
        self.update()
        return self.use_aggrid

    def set_language(self, lang: str):
        self.lang = lang
        is_en = lang == 'en'
        self.th_id.text = 'Invoice ID' if is_en else 'ID Factura'
        self.th_client.text = 'Client' if is_en else 'Cliente'
        self.th_amount.text = 'Amount' if is_en else 'Monto'
        arrow = '&uarr;' if self.sort_asc else '&darr;'
        due_txt = 'Due Date' if is_en else 'Vencimiento'
        self.sort_label.content = f'<span style="user-select:none;">{due_txt} {arrow}</span>'
        self.th_status.text = 'Status' if is_en else 'Estado'
        self.th_actions.text = 'Actions' if is_en else 'Acciones'
        if self.aggrid_widget:
            self.aggrid_widget.options['columnDefs'] = self._build_aggrid_options()['columnDefs']
            self.aggrid_widget.update()
        self._render_rows()

    def toggle_sort(self):
        self.sort_asc = not self.sort_asc
        arrow = '&uarr;' if self.sort_asc else '&darr;'
        due_txt = 'Due Date' if self.lang == 'en' else 'Vencimiento'
        self.sort_label.content = f'<span style="user-select:none;">{due_txt} {arrow}</span>'
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
        btn_txt = 'SEND REMINDER' if self.lang == 'en' else 'ENVIAR RECORDATORIO'

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
                        btn_txt,
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
        if self.on_send_reminder:
            with self.card:
                self.on_send_reminder(row)
        self._render_rows()

    def update(self):
        self._render_rows()
        if self.aggrid_widget:
            self.aggrid_widget.options['rowData'] = self.rows
            self.aggrid_widget.update()
        if self.on_data_change:
            self.on_data_change()


def invoice_grid(on_send_reminder=None, on_select_client=None, on_data_change=None, lang: str = 'es'):
    return InvoiceTable(
        on_send_reminder=on_send_reminder,
        on_select_client=on_select_client,
        on_data_change=on_data_change,
        lang=lang,
    )


def set_status(grid, client, status, new_amount=None):
    """Cambia el estado en BD y memoria, y refresca la tabla."""
    update_invoice_status_in_db(client, status, new_amount)
    for row in grid.options['rowData']:
        if row['client'] == client or row.get('id') == client:
            row['status'] = status
            if new_amount is not None:
                row['amount'] = new_amount
    grid.update()


def first_with_status(grid, status):
    for row in grid.options['rowData']:
        if row['status'] == status:
            return row
    return None
