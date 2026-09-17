from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional, List
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator, model_validator, ConfigDict


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
    supplier: str = Field(..., min_length=2, max_length=200, description="Supplier company name")
    budget_limit: float = Field(..., gt=0, le=1_000_000, description="Maximum budget limit in TL")
    anomaly_threshold: Optional[float] = Field(None, gt=0, le=10_000_000, description="Anomaly detection threshold")
    product_hint: Optional[str] = Field(None, max_length=100, description="Product category hint")
    raw_text: Optional[str] = Field(None, max_length=500, description="Original natural language rule text")

    @model_validator(mode='after')
    def validate_threshold(self) -> 'RuleCreate':
        if self.anomaly_threshold is None:
            object.__setattr__(self, 'anomaly_threshold', self.budget_limit * 2)
        elif self.anomaly_threshold < self.budget_limit:
            raise ValueError("anomaly_threshold must be greater than or equal to budget_limit")
        return self


class Rule(BaseModel):
    id: str = Field(default_factory=new_id)
    supplier: str
    budget_limit: float
    anomaly_threshold: float
    product_hint: Optional[str] = None
    raw_text: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class InvoiceCreate(BaseModel):
    supplier: str = Field(..., min_length=2, max_length=200, description="Supplier company name")
    product: str = Field(default="bardak", min_length=1, max_length=100, description="Product name")
    quantity: int = Field(default=500, gt=0, le=100_000, description="Product quantity")
    amount: float = Field(..., gt=0, le=10_000_000, description="Invoice amount in TL")
    force_anomaly: bool = Field(default=False, description="Force anomaly detection for demo purposes")
    lang: Optional[str] = Field(None, description="UI language selection, only passed to agent prompts")

    @field_validator('supplier')
    @classmethod
    def validate_supplier(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("supplier cannot be empty or whitespace")
        return v.strip()


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
    amount: float = Field(..., gt=0, le=1_000_000, description="Withdrawal amount")
    iban: str = Field(default="TR00 0000 0000 0000 0000 0000 00", min_length=15, max_length=34, description="IBAN for withdrawal")
    asset: str = Field(default="USDC", pattern=r'^[A-Z]{3,12}$', description="Asset code")
    sep10_token: Optional[str] = Field(None, max_length=500, description="SEP-10 authentication token")
    account: Optional[str] = Field(None, min_length=56, max_length=56, description="Stellar public key")

    @field_validator('iban')
    @classmethod
    def validate_iban(cls, v: str) -> str:
        cleaned = v.replace(' ', '').upper()
        if not cleaned.startswith('TR') or len(cleaned) != 26:
            raise ValueError("Invalid Turkish IBAN format")
        return cleaned


class ReturnCreate(BaseModel):
    text: str = Field(..., min_length=5, max_length=1000, description="Return request text")
    lang: str = Field(default="tr", pattern=r'^(tr|en)$', description="Language code (tr or en)")

    @field_validator('text')
    @classmethod
    def validate_text(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("text cannot be empty or whitespace")
        return v.strip()


class AgentLog(BaseModel):
    id: str = Field(default_factory=new_id)
    level: str = "info"  # info | warn | success | error | buyer | seller
    source: str = "system"
    message: str
    negotiation_id: Optional[str] = None
    ts: datetime = Field(default_factory=datetime.utcnow)


# ==================== CONTEXT-BASED REQUEST MODELS ====================

class PastInvoice(BaseModel):
    """Historical invoice data for RAG context"""
    supplier: str = Field(..., min_length=2, max_length=200)
    product: str = Field(..., min_length=1, max_length=100)
    amount: float = Field(..., gt=0, le=10_000_000)
    date: str = Field(..., min_length=8, max_length=50, description="Date in any format")


class NegotiationContext(BaseModel):
    """Context data for stateless negotiation"""
    past_invoices: List[PastInvoice] = Field(default_factory=list, description="Historical invoice data")
    rules: List[Rule] = Field(default_factory=list, description="Applicable business rules")
    wallet_public_key: Optional[str] = Field(None, min_length=56, max_length=56, description="Stellar wallet public key")


class StatelessInvoiceRequest(BaseModel):
    """Stateless invoice submission with context"""
    invoice: InvoiceCreate
    context: NegotiationContext
    lang: str = Field(default="tr", pattern=r'^(tr|en)$')


class StatelessReturnRequest(BaseModel):
    """Stateless return request with context"""
    return_request: ReturnCreate
    context: NegotiationContext


# ==================== ERROR RESPONSE MODELS ====================

class ErrorDetail(BaseModel):
    field: Optional[str] = None
    message: str
    code: str


class ErrorResponse(BaseModel):
    success: bool = False
    error: str
    error_code: str
    details: Optional[List[ErrorDetail]] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)


# ==================== EXISTING MODELS (UPDATED) ====================

class BalanceResponse(BaseModel):
    public_key: Optional[str] = Field(None, min_length=56, max_length=56)
    xlm: float = Field(default=0.0, ge=0)
    usdc: float = Field(default=0.0, ge=0)
    mock_try: float = Field(default=0.0, ge=0)
    network: str = Field(default="testnet", pattern=r'^(testnet|public|mainnet)$')
