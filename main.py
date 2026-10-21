from fastapi import FastAPI, Request, Depends, HTTPException
from sqlalchemy.orm import Session
import database as db_module

db_module.init_db()  # Inicializa la base de datos y crea las tablas si no existen

app=FastAPI(title="Paypal Collection Agent Backend")

@app.get("/")
def home():
    return {"message": "El agente de cobranza está activo y listo"}

#Receptor de webhooks de PayPal
@app.post("/api/paypal-webhook")
async def paypal_webhook(request: Request, db: Session = Depends(db_module.get_db)):
    try:
        #Recibe la notificacion JSON de PayPal
        body=await request.json()
        event_type=body.get("event_type")
        resource=body.get("resource", {})
        
        print(f"\n [Webhook recibido] Tipo de evento: {event_type}")

        #ID de la factura en PayPal
        paypal_id=resource.get("id")

        #Procesa el evento según su tipo
        if event_type=="INVOICING.INVOICE.PAID":
            print(f"La factura {paypal_id} ha sido pagada.")
            invoice=db.query(db_module.Invoice).filter(db_module.Invoice.paypal_invoice_id==paypal_id).first()
            if invoice:
                invoice.status="PAID"
                db.commit()

        elif event_type=="INVOICING.INVOICE.REFUNDED" or event_type=="INVOICING.INVOICE.CANCELLED":
            print(f"La factura {paypal_id} ha sido reembolsada o cancelada.")
            invoice=db.query(db_module.Invoice).filter(db_module.Invoice.paypal_invoice_id==paypal_id).first()
            if invoice:
                invoice.status="CANCELLED"
                db.commit()

        #Responder a Paypal confirmando que se recibió el webhook
        return{"status": "success", "event_processed": event_type}

    except Exception as e:
        print(f"Error al procesar el webhook: {e}")
        raise HTTPException(status_code=400, detail="Error procesando payload de Webhook")
    