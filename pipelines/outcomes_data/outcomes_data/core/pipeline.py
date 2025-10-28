from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

from outcomes_data.core.cache import CacheManager
from outcomes_data.core.config import Settings
from outcomes_data.core.database import PostgresWriter


class BasePipeline(ABC):
    """
    Abstract base class for all data source pipelines.

    Provides common infrastructure (cache, database, config, logging)
    while allowing each pipeline to implement its own specific logic.
    """

    def __init__(self, settings: Settings, cache_manager: CacheManager, db_writer: PostgresWriter):
        self.settings = settings
        self.cache = cache_manager
        self.db = db_writer
        self.logger = logging.getLogger(self.__class__.__name__)

    @abstractmethod
    def run(self, **kwargs) -> None:
        """
        Run the pipeline with specified parameters.

        Each pipeline implements its own run logic based on its data source requirements.
        """
        pass

    def log_start(self, operation: str, **kwargs) -> None:
        """Log the start of a pipeline operation."""
        params_str = ", ".join(f"{k}={v}" for k, v in kwargs.items())
        self.logger.info(f"Starting {operation} ({params_str})")

    def log_complete(self, operation: str, **kwargs) -> None:
        """Log the completion of a pipeline operation."""
        params_str = ", ".join(f"{k}={v}" for k, v in kwargs.items())
        self.logger.info(f"Completed {operation} ({params_str})")

    def log_error(self, operation: str, error: Exception, **kwargs) -> None:
        """Log an error during a pipeline operation."""
        params_str = ", ".join(f"{k}={v}" for k, v in kwargs.items())
        self.logger.error(f"Failed {operation} ({params_str}): {error}")
