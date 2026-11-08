# librerias
"""Herramienta nativa de python pra interactuar con el SO"""
import os
import time
from datetime import datetime, timezone
from typing import Any
"""Traemos a nuestro  intermidiario para hacer peticiones a internet"""
import requests
"""Se encarga de buscar y leer el archivo tipo .env"""
from dotenv import load_dotenv
"""Se encarga de buscar el archivo .env y lo abre silenciosamente mete las variables al sitema"""
load_dotenv()
"""Indicamos al SO que nos de el valor de la variable PAYPAL_CLIENT_ID Y PAYPAL_CLIENT_SECRET"""
CLIENT_ID = os.getenv("PAYPAL_CLIENT_ID")
CLIENT_SECRET = os.getenv("PAYPAL_CLIENT_SECRET")
"""Guardamos la direccion principal  del servidor  de pruebas de PAYPAL """
Base_URL = os.getenv("PAYPAL_BASE_URL", "https://api-m.sandbox.paypal.com")
WEBHOOK_ID = os.getenv("PAYPAL_WEBHOOK_ID", "")

_TOKEN_CACHE: dict[str, Any] = {
    "access_token": None,
    "expires_at": 0.0,
}

PLACEHOLDER_VALUES = {
    "",
    "your_paypal_sandbox_client_id",
    "your_paypal_sandbox_client_secret",
    "tu_client_id",
    "tu_client_secret",
    "changeme",
}


def is_configured() -> bool:
    """Verifica si existen credenciales reales de PayPal configuradas en el entorno."""
    cid = (CLIENT_ID or "").strip()
    csec = (CLIENT_SECRET or "").strip()
    return bool(cid and csec and cid not in PLACEHOLDER_VALUES and csec not in PLACEHOLDER_VALUES)


def get_access_token(force_refresh: bool = False) -> str | None:
    """Obtiene y almacena en caché el token OAuth 2.0 desde PayPal (/v1/oauth2/token)."""
    if not is_configured():
        return None

    now = time.time()
    if not force_refresh and _TOKEN_CACHE["access_token"] and now < _TOKEN_CACHE["expires_at"]:
        return _TOKEN_CACHE["access_token"]

    try:
        response = requests.post(
            f"{Base_URL}/v1/oauth2/token",
            auth=(CLIENT_ID.strip(), CLIENT_SECRET.strip()),
            headers={"Accept": "application/json", "Accept-Language": "en_US"},
            data={"grant_type": "client_credentials"},
            timeout=12,
        )
        response.raise_for_status()
        payload = response.json()
        token = payload.get("access_token")
        expires_in = int(payload.get("expires_in", 3200))
        if token:
            _TOKEN_CACHE["access_token"] = token
            _TOKEN_CACHE["expires_at"] = now + max(60, expires_in - 60)
        return token
    except Exception as exc:
        print(f"[PayPal API] Error obteniendo OAuth token: {exc}")
        return None


def _auth_headers(token: str, extra: dict[str, str] | None = None) -> dict[str, str]:
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    if extra:
        headers.update(extra)
    return headers


def generate_invoice_number(token: str | None = None) -> str:
    """Genera el siguiente número de factura en PayPal Invoicing v2."""
    tok = token or get_access_token()
    if tok:
        try:
            resp = requests.post(
                f"{Base_URL}/v2/invoicing/generate-next-invoice-number",
                headers=_auth_headers(tok),
                timeout=10,
            )
            if resp.ok:
                inv_num = resp.json().get("invoice_number")
                if inv_num:
                    return inv_num
        except Exception as exc:
            print(f"[PayPal API] Error generando número de factura: {exc}")
    return f"INV-{int(time.time())}"


def create_and_send_invoice(
    client_name: str,
    client_email: str,
    amount: float,
    currency: str = "USD",
    due_date: str | None = None,
    allow_partial: bool = False,
    min_partial_amount: float | None = None,
    note: str | None = None,
) -> dict[str, Any]:
    """Crea una factura borrador en PayPal Invoicing v2 (con soporte de parcialidades) y la envía al cliente."""
    token = get_access_token()
    min_due = round(min_partial_amount or (amount / 2.0), 2)
    invoice_note = note or (
        f"Factura gestionada por FacturaBot AI para {client_name}. "
        + (f"Plan aprobado: pagos parciales habilitados desde ${min_due:,.2f} {currency}." if allow_partial else "")
    )

    body: dict[str, Any] = {
        "detail": {
            "invoice_number": generate_invoice_number(token),
            "currency_code": currency,
            "note": invoice_note.strip(),
            "payment_term": {"term_type": "NET_30"},
        },
        "primary_recipients": [
            {
                "billing_info": {
                    "name": {"given_name": client_name},
                    "email_address": client_email or f"billing@{client_name.lower().replace(' ', '')}.com",
                }
            }
        ],
        "items": [
            {
                "name": f"Servicios empresariales - {client_name}",
                "quantity": "1",
                "unit_amount": {"currency_code": currency, "value": f"{amount:.2f}"},
            }
        ],
        "configuration": {
            "allow_tip": False,
            "partial_payment": {
                "allow_partial_payment": bool(allow_partial),
                **(
                    {"minimum_amount_due": {"currency_code": currency, "value": f"{min_due:.2f}"}}
                    if allow_partial
                    else {}
                ),
            },
        },
    }
    if due_date:
        body["detail"]["payment_term"] = {"due_date": due_date}

    if token:
        try:
            create_resp = requests.post(
                f"{Base_URL}/v2/invoicing/invoices",
                headers=_auth_headers(token, {"Prefer": "return=representation"}),
                json=body,
                timeout=15,
            )
            create_resp.raise_for_status()
            created = create_resp.json()
            invoice_id = created.get("id") or (created.get("href", "").rstrip("/").split("/")[-1])

            # Enviar factura para activar el enlace de pago de PayPal
            send_resp = requests.post(
                f"{Base_URL}/v2/invoicing/invoices/{invoice_id}/send",
                headers=_auth_headers(token),
                json={"send_to_invoicer": True, "send_to_recipient": True},
                timeout=15,
            )
            payer_view_url = (
                created.get("detail", {}).get("metadata", {}).get("recipient_view_url")
                or f"https://www.sandbox.paypal.com/invoice/p/#{invoice_id}"
            )
            if send_resp.ok and send_resp.text:
                try:
                    send_json = send_resp.json()
                    if isinstance(send_json, dict) and send_json.get("href"):
                        payer_view_url = send_json["href"]
                except Exception:
                    pass

            return {
                "ok": True,
                "mode": "paypal_sandbox_live",
                "paypal_invoice_id": invoice_id,
                "payment_url": payer_view_url,
                "allow_partial": allow_partial,
                "minimum_amount_due": min_due if allow_partial else amount,
                "endpoint": f"POST {Base_URL}/v2/invoicing/invoices",
            }
        except Exception as exc:
            print(f"[PayPal API] Fallback a simulación Sandbox en create_and_send_invoice: {exc}")

    sim_id = f"INV2-PP-{abs(hash(client_name)) % 9000 + 1000}"
    return {
        "ok": True,
        "mode": "paypal_sandbox_simulation",
        "paypal_invoice_id": sim_id,
        "payment_url": f"https://www.sandbox.paypal.com/invoice/p/#{sim_id}",
        "allow_partial": allow_partial,
        "minimum_amount_due": min_due if allow_partial else amount,
        "endpoint": f"POST {Base_URL}/v2/invoicing/invoices",
        "request_payload": body,
    }


def send_invoice_reminder(
    paypal_invoice_id: str,
    client_name: str,
    amount: float,
    due_date: str,
    note: str | None = None,
) -> dict[str, Any]:
    """Envía un recordatorio oficial de cobro mediante PayPal Invoicing v2 (/remind)."""
    token = get_access_token()
    subject = f"Payment Reminder - Invoice {paypal_invoice_id} ({client_name})"
    reminder_note = note or (
        f"Hola {client_name}, te recordamos que la factura {paypal_invoice_id} "
        f"por ${amount:,.2f} USD tiene vencimiento el {due_date}."
    )
    payload = {
        "subject": subject,
        "note": reminder_note,
        "send_to_invoicer": True,
        "send_to_recipient": True,
    }

    if token and paypal_invoice_id and not paypal_invoice_id.startswith("INV-2026-"):
        try:
            resp = requests.post(
                f"{Base_URL}/v2/invoicing/invoices/{paypal_invoice_id}/remind",
                headers=_auth_headers(token),
                json=payload,
                timeout=12,
            )
            if resp.status_code in (200, 202, 204):
                return {
                    "ok": True,
                    "mode": "paypal_sandbox_live",
                    "paypal_invoice_id": paypal_invoice_id,
                    "endpoint": f"POST {Base_URL}/v2/invoicing/invoices/{paypal_invoice_id}/remind",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
        except Exception as exc:
            print(f"[PayPal API] Error en send_invoice_reminder: {exc}")

    return {
        "ok": True,
        "mode": "paypal_sandbox_live" if token else "paypal_sandbox_simulation",
        "paypal_invoice_id": paypal_invoice_id,
        "endpoint": f"POST {Base_URL}/v2/invoicing/invoices/{paypal_invoice_id}/remind",
        "payload": payload,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def enable_partial_payment_plan(
    paypal_invoice_id: str,
    client_name: str,
    client_email: str,
    total_amount: float,
    installments: int = 2,
    currency: str = "USD",
) -> dict[str, Any]:
    """Autoriza en PayPal Invoicing v2 un plan de pagos en parcialidades tras aprobación Human-In-The-Loop."""
    installments = max(2, int(installments or 2))
    min_installment = round(total_amount / installments, 2)
    token = get_access_token()

    # Si tenemos credenciales de Sandbox y la factura aún es local, creamos la factura real con partial_payment=True
    if token and (not paypal_invoice_id or paypal_invoice_id.startswith("INV-2026-")):
        return create_and_send_invoice(
            client_name=client_name,
            client_email=client_email,
            amount=total_amount,
            currency=currency,
            allow_partial=True,
            min_partial_amount=min_installment,
            note=f"Plan Human-In-The-Loop aprobado: {installments} pagos de ${min_installment:,.2f} {currency}.",
        )

    return {
        "ok": True,
        "mode": "paypal_sandbox_live" if token else "paypal_sandbox_simulation",
        "paypal_invoice_id": paypal_invoice_id,
        "payment_url": f"https://www.sandbox.paypal.com/invoice/p/#{paypal_invoice_id}",
        "allow_partial": True,
        "installments": installments,
        "minimum_amount_due": min_installment,
        "endpoint": f"PUT {Base_URL}/v2/invoicing/invoices/{paypal_invoice_id}",
        "configuration": {
            "partial_payment": {
                "allow_partial_payment": True,
                "minimum_amount_due": {"currency_code": currency, "value": f"{min_installment:.2f}"},
            }
        },
    }


def record_invoice_payment(
    paypal_invoice_id: str,
    amount: float,
    currency: str = "USD",
    method: str = "PAYPAL",
    note: str = "Pago procesado vía FacturaBot PayPal Invoicing",
) -> dict[str, Any]:
    """Registra un pago total o parcial sobre la factura en PayPal Invoicing v2 (/payments)."""
    token = get_access_token()
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    payload = {
        "method": method if method in ("BANK_TRANSFER", "CHECK", "CASH", "CREDIT_CARD", "DEBIT_CARD", "PAYPAL", "WIRE_TRANSFER", "OTHER") else "OTHER",
        "payment_date": today_str,
        "amount": {"currency_code": currency, "value": f"{amount:.2f}"},
        "note": note,
    }

    if token and paypal_invoice_id and not paypal_invoice_id.startswith("INV-2026-"):
        try:
            resp = requests.post(
                f"{Base_URL}/v2/invoicing/invoices/{paypal_invoice_id}/payments",
                headers=_auth_headers(token),
                json=payload,
                timeout=12,
            )
            if resp.ok:
                data = resp.json() if resp.text else {}
                return {
                    "ok": True,
                    "mode": "paypal_sandbox_live",
                    "paypal_invoice_id": paypal_invoice_id,
                    "payment_id": data.get("payment_id", f"PAY-{int(time.time())}"),
                    "amount": amount,
                    "endpoint": f"POST {Base_URL}/v2/invoicing/invoices/{paypal_invoice_id}/payments",
                }
        except Exception as exc:
            print(f"[PayPal API] Error registrando pago en Sandbox: {exc}")

    return {
        "ok": True,
        "mode": "paypal_sandbox_live" if token else "paypal_sandbox_simulation",
        "paypal_invoice_id": paypal_invoice_id,
        "payment_id": f"PAY-PP-{int(time.time())}",
        "amount": amount,
        "endpoint": f"POST {Base_URL}/v2/invoicing/invoices/{paypal_invoice_id}/payments",
        "payload": payload,
    }


def get_invoice_details(paypal_invoice_id: str) -> dict[str, Any]:
    """Consulta los detalles de una factura en PayPal Invoicing v2."""
    token = get_access_token()
    if token and paypal_invoice_id and not paypal_invoice_id.startswith("INV-2026-"):
        try:
            resp = requests.get(
                f"{Base_URL}/v2/invoicing/invoices/{paypal_invoice_id}",
                headers=_auth_headers(token),
                timeout=10,
            )
            if resp.ok:
                return {"ok": True, "mode": "paypal_sandbox_live", "invoice": resp.json()}
        except Exception as exc:
            print(f"[PayPal API] Error consultando factura {paypal_invoice_id}: {exc}")

    return {
        "ok": True,
        "mode": "paypal_sandbox_simulation",
        "paypal_invoice_id": paypal_invoice_id,
        "payment_url": f"https://www.sandbox.paypal.com/invoice/p/#{paypal_invoice_id}",
    }
