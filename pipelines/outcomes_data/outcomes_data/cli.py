#!/usr/bin/env python3
"""Command-line interface for outcomes_data pipelines."""

import logging
import sys
from pathlib import Path

import typer

from outcomes_data.core.cache import CacheManager
from outcomes_data.core.config import load_settings, test_db_connection
from outcomes_data.core.database import PostgresWriter
from outcomes_data.core.logging import setup_logging
from outcomes_data.data_sources.rtt.pipeline import RTTPipeline
from outcomes_data.data_sources.oversight.pipeline import OversightPipeline
from outcomes_data.data_sources.cancer.pipeline import CancerPipeline
from outcomes_data.data_sources.ods.pipeline import OdsPipeline


app = typer.Typer(help="NHS Outcomes Data Pipeline V2")
rtt_app = typer.Typer(help="RTT (Referral to Treatment) pipeline commands")
app.add_typer(rtt_app, name="rtt")
oversight_app = typer.Typer(help="NHS Oversight Framework pipeline commands")
app.add_typer(oversight_app, name="oversight")
cancer_app = typer.Typer(help="Cancer Waiting Times pipeline commands")
app.add_typer(cancer_app, name="cancer")
ods_app = typer.Typer(help="ODS (Organisation Data Service) pipeline commands")
app.add_typer(ods_app, name="ods")


@app.command()
def test_db():
    """Test database connection."""
    settings = load_settings()
    ok, msg = test_db_connection(settings)
    if ok:
        typer.secho(f"✓ {msg}", fg=typer.colors.GREEN)
    else:
        typer.secho(f"✗ {msg}", fg=typer.colors.RED)
        raise typer.Exit(code=1)


@rtt_app.command()
def refresh_latest(
    cache_root: str = typer.Option(None, help="Override cache directory"),
    log_level: str = typer.Option("INFO", help="Log level (DEBUG, INFO, WARNING, ERROR)"),
):
    """Process the latest RTT period only."""
    settings = load_settings()
    setup_logging(getattr(logging, log_level.upper()))

    if cache_root:
        settings.cache_root = Path(cache_root)

    cache_mgr = CacheManager(settings.cache_root / "rtt")
    db_writer = PostgresWriter(settings.effective_db_url)
    pipeline = RTTPipeline(settings, cache_mgr, db_writer)

    pipeline.run(command="refresh_latest")


@rtt_app.command()
def backfill(
    start: str = typer.Option("2015-10", help="Start period (YYYY-MM)"),
    cache_root: str = typer.Option(None, help="Override cache directory"),
    log_level: str = typer.Option("INFO", help="Log level"),
):
    """Backfill RTT data from a start period to latest."""
    settings = load_settings()
    setup_logging(getattr(logging, log_level.upper()))

    if cache_root:
        settings.cache_root = Path(cache_root)

    cache_mgr = CacheManager(settings.cache_root / "rtt")
    db_writer = PostgresWriter(settings.effective_db_url)
    pipeline = RTTPipeline(settings, cache_mgr, db_writer)

    pipeline.run(command="backfill", start=start)


@rtt_app.command()
def rebuild_month(
    period: str = typer.Argument(..., help="Period to rebuild (YYYY-MM)"),
    cache_root: str = typer.Option(None, help="Override cache directory"),
    log_level: str = typer.Option("INFO", help="Log level"),
):
    """Rebuild a specific RTT month."""
    settings = load_settings()
    setup_logging(getattr(logging, log_level.upper()))

    if cache_root:
        settings.cache_root = Path(cache_root)

    cache_mgr = CacheManager(settings.cache_root / "rtt")
    db_writer = PostgresWriter(settings.effective_db_url)
    pipeline = RTTPipeline(settings, cache_mgr, db_writer)

    pipeline.run(command="rebuild_month", period=period)


@oversight_app.command()
def run(
    log_level: str = typer.Option("INFO", help="Log level (DEBUG, INFO, WARNING, ERROR)"),
):
    """Run the full Oversight Framework pipeline.

    Downloads and processes:
    - Metrics data (3 CSVs: acute, non-acute, ambulance)
    - League table data (3 CSVs)
    - Organisation dimension (extracted from league table)
    """
    settings = load_settings()
    setup_logging(getattr(logging, log_level.upper()))

    cache_mgr = CacheManager(settings.cache_root / "oversight")
    db_writer = PostgresWriter(settings.effective_db_url)
    pipeline = OversightPipeline(settings, cache_mgr, db_writer)

    pipeline.run()


@cancer_app.command()
def refresh_latest(
    cache_root: str = typer.Option(None, help="Override cache directory"),
    log_level: str = typer.Option("INFO", help="Log level (DEBUG, INFO, WARNING, ERROR)"),
):
    """Process the latest cancer waiting times data for all metrics (3, 5, 8)."""
    settings = load_settings()
    setup_logging(getattr(logging, log_level.upper()))

    if cache_root:
        settings.cache_root = Path(cache_root)

    cache_mgr = CacheManager(settings.cache_root / "cancer")
    db_writer = PostgresWriter(settings.effective_db_url)
    pipeline = CancerPipeline(settings, cache_mgr, db_writer)

    pipeline.run(command="refresh_latest")


@cancer_app.command()
def backfill(
    start: str = typer.Option("2015-10", help="Start period (YYYY-MM)"),
    cache_root: str = typer.Option(None, help="Override cache directory"),
    log_level: str = typer.Option("INFO", help="Log level"),
):
    """Backfill cancer waiting times data from a start period to latest."""
    settings = load_settings()
    setup_logging(getattr(logging, log_level.upper()))

    if cache_root:
        settings.cache_root = Path(cache_root)

    cache_mgr = CacheManager(settings.cache_root / "cancer")
    db_writer = PostgresWriter(settings.effective_db_url)
    pipeline = CancerPipeline(settings, cache_mgr, db_writer)

    pipeline.run(command="backfill", start=start)


@cancer_app.command()
def rebuild_month(
    period: str = typer.Argument(..., help="Period to rebuild (YYYY-MM)"),
    cache_root: str = typer.Option(None, help="Override cache directory"),
    log_level: str = typer.Option("INFO", help="Log level"),
):
    """Rebuild a specific cancer waiting times month (all metrics 3, 5, 8)."""
    settings = load_settings()
    setup_logging(getattr(logging, log_level.upper()))

    if cache_root:
        settings.cache_root = Path(cache_root)

    cache_mgr = CacheManager(settings.cache_root / "cancer")
    db_writer = PostgresWriter(settings.effective_db_url)
    pipeline = CancerPipeline(settings, cache_mgr, db_writer)

    pipeline.run(command="rebuild_month", period=period)


@ods_app.command()
def sync(
    role_codes: list[str] = typer.Option(None, "--role-code", help="NHS role codes to fetch (e.g., RO197, RO198)"),
    log_level: str = typer.Option("INFO", help="Log level (DEBUG, INFO, WARNING, ERROR)"),
):
    """Sync organisation data from NHS ODS FHIR API.

    If no role codes are specified, fetches NHS TRUST (RO197) and NHS TRUST SITE (RO198) by default.
    """
    settings = load_settings()
    setup_logging(getattr(logging, log_level.upper()))

    cache_mgr = CacheManager(settings.cache_root / "ods")
    db_writer = PostgresWriter(settings.effective_db_url)
    pipeline = OdsPipeline(settings, cache_mgr, db_writer)

    pipeline.run(role_codes=role_codes)


@app.command()
def run_all(
    start: str = typer.Option(None, help="Start period for backfill (YYYY-MM)"),
    log_level: str = typer.Option("INFO", help="Log level"),
):
    """Run all pipelines (RTT, Cancer, Oversight)."""
    settings = load_settings()
    setup_logging(getattr(logging, log_level.upper()))

    logger = logging.getLogger("run_all")
    logger.info("Running all pipelines...")

    db_writer = PostgresWriter(settings.effective_db_url)

    # RTT
    logger.info("Starting RTT pipeline...")
    cache_mgr_rtt = CacheManager(settings.cache_root / "rtt")
    rtt_pipeline = RTTPipeline(settings, cache_mgr_rtt, db_writer)

    if start:
        rtt_pipeline.run(command="backfill", start=start)
    else:
        rtt_pipeline.run(command="refresh_latest")

    # Cancer
    logger.info("Starting Cancer pipeline...")
    cache_mgr_cancer = CacheManager(settings.cache_root / "cancer")
    cancer_pipeline = CancerPipeline(settings, cache_mgr_cancer, db_writer)

    if start:
        cancer_pipeline.run(command="backfill", start=start)
    else:
        cancer_pipeline.run(command="refresh_latest")

    # Oversight
    logger.info("Starting Oversight Framework pipeline...")
    cache_mgr_oversight = CacheManager(settings.cache_root / "oversight")
    oversight_pipeline = OversightPipeline(settings, cache_mgr_oversight, db_writer)
    oversight_pipeline.run()

    # ODS
    logger.info("Starting ODS pipeline...")
    cache_mgr_ods = CacheManager(settings.cache_root / "ods")
    ods_pipeline = OdsPipeline(settings, cache_mgr_ods, db_writer)
    ods_pipeline.run()


def main():
    """Entry point for the CLI."""
    app()


if __name__ == "__main__":
    main()
