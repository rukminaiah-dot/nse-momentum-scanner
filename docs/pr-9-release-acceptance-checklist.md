# PR #9 — Release acceptance and handoff

Status checked: 2026-10-17. This is an evidence-based gate ledger, **not** a release approval.
PR: https://github.com/rukminaiah-dot/nse-momentum-scanner/pull/9
Branch: `feature/isolated-recovery-worker-manager-integration` into `feature/atomic-candle-state-prototype`.

## Verified evidence

| Gate | Status | Evidence / boundary |
|---|---|---|
| Atomic Candle State CI | PASS | [run 38950575459](https://github.com/rukminaiah-dot/nse-momentum-scanner/actions/runs/38950575459), latest checked commit `192faf9` |
| Worker Manager Integration CI | PASS | [run 38950575542](https://github.com/rukminaiah-dot/nse-momentum-scanner/actions/runs/38950575542), latest checked commit `192faf9` |
| Synthetic scanner decision regression | PASS (limited scope) | Source-extracted calculation/decision paths; synthetic inputs, not full scanner lifecycle or approved replay |
| Recovery/update race regression | PASS (limited scope) | Same-session rollover, cross-session rejection, aliasing and duplicate concurrent recovery; isolated manager |
| Synthetic snapshot and merge benchmarks | RECORDED | See `docs/candle-history-retention-performance-review.md`; no agreed release SLO |
| Multi-thread contention benchmark | RECORDED — RISK | [run 38950035431](https://github.com/rukminaiah-dot/nse-momentum-scanner/actions/runs/38950035431): 8 threads / 200 symbols / 1950 bars, update p95 103.4829 ms, p99 126.8856 ms |
| Retention cap safety | NOT ACCEPTED | Short caps can alter EMA and signal decisions; default cap remains `None`, scanner cap not activated |
| Approved historical market replay | BLOCKED | No approved dataset / replay sign-off demonstrated; safe no-database acquisition procedure in `docs/pr-9-historical-replay-acquisition.md` |
| Full scanner lifecycle parity | BLOCKED | Synthetic source extraction excludes complete runtime, persistence, staleness and order boundaries |
| Representative performance acceptance | BLOCKED | Requires owner-approved load model, latency threshold, and measurements |
| Independent review | BLOCKED | No approvals recorded on PR at status check |
| Branch protection and merge eligibility | UNVERIFIED | No verified branch-protection decision or completed acceptance approvals |
| Merge | NOT DONE | PR open/draft |

## Required actions and decision owners

1. **Replay owner / data custodian:** supply an authorized, sanitized historical dataset, expected decision outputs, replay environment and permission to use it offline. Record provenance, sessions, symbols, missing-minute behavior, and acceptance criteria. Never ingest unapproved private or broker data.
2. **Scanner owner:** verify end-to-end warmup, session rollover, staleness, market regime routing, persistence boundary and order safety against the approved replay. Record a signed-off parity report; do not claim parity from the extracted-source test alone.
3. **Performance owner:** specify realistic symbol count, feed rate, number of workers, hardware, acceptable p95/p99 update latency and recovery workload. Evaluate the measured 103.48 ms update p95 and 126.89 ms p99 under the synthetic heavy case. Record a pass/fail against the agreed thresholds, not against an invented target.
4. **Retention owner:** decide whether a history cap is necessary and define an indicator-equivalent retention/seeding policy. Existing evidence shows 60/200-bar caps can change EMA/signal outcomes; **do not enable a cap without explicit acceptance**.
5. **Independent reviewers / repository maintainers:** inspect code and evidence, provide genuine review decisions, confirm branch protection, then decide whether to mark ready and merge. Do not self-approve or infer approval from green CI.

## Release decision

**HOLD / keep draft and unmerged.** CI is green, but replay, lifecycle parity, performance acceptance, retention approval, independent reviews and branch-protection verification are outstanding. No live trading, broker configuration, production database or retention activation is authorized by this checklist.

## Scope control

Do not add further synthetic tests merely to increase test count. New tests or implementation changes should be tied to a documented failing gate or reviewer finding. Keep existing defaults and live behavior unchanged until acceptance is explicit.
