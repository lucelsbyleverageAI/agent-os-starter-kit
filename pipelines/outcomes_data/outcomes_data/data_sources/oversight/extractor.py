from __future__ import annotations

import io
import logging
from dataclasses import dataclass
from typing import List

import pandas as pd

from outcomes_data.utils.http import build_retrying_session


logger = logging.getLogger(__name__)


@dataclass
class CsvData:
    """Container for downloaded CSV data."""

    url: str
    dataframe: pd.DataFrame


class CsvExtractor:
    """Extractor for downloading and combining CSV files from multiple URLs.

    Unlike RTT which extracts from ZIP files, Oversight Framework provides
    direct CSV downloads that can be combined into a single DataFrame.
    """

    def __init__(self, timeout_s: int = 60):
        self.timeout_s = timeout_s
        self.session = build_retrying_session()

    def download_csv(self, url: str) -> pd.DataFrame | None:
        """Download a single CSV file from URL and return as DataFrame.

        Args:
            url: URL to CSV file

        Returns:
            DataFrame if successful, None if download failed
        """
        try:
            logger.info(f"Downloading CSV from {url}")
            response = self.session.get(url, timeout=self.timeout_s)
            response.raise_for_status()

            # Read CSV from response text using StringIO
            csv_data = io.StringIO(response.text)
            df = pd.read_csv(csv_data)

            logger.info(f"Downloaded {len(df)} rows from {url}")
            return df

        except Exception as e:
            logger.error(f"Failed to download {url}: {e}")
            return None

    def download_and_combine(self, urls: List[str]) -> pd.DataFrame:
        """Download multiple CSV files and combine into single DataFrame.

        Args:
            urls: List of CSV URLs to download

        Returns:
            Combined DataFrame with all rows from successful downloads
        """
        dataframes = []

        for url in urls:
            df = self.download_csv(url)
            if df is not None:
                dataframes.append(df)

        if not dataframes:
            logger.warning("No CSV files were successfully downloaded")
            return pd.DataFrame()

        # Combine all dataframes
        combined = pd.concat(dataframes, ignore_index=True)
        logger.info(f"Combined {len(dataframes)} CSVs into {len(combined)} total rows")

        return combined
