from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import uuid4

from pydantic import BaseModel, Field


def new_id() -> str:
    return str(uuid4())


class Decision(str, Enum):
    ACCEPT = "ACCEPT"
    COUNTER_OFFER = "COUNTER_OFFER"
    ANOMALY = "ANOMALY"
    REJECT = "REJECT"


class NegotiationStatus(str, Enum):
    PENDING = "pending"
    NEGOTIATING = "negotiating"
    AGREED = "agreed"
    FAILED = "failed"
    ANOMALY = "anomaly"
    AWAITING_APPROVAL = "awaiting_approval"
    PENDING_MULTISIG = "pending_multisig"
    PAID = "paid"
    REJECTED = "rejected"


class RuleCreate(BaseModel):
    supplier: str
    budget_limit: float
    anomaly_threshold: Optional[float] = None
    product_hint: Optional[str] = None
    raw_text: Optional[str] = None


class Rule(BaseModel):
    id: str = Field(default_factory=new_id)
    supplier: str
    budget_limit: float
    anomaly_threshold: float
    product_hint: Optional[str] = None
    raw_text: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class InvoiceCreate(BaseModel):
    supplier: str
    product: str = "bardak"
    quantity: int = 500
    amount: float
    force_anomaly: bool = False


class Invoice(BaseModel):
    id: str = Field(default_factory=new_id)
    supplier: str
    product: str
    quantity: int
    amount: float
    force_anomaly: bool = False
    created_at: datetime = Field(default_factory=datetime.utcnow)


class OfferMessage(BaseModel):
    role: str  # buyer | seller
    amount: float
    text: str
    round: int
    ts: datetime = Field(default_factory=datetime.utcnow)


class Negotiation(BaseModel):
    id: str = Field(default_factory=new_id)
    invoice_id: str
    supplier: str
    product: str
    quantity: int
    initial_amount: float
    current_amount: float
    agreed_amount: Optional[float] = None
    status: NegotiationStatus = NegotiationStatus.PENDING
    round: int = 0
    max_rounds: int = 3
    messages: list[OfferMessage] = Field(default_factory=list)
    anomaly_reason: Optional[str] = None
    payment_tx: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class AnomalyAction(BaseModel):
    negotiation_id: str
    approved: bool = True


class PaymentSession(BaseModel):
    id: str = Field(default_factory=new_id)
    negotiation_id: str
    deposit_tx: Optional[str] = None
    settlement_tx: Optional[str] = None
    amount: float
    asset: str = "USDC"
    status: str = "open"
    created_at: datetime = Field(default_factory=datetime.utcnow)


class TransactionRecord(BaseModel):
    id: str = Field(default_factory=new_id)
    negotiation_id: str
    supplier: str
    amount: float
    asset: str = "USDC"
    tx_hash: Optional[str] = None
    status: str = "completed"
    created_at: datetime = Field(default_factory=datetime.utcnow)


class WithdrawRequest(BaseModel):
    amount: float
    iban: str = "TR00 0000 0000 0000 0000 0000 00"
    asset: str = "USDC"
    sep10_token: Optional[str] = None
    account: Optional[str] = None


class ReturnCreate(BaseModel):
    text: str = "Siyah Deri Ceket, 5000 TL"
    lang: str = "tr"


class AgentLog(BaseModel):
    id: str = Field(default_factory=new_id)
    level: str = "info"  # info | warn | success | error | buyer | seller
    source: str = "system"
    message: str
    negotiation_id: Optional[str] = None
    ts: datetime = Field(default_factory=datetime.utcnow)


class BalanceResponse(BaseModel):
    public_key: Optional[str] = None
    xlm: float = 0.0
    usdc: float = 0.0
    mock_try: float = 0.0
    network: str = "testnet"
