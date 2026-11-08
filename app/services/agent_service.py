"""Servicio de Agente de IA para Cobranza B2B con PayPal Invoicing y Human-In-The-Loop.

Incluye:
- Guardrails estrictos de dominio financiero (rechaza cualquier tema ajeno a cobranza/PayPal).
- Reglas de política crediticia B2B (máximo 6 cuotas, cuota mínima $1,000 USD, sin descuentos arbitrarios).
- Verificación anti-fraude (no marca una factura como Paid solo porque el usuario diga 'ya pagué' en texto).
"""
import json
import re
from datetime import datetime, timezone
from typing import Any
import requests

from app.config import (
    GEMINI_API_KEY,
    GEMINI_MODEL,
    OPENAI_API_KEY,
    OPENAI_BASE_URL,
    OPENAI_MODEL,
)

PLACEHOLDER_KEYS = {
    '',
    'your_gemini_api_key',
    'your_openai_api_key',
    'changeme',
}

MAX_ALLOWED_INSTALLMENTS = 6
MIN_INSTALLMENT_USD = 1000.0


def get_active_ai_provider() -> str:
    """Devuelve el nombre del motor de IA activo para mostrar en diagnósticos y UI."""
    if GEMINI_API_KEY and GEMINI_API_KEY not in PLACEHOLDER_KEYS:
        return f'Google Gemini ({GEMINI_MODEL})'
    if OPENAI_API_KEY and OPENAI_API_KEY not in PLACEHOLDER_KEYS:
        return f'OpenAI ({OPENAI_MODEL})'
    return 'FacturaBot Financial Policy Engine (Bilingual ES/EN)'


def _detect_language(text: str, default_lang: str = 'es') -> str:
    """Detecta si el mensaje del cliente está en inglés o español."""
    t = text.lower()
    en_markers = (
        'split', 'installment', 'partial', 'parts', 'paid', 'pay ', 'payment',
        'cannot', "can't", 'balance', 'how much', 'invoice', 'next week',
        'tomorrow', 'friday', 'monday', 'please', 'help', 'total now', 'hello', 'hi ',
    )
    es_markers = (
        'parte', 'parcial', 'cuota', 'pagu', 'pagado', 'cuánto', 'cuanto',
        'mañana', 'semana', 'factura', 'puedo', 'tengo', 'abono', 'mitad', 'hola', 'qué', 'que',
    )
    en_hits = sum(1 for w in en_markers if w in t)
    es_hits = sum(1 for w in es_markers if w in t)
    if en_hits > es_hits:
        return 'en'
    if es_hits > en_hits:
        return 'es'
    return default_lang if default_lang in ('es', 'en') else 'es'


def _extract_requested_installments(text: str) -> int:
    """Extrae el número de pagos solicitados por el cliente (incluso si excede el máximo para poder contraofertar)."""
    t = text.lower()
    word_map = {
        'two': 2, 'dos': 2, 'mitad': 2, 'half': 2,
        'three': 3, 'tres': 3,
        'four': 4, 'cuatro': 4,
        'five': 5, 'cinco': 5,
        'six': 6, 'seis': 6,
        'seven': 7, 'siete': 7,
        'eight': 8, 'ocho': 8,
        'ten': 10, 'diez': 10,
        'twelve': 12, 'doce': 12,
    }
    match = re.search(r'\b(\d{1,3})\s*(?:pagos?|partes?|cuotas?|payments?|installments?|parts?|meses|quincenas)\b', t)
    if match:
        return max(1, int(match.group(1)))
    for word, val in word_map.items():
        if re.search(rf'\b{word}\b', t):
            return val
    if '3' in t:
        return 3
    if '4' in t:
        return 4
    return 2


def _days_overdue_info(due_date_str: str) -> str:
    """Calcula cuántos días de vencimiento o plazo tiene la factura."""
    if not due_date_str:
        return 'Unknown due date'
    try:
        due_dt = datetime.strptime(due_date_str, '%Y-%m-%d').replace(tzinfo=timezone.utc)
        now_dt = datetime.now(timezone.utc)
        delta = (now_dt - due_dt).days
        if delta > 0:
            return f'{delta} days OVERDUE (since {due_date_str})'
        return f'Due in {abs(delta)} days ({due_date_str})'
    except Exception:
        return due_date_str


def _call_llm_agent(
    text: str,
    client: str,
    amount: float,
    lang: str,
    due_date: str = '',
    invoice_id: str = '',
    invoice_status: str = 'Overdue',
    history: list[dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    """Invoca a Gemini 3.5 Flash con Guardrails estrictos de cobranza B2B y políticas de PayPal."""
    has_gemini = bool(GEMINI_API_KEY and GEMINI_API_KEY not in PLACEHOLDER_KEYS)
    has_openai = bool(OPENAI_API_KEY and OPENAI_API_KEY not in PLACEHOLDER_KEYS)
    if not has_gemini and not has_openai:
        return None

    lang_name = 'English' if lang == 'en' else 'Spanish'
    overdue_desc = _days_overdue_info(due_date)
    max_by_min_amount = max(2, min(MAX_ALLOWED_INSTALLMENTS, int(amount // MIN_INSTALLMENT_USD) or 2))

    recent_context = ''
    if history:
        turns = history[-6:]
        recent_context = '\n'.join(f"- {m.get('sender', 'user')}: {m.get('text', '')}" for m in turns)

    system_prompt = (
        "You are FacturaBot, a strict, specialized B2B Accounts Receivable & Collections AI Agent "
        "operating exclusively on the PayPal Invoicing v2 Platform.\n\n"
        "=== LIVE INVOICE LEDGER DATA ===\n"
        f"- Client Company: {client}\n"
        f"- PayPal Invoice ID: {invoice_id or 'INV-2026-001'}\n"
        f"- Current Ledger Status: {invoice_status}\n"
        f"- Aging / Due Status: {overdue_desc}\n"
        f"- Outstanding Balance: ${amount:,.2f} USD\n"
        f"- Credit Policy Limits: Min 2 installments, Max {max_by_min_amount} installments (minimum ${MIN_INSTALLMENT_USD:,.2f} USD per installment). Zero discounts allowed without executive override.\n"
        f"- Output Language: {lang_name}\n\n"
        "=== STRICT SECURITY & DOMAIN GUARDRAILS (MANDATORY) ===\n"
        "1. NEVER answer general knowledge, science (e.g., Laplace's law, physics, math), history, coding, recipes, trivia, jokes, or ANY topic outside this specific PayPal invoice and its payment collection.\n"
        "2. If the user's message is completely off-topic, set `intent: \"GUARDRAIL_BLOCKED\"`, `trigger_hitl: false`, `show_paypal_btn: true`, and firmly state that you are an automated PayPal Invoicing Collections Agent and can only process payments or credit plans for Invoice "
        f"{invoice_id} (${amount:,.2f} USD).\n"
        "3. If the user mixes an off-topic question with a payment request (e.g. 'Split into 4 payments, and explain Laplace's law'), EXPLICITLY REFUSE the off-topic question in one short clause ('Por políticas de seguridad, solo atiendo gestiones de cobranza de PayPal') and immediately process ONLY the financial request.\n"
        "4. ANTI-FRAUD PAYMENT VERIFICATION: If the client claims 'I already paid' / 'Ya pagué' in text, DO NOT mark the invoice as paid (`mark_paid: false`) because the live PayPal ledger status is currently "
        f"'{invoice_status}'. Inform them that PayPal Invoicing API (`{invoice_id}`) still shows an unpaid balance of ${amount:,.2f} USD and ask them to complete payment via the official `[ Pay with PayPal ]` button (`show_paypal_btn: true`).\n"
        "5. CREDIT POLICY ENFORCEMENT:\n"
        f"   - If the client requests between 2 and {max_by_min_amount} installments: approve the structure, calculate the exact installment (${amount:,.2f} / N), set `trigger_hitl: true`, `installments: N`, `show_paypal_btn: false`, and explain it has been sent to Human-In-The-Loop supervision to enable `allow_partial_payment` on PayPal.\n"
        f"   - If the client requests MORE than {max_by_min_amount} installments or a discount: reject that term citing credit policy, counter-offer the maximum allowed {max_by_min_amount} installments (${amount / max_by_min_amount:,.2f} USD each), and set `trigger_hitl: true` with `installments: {max_by_min_amount}`.\n\n"
        "Return ONLY a valid JSON object with these exact keys:\n"
        "{\n"
        '  "intent": "INSTALLMENT_PROPOSAL" | "POLICY_COUNTEROFFER" | "UNVERIFIED_PAYMENT_CLAIM" | "PROMISE_TO_PAY" | "BALANCE_AUDIT" | "GUARDRAIL_BLOCKED",\n'
        '  "reasoning": "Brief internal audit log (1 sentence): e.g. [Guardrail: Off-topic blocked] or [Credit Policy: 4x $5,500 USD valid -> Escalating to HITL]",\n'
        '  "message": "Direct, professional financial collection response (2-3 sentences max, strictly focused on the invoice)",\n'
        '  "installments": 2,\n'
        '  "trigger_hitl": false,\n'
        '  "mark_paid": false,\n'
        '  "show_paypal_btn": true\n'
        "}"
    )
    user_prompt = f"Conversation history:\n{recent_context}\n\nClient message: \"{text}\""

    if has_gemini:
        candidate_models = [GEMINI_MODEL, 'gemini-3.5-flash-lite', 'gemini-3.1-flash-lite']
        seen = set()
        for model_name in candidate_models:
            if not model_name or model_name in seen:
                continue
            seen.add(model_name)
            try:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={GEMINI_API_KEY}"
                payload = {
                    "systemInstruction": {"parts": [{"text": system_prompt}]},
                    "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
                    "generationConfig": {
                        "temperature": 0.15,
                        "responseMimeType": "application/json",
                    },
                }
                resp = requests.post(url, json=payload, timeout=12)
                if not resp.ok:
                    continue
                raw_text = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
                parsed = json.loads(raw_text)
                parsed["_provider"] = f"Google Gemini ({model_name})"
                return parsed
            except Exception as exc:
                print(f"[FacturaBot AI] Intento con {model_name} falló: {exc}")
                continue

    if has_openai:
        try:
            url = f"{OPENAI_BASE_URL.rstrip('/')}/chat/completions"
            headers = {
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "Content-Type": "application/json",
            }
            payload = {
                "model": OPENAI_MODEL,
                "temperature": 0.15,
                "response_format": {"type": "json_object"},
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            }
            resp = requests.post(url, headers=headers, json=payload, timeout=12)
            resp.raise_for_status()
            raw_text = resp.json()["choices"][0]["message"]["content"]
            parsed = json.loads(raw_text)
            parsed["_provider"] = f"OpenAI ({OPENAI_MODEL})"
            return parsed
        except Exception as exc:
            print(f"[FacturaBot AI] Fallback a motor financiero local ({exc})")

    return None


def agent_reply(
    text: str,
    client: str = 'Cliente',
    amount: float = 0.0,
    lang: str | None = None,
    due_date: str = '',
    invoice_id: str = '',
    invoice_status: str = 'Overdue',
    history: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Analiza el mensaje del cliente aplicando Guardrails financieros y políticas de PayPal Invoicing."""
    detected_lang = _detect_language(text, default_lang=lang or 'es')
    max_by_min_amount = max(2, min(MAX_ALLOWED_INSTALLMENTS, int(amount // MIN_INSTALLMENT_USD) or 2))

    llm_res = _call_llm_agent(
        text,
        client=client,
        amount=amount,
        lang=detected_lang,
        due_date=due_date,
        invoice_id=invoice_id,
        invoice_status=invoice_status,
        history=history,
    )
    if llm_res and isinstance(llm_res, dict) and llm_res.get('message'):
        trigger_hitl = bool(llm_res.get('trigger_hitl'))
        raw_inst = int(llm_res.get('installments') or _extract_requested_installments(text))
        installments = max(2, min(max_by_min_amount, raw_inst))
        return {
            'message': str(llm_res['message']),
            'reasoning': str(llm_res.get('reasoning') or ''),
            'new_status': None,  # Nunca marcar Paid solo por texto sin verificación real de PayPal
            'hitl_proposal': (
                {
                    'client': client,
                    'payments': installments,
                    'amount': amount,
                }
                if trigger_hitl
                else None
            ),
            'show_paypal_btn': bool(llm_res.get('show_paypal_btn', not trigger_hitl)),
            'paypal_amount': amount,
            'intent': llm_res.get('intent', 'BALANCE_AUDIT'),
            'ai_provider': llm_res.get('_provider', get_active_ai_provider()),
        }

    # Motor de respaldo con Guardrails estrictos
    t = text.lower()
    is_en = detected_lang == 'en'

    plan_keywords = (
        'parte', 'parcial', 'plan', 'cuota', 'mitad', 'plazo',
        'no tengo el total', 'no cuento con el total', 'pagos',
        'dividir', 'abono', 'abonar', 'meses', 'quincenas',
        'split', 'installment', 'partial', 'parts', 'half', 'payments',
    )
    if any(k in t for k in plan_keywords):
        req_payments = _extract_requested_installments(text)
        num_payments = max(2, min(max_by_min_amount, req_payments))
        installment = (amount / num_payments) if amount else 0
        if is_en:
            msg = (
                f'As PayPal Invoicing Collections Agent for {client} (Invoice {invoice_id}, ${amount:,.2f} USD), '
                f'I have structured a {num_payments}-installment plan of ${installment:,.2f} USD per payment '
                f'and escalated it to Human-In-The-Loop supervision for PayPal authorization.'
            )
            reasoning = f'[Credit Policy] {num_payments}x ${installment:,.2f} USD validated -> Escalated to HITL.'
        else:
            msg = (
                f'En relación exclusiva a su factura {invoice_id} (${amount:,.2f} USD), he estructurado '
                f'un plan de {num_payments} cuotas de ${installment:,.2f} USD c/u y lo envié a supervisión '
                f'(Human-In-The-Loop) para habilitar el pago parcial en PayPal.'
            )
            reasoning = f'[Política de Crédito] {num_payments}x ${installment:,.2f} USD validado -> Escalado a HITL.'
        return {
            'message': msg,
            'reasoning': reasoning,
            'new_status': None,
            'hitl_proposal': {
                'client': client,
                'payments': num_payments,
                'amount': amount,
            },
            'show_paypal_btn': False,
            'paypal_amount': amount,
            'intent': 'INSTALLMENT_PROPOSAL',
            'ai_provider': get_active_ai_provider(),
        }

    paid_keywords = (
        'pagu', 'pagado', 'transfer', 'listo', 'comprobante', 'deposit', 'liquid',
        'i paid', 'already paid', 'just paid', 'payment sent',
    )
    if any(k in t for k in paid_keywords):
        msg = (
            f'We audited Invoice {invoice_id} in PayPal Sandbox and it still shows an unpaid balance '
            f'of ${amount:,.2f} USD ({invoice_status}). Please complete the payment using the official '
            f'PayPal Checkout button below so the webhook reconciles your account:'
            if is_en
            else f'He consultado en vivo la factura {invoice_id} en PayPal Invoicing y aún registra '
            f'un saldo pendiente de ${amount:,.2f} USD ({invoice_status}). Por favor realice el pago '
            f'mediante el botón oficial de PayPal a continuación para acreditarlo:'
        )
        return {
            'message': msg,
            'reasoning': f'[Auditoría PayPal] Reclamo de pago no verificado en ledger ({invoice_status}).',
            'new_status': None,
            'hitl_proposal': None,
            'show_paypal_btn': True,
            'paypal_amount': amount,
            'intent': 'UNVERIFIED_PAYMENT_CLAIM',
            'ai_provider': get_active_ai_provider(),
        }

    msg = (
        f'I am FacturaBot, an automated PayPal Invoicing Collections Agent. I can only assist with '
        f'Invoice {invoice_id} for {client} (Balance: ${amount:,.2f} USD, Due: {due_date}). '
        f'Would you like to pay in full via PayPal now or request a 2-to-{max_by_min_amount} installment plan?'
        if is_en
        else f'Soy el Agente de Cobranza de PayPal Invoicing y únicamente gestiono la factura '
        f'{invoice_id} de {client} (Saldo: ${amount:,.2f} USD, Vencimiento: {due_date}). '
        f'¿Desea liquidar el total ahora con PayPal o solicitar un plan de 2 a {max_by_min_amount} pagos?'
    )
    return {
        'message': msg,
        'reasoning': '[Guardrail Financiero] Respuesta restringida estrictamente al cobro de la factura.',
        'new_status': None,
        'hitl_proposal': None,
        'show_paypal_btn': True,
        'paypal_amount': amount,
        'intent': 'GUARDRAIL_BLOCKED',
        'ai_provider': get_active_ai_provider(),
    }
