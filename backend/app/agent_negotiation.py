from __future__ import annotations

import asyncio
import numpy as np
from typing import Any, Dict, Optional, List

import google.generativeai as genai

from .llm_negotiation import append_log, apply_deal_rule, llm
from .models import (
    Decision,
    Invoice,
    InvoiceCreate,
    Negotiation,
    NegotiationStatus,
    PastInvoice,
)
from .rules_engine import RuleEngine
from .stellar_anchor import stellar_anchor_service
from .store import store
from .websocket_manager import ws_manager

# ============================================================================
# LANGUAGE LAYER
# ============================================================================
# The UI TR/EN toggle is forwarded as `lang` on the invoice payload. Only the
# natural-language parts of the prompts and the system log lines change; the
# JSON contract returned by the LLM stays in English so the parser and the
# rest of the pipeline are untouched.
# ============================================================================

DEFAULT_LANG = "tr"
LANG_NAMES = {"tr": "Turkish", "en": "English"}

SYSTEM_TEXT = {
    "tr": {
        "anomaly_freeze": (
            "Anormal tutar tespit edildi. Fatura iptal edilmedi — işlem donduruldu. "
            "Stellar Multi-Sig: yönetici (CFO) ikinci imzası bekleniyor."
        ),
        "multisig_approved": (
            "Yönetici (CFO) ikinci imzayı attı. Multi-Sig kilidi açıldı. "
            "Mutabakat sağlandı."
        ),
        "accept": "Kabul — {price:.2f} TL ≤ {limit:.2f} TL. Deal.",
        "over_limit": "{price:.2f} TL limitin üzerinde ({limit:.2f} TL).",
        "llm_error": "LLM pazarlık hatası: {error}",
    },
    "en": {
        "anomaly_freeze": (
            "Anomalous amount detected. The invoice was not cancelled — the "
            "transaction is frozen. Stellar Multi-Sig: awaiting the second "
            "signature from the manager (CFO)."
        ),
        "multisig_approved": (
            "The manager (CFO) added the second signature. The Multi-Sig lock is "
            "released. Settlement reached."
        ),
        "accept": "Accepted — {price:.2f} TRY <= {limit:.2f} TRY. Deal.",
        "over_limit": "{price:.2f} TRY is above the limit ({limit:.2f} TRY).",
        "llm_error": "LLM negotiation error: {error}",
    },
}


def normalize_lang(lang: Optional[str]) -> str:
    """Return a supported language code, falling back to the default."""
    code = (lang or "").strip().lower()[:2]
    return code if code in LANG_NAMES else DEFAULT_LANG


def lang_name(lang: str) -> str:
    return LANG_NAMES[normalize_lang(lang)]


def text(lang: str, key: str, **kwargs: Any) -> str:
    return SYSTEM_TEXT[normalize_lang(lang)][key].format(**kwargs)


def _language_clause(lang: str) -> str:
    """Shared language directive appended to every agent system prompt."""
    return (
        f"LANGUAGE: write every natural-language sentence ONLY in {lang_name(lang)}. "
        "Do not mix languages and do not translate the JSON keys or enum values — "
        "they must stay exactly as specified in English."
    )


# ============================================================================
# ON-THE-FLY RAG VECTOR SEARCH VIA COSINE SIMILARITY
# ============================================================================
# This module implements a real RAG (Retrieval-Augmented Generation) system
# using Gemini embeddings and NumPy cosine similarity for semantic search.
# It retrieves the most relevant past invoices to inform negotiation context.
# ============================================================================

# Mock RAG: kurumsal geçmiş alım hafızası (tedarikçi adı → son fatura)
PAST_INVOICES = {
    "Kağıt Tedarik A.Ş.": {"urun": "bardak", "son_fiyat": 400, "tarih": "1 ay önce"},
}

EMBEDDING_MODEL = "models/text-embedding-004"


def lookup_past_invoice(supplier: str) -> dict | None:
    """Legacy mock lookup - kept for backward compatibility"""
    name = (supplier or "").strip()
    if name in PAST_INVOICES:
        return PAST_INVOICES[name]
    folded = name.casefold()
    for key, record in PAST_INVOICES.items():
        if key.casefold() == folded:
            return record
    return None


def _as_dict(invoice: Any) -> Dict[str, Any]:
    """Normalize an invoice (pydantic model or plain dict) to a dict.

    Both `InvoiceCreate` instances and raw dicts flow through the RAG path, so
    every reader goes through this helper instead of assuming one shape.
    """
    if isinstance(invoice, dict):
        return invoice
    if hasattr(invoice, "model_dump"):
        return invoice.model_dump()
    return {
        key: getattr(invoice, key, None)
        for key in ("supplier", "product", "quantity", "amount", "date")
    }


def _invoice_to_text(invoice: InvoiceCreate | PastInvoice | dict) -> str:
    """Convert invoice to text representation for embedding generation.

    Args:
        invoice: Invoice object or dict with supplier, product, quantity, amount

    Returns:
        Text string representing the invoice for embedding
    """
    data = _as_dict(invoice)
    return (
        f"Tedarikçi: {data.get('supplier', '')}, "
        f"Ürün: {data.get('product', '')}, "
        f"Miktar: {data.get('quantity', 0)}, "
        f"Tutar: {data.get('amount', 0)} TL"
    )


def _get_embedding(text_input: str) -> np.ndarray:
    """Generate embedding for text using the Gemini embedding model.

    Args:
        text_input: Input text to embed

    Returns:
        NumPy array representing the embedding vector

    Raises:
        ValueError: If embedding generation fails
    """
    try:
        result = genai.embed_content(
            model=EMBEDDING_MODEL,
            content=text_input,
            task_type="retrieval_document",
        )
        values = result["embedding"] if isinstance(result, dict) else result.embedding
        return np.array(values, dtype=np.float32)
    except Exception as e:
        raise ValueError(f"Embedding generation failed: {e}") from e


def _cosine_similarity(vec1: np.ndarray, vec2: np.ndarray) -> float:
    """Calculate cosine similarity between two vectors.

    Args:
        vec1: First embedding vector
        vec2: Second embedding vector

    Returns:
        Cosine similarity score between -1 and 1
    """
    dot_product = np.dot(vec1, vec2)
    norm1 = np.linalg.norm(vec1)
    norm2 = np.linalg.norm(vec2)

    if norm1 == 0 or norm2 == 0:
        return 0.0

    return float(dot_product / (norm1 * norm2))


def retrieve_relevant_invoices(
    current_invoice: InvoiceCreate,
    past_invoices: List[PastInvoice],
    top_k: int = 3,
) -> List[Dict[str, Any]]:
    """Retrieve top-k most relevant past invoices using vector search.

    This function implements on-the-fly RAG by:
    1. Generating embeddings for the current invoice
    2. Generating embeddings for all past invoices
    3. Calculating cosine similarity between current and each past invoice
    4. Returning the top-k most similar invoices

    Args:
        current_invoice: The invoice being negotiated
        past_invoices: List of past invoices for RAG context
        top_k: Number of top results to return (default: 3)

    Returns:
        List of top-k most relevant past invoices as dicts, sorted by similarity
    """
    if not past_invoices:
        return []

    try:
        # Generate embedding for current invoice
        current_embedding = _get_embedding(_invoice_to_text(current_invoice))

        # Calculate similarities with all past invoices
        similarities = []
        for past_invoice in past_invoices:
            past_embedding = _get_embedding(_invoice_to_text(past_invoice))
            similarity = _cosine_similarity(current_embedding, past_embedding)
            similarities.append((similarity, _as_dict(past_invoice)))

        # Sort by similarity (descending) and return top-k
        similarities.sort(key=lambda x: x[0], reverse=True)
        return [invoice for _, invoice in similarities[:top_k]]

    except Exception as e:
        # Fallback to empty list if embedding fails
        print(f"RAG retrieval failed: {e}")
        return []


class AgentNegotiationService:
    """3-step buyer ↔ seller loop driven by LLM JSON offers."""

    # Seller may concede at most this share of the invoice amount.
    FLOOR_RATIO = 0.90

    def __init__(self, rules: Optional[RuleEngine] = None) -> None:
        self.rules = rules or RuleEngine()

    async def _append_log(
        self,
        neg: Negotiation,
        speaker: str,
        price: float,
        message: str,
        status: str,
        round_no: int,
    ) -> None:
        await append_log(neg, speaker, price, message, status, round_no)

    # ------------------------------------------------------------------
    # PROMPTS
    # ------------------------------------------------------------------

    def _seller_opening_prompts(self, neg, invoice_amount, lang):
        qty_line = (
        f"Quantity: {neg.quantity}.\n" if neg.quantity else ""
    )
        system = (
        "You are the SELLER agent in an autonomous B2B settlement negotiation.\n"
        f"{_language_clause(lang)}\n"
        "HARD CONSTRAINTS (a violated turn is discarded):\n"
        f"- The invoice amount is {invoice_amount:.2f} TL and it IS your opening "
        "price. Quote exactly this number.\n"
        "- Never invent another figure, never add margin, never round up or down.\n"
        "- Do NOT invent quantities, dates, delivery times or any other concrete "
        "detail that was not given to you below. If a detail is missing, speak in "
        "general terms (e.g. 'this order' instead of a specific unit count).\n"
        "- Amounts are plain numbers with at most 2 decimals, no separators.\n"
        "STYLE: one or two short sentences, professional, justify the price with "
        "quality and terms. No emoji."
    )
        user = (
        f"Product: {neg.product}. {qty_line}"
        f"Supplier: {neg.supplier}.\n"
        f"Make your opening offer at exactly {invoice_amount:.2f} TL."
    )
        return system, user

    def _buyer_prompts(
        self,
        neg: Negotiation,
        max_limit: float,
        fatura_tutari: float,
        seller_ask: float,
        rag_context: Optional[List[Dict[str, Any]]] = None,
        lang: str = DEFAULT_LANG,
    ) -> tuple[str, str]:
        """Generate buyer agent prompts with RAG context injection.

        Args:
            neg: Current negotiation
            max_limit: Budget limit
            fatura_tutari: Current invoice amount
            seller_ask: Seller's asking price
            rag_context: Top-K relevant past invoices from RAG retrieval
            lang: UI language code ("tr" | "en")

        Returns:
            Tuple of (system_prompt, user_prompt)
        """
        system = (
            "You are the Settlex BUYER (procurement) agent.\n"
            f"{_language_clause(lang)}\n"
            "HARD CONSTRAINTS:\n"
            f"- Your absolute budget limit is {max_limit:.2f} TL. Never accept above it.\n"
            f"- If the seller's price is at or below {max_limit:.2f} TL, accept it.\n"
            "- Otherwise reject and counter with a lower figure that sits at or below "
            "your limit, and never above the seller's current price.\n"
            "- Amounts are plain numbers with at most 2 decimals, no separators.\n"
            "STYLE: one or two short sentences, budget-focused and cooperative. "
            "No emoji."
        )
        user = (
            f"Invoice amount: {fatura_tutari:.2f} TL. "
            f"Seller's current offer: {seller_ask:.2f} TL. "
            f"Your limit: {max_limit:.2f} TL.\n"
            "Analyse the offer and respond."
        )

        # Inject RAG context if available (Top-3 most relevant invoices)
        if rag_context:
            rag_context_text = "\n".join(
                [
                    f"- {inv.get('supplier', 'Unknown')}: "
                    f"{inv.get('product', 'Unknown')}, "
                    f"{inv.get('amount', 0)} TL (date: {inv.get('date', 'unknown')})"
                    for inv in rag_context
                ]
            )
            system = (
                f"{system}\n"
                "=== CORPORATE MEMORY (RAG - Top-3 most relevant invoices) ===\n"
                f"{rag_context_text}\n"
                "Use these past transactions as leverage: if the current offer is "
                "above the historical prices, cite the corporate memory and push the "
                "price back towards those levels.\n"
                "============================================================"
            )

        return system, user

    def _seller_closing_prompts(
        self,
        neg: Negotiation,
        max_limit: float,
        seller_ask: float,
        buyer_offer: float,
        floor_amount: float,
        lang: str,
    ) -> tuple[str, str]:
        """Final seller turn: concede towards the buyer's limit, never below floor."""
        system = (
            "You are the SELLER agent and you want to close the deal.\n"
            f"{_language_clause(lang)}\n"
            "HARD CONSTRAINTS:\n"
            f"- Your final price must be at or below your previous offer of "
            f"{seller_ask:.2f} TL.\n"
            f"- Your final price must never go below {floor_amount:.2f} TL.\n"
            f"- Aim at or just under the buyer's limit of {max_limit:.2f} TL.\n"
            "- Amounts are plain numbers with at most 2 decimals, no separators.\n"
            "STYLE: one or two short sentences, warm closing tone. No emoji."
        )
        user = (
            f"Your previous offer: {seller_ask:.2f} TL. "
            f"Buyer's counter offer: {buyer_offer:.2f} TL. "
            f"Buyer's limit: {max_limit:.2f} TL.\n"
            "Make your final offer."
        )
        return system, user

    # ------------------------------------------------------------------
    # FLOW
    # ------------------------------------------------------------------

    async def submit_invoice(
        self,
        payload: InvoiceCreate,
        past_invoices: Optional[List[PastInvoice]] = None,
        lang: Optional[str] = None,
    ) -> Negotiation:
        # The UI toggle can arrive either as an explicit argument or on the payload.
        lang = normalize_lang(lang or getattr(payload, "lang", None))

        invoice_data = payload.model_dump()
        invoice_data.pop("lang", None)
        invoice = Invoice(**invoice_data)
        store.invoices[invoice.id] = invoice

        neg = Negotiation(
            invoice_id=invoice.id,
            supplier=invoice.supplier,
            product=invoice.product,
            quantity=invoice.quantity,
            initial_amount=invoice.amount,
            current_amount=invoice.amount,
            status=NegotiationStatus.PENDING,
        )
        store.negotiations[neg.id] = neg

        rules = list(store.rules.values())
        decision, rule, reason = self.rules.evaluate_invoice(invoice, rules)

        if decision == Decision.ANOMALY:
            neg.status = NegotiationStatus.PENDING_MULTISIG
            neg.anomaly_reason = reason
            store.negotiations[neg.id] = neg
            await self._append_log(
                neg,
                "seller",
                invoice.amount,
                text(lang, "anomaly_freeze"),
                "pending_multisig",
                0,
            )
            await ws_manager.broadcast({"type": "negotiation", "data": neg.model_dump()})
            return neg

        max_limit = rule.budget_limit if rule else 450.0

        # Perform RAG retrieval if past_invoices provided
        rag_context = None
        if past_invoices:
            rag_context = retrieve_relevant_invoices(invoice, past_invoices, top_k=3)

        try:
            await self._three_step_loop(
                neg,
                max_limit=max_limit,
                ask=invoice.amount,
                rag_context=rag_context,
                lang=lang,
            )
        except Exception as exc:
            await self._append_log(
                neg,
                "buyer",
                invoice.amount,
                text(lang, "llm_error", error=exc),
                "negotiating",
                0,
            )
        return neg

    async def _three_step_loop(
        self,
        neg: Negotiation,
        max_limit: float,
        ask: float,
        rag_context: Optional[List[Dict[str, Any]]] = None,
        lang: str = DEFAULT_LANG,
    ) -> None:
        lang = normalize_lang(lang)
        neg.status = NegotiationStatus.NEGOTIATING
        store.negotiations[neg.id] = neg

        ask = float(ask or 0) or float(neg.initial_amount)
        floor_amount = round(ask * self.FLOOR_RATIO, 2)

        # Adım 1 — satıcı ajan: açılış teklifi fatura tutarına sabit
        seller_system, seller_user = self._seller_opening_prompts(neg, ask, lang)
        seller = await llm.complete(seller_system, seller_user)
        # The wording comes from the model, the number comes from the invoice.
        seller_ask = ask
        await self._append_log(
            neg, "seller", seller_ask, seller["message"], "negotiating", 1
        )
        await asyncio.sleep(1)

        # Adım 2 — alıcı ajan (RAG kurumsal hafıza + bütçe limiti)
        buyer_system, buyer_user = self._buyer_prompts(
            neg,
            max_limit=max_limit,
            fatura_tutari=ask,
            seller_ask=seller_ask,
            rag_context=rag_context,
            lang=lang,
        )
        buyer = await llm.complete(buyer_system, buyer_user)
        # A counter offer can never exceed the seller's standing price.
        buyer_price = min(float(buyer["price"]), seller_ask)
        await self._append_log(
            neg, "buyer", buyer_price, buyer["message"], "negotiating", 2
        )
        await asyncio.sleep(1)

        # Adım 3 — satıcı 2. teklif
        closing_system, closing_user = self._seller_closing_prompts(
            neg,
            max_limit=max_limit,
            seller_ask=seller_ask,
            buyer_offer=buyer_price,
            floor_amount=floor_amount,
            lang=lang,
        )
        seller2 = await llm.complete(closing_system, closing_user)
        # Monotonic concession: never above the previous offer, never below the floor.
        seller2["price"] = max(min(float(seller2["price"]), seller_ask), floor_amount)
        seller2 = apply_deal_rule(seller2, max_limit)
        await self._append_log(
            neg, "seller", seller2["price"], seller2["message"], seller2["status"], 3
        )

        if seller2["price"] <= max_limit:
            seller2["status"] = "deal"
            await self._append_log(
                neg,
                "buyer",
                seller2["price"],
                text(lang, "accept", price=seller2["price"], limit=max_limit),
                "deal",
                3,
            )
            await self._close_deal(neg, seller2["price"])
            return

        neg.status = NegotiationStatus.FAILED
        store.negotiations[neg.id] = neg
        await self._append_log(
            neg,
            "buyer",
            seller2["price"],
            text(lang, "over_limit", price=seller2["price"], limit=max_limit),
            "negotiating",
            3,
        )

    async def _close_deal(self, neg: Negotiation, amount: float) -> None:
        neg.agreed_amount = amount
        neg.current_amount = amount
        neg.status = NegotiationStatus.AGREED
        store.negotiations[neg.id] = neg
        await ws_manager.broadcast({"type": "negotiation", "data": neg.model_dump()})
        await stellar_anchor_service.on_deal_reached(amount, neg.id)
        if store.transactions:
            neg.payment_tx = store.transactions[0].tx_hash
        neg.status = NegotiationStatus.PAID
        store.negotiations[neg.id] = neg
        await ws_manager.broadcast({"type": "negotiation", "data": neg.model_dump()})

    async def resolve_anomaly(
        self,
        negotiation_id: str,
        approved: bool,
        lang: Optional[str] = None,
    ) -> Negotiation:
        neg = store.negotiations[negotiation_id]
        if not approved:
            neg.status = NegotiationStatus.REJECTED
            store.negotiations[neg.id] = neg
            await ws_manager.broadcast({"type": "negotiation", "data": neg.model_dump()})
            return neg
        return await self.approve_multisig(negotiation_id, lang=lang)

    async def approve_multisig(
        self, negotiation_id: str, lang: Optional[str] = None
    ) -> Negotiation:
        """CFO ikinci imza: kilidi aç, mutabakat, SEP-6 on-chain."""
        lang = normalize_lang(lang)
        neg = store.negotiations[negotiation_id]
        amount = float(neg.current_amount or neg.initial_amount)
        await self._append_log(
            neg,
            "buyer",
            amount,
            text(lang, "multisig_approved"),
            "deal",
            1,
        )
        await self._close_deal(neg, amount)
        return neg


negotiation_service = AgentNegotiationService()