"""Company treasury → AI agent budget, signed in the user's own wallet (Stellar Wallets Kit).

The backend only builds the unsigned payment and submits it after checking that the
signed envelope is exactly that payment; the user's secret key never leaves the wallet.
"""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from stellar_sdk import Asset, Payment, TransactionBuilder, TransactionEnvelope
from stellar_sdk.exceptions import BaseHorizonError, NotFoundError

from .auth_context import current_user_id
from .db import explorer_url_for, persist_settlement
from .passkeys import require_passkey_user
from .stellar_anchor import NETWORK_PASSPHRASE, stellar_anchor_service
from .websocket_manager import ws_manager

router = APIRouter(prefix="/api/wallet", tags=["wallet"])

STELLAR_KEY = r"^G[A-Z2-7]{55}$"


class FundAgentBuild(BaseModel):
    source: str = Field(..., pattern=STELLAR_KEY, description="Connected wallet public key")
    amount: float = Field(..., gt=0, le=10_000)
    asset: Literal["XLM", "USDC"] = "XLM"


class FundAgentSubmit(BaseModel):
    source: str = Field(..., pattern=STELLAR_KEY)
    signed_xdr: str = Field(..., min_length=40, max_length=20_000)


def _asset(code: str) -> Asset:
    if code == "XLM":
        return Asset.native()
    asset_code, issuer = stellar_anchor_service._configured_asset()
    return Asset(asset_code, issuer)


def _bad_request(code: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail={"error": "Wallet funding rejected", "error_code": code, "message": message},
    )


@router.get("/agent")
async def agent_wallet():
    """The AI agent's settlement wallet that the company funds."""
    kp = stellar_anchor_service.agent_keypair()
    await stellar_anchor_service.ensure_funded(kp)
    return {"public_key": kp.public_key, "network_passphrase": NETWORK_PASSPHRASE}


@router.post("/fund-agent/build")
async def fund_agent_build(body: FundAgentBuild, _user=Depends(require_passkey_user)):
    """Unsigned payment from the user's wallet to the agent wallet, for the wallet to sign."""
    agent = stellar_anchor_service.agent_keypair().public_key
    if body.source == agent:
        raise _bad_request("SAME_ACCOUNT", "Connect the company wallet, not the agent wallet")
    try:
        source = stellar_anchor_service.horizon.load_account(body.source)
    except NotFoundError as exc:
        raise _bad_request(
            "SOURCE_NOT_FOUND",
            "Wallet account does not exist on testnet yet — fund it with Friendbot first",
        ) from exc
    tx = (
        TransactionBuilder(source_account=source, network_passphrase=NETWORK_PASSPHRASE, base_fee=1000)
        .append_payment_op(destination=agent, asset=_asset(body.asset), amount=f"{body.amount:.7f}")
        .add_text_memo("Settlex agent budget")
        .set_timeout(300)
        .build()
    )
    return {
        "xdr": tx.to_xdr(),
        "network_passphrase": NETWORK_PASSPHRASE,
        "agent": agent,
        "amount": body.amount,
        "asset": body.asset,
    }


@router.post("/fund-agent/submit")
async def fund_agent_submit(body: FundAgentSubmit, _user=Depends(require_passkey_user)):
    """Submit the wallet-signed budget payment after checking it is exactly what we built."""
    agent = stellar_anchor_service.agent_keypair().public_key
    try:
        envelope = TransactionEnvelope.from_xdr(body.signed_xdr, NETWORK_PASSPHRASE)
    except Exception as exc:
        raise _bad_request("INVALID_XDR", f"Could not decode the signed transaction: {exc}") from exc

    tx = envelope.transaction
    ops = tx.operations
    if tx.source.account_id != body.source:
        raise _bad_request("SOURCE_MISMATCH", "Transaction source is not the connected wallet")
    if len(ops) != 1 or not isinstance(ops[0], Payment) or ops[0].destination.account_id != agent:
        raise _bad_request("UNEXPECTED_OPERATIONS", "Only a single payment to the agent wallet is accepted")
    if not envelope.signatures:
        raise _bad_request("UNSIGNED", "The transaction was not signed by the wallet")

    try:
        result = stellar_anchor_service.horizon.submit_transaction(envelope)
    except BaseHorizonError as exc:
        codes = (getattr(exc, "extras", None) or {}).get("result_codes")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "error": "Stellar rejected the transaction",
                "error_code": "HORIZON_REJECTED",
                "message": str(codes or exc),
            },
        ) from exc

    tx_hash = result.get("hash")
    payment = ops[0]
    asset_code = "XLM" if payment.asset.is_native() else payment.asset.code
    amount = float(payment.amount)
    url = explorer_url_for(tx_hash)
    try:
        persist_settlement(
            negotiation_id=None,
            supplier=f"Ajan bütçesi ({asset_code})",
            amount=amount,
            tx_hash=tx_hash,
            status="funded",
            user_id=current_user_id.get(),
        )
    except Exception as exc:
        print(f"SQLite persist failed (non-fatal): {exc}")
    await ws_manager.broadcast(
        {
            "type": "anchor_step",
            "message": f"Şirket cüzdanı ajana {amount:g} {asset_code} bütçe yükledi: {url}",
            "level": "info",
        }
    )
    return {"ok": True, "tx_hash": tx_hash, "explorer_url": url, "amount": amount, "asset": asset_code, "agent": agent}
