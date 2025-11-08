#!/usr/bin/env python3
"""
Database Cleanup Script for Corrupted Metadata

This script detects and fixes corrupted JSONB data in the assistants_mirror table
that was caused by double JSON encoding or character array conversion.

Usage:
    # Dry-run (preview only)
    python database/cleanup_corrupted_metadata.py --dry-run

    # Fix corrupted metadata
    python database/cleanup_corrupted_metadata.py

    # Fix only specific assistant
    python database/cleanup_corrupted_metadata.py --assistant-id <uuid>
"""

import asyncio
import sys
import json
import argparse
from pathlib import Path
from datetime import datetime

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "apps" / "langconnect"))

from langconnect.database.connection import get_db_connection
from langconnect.utils.metadata_validation import (
    parse_metadata_safe,
    is_character_indexed_dict,
    validate_field_size
)

import logging

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)


async def detect_corrupted_assistants(assistant_id: str = None):
    """
    Detect assistants with corrupted metadata/config/context.

    Returns:
        List of corrupted assistant records with details
    """
    corrupted = []

    async with get_db_connection() as conn:
        if assistant_id:
            query = """
                SELECT assistant_id, name, metadata, config, context, langgraph_hash
                FROM langconnect.assistants_mirror
                WHERE assistant_id = $1
            """
            rows = await conn.fetch(query, assistant_id)
        else:
            query = """
                SELECT assistant_id, name, metadata, config, context, langgraph_hash
                FROM langconnect.assistants_mirror
                ORDER BY updated_at DESC
            """
            rows = await conn.fetch(query)

    for row in rows:
        assistant_id = str(row["assistant_id"])
        name = row["name"]
        issues = []

        # Check metadata
        metadata = row["metadata"]
        if metadata:
            if isinstance(metadata, str):
                issues.append(f"metadata is string (should be JSONB dict)")
            elif isinstance(metadata, dict):
                if is_character_indexed_dict(metadata):
                    issues.append(f"metadata is character-indexed dict (corrupted)")
                else:
                    # Check for double-encoded strings in metadata values
                    for key, value in metadata.items():
                        if isinstance(value, str) and value.startswith('{"') or value.startswith('['):
                            try:
                                json.loads(value)
                                issues.append(f"metadata.{key} contains JSON string (possible double-encoding)")
                            except:
                                pass

            # Check size
            valid, error = validate_field_size(metadata, "metadata")
            if not valid:
                issues.append(f"metadata too large: {error}")

        # Check config
        config = row["config"]
        if config:
            if isinstance(config, str):
                issues.append(f"config is string (should be JSONB dict)")
            elif isinstance(config, dict) and is_character_indexed_dict(config):
                issues.append(f"config is character-indexed dict (corrupted)")

            valid, error = validate_field_size(config, "config")
            if not valid:
                issues.append(f"config too large: {error}")

        # Check context
        context = row["context"]
        if context:
            if isinstance(context, str):
                issues.append(f"context is string (should be JSONB dict)")
            elif isinstance(context, dict) and is_character_indexed_dict(context):
                issues.append(f"context is character-indexed dict (corrupted)")

            valid, error = validate_field_size(context, "context")
            if not valid:
                issues.append(f"context too large: {error}")

        if issues:
            corrupted.append({
                "assistant_id": assistant_id,
                "name": name,
                "issues": issues,
                "metadata": metadata,
                "config": config,
                "context": context
            })

    return corrupted


async def fix_corrupted_assistant(assistant_id: str, dry_run: bool = False):
    """
    Fix corrupted metadata/config/context for a single assistant.

    Args:
        assistant_id: Assistant to fix
        dry_run: If True, only preview fixes without applying

    Returns:
        Dict with fix results
    """
    result = {
        "assistant_id": assistant_id,
        "fixed_fields": [],
        "errors": []
    }

    async with get_db_connection() as conn:
        # Fetch current data
        row = await conn.fetchrow(
            """
            SELECT assistant_id, name, metadata, config, context, description
            FROM langconnect.assistants_mirror
            WHERE assistant_id = $1
            """,
            assistant_id
        )

        if not row:
            result["errors"].append(f"Assistant {assistant_id} not found")
            return result

        name = row["name"]
        updates = {}

        # Fix metadata
        if row["metadata"]:
            original = row["metadata"]
            fixed = parse_metadata_safe(original, "metadata")
            if fixed != original:
                updates["metadata"] = fixed
                result["fixed_fields"].append("metadata")
                log.info(f"[{name}] metadata: {type(original).__name__} -> dict with {len(fixed)} keys")

        # Fix config
        if row["config"]:
            original = row["config"]
            fixed = parse_metadata_safe(original, "config")
            if fixed != original:
                updates["config"] = fixed
                result["fixed_fields"].append("config")
                log.info(f"[{name}] config: {type(original).__name__} -> dict with {len(fixed)} keys")

        # Fix context
        if row["context"]:
            original = row["context"]
            fixed = parse_metadata_safe(original, "context")
            if fixed != original:
                updates["context"] = fixed
                result["fixed_fields"].append("context")
                log.info(f"[{name}] context: {type(original).__name__} -> dict with {len(fixed)} keys")

        # Apply updates
        if updates and not dry_run:
            try:
                # Build UPDATE query dynamically
                set_clauses = []
                params = [assistant_id]
                param_idx = 2

                for field, value in updates.items():
                    set_clauses.append(f"{field} = ${param_idx}")
                    params.append(value)
                    param_idx += 1

                # Always update mirror_updated_at
                set_clauses.append(f"mirror_updated_at = NOW()")
                set_clauses.append(f"updated_at = NOW()")

                query = f"""
                    UPDATE langconnect.assistants_mirror
                    SET {', '.join(set_clauses)}
                    WHERE assistant_id = $1
                """

                await conn.execute(query, *params)

                # Increment cache version
                await conn.fetchval("SELECT langconnect.increment_cache_version('assistants')")

                log.info(f"[{name}] Successfully updated {len(updates)} fields")
                result["success"] = True

            except Exception as e:
                error_msg = f"Failed to update assistant: {e}"
                log.error(f"[{name}] {error_msg}")
                result["errors"].append(error_msg)
                result["success"] = False
        else:
            result["success"] = True if updates else None  # None means no updates needed

    return result


async def main():
    parser = argparse.ArgumentParser(description="Clean up corrupted metadata in assistants_mirror table")
    parser.add_argument("--dry-run", action="store_true", help="Preview fixes without applying")
    parser.add_argument("--assistant-id", type=str, help="Fix only specific assistant ID")
    args = parser.parse_args()

    log.info("=" * 80)
    log.info("Database Metadata Cleanup Script")
    log.info("=" * 80)
    log.info(f"Mode: {'DRY RUN (preview only)' if args.dry_run else 'LIVE (will apply fixes)'}")
    log.info(f"Scope: {'Single assistant ' + args.assistant_id if args.assistant_id else 'All assistants'}")
    log.info("=" * 80)

    # Step 1: Detect corrupted assistants
    log.info("\n[1/3] Detecting corrupted assistants...")
    corrupted = await detect_corrupted_assistants(args.assistant_id)

    if not corrupted:
        log.info("✓ No corrupted assistants found!")
        return

    log.info(f"✗ Found {len(corrupted)} corrupted assistants:\n")

    for item in corrupted:
        log.info(f"  • {item['name']} ({item['assistant_id']})")
        for issue in item['issues']:
            log.info(f"    - {issue}")
        log.info("")

    # Step 2: Preview/apply fixes
    if args.dry_run:
        log.info("\n[2/3] DRY RUN - Previewing fixes (no changes will be made)...")
    else:
        log.info("\n[2/3] Applying fixes...")
        response = input("Continue with fixes? [y/N]: ")
        if response.lower() != 'y':
            log.info("Aborted by user")
            return

    results = []
    for item in corrupted:
        result = await fix_corrupted_assistant(item['assistant_id'], dry_run=args.dry_run)
        results.append(result)

    # Step 3: Summary
    log.info("\n[3/3] Summary")
    log.info("=" * 80)

    fixed_count = sum(1 for r in results if r.get('success') is True)
    no_fix_needed = sum(1 for r in results if r.get('success') is None)
    failed_count = sum(1 for r in results if r.get('success') is False)

    log.info(f"Total assistants checked: {len(corrupted)}")
    log.info(f"Successfully fixed: {fixed_count}")
    log.info(f"No fix needed: {no_fix_needed}")
    log.info(f"Failed: {failed_count}")

    if args.dry_run:
        log.info("\n⚠️  DRY RUN MODE - No changes were made to the database")
        log.info("Run without --dry-run to apply fixes")
    else:
        log.info("\n✓ Cleanup complete!")

    # Show any errors
    errors = [r for r in results if r.get('errors')]
    if errors:
        log.error("\nErrors encountered:")
        for r in errors:
            log.error(f"  • {r['assistant_id']}: {', '.join(r['errors'])}")


if __name__ == "__main__":
    asyncio.run(main())
