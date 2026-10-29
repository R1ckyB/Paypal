def agent_reply(text: str):
    """Respuesta simulada del agente.
    TODO: reemplazar por la llamada al backend/agente real.
    Regresa (mensaje, nuevo_estado o None)."""
    t = text.lower()
    if 'pagu' in t or 'transfer' in t or 'listo' in t:
        return 'Gracias, registré su pago. ¡Factura marcada como pagada!', 'Paid'
    if 'mañana' in t or 'semana' in t or 'viernes' in t:
        return 'Perfecto, registré su promesa de pago. Le enviaré un recordatorio.', None
    return 'Gracias por su respuesta. ¿Me confirma cuándo realizará el pago?', None
