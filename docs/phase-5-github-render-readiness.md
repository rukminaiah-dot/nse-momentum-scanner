# Phase 5: GitHub and Render readiness (offline review)

Scope: PR #5, `feature/verified-gap-recovery`. **No deployment, live
feed, production database access, merging, or trading is authorized.**

## GitHub findings (2026-10-15)

- Latest reviewed CI baseline: `0d4c100`, Verified Gap Recovery Tests
  282/282 passed (including 4 offline backup tests); WebSocket preflight
  105/105 passed.
- PR #5 returned zero submitted reviews and zero review threads at inspection.
  This does **not** establish branch protection, approvals, mergeability, or
  production readiness.
- CI uses Python 3.11 and has read-only `contents` permission.
- No root `render.yaml`, root `requirements.txt`, or
  `v2/backend/requirements.txt` was found on this branch. Deployment may be
  configured in the Render dashboard or in other files. Do not infer a start
  command or runtime from the repository.

## Render review blocked pending workspace confirmation

The Render account reports one accessible workspace named `My Workspace`.
Do not select a workspace or inspect service configuration until the operator
confirms the intended workspace. After confirmation, **read only**:

1. Identify scanner-related services and their environment (production vs
   preview/staging), service type, branch, root directory and start command.
2. Review auto-deploy setting, latest deploy status, build logs and runtime
   logs. Avoid disclosing secret values.
3. Confirm database service association, health check, and whether backups
   and restore procedures exist. Never test against production.
4. Verify whether a separate non-production environment exists. If absent,
   mark controlled live-feed testing blocked, rather than repurposing production.
5. Review the rollback route and who is authorized to execute it. Do not
   trigger a deploy or rollback during inspection.

## Live-feed testing gate

- Authoritative NSE trading-session schedule independently verified.
- Read-only Upstox V3 feed and decoded exchange timestamps validated.
- Explicit safety proof that order execution and trading remain disabled.
- Separate test environment and credentials authorized.
- Operator explicitly authorizes the live feed connection.

## Handover

**Completed:** Offline GitHub CI verification and preliminary PR review;
backup script and restore checklist in branch.

**Blocked:** Render service/configuration inspection (workspace confirmation),
isolated PostgreSQL restore (separate empty test database + authorization),
external calendar verification, and controlled Upstox validation (authorization).

**No change made** to Render services, live feeds, production database, or
GitHub merge state.
