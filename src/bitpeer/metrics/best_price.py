from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional

from bitpeer.models import Offer


@dataclass(frozen=True)
class Constraints:
    payment_methods_any: Optional[set[str]] = None
    merchant_only: bool = False
    min_rating: float = 0.0


@dataclass(frozen=True)
class BestSingleResult:
    offer: Offer
    price_fiat_per_usdt: float


def _passes_constraints(offer: Offer, c: Constraints) -> bool:
    if c.merchant_only and offer.is_merchant is not True:
        return False
    if offer.rating is not None and offer.rating < c.min_rating:
        return False
    if c.payment_methods_any:
        if not any(m in c.payment_methods_any for m in offer.payment_methods):
            return False
    return True


def _executable_for_fiat_amount(offer: Offer, amount_fiat: float) -> bool:
    return offer.min_fiat <= amount_fiat <= offer.max_fiat


def _executable_for_usdt_amount(offer: Offer, amount_usdt: float) -> bool:
    amount_fiat = amount_usdt * offer.price_fiat_per_usdt
    return offer.min_fiat <= amount_fiat <= offer.max_fiat


def best_single(
    offers: list[Offer],
    *,
    direction: Literal["buy_usdt", "sell_usdt"],
    amount: float,
    constraints: Constraints,
) -> Optional[BestSingleResult]:
    """
    Best executable single offer:
    - buy_usdt: pick minimum price (fiat/USDT) among SELL-side offers executable for amount_fiat
    - sell_usdt: pick maximum price among BUY-side offers executable for amount_usdt (fiat constraints applied)
    """

    candidates: list[Offer] = []
    for offer in offers:
        if not _passes_constraints(offer, constraints):
            continue
        if direction == "buy_usdt":
            if offer.side != "SELL":
                continue
            if not _executable_for_fiat_amount(offer, amount):
                continue
        else:
            if offer.side != "BUY":
                continue
            if not _executable_for_usdt_amount(offer, amount):
                continue
        candidates.append(offer)

    if not candidates:
        return None

    if direction == "buy_usdt":
        best = min(candidates, key=lambda o: o.price_fiat_per_usdt)
    else:
        best = max(candidates, key=lambda o: o.price_fiat_per_usdt)

    return BestSingleResult(offer=best, price_fiat_per_usdt=best.price_fiat_per_usdt)

