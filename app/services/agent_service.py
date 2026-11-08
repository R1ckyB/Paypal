"""Servicio de Agente de IA para Cobranza B2B con PayPal Invoicing y Human-In-The-Loop.

Soporta:
1. Google Gemini API (Structured JSON Output) si GEMINI_API_KEY está configurada.
2. OpenAI / Compatible API (Structured JSON Output) si OPENAI_API_KEY está configurada.
3. Motor NLU determinista bilingüe (ES/EN) como fallback instantáneo sin latencia.
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
        'tomorrow', 'friday', 'monday', 'please', 'help', 'total now',
    )
    es_markers = (
        'parte', 'parcial', 'cuota', 'pagu', 'pagado', 'cuánto', 'cuanto',
        'mañana', 'semana', 'factura', 'puedo', 'tengo', 'abono', 'mitad',
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
    match = re.search(r'\b([2-6])\s*(?:pagos?|partes?|cuotas?|payments?|installments?|parts?)\b', t)
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
    history: list[dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    """Invoca a Gemini u OpenAI para analizar la intención del cliente y generar la acción de cobranza."""
    has_gemini = bool(GEMINI_API_KEY and GEMINI_API_KEY not in PLACEHOLDER_KEYS)
    has_openai = bool(OPENAI_API_KEY and OPENAI_API_KEY not in PLACEHOLDER_KEYS)
    if not has_gemini and not has_openai:
        return None

    lang_name = 'English' if lang == 'en' else 'Spanish'
    recent_context = ''
    if history:
        turns = history[-4:]
        recent_context = '\n'.join(f"- {m.get('sender', 'user')}: {m.get('text', '')}" for m in turns)

    system_prompt = (
        "You are FacturaBot, an autonomous AI Accounts Receivable & Collections Agent integrated with "
        "PayPal Invoicing v2 API and a Human-In-The-Loop (HITL) credit approval workflow.\n"
        f"Client Name: {client}\n"
        f"Invoice Outstanding Balance: ${amount:,.2f} USD\n"
        f"Respond in {lang_name}.\n\n"
        "Classify the client's message and return ONLY a valid JSON object with these exact keys:\n"
        "- \"intent\": one of [\"INSTALLMENT_REQUEST\", \"PAYMENT_CONFIRMATION\", \"PROMISE_TO_PAY\", \"BALANCE_INQUIRY\", \"GENERAL\"]\n"
        "- \"message\": concise, professional, empathetic reply to the client (2-3 sentences max).\n"
        "- \"installments\": integer between 2 and 6 if intent is INSTALLMENT_REQUEST, else 0.\n"
        "- \"trigger_hitl\": boolean (true ONLY if the client asks to split/pay in parts/installments).\n"
        "- \"mark_paid\": boolean (true ONLY if the client confirms they already completed full payment).\n"
        "- \"show_paypal_btn\": boolean (true if the client should see the PayPal checkout button right now; false if waiting for HITL approval or already paid).\n"
    )
    user_prompt = f"Recent conversation:\n{recent_context}\n\nClient new message: \"{text}\""

    try:
        if has_gemini:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"
            payload = {
                "systemInstruction": {"parts": [{"text": system_prompt}]},
                "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
                "generationConfig": {
                    "temperature": 0.2,
                    "responseMimeType": "application/json",
                },
            }
            resp = requests.post(url, json=payload, timeout=10)
            resp.raise_for_status()
            raw_text = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
            parsed = json.loads(raw_text)
            parsed["_provider"] = f"gemini:{GEMINI_MODEL}"
            return parsed

        if has_openai:
            url = f"{OPENAI_BASE_URL.rstrip('/')}/chat/completions"
            headers = {
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "Content-Type": "application/json",
            }
            payload = {
                "model": OPENAI_MODEL,
                "temperature": 0.2,
                "response_format": {"type": "json_object"},
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            }
            resp = requests.post(url, headers=headers, json=payload, timeout=10)
            resp.raise_for_status()
            raw_text = resp.json()["choices"][0]["message"]["content"]
            parsed = json.loads(raw_text)
            parsed["_provider"] = f"openai:{OPENAI_MODEL}"
            return parsed
    except Exception as exc:
        print(f"[FacturaBot AI] Fallback a motor NLU local ({exc})")
        return None
    return None


def agent_reply(
    text: str,
    client: str = 'Cliente',
    amount: float = 0.0,
    lang: str | None = None,
    history: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Analiza el mensaje del cliente y genera la respuesta de FacturaBot.

    Regresa un diccionario con:
      - message: texto de respuesta del bot
      - new_status: nuevo estado de la factura ('Paid', 'Partial Plan', None)
      - hitl_proposal: dict con propuesta para Human-In-The-Loop o None
      - show_paypal_btn: bool indicando si mostrar el botón [ Pagar con PayPal ]
      - paypal_amount: monto sugerido para el botón de PayPal
      - intent: intención detectada
      - ai_provider: motor de IA utilizado
    """
    detected_lang = _detect_language(text, default_lang=lang or 'es')

    # Intentar primero con LLM real (Gemini / OpenAI) si hay API key configurada
    llm_res = _call_llm_agent(text, client=client, amount=amount, lang=detected_lang, history=history)
    if llm_res and isinstance(llm_res, dict) and llm_res.get('message'):
        trigger_hitl = bool(llm_res.get('trigger_hitl'))
        mark_paid = bool(llm_res.get('mark_paid'))
        installments = max(2, int(llm_res.get('installments') or _extract_installments(text)))
        return {
            'message': str(llm_res['message']),
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
            'intent': llm_res.get('intent', 'GENERAL'),
            'ai_provider': llm_res.get('_provider', get_active_ai_provider()),
        }

    # Motor NLU determinista bilingüe (ES / EN)
    t = text.lower()
    is_en = detected_lang == 'en'

    # 1. Solicitud de pago en partes / plan de pagos -> Activa Human-In-The-Loop
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
        else:
            monto_txt = f' (${installment:,.2f} por pago)' if installment else ''
            msg = (
                f'Entendido, {client}. He generado una solicitud de plan de '
                f'{num_payments} pagos{monto_txt} y la envié a supervisión '
                f'(Human-In-The-Loop) para autorizarla en PayPal.'
            )
        return {
            'message': msg,
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

    # 2. Confirmación de pago realizado
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
            'new_status': 'Paid',
            'hitl_proposal': None,
            'show_paypal_btn': False,
            'paypal_amount': 0.0,
            'intent': 'PAYMENT_CONFIRMATION',
            'ai_provider': get_active_ai_provider(),
        }

    # 3. Promesa de pago en fecha próxima
    promise_keywords = (
        'mañana', 'semana', 'viernes', 'lunes', 'martes', 'jueves', 'quincena', 'fin de mes', 'día',
        'tomorrow', 'next week', 'friday', 'monday', 'tuesday', 'thursday', 'end of month',
    )
    if any(k in t for k in promise_keywords):
        msg = (
            f'Perfect, {client}. I have logged your payment commitment in the system. '
            f'Here is your direct PayPal Invoicing checkout link for when you complete the transaction:'
            if is_en
            else f'Perfecto, {client}. Registré su compromiso de pago en el sistema. '
            f'Le comparto el enlace directo de PayPal para cuando realice la transacción:'
        )
        return {
            'message': msg,
            'new_status': None,
            'hitl_proposal': None,
            'show_paypal_btn': True,
            'paypal_amount': amount,
            'intent': 'PROMISE_TO_PAY',
            'ai_provider': get_active_ai_provider(),
        }

    # 4. Consulta de saldo, factura o link de pago
    info_keywords = (
        'cuánto', 'cuanto', 'monto', 'saldo', 'link', 'liga', 'paypal', 'factura', 'debo',
        'how much', 'balance', 'amount', 'invoice', 'owe', 'checkout',
    )
    if any(k in t for k in info_keywords):
        monto_str = f'${amount:,.2f} USD' if amount else ('pending' if is_en else 'pendiente')
        msg = (
            f'Hello {client}, your current invoice balance is {monto_str}. '
            f'You can pay it in full right away via PayPal or request an installment payment plan:'
            if is_en
            else f'Hola {client}, el saldo actual de su factura es de {monto_str}. '
            f'Puede liquidarla directamente con PayPal o solicitar un plan de pagos:'
        )
        return {
            'message': msg,
            'new_status': None,
            'hitl_proposal': None,
            'show_paypal_btn': True,
            'paypal_amount': amount,
            'intent': 'BALANCE_INQUIRY',
            'ai_provider': get_active_ai_provider(),
        }

    # 5. Respuesta por defecto con opción de pago o convenio
    msg = (
        f'Thank you for reaching out, {client}. Would you like to settle the outstanding balance '
        f'(${amount:,.2f} USD) now with PayPal, or would you prefer to request a partial payment plan?'
        if is_en
        else f'Gracias por escribirnos, {client}. ¿Desea liquidar el saldo pendiente ahora '
        f'con PayPal o prefiere que evaluemos un plan de pagos en parcialidades?'
    )
    return {
        'message': msg,
        'new_status': None,
        'hitl_proposal': None,
        'show_paypal_btn': True,
        'paypal_amount': amount,
        'intent': 'GENERAL',
        'ai_provider': get_active_ai_provider(),
    }
