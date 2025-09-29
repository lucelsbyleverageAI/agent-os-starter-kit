"""
Background sync scheduler for LangGraph mirroring.

This service runs periodic sync operations to keep mirrors up-to-date
with external changes in LangGraph (assistants created outside the UI).
"""

import asyncio
import logging
from typing import Optional
from datetime import datetime, timedelta

from langconnect.services.langgraph_sync import LangGraphSyncService
from langconnect.services.langgraph_integration import get_langgraph_service

log = logging.getLogger(__name__)


class SyncScheduler:
    """Background scheduler for LangGraph sync operations."""
    
    def __init__(
        self,
        incremental_interval_minutes: int = 2,
        full_sync_interval_minutes: int = 15,
        cleanup_interval_hours: int = 24
    ):
        self.incremental_interval = timedelta(minutes=incremental_interval_minutes)
        self.full_sync_interval = timedelta(minutes=full_sync_interval_minutes)
        self.cleanup_interval = timedelta(hours=cleanup_interval_hours)
        
        self.last_incremental_sync: Optional[datetime] = None
        self.last_full_sync: Optional[datetime] = None
        self.last_cleanup: Optional[datetime] = None
        
        self.running = False
        self.task: Optional[asyncio.Task] = None
        
        log.info(f"Sync scheduler initialized: incremental={incremental_interval_minutes}m, full={full_sync_interval_minutes}m, cleanup={cleanup_interval_hours}h")
    
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
                
                # Check if cleanup is due
                if (self.last_cleanup is None or 
                    now - self.last_cleanup >= self.cleanup_interval):
                    await self._run_cleanup()
                    self.last_cleanup = now
                
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


# Global scheduler instance
_scheduler: Optional[SyncScheduler] = None


def get_scheduler() -> SyncScheduler:
    """Get the global scheduler instance."""
    global _scheduler
    if _scheduler is None:
        _scheduler = SyncScheduler()
    return _scheduler


async def start_sync_scheduler():
    """Start the background sync scheduler."""
    scheduler = get_scheduler()
    await scheduler.start()


async def stop_sync_scheduler():
    """Stop the background sync scheduler."""
    scheduler = get_scheduler()
    await scheduler.stop()
