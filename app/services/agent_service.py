def agent_reply(text: str, client: str = 'Cliente', amount: float = 0.0):
    """Analiza el mensaje del cliente y genera la respuesta de FacturaBot.

    Regresa un diccionario con:
      - message: texto de respuesta del bot
      - new_status: nuevo estado de la factura ('Paid', 'Partial Plan', None)
      - hitl_proposal: dict con propuesta para Human-In-The-Loop o None
      - show_paypal_btn: bool indicando si mostrar el botón [ Pagar con PayPal ]
      - paypal_amount: monto sugerido para el botón de PayPal
    """
    t = text.lower()

    # 1. Solicitud de pago en partes / plan de pagos -> Activa Human-In-The-Loop
    plan_keywords = (
        'parte', 'parcial', 'plan', 'cuota', 'mitad', 'plazo',
        'no tengo el total', 'no cuento con el total', '2 pagos', 'dos pagos',
        'dividir', 'abono', 'abonar',
    )
    if any(k in t for k in plan_keywords):
        num_payments = 3 if ('3' in t or 'tres' in t) else 2
        installment = (amount / num_payments) if amount else 0
        monto_txt = f' (${installment:,.2f} por pago)' if installment else ''
        return {
            'message': (
                f'Entendido, {client}. He generado una solicitud de plan de '
                f'{num_payments} pagos{monto_txt} y la envié a supervisión '
                f'(Human-In-The-Loop) para autorizarla en PayPal.'
            ),
            'new_status': None,
            'hitl_proposal': {
                'client': client,
                'payments': num_payments,
                'amount': amount,
            },
            'show_paypal_btn': False,
            'paypal_amount': amount,
        }

    # 2. Confirmación de pago realizado
    paid_keywords = ('pagu', 'pagado', 'transfer', 'listo', 'comprobante', 'deposit', 'liquid')
    if any(k in t for k in paid_keywords):
        return {
            'message': (
                f'¡Excelente, {client}! Hemos verificado y registrado su pago en PayPal. '
                f'Su factura ha quedado marcada como Pagada (Paid).'
            ),
            'new_status': 'Paid',
            'hitl_proposal': None,
            'show_paypal_btn': False,
            'paypal_amount': 0.0,
        }

    # 3. Promesa de pago en fecha próxima
    promise_keywords = ('mañana', 'semana', 'viernes', 'lunes', 'martes', 'jueves', 'quincena', 'fin de mes', 'día')
    if any(k in t for k in promise_keywords):
        return {
            'message': (
                f'Perfecto, {client}. Registré su compromiso de pago en el sistema. '
                f'Le comparto el enlace directo de PayPal para cuando realice la transacción:'
            ),
            'new_status': None,
            'hitl_proposal': None,
            'show_paypal_btn': True,
            'paypal_amount': amount,
        }

    # 4. Consulta de saldo, factura o link de pago
    info_keywords = ('cuánto', 'cuanto', 'monto', 'saldo', 'link', 'liga', 'paypal', 'factura', 'debo')
    if any(k in t for k in info_keywords):
        monto_str = f'${amount:,.2f}' if amount else 'pendiente'
        return {
            'message': (
                f'Hola {client}, el saldo actual de su factura es de {monto_str}. '
                f'Puede liquidarla directamente con PayPal o solicitar un plan de pagos:'
            ),
            'new_status': None,
            'hitl_proposal': None,
            'show_paypal_btn': True,
            'paypal_amount': amount,
        }

    # 5. Respuesta por defecto con opción de pago o convenio
    return {
        'message': (
            f'Gracias por escribirnos, {client}. ¿Desea liquidar el saldo pendiente ahora '
            f'con PayPal o prefiere que evaluemos un plan de pagos en parcialidades?'
        ),
        'new_status': None,
        'hitl_proposal': None,
        'show_paypal_btn': True,
        'paypal_amount': amount,
    }
