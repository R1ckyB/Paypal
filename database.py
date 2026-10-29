import os
from datetime import datetime, timezone
from dotenv import load_dotenv
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship

load_dotenv()

# Base de datos en SQLite (se guarda en paypal_agent.db) o definida en .env
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///paypal_agent.db")

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Tabla 1: Facturas
class Invoice(Base):
    __tablename__ = "invoices"

    id = Column(Integer, primary_key=True, index=True)
    paypal_invoice_id = Column(String, unique=True, index=True)
    client_email = Column(String, index=True)
    amount = Column(Float)
    currency = Column(String, default="USD")
    status = Column(String, default="SENT")  # SENT, OVERDUE, PAID, PARTIAL_PLAN, CANCELLED
    due_date = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Relacion con acuerdos de pago
    agrements = relationship("PaymentAgreement", back_populates="invoice")

# Tabla 2: Acuerdos de pago (Parcialidades)
class PaymentAgreement(Base):
    __tablename__ = "payment_agreements"
    id = Column(Integer, primary_key=True, index=True)
    invoice_id = Column(Integer, ForeignKey("invoices.id"))
    proposed_plan = Column(String)  # Ejem: "50% hoy, 50% en 30 días"
    status = Column(String, default="PENDING_HUMAN_APPROVAL")  # PENDING_HUMAN_APPROVAL, APPROVED, REJECTED
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    invoice = relationship("Invoice", back_populates="agrements")

def init_db():
    Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
