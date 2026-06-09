from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Any

from hollow_lodge.client.event_log_migration import (
    EVENT_DATABASE_URL_ENV,
    load_events,
    migrate_event_log_to_postgres,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Import an exported Hollow Lodge event log into empty Postgres storage."
    )
    parser.add_argument(
        "--source",
        required=True,
        type=Path,
        help="Event export file. Accepts admin export JSON, JSON array, or JSONL rows.",
    )
    parser.add_argument(
        "--database-url",
        default=os.environ.get(EVENT_DATABASE_URL_ENV, ""),
        help=f"Destination Postgres URL. Defaults to ${EVENT_DATABASE_URL_ENV}.",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=None,
        help="Optional backup manifest that must match the source before import.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate the source chain without writing to Postgres.",
    )
    args = parser.parse_args()

    result = migrate_event_log(
        source=args.source,
        database_url=args.database_url,
        manifest=args.manifest,
        dry_run=args.dry_run,
    )
    if result["dry_run"]:
        manifest_note = " manifest verified" if result.get("manifest_verified") else ""
        print(f"event log import dry-run ok: {result['event_count']} events{manifest_note}")
    else:
        manifest_note = " manifest verified" if result.get("manifest_verified") else ""
        print(
            "event log import ok: "
            f"{result['event_count']} events into {result['database_url']}"
            f"{manifest_note}"
        )


def migrate_event_log(
    *,
    source: Path,
    database_url: str,
    manifest: Path | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    return migrate_event_log_to_postgres(
        source=source,
        database_url=database_url,
        manifest=manifest,
        dry_run=dry_run,
    )


if __name__ == "__main__":
    main()
