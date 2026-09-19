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

from .models import Negotiation, OfferMessage, ErrorResponse, ErrorDetail
from .websocket_manager import ws_manager

JSON_SCHEMA_HINT = (
    'Yalnızca JSON döndür: '
    '{"price": <float>, "message": "<ikna edici kısa mesaj>", '
    '"status": "negotiating" veya "deal"}'
)


def _parse_json_object(raw: str) -> dict[str, Any]:
    """Parse JSON from LLM response with robust error handling"""
    text = (raw or "").strip()
    
    
    if not text:
        raise ValueError("Empty response to parse")
    
    # Try to extract JSON from markdown code blocks
    fenced = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if fenced:
        text = fenced.group(1).strip()
    
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        # Try to fix common JSON issues
        try:
            # Remove trailing commas
            text = re.sub(r",\s*([}\]])", r"\1", text)
            return json.loads(text)
        except json.JSONDecodeError:
            raise json.JSONDecodeError(
                f"Failed to parse JSON: {e.msg}",
                text,
                e.pos
            ) from e

class NegotiationLLM:
    def __init__(self) -> None:
        # .env'yi devre dışı bırakıp modeli direkt string olarak veriyoruz:
        self.model_name = "gemini-2.5-flash"
        
        self.api_key = os.environ.get("GEMINI_API_KEY")
        if self.api_key:
            genai.configure(api_key=self.api_key)
    async def complete(self, system: str, user: str) -> dict[str, Any]:
        """Execute LLM completion with comprehensive error handling"""
        if not self.api_key:
            raise ValueError(
                ErrorResponse(
                    error="GEMINI_API_KEY not configured",
                    error_code="MISSING_API_KEY",
                    details=[
                        ErrorDetail(
                            field="GEMINI_API_KEY",
                            message="Gemini API key is required for LLM negotiation",
                            code="ENV_VAR_MISSING"
                        )
                    ]
                ).model_dump_json()
            )

        try:
            model = genai.GenerativeModel(
                self.model_name,
                system_instruction=f"{system}\n{JSON_SCHEMA_HINT}",
                generation_config={
                    "temperature": 0.7,
                    "response_mime_type": "application/json",
                },
            )
            resp = await asyncio.to_thread(model.generate_content, user)
            
            if not resp or not resp.text:
                raise ValueError("Empty response from LLM")
                
            data = _parse_json_object(resp.text)
            
            if "price" not in data:
                raise ValueError("LLM response missing 'price' field")
                
            price = float(data["price"])
            message = str(data.get("message") or "")
            status = str(data.get("status") or "negotiating")
            
            if status not in ("negotiating", "deal"):
                status = "negotiating"
                
            return {"price": round(price, 2), "message": message, "status": status}
            
        except json.JSONDecodeError as e:
            raise ValueError(
                ErrorResponse(
                    error="Invalid JSON response from LLM",
                    error_code="LLM_JSON_PARSE_ERROR",
                    details=[
                        ErrorDetail(
                            field="response",
                            message=f"Failed to parse LLM JSON response: {str(e)}",
                            code="JSON_DECODE_ERROR"
                        )
                    ]
                ).model_dump_json()
            ) from e
            
        except (KeyError, ValueError) as e:
            raise ValueError(
                ErrorResponse(
                    error="Invalid LLM response format",
                    error_code="LLM_INVALID_FORMAT",
                    details=[
                        ErrorDetail(
                            field="response",
                            message=f"LLM response validation failed: {str(e)}",
                            code="VALIDATION_ERROR"
                        )
                    ]
                ).model_dump_json()
            ) from e
            
        except Exception as e:
            # Handle network errors, rate limits, etc.
            error_msg = str(e).lower()
            if "quota" in error_msg or "limit" in error_msg:
                raise ValueError(
                    ErrorResponse(
                        error="LLM API quota exceeded",
                        error_code="LLM_QUOTA_EXCEEDED",
                        details=[
                            ErrorDetail(
                                field="api",
                                message="Gemini API quota or rate limit exceeded",
                                code="RATE_LIMIT_ERROR"
                            )
                        ]
                ).model_dump_json()
                ) from e
            elif "timeout" in error_msg or "connection" in error_msg:
                raise ValueError(
                    ErrorResponse(
                        error="LLM API connection timeout",
                        error_code="LLM_TIMEOUT",
                        details=[
                            ErrorDetail(
                                field="api",
                                message="Failed to connect to Gemini API (timeout)",
                                code="CONNECTION_ERROR"
                            )
                        ]
                ).model_dump_json()
                ) from e
            else:
                raise ValueError(
                    ErrorResponse(
                        error="LLM API error",
                        error_code="LLM_API_ERROR",
                        details=[
                            ErrorDetail(
                                field="api",
                                message=f"Unexpected LLM API error: {str(e)}",
                                code="UNKNOWN_ERROR"
                            )
                        ]
                ).model_dump_json()
                ) from e


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
