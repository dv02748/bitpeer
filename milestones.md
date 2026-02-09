# Milestones — Bybit P2P Analytics (RUB → USDT → VND)

This roadmap breaks the project into an MVP and three follow-up versions (v1–v3). Each milestone lists what to implement and what “done” means.

## MVP (v0) — Local-first analytics baseline

**Goal:** reliably collect public Bybit P2P offers and answer “is it good right now / when is it usually better”.

**Implement**
- Collector (30s) for `USDT/RUB` and `USDT/VND`, both sides (BUY/SELL), multi-page until post-filter ≥ `M`, with retries/backoff.
- Raw storage (append-only) with `ts_utc`, request params, status, body, `parse_version`.
- Parser → normalized `Offer` rows (payment methods normalized; merchant/rating parsed).
- Core metrics:
  - `best_single_offer_price` (RUB buy leg + VND sell leg) with strict min/max “executability”.
  - `best_split_vwap_price` (greedy; `max_splits`).
  - Optional “combo now”: `effective_vnd_per_rub = vnd_received / buy_amount_rub` when executable.
- Liquidity proxies: near-best liquidity (X%), top stability, offer half-life (basic).
- Dashboard (local): “Now” view + “History” view + “Data quality” view.
- Data quality checks + UI warnings (gaps, empty pages, schema changes).

**Done when**
- Runs locally for 7–14 days with minimal manual babysitting.
- Dashboard shows consistent numbers for a chosen `buy_amount_rub` and filters.
- Heatmap/time-of-day aggregates render from stored history.

## v1 — Hardening + actionable recommendations

**Goal:** make it robust to real-world P2P messiness and provide confident “best windows” with explainability.

**Implement**
- Source hardening:
  - Prefer stable JSON endpoints; add HTML parser fallback; add Playwright fallback (toggle).
  - Better anti-breakage telemetry (error budget; alert in dashboard).
- Better executability model:
  - Support both “buy_amount_rub” and “sell_amount_usdt” cleanly across legs.
  - Smarter split allocator (handles min_fiat constraints; avoids tiny leftover; fallback strategies).
- Recommendation layer:
  - “Best windows” by hour/day with confidence (sample size, dispersion).
  - “Expected improvement vs baseline” and “worst-case regret” summaries.
- Advertiser/offer behavior basics:
  - advertiser keying improvements, price update frequency, persistence metrics.
- Packaging:
  - CLI commands: `collect`, `process`, `dashboard`, `backfill` (from raw).
  - Config file + sane defaults (timezone, filters, pages, thresholds).

**Done when**
- Collector survives endpoint/schema changes with a clear fallback path.
- Recommendations are stable week-to-week and include uncertainty indicators.
- Split pricing behaves sensibly for typical RUB amounts (20k–100k) without manual tweaks.

## v2 — Broader coverage + advanced analytics

**Goal:** expand market coverage and add deeper analysis to reduce false “good deals”.

**Implement**
- Coverage expansion:
  - More fiat/country configurations (parameterized markets; easy to add).
  - Multiple payment method profiles (“strict”, “wide”, custom).
- Risk & reliability scoring (still proxy-based):
  - filter presets based on merchant/rating/other available public signals.
  - “deal quality score” combining price, liquidity, stability, advertiser persistence.
- Better time-series analysis:
  - seasonality decomposition, anomaly detection (“today is unusual”).
  - event tags (weekends/holidays manual tags; later automated).
- Performance/ops:
  - Incremental processing, partition management, compaction.
  - Caching for dashboard queries; faster cold-start.
- Optional notifications:
  - Local notifications / Telegram bot when “combo now” crosses a threshold and is executable.

**Done when**
- Adding a new market is mostly config, not code.
- Dashboard stays fast with months of data.
- Alerts trigger rarely and only when the signal is meaningfully executable.

## v3 — Productization (hosted) + automation

**Goal:** move from “personal tool” to a deployable product (still optional if you stay local).

**Implement**
- Architecture upgrade:
  - API service (FastAPI), background jobs (Prefect/Dagster/Celery), central DB (Postgres).
  - Object storage for raw (S3-compatible) and retention policies.
- Auth + multi-user:
  - user accounts, per-user filter profiles, saved dashboards.
- Real-time UX:
  - websockets / streaming updates for “Now”.
  - shareable links / reports.
- Reliability:
  - monitoring, structured logs, automated recovery, deployment scripts.
- Optional “execution assist” (non-custodial):
  - checklists, trade journal, post-trade outcome capture to validate proxies.
  - (Only if desired) integration hooks; no keys stored by default.

**Done when**
- Deployable on a small server with one command and runs unattended.
- Multiple profiles/users supported with isolation.
- Clear monitoring/alerting for scraper + pipelines.

