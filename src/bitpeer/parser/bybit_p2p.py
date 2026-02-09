from __future__ import annotations

import gzip
import json
import logging
from pathlib import Path
from typing import Any, Iterable, Optional

import polars as pl

from bitpeer.common.config import AppConfig
from bitpeer.models import Offer, RawFetchRecord

log = logging.getLogger(__name__)


def iter_raw_records(data_dir: Path, *, day: str) -> Iterable[RawFetchRecord]:
    raw_dir = data_dir / "raw" / day
    if not raw_dir.exists():
        return

    for path in sorted(raw_dir.glob("*.jsonl.gz")):
        with gzip.open(path, "rt", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    yield RawFetchRecord.model_validate_json(line)
                except Exception as e:  # noqa: BLE001
                    log.warning("bad raw line file=%s error=%s", path, repr(e))


def _to_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.replace(",", "").strip())
        except ValueError:
            return None
    return None


def _first_present(d: dict[str, Any], keys: list[str]) -> Any:
    for k in keys:
        if k in d:
            return d[k]
    return None


def _maybe_dict(value: Any) -> Optional[dict[str, Any]]:
    return value if isinstance(value, dict) else None


def _maybe_list(value: Any) -> Optional[list[Any]]:
    return value if isinstance(value, list) else None


_PRICE_KEYS = ["price", "unitPrice", "priceValue", "rate", "unit_price"]
_MIN_KEYS = ["minAmount", "minFiat", "minOrderAmount", "min", "min_amount"]
_MAX_KEYS = ["maxAmount", "maxFiat", "maxOrderAmount", "max", "max_amount"]
_PAYMENT_KEYS = ["payment", "payments", "paymentMethods", "payment_methods", "payMethods"]
_MERCHANT_KEYS = ["isMerchant", "merchant", "is_merchant"]
_RATING_KEYS = ["rating", "userRating", "user_rating", "score"]
_ADVERTISER_KEYS = ["userId", "uid", "advertiserId", "advertiser_id", "nickName", "nickname"]


def _extract_offer_items(payload: Any) -> list[dict[str, Any]]:
    """
    Best-effort extraction for a list of offer dicts from an unknown JSON schema.
    This is intentionally heuristic until we lock the exact Bybit response shape.
    """

    def looks_like_offer(d: dict[str, Any]) -> bool:
        keys = set(d.keys())
        if keys.intersection(_PRICE_KEYS):
            return True
        # Sometimes price is nested; accept advertiser/adv keys as signal.
        if "adv" in keys or "advertiser" in keys:
            return True
        return False

    def find(obj: Any, depth: int) -> Optional[list[dict[str, Any]]]:
        if depth <= 0:
            return None

        if isinstance(obj, list) and obj:
            if all(isinstance(x, dict) for x in obj[: min(3, len(obj))]):
                dicts: list[dict[str, Any]] = [x for x in obj if isinstance(x, dict)]
                if dicts and sum(1 for d in dicts[: min(5, len(dicts))] if looks_like_offer(d)) >= 2:
                    return dicts
            for x in obj:
                res = find(x, depth - 1)
                if res is not None:
                    return res

        if isinstance(obj, dict):
            for v in obj.values():
                res = find(v, depth - 1)
                if res is not None:
                    return res

        return None

    if isinstance(payload, dict):
        result = payload.get("result")
        if isinstance(result, dict):
            for key in ("items", "data", "list", "rows"):
                v = result.get(key)
                if isinstance(v, list) and v and all(isinstance(x, dict) for x in v[: min(3, len(v))]):
                    return [x for x in v if isinstance(x, dict)]

    found = find(payload, depth=6)
    return found or []


def _extract_payment_methods(item: dict[str, Any]) -> list[str]:
    raw = _first_present(item, _PAYMENT_KEYS)
    methods: list[str] = []

    if isinstance(raw, list):
        for p in raw:
            if isinstance(p, str):
                methods.append(p)
                continue
            if isinstance(p, dict):
                name = (
                    p.get("name")
                    or p.get("paymentMethodName")
                    or p.get("identifier")
                    or p.get("id")
                    or p.get("key")
                )
                if name:
                    methods.append(str(name))
    elif isinstance(raw, dict):
        # Sometimes payments are a dict keyed by method.
        methods.extend(str(k) for k in raw.keys())

    # Dedupe, keep order
    out: list[str] = []
    for m in methods:
        if m not in out:
            out.append(m)
    return out


def parse_raw_fetch(record: RawFetchRecord) -> list[Offer]:
    if not record.response_text:
        return []

    try:
        payload = json.loads(record.response_text)
    except Exception:  # noqa: BLE001
        return []

    items = _extract_offer_items(payload)
    offers: list[Offer] = []

    for item in items:
        adv = _maybe_dict(item.get("adv")) or _maybe_dict(item.get("advertisement")) or {}
        advertiser = _maybe_dict(item.get("advertiser")) or _maybe_dict(item.get("user")) or {}

        price = _to_float(_first_present(adv, _PRICE_KEYS) or _first_present(item, _PRICE_KEYS))
        min_fiat = _to_float(_first_present(adv, _MIN_KEYS) or _first_present(item, _MIN_KEYS))
        max_fiat = _to_float(_first_present(adv, _MAX_KEYS) or _first_present(item, _MAX_KEYS))
        if price is None or min_fiat is None or max_fiat is None:
            continue

        is_merchant_raw = _first_present(advertiser, _MERCHANT_KEYS) or _first_present(item, _MERCHANT_KEYS)
        is_merchant = bool(is_merchant_raw) if is_merchant_raw is not None else None

        rating_raw = _first_present(advertiser, _RATING_KEYS) or _first_present(item, _RATING_KEYS)
        rating = _to_float(rating_raw)

        advertiser_key_raw = (
            _first_present(advertiser, _ADVERTISER_KEYS) or _first_present(item, _ADVERTISER_KEYS)
        )
        advertiser_key = str(advertiser_key_raw) if advertiser_key_raw is not None else None

        offers.append(
            Offer(
                ts_utc=record.ts_utc,
                fiat=record.fiat,
                side=record.side,
                price_fiat_per_usdt=price,
                min_fiat=min_fiat,
                max_fiat=max_fiat,
                payment_methods=_extract_payment_methods(item),
                is_merchant=is_merchant,
                rating=rating,
                advertiser_key=advertiser_key,
                market=record.market,
                page=record.page,
            )
        )

    return offers


def process_day(cfg: AppConfig, *, day: str) -> Path:
    data_dir = Path(cfg.app.data_dir)
    offers: list[dict[str, Any]] = []

    for record in iter_raw_records(data_dir, day=day):
        for offer in parse_raw_fetch(record):
            offers.append(offer.model_dump())

    out_dir = data_dir / "processed" / "offers"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{day}.parquet"

    if not offers:
        # Write an empty file with a minimal schema for downstream code.
        df = pl.DataFrame(
            schema={
                "ts_utc": pl.Datetime(time_unit="us", time_zone="UTC"),
                "asset": pl.Utf8,
                "fiat": pl.Utf8,
                "side": pl.Utf8,
                "price_fiat_per_usdt": pl.Float64,
                "min_fiat": pl.Float64,
                "max_fiat": pl.Float64,
                "payment_methods": pl.List(pl.Utf8),
                "is_merchant": pl.Boolean,
                "rating": pl.Float64,
                "advertiser_key": pl.Utf8,
                "market": pl.Utf8,
                "page": pl.Int64,
            }
        )
    else:
        df = pl.DataFrame(offers)

    df.write_parquet(out_path)
    return out_path
