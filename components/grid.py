import json
from pathlib import Path
from nicegui import ui

# Ruta al JSON: facturabot/data/invoices.json
DATA_FILE = Path(__file__).resolve().parent.parent / 'data' / 'invoices.json'

# Badge visual para el estado (Pending / Paid / Overdue)
BADGE = """params => {
  const c = {Pending:'#F59E0B', Paid:'#10B981', Overdue:'#EF4444'}[params.value] || '#64748B';
  return `<span style="background:${c}22;color:${c};padding:2px 12px;
          border-radius:999px;font-weight:600;font-size:12px">${params.value}</span>`;
}"""


def load_invoices():
    with open(DATA_FILE, encoding='utf-8') as f:
        return json.load(f)


def invoice_grid():
    rows = load_invoices()

    return ui.aggrid({
        'columnDefs': [
            {'headerName': 'Cliente', 'field': 'client', 'filter': True},
            {'headerName': 'Monto', 'field': 'amount',
             ':valueFormatter': "p => '$' + p.value.toLocaleString()"},
            {'headerName': 'Vencimiento', 'field': 'due_date', 'sort': 'asc'},
            {'headerName': 'Estado', 'field': 'status', 'filter': True,
             ':cellRenderer': BADGE},
        ],
        'rowData': rows,
        'defaultColDef': {'flex': 1, 'sortable': True},
    }, html_columns=[3]).classes('h-full')