"""
Background sync scheduler for LangGraph mirroring.

This service runs periodic sync operations to keep mirrors up-to-date
with external changes in LangGraph (assistants created outside the UI).
"""

import asyncio
import logging
import os
from typing import Optional
from datetime import datetime, timedelta

from langconnect.services.langgraph_sync import LangGraphSyncService
from langconnect.services.langgraph_integration import get_langgraph_service
from langconnect.services.thread_naming_service import ThreadNamingService
from langconnect.database.connection import get_db_pool

log = logging.getLogger(__name__)


class SyncScheduler:
    """Background scheduler for LangGraph sync operations."""

    def __init__(
        self,
        incremental_interval_minutes: int = 2,
        full_sync_interval_minutes: int = 15,
        cleanup_interval_hours: int = 24,
        graph_discovery_interval_minutes: int = 15,
        thread_naming_interval_seconds: int = 30
    ):
        self.incremental_interval = timedelta(minutes=incremental_interval_minutes)
        self.full_sync_interval = timedelta(minutes=full_sync_interval_minutes)
        self.cleanup_interval = timedelta(hours=cleanup_interval_hours)
        self.graph_discovery_interval = timedelta(minutes=graph_discovery_interval_minutes)
        self.thread_naming_interval = timedelta(seconds=thread_naming_interval_seconds)

        self.last_incremental_sync: Optional[datetime] = None
        self.last_full_sync: Optional[datetime] = None
        self.last_cleanup: Optional[datetime] = None
        self.last_graph_discovery: Optional[datetime] = None
        self.last_thread_naming: Optional[datetime] = None

        self.running = False
        self.task: Optional[asyncio.Task] = None

        log.info(f"Sync scheduler initialized: incremental={incremental_interval_minutes}m, full={full_sync_interval_minutes}m, cleanup={cleanup_interval_hours}h, graph_discovery={graph_discovery_interval_minutes}m, thread_naming={thread_naming_interval_seconds}s")
    
    async def start(self):
        """Start the background sync scheduler."""
        if self.running:
            log.warning("Sync scheduler already running")
            return
        
        self.running = True
        self.task = asyncio.create_task(self._run_scheduler())
        log.info("Sync scheduler started")
    
    async def stop(self):
        """Stop the background sync scheduler."""
        if not self.running:
            return
        
        self.running = False
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
        
        log.info("Sync scheduler stopped")
    
    async def _run_scheduler(self):
        """Main scheduler loop."""
        try:
            while self.running:
                now = datetime.utcnow()

                # Check if incremental sync is due
                if (self.last_incremental_sync is None or
                    now - self.last_incremental_sync >= self.incremental_interval):
                    await self._run_incremental_sync()
                    self.last_incremental_sync = now

                # Check if full sync is due
                if (self.last_full_sync is None or
                    now - self.last_full_sync >= self.full_sync_interval):
                    await self._run_full_sync()
                    self.last_full_sync = now

                # Check if graph discovery is due
                if (self.last_graph_discovery is None or
                    now - self.last_graph_discovery >= self.graph_discovery_interval):
                    await self._run_graph_discovery()
                    self.last_graph_discovery = now

                # Check if cleanup is due
                if (self.last_cleanup is None or
                    now - self.last_cleanup >= self.cleanup_interval):
                    await self._run_cleanup()
                    self.last_cleanup = now

                # Check if thread naming is due
                if (self.last_thread_naming is None or
                    now - self.last_thread_naming >= self.thread_naming_interval):
                    await self._run_thread_naming()
                    self.last_thread_naming = now

                # Sleep for 30 seconds before next check
                await asyncio.sleep(30)
                
        except asyncio.CancelledError:
            log.info("Sync scheduler cancelled")
        except Exception as e:
            log.error(f"Sync scheduler error: {e}")
            # Continue running despite errors
            if self.running:
                await asyncio.sleep(60)  # Wait a minute before retrying
                await self._run_scheduler()  # Restart the loop
    
    async def _run_incremental_sync(self):
        """Run incremental sync operation."""
        try:
            log.info("Running scheduled incremental sync")
            
            langgraph_service = get_langgraph_service()
            sync_service = LangGraphSyncService(langgraph_service)
            
            stats = await sync_service.sync_assistants_incremental()
            
            # Log summary
            if "error" not in stats:
                log.info(f"Incremental sync completed: {stats.get('new_assistants', 0)} new, {stats.get('updated_assistants', 0)} updated, {len(stats.get('errors', []))} errors")
            else:
                log.error(f"Incremental sync failed: {stats['error']}")
                
        except Exception as e:
            log.error(f"Failed to run incremental sync: {e}")
    
    async def _run_full_sync(self):
        """Run full sync operation."""
        try:
            log.info("Running scheduled full sync")

            langgraph_service = get_langgraph_service()
            sync_service = LangGraphSyncService(langgraph_service)

            stats = await sync_service.sync_all_full()

            # Log summary
            if "error" not in stats:
                log.info(f"Full sync completed: {stats.get('new_assistants', 0)} new, {stats.get('updated_assistants', 0)} updated, {stats.get('inactive_graphs', 0)} inactive graphs")
            else:
                log.error(f"Full sync failed: {stats['error']}")

        except Exception as e:
            log.error(f"Failed to run full sync: {e}")

    async def _run_graph_discovery(self):
        """Run graph discovery and permission sync operation."""
        try:
            log.info("Running scheduled graph discovery and permission sync")

            langgraph_service = get_langgraph_service()
            sync_service = LangGraphSyncService(langgraph_service)

            stats = await sync_service.sync_graph_discovery_and_permissions()

            # Log summary
            if stats.get("success"):
                log.info(f"Graph discovery completed: {stats.get('graphs_found', 0)} graphs found, "
                        f"{stats.get('graphs_updated', 0)} updated, "
                        f"{stats.get('permissions_granted', 0)} permissions granted")
            else:
                log.error(f"Graph discovery failed: {stats.get('error', 'Unknown error')}")

        except Exception as e:
            log.error(f"Failed to run graph discovery: {e}")

    async def _run_cleanup(self):
        """Run cleanup operation."""
        try:
            log.info("Running scheduled cleanup")

            langgraph_service = get_langgraph_service()
            sync_service = LangGraphSyncService(langgraph_service)

            stats = await sync_service.cleanup_stale_mirrors(grace_period_days=7)

            # Log summary
            if "error" not in stats:
                removed_assistants = stats.get('stale_assistants_removed', 0)
                removed_graphs = stats.get('stale_graphs_removed', 0)
                if removed_assistants > 0 or removed_graphs > 0:
                    log.info(f"Cleanup completed: {removed_assistants} assistants, {removed_graphs} graphs removed")
                else:
                    log.debug("Cleanup completed: nothing to remove")
            else:
                log.error(f"Cleanup failed: {stats['error']}")

        except Exception as e:
            log.error(f"Failed to run cleanup: {e}")

    async def _run_thread_naming(self):
        """Run thread naming operation."""
        try:
            log.debug("Running scheduled thread naming")

            # Get database pool
            db_pool = await get_db_pool()

            # Create naming service instance
            naming_service = ThreadNamingService(db_pool=db_pool)

            # Process batch of threads (max 5 per run, min 60s since last naming)
            batch_size = int(os.getenv("THREAD_NAMING_BATCH_SIZE", "5"))
            min_interval = int(os.getenv("THREAD_NAMING_MIN_INTERVAL_SECONDS", "60"))

            stats = await naming_service.process_batch(
                limit=batch_size,
                min_interval_seconds=min_interval
            )

            # Log summary (only if threads were processed)
            if stats["processed"] > 0:
                log.info(
                    f"Thread naming completed: {stats['succeeded']} succeeded, "
                    f"{stats['failed']} failed of {stats['processed']} processed"
                )

        except Exception as e:
            log.error(f"Failed to run thread naming: {e}")


# Global scheduler instance
_scheduler: Optional[SyncScheduler] = None


def get_scheduler() -> SyncScheduler:
    """Get the global scheduler instance with configuration from environment variables."""
    global _scheduler
    if _scheduler is None:
        # Read intervals from environment variables with sensible defaults
        incremental_interval = int(os.getenv("SYNC_INCREMENTAL_INTERVAL_MINUTES", "2"))
        full_sync_interval = int(os.getenv("SYNC_FULL_INTERVAL_MINUTES", "15"))
        cleanup_interval = int(os.getenv("SYNC_CLEANUP_INTERVAL_HOURS", "24"))
        graph_discovery_interval = int(os.getenv("SYNC_GRAPH_DISCOVERY_INTERVAL_MINUTES", "15"))
        thread_naming_interval = int(os.getenv("THREAD_NAMING_INTERVAL_SECONDS", "30"))

        _scheduler = SyncScheduler(
            incremental_interval_minutes=incremental_interval,
            full_sync_interval_minutes=full_sync_interval,
            cleanup_interval_hours=cleanup_interval,
            graph_discovery_interval_minutes=graph_discovery_interval,
            thread_naming_interval_seconds=thread_naming_interval
        )
    return _scheduler


async def start_sync_scheduler():
    """Start the background sync scheduler."""
    scheduler = get_scheduler()
    await scheduler.start()


async def stop_sync_scheduler():
    """Stop the background sync scheduler."""
    scheduler = get_scheduler()
    await scheduler.stop()
