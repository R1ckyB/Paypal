from nicegui import ui

from app.services.invoice_service import load_invoices

BADGE = """params => {
  const c = {Pending:'#F59E0B', Paid:'#10B981', Overdue:'#EF4444'}[params.value] || '#64748B';
  return `<span style="background:${c}22;color:${c};padding:2px 12px;
          border-radius:999px;font-weight:600;font-size:12px">${params.value}</span>`;
}"""


def invoice_grid():
    grid = ui.aggrid({
        'columnDefs': [
            {'headerName': 'Cliente', 'field': 'client', 'filter': True},
            {'headerName': 'Monto', 'field': 'amount',
             ':valueFormatter': "p => '$' + p.value.toLocaleString()"},
            {'headerName': 'Vencimiento', 'field': 'due_date', 'sort': 'asc'},
            {'headerName': 'Estado', 'field': 'status', 'filter': True,
             ':cellRenderer': BADGE},
        ],
        'rowData': load_invoices(),
        'defaultColDef': {'flex': 1, 'sortable': True},
    }, html_columns=[3]).classes('h-full')
    return grid


def set_status(grid, client, status):
    """Cambia el estado de una factura y refresca la tabla en vivo."""
    for row in grid.options['rowData']:
        if row['client'] == client:
            row['status'] = status
    grid.update()


def first_with_status(grid, status):
    for row in grid.options['rowData']:
        if row['status'] == status:
            return row
    return None
