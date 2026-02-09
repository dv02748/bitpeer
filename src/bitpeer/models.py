from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class Offer(BaseModel):
    ts_utc: datetime
    asset: str = "USDT"
    fiat: str
    side: Literal["BUY", "SELL"]

    price_fiat_per_usdt: float
    min_fiat: float
    max_fiat: float

    payment_methods: list[str] = Field(default_factory=list)
    is_merchant: Optional[bool] = None
    rating: Optional[float] = None
    advertiser_key: Optional[str] = None

    market: Optional[str] = None
    page: Optional[int] = None


class RawFetchRecord(BaseModel):
    format_version: Literal["rawfetch-v1"] = "rawfetch-v1"
    ts_utc: datetime

    market: str
    fiat: str
    side: Literal["BUY", "SELL"]
    page: int

    request_url: str
    request_method: Literal["GET", "POST"]
    request_headers: dict[str, str] = Field(default_factory=dict)
    request_body: dict[str, Any] = Field(default_factory=dict)

    http_status: Optional[int] = None
    response_text: Optional[str] = None
    error: Optional[str] = None

