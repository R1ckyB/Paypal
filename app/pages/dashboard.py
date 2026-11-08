from nicegui import ui

from app.config import COLORS
from app.components import app_header, invoice_grid, set_status, ClientInbox
from app.services.invoice_service import (
    save_payment_agreement_in_db,
    approve_partial_plan_in_paypal,
)


@ui.page('/')
def dashboard_page():
    ui.colors(**COLORS)

    # Estado reactivo de idioma ('es' por defecto para mantener diseño original, alternable a 'en' para jueces)
    lang_state = {'lang': 'es'}

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
    header_refs = {'refs': None}

    def toggle_lang():
        lang_state['lang'] = 'en' if lang_state['lang'] == 'es' else 'es'
        is_en = lang_state['lang'] == 'en'
        ui.run_javascript(f"window.__fbLang = '{lang_state['lang']}';")

        if header_refs['refs'] and header_refs['refs'].get('subtitle_label'):
            header_refs['refs']['subtitle_label'].text = (
                'Intelligent AI Collections (PayPal Invoicing v2 API)'
                if is_en
                else 'Cobranza inteligente con IA (Invoicing API)'
            )

        dash_title.text = 'Invoice Dashboard' if is_en else 'Dashboard de Facturas'
        kpi_pending_title.text = 'Pending' if is_en else 'Pendiente'
        kpi_recovered_title.text = 'Recovered' if is_en else 'Recuperado'
        kpi_ai_title.text = 'AI Status' if is_en else 'Estado de IA'
        kpi_ai_status.text = 'Active & Monitoring' if is_en else 'Activo y Monitoreando'
        approve_btn.text = 'APPROVE IN PAYPAL' if is_en else 'APROBAR EN PAYPAL'
        reject_btn.text = 'REJECT' if is_en else 'RECHAZAR'

        if grid_ref['grid']:
            grid_ref['grid'].set_language(lang_state['lang'])
        if inbox_ref['inbox']:
            inbox_ref['inbox'].set_language(lang_state['lang'])
        refresh_hitl()

    def toggle_grid():
        if not grid_ref['grid']:
            return
        is_ag = grid_ref['grid'].toggle_grid_mode()
        if header_refs['refs'] and header_refs['refs'].get('grid_btn'):
            header_refs['refs']['grid_btn'].text = 'AG Grid: ON' if is_ag else 'AG Grid: View'
        ui.notify(
            'AG Grid Interactive Mode Activated (Sponsor Track)'
            if is_ag
            else 'FacturaBot Compact Table View Activated',
            color='primary',
        )

    header_refs['refs'] = app_header(
        lang=lang_state['lang'],
        on_toggle_lang=toggle_lang,
        on_toggle_grid_mode=toggle_grid,
    )
    if header_refs['refs'] and header_refs['refs'].get('grid_btn'):
        header_refs['refs']['grid_btn'].text = 'AG Grid: View'

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
        is_en = lang_state['lang'] == 'en'
        if hitl_state['active']:
            c = hitl_state['client']
            n = hitl_state['payments']
            hitl_text.text = (
                f'AI Proposal: Approve {n}-installment payment plan for {c}?'
                if is_en
                else f'Propuesta de IA: ¿Aprobar plan de {n} pagos para {c}?'
            )
            approve_btn.set_visibility(True)
            reject_btn.set_visibility(True)
        else:
            default_idle = (
                'No proposals pending human approval.'
                if is_en
                else 'Sin propuestas pendientes de aprobación humana.'
            )
            hitl_text.text = hitl_state['resolved_msg'] or default_idle
            approve_btn.set_visibility(False)
            reject_btn.set_visibility(False)

    def handle_approve():
        if not hitl_state['active']:
            return
        is_en = lang_state['lang'] == 'en'
        client = hitl_state['client']
        payments = hitl_state['payments']
        amount = hitl_state['amount']
        hitl_state['active'] = False

        # Ejecuta la aprobación real/híbrida en PayPal Invoicing v2 API (allow_partial_payment=True)
        pp_res = approve_partial_plan_in_paypal(client, payments=payments)
        installment = amount / max(payments, 1)

        hitl_state['resolved_msg'] = (
            f'✅ {payments}-payment plan for {client} approved in PayPal (${installment:,.2f}/payment).'
            if is_en
            else f'✅ Plan de {payments} pagos para {client} aprobado en PayPal (${installment:,.2f}/pago).'
        )
        set_status(grid_ref['grid'], client, 'Partial Plan')
        inbox_ref['inbox'].notify_plan_approved(client, payments, amount, paypal_info=pp_res)
        refresh_hitl()
        refresh_kpis()
        ui.notify(
            f'PayPal Partial Payment Plan ({payments}x ${installment:,.2f}) approved for {client}'
            if is_en
            else f'Plan de {payments} pagos aprobado en PayPal para {client}',
            type='positive',
        )

    def handle_reject():
        if not hitl_state['active']:
            return
        is_en = lang_state['lang'] == 'en'
        client = hitl_state['client']
        payments = hitl_state['payments']
        amount = hitl_state['amount']
        hitl_state['active'] = False
        plan_desc = f'Plan de {payments} pagos (${amount / max(payments, 1):,.2f} USD c/u)'
        hitl_state['resolved_msg'] = (
            f'❌ Partial payment proposal for {client} rejected. Full payment required.'
            if is_en
            else f'❌ Propuesta de pagos parciales para {client} rechazada. Se requiere pago total.'
        )
        save_payment_agreement_in_db(client, plan_desc, status='REJECTED')
        inbox_ref['inbox'].notify_plan_rejected(client, amount)
        refresh_hitl()
        refresh_kpis()
        ui.notify(
            f'Proposal for {client} rejected' if is_en else f'Propuesta para {client} rechazada',
            type='warning',
        )

    def on_new_hitl_proposal(proposal: dict):
        is_en = lang_state['lang'] == 'en'
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
        ui.notify(
            f'New Human-In-The-Loop proposal generated for {client}'
            if is_en
            else f'Nueva propuesta Human-In-The-Loop generada para {client}',
            color='warning',
        )

    def on_paypal_payment(client: str, amount: float):
        is_en = lang_state['lang'] == 'en'
        set_status(grid_ref['grid'], client, 'Paid')
        if hitl_state['active'] and hitl_state['client'] == client:
            hitl_state['active'] = False
            hitl_state['resolved_msg'] = (
                f'✅ Invoice for {client} settled via PayPal.'
                if is_en
                else f'✅ Factura de {client} liquidada mediante PayPal.'
            )
            refresh_hitl()
        refresh_kpis()
        ui.notify(
            f'PayPal payment of ${amount:,.2f} received ({client})'
            if is_en
            else f'Pago de ${amount:,.2f} recibido en PayPal ({client})',
            type='positive',
        )

    def on_status_updated(client: str, status: str):
        is_en = lang_state['lang'] == 'en'
        set_status(grid_ref['grid'], client, status)
        if status == 'Paid' and hitl_state['active'] and hitl_state['client'] == client:
            hitl_state['active'] = False
            hitl_state['resolved_msg'] = (
                f'✅ Invoice for {client} marked as Paid.'
                if is_en
                else f'✅ Factura de {client} marcada como pagada.'
            )
            refresh_hitl()
        refresh_kpis()

    # Contenedor principal dividido (Dashboard izquierda | Bandeja derecha)
    with ui.row().classes('w-full no-wrap fb-main-layout'):
        # Panel Izquierdo: Dashboard de Facturas
        with ui.column().classes('h-full justify-between no-wrap fb-left-panel'):
            # Título
            dash_title = ui.label('Dashboard de Facturas').classes(
                'text-white text-base font-bold tracking-tight mb-1'
            )

            # Tarjetas KPI (Pendiente, Recuperado, Estado de IA)
            with ui.row().classes('w-full gap-3 no-wrap mb-2'):
                with ui.column().classes('flex-1 fb-kpi-card gap-0.5'):
                    kpi_pending_title = ui.label('Pendiente').classes('fb-kpi-title')
                    pending_label = ui.label('($50,400.00)').classes('fb-kpi-value')

                with ui.column().classes('flex-1 fb-kpi-card gap-0.5'):
                    kpi_recovered_title = ui.label('Recuperado').classes('fb-kpi-title')
                    recovered_label = ui.label('($3,400.00)').classes('fb-kpi-value')

                with ui.column().classes('flex-1 fb-kpi-card gap-1 justify-between'):
                    kpi_ai_title = ui.label('Estado de IA').classes('fb-kpi-title')
                    with ui.row().classes('items-center gap-2 no-wrap mt-0.5'):
                        kpi_ai_status = ui.label('Activo y Monitoreando').classes('fb-ai-status-text')
                        ui.html('<span class="fb-ai-dot"></span>')

            # Tabla de Facturas (Soporta Vista FacturaBot + AG Grid)
            grid = invoice_grid(
                on_send_reminder=lambda row: inbox_ref['inbox'].send_reminder(
                    row['client'], row['amount'], row['due_date'], row.get('id')
                ),
                on_select_client=lambda row: inbox_ref['inbox'].select_client(row),
                on_data_change=refresh_kpis,
                lang=lang_state['lang'],
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
                lang=lang_state['lang'],
            )
            inbox_ref['inbox'] = inbox
