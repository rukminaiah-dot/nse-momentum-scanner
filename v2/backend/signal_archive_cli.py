"""Manual-only scanner signal archive maintenance.

Examples (from repository root, in an authorized environment):
  python -m v2.backend.signal_archive_cli init
  python -m v2.backend.signal_archive_cli sync
  python -m v2.backend.signal_archive_cli report --end-date 2026-10-14
  python -m v2.backend.signal_archive_cli verify

No command runs on import. Never prints DATABASE_URL or credentials.
"""
import argparse
import json
import os
import sys
import sqlite3
from datetime import date

def main(argv=None):
    parser = argparse.ArgumentParser(description="Manual paper signal archive maintenance")
    parser.add_argument("action", choices=("init", "sync", "report", "verify"))
    parser.add_argument("--end-date", help="IST YYYY-MM-DD, required for report")
    args = parser.parse_args(argv)
    if args.action == "report":
        if not args.end_date:
            parser.error("--end-date required for report")
        date.fromisoformat(args.end_date)
    elif args.end_date:
        parser.error("--end-date is only supported for report")

    url = os.getenv("DATABASE_URL")
    if not url:
        print("ERROR: DATABASE_URL is not configured", file=sys.stderr)
        return 2

    import psycopg
    from .database import DB_PATH
    from .market_config import INDICES
    from .signal_archive_postgres import init_signal_archive
    from .signal_archive_sync import sync_observed_signals
    from .signal_archive_health import compare_archive_keys
    from .signal_cumulative_report import cumulative_report, fetch_cumulative_archive

    try:
        with psycopg.connect(url, connect_timeout=5) as pg:
            if args.action == "init":
                init_signal_archive(pg)
                print("Signal archive schema initialized")
            elif args.action == "sync":
                result = sync_observed_signals(DB_PATH, pg)
                print(json.dumps(result, sort_keys=True))
            elif args.action == "verify":
                result = compare_archive_keys(DB_PATH, pg)
                print(json.dumps(result, sort_keys=True))
                if (not result["available_source_reconciliation_verified"]
                        or result["missing_from_archive"] or result["mismatched_archive_values"]):
                    return 3
            else:
                rows = fetch_cumulative_archive(pg, end_date=args.end_date)
                result = cumulative_report(rows, index_symbols=set(INDICES))
                print(json.dumps(result, sort_keys=True))
    except (psycopg.Error, sqlite3.Error, OSError) as exc:
        print("ERROR: signal archive operation failed (" + type(exc).__name__ + ")", file=sys.stderr)
        return 1
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
