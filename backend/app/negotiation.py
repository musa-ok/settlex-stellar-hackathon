from __future__ import annotations

from typing import Optional


def buyer_counter_offer(
    current_offer: float,
    budget_limit: float,
    round_num: int,
    max_rounds: int = 3,
) -> Optional[float]:
    if round_num >= max_rounds:
        return None
    if round_num == 0:
        gap = current_offer - budget_limit
        return round(max(budget_limit - 20, current_offer - gap * 1.67), 2)
    gap = current_offer - budget_limit
    new_offer = current_offer - (gap * 0.5)
    return round(min(new_offer, budget_limit), 2)


def seller_counter_offer(
    buyer_offer: float,
    seller_ask: float,
    floor_ratio: float = 0.88,
) -> float:
    floor = seller_ask * floor_ratio
    mid = buyer_offer + (seller_ask - buyer_offer) * 0.3
    return round(max(mid, floor, buyer_offer), 2)


def should_buyer_accept(amount: float, budget_limit: float) -> bool:
    return amount <= budget_limit


def should_seller_accept(amount: float, original_ask: float, floor_ratio: float = 0.90) -> bool:
    return amount >= original_ask * floor_ratio
