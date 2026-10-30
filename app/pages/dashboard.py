from nicegui import ui

from app.config import COLORS
from app.components import app_header, invoice_grid, set_status, ClientInbox
from app.services.invoice_service import save_payment_agreement_in_db


@ui.page('/')
def dashboard_page():
    ui.colors(**COLORS)
    app_header()

    # Estado reactivo para Human-In-The-Loop (precargado con la propuesta de Globex)
    hitl_state = {
        'active': True,
        'client': 'Globex',
        'payments': 2,
        'amount': 8200.0,
        'resolved_msg': None,
    }

    grid_ref = {'grid': None}
    inbox_ref = {'inbox': None}

    def compute_totals():
        grid = grid_ref['grid']
        if not grid:
            return 50400.0, 3400.0
        rows = grid.options['rowData']
        recovered = sum(float(r['amount']) for r in rows if r['status'] == 'Paid')
        unpaid = sum(float(r['amount']) for r in rows if r['status'] != 'Paid')
        # Si hay una factura retenida en revisión Human-In-The-Loop aún sin resolver, se descuenta de Pendiente operativo
        if hitl_state['active']:
            for r in rows:
                if r['client'] == hitl_state['client'] and r['status'] == 'Overdue':
                    unpaid = max(0.0, unpaid - float(r['amount']))
                    break
        return unpaid, recovered

    def refresh_kpis():
        pending_val, recovered_val = compute_totals()
        pending_label.text = f'(${pending_val:,.2f})'
        recovered_label.text = f'(${recovered_val:,.2f})'

    def refresh_hitl():
        if hitl_state['active']:
            c = hitl_state['client']
            n = hitl_state['payments']
            hitl_text.text = f'Propuesta de IA: ¿Aprobar plan de {n} pagos para {c}?'
            approve_btn.set_visibility(True)
            reject_btn.set_visibility(True)
        else:
            hitl_text.text = hitl_state['resolved_msg'] or 'Sin propuestas pendientes de aprobación humana.'
            approve_btn.set_visibility(False)
            reject_btn.set_visibility(False)

    def handle_approve():
        if not hitl_state['active']:
            return
        client = hitl_state['client']
        payments = hitl_state['payments']
        amount = hitl_state['amount']
        hitl_state['active'] = False
        plan_desc = f'Plan de {payments} pagos (${amount / max(payments, 1):,.2f} USD c/u)'
        hitl_state['resolved_msg'] = (
            f'✅ Plan de {payments} pagos para {client} aprobado en PayPal (${amount / max(payments, 1):,.2f}/pago).'
        )
        save_payment_agreement_in_db(client, plan_desc, status='APPROVED')
        set_status(grid_ref['grid'], client, 'Partial Plan')
        inbox_ref['inbox'].notify_plan_approved(client, payments, amount)
        refresh_hitl()
        refresh_kpis()
        ui.notify(f'Plan de {payments} pagos aprobado en PayPal para {client}', type='positive')

    def handle_reject():
        if not hitl_state['active']:
            return
        client = hitl_state['client']
        payments = hitl_state['payments']
        amount = hitl_state['amount']
        hitl_state['active'] = False
        plan_desc = f'Plan de {payments} pagos (${amount / max(payments, 1):,.2f} USD c/u)'
        hitl_state['resolved_msg'] = f'❌ Propuesta de pagos parciales para {client} rechazada. Se requiere pago total.'
        save_payment_agreement_in_db(client, plan_desc, status='REJECTED')
        inbox_ref['inbox'].notify_plan_rejected(client, amount)
        refresh_hitl()
        refresh_kpis()
        ui.notify(f'Propuesta para {client} rechazada', type='warning')

    def on_new_hitl_proposal(proposal: dict):
        client = proposal['client']
        amount = proposal.get('amount') or 0.0
        if grid_ref['grid']:
            for r in grid_ref['grid'].options['rowData']:
                if r['client'] == client:
                    amount = float(r['amount'])
                    break
        payments = proposal.get('payments', 2)
        hitl_state['active'] = True
        hitl_state['client'] = client
        hitl_state['payments'] = payments
        hitl_state['amount'] = amount
        hitl_state['resolved_msg'] = None
        plan_desc = f'Plan de {payments} pagos (${amount / max(payments, 1):,.2f} USD c/u)'
        save_payment_agreement_in_db(client, plan_desc, status='PENDING_HUMAN_APPROVAL')
        refresh_hitl()
        refresh_kpis()
        ui.notify(f'Nueva propuesta Human-In-The-Loop generada para {client}', color='warning')

    def on_paypal_payment(client: str, amount: float):
        set_status(grid_ref['grid'], client, 'Paid')
        if hitl_state['active'] and hitl_state['client'] == client:
            hitl_state['active'] = False
            hitl_state['resolved_msg'] = f'✅ Factura de {client} liquidada mediante PayPal.'
            refresh_hitl()
        refresh_kpis()
        ui.notify(f'Pago de ${amount:,.2f} recibido en PayPal ({client})', type='positive')

    def on_status_updated(client: str, status: str):
        set_status(grid_ref['grid'], client, status)
        if status == 'Paid' and hitl_state['active'] and hitl_state['client'] == client:
            hitl_state['active'] = False
            hitl_state['resolved_msg'] = f'✅ Factura de {client} marcada como pagada.'
            refresh_hitl()
        refresh_kpis()

    # Contenedor principal dividido (Dashboard izquierda | Bandeja derecha)
    with ui.row().classes('w-full no-wrap fb-main-layout'):
        # Panel Izquierdo: Dashboard de Facturas
        with ui.column().classes('h-full justify-between no-wrap fb-left-panel'):
            # Título
            ui.label('Dashboard de Facturas').classes('text-white text-base font-bold tracking-tight mb-1')

            # Tarjetas KPI (Pendiente, Recuperado, Estado de IA)
            with ui.row().classes('w-full gap-3 no-wrap mb-2'):
                with ui.column().classes('flex-1 fb-kpi-card gap-0.5'):
                    ui.label('Pendiente').classes('fb-kpi-title')
                    pending_label = ui.label('($50,400.00)').classes('fb-kpi-value')

                with ui.column().classes('flex-1 fb-kpi-card gap-0.5'):
                    ui.label('Recuperado').classes('fb-kpi-title')
                    recovered_label = ui.label('($3,400.00)').classes('fb-kpi-value')

                with ui.column().classes('flex-1 fb-kpi-card gap-1 justify-between'):
                    ui.label('Estado de IA').classes('fb-kpi-title')
                    with ui.row().classes('items-center gap-2 no-wrap mt-0.5'):
                        ui.label('Activo y Monitoreando').classes('fb-ai-status-text')
                        ui.html('<span class="fb-ai-dot"></span>')

            # Tabla de Facturas
            grid = invoice_grid(
                on_send_reminder=lambda row: inbox_ref['inbox'].send_reminder(
                    row['client'], row['amount'], row['due_date'], row.get('id')
                ),
                on_select_client=lambda row: inbox_ref['inbox'].select_client(row),
                on_data_change=refresh_kpis,
            )
            grid_ref['grid'] = grid
            refresh_kpis()

            # Panel Inferior: Human-In-The-Loop
            with ui.column().classes('w-full fb-hitl-card gap-1.5 mt-2'):
                with ui.row().classes('items-center gap-2 no-wrap'):
                    ui.html('<span class="fb-hitl-icon">!</span>')
                    ui.label('Human-In-The-Loop').classes('text-white text-xs font-bold tracking-wide')

                with ui.row().classes('w-full items-center justify-between gap-2 flex-wrap'):
                    hitl_text = ui.label(
                        'Propuesta de IA: ¿Aprobar plan de 2 pagos para Globex?'
                    ).classes('text-slate-300 text-sm')

                    with ui.row().classes('items-center gap-2 no-wrap'):
                        approve_btn = (
                            ui.button('APROBAR EN PAYPAL', on_click=handle_approve)
                            .props('unelevated dense no-caps')
                            .classes('fb-hitl-approve')
                        )
                        reject_btn = (
                            ui.button('RECHAZAR', on_click=handle_reject)
                            .props('unelevated dense no-caps')
                            .classes('fb-hitl-reject')
                        )

        # Panel Derecho: Bandeja del cliente (simulada)
        with ui.column().classes('h-full no-wrap fb-right-panel'):
            inbox = ClientInbox(
                on_status_change=on_status_updated,
                on_hitl_proposal=on_new_hitl_proposal,
                on_paypal_pay=on_paypal_payment,
            )
            inbox_ref['inbox'] = inbox
