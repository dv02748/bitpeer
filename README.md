# bitpeer

Local-first analytics for Bybit P2P offers (focus: `USDT/RUB` and `USDT/VND`).

Docs:
- `project_spec.md` — MVP spec
- `tech_stack.md` — proposed stack
- `milestones.md` — roadmap

## Quick start

1) Create config from `config.example.toml`.
2) Install deps (recommended):
   - `uv sync --extra dev --extra dashboard`
3) Run:
   - `.venv/bin/bitpeer --help`

Typical flow:
- collect raw data: `.venv/bin/bitpeer collect --config config.toml`
- process one day: `.venv/bin/bitpeer process --config config.toml --day 2026-02-09`
- start dashboard: `.venv/bin/bitpeer dashboard --config config.toml`

## Bybit endpoint notes

- The collector is designed to call the same JSON endpoint your browser calls.
- Do **not** commit cookies/tokens:
  - `config.toml` and `.env` are gitignored.
  - Put unstable/sensitive headers (e.g., `cookie`, `guid`, `riskToken`) into `.env` via the variables in `.env.example`.
