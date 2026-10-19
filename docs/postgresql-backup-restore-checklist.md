# PostgreSQL backup restore verification (operator-run only)

**Scope:** PR #5, offline documentation. Do not connect to production or
restore into the existing Telix/PostgreSQL database. The operator's encrypted
Termux archive and Google Drive copy are private and must not be committed.

## Evidence already observed (15 October 2026)

- Termux GPG recognized AES256.CFB encrypted data and successfully decrypted
  the encrypted archive with the supplied passphrase.
- The decrypted archive's SHA-256 matched the original local .dump.
- `pg_restore --list` succeeded; the archive contains TABLE DATA entries for
  `active_trade_backup`, `daily_trade_history`,
  `index_candle_snapshots`, `signal_history`, and `universe_changes`.
- The encrypted file appeared in Android Download (~89 KB) and Google Drive
  (~88.8 KB, not shared). The complete Drive filename/extension and a
  post-download checksum have not been independently verified.
- These checks establish *archive readability*, not successful recovery or
  nonempty rows.

## Read-only inspection (safe to run in Termux)

```sh
ARCHIVE="$HOME/pg-backups/nse-momentum-2026-10-15.dump"
test -s "$ARCHIVE" || { echo "Missing or empty archive"; exit 1; }
pg_restore --list "$ARCHIVE" > "$HOME/pg-backups/restore-contents.txt"
grep 'TABLE DATA' "$HOME/pg-backups/restore-contents.txt"
```

This does not contact any database. Do not upload the decrypted dump or the
contents listing if it contains sensitive identifiers.

## Isolated restore acceptance procedure — requires explicit approval

1. Create an **empty, disposable, separate PostgreSQL database**, with its
   own distinct credentials. Record its host and database name privately.
   Never reuse the production `DATABASE_URL` or production credentials.
2. Independently confirm the target identity and that it contains no valuable
   data. Do not use `--clean`, `--create`, or `--if-exists` flags.
3. Only after authorization, restore the local decrypted dump to the verified
   disposable target:

   ```sh
   # RESTORE_DATABASE_URL must refer to a confirmed EMPTY TEST DATABASE.
   # Do not paste this URL into chats, commits, screenshots or logs.
   pg_restore --no-owner --no-privileges --exit-on-error \
     --dbname "$RESTORE_DATABASE_URL" \
     "$HOME/pg-backups/nse-momentum-2026-10-15.dump"
   ```

4. Inspect the restored schema and row counts *on the test database only*:

   ```sh
   psql "$RESTORE_DATABASE_URL" -X -v ON_ERROR_STOP=1 -c \
     "SELECT table_name FROM information_schema.tables WHERE table_schema='public' ORDER BY table_name;"
   psql "$RESTORE_DATABASE_URL" -X -v ON_ERROR_STOP=1 -c \
     "SELECT 'active_trade_backup' AS name, count(*) FROM public.active_trade_backup
      UNION ALL SELECT 'daily_trade_history', count(*) FROM public.daily_trade_history
      UNION ALL SELECT 'index_candle_snapshots', count(*) FROM public.index_candle_snapshots
      UNION ALL SELECT 'signal_history', count(*) FROM public.signal_history
      UNION ALL SELECT 'universe_changes', count(*) FROM public.universe_changes;"
   ```

5. Compare restored row counts against counts captured at backup time, if
   available. An empty table can be legitimate; table-data archive entries
   alone do not prove rows exist. Verify constraints and application-specific
   queries, then securely retire the disposable database when approved.

## Completion criteria

- Archive is readable and encrypted offsite copy is recoverable.
- Restore exits successfully against the separate empty database.
- All five expected tables, their constraints, and intended rows are present.
- No production database, credentials, or deployment was touched.

**Status:** Restore not performed. A separate disposable PostgreSQL target,
authorization, and a private restore connection are required.
