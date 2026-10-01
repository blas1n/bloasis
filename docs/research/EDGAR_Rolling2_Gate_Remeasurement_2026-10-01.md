# `edgar-rolling2` gate re-measurement and founder decision (2026-10-01)

Point-in-time record. Per `docs/research/README.md`, measurement logs are not
updated after the fact — if these numbers move, write a new document.

Issue: [#85](https://github.com/blas1n/bloasis/issues/85). Measured while
fixing [#83](https://github.com/blas1n/bloasis/issues/83).

## Protocol

Canonical 7-fold walk-forward, identical for every arm below:

- Grid/protocol file: `configs/grids/pr21-edgar-rolling.yaml`
- Window: 2022-01-01 .. 2024-10-17, train 180 / test 120 / step 120 → 7 folds
- Universe: `sp500_at:2024-12-31` (resolved to 487 tradable names today)
- Same OHLCV parquet and same EDGAR cache for the before/after arms

## Verdict

| arm | folds | α/yr | sharpe vs SPY | median max-DD ratio | trades |
|---|---|---|---|---|---|
| documented baseline (2026-05-09, config header) | 7 | +4.09% | 1.334 | 0.80 **PASS** | ~440 |
| 2026-10-01, pre-#83 code | 7 | +5.62% | 1.107 | **0.883 FAIL** | 394 |
| 2026-10-01, post-#83 code (shipped) | 7 | +3.74% | 1.013 | **0.873 FAIL** | 398 |

Gate (`docs/mission.md`, live-trading entry; the config's
`acceptance_criteria` carries the paper variant):

| criterion | bar | measured 2026-10-01 | |
|---|---|---|---|
| walk-forward folds | ≥ 5 | 7 | PASS |
| median α annualized | ≥ −0.5% | +3.74% | PASS |
| median sharpe vs SPY | ≥ 1.0 | 1.013 | PASS |
| median max-DD ratio to SPY | ≤ 0.85 | 0.873 | **FAIL** |

**`configs/edgar-rolling2.yaml` no longer clears the gate.** Drawdown is the
only failing criterion, and it fails by 0.023.

## Cause: data drift, not a code regression

The #83 extraction fix is not responsible — the pre-#83 code measures a
*worse* DD (0.883) on the same universe and the same OHLCV parquet. #83 moves
DD slightly in the right direction (0.883 → 0.873) at a cost of −0.094 sharpe
and −1.88pp α.

What changed since 2026-05:

- resolved universe is 487 names vs 490 (delistings/renames)
- yfinance has re-adjusted historical prices
- four months of new 10-Ks have entered the rolling 5-year window

## Founder decision (2026-10-01)

**Paper trading continues while DD-reduction research runs.** The failing
drawdown gate is recorded rather than acted on by shutdown: the paper track
record is evidence accumulation, and stopping it would discard the 6-month
series that `docs/mission.md` requires as the input to the real-money
decision. Real money remains blocked — it was already blocked, and this
measurement does not change that.

`configs/edgar-rolling2.yaml`'s live parameters are deliberately unchanged by
this record. Only the rotted gate claim in its header was corrected.

## Follow-up

DD-reduction research, scoped in #85: re-measure the regime overlay and
position sizing/concentration **against drawdown specifically**. `docs/roadmap.md`
records the regime overlay as falsified, but it was falsified on *returns* — it
has never been evaluated against the drawdown criterion, which is the only one
failing.
