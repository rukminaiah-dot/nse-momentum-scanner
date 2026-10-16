"""Opt-in PostgreSQL backup helper. Never connects unless explicitly invoked."""
import argparse
import os
from pathlib import Path
import subprocess
import sys
from datetime import datetime, timezone


def backup(*, tier: str, root: Path, url: str, executable: str = "pg_dump") -> Path:
    """Create an atomic local custom-format dump; never print credentials."""
    if tier not in ("daily", "weekly", "monthly"):
        raise ValueError("unsupported backup tier")
    if not url:
        raise ValueError("DATABASE_URL is required")
    destination = root / tier
    destination.mkdir(parents=True, exist_ok=True, mode=0o700)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output = destination / f"postgres_{tier}_{timestamp}.dump"
    temporary = destination / f".{output.name}.partial"
    if output.exists() or temporary.exists():
        raise FileExistsError("backup already exists for this timestamp")
    # A failed pg_dump must never leave a file mistaken for a valid backup.
    try:
        with temporary.open("xb") as stream:
            os.chmod(temporary, 0o600)
            # Never place the connection URL in process arguments: local
            # process listings and exception messages can expose argv.
            # libpq accepts a connection URI via PGDATABASE.
            environment = os.environ.copy()
            environment["PGDATABASE"] = url
            subprocess.run(
                [executable, "--format=custom", "--no-owner",
                 "--no-privileges"],
                stdout=stream, stderr=subprocess.PIPE, check=True,
                env=environment,
            )
        if temporary.stat().st_size == 0:
            raise RuntimeError("pg_dump returned an empty backup")
        temporary.rename(output)
        return output
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description="Manual, offline-safe PostgreSQL backup")
    parser.add_argument("--tier", choices=("daily", "weekly", "monthly"), required=True)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1] / "backups")
    args = parser.parse_args()
    try:
        path = backup(tier=args.tier, root=args.root,
                      url=os.environ.get("DATABASE_URL", ""))
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as exc:
        # Never include pg_dump's stderr or command arguments: both may leak
        # the connection string. Operators should investigate privately.
        print(f"Backup failed ({type(exc).__name__}); check private logs and configuration.",
              file=sys.stderr)
        return 1
    print(f"Backup written: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
