# librerias
"""Herramienta nativa de python pra interactuar con el SO"""
import os
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
Base_URL = "https://api-m.sandbox.paypal.com"