from __future__ import annotations

import logging

from outcomes_data.core.cache import CacheManager
from outcomes_data.core.config import Settings
from outcomes_data.core.database import PostgresWriter
from outcomes_data.core.pipeline import BasePipeline
from outcomes_data.data_sources.oversight.extractor import CsvExtractor
from outcomes_data.data_sources.oversight.scraper import OversightSourceScraper
from outcomes_data.data_sources.oversight.transforms import (
    clean_league_table_data,
    clean_metrics_data,
    extract_organisations,
    load_bronze_league_table,
    load_bronze_metrics,
)


class OversightPipeline(BasePipeline):
    """Pipeline for NHS Oversight Framework data.

    Processes:
    1. Metrics data (detailed domain-level performance) → oversight_metrics_raw
    2. League table data (overall scores & rankings) → oversight_league_table_raw
    3. Organisation dimension → dim_organisations
    """

    def __init__(
        self,
        settings: Settings,
        cache_manager: CacheManager,
        db_writer: PostgresWriter,
    ):
        super().__init__(settings, cache_manager, db_writer)

        # Initialize scraper with oversight URL settings
        self.scraper = OversightSourceScraper(
            metrics_acute=settings.oversight_metrics_acute,
            metrics_non_acute=settings.oversight_metrics_non_acute,
            metrics_ambulance=settings.oversight_metrics_ambulance,
            league_table_acute=settings.oversight_league_table_acute,
            league_table_non_acute=settings.oversight_league_table_non_acute,
            league_table_ambulance=settings.oversight_league_table_ambulance,
        )

        # Initialize CSV extractor
        self.extractor = CsvExtractor(timeout_s=settings.http_timeout_s)

    def run(self, **kwargs) -> None:
        """Run the complete Oversight Framework pipeline.

        Steps:
        1. Download and process metrics data (3 CSVs)
        2. Download and process league table data (3 CSVs)
        3. Extract and upsert organisations dimension

        Returns total number of rows upserted across all tables.
        """
        self.logger.info("Starting Oversight Framework pipeline")

        total_upserted = 0

        # Step 1: Process Metrics Data
        metrics_count = self._process_metrics()
        total_upserted += metrics_count

        # Step 2: Process League Table Data
        league_table_count = self._process_league_table()
        total_upserted += league_table_count

        # Step 3: Extract and Upsert Organisations
        # (must happen after league table is processed)
        org_count = self._process_organisations()
        total_upserted += org_count

        self.logger.info(
            f"Completed Oversight Framework pipeline "
            f"(metrics={metrics_count}, league_table={league_table_count}, orgs={org_count})"
        )

    def _process_metrics(self) -> int:
        """Process metrics data through Bronze → Silver → Database.

        Returns:
            Number of rows upserted to oversight_metrics_raw
        """
        self.logger.info("Processing metrics data...")

        # Get URLs for all trust types (acute, non-acute, ambulance)
        metrics_urls = self.scraper.get_metrics_urls()

        # Download and combine CSVs
        raw_df = self.extractor.download_and_combine(metrics_urls)

        if raw_df.empty:
            self.logger.warning("No metrics data downloaded")
            return 0

        # Bronze: Normalize columns
        bronze_df = load_bronze_metrics(raw_df)
        self.logger.info(f"Bronze metrics: {len(bronze_df)} rows")

        # Silver: Clean and validate
        silver_df = clean_metrics_data(bronze_df)
        self.logger.info(f"Silver metrics: {len(silver_df)} rows")

        # Database: Upsert
        records = silver_df.to_dict(orient="records")
        upserted = self.db.upsert(
            table_name="oversight_metrics_raw",
            records=records,
            p_keys=["org_code", "metric_id", "reporting_date"],
        )

        self.logger.info(f"Upserted {upserted} metrics rows")
        return upserted

    def _process_league_table(self) -> int:
        """Process league table data through Bronze → Silver → Database.

        Returns:
            Number of rows upserted to oversight_league_table_raw
        """
        self.logger.info("Processing league table data...")

        # Get URLs for all trust types
        league_table_urls = self.scraper.get_league_table_urls()

        # Download and combine CSVs
        raw_df = self.extractor.download_and_combine(league_table_urls)

        if raw_df.empty:
            self.logger.warning("No league table data downloaded")
            return 0

        # Bronze: Normalize columns
        bronze_df = load_bronze_league_table(raw_df)
        self.logger.info(f"Bronze league table: {len(bronze_df)} rows")

        # Silver: Clean and validate
        silver_df = clean_league_table_data(bronze_df)
        self.logger.info(f"Silver league table: {len(silver_df)} rows")

        # Store for organisation extraction
        self._league_table_silver = silver_df

        # Database: Upsert
        records = silver_df.to_dict(orient="records")
        upserted = self.db.upsert(
            table_name="oversight_league_table_raw",
            records=records,
            p_keys=["org_code", "reporting_date"],
        )

        self.logger.info(f"Upserted {upserted} league table rows")
        return upserted

    def _process_organisations(self) -> int:
        """Extract organisations from league table and upsert to dim_organisations.

        This must be called after _process_league_table() has stored the silver data.

        Returns:
            Number of organisations upserted to dim_organisations
        """
        self.logger.info("Extracting organisations dimension...")

        if not hasattr(self, '_league_table_silver'):
            self.logger.error(
                "League table data not available. "
                "Call _process_league_table() first."
            )
            return 0

        # Extract unique organisations from league table
        org_df = extract_organisations(self._league_table_silver)

        if org_df.empty:
            self.logger.warning("No organisations extracted")
            return 0

        # Database: Upsert
        records = org_df.to_dict(orient="records")
        upserted = self.db.upsert(
            table_name="dim_organisations",
            records=records,
            p_keys=["org_code"],
        )

        self.logger.info(f"Upserted {upserted} organisations")
        return upserted
