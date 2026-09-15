from __future__ import annotations

import asyncio
from typing import Optional

from stellar_sdk import Keypair, Network, Server
from stellar_sdk.exceptions import NotFoundError

from .models import AgentLog, BalanceResponse, PaymentSession, TransactionRecord
from .store import store
from .websocket_manager import ws_manager

HORIZON_URL = "https://horizon-testnet.stellar.org"
NETWORK_PASSPHRASE = Network.TESTNET_NETWORK_PASSPHRASE
FRIENDBOT_URL = "https://friendbot.stellar.org"


class StellarService:
    """Stellar testnet helpers. Falls back to mock hashes when keys are absent."""

    def __init__(self) -> None:
        self.server = Server(horizon_url=HORIZON_URL)
        self._demo_keypair: Optional[Keypair] = None

    def ensure_demo_keypair(self) -> Keypair:
        if self._demo_keypair is None:
            self._demo_keypair = Keypair.random()
        return self._demo_keypair

    async def fund_account(self, public_key: Optional[str] = None) -> dict:
        import httpx

        kp = self.ensure_demo_keypair() if not public_key else None
        pk = public_key or kp.public_key
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(FRIENDBOT_URL, params={"addr": pk})
            ok = resp.status_code in (200, 201)
        store.wallet_public_key = pk
        store.mock_balances["xlm"] = max(store.mock_balances["xlm"], 10_000.0)
        await self.emit_log(
            "success",
            "stellar",
            f"Friendbot ile fonlandı: {pk[:8]}…{pk[-4:]}",
        )
        return {"public_key": pk, "funded": ok, "secret_hint": "demo-only" if kp else None}

    async def get_balance(self, public_key: Optional[str] = None) -> BalanceResponse:
        pk = public_key or store.wallet_public_key
        if not pk:
            return BalanceResponse(
                public_key=None,
                xlm=store.mock_balances["xlm"],
                usdc=store.mock_balances["usdc"],
                mock_try=store.mock_balances["mock_try"],
            )
        try:
            account = self.server.accounts().account_id(pk).call()
            xlm = 0.0
            usdc = 0.0
            for bal in account.get("balances", []):
                if bal.get("asset_type") == "native":
                    xlm = float(bal["balance"])
                elif bal.get("asset_code") == "USDC":
                    usdc = float(bal["balance"])
            store.mock_balances["xlm"] = xlm
            if usdc:
                store.mock_balances["usdc"] = usdc
            return BalanceResponse(
                public_key=pk,
                xlm=xlm,
                usdc=store.mock_balances["usdc"],
                mock_try=store.mock_balances["mock_try"],
            )
        except NotFoundError:
            return BalanceResponse(
                public_key=pk,
                xlm=store.mock_balances["xlm"],
                usdc=store.mock_balances["usdc"],
                mock_try=store.mock_balances["mock_try"],
            )
        except Exception:
            return BalanceResponse(
                public_key=pk,
                xlm=store.mock_balances["xlm"],
                usdc=store.mock_balances["usdc"],
                mock_try=store.mock_balances["mock_try"],
            )

    async def start_mpp_session(self, negotiation_id: str, amount: float) -> PaymentSession:
        # One deposit, many off-chain signed rounds, one settlement (MPP Session mode)
        mock_deposit = f"mock-deposit-{negotiation_id[:8]}"
        session = PaymentSession(
            negotiation_id=negotiation_id,
            amount=amount,
            deposit_tx=mock_deposit,
            status="deposited",
        )
        store.sessions[session.id] = session
        await self.emit_log(
            "info",
            "mpp",
            f"MPP Session açıldı — deposit {amount:.2f} USDC ({mock_deposit})",
            negotiation_id,
        )
        await self.emit_log(
            "info",
            "mpp",
            "Off-chain imzalı turlar ağa yazılmıyor; sadece final settlement yazılacak.",
            negotiation_id,
        )
        return session

    async def execute_settlement(self, negotiation_id: str, amount: float, supplier: str) -> TransactionRecord:
        session = next(
            (s for s in store.sessions.values() if s.negotiation_id == negotiation_id),
            None,
        )
        # Simulate network latency for live console drama
        await asyncio.sleep(0.6)
        tx_hash = f"stellar-tx-{negotiation_id[:8]}-{int(amount * 100)}"
        if session:
            session.settlement_tx = tx_hash
            session.status = "settled"
            session.amount = amount

        store.mock_balances["usdc"] = max(0.0, store.mock_balances["usdc"] - amount)
        store.mock_balances["mock_try"] += amount  # supplier side credit for withdraw demo

        record = TransactionRecord(
            negotiation_id=negotiation_id,
            supplier=supplier,
            amount=amount,
            tx_hash=tx_hash,
            status="completed",
        )
        store.transactions.insert(0, record)
        await self.emit_log(
            "success",
            "stellar",
            f"Settlement onaylandı — {amount:.2f} USDC → {supplier} | tx: {tx_hash}",
            negotiation_id,
        )
        return record

    async def emit_log(
        self,
        level: str,
        source: str,
        message: str,
        negotiation_id: Optional[str] = None,
    ) -> AgentLog:
        log = AgentLog(
            level=level,
            source=source,
            message=message,
            negotiation_id=negotiation_id,
        )
        store.logs.append(log)
        await ws_manager.broadcast({"type": "log", "data": log.model_dump()})
        return log


stellar_service = StellarService()
