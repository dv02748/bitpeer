from __future__ import annotations

import asyncio
import json
import logging
import math
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential_jitter

from bitpeer.common.config import AppConfig, MarketConfig
from bitpeer.models import RawFetchRecord
from bitpeer.storage.raw import RawStore

log = logging.getLogger(__name__)

_SENSITIVE_HEADERS = {
    "authorization",
    "cookie",
    "x-api-key",
    "x-csrf-token",
    "guid",
    "risktoken",
    "traceparent",
}


def _sanitize_headers(headers: dict[str, str]) -> dict[str, str]:
    return {k: v for k, v in headers.items() if k.lower() not in _SENSITIVE_HEADERS}


def _substitute_placeholders(value: Any, ctx: dict[str, Any]) -> Any:
    if isinstance(value, str):
        try:
            return value.format(**ctx)
        except Exception:
            return value
    if isinstance(value, list):
        return [_substitute_placeholders(v, ctx) for v in value]
    if isinstance(value, dict):
        return {k: _substitute_placeholders(v, ctx) for k, v in value.items()}
    return value


def _build_body(
    template: dict[str, Any], *, fiat: str, side: str, endpoint_side: str, page: int
) -> dict[str, Any]:
    ctx = {"fiat": fiat, "side": side, "endpoint_side": endpoint_side, "page": page}
    return _substitute_placeholders(template, ctx)


@retry(stop=stop_after_attempt(3), wait=wait_exponential_jitter(initial=1, max=10), reraise=True)
async def _request(
    client: httpx.AsyncClient,
    *,
    method: str,
    url: str,
    headers: dict[str, str],
    json_body: dict[str, Any],
) -> httpx.Response:
    if method.upper() == "GET":
        return await client.request(method, url, headers=headers, params=json_body)
    return await client.request(method, url, headers=headers, json=json_body)


async def fetch_market_page(
    client: httpx.AsyncClient, cfg: AppConfig, market: MarketConfig, page: int
) -> RawFetchRecord:
    endpoint = cfg.bybit_p2p_endpoint
    request_headers = dict(endpoint.headers)
    request_body = _build_body(
        endpoint.body_template,
        fiat=market.fiat,
        side=market.side,
        endpoint_side=market.endpoint_side,
        page=page,
    )

    ts = datetime.now(UTC)
    try:
        resp = await _request(
            client,
            method=endpoint.method,
            url=endpoint.url,
            headers=request_headers,
            json_body=request_body,
        )
        text = resp.text
        status = resp.status_code
        err: str | None = None
    except Exception as e:  # noqa: BLE001
        text = None
        status = None
        err = repr(e)

    return RawFetchRecord(
        ts_utc=ts,
        market=market.name,
        fiat=market.fiat,
        side=market.side,
        page=page,
        request_url=endpoint.url,
        request_method=endpoint.method,
        request_headers=_sanitize_headers(request_headers),
        request_body=request_body,
        http_status=status,
        response_text=text,
        error=err,
    )


async def collect_once(cfg: AppConfig, store: RawStore) -> None:
    endpoint = cfg.bybit_p2p_endpoint
    timeout = httpx.Timeout(timeout=endpoint.timeout_seconds)

    async with httpx.AsyncClient(timeout=timeout) as client:
        for market in cfg.markets:
            first = await fetch_market_page(client, cfg, market, page=1)
            _log_and_store(store, first)

            total_pages = _derive_total_pages(first)
            # `max_pages <= 0` means "no manual limit", but still keep a safety cap.
            safety_cap = 200
            if cfg.collector.max_pages > 0:
                pages_to_fetch = min(total_pages, cfg.collector.max_pages, safety_cap)
            else:
                pages_to_fetch = min(total_pages, safety_cap)

            if pages_to_fetch <= 1:
                continue

            tasks: list[asyncio.Task[RawFetchRecord]] = []
            for page in range(2, pages_to_fetch + 1):
                tasks.append(asyncio.create_task(fetch_market_page(client, cfg, market, page)))

            for task in asyncio.as_completed(tasks):
                rec = await task
                _log_and_store(store, rec)


def _derive_total_pages(record: RawFetchRecord) -> int:
    if not record.response_text:
        return 1
    try:
        payload = json.loads(record.response_text)
    except Exception:  # noqa: BLE001
        return 1

    result = payload.get("result") if isinstance(payload, dict) else None
    if not isinstance(result, dict):
        return 1

    count_raw = result.get("count")
    try:
        total_count = int(count_raw)
    except Exception:  # noqa: BLE001
        return 1

    # Request body keeps size as a string in our endpoint template.
    size_raw = record.request_body.get("size", 10)
    try:
        page_size = max(int(size_raw), 1)
    except Exception:  # noqa: BLE001
        page_size = 10

    return max(1, math.ceil(total_count / page_size))


def _log_and_store(store: RawStore, rec: RawFetchRecord) -> None:
    out_path = store.append(rec)
    if rec.error:
        log.warning("fetch failed market=%s page=%s error=%s", rec.market, rec.page, rec.error)
    elif rec.http_status and rec.http_status >= 400:
        log.warning(
            "fetch http error market=%s page=%s status=%s -> %s",
            rec.market,
            rec.page,
            rec.http_status,
            out_path,
        )


async def collect_forever(cfg: AppConfig, *, once: bool = False) -> None:
    store = RawStore(data_dir=Path(cfg.app.data_dir))

    while True:
        started = datetime.now(UTC)
        await collect_once(cfg, store)

        if once:
            return

        elapsed = (datetime.now(UTC) - started).total_seconds()
        sleep_s = max(0.0, cfg.collector.interval_seconds - elapsed)
        await asyncio.sleep(sleep_s)
