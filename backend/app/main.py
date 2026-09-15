from __future__ import annotations

import json
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
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
)
from .rules_engine import RuleEngine
from .stellar_client import stellar_service
from .store import store
from .websocket_manager import ws_manager

rule_engine = RuleEngine()

app = FastAPI(
    title="Kasa AI",
    description="Otonom ödeme ajanı — çevrimiçi ajan pazarlığı × Stellar × SEP-6/SEP-10",
    version="0.2.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "kasa-ai"}


@app.post("/api/rules")
async def create_rule(body: RuleCreate):
    anomaly = body.anomaly_threshold if body.anomaly_threshold else body.budget_limit * 2
    rule = Rule(
        supplier=body.supplier,
        budget_limit=body.budget_limit,
        anomaly_threshold=anomaly,
        product_hint=body.product_hint,
        raw_text=body.raw_text,
    )
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
    return list(store.rules.values())


@app.delete("/api/rules/{rule_id}")
async def delete_rule(rule_id: str):
    store.rules.pop(rule_id, None)
    return {"ok": True}


@app.post("/api/invoice")
async def post_invoice(body: InvoiceCreate):
    return await negotiation_service.submit_invoice(body)


@app.post("/api/return")
async def post_return(body: ReturnCreate | None = None):
    """Frecciani B2C iade ajanı — müşteri simülasyonu + SEP-6 nakit iade."""
    text = body.text if body else ""
    lang = body.lang if body and body.lang else "tr"
    return await return_agent.start_return(text, lang=lang)


@app.get("/api/negotiations")
async def list_negotiations():
    return sorted(store.negotiations.values(), key=lambda n: n.created_at, reverse=True)


@app.get("/api/negotiations/{neg_id}")
async def get_negotiation(neg_id: str):
    return store.negotiations[neg_id]


@app.post("/api/anomaly/approve")
async def anomaly_approve(body: AnomalyAction):
    return await negotiation_service.resolve_anomaly(body.negotiation_id, approved=True)


@app.post("/api/anomaly/reject")
async def anomaly_reject(body: AnomalyAction):
    return await negotiation_service.resolve_anomaly(body.negotiation_id, approved=False)


@app.post("/api/multisig/approve")
async def multisig_approve(body: AnomalyAction):
    """CFO ikinci imza — PENDING_MULTISIG kilidini açar, SEP-6'yı başlatır."""
    return await negotiation_service.approve_multisig(body.negotiation_id)


@app.get("/api/balance")
async def balance(public_key: str | None = None):
    return await stellar_service.get_balance(public_key)


@app.post("/api/wallet/fund")
async def fund_wallet(payload: dict | None = None):
    payload = payload or {}
    return await stellar_service.fund_account(payload.get("public_key"))


@app.post("/api/wallet/connect")
async def connect_wallet(payload: dict):
    pk = payload.get("public_key")
    store.wallet_public_key = pk
    await stellar_service.emit_log("success", "wallet", f"Cüzdan bağlandı (SEP-10 hazır): {pk[:8]}…{pk[-4:]}")
    return {"ok": True, "public_key": pk}


@app.post("/api/sep10/challenge")
async def sep10_challenge(payload: dict):
    account = payload.get("account") or store.wallet_public_key
    if not account:
        return {"ok": False, "error": "account gerekli"}
    return stellar_anchor_service.challenge(account)


@app.post("/api/sep10/token")
async def sep10_token(payload: dict):
    account = payload.get("account") or store.wallet_public_key
    signed = payload.get("signed_transaction") or ""
    return stellar_anchor_service.verify(account, signed)


@app.get("/api/transactions")
async def transactions():
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
