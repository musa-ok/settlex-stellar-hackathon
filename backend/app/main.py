from __future__ import annotations

import json
import os
from pathlib import Path
from typing import List

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware

from .agent_negotiation import negotiation_service
from .return_agent import return_agent
from .stellar_anchor import stellar_anchor_service
from .models import (
    AnomalyAction,
    InvoiceCreate,
    ReturnCreate,
    Rule,
    RuleCreate,
    WithdrawRequest,
    StatelessInvoiceRequest,
    StatelessReturnRequest,
    NegotiationContext,
    PastInvoice,
    ErrorResponse,
    ErrorDetail,
)
from .rules_engine import RuleEngine
from .stellar_client import stellar_service
from .store import store
from .websocket_manager import ws_manager

rule_engine = RuleEngine()

# CORS Configuration from environment
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "http://localhost:5173,http://localhost:3000").split(",")
ALLOWED_ORIGINS = [origin.strip() for origin in ALLOWED_ORIGINS if origin.strip()]

app = FastAPI(
    title="Settlex",
    description="Otonom ödeme ajanı — çevrimiçi ajan pazarlığı × Stellar × SEP-6/SEP-10",
    version="0.3.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)


@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "settlex"}


@app.post("/api/rules")
async def create_rule(body: RuleCreate):
    """Create a rule (DEPRECATED: Use context-based negotiation instead)"""
    anomaly = body.anomaly_threshold if body.anomaly_threshold else body.budget_limit * 2
    rule = Rule(
        supplier=body.supplier,
        budget_limit=body.budget_limit,
        anomaly_threshold=anomaly,
        product_hint=body.product_hint,
        raw_text=body.raw_text,
    )
    # Note: Still storing for backward compatibility, but clients should use context
    store.rules[rule.id] = rule
    await stellar_service.emit_log(
        "info",
        "rules",
        f"Yeni kural: {rule.supplier} → max {rule.budget_limit:.2f} TL",
    )
    return rule


@app.post("/api/rules/parse")
async def parse_rule(payload: dict):
    return rule_engine.parse_natural_language(payload.get("text", ""))


@app.get("/api/rules")
async def list_rules():
    """List stored rules (DEPRECATED: Use context-based negotiation instead)"""
    return list(store.rules.values())


@app.delete("/api/rules/{rule_id}")
async def delete_rule(rule_id: str):
    """Delete a rule (DEPRECATED: Use context-based negotiation instead)"""
    store.rules.pop(rule_id, None)
    return {"ok": True}


@app.post("/api/invoice")
async def post_invoice(body: InvoiceCreate):
    """Submit invoice (LEGACY: Use /api/invoice/stateless for new integrations)"""
    return await negotiation_service.submit_invoice(body, lang=body.lang)


@app.post("/api/invoice/stateless")
async def post_invoice_stateless(body: StatelessInvoiceRequest):
    """Submit invoice with context (STATELESS - Recommended for new integrations)"""
    try:
        # Extract context data
        context = body.context
        past_invoices = context.past_invoices
        rules = context.rules
        wallet_public_key = context.wallet_public_key
        
        # Create invoice from request
        invoice_data = body.invoice
        
        # Temporarily inject context into negotiation service
        # Note: This is a transitional approach - ideally, negotiation_service should accept context
        # For now, we'll use the rules from context and past invoices for RAG
        
        # Override store rules with context rules for this request
        original_rules = store.rules.copy()
        store.rules = {rule.id: rule for rule in rules}
        
        # Update wallet public key if provided
        if wallet_public_key:
            original_wallet = store.wallet_public_key
            store.wallet_public_key = wallet_public_key
        else:
            original_wallet = None
        
        try:
            # Execute negotiation with context (including RAG past_invoices)
            result = await negotiation_service.submit_invoice(invoice_data, past_invoices, lang=body.lang)
            return result
        finally:
            # Restore original state
            store.rules = original_rules
            if original_wallet is not None:
                store.wallet_public_key = original_wallet
                
    except ValueError as e:
        # Handle ErrorResponse from services
        error_json = str(e)
        try:
            error_data = json.loads(error_json)
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=error_data
            )
        except json.JSONDecodeError:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={
                    "error": "Invoice processing error",
                    "error_code": "INVOICE_ERROR",
                    "message": str(e)
                }
            )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "Internal server error",
                "error_code": "INTERNAL_ERROR",
                "message": str(e)
            }
        )


@app.post("/api/return")
async def post_return(body: ReturnCreate | None = None):
    """Submit return request (LEGACY: Use /api/return/stateless for new integrations)"""
    text = body.text if body else ""
    lang = body.lang if body and body.lang else "tr"
    return await return_agent.start_return(text, lang=lang)


@app.post("/api/return/stateless")
async def post_return_stateless(body: StatelessReturnRequest):
    """Submit return request with context (STATELESS - Recommended for new integrations)"""
    try:
        # Extract context data
        context = body.context
        wallet_public_key = context.wallet_public_key
        
        # Create return request from body
        return_data = body.return_request
        
        # Update wallet public key if provided
        if wallet_public_key:
            original_wallet = store.wallet_public_key
            store.wallet_public_key = wallet_public_key
        else:
            original_wallet = None
        
        try:
            # Execute return negotiation
            result = await return_agent.start_return(
                text=return_data.text,
                lang=return_data.lang
            )
            return result
        finally:
            # Restore original wallet state
            if original_wallet is not None:
                store.wallet_public_key = original_wallet
                
    except ValueError as e:
        # Handle ErrorResponse from services
        error_json = str(e)
        try:
            error_data = json.loads(error_json)
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=error_data
            )
        except json.JSONDecodeError:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={
                    "error": "Return processing error",
                    "error_code": "RETURN_ERROR",
                    "message": str(e)
                }
            )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "Internal server error",
                "error_code": "INTERNAL_ERROR",
                "message": str(e)
            }
        )


@app.get("/api/negotiations")
async def list_negotiations():
    """List negotiations (DEPRECATED: Stateless API doesn't store history)"""
    return sorted(store.negotiations.values(), key=lambda n: n.created_at, reverse=True)


@app.get("/api/negotiations/{neg_id}")
async def get_negotiation(neg_id: str):
    """Get negotiation by ID (DEPRECATED: Stateless API doesn't store history)"""
    if neg_id not in store.negotiations:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "Negotiation not found",
                "error_code": "NOT_FOUND",
                "message": f"Negotiation {neg_id} not found in local store"
            }
        )
    return store.negotiations[neg_id]


@app.post("/api/anomaly/approve")
async def anomaly_approve(body: AnomalyAction, lang: str | None = None):
    """Approve anomaly (DEPRECATED: Stateless API doesn't support multi-step approvals)"""
    return await negotiation_service.resolve_anomaly(body.negotiation_id, approved=True, lang=lang)


@app.post("/api/anomaly/reject")
async def anomaly_reject(body: AnomalyAction, lang: str | None = None):
    """Reject anomaly (DEPRECATED: Stateless API doesn't support multi-step approvals)"""
    return await negotiation_service.resolve_anomaly(body.negotiation_id, approved=False, lang=lang)


@app.post("/api/multisig/approve")
async def multisig_approve(body: AnomalyAction, lang: str | None = None):
    """Approve multisig (DEPRECATED: Stateless API doesn't support multi-step approvals)"""
    return await negotiation_service.approve_multisig(body.negotiation_id, lang=lang)


@app.get("/api/balance")
async def balance(public_key: str | None = None):
    return await stellar_service.get_balance(public_key)


@app.post("/api/wallet/fund")
async def fund_wallet(payload: dict | None = None):
    payload = payload or {}
    return await stellar_service.fund_account(payload.get("public_key"))


@app.post("/api/wallet/connect")
async def connect_wallet(payload: dict):
    """Connect wallet (DEPRECATED: Use wallet_public_key in context instead)"""
    pk = payload.get("public_key")
    if not pk:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "Public key required",
                "error_code": "MISSING_PUBLIC_KEY",
                "message": "public_key field is required"
            }
        )
    store.wallet_public_key = pk
    await stellar_service.emit_log("success", "wallet", f"Cüzdan bağlandı (SEP-10 hazır): {pk[:8]}…{pk[-4:]}")
    return {"ok": True, "public_key": pk}


@app.post("/api/sep10/challenge")
async def sep10_challenge(payload: dict):
    """Get SEP-10 challenge (DEPRECATED: Use wallet_public_key in context instead)"""
    account = payload.get("account") or store.wallet_public_key
    if not account:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "Account required",
                "error_code": "MISSING_ACCOUNT",
                "message": "account field is required or wallet must be connected"
            }
        )
    return stellar_anchor_service.challenge(account)


@app.post("/api/sep10/token")
async def sep10_token(payload: dict):
    """Get SEP-10 token (DEPRECATED: Use wallet_public_key in context instead)"""
    account = payload.get("account") or store.wallet_public_key
    if not account:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "Account required",
                "error_code": "MISSING_ACCOUNT",
                "message": "account field is required or wallet must be connected"
            }
        )
    signed = payload.get("signed_transaction") or ""
    if not signed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "Signed transaction required",
                "error_code": "MISSING_SIGNED_TX",
                "message": "signed_transaction field is required"
            }
        )
    return stellar_anchor_service.verify(account, signed)


@app.get("/api/transactions")
async def transactions():
    """List transactions (DEPRECATED: Stateless API doesn't store history)"""
    return store.transactions


@app.post("/api/anchor/withdraw")
async def anchor_withdraw(body: WithdrawRequest):
    """SEP-6 withdraw via tr-mock-anchor. Auth: SEP-10 wallet signature only."""
    return await stellar_anchor_service.execute_offramp(
        amount=body.amount,
        iban=body.iban,
        supplier="TRY Anchor",
    )


@app.get("/api/logs")
async def get_logs():
    """Get recent logs (WebSocket logs are ephemeral, only available during connection)"""
    return store.logs[-200:]


@app.websocket("/ws/agent-console")
async def agent_console(websocket: WebSocket):
    await ws_manager.connect(websocket, role="console")
    for log in store.logs[-50:]:
        await websocket.send_json({"type": "log", "data": log.model_dump(mode="json")})
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)


@app.websocket("/ws/agents")
async def agent_mesh(websocket: WebSocket):
    """Buyer/seller agents exchange offers in real time."""
    await websocket.accept()
    role = "buyer"
    try:
        hello = await websocket.receive_text()
        try:
            meta = json.loads(hello)
            role = meta.get("role") or "buyer"
        except json.JSONDecodeError:
            role = hello.strip() or "buyer"
        ws_manager.active.append(websocket)
        ws_manager.by_role.setdefault(role, []).append(websocket)
        await websocket.send_json({"type": "joined", "role": role})
        while True:
            raw = await websocket.receive_text()
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                payload = {"text": raw}
            await ws_manager.relay_agent_offer(role, payload)
            await ws_manager.broadcast(
                {
                    "type": "log",
                    "data": {
                        "id": f"mesh-{role}",
                        "level": role,
                        "source": role,
                        "message": f"Ajan mesajı ({role}): {payload}",
                        "ts": None,
                    },
                }
            )
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
