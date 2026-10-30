import json
import database as db_module
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
                result.append({
                    'id': inv.paypal_invoice_id or f'INV-2026-{idx:03d}',
                    'client': client_display,
                    'client_email': inv.client_email or '',
                    'amount': float(inv.amount or 0.0),
                    'due_date': due_str,
                    'status': STATUS_MAP.get(inv.status, inv.status or 'Pending'),
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


def update_invoice_status_in_db(client_or_id: str, new_status: str, new_amount: float | None = None):
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
            db.commit()
    finally:
        db.close()


def save_payment_agreement_in_db(client: str, proposed_plan: str, status: str = 'PENDING_HUMAN_APPROVAL'):
    """Crea o actualiza un acuerdo de pago (PaymentAgreement) en la base de datos."""
    db = db_module.SessionLocal()
    try:
        inv = db.query(db_module.Invoice).filter(db_module.Invoice.client_name == client).first()
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
