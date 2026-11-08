import json
import database as db_module
import InvoicingAPI as paypal_api
from app.config import INVOICES_FILE


STATUS_MAP = {
    'PAID': 'Paid',
    'Paid': 'Paid',
    'OVERDUE': 'Overdue',
    'Overdue': 'Overdue',
    'PENDING': 'Pending',
    'Pending': 'Pending',
    'SENT': 'Pending',
    'PARTIAL_PLAN': 'Partial Plan',
    'Partial Plan': 'Partial Plan',
    'CANCELLED': 'Cancelled',
    'Cancelled': 'Cancelled',
}


def load_invoices():
    """Carga las facturas desde la base de datos SQLite (o inicializa desde JSON si está vacía)."""
    db_module.init_db()
    db = db_module.SessionLocal()
    try:
        invoices = db.query(db_module.Invoice).order_by(db_module.Invoice.due_date.asc()).all()
        if invoices:
            result = []
            for idx, inv in enumerate(invoices, start=1):
                due_str = (
                    inv.due_date.strftime('%Y-%m-%d')
                    if inv.due_date
                    else '2026-10-30'
                )
                client_display = inv.client_name or (
                    inv.client_email.split('@')[0].capitalize() if inv.client_email else f'Cliente {idx}'
                )
                inv_id = inv.paypal_invoice_id or f'INV-2026-{idx:03d}'
                result.append({
                    'id': inv_id,
                    'client': client_display,
                    'client_email': inv.client_email or f'billing@{client_display.lower().replace(" ", "")}.com',
                    'amount': float(inv.amount or 0.0),
                    'due_date': due_str,
                    'status': STATUS_MAP.get(inv.status, inv.status or 'Pending'),
                    'payment_url': f'https://www.sandbox.paypal.com/invoice/p/#{inv_id}',
                })
            return result
    finally:
        db.close()

    with open(INVOICES_FILE, encoding='utf-8') as f:
        data = json.load(f)
    for idx, inv in enumerate(data, start=1):
        if 'id' not in inv:
            inv['id'] = f'INV-2026-{idx:03d}'
    return data


def get_invoice_by_client_or_id(client_or_id: str) -> dict | None:
    """Busca una factura por nombre de cliente o ID de factura."""
    for inv in load_invoices():
        if inv['client'].lower() == client_or_id.lower() or inv['id'].lower() == client_or_id.lower():
            return inv
    return None


def update_invoice_status_in_db(
    client_or_id: str,
    new_status: str,
    new_amount: float | None = None,
    new_paypal_id: str | None = None,
):
    """Actualiza el estado de la factura en la base de datos SQLite."""
    normalized_status = STATUS_MAP.get(new_status, new_status)
    db = db_module.SessionLocal()
    try:
        inv = (
            db.query(db_module.Invoice)
            .filter(
                (db_module.Invoice.client_name == client_or_id)
                | (db_module.Invoice.paypal_invoice_id == client_or_id)
            )
            .first()
        )
        if inv:
            inv.status = normalized_status
            if new_amount is not None:
                inv.amount = float(new_amount)
            if new_paypal_id:
                inv.paypal_invoice_id = new_paypal_id
            db.commit()
    finally:
        db.close()


def save_payment_agreement_in_db(client: str, proposed_plan: str, status: str = 'PENDING_HUMAN_APPROVAL'):
    """Crea o actualiza un acuerdo de pago (PaymentAgreement) en la base de datos."""
    db = db_module.SessionLocal()
    try:
        inv = (
            db.query(db_module.Invoice)
            .filter(
                (db_module.Invoice.client_name == client)
                | (db_module.Invoice.paypal_invoice_id == client)
            )
            .first()
        )
        if not inv:
            return
        agreement = (
            db.query(db_module.PaymentAgreement)
            .filter(db_module.PaymentAgreement.invoice_id == inv.id)
            .order_by(db_module.PaymentAgreement.id.desc())
            .first()
        )
        if agreement and agreement.status == 'PENDING_HUMAN_APPROVAL':
            agreement.proposed_plan = proposed_plan
            agreement.status = status
        else:
            agreement = db_module.PaymentAgreement(
                invoice_id=inv.id,
                proposed_plan=proposed_plan,
                status=status,
            )
            db.add(agreement)
        db.commit()
    finally:
        db.close()


def _ensure_paypal_sandbox_invoice(inv: dict, allow_partial: bool = False, min_partial: float | None = None) -> str:
    """Si la factura tiene un ID semilla local (INV-2026-...) y PayPal Sandbox está activo, la crea en PayPal."""
    inv_id = inv['id']
    if inv_id.startswith('INV-2026-') and paypal_api.is_configured():
        created = paypal_api.create_and_send_invoice(
            client_name=inv['client'],
            client_email=inv.get('client_email', ''),
            amount=float(inv['amount']),
            allow_partial=allow_partial,
            min_partial_amount=min_partial,
        )
        new_id = created.get('paypal_invoice_id')
        if new_id and new_id != inv_id:
            update_invoice_status_in_db(inv['client'], inv['status'], new_paypal_id=new_id)
            return new_id
    return inv_id


def trigger_paypal_reminder(client_or_id: str) -> dict:
    """Envía un recordatorio a través de PayPal Invoicing v2 API para la factura indicada."""
    inv = get_invoice_by_client_or_id(client_or_id)
    if not inv:
        return {'ok': False, 'error': f'Invoice not found for {client_or_id}'}

    pp_id = _ensure_paypal_sandbox_invoice(inv)
    return paypal_api.send_invoice_reminder(
        paypal_invoice_id=pp_id,
        client_name=inv['client'],
        amount=inv['amount'],
        due_date=inv['due_date'],
    )


def approve_partial_plan_in_paypal(client_or_id: str, payments: int = 2) -> dict:
    """Aprueba el plan de pagos parciales en PayPal Invoicing v2 y actualiza SQLite."""
    inv = get_invoice_by_client_or_id(client_or_id)
    if not inv:
        return {'ok': False, 'error': f'Invoice not found for {client_or_id}'}

    amount = float(inv['amount'])
    installment = amount / max(payments, 1)
    plan_desc = f'Plan de {payments} pagos (${installment:,.2f} USD c/u)'

    paypal_res = paypal_api.enable_partial_payment_plan(
        paypal_invoice_id=inv['id'],
        client_name=inv['client'],
        client_email=inv.get('client_email', ''),
        total_amount=amount,
        installments=payments,
    )

    new_pp_id = paypal_res.get('paypal_invoice_id')
    save_payment_agreement_in_db(inv['client'], plan_desc, status='APPROVED')
    update_invoice_status_in_db(
        inv['client'],
        'Partial Plan',
        new_paypal_id=new_pp_id if new_pp_id and new_pp_id != inv['id'] else None,
    )
    return {
        **paypal_res,
        'client': inv['client'],
        'payments': payments,
        'installment': installment,
        'plan_description': plan_desc,
    }


def process_paypal_payment(client_or_id: str, amount: float | None = None) -> dict:
    """Registra el pago en PayPal Invoicing v2 y actualiza el estado de la factura a Paid."""
    inv = get_invoice_by_client_or_id(client_or_id)
    paid_amount = float(amount if amount is not None else (inv['amount'] if inv else 0.0))
    client_name = inv['client'] if inv else client_or_id
    pp_id = _ensure_paypal_sandbox_invoice(inv) if inv else client_or_id

    paypal_res = paypal_api.record_invoice_payment(
        paypal_invoice_id=pp_id,
        amount=paid_amount,
    )
    update_invoice_status_in_db(client_name, 'Paid', new_paypal_id=pp_id if pp_id else None)
    return {
        **paypal_res,
        'client': client_name,
        'amount_paid': paid_amount,
        'new_status': 'Paid',
    }
