from __future__ import annotations

import os
import json
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Optional

from dotenv import load_dotenv
from pydantic import BaseModel, Field


class BybitP2PEndpoint(BaseModel):
    url: str
    method: Literal["GET", "POST"] = "POST"
    timeout_seconds: int = 20
    headers: dict[str, str] = Field(default_factory=dict)
    body_template: dict[str, Any] = Field(default_factory=dict)


class MarketConfig(BaseModel):
    name: str
    fiat: str
    side: Literal["BUY", "SELL"]
    endpoint_side: str


class CollectorConfig(BaseModel):
    interval_seconds: int = 30
    max_pages: int = 5
    min_offers_after_filter: int = 30


class AppSection(BaseModel):
    timezone: str = "Asia/Ho_Chi_Minh"
    data_dir: str = "data"


class AppConfig(BaseModel):
    app: AppSection = Field(default_factory=AppSection)
    collector: CollectorConfig = Field(default_factory=CollectorConfig)
    bybit_p2p_endpoint: BybitP2PEndpoint
    markets: list[MarketConfig]


@dataclass(frozen=True)
class ConfigPaths:
    config_file: Path


def _default_config_path() -> Path:
    return Path("config.toml")


def load_config(path: Optional[Path]) -> AppConfig:
    load_dotenv(override=False)
    config_path = path or _default_config_path()
    if not config_path.exists():
        raise FileNotFoundError(
            f"Missing config file: {config_path}. Copy config.example.toml to config.toml and edit it."
        )

    raw = tomllib.loads(config_path.read_text(encoding="utf-8"))

    # Allow overriding endpoint URL via env var for quick experiments.
    endpoint_url = os.getenv("BYBIT_P2P_URL")
    if endpoint_url:
        raw.setdefault("bybit_p2p_endpoint", {})
        raw["bybit_p2p_endpoint"]["url"] = endpoint_url

    # Allow adding/updating headers via env to avoid committing sensitive values to config.
    endpoint_headers = raw.setdefault("bybit_p2p_endpoint", {}).setdefault("headers", {})
    headers_json = os.getenv("BYBIT_P2P_HEADERS_JSON")
    if headers_json:
        try:
            parsed = json.loads(headers_json)
            if isinstance(parsed, dict):
                for k, v in parsed.items():
                    if v is None:
                        continue
                    endpoint_headers[str(k)] = str(v)
        except Exception:  # noqa: BLE001
            # Config validation will still run; ignore env errors here.
            pass

    cookie = os.getenv("BYBIT_P2P_COOKIE")
    if cookie:
        endpoint_headers["Cookie"] = cookie
    guid = os.getenv("BYBIT_P2P_GUID")
    if guid:
        endpoint_headers["guid"] = guid
    risk_token = os.getenv("BYBIT_P2P_RISKTOKEN")
    if risk_token:
        endpoint_headers["riskToken"] = risk_token

    return AppConfig.model_validate(raw)
