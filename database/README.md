# Database Migration System

This directory contains the custom migration system for the Agent OS. It is designed to manage application-specific database schema changes separately from Supabase's internal schema. The system ensures that all environments (local, staging, production) are kept in sync automatically by applying SQL migrations in a controlled, idempotent manner.

## Core Concepts

- **Schema Isolation**: Migrations only affect our application-specific schema (`langconnect`), never Supabase's internal tables (`auth`, `storage`, etc.).
- **Automated Execution**: Migrations are designed to be run automatically on service startup. A dedicated `migration-init` service in Docker Compose executes the `migrate.py` script before any application containers are started.
- **Two-Track System**: The system supports two independent migration paths to separate core platform changes from client-specific customizations.
- **Idempotency**: SQL scripts should be written to be safely executable multiple times without causing errors (e.g., using `CREATE TABLE IF NOT EXISTS`).

## Directory Structure

Migrations are organized into a two-track system within the `database/migrations/` directory:

- **`lanconnect/`**: Contains baseline schema migrations for the core OS platform. These are fundamental changes required for the application to function.
- **`client_specific/`**: Contains additional or overriding migrations for a specific client or deployment. These are applied *after* the `lanconnect` migrations.

## How It Works

The migration process is managed by the `database/migrate.py` script.

1.  **Database Connection**: The script waits for the PostgreSQL database to become available before proceeding.
2.  **Tracking Tables**: It ensures two tracking tables exist in the `langconnect` schema:
    - `langconnect.lanconnect_migration_versions`
    - `langconnect.client_migration_versions`
    These tables store a record of every migration that has been successfully applied for each track.
3.  **Finding Pending Migrations**: The script scans the `lanconnect/` and `client_specific/` directories for SQL files. It compares the list of files against the records in the corresponding version tables to determine which migrations are pending.
4.  **Executing Migrations**:
    - Pending migrations are executed in numerical order based on their filename prefix (`001_`, `002_`, etc.).
    - The `lanconnect` track is always executed before the `client_specific` track.
    - The script uses the `psql` command-line tool to apply each migration file, which correctly handles multi-statement SQL and transaction blocks.
5.  **Recording Status**:
    - On success, a new row is added to the appropriate version table, marking the migration as `applied`.
    - If an error occurs, the script immediately stops and records the failure in the version table with a status of `failed` and the corresponding error message. This prevents subsequent migrations from running and ensures application services do not start with a partially migrated database.

## How to Create and Apply Migrations

1.  **Create a New Migration File**:
    - Decide if the change is a core platform change (`lanconnect/`) or a client-specific one (`client_specific/`).
    - Create a new SQL file in the appropriate directory.
    - Name the file using a zero-padded, three-digit prefix followed by a description (e.g., `004_add_user_preferences.sql`). The prefix determines the execution order.

2.  **Write Idempotent SQL**:
    - Always write your SQL to be safely re-runnable. Use `IF NOT EXISTS` for tables/columns and other defensive checks.
    - It's good practice to set the schema context at the top of your file: `SET search_path = langconnect, public;`

3.  **Run Migrations**:
    - **Automatically (Recommended)**: The migrations will run automatically when you start the full application stack (e.g., via `make dev-start` or `make start`), as the `migration-init` service is part of the startup sequence.
    - **Manually**: You can run the migration script directly to check status, preview changes (dry run), or apply pending migrations without restarting the full stack.

      ```bash
      # Ensure your local Supabase container is running
      
      # Check the status of all migrations
      python3 database/migrate.py --status
      
      # Preview which migrations will be applied (no changes made)
      python3 database/migrate.py --dry-run
      
      # Apply all pending migrations
      python3 database/migrate.py
      ```

## Best Practices

- **Never modify an applied migration file.** If you need to make changes or reverse a migration, create a *new* migration file.
- **Test migrations locally** using the manual commands before committing your changes.
- **Keep migrations small and focused** on a single logical change. This makes them easier to debug if they fail.