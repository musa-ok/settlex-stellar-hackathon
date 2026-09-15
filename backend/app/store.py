from __future__ import annotations

import asyncio
from typing import Optional

from .models import (
    AgentLog,
    Invoice,
    Negotiation,
    PaymentSession,
    Rule,
    TransactionRecord,
)


class InMemoryStore:
    """Hackathon-friendly in-memory store (swap for SQLite later)."""

    def __init__(self) -> None:
        self.rules: dict[str, Rule] = {}
        self.invoices: dict[str, Invoice] = {}
        self.negotiations: dict[str, Negotiation] = {}
        self.sessions: dict[str, PaymentSession] = {}
        self.transactions: list[TransactionRecord] = []
        self.logs: list[AgentLog] = []
        self.wallet_public_key: Optional[str] = None
        self.mock_balances = {"xlm": 10_000.0, "usdc": 2_500.0, "mock_try": 0.0}
        self._lock = asyncio.Lock()

    def seed_defaults(self) -> None:
        if self.rules:
            return
        defaults = [
            Rule(
                supplier="Kağıt Tedarik A.Ş.",
                budget_limit=450.0,
                anomaly_threshold=900.0,
                product_hint="bardak",
                raw_text="Kağıt Tedarik A.Ş.'den bardak alımlarında bütçe max 450 TL, otomatik öde.",
            ),
            Rule(
                supplier="OfisMarket Ltd.",
                budget_limit=300.0,
                anomaly_threshold=600.0,
                product_hint="kalem",
                raw_text="OfisMarket Ltd. için max 300 TL.",
            ),
        ]
        for rule in defaults:
            self.rules[rule.id] = rule


store = InMemoryStore()
store.seed_defaults()
