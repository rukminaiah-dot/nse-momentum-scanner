# PR #9 — Release acceptance and handoff

Status checked: 2026-10-18. This is an evidence-based gate ledger, **not** a release approval.
PR: https://github.com/rukminaiah-dot/nse-momentum-scanner/pull/9
Branch: `feature/isolated-recovery-worker-manager-integration` into `feature/atomic-candle-state-prototype`.

## Verified evidence

| Gate | Status | Evidence / boundary |
|---|---|---|
| V2 frontend Preview and page navigation | PASS — UI only | Commit `db56a7b` Vercel check passed and browser screenshots confirmed page navigation; follow-up `40e96a5` adds an explicit notice when the Preview has no scanner API connection. No market data verified. |
| Offline Preview API contract | PASS — offline only | Commit `ceb8535` adds a read-only fixture API and Vercel `/api/v2/*` rewrite. CI run [39088973939](https://github.com/rukminaiah-dot/nse-momentum-scanner/actions/runs/39088973939) passed both UI and offline API contract steps. Isolated Render service [`nse-v2-offline-preview`](https://nse-v2-offline-preview.onrender.com/health) is live; `/health` and `/api/v2/preview-status` confirmed `OFFLINE_PREVIEW_NO_MARKET_DATA`, disconnected market data, and disabled order execution. Vercel Preview deployment is marked Ready, but the route could not be smoke-tested in this browser because Vercel redirected to login. No live-data verification performed. |
| Read-only live API integration | PASS — wiring; live ticks pending | Commit `d5c02ba` replaces the broad Preview proxy with five explicit read-only scanner routes to the existing API. The UI contract test passed in run [39090777791](https://github.com/rukminaiah-dot/nse-momentum-scanner/actions/runs/39090777791); latest Vercel deployment is marked Ready. Direct upstream scorecard request returned `MARKET_CLOSED` with no fresh tick coverage on 2026-10-18; this confirms the historical response path only, not live-session data. The Vercel proxied route could not be browser-smoke-tested here because Preview access redirected to Vercel login. No production API configuration, credentials, or order routes were changed. |
| Atomic Candle State CI | PASS | [run 38950575459](https://github.com/rukminaiah-dot/nse-momentum-scanner/actions/runs/38950575459), latest checked commit `192faf9` |
| Worker Manager Integration CI | PASS | [run 38950575542](https://github.com/rukminaiah-dot/nse-momentum-scanner/actions/runs/38950575542), latest checked commit `192faf9` |
| Synthetic scanner decision regression | PASS (limited scope) | Source-extracted calculation/decision paths; synthetic inputs, not full scanner lifecycle or approved replay |
| Recovery/update race regression | PASS (limited scope) | Same-session rollover, cross-session rejection, aliasing and duplicate concurrent recovery; isolated manager |
| Synthetic snapshot and merge benchmarks | RECORDED | See `docs/candle-history-retention-performance-review.md`; no agreed release SLO |
| Multi-thread contention benchmark | RECORDED — RISK | [run 38950035431](https://github.com/rukminaiah-dot/nse-momentum-scanner/actions/runs/38950035431): 8 threads / 200 symbols / 1950 bars, update p95 103.4829 ms, p99 126.8856 ms |
| Retention cap safety | NOT ACCEPTED | Short caps can alter EMA and signal decisions; default cap remains `None`, scanner cap not activated |
| Read-only historical acquisition and offline trace | PASS — TRACE ONLY | [PR9 historical replay workflow run #5](https://github.com/rukminaiah-dot/nse-momentum-scanner/actions/workflows/pr9-historical-replay.yml): 2026-10-15 through 2026-10-16, `NSE_EQ|INE974X01010`, `stock`, 750 candles reported by the successful exporter in preceding run #4; run #5 passed the fetch-and-trace step and overall workflow (16 s). Raw candles and trace remained temporary on the runner and were deleted, not published as artifacts. Exact run #5 summary counts/hash not independently captured. |\n| Independent historical decision parity | BLOCKED | Real-data offline trace ran successfully, but no separately produced expected scanner decision baseline, discrepancy report, or owner sign-off. A successful trace is not parity acceptance. Production preload logs confirm acquisition but contain no OHLCV rows. |
| Full scanner lifecycle parity | BLOCKED | Synthetic source extraction excludes complete runtime, persistence, staleness and order boundaries |
| Representative performance acceptance | BLOCKED | Requires owner-approved load model, latency threshold, and measurements |
| Independent review | BLOCKED | No approvals recorded on PR at status check |
| Branch protection | CONFIRMED ABSENT — repository setting | User-provided screenshot of repository Settings → Branches shows “Classic branch protections have not been configured”; the repository rulesets API returned `[]` on 2026-10-18. No classic branch protection rules or repository rulesets were found. The direct branch-protection API 403 is a GitHub integration scope limitation, not evidence of a configured rule. |
| Merge | NOT DONE | PR open/draft |

## 2026-10-18 Preview integration update

- Latest UI/API wiring commit: `e79a74e0e80ecb1c67591bf4e62023cd2ddfb474`.
- GitHub UI contract, atomic candle-state, and worker-manager workflows all passed at this commit: [UI contract](https://github.com/rukminaiah-dot/nse-momentum-scanner/actions/runs/39096086055), [atomic state](https://github.com/rukminaiah-dot/nse-momentum-scanner/actions/runs/39096086054), [worker manager](https://github.com/rukminaiah-dot/nse-momentum-scanner/actions/runs/39096086076). Vercel reported the Preview deployment complete.
- Mobile navigation now shows all five tabs, rejects invalid page IDs without blanking the app, and times out stalled API requests after 12 seconds.
- The five scanner/feed GET routes remain wired to the existing live API. `preview-status` aliases the read-only feed-health endpoint. `decision-learning`, `pnl-history`, and `signal-activity` are routed to the isolated offline Preview API, avoiding missing-route responses while returning explicit offline or storage-unavailable states.
- Isolated Render Preview deployment `dep-dba4clh124ks73e8dfdg` is live at the same commit and runs only `v2.backend.offline_preview_api`. It has no market data, broker, database, or order-execution path. This does not create or verify recorded history.
- No browser-driven smoke test of the Vercel page or live-market check was performed. Verify the market feed and completed candles during the Monday session; keep this PR draft and unmerged pending the existing release gates.

## Required actions and decision owners

1. **Replay owner / data custodian:** supply an authorized, sanitized historical dataset, expected decision outputs, replay environment and permission to use it offline. Record provenance, sessions, symbols, missing-minute behavior, and acceptance criteria. Never ingest unapproved private or broker data.
2. **Scanner owner:** verify end-to-end warmup, session rollover, staleness, market regime routing, persistence boundary and order safety against the approved replay. Record a signed-off parity report; do not claim parity from the extracted-source test alone.
3. **Performance owner:** specify realistic symbol count, feed rate, number of workers, hardware, acceptable p95/p99 update latency and recovery workload. Evaluate the measured 103.48 ms update p95 and 126.89 ms p99 under the synthetic heavy case. Record a pass/fail against the agreed thresholds, not against an invented target.
4. **Retention owner:** decide whether a history cap is necessary and define an indicator-equivalent retention/seeding policy. Existing evidence shows 60/200-bar caps can change EMA/signal outcomes; **do not enable a cap without explicit acceptance**.
5. **Independent reviewers / repository maintainers:** inspect code and evidence, provide genuine review decisions, and decide whether branch protection should be configured before marking ready or merging. No classic protections or repository rulesets are currently configured. Do not self-approve or infer approval from green CI; do not add branch rules without an owner-selected policy.

## Release decision

**HOLD / keep draft and unmerged.** CI and the read-only historical acquisition/trace are green, but independent historical decision parity, lifecycle parity, performance acceptance, retention approval and independent review are outstanding. Branch protection was checked and is absent; repository maintainers must decide whether to configure it before merge. No live trading, broker configuration, production database or retention activation is authorized by this checklist.

## Scope control

Do not add further synthetic tests merely to increase test count. New tests or implementation changes should be tied to a documented failing gate or reviewer finding. Keep existing defaults and live behavior unchanged until acceptance is explicit.


## 2026-10-18 Assistant local-only update

- Gemini API calls and the server-side proxy were removed from the Preview branch. No API key or AI provider is required.
- The assistant keeps local app-data validation, candle-based stock explanations, read-only answers from the loaded AI Learning · Loss Review summary, and reviewable GitHub modification requests. It cannot edit learning data, model settings or BUY/SELL rules.
- General or current outside questions show an optional Google Search link. The query leaves the app only if the user taps that link.
- The Five-Page UI Contract Tests pass at `c597ea3` ([run 39103314273](https://github.com/rukminaiah-dot/nse-momentum-scanner/actions/runs/39103314273)); Atomic Candle State ([run 39103314257](https://github.com/rukminaiah-dot/nse-momentum-scanner/actions/runs/39103314257)) and Worker Manager Integration ([run 39103314270](https://github.com/rukminaiah-dot/nse-momentum-scanner/actions/runs/39103314270)) also pass. Vercel Preview is ready. These checks do not verify market data.
- No live-market verification was performed. This does not close historical replay, scanner lifecycle, performance, retention or independent-review gates; keep PR draft and unmerged.

