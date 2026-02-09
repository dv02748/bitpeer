from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import polars as pl


@dataclass(frozen=True)
class UiState:
    data_dir: Path


def _default_data_dir() -> Path:
    return Path("data")


def _list_days(data_dir: Path) -> list[str]:
    offers_dir = data_dir / "processed" / "offers"
    if not offers_dir.exists():
        return []
    return sorted([p.stem for p in offers_dir.glob("*.parquet")])


def _load_offers(data_dir: Path, *, day: str) -> pl.DataFrame:
    path = data_dir / "processed" / "offers" / f"{day}.parquet"
    return pl.read_parquet(path)


def _as_number(v: Optional[float], *, default: float) -> float:
    try:
        return float(v) if v is not None else default
    except Exception:
        return default


def main() -> None:
    import streamlit as st

    st.set_page_config(page_title="bitpeer — Bybit P2P", layout="wide")

    data_dir = st.sidebar.text_input("Data dir", value=str(_default_data_dir()))
    state = UiState(data_dir=Path(data_dir))

    days = _list_days(state.data_dir)
    if not days:
        st.info(
            "No processed data found. Run `bitpeer collect` and then `bitpeer process --day YYYY-MM-DD`."
        )
        return

    day = st.sidebar.selectbox("Day (UTC)", options=days, index=len(days) - 1)
    df = _load_offers(state.data_dir, day=day)

    st.sidebar.markdown("### Inputs")
    buy_amount_rub = st.sidebar.number_input("buy_amount_rub", min_value=1.0, value=50_000.0, step=1000.0)
    sell_amount_usdt = st.sidebar.number_input("sell_amount_usdt", min_value=1.0, value=500.0, step=10.0)
    merchant_only = st.sidebar.checkbox("merchant_only", value=False)
    min_rating = st.sidebar.number_input("min_rating", min_value=0.0, value=0.0, step=0.1)

    def payment_filter_expr(selected: list[str]) -> pl.Expr:
        if not selected:
            return pl.lit(True)
        # Any overlap between offer.payment_methods and selected list.
        return pl.col("payment_methods").list.eval(pl.element().is_in(selected)).list.any()

    st.sidebar.markdown("### Payment filters")
    rub_methods_all = (
        df.filter(pl.col("fiat") == "RUB")
        .select(pl.col("payment_methods").explode())
        .drop_nulls()
        .unique()
        .sort("payment_methods")
        .to_series()
        .to_list()
    )
    vnd_methods_all = (
        df.filter(pl.col("fiat") == "VND")
        .select(pl.col("payment_methods").explode())
        .drop_nulls()
        .unique()
        .sort("payment_methods")
        .to_series()
        .to_list()
    )
    rub_methods = st.sidebar.multiselect("RUB leg methods", options=rub_methods_all, default=[])
    vnd_methods = st.sidebar.multiselect("VND leg methods", options=vnd_methods_all, default=[])

    base = df
    if merchant_only:
        base = base.filter(pl.col("is_merchant") == True)  # noqa: E712
    if min_rating > 0:
        base = base.filter(pl.col("rating").is_null() | (pl.col("rating") >= min_rating))

    col_buy, col_sell = st.columns(2)

    with col_buy:
        st.subheader("Buy USDT with RUB (fiat=RUB, side=SELL)")
        leg = base.filter((pl.col("fiat") == "RUB") & (pl.col("side") == "SELL"))
        leg = leg.filter((pl.col("min_fiat") <= buy_amount_rub) & (buy_amount_rub <= pl.col("max_fiat")))
        leg = leg.filter(payment_filter_expr(rub_methods))

        if leg.is_empty():
            st.warning("No executable offers for current filters/amount.")
        else:
            latest_ts = leg.select(pl.col("ts_utc").max()).item()
            snap = leg.filter(pl.col("ts_utc") == latest_ts)
            best = snap.sort("price_fiat_per_usdt").head(1)
            st.metric("best_rub_per_usdt (single)", f"{best['price_fiat_per_usdt'][0]:.4f}")
            st.caption(f"snapshot ts_utc: {latest_ts}")
            st.dataframe(snap.sort("price_fiat_per_usdt").head(20).to_pandas(), use_container_width=True)

    with col_sell:
        st.subheader("Sell USDT for VND (fiat=VND, side=BUY)")
        leg = base.filter((pl.col("fiat") == "VND") & (pl.col("side") == "BUY"))
        fiat_amount = sell_amount_usdt * pl.col("price_fiat_per_usdt")
        leg = leg.filter((pl.col("min_fiat") <= fiat_amount) & (fiat_amount <= pl.col("max_fiat")))
        leg = leg.filter(payment_filter_expr(vnd_methods))

        if leg.is_empty():
            st.warning("No executable offers for current filters/amount.")
        else:
            latest_ts = leg.select(pl.col("ts_utc").max()).item()
            snap = leg.filter(pl.col("ts_utc") == latest_ts)
            best = snap.sort("price_fiat_per_usdt", descending=True).head(1)
            st.metric("best_vnd_per_usdt (single)", f"{best['price_fiat_per_usdt'][0]:.4f}")
            st.caption(f"snapshot ts_utc: {latest_ts}")
            st.dataframe(
                snap.sort("price_fiat_per_usdt", descending=True).head(20).to_pandas(),
                use_container_width=True,
            )

    st.divider()
    st.subheader("History (best single per snapshot)")

    hist_cols = st.columns(2)
    with hist_cols[0]:
        leg = base.filter((pl.col("fiat") == "RUB") & (pl.col("side") == "SELL"))
        leg = leg.filter((pl.col("min_fiat") <= buy_amount_rub) & (buy_amount_rub <= pl.col("max_fiat")))
        leg = leg.filter(payment_filter_expr(rub_methods))
        if not leg.is_empty():
            ts = (
                leg.group_by("ts_utc")
                .agg(pl.col("price_fiat_per_usdt").min().alias("best_rub_per_usdt"))
                .sort("ts_utc")
            )
            st.line_chart(ts.to_pandas().set_index("ts_utc"))

    with hist_cols[1]:
        leg = base.filter((pl.col("fiat") == "VND") & (pl.col("side") == "BUY"))
        fiat_amount = sell_amount_usdt * pl.col("price_fiat_per_usdt")
        leg = leg.filter((pl.col("min_fiat") <= fiat_amount) & (fiat_amount <= pl.col("max_fiat")))
        leg = leg.filter(payment_filter_expr(vnd_methods))
        if not leg.is_empty():
            ts = (
                leg.group_by("ts_utc")
                .agg(pl.col("price_fiat_per_usdt").max().alias("best_vnd_per_usdt"))
                .sort("ts_utc")
            )
            st.line_chart(ts.to_pandas().set_index("ts_utc"))


if __name__ == "__main__":
    main()

