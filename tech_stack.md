# Tech stack (proposed) — Bybit P2P Analytics MVP

This file proposes a pragmatic stack for a **personal, local-first** MVP that:
- scrapes public Bybit P2P offers every ~30s,
- stores raw data for reprocessing,
- computes “best executable” prices and time-of-day patterns,
- serves a small dashboard for exploration.

## Guiding constraints

- **Local-first**: runs on your laptop (macOS) with minimal ops.
- **Reproducible**: raw data preserved; metrics can be recomputed.
- **Scraper-resilient**: start with JSON endpoints; have an HTML/headless fallback.
- **Fast iteration**: strong Python ecosystem for data + quick UI.

## MVP stack (recommended)

### Language & tooling

- **Python 3.12+**
- **uv** for dependency management + virtualenv + running tools (fast, reproducible)
- **ruff** (lint + format)
- **pytest** (tests)
- Optional: **pyright** (type checking) if you want stronger typing discipline

### Data collection (scraping)

Preferred path (no browser):
- **httpx** (HTTP client; supports async)
- **tenacity** (retries with backoff/jitter)

Fallback paths (if JSON endpoints become unavailable):
- **selectolax** or **lxml** for HTML parsing (if content is server-rendered)
- **Playwright** for headless scraping (if content is client-rendered / protected)

Anti-breakage basics:
- store full raw responses + request params,
- version your parsers (`parse_version`) to handle schema drift.

### Data model & parsing

- **pydantic** for normalized models (`Offer`, `RawFetch`, etc.)
- Simple normalization layer (payment method mapping, merchant/rating parsing, etc.)

### Storage

Raw (append-only, easy to reprocess):
- **JSONL + gzip** on filesystem: `data/raw/YYYY-MM-DD/{market_key}.jsonl.gz`

Processed (analytics-friendly):
- **Parquet** via **pyarrow**: `data/processed/offers/*.parquet` (partition by date/fiat/side)

Query/analytics engine:
- **DuckDB** (local OLAP; great with Parquet; powers dashboard queries)

### Data processing

- **polars** (fast columnar transformations) *or* **pandas** (if you prefer simplicity)
- **duckdb** Python client for aggregations and joins

### Dashboard (UI)

- **Streamlit** for a local dashboard (filters, tables, quick charts)
- Charts:
  - **plotly** (interactive time series / heatmaps), or
  - **altair** (clean declarative charts)

### Scheduling / running

For MVP:
- one long-running process: `collect` loop (async) + periodic flush to disk
- a separate `process` job (manual or daily)

Optional lightweight scheduler:
- **APScheduler** (if you want “run every 30s” without relying on OS cron)

### Configuration & secrets

- `.env` + **python-dotenv**
- `config.yaml` (or TOML) for defaults (timezone, markets, pages, thresholds)

### Logging

- standard `logging` + JSON formatting (or **structlog** if you prefer structured logs)

## Repo layout (suggested)

```
.
├─ src/
│  ├─ collector/        # fetch + raw persistence
│  ├─ parser/           # raw -> Offer normalization
│  ├─ metrics/          # best_* and liquidity calculations
│  ├─ dashboard/        # streamlit app
│  └─ common/           # config, logging, models
├─ data/
│  ├─ raw/
│  └─ processed/
├─ tests/
└─ project_spec.md
```

## “Scale later” options (not for MVP)

- If you want multi-user / hosted:
  - API: **FastAPI**
  - DB: **Postgres** (Timescale optional), object storage for raw
  - Orchestration: **Prefect** / **Dagster**
  - Frontend: **Next.js** + charting

## Decisions (confirmed)

1) **Stable JSON endpoint (no login):** yes — can be captured from Chrome DevTools (MVP uses this as the primary source).
2) **`available_usdt` availability:** unclear at the listing level; assume **not available** in MVP and rely on `max_fiat` as a capacity proxy (upgrade later if we add per-offer detail fetch).
3) **Product focus:** start with **separate legs** (RUB-buy and VND-sell). “Combo now” can be added later.
