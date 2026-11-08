from nicegui import ui

from app.services.agent_service import agent_reply
from app.services.invoice_service import trigger_paypal_reminder, process_paypal_payment


class ClientInbox:
    """Bandeja del cliente (simulada) con burbujas estilo WhatsApp/Email y botón de pago PayPal."""

    def __init__(self, on_status_change=None, on_hitl_proposal=None, on_paypal_pay=None, lang: str = 'es'):
        self.on_status_change = on_status_change
        self.on_hitl_proposal = on_hitl_proposal
        self.on_paypal_pay = on_paypal_pay
        self.lang = lang

        self.current_client = 'Globex'
        self.current_amount = 8200.0
        self.current_invoice_id = 'INV-2026-001'
        self.current_due_date = '2026-09-15'
        self.view_mode = 'chat'  # 'chat' o 'email'

        # Historial por cliente (precargado para Globex exactamente como en el diseño)
        self.histories = {
            'Globex': [
                {
                    'sender': 'bot',
                    'text': 'Hola Globex, recordamos que tienes una factura pendiente. ¿Te gustaría acordar un plan de pagos?',
                    'show_paypal': True,
                    'paypal_label': '[ Pagar con PayPal ]',
                    'amount': 8200.0,
                },
                {
                    'sender': 'client',
                    'text': 'No tengo el total ahora, ¿puedo pagar en partes?',
                },
            ]
        }

        with ui.column().classes('w-full h-full justify-between no-wrap fb-inbox-panel') as self.panel:
            # Header de la bandeja
            with ui.row().classes('w-full items-center justify-between px-5 pt-4 pb-2 no-wrap'):
                with ui.row().classes('items-center gap-2 no-wrap'):
                    ui.html('<span style="font-size:18px;">📬</span>')
                    self.title_label = ui.label('Bandeja del cliente (simulada)').classes(
                        'text-white font-semibold text-base tracking-tight'
                    )
                self.mode_btn = ui.button(
                    'Vista de Email / WhatsApp',
                    on_click=self.toggle_view_mode,
                ).props('unelevated dense no-caps').classes('fb-view-toggle-btn')

            # Área de mensajes (scrollable)
            self.chat = ui.column().classes('w-full flex-grow overflow-auto px-6 py-4 gap-4')

            # Barra inferior de entrada
            with ui.row().classes('w-full items-center gap-3 px-4 py-3 no-wrap fb-inbox-footer'):
                self.box = (
                    ui.input(placeholder='Responder como cliente...')
                    .props('borderless dense dark')
                    .classes('flex-grow fb-chat-input')
                    .on('keydown.enter', self.reply)
                )
                self.send_btn = ui.button('ENVIAR', on_click=self.reply).props('unelevated no-caps').classes(
                    'fb-send-btn'
                )

        self._render_messages()

    def set_language(self, lang: str):
        self.lang = lang
        is_en = lang == 'en'
        self.title_label.text = 'Client Inbox (Simulated)' if is_en else 'Bandeja del cliente (simulada)'
        self.mode_btn.text = 'Email / WhatsApp View' if is_en else 'Vista de Email / WhatsApp'
        self.box.props(f'placeholder="{"Reply as client..." if is_en else "Responder como cliente..."}"')
        self.send_btn.text = 'SEND' if is_en else 'ENVIAR'
        self._render_messages()

    def toggle_view_mode(self):
        self.view_mode = 'email' if self.view_mode == 'chat' else 'chat'
        modo_str = 'Email (PayPal Invoice)' if self.view_mode == 'email' else 'Chat / WhatsApp'
        with self.panel:
            ui.notify(f'Vista: {modo_str} ({self.current_client})', color='primary')
        self._render_messages()

    def select_client(self, row: dict):
        """Cambia la conversación activa al cliente seleccionado en la tabla."""
        client = row['client']
        self.current_client = client
        self.current_amount = float(row.get('amount', 0))
        self.current_invoice_id = row.get('id', 'INV-2026-000')
        self.current_due_date = row.get('due_date', '')
        is_en = self.lang == 'en'
        pp_btn = '[ Pay with PayPal ]' if is_en else '[ Pagar con PayPal ]'

        if client not in self.histories:
            status = row.get('status', 'Pending')
            if status == 'Paid':
                self.histories[client] = [
                    {
                        'sender': 'bot',
                        'text': (
                            f'Hello {client}, we confirm that your invoice {self.current_invoice_id} for ${self.current_amount:,.2f} USD is Paid. Thank you!'
                            if is_en
                            else f'Hola {client}, confirmamos que tu factura {self.current_invoice_id} por ${self.current_amount:,.2f} se encuentra pagada. ¡Gracias!'
                        ),
                        'show_paypal': False,
                        'amount': 0.0,
                    }
                ]
            else:
                self.histories[client] = [
                    {
                        'sender': 'bot',
                        'text': (
                            f'Hello {client}, this is a reminder for your pending invoice ({self.current_invoice_id} for ${self.current_amount:,.2f} USD). Would you like to arrange an installment payment plan?'
                            if is_en
                            else f'Hola {client}, recordamos que tienes una factura pendiente ({self.current_invoice_id} por ${self.current_amount:,.2f}). ¿Te gustaría acordar un plan de pagos?'
                        ),
                        'show_paypal': True,
                        'paypal_label': pp_btn,
                        'amount': self.current_amount,
                    }
                ]
        self._render_messages()

    def send_reminder(self, client, amount, due_date, invoice_id=None):
        """El agente envía un recordatorio de cobro al cliente e invoca PayPal Invoicing v2 /remind."""
        self.current_client = client
        self.current_amount = float(amount)
        self.current_due_date = due_date
        if invoice_id:
            self.current_invoice_id = invoice_id

        # Invocar API de PayPal Invoicing v2 (/v2/invoicing/invoices/{id}/remind)
        pp_res = trigger_paypal_reminder(self.current_invoice_id or client)
        is_en = self.lang == 'en'
        pp_btn = '[ Pay with PayPal ]' if is_en else '[ Pagar con PayPal ]'

        history = self.histories.setdefault(client, [])
        history.append(
            {
                'sender': 'bot',
                'text': (
                    f'Hello {client}, PayPal Invoicing reminder for invoice {self.current_invoice_id} '
                    f'(${float(amount):,.2f} USD, due: {due_date}). Would you like to set up a payment plan?'
                    if is_en
                    else f'Hola {client}, recordamos que tienes una factura pendiente '
                    f'por ${float(amount):,.2f} (vencimiento: {due_date}). '
                    f'¿Te gustaría acordar un plan de pagos?'
                ),
                'show_paypal': True,
                'paypal_label': pp_btn,
                'amount': float(amount),
            }
        )
        with self.panel:
            endpoint_info = pp_res.get('mode', 'paypal_sandbox')
            ui.notify(
                f'PayPal Reminder sent to {client} ({endpoint_info})'
                if is_en
                else f'Recordatorio PayPal enviado a {client} ({endpoint_info})',
                type='positive',
            )
        self._render_messages()

    def notify_plan_approved(self, client: str, payments: int, total_amount: float, paypal_info: dict | None = None):
        """Notifica en el chat del cliente que su plan de pagos fue aprobado en PayPal."""
        self.current_client = client
        installment = total_amount / max(payments, 1)
        is_en = self.lang == 'en'
        pp_btn = f'[ Pay 1st Installment (${installment:,.2f}) with PayPal ]' if is_en else '[ Pagar con PayPal ]'
        history = self.histories.setdefault(client, [])
        history.append(
            {
                'sender': 'bot',
                'text': (
                    f'Great news, {client}! Your {payments}-installment payment plan of '
                    f'${installment:,.2f} USD per payment has been approved in PayPal Invoicing '
                    f'(allow_partial_payment=true). You can complete your payment below:'
                    if is_en
                    else f'¡Buenas noticias, {client}! Tu plan de {payments} pagos de '
                    f'${installment:,.2f} USD fue aprobado en PayPal. '
                    f'Puedes realizar tu pago a continuación:'
                ),
                'show_paypal': True,
                'paypal_label': pp_btn,
                'amount': total_amount,
            }
        )
        self._render_messages()

    def notify_plan_rejected(self, client: str, total_amount: float):
        """Notifica en el chat del cliente que su propuesta de plan fue rechazada."""
        self.current_client = client
        is_en = self.lang == 'en'
        pp_btn = '[ Pay with PayPal ]' if is_en else '[ Pagar con PayPal ]'
        history = self.histories.setdefault(client, [])
        history.append(
            {
                'sender': 'bot',
                'text': (
                    f'Hello {client}, due to credit policy we could not approve the installment plan '
                    f'at this time. Here is the direct PayPal link to settle the ${total_amount:,.2f} USD balance:'
                    if is_en
                    else f'Hola {client}, por políticas de crédito no fue posible aprobar el plan en parcialidades '
                    f'en este momento. Te compartimos el enlace para liquidar el saldo de ${total_amount:,.2f}:'
                ),
                'show_paypal': True,
                'paypal_label': pp_btn,
                'amount': total_amount,
            }
        )
        self._render_messages()

    def _handle_paypal_click(self, client: str, amount: float):
        """Procesa y registra el pago de la factura en PayPal Invoicing v2 (/payments)."""
        pp_res = process_paypal_payment(client, amount)
        payment_id = pp_res.get('payment_id', 'PAY-PP')
        is_en = self.lang == 'en'
        history = self.histories.setdefault(client, [])
        history.append(
            {
                'sender': 'client',
                'text': (
                    f'I have completed the ${amount:,.2f} USD payment via PayPal Checkout ({payment_id}).'
                    if is_en
                    else f'He completado el pago de ${amount:,.2f} vía PayPal Checkout ({payment_id}).'
                ),
            }
        )
        history.append(
            {
                'sender': 'bot',
                'text': (
                    f'✅ Payment of ${amount:,.2f} USD verified in PayPal Invoicing (Ref: {payment_id}). '
                    f'Invoice for {client} is now Paid. Thank you!'
                    if is_en
                    else f'✅ Pago recibido en PayPal por ${amount:,.2f} USD (Ref: {payment_id}). '
                    f'La factura de {client} ha sido actualizada a Paid. ¡Muchas gracias!'
                ),
                'show_paypal': False,
                'amount': 0.0,
            }
        )
        with self.panel:
            if self.on_paypal_pay:
                self.on_paypal_pay(client, amount)
            elif self.on_status_change:
                self.on_status_change(client, 'Paid')
        self._render_messages()

    def reply(self):
        text = (self.box.value or '').strip()
        if not text:
            return
        client = self.current_client or 'Globex'
        history = self.histories.setdefault(client, [])
        history.append({'sender': 'client', 'text': text})

        res = agent_reply(
            text,
            client=client,
            amount=self.current_amount,
            lang=self.lang,
            history=history,
        )
        is_en = self.lang == 'en'
        history.append(
            {
                'sender': 'bot',
                'text': res['message'],
                'show_paypal': res.get('show_paypal_btn', False),
                'paypal_label': '[ Pay with PayPal ]' if is_en else '[ Pagar con PayPal ]',
                'amount': res.get('paypal_amount', self.current_amount),
            }
        )
        self.box.value = ''

        with self.panel:
            if res.get('hitl_proposal') and self.on_hitl_proposal:
                self.on_hitl_proposal(res['hitl_proposal'])

            if res.get('new_status') and self.on_status_change:
                self.on_status_change(client, res['new_status'])

        self._render_messages()

    def _render_messages(self):
        self.chat.clear()
        history = self.histories.get(self.current_client, [])
        is_en = self.lang == 'en'

        with self.chat:
            if self.view_mode == 'email':
                # Vista previa de correo formal con plantilla de PayPal Invoicing
                with ui.column().classes('w-full fb-email-card p-4 gap-3'):
                    from_lbl = 'From' if is_en else 'De'
                    to_lbl = 'To' if is_en else 'Para'
                    subj_lbl = (
                        f'PayPal Invoice Notice {self.current_invoice_id} - Due {self.current_due_date}'
                        if is_en
                        else f'Aviso de Factura {self.current_invoice_id} - Vencimiento {self.current_due_date}'
                    )
                    ui.html(
                        f'<div style="border-bottom:1px solid #1E293B;padding-bottom:8px;">'
                        f'<div style="font-size:11px;color:#94A3B8;">{from_lbl}: <b>FacturaBot PayPal Invoicing &lt;cobranza@facturabot.ai&gt;</b></div>'
                        f'<div style="font-size:11px;color:#94A3B8;">{to_lbl}: <b>{self.current_client}</b></div>'
                        f'<div style="font-size:13px;color:#F8FAFC;font-weight:600;margin-top:4px;">'
                        f'{subj_lbl}</div>'
                        f'</div>'
                    )
                    for msg in history:
                        role_tag = 'FacturaBot' if msg['sender'] == 'bot' else self.current_client
                        ui.html(
                            f'<div style="font-size:13px;color:#E2E8F0;line-height:1.5;">'
                            f'<b style="color:#60A5FA;">{role_tag}:</b> {msg["text"]}</div>'
                        )
                        if msg.get('show_paypal'):
                            amt = float(msg.get('amount') or self.current_amount)
                            ui.button(
                                msg.get('paypal_label', '[ Pagar con PayPal ]'),
                                on_click=lambda _, c=self.current_client, a=amt: self._handle_paypal_click(c, a),
                            ).props('unelevated no-caps').classes('w-full fb-paypal-btn')
                return

            # Vista predeterminada (idéntica a la imagen de referencia)
            for msg in history:
                if msg['sender'] == 'bot':
                    with ui.row().classes('w-full items-end gap-2.5 no-wrap'):
                        ui.html('<div class="fb-bot-chat-icon">🤖</div>')
                        with ui.column().classes('fb-bot-bubble gap-3'):
                            ui.label(msg['text']).classes('text-slate-200 text-sm leading-relaxed')
                            if msg.get('show_paypal'):
                                amt = float(msg.get('amount') or self.current_amount)
                                ui.button(
                                    msg.get('paypal_label', '[ Pagar con PayPal ]'),
                                    on_click=lambda _, c=self.current_client, a=amt: self._handle_paypal_click(c, a),
                                ).props('unelevated no-caps').classes('w-full fb-paypal-btn')
                else:
                    with ui.row().classes('w-full justify-end no-wrap'):
                        with ui.column().classes('fb-client-bubble'):
                            ui.label(msg['text']).classes('text-slate-200 text-sm leading-relaxed')
