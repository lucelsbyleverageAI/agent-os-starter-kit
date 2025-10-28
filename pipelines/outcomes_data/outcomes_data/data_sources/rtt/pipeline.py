from __future__ import annotations

from pathlib import Path

from outcomes_data.core.cache import CacheManager
from outcomes_data.core.config import Settings
from outcomes_data.core.database import PostgresWriter
from outcomes_data.core.pipeline import BasePipeline
from outcomes_data.data_sources.rtt.extractor import ZipCsvExtractor
from outcomes_data.data_sources.rtt.scraper import RttSourceScraper
from outcomes_data.data_sources.rtt.transforms import build_silver_from_bronze, compute_gold_metrics, load_bronze_long


class RTTPipeline(BasePipeline):
    """Pipeline for RTT (Referral to Treatment) waiting times data."""

    def __init__(self, settings: Settings, cache_manager: CacheManager, db_writer: PostgresWriter):
        super().__init__(settings, cache_manager, db_writer)
        self.scraper = RttSourceScraper(top_url=settings.rtt_top_url, timeout_s=settings.http_timeout_s)
        self.extractor = ZipCsvExtractor(cache_root=settings.cache_root / "rtt")

    def discover_periods(self) -> list:
        """Discover all available RTT periods from NHS England."""
        return self.scraper.build_period_url_list()

    def process_period(self, period_url) -> int:
        """Process a single RTT period through Bronze→Silver→Gold→Database."""
        self.logger.info(f"Processing period: {period_url.period} -> {period_url.url}")

        # Download ZIP (with caching)
        rec = self.cache.download_zip(period_url.url)

        # Extract CSV from ZIP
        extracted = self.extractor.extract(rec.path)

        # Bronze: Load and normalize
        df_long = load_bronze_long(extracted.csv_path, extracted.header_idx, extracted.encoding)
        self.logger.info(f"Bronze long-form for {period_url.period}: rows={len(df_long)}")

        # Silver: Aggregate by entity level
        silver = build_silver_from_bronze(df_long)
        self.logger.info(f"Silver aggregates for {period_url.period}: rows={len(silver)}")

        # Gold: Compute derived metrics
        gold = compute_gold_metrics(silver)
        self.logger.info(f"Gold metrics for {period_url.period}: rows={len(gold)}")

        # Write to database
        records = gold.to_dict(orient="records")
        inserted = self.db.upsert_gold(records)
        self.logger.info(f"Upserted gold rows for {period_url.period}: {inserted}")

        return inserted

    def run(self, command: str = "refresh_latest", start: str | None = None, period: str | None = None) -> None:
        """
        Run the RTT pipeline with specified command.

        Args:
            command: One of "refresh_latest", "backfill", "rebuild_month"
            start: Start period for backfill (YYYY-MM format)
            period: Specific period for rebuild_month (YYYY-MM format)
        """
        self.log_start("RTT pipeline", command=command)

        # Ensure schema and tables exist
        self.db.ensure_schema_and_tables()

        # Discover all available periods
        all_period_urls = self.discover_periods()
        if not all_period_urls:
            self.logger.warning("No RTT periods discovered")
            return

        self.logger.info(f"Discovered {len(all_period_urls)} RTT periods")

        # Determine which periods to process based on command
        if command == "refresh_latest":
            periods_to_process = [all_period_urls[-1]]
            self.logger.info(f"Processing latest period: {periods_to_process[0].period}")

        elif command == "backfill":
            start_period = start or "2015-10"
            periods_to_process = [p for p in all_period_urls if p.period >= start_period]
            self.logger.info(f"Backfilling from {start_period}: {len(periods_to_process)} periods")

        elif command == "rebuild_month":
            if not period:
                raise ValueError("rebuild_month requires a period argument (YYYY-MM)")
            periods_to_process = [p for p in all_period_urls if p.period == period]
            if not periods_to_process:
                self.logger.warning(f"Period {period} not found in discovered URLs")
                return
            self.logger.info(f"Rebuilding period {period}")

        else:
            raise ValueError(f"Unknown command: {command}")

        # Process each period
        total_inserted = 0
        for period_url in periods_to_process:
            try:
                inserted = self.process_period(period_url)
                total_inserted += inserted
            except Exception as e:
                self.log_error(f"RTT period {period_url.period}", e)
                # Continue processing other periods
                continue

        self.log_complete("RTT pipeline", total_upserted=total_inserted)
