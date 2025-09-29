#!/usr/bin/env python3
import argparse
import logging
import os
import re
import sys
import time
import subprocess
from pathlib import Path
from typing import List, Optional, Tuple

import psycopg2
from psycopg2 import sql
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)


class MigrationError(Exception):
    """Custom exception for migration-related errors."""
    pass


class DatabaseMigrator:
    """Handles database migration operations."""
    
    def __init__(self, host: str, port: int, database: str, user: str, password: str):
        """Initialize the migrator with database connection parameters."""
        self.host = host
        self.port = port
        self.database = database
        self.user = user
        self.password = password
        self.migrations_dir = Path(__file__).parent / "migrations"
        
        # New: track-specific migration directories
        self.lanconnect_dir = self.migrations_dir / "lanconnect"
        self.client_specific_dir = self.migrations_dir / "client_specific"
        
        # Ensure directories exist
        self.migrations_dir.mkdir(exist_ok=True)
        self.lanconnect_dir.mkdir(exist_ok=True)
        self.client_specific_dir.mkdir(exist_ok=True)
    
    def wait_for_database(self, max_wait_time: int = 180, retry_interval: int = 5) -> bool:
        """Wait for database to be ready before proceeding with migrations."""
        logger.info(f"Waiting for database at {self.host}:{self.port} to be ready...")
        start_time = time.time()
        attempt = 0
        
        while time.time() - start_time < max_wait_time:
            attempt += 1
            try:
                # Try to connect and perform a simple query to ensure DB is actually ready
                conn = psycopg2.connect(
                    host=self.host,
                    port=self.port,
                    database=self.database,
                    user=self.user,
                    password=self.password,
                    connect_timeout=5
                )
                
                with conn.cursor() as cur:
                    # Test that we can actually perform operations
                    cur.execute("SELECT 1")
                    cur.fetchone()
                    
                    # Test that we can create schemas (important for first-time setup)
                    cur.execute("SELECT current_database()")
                    cur.fetchone()
                    
                conn.close()
                logger.info(f"✅ Database is ready after {attempt} attempts")
                return True
                
            except psycopg2.OperationalError as e:
                elapsed = time.time() - start_time
                remaining = max_wait_time - elapsed
                
                if remaining <= 0:
                    logger.error(f"❌ Database not ready after {max_wait_time} seconds")
                    return False
                
                logger.info(f"⏳ Database not ready (attempt {attempt}), retrying in {retry_interval}s... ({remaining:.0f}s remaining)")
                time.sleep(retry_interval)
                
            except Exception as e:
                logger.error(f"❌ Unexpected error connecting to database: {e}")
                return False
        
        logger.error(f"❌ Database not ready after {max_wait_time} seconds")
        return False
        
    def get_connection(self) -> psycopg2.extensions.connection:
        """Create and return a database connection."""
        try:
            conn = psycopg2.connect(
                host=self.host,
                port=self.port,
                database=self.database,
                user=self.user,
                password=self.password
            )
            return conn
        except psycopg2.Error as e:
            raise MigrationError(f"Failed to connect to database: {e}")
    
    def ensure_migration_table(self) -> None:
        """Create the migration version tables if they don't exist."""
        create_table_sql = """
        CREATE SCHEMA IF NOT EXISTS langconnect;
        
        CREATE TABLE IF NOT EXISTS langconnect.lanconnect_migration_versions (
            version VARCHAR(255) NOT NULL PRIMARY KEY,
            applied_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            description TEXT,
            status TEXT NOT NULL DEFAULT 'applied', -- 'applied' | 'failed'
            error_message TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_lc_migrations_applied_at 
        ON langconnect.lanconnect_migration_versions(applied_at);
        CREATE INDEX IF NOT EXISTS idx_lc_migrations_status 
        ON langconnect.lanconnect_migration_versions(status);
        
        CREATE TABLE IF NOT EXISTS langconnect.client_migration_versions (
            version VARCHAR(255) NOT NULL PRIMARY KEY,
            applied_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            description TEXT,
            status TEXT NOT NULL DEFAULT 'applied', -- 'applied' | 'failed'
            error_message TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_client_migrations_applied_at 
        ON langconnect.client_migration_versions(applied_at);
        CREATE INDEX IF NOT EXISTS idx_client_migrations_status 
        ON langconnect.client_migration_versions(status);
        """
        
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(create_table_sql)
                    # Ensure columns exist if tables were created previously without them
                    cur.execute("ALTER TABLE langconnect.lanconnect_migration_versions ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'applied'")
                    cur.execute("ALTER TABLE langconnect.lanconnect_migration_versions ADD COLUMN IF NOT EXISTS error_message TEXT")
                    cur.execute("ALTER TABLE langconnect.client_migration_versions ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'applied'")
                    cur.execute("ALTER TABLE langconnect.client_migration_versions ADD COLUMN IF NOT EXISTS error_message TEXT")
                    conn.commit()
                    logger.info("Migration tracking tables ensured (lanconnect/client)")
        except psycopg2.Error as e:
            raise MigrationError(f"Failed to create migration tables: {e}")
    
    def _get_applied_migrations_for(self, table_name: str) -> List[str]:
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        f"SELECT version FROM langconnect.{table_name} WHERE status = 'applied' ORDER BY version"
                    )
                    return [row[0] for row in cur.fetchall()]
        except psycopg2.Error as e:
            raise MigrationError(f"Failed to get applied migrations for {table_name}: {e}")
    
    def _get_available_migrations_in(self, dir_path: Path) -> List[Tuple[str, Path]]:
        migration_pattern = re.compile(r'^(\d{3})_.*\.sql$')
        migrations: List[Tuple[str, Path]] = []
        for file_path in sorted(dir_path.glob("*.sql")):
            match = migration_pattern.match(file_path.name)
            if match:
                version = match.group(1)
                migrations.append((version, file_path))
            else:
                logger.warning(f"Skipping file with invalid name format: {file_path.name}")
        return migrations
    
    def _get_pending_for(self, dir_path: Path, table_name: str) -> List[Tuple[str, Path]]:
        applied = set(self._get_applied_migrations_for(table_name))
        available = self._get_available_migrations_in(dir_path)
        pending = [(version, path) for version, path in available if version not in applied]
        logger.info(f"Track {table_name}: {len(available)} available, {len(applied)} applied, {len(pending)} pending")
        return pending
    
    def validate_migration_content(self, file_path: Path) -> str:
        """Read and validate migration file content."""
        try:
            content = file_path.read_text(encoding='utf-8')
            if not content.strip():
                raise MigrationError(f"Migration file is empty: {file_path}")
            return content
        except UnicodeDecodeError as e:
            raise MigrationError(f"Migration file has invalid encoding: {file_path} - {e}")
        except IOError as e:
            raise MigrationError(f"Failed to read migration file: {file_path} - {e}")
    
    def execute_migration(self, version: str, file_path: Path, track_table: str, dry_run: bool = False) -> None:
        logger.info(f"{'[DRY RUN] ' if dry_run else ''}Applying {track_table} migration {version}: {file_path.name}")
        migration_sql = self.validate_migration_content(file_path)
        if dry_run:
            logger.debug(f"[DRY RUN] SQL content (head):\n{migration_sql[:200]}...")
            return
        start_time = time.time()
        try:
            # Execute via psql to properly handle DO $$ blocks and multi-statement files
            env = os.environ.copy()
            env['PGPASSWORD'] = self.password or ''
            cmd = [
                'psql',
                '-h', str(self.host),
                '-p', str(self.port),
                '-U', str(self.user),
                '-d', str(self.database),
                '-v', 'ON_ERROR_STOP=1',
                '-f', str(file_path)
            ]
            completed = subprocess.run(cmd, capture_output=True, text=True, env=env)
            if completed.returncode != 0:
                raise MigrationError(completed.stderr or completed.stdout or 'Unknown psql error')

            # Record success
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        f"""
                        INSERT INTO langconnect.{track_table} (version, description, status, error_message)
                        VALUES (%s, %s, 'applied', NULL)
                        ON CONFLICT (version) DO UPDATE SET
                          description = EXCLUDED.description,
                          status = 'applied',
                          error_message = NULL,
                          applied_at = CURRENT_TIMESTAMP
                        """,
                        (version, f"Applied {file_path.name}")
                    )
                    conn.commit()
            elapsed = int((time.time() - start_time) * 1000)
            logger.info(f"✅ Successfully applied {track_table} migration {version} in {elapsed}ms")
        except psycopg2.Error as e:
            elapsed = int((time.time() - start_time) * 1000)
            logger.error(f"❌ {track_table} migration {version} failed after {elapsed}ms: {e}")
            # Record failure (upsert for retries)
            try:
                with self.get_connection() as conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            f"""
                            INSERT INTO langconnect.{track_table} (version, description, status, error_message)
                            VALUES (%s, %s, 'failed', %s)
                            ON CONFLICT (version) DO UPDATE SET
                              description = EXCLUDED.description,
                              status = 'failed',
                              error_message = EXCLUDED.error_message,
                              applied_at = CURRENT_TIMESTAMP
                            """,
                            (version, f"FAILED: {file_path.name}", str(e))
                        )
                        conn.commit()
            except psycopg2.Error:
                logger.error("Failed to record migration failure in database")
            raise MigrationError(f"{track_table} migration {version} failed: {e}")
        except MigrationError as e:
            elapsed = int((time.time() - start_time) * 1000)
            logger.error(f"❌ {track_table} migration {version} failed after {elapsed}ms: {e}")
            # Record failure (upsert for retries)
            try:
                with self.get_connection() as conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            f"""
                            INSERT INTO langconnect.{track_table} (version, description, status, error_message)
                            VALUES (%s, %s, 'failed', %s)
                            ON CONFLICT (version) DO UPDATE SET
                              description = EXCLUDED.description,
                              status = 'failed',
                              error_message = EXCLUDED.error_message,
                              applied_at = CURRENT_TIMESTAMP
                            """,
                            (version, f"FAILED: {file_path.name}", str(e))
                        )
                        conn.commit()
            except psycopg2.Error:
                logger.error("Failed to record migration failure in database")
            raise
    
    def run_migrations(self, dry_run: bool = False) -> None:
        logger.info(f"{'[DRY RUN] ' if dry_run else ''}Starting database migration process (two-track)")
        if not dry_run:
            max_wait_time = int(os.getenv('MAX_WAIT_TIME', '180'))
            retry_interval = int(os.getenv('WAIT_RETRY_INTERVAL', '5'))
            if not self.wait_for_database(max_wait_time, retry_interval):
                raise MigrationError("Database is not ready for migrations")
        # Ensure tracking tables
        if not dry_run:
            self.ensure_migration_table()
        else:
            logger.info("[DRY RUN] Would ensure migration tracking tables exist")
        
        # Optional destructive reset (drops langconnect schema and related triggers)
        reset_flag = os.getenv('MIGRATION_RESET_SCHEMA', '').lower() in ('1', 'true', 'yes', 'on')
        if reset_flag and not dry_run:
            logger.warning("⚠️ MIGRATION_RESET_SCHEMA is enabled – dropping langconnect schema and related triggers")
            reset_sql = """
            DO $$ BEGIN
              IF EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trigger_auto_create_user_role') THEN
                DROP TRIGGER trigger_auto_create_user_role ON auth.users;
              END IF;
              IF EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trigger_auto_grant_public_permissions') THEN
                DROP TRIGGER trigger_auto_grant_public_permissions ON auth.users;
              END IF;
            END $$;
            DROP SCHEMA IF EXISTS langconnect CASCADE;
            """
            try:
                with self.get_connection() as conn:
                    with conn.cursor() as cur:
                        cur.execute(reset_sql)
                        conn.commit()
                        logger.info("✅ Schema reset completed")
                # Recreate migration tracking tables after destructive reset
                self.ensure_migration_table()
            except psycopg2.Error as e:
                raise MigrationError(f"Failed to reset schema: {e}")

        # Run LAN Connect track first
        lc_pending = self._get_pending_for(self.lanconnect_dir, 'lanconnect_migration_versions')
        # Then client-specific track
        client_pending = self._get_pending_for(self.client_specific_dir, 'client_migration_versions')
        
        if not lc_pending and not client_pending:
            logger.info("No pending migrations in either track")
            return
        
        for version, path in lc_pending:
            self.execute_migration(version, path, 'lanconnect_migration_versions', dry_run)
        for version, path in client_pending:
            self.execute_migration(version, path, 'client_migration_versions', dry_run)
        
        logger.info(f"{'[DRY RUN] ' if dry_run else ''}Two-track migration process completed successfully")
    
    def get_migration_status(self) -> None:
        """Display current migration status."""
        logger.info("=== Migration Status ===")
        
        try:
            lc_applied = self._get_applied_migrations_for('lanconnect_migration_versions')
            lc_available = self._get_available_migrations_in(self.lanconnect_dir)
            lc_pending = self._get_pending_for(self.lanconnect_dir, 'lanconnect_migration_versions')
            
            client_applied = self._get_applied_migrations_for('client_migration_versions')
            client_available = self._get_available_migrations_in(self.client_specific_dir)
            client_pending = self._get_pending_for(self.client_specific_dir, 'client_migration_versions')
            
            logger.info(f"LAN Connect Track:")
            logger.info(f"   Total available migrations: {len(lc_available)}")
            logger.info(f"   Applied migrations: {len(lc_applied)}")
            logger.info(f"   Pending migrations: {len(lc_pending)}")
            
            if lc_applied:
                logger.info("   Applied migrations:")
                for version in lc_applied:
                    logger.info(f"     ✅ {version}")
            
            if lc_pending:
                logger.info("   Pending migrations:")
                for version, file_path in lc_pending:
                    logger.info(f"     ⏳ {version}: {file_path.name}")
            
            logger.info(f"\nClient-Specific Track:")
            logger.info(f"   Total available migrations: {len(client_available)}")
            logger.info(f"   Applied migrations: {len(client_applied)}")
            logger.info(f"   Pending migrations: {len(client_pending)}")
            
            if client_applied:
                logger.info("   Applied migrations:")
                for version in client_applied:
                    logger.info(f"     ✅ {version}")
            
            if client_pending:
                logger.info("   Pending migrations:")
                for version, file_path in client_pending:
                    logger.info(f"     ⏳ {version}: {file_path.name}")
            
        except MigrationError as e:
            logger.error(f"Failed to get migration status: {e}")


def get_db_config() -> dict:
    """Get database configuration from environment variables or defaults."""
    return {
        'host': os.getenv('POSTGRES_HOST', 'localhost'),
        'port': int(os.getenv('POSTGRES_PORT', '5432')),
        'database': os.getenv('POSTGRES_DB', 'postgres'),
        'user': os.getenv('POSTGRES_USER', 'postgres'),
        'password': os.getenv('POSTGRES_PASSWORD')
    }


def main():
    """Main entry point for the migration runner."""
    parser = argparse.ArgumentParser(description='Database Migration Runner')
    parser.add_argument('--host', help='Database host (default: POSTGRES_HOST env var or localhost)')
    parser.add_argument('--port', type=int, help='Database port (default: POSTGRES_PORT env var or 5432)')
    parser.add_argument('--database', help='Database name (default: POSTGRES_DB env var or postgres)')
    parser.add_argument('--user', help='Database user (default: POSTGRES_USER env var or postgres)')
    parser.add_argument('--password', help='Database password (default: POSTGRES_PASSWORD env var)')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be executed without applying changes')
    parser.add_argument('--status', action='store_true', help='Show migration status and exit')
    parser.add_argument('--verbose', '-v', action='store_true', help='Enable verbose logging')
    
    args = parser.parse_args()
    
    # Configure logging level
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Get database configuration
    db_config = get_db_config()
    
    # Override with command line arguments if provided
    if args.host:
        db_config['host'] = args.host
    if args.port:
        db_config['port'] = args.port
    if args.database:
        db_config['database'] = args.database
    if args.user:
        db_config['user'] = args.user
    if args.password:
        db_config['password'] = args.password
    
    # Validate required configuration
    if not db_config['password']:
        logger.error("Database password is required (set POSTGRES_PASSWORD env var or use --password)")
        sys.exit(1)
    
    logger.info(f"Connecting to database: {db_config['user']}@{db_config['host']}:{db_config['port']}/{db_config['database']}")
    
    try:
        migrator = DatabaseMigrator(**db_config)
        
        if args.status:
            migrator.get_migration_status()
        else:
            migrator.run_migrations(dry_run=args.dry_run)
            
    except MigrationError as e:
        logger.error(f"Migration failed: {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        logger.info("Migration interrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main() 