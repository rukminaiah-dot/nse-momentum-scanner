# NIFTY 50 five-session event rules (research baseline)

Version: `NIFTY50_5SESSION_RULES_V1`
Status: rules are prepared; the forecasting model is **not trained or backtested**.

## 1. Forecast target

At a timestamped cutoff, anchor the event to the latest **verified, completed NSE session close**. Over the next five trading sessions, label the path:

- `UP_ONLY` if the index reaches at least `close + 500` and never reaches `close - 500`.
- `DOWN_ONLY` if it reaches at least `close - 500` and never reaches `close + 500`.
- `BOTH` if it reaches both barriers, regardless of which is first.
- `NEITHER` if neither barrier is reached.

Show the target percentage as `500 / anchor_close × 100`, and display both point levels. Probabilities for +500 and −500 are overlapping events when the `BOTH` outcome occurs; the model must also report `NEITHER` and disclose that overlap. With daily OHLC only, if both barriers are touched in the same session, the intraday order is unknown and must be marked ambiguous.

## 2. Reversal versus continuation

The **500-point movement is the reversal threshold**; the **five trading sessions are the forecast horizon** from the earlier report specification. They are separate conditions. A countertrend setup that has not yet traveled 500 points from the verified anchor close is a reversal watch only, not a confirmed 500-point reversal. Once a threshold is reached, compare its direction with the prior trend: against the trend is a reversal event; with the trend is continuation. A threshold touch by itself does not establish a reversal.

Determine the recent regime from point-in-time daily closes: five-session return and close versus the 20-session trend measure. If they conflict, classify the regime as `MIXED`.

The provisional baseline may report `UP`, `DOWN`, or `NO CLEAR EDGE`; it must not translate an evidence score into a probability. An **upside reversal watch** needs a prior down regime, a completed close above both the prior close and five-session average, plus at least two of these three fresh confirmations: (1) India VIX at or above 25 and falling, (2) same-date DII net buying at least as large as FII/FPI net selling, or (3) bullish relative volume (RVOL) at or above 1.5×. A **downside reversal watch** mirrors this after an up regime: close below both the prior close and five-session average, plus at least two of (1) VIX up at least 5% versus its prior close, (2) same-date FII/FPI cash net selling, or (3) bearish RVOL at or above 1.5×. If neither reversal qualifies, a continuation watch needs price/volume aligned with the recent regime plus two independent fresh confirmations. Otherwise return `NO CLEAR EDGE` or `PENDING INPUTS`. These thresholds are provisional rule candidates, not validated predictors.

## 3. Evidence rules

| Input | Rule | Guardrail |
|---|---|---|
| Price | Use only completed daily OHLC known by cutoff. Measure 1-, 5-, and 20-session trend, range, and close location. | No intraday or later-session candle may leak into a prior forecast. |
| Volume | NIFTY 50 itself has no directly traded cash-index volume. Use a named proxy: constituent breadth/turnover or NIFTY futures volume, compared with its own recent history. RVOL ≥1.5× is a candidate confirmation only. | Store the proxy, denominator, source timestamp, and session date. Do not substitute missing volume with zero or an unrelated stock basket. |
| India VIX | Record value, prior close, change and source timestamp. VIX ≥25 and falling may support an exhaustion/reversal case; a rise ≥5% is a volatility-stress observation. | VIX by itself is not a directional call. A holiday/closed-market quote is historical. |
| FII/FPI and DII | Use same-date NSE cash net flows, including the time they became available. DII positive buying against FII/FPI selling can be described as absorption. | End-of-day flow is not intraday flow. Stale or unpublished rows do not count as current confirmations. |
| P/E | Compare only with a point-in-time history on a consistent earnings basis; show percentile and basis where available. | Descriptive context only. A value such as 18 is not a standalone buy/reversal trigger. Do not bridge the NSE earnings-basis change without adjustment. |
| News and crude | Include only source-timestamped information published by cutoff. Crude direction may be described as a macro channel; headlines remain context unless a reproducible, point-in-time feature is validated. | No after-cutoff headlines, guessed sentiment, invented impact score, or causal claim. |

## 4. Required result and missing-data behavior

Every run records cutoff, anchor close/date, target levels/percentage, source and availability timestamp for each factor, reversal/continuation classification, strongest evidence on both sides, and missing/stale inputs. If the completed close, trend history, or an explicitly named volume proxy is unavailable, do not issue a directional forecast. Missing inputs remain missing; do not backfill with guesses.

The API currently exposes the rule definition and marks probabilities `NOT_BACKTESTED`. It does not yet have the joined ten-year, point-in-time data needed to produce this forecast. The existing current-session reversal watch is a separate rule and must not be described as this five-session model.

## 5. Suggested medium-term sustained-reversal target

For the separate question “could a reversal persist?”, use a 60-trading-session horizon (about three months, a medium-term outlook rather than a multi-year forecast). Set the prior regime using only the 60 completed daily closes available at cutoff: UP when the latest 20-session return is positive and SMA20 is above SMA50; DOWN when both are negative/below; otherwise MIXED.

Label a sustained 500-point reversal only when the close has moved at least 500 points from the anchor against the prior UP/DOWN regime and at least 10 of the final 15 completed closes in the 60-session horizon remain beyond that barrier. If ±500 is touched but the persistence condition fails, label `THRESHOLD_TOUCHED_NOT_SUSTAINED`; if no barrier is reached, label `NO_500_POINT_MOVE`. If the prior regime is MIXED, do not call the move a reversal or continuation. The 10-of-15 persistence threshold is a proposed outcome definition; test it against alternative windows and volatility-scaled targets before treating it as useful.

The live evidence can create a reversal **watch** before this outcome is realized, but it is not a confirmed reversal and has no probability until a backtest supports one. A horizon of 60 sessions is roughly a quarter; a multi-year outlook needs a separate target and validation.

## 6. Validation required before probabilities

Use roughly ten years of daily history where coverage is consistent. Preserve publication/availability times for flows, news, and quotes. Prevent look-ahead and survivorship leakage; keep the final test period untouched. Use chronological walk-forward folds and compare:

1. Historical event base rate and a simple volatility baseline.
2. Interpretable logistic regression.
3. Gradient-boosted trees.

Handle class imbalance using training-fold-only methods. Calibrate using training/validation data only. Report Brier score/log loss, calibration, precision, recall, false alarms, and results by volatility regime. Also compare the fixed ±500-point barrier with percentage- and volatility-scaled barriers. Do not call the model usable if source coverage or out-of-sample performance is inadequate.

`classify_five_session_path` creates outcome labels from five future daily OHLC bars for retrospective evaluation; those future bars must never be used as forecast features.
