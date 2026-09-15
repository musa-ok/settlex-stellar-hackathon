from __future__ import annotations

import asyncio
import json
import os
import re
from pathlib import Path
from typing import Any

import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from .models import Negotiation, OfferMessage
from .websocket_manager import ws_manager

JSON_SCHEMA_HINT = (
    'Yalnızca JSON döndür: '
    '{"price": <float>, "message": "<ikna edici kısa mesaj>", '
    '"status": "negotiating" veya "deal"}'
)


def _parse_json_object(raw: str) -> dict[str, Any]:
    text = (raw or "").strip()
    fenced = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if fenced:
        text = fenced.group(1).strip()
    return json.loads(text)


class NegotiationLLM:
    def __init__(self) -> None:
        self.model_name = os.environ.get("GEMINI_MODEL", "gemini-3.8-flash")
        self.api_key = os.environ.get("GEMINI_API_KEY")
        if self.api_key:
            genai.configure(api_key=self.api_key)

    async def complete(self, system: str, user: str) -> dict[str, Any]:
        if not self.api_key:
            raise RuntimeError("GEMINI_API_KEY tanımlı değil")
        model = genai.GenerativeModel(
            self.model_name,
            system_instruction=f"{system}\n{JSON_SCHEMA_HINT}",
            generation_config={
                "temperature": 0.7,
                "response_mime_type": "application/json",
            },
        )
        resp = await asyncio.to_thread(model.generate_content, user)
        data = _parse_json_object(resp.text or "{}")
        price = float(data["price"])
        message = str(data.get("message") or "")
        status = str(data.get("status") or "negotiating")
        if status not in ("negotiating", "deal"):
            status = "negotiating"
        return {"price": round(price, 2), "message": message, "status": status}


llm = NegotiationLLM()


def apply_deal_rule(offer: dict[str, Any], max_price: float) -> dict[str, Any]:
    if offer["price"] <= max_price:
        offer["status"] = "deal"
    return offer


async def append_log(
    neg: Negotiation,
    speaker: str,
    price: float,
    message: str,
    status: str,
    round_no: int,
) -> None:
    """Persist the turn and push it to /ws/agent-console."""
    neg.messages.append(
        OfferMessage(role=speaker, amount=price, text=message, round=round_no)
    )
    neg.round = round_no
    neg.current_amount = price
    from .store import store

    store.negotiations[neg.id] = neg
    await ws_manager.broadcast(
        {
            "speaker": speaker,
            "message": message,
            "price": price,
            "status": status,
        }
    )
    await ws_manager.broadcast({"type": "negotiation", "data": neg.model_dump()})
