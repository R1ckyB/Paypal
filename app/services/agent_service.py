"""Servicio de Agente de IA para Cobranza B2B con PayPal Invoicing y Human-In-The-Loop.

Soporta:
1. Google Gemini API (gemini-3.5-flash / gemini-3.5-flash-lite) con Structured JSON Output.
2. OpenAI / Compatible API con Structured JSON Output.
3. Motor NLU determinista bilingüe (ES/EN) como fallback en caso de falta de red.
"""
import json
import re
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


def get_active_ai_provider() -> str:
    """Devuelve el nombre del motor de IA activo para mostrar en diagnósticos y UI."""
    if GEMINI_API_KEY and GEMINI_API_KEY not in PLACEHOLDER_KEYS:
        return f'Google Gemini ({GEMINI_MODEL})'
    if OPENAI_API_KEY and OPENAI_API_KEY not in PLACEHOLDER_KEYS:
        return f'OpenAI ({OPENAI_MODEL})'
    return 'FacturaBot Hybrid NLU + Rules Engine (Bilingual ES/EN)'


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


def _extract_installments(text: str) -> int:
    """Extrae el número de pagos solicitados por el cliente (entre 2 y 6)."""
    t = text.lower()
    word_map = {
        'two': 2, 'dos': 2, 'mitad': 2, 'half': 2,
        'three': 3, 'tres': 3,
        'four': 4, 'cuatro': 4,
        'five': 5, 'cinco': 5,
        'six': 6, 'seis': 6,
    }
    for word, val in word_map.items():
        if re.search(rf'\b{word}\b', t):
            return val
    match = re.search(r'\b([2-6])\s*(?:pagos?|partes?|cuotas?|payments?|installments?|parts?|meses|quincenas)\b', t)
    if match:
        return int(match.group(1))
    if '3' in t:
        return 3
    if '4' in t:
        return 4
    return 2


def _call_llm_agent(
    text: str,
    client: str,
    amount: float,
    lang: str,
    due_date: str = '',
    invoice_id: str = '',
    history: list[dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    """Invoca a Gemini 3.5 Flash (o fallback 3.5-flash-lite / OpenAI) para razonar y negociar con el cliente."""
    has_gemini = bool(GEMINI_API_KEY and GEMINI_API_KEY not in PLACEHOLDER_KEYS)
    has_openai = bool(OPENAI_API_KEY and OPENAI_API_KEY not in PLACEHOLDER_KEYS)
    if not has_gemini and not has_openai:
        return None

    lang_name = 'English' if lang == 'en' else 'Spanish'
    recent_context = ''
    if history:
        turns = history[-6:]
        recent_context = '\n'.join(f"- {m.get('sender', 'user')}: {m.get('text', '')}" for m in turns)

    system_prompt = (
        "You are FacturaBot, an intelligent, empathetic B2B Accounts Receivable & Collections AI Agent "
        "powered by PayPal Invoicing v2 API and a Human-In-The-Loop (HITL) supervisor credit workflow.\n"
        f"- Client Company: {client}\n"
        f"- Invoice ID: {invoice_id or 'INV-2026'}\n"
        f"- Invoice Due Date: {due_date or '2026-09-30'}\n"
        f"- Outstanding Balance: ${amount:,.2f} USD\n"
        f"- Preferred Language: {lang_name} (always reply in the language the client used in their last message).\n\n"
        "BEHAVIOR GUIDELINES:\n"
        "1. Think carefully about what the client is actually saying or asking. Respond naturally and specifically to their situation (never sound like a rigid template).\n"
        "2. If the client asks to split the payment, pay in installments/parts, or says they only have part of the money right now:\n"
        "   - Calculate the exact installment amount ($amount / installments).\n"
        "   - Set `trigger_hitl: true` and `installments` to the number of payments requested (2 to 6, default 2).\n"
        "   - Explain warmly that you have structured the plan and sent it to the Human-In-The-Loop supervisor to enable `allow_partial_payment` on their PayPal Invoice.\n"
        "   - Set `show_paypal_btn: false` while waiting for human approval.\n"
        "3. If the client confirms they already paid or sent the transfer:\n"
        "   - Set `mark_paid: true` and `show_paypal_btn: false`, and thank them warmly.\n"
        "4. If the client promises to pay on a specific date, asks a question about the invoice, asks for a discount, or explains a delay:\n"
        "   - Address their specific point empathetically, mention the invoice details ($amount USD), and offer either immediate PayPal checkout (`show_paypal_btn: true`) or the option to request an installment plan.\n\n"
        "Return ONLY a valid JSON object with these exact keys:\n"
        "{\n"
        '  "intent": "INSTALLMENT_REQUEST" | "PAYMENT_CONFIRMATION" | "PROMISE_TO_PAY" | "BALANCE_INQUIRY" | "NEGOTIATION_OR_QUESTION",\n'
        '  "reasoning": "1 brief sentence explaining your financial/collections analysis of the client message (in the same language)",\n'
        '  "message": "Your natural, personalized reply to the client (2-3 sentences)",\n'
        '  "installments": 2,\n'
        '  "trigger_hitl": false,\n'
        '  "mark_paid": false,\n'
        '  "show_paypal_btn": true\n'
        "}"
    )
    user_prompt = f"Conversation history:\n{recent_context}\n\nClient's latest message: \"{text}\""

    if has_gemini:
        # Probar el modelo configurado y respaldos rápidos de la familia Gemini 3.x
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
                        "temperature": 0.35,
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
                "temperature": 0.35,
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
            print(f"[FacturaBot AI] Fallback a motor NLU local ({exc})")

    return None


def agent_reply(
    text: str,
    client: str = 'Cliente',
    amount: float = 0.0,
    lang: str | None = None,
    due_date: str = '',
    invoice_id: str = '',
    history: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Analiza el mensaje del cliente con Gemini 3.5 Flash y genera la respuesta y acciones de FacturaBot."""
    detected_lang = _detect_language(text, default_lang=lang or 'es')

    llm_res = _call_llm_agent(
        text,
        client=client,
        amount=amount,
        lang=detected_lang,
        due_date=due_date,
        invoice_id=invoice_id,
        history=history,
    )
    if llm_res and isinstance(llm_res, dict) and llm_res.get('message'):
        trigger_hitl = bool(llm_res.get('trigger_hitl'))
        mark_paid = bool(llm_res.get('mark_paid'))
        installments = max(2, int(llm_res.get('installments') or _extract_installments(text)))
        return {
            'message': str(llm_res['message']),
            'reasoning': str(llm_res.get('reasoning') or ''),
            'new_status': 'Paid' if mark_paid else None,
            'hitl_proposal': (
                {
                    'client': client,
                    'payments': installments,
                    'amount': amount,
                }
                if trigger_hitl
                else None
            ),
            'show_paypal_btn': bool(llm_res.get('show_paypal_btn', not trigger_hitl and not mark_paid)),
            'paypal_amount': 0.0 if mark_paid else amount,
            'intent': llm_res.get('intent', 'NEGOTIATION_OR_QUESTION'),
            'ai_provider': llm_res.get('_provider', get_active_ai_provider()),
        }

    # Motor NLU determinista bilingüe (ES / EN) sólo si no hay conexión a internet
    t = text.lower()
    is_en = detected_lang == 'en'

    plan_keywords = (
        'parte', 'parcial', 'plan', 'cuota', 'mitad', 'plazo',
        'no tengo el total', 'no cuento con el total', '2 pagos', 'dos pagos',
        'dividir', 'abono', 'abonar',
        'split', 'installment', 'partial', 'parts', 'half', 'two payments',
        "don't have the full", 'cannot pay the full', "can't pay all",
    )
    if any(k in t for k in plan_keywords):
        num_payments = _extract_installments(text)
        installment = (amount / num_payments) if amount else 0
        if is_en:
            monto_txt = f' (${installment:,.2f} USD per payment)' if installment else ''
            msg = (
                f'Understood, {client}. I have structured a {num_payments}-installment payment plan'
                f'{monto_txt} and escalated it to Human-In-The-Loop supervision to authorize '
                f'partial payments on your PayPal Invoice.'
            )
            reasoning = f'Client requested {num_payments} installments (${installment:,.2f}/each); escalating to HITL.'
        else:
            monto_txt = f' (${installment:,.2f} por pago)' if installment else ''
            msg = (
                f'Entendido, {client}. He generado una solicitud de plan de '
                f'{num_payments} pagos{monto_txt} y la envié a supervisión '
                f'(Human-In-The-Loop) para autorizarla en PayPal.'
            )
            reasoning = f'Cliente solicita diferir en {num_payments} pagos (${installment:,.2f} c/u); requiere autorización HITL.'
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
            'intent': 'INSTALLMENT_REQUEST',
            'ai_provider': get_active_ai_provider(),
        }

    paid_keywords = (
        'pagu', 'pagado', 'transfer', 'listo', 'comprobante', 'deposit', 'liquid',
        'i paid', 'already paid', 'just paid', 'payment sent', 'completed payment',
    )
    if any(k in t for k in paid_keywords):
        msg = (
            f'Thank you, {client}! We have verified and recorded your payment in PayPal Invoicing. '
            f'Your invoice status is now marked as Paid.'
            if is_en
            else f'¡Excelente, {client}! Hemos verificado y registrado su pago en PayPal. '
            f'Su factura ha quedado marcada como Pagada (Paid).'
        )
        return {
            'message': msg,
            'reasoning': 'Payment confirmation detected; updating ledger status to Paid.' if is_en else 'Confirmación de liquidación detectada; actualizando estado a Paid.',
            'new_status': 'Paid',
            'hitl_proposal': None,
            'show_paypal_btn': False,
            'paypal_amount': 0.0,
            'intent': 'PAYMENT_CONFIRMATION',
            'ai_provider': get_active_ai_provider(),
        }

    msg = (
        f'Thank you for reaching out, {client}. Would you like to settle the outstanding balance '
        f'(${amount:,.2f} USD) now with PayPal, or would you prefer to request a partial payment plan?'
        if is_en
        else f'Gracias por escribirnos, {client}. ¿Desea liquidar el saldo pendiente ahora '
        f'con PayPal o prefiere que evaluemos un plan de pagos en parcialidades?'
    )
    return {
        'message': msg,
        'reasoning': 'General inquiry; providing PayPal checkout and installment options.' if is_en else 'Consulta general de cobranza; ofreciendo enlace PayPal o convenio.',
        'new_status': None,
        'hitl_proposal': None,
        'show_paypal_btn': True,
        'paypal_amount': amount,
        'intent': 'GENERAL',
        'ai_provider': get_active_ai_provider(),
    }
