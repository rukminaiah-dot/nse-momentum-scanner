# PR #9 — Release acceptance and handoff

Status checked: 2026-10-19. This is an evidence-based gate ledger, **not** a release approval.
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
| Read-only historical acquisition and offline trace | PASS — TRACE ONLY | [Workflow run #5](https://github.com/rukminaiah-dot/nse-momentum-scanner/actions/runs/38958470845), job `offline-historical-trace` (job ID `117167202498`), completed successfully on 2026-10-16 UTC. Job logs confirm the read-only exporter saved 750 Upstox candles and the offline trace completed. The run inputs are documented as 2026-10-15 through 2026-10-16, `NSE_EQ|INE974X01010`, `stock`. Raw CSV and trace were deleted from temporary runner storage. Run logs do not expose the resulting trace checksum/count summary, so there is no retained replay artifact. This is trace evidence only, not parity acceptance. |\n| Independent historical decision parity | BLOCKED | Real-data offline trace ran successfully, but no separately produced expected scanner decision baseline, discrepancy report, or owner sign-off. A successful trace is not parity acceptance. Production preload logs confirm acquisition but contain no OHLCV rows. |
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
- The Five-Page UI Contract Tests pass at `afaded6` ([run 39103540498](https://github.com/rukminaiah-dot/nse-momentum-scanner/actions/runs/39103540498)), including executable sample and empty-state checks for the learning-summary response. Atomic Candle State ([run 39103540497](https://github.com/rukminaiah-dot/nse-momentum-scanner/actions/runs/39103540497)) and Worker Manager Integration ([run 39103540518](https://github.com/rukminaiah-dot/nse-momentum-scanner/actions/runs/39103540518)) also pass. Vercel Preview is ready. These checks do not verify market data.
- No live-market verification was performed. This does not close historical replay, scanner lifecycle, performance, retention or independent-review gates; keep PR draft and unmerged.

## 2026-10-18 Isolated scanner tick lifecycle regression
- Commit `31e91eb821f0732db5d01de04fa862df4e0150cc` adds `tests/test_scanner_tick_lifecycle.py`, which AST-selects and executes the real `on_tick` function without importing scanner startup or connecting external services.
- The isolated test checks malformed, stale and future tick rejection without feed, candle, volume or active-position mutation; a simulated position advances through Target 1 and closes at Target 2; live candle rollover orders recovery request, candle-quality write and analysis.
- Worker Manager Integration [run 39110462037](https://github.com/rukminaiah-dot/nse-momentum-scanner/actions/runs/39110462037), Atomic Candle State [run 39110462025](https://github.com/rukminaiah-dot/nse-momentum-scanner/actions/runs/39110462025), and Five-Page UI Contract [run 39110462065](https://github.com/rukminaiah-dot/nse-momentum-scanner/actions/runs/39110462065) passed. The new lifecycle test is step 24 in the worker job. Vercel Preview is marked Ready.
- This is a limited scanner tick-handler regression using fake storage and trade functions. It does not test the full scanner process, real persistence, Upstox connectivity, broker/order boundaries, or independent expected-decision parity. The full lifecycle parity gate remains **BLOCKED** pending an isolated end-to-end environment and owner-approved evidence. No live data was verified; no deployment or production settings changed.

## 2026-10-18 Malformed price guard
- Commit `1c0bdf0a005767ffd116d8fb35d1b8ec5d4dfe54` hardens the live tick handler to convert incoming prices to finite positive numbers before feed-health, trade-state, volume or candle updates. Invalid strings, NaN, infinities, zero and negative prices are discarded.
- The isolated scanner tick lifecycle test now verifies invalid-price and invalid-timestamp rejection, Target 1 → Target 2 position lifecycle, and rollover call order. Worker Manager Integration [run 39110632378](https://github.com/rukminaiah-dot/nse-momentum-scanner/actions/runs/39110632378), Atomic Candle State [run 39110632482](https://github.com/rukminaiah-dot/nse-momentum-scanner/actions/runs/39110632482), and Five-Page UI Contract [run 39110632611](https://github.com/rukminaiah-dot/nse-momentum-scanner/actions/runs/39110632611) passed; Vercel Preview is Ready.
- The lifecycle evidence remains isolated/source-executed with fake side effects; full scanner-process, persistence, broker boundary, historical decision parity and owner review gates remain open. No live market data was checked and no production behavior was deployed.

## 2026-10-18 Cumulative volume validation
- Commit `4df9fa127f82078150b1ec07c3c4e80a400690b2` validates cumulative-volume values before converting or updating the per-symbol baseline. Nonnumeric, non-finite, negative, and overflowing values are ignored for that tick; valid price processing continues with zero minute volume.
- The scanner tick lifecycle test covers malformed volume values and confirms they neither crash the callback nor poison the baseline. Worker Manager Integration [run 39112602992](https://github.com/rukminaiah-dot/nse-momentum-scanner/actions/runs/39112602992), Atomic Candle State [run 39112602959](https://github.com/rukminaiah-dot/nse-momentum-scanner/actions/runs/39112602959), and Five-Page UI Contract [run 39112602973](https://github.com/rukminaiah-dot/nse-momentum-scanner/actions/runs/39112602973) passed; Vercel Preview is Ready.
- This closes the identified malformed-volume callback risk only. Full lifecycle parity, historical-decision acceptance, approved performance criteria, independent review and any live-data verification remain open or out of scope. The PR remains draft and unmerged.


## 2026-10-19 completion pass

- **Read-only live API and Vercel route integration:** at 11:21 IST, all four core GET routes returned HTTP 200 through both upstream Render and the Vercel project domain; 203 scanner rows were present, the stock board had 195/200 fresh candles, and the sampled rating sets matched scanner symbol, signal, and candle timestamp. Feed health reported 200/200 recent ticks; ratings remained research-only with volume unverified and order execution disabled. This is shape/alignment evidence, not a price-accuracy guarantee.
- **Independent index spot check:** at 11:33 IST, official NSE values and app completed candles were close for NIFTY 50 and NIFTY BANK; both previous-close values matched exactly. The quote and candle timestamps were asynchronous, so exact OHLCV parity is still open. The BSE page returned HTTP 403 from this environment; SENSEX independent parity is not verified.
- **Known restart-preload defect fixed on the draft branch:** scanner startup now retains all unique completed current-session candles rather than only the last 60, while still excluding the forming candle. Restart regression compares exact EMA9/EMA20, momentum, trend and signal results through a 375-candle synthetic session. At code commit `14d36dc`, Worker Manager Integration run 743, Atomic Candle State run 452, and Five-Page UI Contract run 448 passed.
- **Current CI:** all three workflows passed again on the latest check commit `2157c0b` (Worker Manager run 747, Atomic run 454, UI run 452); Vercel check reported success. The protected Preview browser still redirects to Vercel login in this environment, so a rendered-page smoke check is open.
- **Release hold remains:** no approved historical dataset / expected decision output or performance threshold was attached during this pass; full live scanner lifecycle parity, exact OHLCV verification for all three indices, independent review, performance acceptance, branch-policy decision, and explicit merge/deploy approval remain open. PR #9 remains draft and unmerged. No production deployment, broker credential, database mutation, retention activation, or order execution occurred.


### 11:44 IST scanner universe audit

- Repeated the four upstream read-only GET checks; all returned HTTP 200. Feed health was `REPORTING`, 200/200 recent ticks, 0.5-second snapshot age, and order execution disabled.
- Scanner response had 203 unique symbols, including all three index rows timestamped 11:43 IST. The stock board had exactly 200 unique rows; every board symbol was present in the scanner response. Reported and independently recomputed fresh stock rows both equaled 198/200 under the UI's 180-second rule; there were no status discrepancies or invalid/nonpositive prices.
- All 3 returned candle ratings aligned with scanner symbol, signal and candle time; stock ratings were on fresh board rows. All ratings remained `RESEARCH_ONLY` with `volume_verified=false`; order execution was disabled.
- This is a point-in-time upstream universe/contract check. It does not replace approved historical replay, sustained lifecycle/performance testing, BSE SENSEX quote parity, or browser-render verification of the protected feature Preview.


- The 11:44 stock-board symbol set was also compared directly with the PR branch's `NIFTY_200` universe: 200/200 symbols matched exactly, with no missing, unexpected, or duplicate symbols. The 203-row scanner response contained 203 unique symbols.
- Additional UI history routes were checked at origin: offline Preview `/health`, `/api/v2/decision-learning`, `/api/v2/pnl-history`, and `/api/v2/signal-activity` all returned HTTP 200 after cold start. They correctly reported no market data / no configured history. The live GET-only `/api/v2/trades` route returned HTTP 200. The current production Vercel deployment returned 404 for the newer offline-history paths because those rewrites belong to the draft Preview branch; the latest Vercel Preview is marked Ready but protected from this unauthenticated browser session.


### 11:51 IST candle-quality and candidate-rank check

- `/api/v2/candle-feed-quality` returned HTTP 200: 200/200 recent ticks, 200/200 positive last-candle volumes, and 196/200 stocks with six consecutive completed candles today; 4 were flagged for a missing minute, none for overnight gaps or warmup. Order execution was disabled.
- `/api/v2/top-momentum-setups` returned HTTP 200 with `NO_QUALIFYING_SETUPS`: 196 fresh stock rows considered and 4 stale rows rejected. This is an explicit empty result, not a failed request or fabricated ranking.
- These quality/ranking endpoints reinforce the UI's stale-data suppression. They do not validate comparative RVOL, external liquidity, or exact signal accuracy.


### 12:27 IST live scanner and UI-proxy recheck

- Production Vercel proxy returned HTTP 200 for `/api/v2/nifty200-feed-health`, `/api/v2/scanner`, and `/api/v2/nifty200-stock-board`; the upstream Render API returned HTTP 200 for all checked routes, including candle quality and top momentum setups.
- Feed health: `REPORTING`, 200/200 NIFTY 200 stocks with recent ticks, snapshot age 5.2 seconds; order execution disabled. Scanner returned 203 rows (200 stocks + 3 indices), latest row timestamp 12:26 IST. Board reported 199/200 fresh stock rows.
- Candle quality reported 199/200 stocks with six consecutive completed candles, 200/200 with recent ticks and positive last-candle volume, one missing-minute stock, zero overnight gaps and zero warmup rows. Top setups returned `NO_QUALIFYING_SETUPS` (199 fresh considered, 1 stale rejected); no ranking was fabricated.
- These checks verify live response shape, route wiring and freshness at one time. Feed `REPORTING` does not guarantee a continuous connection; the one stale stock remains excluded. RVOL/volume-surge ranking and persisted P&L/history remain unavailable. Historical real-data trace remains completed, while expected-decision parity and owner sign-off remain blocked. No production settings, databases, orders or deployments were changed.
