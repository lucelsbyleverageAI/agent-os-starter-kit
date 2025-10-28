from __future__ import annotations

from dataclasses import dataclass
from typing import List


@dataclass
class OversightURLs:
    """Container for NHS Oversight Framework CSV URLs."""

    metrics_acute: str
    metrics_non_acute: str
    metrics_ambulance: str
    league_table_acute: str
    league_table_non_acute: str
    league_table_ambulance: str

    def get_metrics_urls(self) -> List[str]:
        """Return list of URLs for metrics data (all trust types)."""
        return [
            self.metrics_acute,
            self.metrics_non_acute,
            self.metrics_ambulance,
        ]

    def get_league_table_urls(self) -> List[str]:
        """Return list of URLs for league table data (all trust types)."""
        return [
            self.league_table_acute,
            self.league_table_non_acute,
            self.league_table_ambulance,
        ]


class OversightSourceScraper:
    """Scraper for NHS Oversight Framework CSV data sources.

    Unlike RTT which dynamically discovers periods, Oversight Framework
    URLs are date-specific and need to be configured/updated manually.
    """

    def __init__(
        self,
        metrics_acute: str,
        metrics_non_acute: str,
        metrics_ambulance: str,
        league_table_acute: str,
        league_table_non_acute: str,
        league_table_ambulance: str,
    ):
        self.urls = OversightURLs(
            metrics_acute=metrics_acute,
            metrics_non_acute=metrics_non_acute,
            metrics_ambulance=metrics_ambulance,
            league_table_acute=league_table_acute,
            league_table_non_acute=league_table_non_acute,
            league_table_ambulance=league_table_ambulance,
        )

    def get_metrics_urls(self) -> List[str]:
        """Get all metrics data URLs (acute, non-acute, ambulance)."""
        return self.urls.get_metrics_urls()

    def get_league_table_urls(self) -> List[str]:
        """Get all league table URLs (acute, non-acute, ambulance)."""
        return self.urls.get_league_table_urls()
