from __future__ import annotations

import asyncio
import numpy as np
from typing import Optional, List

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


def _invoice_to_text(invoice: InvoiceCreate | PastInvoice) -> str:
    """Convert invoice to text representation for embedding generation.
    
    Args:
        invoice: Invoice object with supplier, product, quantity, amount
        
    Returns:
        Text string representing the invoice for embedding
    """
    if hasattr(invoice, 'supplier'):
        supplier = invoice.supplier
        product = invoice.product
        quantity = invoice.quantity
        amount = invoice.amount
    else:
        # PastInvoice model
        supplier = invoice.get('supplier', '')
        product = invoice.get('product', '')
        quantity = invoice.get('quantity', 0)
        amount = invoice.get('amount', 0)
    
    return f"Tedarikçi: {supplier}, Ürün: {product}, Miktar: {quantity}, Tutar: {amount} TL"


def _get_embedding(text: str) -> np.ndarray:
    """Generate embedding for text using Gemini embedding model.
    
    Args:
        text: Input text to embed
        
    Returns:
        NumPy array representing the embedding vector
        
    Raises:
        ValueError: If embedding generation fails
    """
    try:
        model = genai.EmbeddingModel("models/text-embedding-004")
        result = model.embed_content(text)
        return np.array(result.embedding.values, dtype=np.float32)
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
    
    return dot_product / (norm1 * norm2)


def retrieve_relevant_invoices(
    current_invoice: InvoiceCreate,
    past_invoices: List[PastInvoice],
    top_k: int = 3
) -> List[PastInvoice]:
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
        List of top-k most relevant past invoices, sorted by similarity
    """
    if not past_invoices:
        return []
    
    try:
        # Generate embedding for current invoice
        current_text = _invoice_to_text(current_invoice)
        current_embedding = _get_embedding(current_text)
        
        # Calculate similarities with all past invoices
        similarities = []
        for past_invoice in past_invoices:
            past_text = _invoice_to_text(past_invoice)
            past_embedding = _get_embedding(past_text)
            similarity = _cosine_similarity(current_embedding, past_embedding)
            similarities.append((similarity, past_invoice))
        
        # Sort by similarity (descending) and return top-k
        similarities.sort(key=lambda x: x[0], reverse=True)
        return [invoice for _, invoice in similarities[:top_k]]
        
    except Exception as e:
        # Fallback to empty list if embedding fails
        print(f"RAG retrieval failed: {e}")
        return []


class AgentNegotiationService:
    """3-step buyer ↔ seller loop driven by LLM JSON offers."""

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

    def _buyer_prompts(
        self,
        neg: Negotiation,
        max_limit: float,
        fatura_tutari: float,
        seller_ask: float,
        rag_context: Optional[List[PastInvoice]] = None,
    ) -> tuple[str, str]:
        """Generate buyer agent prompts with RAG context injection.
        
        Args:
            neg: Current negotiation
            max_limit: Budget limit
            fatura_tutari: Current invoice amount
            seller_ask: Seller's asking price
            rag_context: Top-K relevant past invoices from RAG retrieval
            
        Returns:
            Tuple of (system_prompt, user_prompt)
        """
        system = "Sen bir Settlex satın alma ajanısın."
        user = (
            f"Sen bir Settlex satın alma ajanısın. Kesin limitin: {max_limit} TL. "
            f"Satıcının {seller_ask} TL teklifini analiz et. "
            "Limitin üstündeyse reddedip daha düşük bir karşı teklif ver."
        )
        
        # Inject RAG context if available (Top-3 most relevant invoices)
        if rag_context:
            rag_context_text = "\n".join([
                f"- {inv.get('supplier', 'Unknown')}: {inv.get('product', 'Unknown')}, "
                f"{inv.get('amount', 0)} TL (tarih: {inv.get('date', 'bilinmiyor')})"
                for inv in rag_context
            ])
            
            rag_rule = (
                "Kurumsal hafıza kayıtlarımıza (RAG) göre, bu tedarikçiyle geçmiş "
                "işlemlerimiz aşağıdaki gibidir:\n"
                f"{rag_context_text}\n\n"
                "Bu geçmiş verileri referans alarak pazarlık yap. "
                "Eğer mevcut teklif geçmiş fiyatların üzerindeyse, "
                "kurumsal hafıza verilerini argüman olarak kullanarak "
                "fiyatı geçmiş seviyelere yaklaştırmalarını talep et."
            )
            system = (
                f"{system}\n"
                f"=== KURUMSAL HAFIZA (RAG - Top-3 En Alakalı Faturalar) ===\n"
                f"{rag_rule}\n"
                f"============================================================"
            )
        
        return system, user

    async def submit_invoice(
        self, 
        payload: InvoiceCreate, 
        past_invoices: Optional[List[PastInvoice]] = None
    ) -> Negotiation:
        invoice = Invoice(**payload.model_dump())
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
            freeze_msg = (
                "Anormal tutar tespit edildi. Fatura iptal edilmedi — işlem donduruldu. "
                "Stellar Multi-Sig: yönetici (CFO) ikinci imzası bekleniyor."
            )
            await self._append_log(
                neg, "seller", invoice.amount, freeze_msg, "pending_multisig", 0
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
                rag_context=rag_context
            )
        except Exception as exc:
            await self._append_log(
                neg,
                "buyer",
                invoice.amount,
                f"LLM pazarlık hatası: {exc}",
                "negotiating",
                0,
            )
        return neg

    async def _three_step_loop(
        self, 
        neg: Negotiation, 
        max_limit: float, 
        ask: float,
        rag_context: Optional[List[PastInvoice]] = None
    ) -> None:
        neg.status = NegotiationStatus.NEGOTIATING
        store.negotiations[neg.id] = neg
        ask = float(ask or 480)

        # Adım 1 — satıcı ajan
        seller = await llm.complete(
            "Sen bir satıcısın.",
            "Sen bir satıcısın. Ürünü 480 TL civarında bir fiyattan satmaya çalışarak "
            f"ilk teklifini yap. Referans fatura tutarı: {ask:.2f} TL. {neg.product}.",
        )
        seller_ask = seller["price"]
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
            rag_context=rag_context
        )
        buyer = await llm.complete(buyer_system, buyer_user)
        await self._append_log(
            neg, "buyer", buyer["price"], buyer["message"], "negotiating", 2
        )
        await asyncio.sleep(1)

        # Adım 3 — satıcı 2. teklif
        seller2 = await llm.complete(
            "Sen bir satıcısın. Anlaşmak istiyorsun.",
            "Alıcının karşı teklifine bakarak "
            f"{max_limit} limitine yakın veya altında son bir teklif yap. "
            f"Alıcı teklifi: {buyer['price']} TL. İlk senin teklifin: {seller_ask} TL.",
        )
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
                f"Kabul — {seller2['price']:.2f} TL ≤ {max_limit:.2f} TL. Deal.",
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
            f"{seller2['price']:.2f} TL limitin üzerinde ({max_limit:.2f} TL).",
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
        neg.status = NegotiationStatus.PAID
        store.negotiations[neg.id] = neg
        await ws_manager.broadcast({"type": "negotiation", "data": neg.model_dump()})

    async def resolve_anomaly(self, negotiation_id: str, approved: bool) -> Negotiation:
        neg = store.negotiations[negotiation_id]
        if not approved:
            neg.status = NegotiationStatus.REJECTED
            store.negotiations[neg.id] = neg
            await ws_manager.broadcast({"type": "negotiation", "data": neg.model_dump()})
            return neg
        return await self.approve_multisig(negotiation_id)

    async def approve_multisig(self, negotiation_id: str) -> Negotiation:
        """CFO ikinci imza: kilidi aç, mutabakat, SEP-6 on-chain."""
        neg = store.negotiations[negotiation_id]
        amount = float(neg.current_amount or neg.initial_amount)
        await self._append_log(
            neg,
            "buyer",
            amount,
            "Yönetici (CFO) ikinci imzayı attı. Multi-Sig kilidi açıldı. Mutabakat sağlandı.",
            "deal",
            1,
        )
        await self._close_deal(neg, amount)
        return neg


negotiation_service = AgentNegotiationService()
