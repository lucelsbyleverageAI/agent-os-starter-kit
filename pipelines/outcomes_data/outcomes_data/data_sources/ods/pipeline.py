from __future__ import annotations

from outcomes_data.core.cache import CacheManager
from outcomes_data.core.config import Settings
from outcomes_data.core.database import PostgresWriter
from outcomes_data.core.pipeline import BasePipeline
from outcomes_data.data_sources.ods.client import OdsClient, OdsSettings, parse_organization


class OdsPipeline(BasePipeline):
    """Pipeline for ODS (Organisation Data Service) data.
    
    Fetches organisation metadata from NHS England FHIR API.
    """

    def __init__(self, settings: Settings, cache_manager: CacheManager, db_writer: PostgresWriter):
        super().__init__(settings, cache_manager, db_writer)
        self.client = OdsClient(
            OdsSettings(
                base_url=settings.ods_base_url,
                api_key=settings.ods_api_key
            )
        )

    def fetch_and_process_role(self, role_code: str, page_size: int = 1000) -> int:
        """Fetch organizations by role code and upsert to database."""
        self.logger.info(f"Fetching organizations with role code: {role_code}")
        
        # Fetch organizations in batches
        batch: list[dict] = []
        total_fetched = 0
        total_inserted = 0
        
        for org in self.client.fetch_organizations_by_role(role_code=role_code, count=page_size):
            row = parse_organization(org, matched_role_code=role_code)
            batch.append(row)
            total_fetched += 1
            
            # Upsert in batches of 500
            if len(batch) >= 500:
                inserted = self.db.upsert(
                    table_name="ods_org_current",
                    records=batch,
                    p_keys=["org_code"]
                )
                total_inserted += inserted
                self.logger.info(f"Fetched {total_fetched} orgs, upserted {inserted} in this batch")
                batch.clear()
        
        # Upsert remaining batch
        if batch:
            inserted = self.db.upsert(
                table_name="ods_org_current",
                records=batch,
                p_keys=["org_code"]
            )
            total_inserted += inserted
            self.logger.info(f"Upserted final batch: {inserted} orgs")
        
        self.logger.info(f"Completed fetching {total_fetched} organizations for role {role_code}")
        return total_inserted

    def run(self, role_codes: list[str] | None = None) -> None:
        """
        Run the ODS pipeline to fetch and upsert organisation data.
        
        Args:
            role_codes: List of NHS role codes to fetch (e.g. ['RO197', 'RO198'])
                        If None, fetches common trust types.
        """
        self.log_start("ODS pipeline")
        
        # Ensure schema and tables exist
        self.db.ensure_schema_and_tables()
        
        # Default to common NHS trust types if no role codes specified
        if role_codes is None:
            role_codes = [
                "RO197",  # NHS TRUST
                "RO198",  # NHS TRUST SITE
            ]
        
        self.logger.info(f"Processing {len(role_codes)} role codes: {role_codes}")
        
        total_inserted = 0
        for role_code in role_codes:
            try:
                inserted = self.fetch_and_process_role(role_code)
                total_inserted += inserted
            except Exception as e:
                self.log_error(f"ODS role {role_code}", e)
                # Continue with other role codes
                continue
        
        self.log_complete("ODS pipeline", total_upserted=total_inserted)
