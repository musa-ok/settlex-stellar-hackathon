from __future__ import annotations

from .db import mark_session_status
from .models import Negotiation, NegotiationStatus
from .stellar_anchor import DEFAULT_IBAN, stellar_anchor_service
from .store import store
from .websocket_manager import ws_manager


class SettlementFailed(Exception):
    """The Stellar / SEP-6 payment did not go through; the payment is back to pending."""


async def _publish(neg: Negotiation, message: str, level: str) -> None:
    store.negotiations[neg.id] = neg
    await ws_manager.broadcast({"type": "negotiation", "data": neg.model_dump()})
    await ws_manager.broadcast({"type": "anchor_step", "message": message, "level": level})


async def settle_pending(
    neg: Negotiation,
    *,
    pending_status: NegotiationStatus,
    amount: float,
    supplier: str,
    iban: str = DEFAULT_IBAN,
) -> Negotiation:
    """Run the held SEP-6 payment. COMPLETED only with an on-chain tx hash;
    on any failure the negotiation returns to `pending_status` so it can be retried."""
    try:
        result = await stellar_anchor_service.execute_offramp(
            amount=amount,
            iban=iban,
            negotiation_id=neg.id,
            supplier=supplier,
        )
        tx_hash = result.get("tx_hash")
        if not tx_hash:
            raise SettlementFailed(
                result.get("error")
                or result.get("message")
                or str(result.get("body") or "No on-chain transaction was submitted")
            )
    except Exception as exc:
        reason = str(exc) or exc.__class__.__name__
        neg.status = pending_status
        # execute_offramp may already have stamped the row "simulated"; put it back in the queue.
        mark_session_status(neg.id, pending_status.value)
        await _publish(neg, f"Ödeme başarısız, işlem tekrar onaya açıldı: {reason}", "warn")
        raise SettlementFailed(reason) from exc

    neg.payment_tx = tx_hash
    neg.status = NegotiationStatus.COMPLETED
    mark_session_status(neg.id, NegotiationStatus.COMPLETED.value)
    await _publish(neg, f"Ödeme tamamlandı (COMPLETED): {tx_hash}", "info")
    return neg


async def reject_pending(neg: Negotiation, message: str) -> Negotiation:
    """Cancel a held payment: nothing is sent to Stellar."""
    neg.status = NegotiationStatus.REJECTED
    mark_session_status(neg.id, NegotiationStatus.REJECTED.value)
    await _publish(neg, message, "warn")
    return neg
