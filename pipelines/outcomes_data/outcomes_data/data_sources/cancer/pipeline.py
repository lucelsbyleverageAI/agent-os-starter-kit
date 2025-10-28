from __future__ import annotations

from outcomes_data.core.cache import CacheManager
from outcomes_data.core.config import Settings
from outcomes_data.core.database import PostgresWriter
from outcomes_data.core.pipeline import BasePipeline
from outcomes_data.data_sources.cancer.extractor import CsvExtractor
from outcomes_data.data_sources.cancer.scraper import CancerSourceScraper
from outcomes_data.data_sources.cancer.transforms import (
    build_silver,
    build_target_gold,
    load_bronze,
)


class CancerPipeline(BasePipeline):
    """Pipeline for NHS Cancer Waiting Times data.

    Processes three key metrics:
    - Metric 3: 28-day faster diagnosis standard
    - Metric 5: 31-day decision to treat to treatment standard
    - Metric 8: 62-day referral to treatment standard
    """

    def __init__(self, settings: Settings, cache_manager: CacheManager, db_writer: PostgresWriter):
        super().__init__(settings, cache_manager, db_writer)
        self.scraper = CancerSourceScraper(
            top_url=settings.cancer_top_url,
            timeout_s=settings.http_timeout_s
        )
        self.extractor = CsvExtractor(cache_root=settings.cache_root / "cancer")

    def discover_metrics(self) -> list:
        """Discover all available cancer metric CSV files from NHS England."""
        return self.scraper.build_period_url_list()

    def process_metric(self, metric_url) -> int:
        """Process a single cancer metric through Bronze→Silver→Gold→Database."""
        self.logger.info(
            f"Processing {metric_url.period} metric {metric_url.metric} "
            f"({'final' if metric_url.is_final else 'provisional'})"
        )

        # Download CSV (with caching)
        rec = self.cache.download_csv(metric_url.url)

        # Extract CSV with header detection
        extracted = self.extractor.extract(rec.path)

        # Bronze: Load raw CSV with multi-level headers
        bronze_df = load_bronze(
            extracted.csv_path,
            extracted.header_idx,
            extracted.encoding
        )
        self.logger.info(
            f"Bronze for {metric_url.period} metric {metric_url.metric}: "
            f"rows={len(bronze_df)}"
        )

        if bronze_df.empty:
            self.logger.warning(
                f"No data in bronze for {metric_url.period} metric {metric_url.metric}"
            )
            return 0

        # Silver: Clean and structure data
        silver_df = build_silver(bronze_df, metric_url.period, metric_url.metric)
        self.logger.info(
            f"Silver for {metric_url.period} metric {metric_url.metric}: "
            f"rows={len(silver_df)}"
        )

        if silver_df.empty:
            self.logger.warning(
                f"No data in silver for {metric_url.period} metric {metric_url.metric}"
            )
            return 0

        # Gold: Produce unified target metrics with referral route breakdown
        gold_df = build_target_gold(silver_df)
        self.logger.info(
            f"Gold for {metric_url.period} metric {metric_url.metric}: "
            f"rows={len(gold_df)}"
        )

        if gold_df.empty:
            self.logger.warning(
                f"No data in gold for {metric_url.period} metric {metric_url.metric}"
            )
            return 0

        # Write to database
        records = gold_df.to_dict(orient="records")
        inserted = self.db.upsert(
            table_name="cancer_target_metrics",
            records=records,
            p_keys=["period", "metric", "org_code", "cancer_type", "referral_route"]
        )
        self.logger.info(
            f"Upserted {inserted} rows for {metric_url.period} metric {metric_url.metric}"
        )

        return inserted

    def run(
        self,
        command: str = "refresh_latest",
        start: str | None = None,
        period: str | None = None
    ) -> None:
        """
        Run the Cancer pipeline with specified command.

        Args:
            command: One of "refresh_latest", "backfill", "rebuild_month"
            start: Start period for backfill (YYYY-MM format)
            period: Specific period for rebuild_month (YYYY-MM format)
        """
        self.log_start("Cancer pipeline", command=command)

        # Ensure schema and tables exist
        self.db.ensure_schema_and_tables()

        # Discover all available metric CSV files
        all_metric_urls = self.discover_metrics()
        if not all_metric_urls:
            self.logger.warning("No cancer metric URLs discovered")
            return

        self.logger.info(
            f"Discovered {len(all_metric_urls)} cancer metric CSV files "
            f"(metrics 3, 5, 8 across periods)"
        )

        # Determine which metrics to process based on command
        if command == "refresh_latest":
            # Get the latest period for each metric (3, 5, 8)
            latest_by_metric = {}
            for metric_url in all_metric_urls:
                key = metric_url.metric
                if key not in latest_by_metric or metric_url.period > latest_by_metric[key].period:
                    latest_by_metric[key] = metric_url

            metrics_to_process = list(latest_by_metric.values())
            self.logger.info(
                f"Processing latest periods: "
                f"{[(m.metric, m.period) for m in metrics_to_process]}"
            )

        elif command == "backfill":
            start_period = start or "2015-10"
            metrics_to_process = [m for m in all_metric_urls if m.period >= start_period]
            self.logger.info(
                f"Backfilling from {start_period}: {len(metrics_to_process)} metric files"
            )

        elif command == "rebuild_month":
            if not period:
                raise ValueError("rebuild_month requires a period argument (YYYY-MM)")
            metrics_to_process = [m for m in all_metric_urls if m.period == period]
            if not metrics_to_process:
                self.logger.warning(f"Period {period} not found in discovered URLs")
                return
            self.logger.info(
                f"Rebuilding period {period}: {len(metrics_to_process)} metric files"
            )

        else:
            raise ValueError(f"Unknown command: {command}")

        # Process each metric file
        total_inserted = 0
        for metric_url in metrics_to_process:
            try:
                inserted = self.process_metric(metric_url)
                total_inserted += inserted
            except Exception as e:
                self.log_error(
                    f"Cancer metric {metric_url.period} metric {metric_url.metric}",
                    e
                )
                # Continue processing other metrics
                continue

        self.log_complete("Cancer pipeline", total_upserted=total_inserted)
