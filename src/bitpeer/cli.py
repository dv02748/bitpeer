from __future__ import annotations

from pathlib import Path
from typing import Annotated, Optional

import typer

import asyncio

from bitpeer.collector.bybit_p2p import collect_forever
from bitpeer.common.config import AppConfig, load_config
from bitpeer.common.logging import configure_logging
from bitpeer.parser.bybit_p2p import process_day

app = typer.Typer(add_completion=False)


@app.callback()
def _main(
    ctx: typer.Context,
    config: Annotated[Optional[Path], typer.Option("--config", exists=True, dir_okay=False)] = None,
    verbose: Annotated[bool, typer.Option("--verbose")] = False,
) -> None:
    """
    Bybit P2P analytics (local-first).
    """

    configure_logging(verbose=verbose)
    ctx.obj = {"config": config}


@app.command()
def doctor(
    config: Annotated[Optional[Path], typer.Option("--config", exists=True, dir_okay=False)] = None,
) -> None:
    """
    Print resolved config and basic environment checks.
    """

    cfg: AppConfig = load_config(config)
    typer.echo(cfg.model_dump_json(indent=2))


@app.command()
def collect(
    config: Annotated[Optional[Path], typer.Option("--config", exists=True, dir_okay=False)] = None,
    once: Annotated[bool, typer.Option("--once")] = False,
) -> None:
    """
    Collect raw P2P offers and store them under `data/raw/`.
    """

    cfg: AppConfig = load_config(config)
    asyncio.run(collect_forever(cfg, once=once))


@app.command()
def process(
    day: Annotated[str, typer.Option("--day", help="UTC day in YYYY-MM-DD format")],
    config: Annotated[Optional[Path], typer.Option("--config", exists=True, dir_okay=False)] = None,
) -> None:
    """
    Parse raw snapshots into a processed offers parquet for a given day.
    """

    cfg: AppConfig = load_config(config)
    out = process_day(cfg, day=day)
    typer.echo(str(out))


@app.command()
def dashboard(
    config: Annotated[Optional[Path], typer.Option("--config", exists=True, dir_okay=False)] = None,
    port: Annotated[int, typer.Option("--port")] = 8501,
) -> None:
    """
    Start the local Streamlit dashboard.
    """

    _ = load_config(config)  # validate config early

    try:
        import bitpeer.dashboard.app as dashboard_app
    except Exception as e:  # noqa: BLE001
        typer.echo(f"Failed to import dashboard: {e}")
        raise typer.Exit(1) from e

    import subprocess

    try:
        subprocess.run(
            ["streamlit", "run", dashboard_app.__file__, "--server.port", str(port)],
            check=True,
        )
    except FileNotFoundError as e:
        typer.echo("streamlit is not installed. Install dashboard deps: `uv sync --extra dashboard`")
        raise typer.Exit(1) from e


if __name__ == "__main__":
    app()
