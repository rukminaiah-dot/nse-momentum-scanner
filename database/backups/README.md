# Private PostgreSQL backup destination

This directory contains **no actual backups** in Git. The daily/, weekly/, and
monthly/ directories are placeholders; generated files are gitignored.

Use `python database/scripts/backup_db.py --tier daily` with `DATABASE_URL`
set **only in the operator's private environment** and PostgreSQL `pg_dump`
installed. The script does not run on import, in CI, or on deployment.
No automatic scheduling or database connection is enabled.

Backups are written using PostgreSQL custom format (.dump), suitable for
`pg_restore`. Never put database URLs or backup archives into GitHub, CI logs,
or public storage. Backups should be stored on an encrypted private volume,
with a separate off-host copy and access restrictions. This repo does not
create offsite copies.

Suggested operator-run cadence: daily (retain 7), weekly (retain 4), monthly
(retain 12). Retention is **not automated**; do not delete backups until restore
tests, encryption, and the service provider's own recovery features are checked.

Restore to a **separate non-production database**, after independent review:
`pg_restore --dbname "$RESTORE_DATABASE_URL" --no-owner --no-privileges path/to/file.dump`.
Do not run restore against production. `pg_restore` may fail when target tables
already exist; prepare an isolated empty target and verify row counts/schema.
The database service's actual PostgreSQL compatibility and access method must
be confirmed before running these commands.
