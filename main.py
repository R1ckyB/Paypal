"""Punto de entrada unificado de FacturaBot (Frontend NiceGUI + Backend FastAPI/PayPal)."""
from fastapi import Request, Depends, HTTPException
from nicegui import app, ui
from sqlalchemy.orm import Session

import database as db_module
import InvoicingAPI as paypal_api
from app.config import APP_PORT, APP_TITLE, STATIC_DIR
from app.services.invoice_service import load_invoices
from app import pages  # noqa: F401  (registra las rutas de NiceGUI en '/')

# Inicializa la base de datos y crea las tablas si no existen
db_module.init_db()

# Archivos estáticos y tipografías del Frontend (NiceGUI)
app.add_static_files('/static', STATIC_DIR)
ui.add_head_html("""
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600&family=Space+Grotesk:wght@600;700&display=swap" rel="stylesheet">
<link rel="stylesheet" href="/static/css/styles.css">
""", shared=True)


@app.get("/api/health")
def health():
    return {
        "message": "El agente de cobranza está activo y listo",
        "paypal_base_url": paypal_api.Base_URL,
        "paypal_configured": bool(paypal_api.CLIENT_ID and paypal_api.CLIENT_SECRET),
    }


@app.get("/api/invoices")
def get_invoices():
    return load_invoices()


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
        paypal_id = resource.get("id")

        # Procesa el evento según su tipo
        if event_type == "INVOICING.INVOICE.PAID":
            print(f"La factura {paypal_id} ha sido pagada.")
            invoice = db.query(db_module.Invoice).filter(db_module.Invoice.paypal_invoice_id == paypal_id).first()
            if invoice:
                invoice.status = "PAID"
                db.commit()

        elif event_type == "INVOICING.INVOICE.REFUNDED" or event_type == "INVOICING.INVOICE.CANCELLED":
            print(f"La factura {paypal_id} ha sido reembolsada o cancelada.")
            invoice = db.query(db_module.Invoice).filter(db_module.Invoice.paypal_invoice_id == paypal_id).first()
            if invoice:
                invoice.status = "CANCELLED"
                db.commit()

        # Responder a PayPal confirmando que se recibió el webhook
        return {"status": "success", "event_processed": event_type}

    except Exception as e:
        print(f"Error al procesar el webhook: {e}")
        raise HTTPException(status_code=400, detail="Error procesando payload de Webhook")


ui.run(title=APP_TITLE, port=APP_PORT, reload=False, show=True)
