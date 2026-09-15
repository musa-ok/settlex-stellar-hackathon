from __future__ import annotations

import re
from typing import Optional

from .models import Decision, Invoice, Rule


class RuleEngine:
    """Natural-language + form rules. Example: 'Kağıt tedarikçisine max 450 TL öde'."""

    def parse_natural_language(self, text: str) -> dict:
        cleaned = text.strip()
        amount_match = re.search(
            r"(?:max|maksimum|en fazla|bütçe)?\s*(\d+(?:[.,]\d+)?)\s*(?:TL|₺)?",
            cleaned,
            re.IGNORECASE,
        )
        budget = float(amount_match.group(1).replace(",", ".")) if amount_match else 450.0

        company = None
        for pattern in [
            r"([A-ZÇĞİÖŞÜa-zçğıöşü0-9\s.&'-]+?(?:A\.Ş\.|Ltd\.|Şti\.))",
            r"(?:tedarikçi[syi]*|için)\s+([A-ZÇĞİÖŞÜ][\w\s.&'-]{2,40})",
        ]:
            m = re.search(pattern, cleaned)
            if m:
                company = m.group(1).strip(" .,'\"")
                break
        if not company:
            before = re.split(r"\b(?:max|maksimum|bütçe|için|öde)\b", cleaned, flags=re.I)[0]
            company = before.strip(" .,:'\"") or "Bilinmeyen Tedarikçi"

        product = None
        product_match = re.search(
            r"(bardak|kalem|kağıt|poşet|kutu|ambalaj|ürün)",
            cleaned,
            re.IGNORECASE,
        )
        if product_match:
            product = product_match.group(1).lower()

        return {
            "supplier": company,
            "budget_limit": budget,
            "anomaly_threshold": budget * 2,
            "product_hint": product,
            "raw_text": cleaned,
        }

    def find_rule_for_supplier(self, supplier: str, rules: list[Rule]) -> Optional[Rule]:
        needle = supplier.casefold().strip()
        for rule in rules:
            if rule.supplier.casefold().strip() == needle:
                return rule
            if needle in rule.supplier.casefold() or rule.supplier.casefold() in needle:
                return rule
        return None

    def evaluate_invoice(
        self, invoice: Invoice, rules: list[Rule]
    ) -> tuple[Decision, Optional[Rule], Optional[str]]:
        if invoice.force_anomaly:
            return Decision.ANOMALY, None, "Şüpheli fatura senaryosu tetiklendi (demo)"

        rule = self.find_rule_for_supplier(invoice.supplier, rules)
        if not rule:
            return Decision.ANOMALY, None, f"Tanımadık tedarikçi: {invoice.supplier}"

        threshold = rule.anomaly_threshold or (rule.budget_limit * 2)
        if invoice.amount > threshold:
            return (
                Decision.ANOMALY,
                rule,
                f"Tutar anormal: {invoice.amount:.2f} TL > eşik {threshold:.2f} TL",
            )

        if invoice.amount <= rule.budget_limit:
            return Decision.ACCEPT, rule, None

        return Decision.COUNTER_OFFER, rule, None


rule_engine = RuleEngine()


def parse_natural_language_rule(text: str) -> dict:
    return rule_engine.parse_natural_language(text)


def find_rule_for_supplier(supplier: str, rules: list[Rule]) -> Optional[Rule]:
    return rule_engine.find_rule_for_supplier(supplier, rules)


def evaluate_invoice(
    invoice: Invoice, rules: list[Rule]
) -> tuple[Decision, Optional[Rule], Optional[str]]:
    return rule_engine.evaluate_invoice(invoice, rules)
