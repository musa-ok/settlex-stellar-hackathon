from __future__ import annotations

import asyncio
from typing import Optional

from .llm_negotiation import append_log, apply_deal_rule, llm
from .models import (
    Decision,
    Invoice,
    InvoiceCreate,
    Negotiation,
    NegotiationStatus,
)
from .rules_engine import RuleEngine
from .stellar_anchor import stellar_anchor_service
from .store import store
from .websocket_manager import ws_manager

# Mock RAG: kurumsal geçmiş alım hafızası (tedarikçi adı → son fatura)
PAST_INVOICES = {
    "Kağıt Tedarik A.Ş.": {"urun": "bardak", "son_fiyat": 400, "tarih": "1 ay önce"},
}


def lookup_past_invoice(supplier: str) -> dict | None:
    name = (supplier or "").strip()
    if name in PAST_INVOICES:
        return PAST_INVOICES[name]
    folded = name.casefold()
    for key, record in PAST_INVOICES.items():
        if key.casefold() == folded:
            return record
    return None


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
    ) -> tuple[str, str]:
        system = "Sen bir satın alma ajanısın."
        user = (
            f"Sen bir satın alma ajanısın. Kesin limitin: {max_limit} TL. "
            f"Satıcının {seller_ask} TL teklifini analiz et. "
            "Limitin üstündeyse reddedip daha düşük bir karşı teklif ver."
        )
        past = lookup_past_invoice(neg.supplier)
        if past:
            rag_rule = (
                "Eğer mevcut tedarikçi için geçmiş alım verisi bulunuyorsa, "
                "pazarlığa kesinlikle bu referansı kullanarak başla. "
                "Argümanını şu şekilde kur: "
                f"'Kurumsal hafıza kayıtlarımıza göre {past['tarih']} sizden aynı ürünü "
                f"{past['son_fiyat']} TL'ye temin etmişiz. Bize sunduğunuz "
                f"{fatura_tutari:.2f} TL'lik yeni teklif piyasa enflasyonunun çok üzerinde. "
                "Anlaşmayı sağlamak için fiyatı geçmiş alım seviyemize yaklaştırmalısınız.'"
            )
            system = (
                f"{system}\n"
                f"Kurumsal hafıza (RAG) eşleşmesi: tedarikçi={neg.supplier}, "
                f"ürün={past.get('urun')}, son_fiyat={past['son_fiyat']} TL, "
                f"tarih={past['tarih']}.\n"
                f"{rag_rule}"
            )
        return system, user

    async def submit_invoice(self, payload: InvoiceCreate) -> Negotiation:
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
        try:
            await self._three_step_loop(neg, max_limit=max_limit, ask=invoice.amount)
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

    async def _three_step_loop(self, neg: Negotiation, max_limit: float, ask: float) -> None:
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
            neg, max_limit=max_limit, fatura_tutari=ask, seller_ask=seller_ask
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
