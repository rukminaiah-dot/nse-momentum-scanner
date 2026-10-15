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

**Blocked:** dedicated staging configuration and authorization,
isolated PostgreSQL restore (separate empty test database + authorization),
external calendar verification, and controlled Upstox validation (authorization).

**No change made** to Render services, live feeds, production database, or
GitHub merge state.

## Confirmed Render inventory (read-only, operator approved workspace)

Workspace: `My Workspace` (confirmed by operator).

| Service | Branch | Auto-deploy | Latest deploy |
| --- | --- | --- | --- |
| `nse-momentum-scanner` static site | `main` | yes, on commit | live, 2026-10-01, `c0b743d` |
| `nse-momentum-scanner-api` Python web service | `main` | yes, on commit | live, 2026-10-14, `0b3c595` |
| `nse-long-term-investment-preview` Python web service | `feature/long-term-investment-tab` | no | live, 2026-10-11, `f1c7f19` |

Production static-site root directory: `nse-momentum-scanner`;
build: `npx expo export --platform web`; publish: `dist`.
Production API root directory: repository root; build:
`pip install fastapi uvicorn yfinance pandas psycopg[binary] upstox-python-sdk`;
start: `./start_v2.sh`. Both production services are publicly reachable
by configuration and track `main`, not PR #5. Both have auto-deploy on
commit; **merging PR #5 to main would therefore be a production-affecting
action**. Do not merge without separate authorization.

The Python API and the investment preview have **no configured HTTP health
check path** in Render service metadata. This is a readiness gap, not proof
the processes are unhealthy. The preview belongs to a separate feature branch
and must not be repurposed for PR #5. No dedicated gap-recovery preview
service was found among the three services.

The listed deploy statuses were `live`; these are Render deployment states,
not independent application-health checks. No deploy, restart, environment
variable edit, or database operation was performed.

## Remaining Phase 5 controls

- A dedicated read-only gap-recovery staging service and isolated database
  are not confirmed. Creating either needs separate authorization.
- Confirm a health-check route and operational alerting strategy before any
  approved staging deployment.
- Confirm a safe rollback plan (revert/previous deploy) with a human operator.
- Review environment variable *names* and secret management without exposing
  values; do not copy production credentials into staging.
- Production `main` auto-deploy must be considered before any eventual merge.
