# Trump Mention Event Study — Baseline-Corrected Findings

**Date**: 2026-06-03 (same-day follow-up to PR55) • **PR**: #56
**Status**: Pipeline + baseline column shipped. NER expanded with CEO names. Re-extraction pending.

## What changed from PR55

PR55's headline numbers were **uncontrolled** — pooled forward 5d return
of +0.13% looked weak, the negative-sentiment cell +1.19% looked
promising. Both were missing the regime baseline.

PR56 adds `compute_baseline_forward(bars, horizon)` — the unconditional
per-ticker mean of `close[T+h] / open[T] − 1` over every valid trading
day in the same window — and surfaces a **baseline** + **excess** column
in `bloasis research mentions-study`.

`excess = mention_forward − baseline` is the honest mention-driven edge.

## Baseline-corrected results (h = 5d, since 2024-01-01)

### Pooled (all sentiment)

```
                 n   fwd     baseline  excess
in_hours        58  -1.28%   +0.74%   -2.02%
after_hours     22  +1.51%   +0.76%   +0.75%
overnight      118  +0.72%   +0.63%   +0.10%
weekend         41  -0.29%   +0.50%   -0.79%
pooled         239  +0.13%   +0.64%   -0.51%
```

The average Trump mention **underperforms baseline by ~0.5%** over 5 days.
The "barely positive" raw forward was regime drift on a tech-mega-cap
basket in a bull window. Net edge: negative.

### Sentiment = NEGATIVE (n=103)

```
                 n   fwd     baseline  excess
in_hours        24  +0.56%   +0.66%   -0.10%
after_hours     11  +2.02%   +0.62%   +1.40%   ← real edge
overnight       50  +1.78%   +0.59%   +1.19%   ← real edge
weekend         18  -0.14%   +0.41%   -0.55%
pooled         103  +1.19%   +0.58%   +0.61%
```

**The negative-mention edge survives baseline-adjustment but shrinks ~50%.**
PR55's "+1.19% pooled" → +0.61% real excess. Concentrated in out-of-hours
posts (overnight + after_hours), where the structural gap-decomposition
model predicts the most retail-feasible move.

### Sentiment = POSITIVE (n=81)

```
                 n   fwd     baseline  excess
in_hours        15  -1.28%   +0.78%   -2.05%
after_hours      7  +1.26%   +1.08%   +0.18%
overnight       46  +0.16%   +0.72%   -0.56%
weekend         13  -2.83%   +0.48%   -3.30%
pooled          81  -0.49%   +0.72%   -1.22%
```

Confirmed bad — every bucket negative or barely positive. Stocks Trump
praises lose to baseline by −1.22% over 5d on average. This is the
"buy-the-pump-sell-the-reversion" pattern the literature documents.

## What this changes operationally

PR55's "ambiguous middle" → **narrowed conclusion**:

- The pooled signal is negative (Trump mention basket underperforms).
- Negative-sentiment out-of-hours posts (overnight + after_hours, n=61)
  show a +1.2 to +1.4% excess. This is the only candidate edge.
- Positive-sentiment posts have negative excess across every bucket.

The "negative criticism → mean reversion" hypothesis from PR55 is
**partially confirmed**: out-of-hours yes, but in-hours (the trader's
natural follow-on-the-news case) shows essentially zero excess (−0.10%).
The post needs to break a session boundary to matter.

## PR56 scope (this PR)

1. **`compute_baseline_forward()`** in `bloasis/analysis/mention_event_study.py`
2. **`summarize_decomposed()`** extended — when rows carry a `baseline`
   field, returns `mean_baseline` + `mean_excess`. Backward compatible.
3. **`bloasis research mentions-study`** CLI — new `baseline` + `excess`
   columns. Per-ticker baseline computed once and cached, attached to
   every event row.
4. **`NAME_TO_TICKER`** expanded with 13 CEO/founder names: bezos→AMZN,
   zuckerberg/zuck→META, tim cook→AAPL, elon/elon musk→TSLA, jensen
   huang→NVDA, sundar pichai→GOOGL, satya nadella→MSFT, jamie dimon→JPM,
   warren buffett→BRK-B, larry fink→BLK, andy jassy→AMZN.
   Single-token names only added when they don't collide with prose
   (`bezos`, `zuckerberg`, `elon` safe; `cook`, `jensen`, `huang`
   require full phrase).
5. **`extractor_version`** bumped 2 → 3. Composite PK on
   `(post_id, ticker, extractor_version)` means v3 re-extraction
   accumulates new CEO-name mentions without overwriting v2 rows.

## Tests

15 new (24 total in the two files):

- 9 prefilter tests in `tests/test_mention_pipeline.py` — CEO matches
  + collision-safety (bare `jensen` / `cook` must NOT match) +
  extractor_version v3 contract.
- 6 baseline tests in `tests/test_mention_event_study.py` — basic mean,
  horizon=2, too-few-bars (returns 0), zero-open filter, mean_baseline
  + mean_excess in summary, backward-compat when baseline absent.

744 passed / 84.69% coverage / mypy clean / ruff clean.

## v3 re-extraction — results (same day, 2026-06-03 18:30 KST)

Reset all `social_posts.mentions_extracted_at` for posts ≥ 2024-01-01
(15,708 posts), re-ran `bloasis research mentions-extract` end-to-end
against the v3 NAME_TO_TICKER (CEO/founder names included). Took
~40 min on llama3.2:3b.

**Result: 342 v3 mentions vs 261 v2 mentions (+81, +31%).** Bigger
sample, more out-of-hours bucket counts, edge SURVIVES.

### Pooled (all sentiment, n=558 — was 239 v2)

```
                 n     fwd     baseline  excess
in_hours        141  -1.46%   +0.75%   -2.20%
after_hours      54  +1.37%   +0.78%   +0.58%
overnight       268  +0.62%   +0.66%   -0.04%
weekend          95  -0.15%   +0.55%   -0.69%
pooled          558  +0.04%   +0.67%   -0.64%
```

(n grew faster than mentions because each event now appears in multiple
events when a single post matches multiple tickers — e.g. "Bezos and
Zuckerberg are…" = 2 events.)

### Sentiment = NEGATIVE (n=222 — was 103)

```
                 n     fwd     baseline  excess
in_hours         53  +0.51%   +0.68%   -0.17%
after_hours      24  +2.31%   +0.63%   +1.68%   ← strengthened
overnight       105  +1.83%   +0.60%   +1.23%   ← stable at 2x n
weekend          40  +0.50%   +0.45%   +0.05%
pooled          222  +1.33%   +0.60%   +0.73%
```

**The headline finding survives the 2x sample expansion:**
- after_hours negative: +1.40% (v2 n=11) → **+1.68%** (v3 n=24). Edge
  STRENGTHENED with more data.
- overnight negative: +1.19% (v2 n=50) → **+1.23%** (v3 n=105). Edge
  STABLE with sample doubling.
- Combined neg + OOT (after + overnight): 129 events, mean excess
  ≈ +1.32%. This is the cleanest cell.

n=129 with mean excess ~+1.3% per 5d is ~2-3σ from zero under reasonable
variance assumptions — first quantitatively defensible Trump-mention
edge claim in this codebase.

### Sentiment = POSITIVE (n=194 — was 81)

```
                 n     fwd     baseline  excess
in_hours         37  -0.47%   +0.79%   -1.27%
after_hours      18  +0.91%   +1.06%   -0.16%
overnight       110  -0.17%   +0.76%   -0.92%
weekend          29  -2.01%   +0.52%   -2.53%
pooled          194  -0.40%   +0.76%   -1.16%
```

**Confirmed bad with bigger n.** Stocks Trump praises lose to baseline
by −1.16% over 5d on average (was −1.22% at v2 n=81). Every bucket
negative or flat. The "buy Trump-pumps" pattern is genuinely loss-making.

## What is now blocking a real edge claim

Down to one — sample size is no longer the issue:

1. **~~Sample size~~** — RESOLVED at v3. Negative + OOT cell is n=129
   with +1.3% excess.
2. **Out-of-sample drift.** 2024-2026 was one regime (tech mega-cap bull
   + Trump 2.0 active term). The paper-trading session
   `edgar-rolling2-paper-2026-05` accumulates OOS data; we should run
   the same study forward against a separate prospective window
   Q3-Q4 2026. The signal must replicate forward to be claimable as
   edge rather than backtest artifact.

## Proposed next step (separate PR / research direction)

**Forward-tracking real-time signal log:**
- Cron-fetch Truth Social archive daily (already in pipeline via
  `mentions-fetch`).
- For each NEW negative + OOT mention, write the model-predicted
  excess (~+1.3%) + the actual realized 5d excess from yfinance.
- 3 months of forward data (Jun-Sep 2026) accumulates ~30-50 events.
- If realized > 0 stays close to +1% — strategy. If collapses to zero —
  falsified.

Bloasis Phase 2 candidate.

We are no longer constrained by "missing baseline". The baseline column
is here.

---

# 2026-06-04 follow-up — PR57 ships + bucket-classification bug fixed

## What changed: the SQLite tz-strip silent shift

PR57 (forward-tracking harness) surfaced a pre-existing bug that the
PR55/56 retrospective ran under. SQLite + SQLAlchemy
`DateTime(timezone=True)` strips tzinfo on round-trip. Downstream
`classify_mention_timing(.).astimezone(ET)` on the naive value used the
system tz — and the Mac Mini that ran the studies is on KST (UTC+9).
Every bucket assignment shifted by ~13 hours.

The fix (defensive normalization `if ts.tzinfo is None: ts =
ts.replace(tzinfo=UTC)` at `classify_mention_timing` and
`entry_open_date`) shipped in PR57. The corrected bucket classification
re-ran on the same v3 corpus through the new `mention_predictions`
table today as a smoke-test of the cron — settled 52 of 53 immediately
since most entry_date + 5d windows had already passed.

## Corrected retrospective on PR55/56's same v3 corpus

```
                  predicted  realized        n
                  excess     excess
after_hours       +1.32%     +0.32%          33
overnight         +1.32%     +0.82%          19
combined          +1.32%     +0.50%          52
```

(One row still pending — entry_date + 5d not yet in OHLCV.)

**The +1.32% number from earlier in this doc was overstated.** With
corrected buckets, the same retrospective on the same corpus reports
~+0.50% pooled excess on neg + OOT. Roughly 38% of the original signal
survives; the rest was tz-shift artifact misallocating events between
buckets.

Why this still matters as a candidate edge:
- +0.50% per 5d is not nothing — annualized that's ~12% if every week
  triggered, but only ~5-10 events fire per month so the realistic
  contribution is much smaller, and we're still inside variance bands
  at n=52.
- The directional pattern (negative criticism → mean-reversion-driven
  positive excess) holds, just at half the magnitude.
- overnight beats after_hours (+0.82% vs +0.32%) — consistent with the
  gap-decomposition theory that more closed-market reaction time gives
  the retail entry-at-open more residual to capture.

## Honest interpretation

- **PR56's "first quantitatively defensible edge" claim → withdrawn at
  +1.32%.** Restated at ~+0.50% pooled excess, n=52 corrected.
- The cell-level sentiment story (negative > positive) remains valid
  qualitatively, but magnitudes shrink across the board.
- The same posts that landed in v3 with the bug are now correctly
  classified going forward — the prediction table freezes per-row
  bucket assignments at write time, so PR57's per-row records are
  immune to future re-classification bugs.

## Genuinely prospective measurement still pending

Today's 52 settled rows are NOT forward-tracking. They are corrected
retrospective on existing posts that the cron happened to discover for
the first time. Real prospective evidence accumulates from posts whose
entry_date + 5d is in the future *as of the cron run*. Today 1 pending.

The launchd job runs Mon-Fri 09:00 KST going forward. After ~3 months
the report rows for truly forward predictions will be a meaningful
fraction of the total and the +0.50% corrected baseline is what they'll
be measured against.

If realized excess on truly-forward rows tracks +0.50% — modest
strategy candidate. If it collapses toward zero or negative — even the
half-strength PR56 claim falsifies.
