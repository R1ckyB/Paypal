import json
import os
from datetime import datetime, timezone
from pathlib import Path
from dotenv import load_dotenv
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, ForeignKey, inspect, text
from sqlalchemy.orm import declarative_base, sessionmaker, relationship

load_dotenv()

# Base de datos en SQLite (se guarda en paypal_agent.db) o definida en .env
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///paypal_agent.db")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


# Tabla 1: Facturas
class Invoice(Base):
    __tablename__ = "invoices"

    id = Column(Integer, primary_key=True, index=True)
    paypal_invoice_id = Column(String, unique=True, index=True)
    client_name = Column(String, index=True)
    client_email = Column(String, index=True)
    amount = Column(Float)
    currency = Column(String, default="USD")
    status = Column(String, default="Pending")  # Pending, Overdue, Paid, Partial Plan, Cancelled
    due_date = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Relación con acuerdos de pago
    agreements = relationship("PaymentAgreement", back_populates="invoice", cascade="all, delete-orphan")

    @property
    def agrements(self):
        return self.agreements


# Tabla 2: Acuerdos de pago (Parcialidades)
class PaymentAgreement(Base):
    __tablename__ = "payment_agreements"

    id = Column(Integer, primary_key=True, index=True)
    invoice_id = Column(Integer, ForeignKey("invoices.id"))
    proposed_plan = Column(String)  # Ejem: "2 pagos de $4,100.00 USD"
    status = Column(String, default="PENDING_HUMAN_APPROVAL")  # PENDING_HUMAN_APPROVAL, APPROVED, REJECTED
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    invoice = relationship("Invoice", back_populates="agreements")


def _ensure_schema_and_seed():
    """Asegura que las columnas nuevas existan y puebla datos iniciales si la BD está vacía."""
    inspector = inspect(engine)
    if "invoices" in inspector.get_table_names():
        columns = [col["name"] for col in inspector.get_columns("invoices")]
        if "client_name" not in columns:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE invoices ADD COLUMN client_name VARCHAR"))

    db = SessionLocal()
    try:
        if db.query(Invoice).count() == 0:
            invoices_path = Path(__file__).resolve().parent / "data" / "invoices.json"
            if invoices_path.exists():
                with open(invoices_path, encoding="utf-8") as f:
                    seed_data = json.load(f)
            else:
                seed_data = [
                    {"id": "INV-2026-001", "client": "Globex", "amount": 8200.0, "due_date": "2026-09-15", "status": "Overdue"},
                    {"id": "INV-2026-002", "client": "Stark Industries", "amount": 22000.0, "due_date": "2026-09-28", "status": "Overdue"},
                    {"id": "INV-2026-003", "client": "Initech", "amount": 3400.0, "due_date": "2026-10-01", "status": "Paid"},
                    {"id": "INV-2026-004", "client": "Acme Corp", "amount": 12500.0, "due_date": "2026-10-30", "status": "Pending"},
                    {"id": "INV-2026-005", "client": "Umbrella SA", "amount": 15900.0, "due_date": "2026-11-12", "status": "Pending"},
                ]

            for idx, item in enumerate(seed_data, start=1):
                inv_id = item.get("id", f"INV-2026-{idx:03d}")
                client = item.get("client", f"Cliente {idx}")
                slug = client.lower().replace(" ", "")
                email = item.get("client_email", f"pagos@{slug}.com")
                due_str = item.get("due_date", "2026-10-30")
                try:
                    due_dt = datetime.strptime(due_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
                except ValueError:
                    due_dt = datetime.now(timezone.utc)

                inv_obj = Invoice(
                    paypal_invoice_id=inv_id,
                    client_name=client,
                    client_email=email,
                    amount=float(item.get("amount", 0.0)),
                    currency="USD",
                    status=item.get("status", "Pending"),
                    due_date=due_dt,
                )
                db.add(inv_obj)
                db.flush()

                # Sembrar acuerdo inicial pendiente para Globex
                if client == "Globex":
                    db.add(
                        PaymentAgreement(
                            invoice_id=inv_obj.id,
                            proposed_plan="Plan de 2 pagos ($4,100.00 USD c/u)",
                            status="PENDING_HUMAN_APPROVAL",
                        )
                    )
            db.commit()
    finally:
        db.close()


def init_db():
    Base.metadata.create_all(bind=engine)
    _ensure_schema_and_seed()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
