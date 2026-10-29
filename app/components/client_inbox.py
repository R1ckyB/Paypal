from nicegui import ui

from app.services.agent_service import agent_reply


class ClientInbox:
    def __init__(self, on_status_change=None):
        self.on_status_change = on_status_change
        self.current_client = None

        with ui.column().classes('w-full h-full p-3 gap-2'):
            ui.label('📬 Bandeja del cliente (simulada)').classes('text-lg font-semibold')
            self.chat = ui.column().classes('w-full gap-2 flex-grow overflow-auto')
            with ui.row().classes('w-full items-center no-wrap'):
                self.box = ui.input(placeholder='Responder como cliente...') \
                    .classes('flex-grow').on('keydown.enter', self.reply)
                ui.button('Enviar', on_click=self.reply)

    def send_reminder(self, client, amount, due_date):
        """El agente envía un recordatorio de cobro al cliente."""
        self.current_client = client
        with self.chat:
            ui.chat_message(
                f'Hola {client}, le recordamos que la factura por ${amount:,} '
                f'venció el {due_date}. ¿Podría confirmarnos la fecha de pago?',
                name='FacturaBot', stamp='ahora')

    def reply(self):
        text = (self.box.value or '').strip()
        if not text:
            return
        with self.chat:
            ui.chat_message(text, name='Cliente', sent=True)
            msg, new_status = agent_reply(text)
            ui.chat_message(msg, name='FacturaBot')
        self.box.value = ''
        if new_status and self.current_client and self.on_status_change:
            self.on_status_change(self.current_client, new_status)
