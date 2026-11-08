"""Punto de entrada unificado de FacturaBot (Frontend NiceGUI + Backend FastAPI/PayPal)."""
from fastapi import Request, Depends, HTTPException
from nicegui import app, ui
from pydantic import BaseModel
from sqlalchemy.orm import Session

import database as db_module
import InvoicingAPI as paypal_api
from app.config import APP_PORT, APP_TITLE, STATIC_DIR
from app.services.agent_service import agent_reply, get_active_ai_provider
from app.services.invoice_service import (
    load_invoices,
    trigger_paypal_reminder,
    approve_partial_plan_in_paypal,
    process_paypal_payment,
    save_payment_agreement_in_db,
    update_invoice_status_in_db,
)
from app import pages  # noqa: F401  (registra las rutas de NiceGUI en '/')

# Inicializa la base de datos y crea las tablas si no existen
db_module.init_db()

# Archivos estáticos y tipografías del Frontend (NiceGUI)
app.add_static_files('/static', STATIC_DIR)
ui.add_head_html("""
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600&family=Space+Grotesk:wght@600;700&display=swap" rel="stylesheet">
<link rel="stylesheet" href="/static/css/styles.css">
""", shared=True)


class AgentChatRequest(BaseModel):
    client: str = "Globex"
    message: str
    amount: float = 8200.0
    lang: str | None = None


class ApprovePlanRequest(BaseModel):
    payments: int = 2


class RecordPaymentRequest(BaseModel):
    amount: float | None = None


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "message": "FacturaBot AI Collection Agent is active and monitoring",
        "paypal_base_url": paypal_api.Base_URL,
        "paypal_configured": paypal_api.is_configured(),
        "ai_engine": get_active_ai_provider(),
        "sponsor_integrations": ["PayPal Invoicing v2 API", "AG Grid", "Render", "Postman"],
    }


@app.get("/api/invoices")
def get_invoices():
    return load_invoices()


@app.post("/api/agent/chat")
def api_agent_chat(payload: AgentChatRequest):
    """Endpoint REST para interactuar con el agente de IA de cobranza."""
    res = agent_reply(
        text=payload.message,
        client=payload.client,
        amount=payload.amount,
        lang=payload.lang,
    )
    if res.get("hitl_proposal"):
        prop = res["hitl_proposal"]
        payments = prop.get("payments", 2)
        amt = float(prop.get("amount") or payload.amount)
        plan_desc = f"Plan de {payments} pagos (${amt / max(payments, 1):,.2f} USD c/u)"
        save_payment_agreement_in_db(payload.client, plan_desc, status="PENDING_HUMAN_APPROVAL")
    if res.get("new_status"):
        update_invoice_status_in_db(payload.client, res["new_status"])
    return res


@app.post("/api/invoices/{invoice_id}/remind")
def api_send_reminder(invoice_id: str):
    """Envía un recordatorio de pago mediante PayPal Invoicing v2 (/remind)."""
    result = trigger_paypal_reminder(invoice_id)
    if not result.get("ok"):
        raise HTTPException(status_code=404, detail=result.get("error", "Invoice not found"))
    return result


@app.post("/api/invoices/{invoice_id}/approve-plan")
def api_approve_plan(invoice_id: str, payload: ApprovePlanRequest):
    """Autoriza un plan de pagos parciales (Human-In-The-Loop) en PayPal Invoicing v2."""
    result = approve_partial_plan_in_paypal(invoice_id, payments=payload.payments)
    if not result.get("ok"):
        raise HTTPException(status_code=404, detail=result.get("error", "Invoice not found"))
    return result


@app.post("/api/invoices/{invoice_id}/pay")
def api_pay_invoice(invoice_id: str, payload: RecordPaymentRequest | None = None):
    """Registra el pago de una factura en PayPal Invoicing v2 y actualiza SQLite."""
    amt = payload.amount if payload else None
    return process_paypal_payment(invoice_id, amount=amt)


# Receptor de webhooks de PayPal
@app.post("/api/paypal-webhook")
async def paypal_webhook(request: Request, db: Session = Depends(db_module.get_db)):
    try:
        # Recibe la notificacion JSON de PayPal
        body = await request.json()
        event_type = body.get("event_type")
        resource = body.get("resource", {})

        print(f"\n [Webhook recibido] Tipo de evento: {event_type}")

        # ID de la factura en PayPal
        paypal_id = resource.get("id") or resource.get("invoice", {}).get("id")

        # Procesa el evento según su tipo
        if event_type == "INVOICING.INVOICE.PAID":
            print(f"La factura {paypal_id} ha sido pagada.")
            invoice = db.query(db_module.Invoice).filter(db_module.Invoice.paypal_invoice_id == paypal_id).first()
            if invoice:
                invoice.status = "Paid"
                db.commit()

        elif event_type in ("INVOICING.INVOICE.REFUNDED", "INVOICING.INVOICE.CANCELLED"):
            print(f"La factura {paypal_id} ha sido reembolsada o cancelada.")
            invoice = db.query(db_module.Invoice).filter(db_module.Invoice.paypal_invoice_id == paypal_id).first()
            if invoice:
                invoice.status = "Cancelled"
                db.commit()

        elif event_type in ("INVOICING.INVOICE.SENT", "INVOICING.INVOICE.SCHEDULED"):
            invoice = db.query(db_module.Invoice).filter(db_module.Invoice.paypal_invoice_id == paypal_id).first()
            if invoice and invoice.status != "Paid":
                invoice.status = "Pending"
                db.commit()

        # Responder a PayPal confirmando que se recibió el webhook
        return {"status": "success", "event_processed": event_type, "invoice_id": paypal_id}

    except Exception as e:
        print(f"Error al procesar el webhook: {e}")
        raise HTTPException(status_code=400, detail="Error procesando payload de Webhook")


if __name__ in {"__main__", "__mp_main__"}:
    ui.run(title=APP_TITLE, host="0.0.0.0", port=APP_PORT, reload=False, show=False)
