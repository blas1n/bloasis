# edgar-rolling2 edge: language or name? — pre-registration and result (2026-10-02)

Point-in-time record. Per `docs/research/README.md`, measurement logs are not
updated after the fact.

Follows [#99](https://github.com/blas1n/bloasis/issues/99) /
`docs/research/Name_Normalization_2026-10-02.md`. Bears on
[#88](https://github.com/blas1n/bloasis/issues/88).

## Why

`edgar-rolling2` was shipped on the "Lazy Prices" hypothesis: firms whose 10-K
risk-factor language changes least outperform. In #99, removing each
registrant's distinctive name forms from those texts took the canonical
backtest (2022-01..2024-10, 7 folds) from α +3.74% to +0.01%. If the edge
moves with how often a company says its own name, the 6-month paper record
cannot answer whether the hypothesis works, so this should be settled before
#88 picks a drawdown bar for it.

That was one in-sample window. This checks two windows the strategy was never
tuned on.

## Pre-registration

Written and committed **before** any window was run.

### Windows (fixed)

| window | span | folds | test periods | universe |
|---|---|---|---|---|
| A | 2018-01-01 .. 2021-12-31 | 10 | 2018-07-01 .. 2021-10-12, all before the canonical tests | `sp500_at:2021-12-31` |
| B | 2024-04-21 .. 2026-09-30 | 5 | 2024-10-19 .. 2026-06-10, all after the canonical tests | `sp500_at:2026-09-30` |

Train 180 / test 120 / step 120, as in the canonical protocol. The EDGAR scorer
fits nothing, so in B the train span is warm-up only; it was moved earlier so
the window yields the project's minimum of 5 folds.

### Arms (fixed)

`raw` is the live config. `normalized` is the #99 variant, unchanged
(`scripts/name-norm-99.py`: `name_forms` / `strip_forms`). Both arms run on one
panel per window and differ only in their risk-factor texts.

### Mechanism check (fixed)

At two as-of dates per window (A: 2019-06-30, 2021-06-30; B: 2025-06-30,
2026-09-30), rank names by raw rolling cosine (engine rule: filing lag, w2,
top 10%). Compare the name-token share (registrant name forms ÷ tokens in the
latest 10-K) of selected names against the rest.

### Decision rule (fixed in advance)

With α = median annualized alpha vs SPY:

- **Language edge supported**: in both windows α_raw > 0 and
  α_normalized ≥ 0.5 × α_raw.
- **Edge depends on the name**: in both windows α_raw > 0 and
  α_normalized < 0.5 × α_raw.
- **No out-of-window edge**: α_raw ≤ 0 in both windows, whatever the
  normalized arm does.
- Anything else is **inconclusive** and is reported as such.

The mechanism check supports the name explanation if the selected names'
median name share exceeds the rest's at every as-of date.

No further windows, universes or variants are added after seeing results.

## Reproduction

```bash
cp -Rc ~/.cache/bloasis /tmp/bloasis-cache-clone
uv run python scripts/edge-robustness.py --window A \
    --cache-dir /tmp/bloasis-cache-clone --out /tmp/edge-A.json
uv run python scripts/edge-robustness.py --window B \
    --cache-dir /tmp/bloasis-cache-clone --out /tmp/edge-B.json
```

Window A needs 10-Ks back to 2013 and OHLCV back to 2017; the first run
downloads them.

## Results

Run 2026-10-02, one cloned cache, window B then A. Both windows met the fold
minimum (B 5, A 10). Names with 10-K history: B 488, A 447.

| window | arm | α/yr (median) | sharpe vs SPY | DD ratio | trades |
|---|---|---|---|---|---|
| A 2018–2021 | raw | **+0.01%** | 1.305 | 0.883 | 536 |
| A 2018–2021 | normalized | −0.53% | 1.310 | 0.893 | 546 |
| B 2024-10–2026-06 | raw | **−1.92%** | 1.276 | 0.898 | 294 |
| B 2024-10–2026-06 | normalized | −3.81% | 0.876 | 1.015 | 302 |
| *canonical 2022–2024 (#99)* | *raw* | *+3.74%* | *1.013* | *0.873* | *398* |

```
fold α  A raw         -0.078 0.147 0.024 -0.024 -0.085 -0.033 -0.221 0.345 0.044 0.058
        A normalized  -0.062 0.146 0.024 -0.034 -0.089 -0.062 -0.183 0.351 0.059 0.081
        B raw         -0.066 -0.019 -0.039 0.026 0.090
        B normalized  -0.065 -0.038 -0.014 -0.055 0.033
```

Mechanism check (median name-token share of the latest 10-K):

| as-of | selected | rest | selected above rest median |
|---|---|---|---|
| 2019-06-30 | 0.14% | 0.11% | 51% |
| 2021-06-30 | 0.11% | 0.10% | 52% |
| 2025-06-30 | 0.10% | 0.11% | 46% |
| 2026-09-30 | 0.07% | 0.11% | 38% |

### Verdict under the pre-registered rule

**Inconclusive.** α_raw is +0.01% in A and −1.92% in B. "No out-of-window
edge" needs α_raw ≤ 0 in both windows, and A misses by one basis point. The
language-vs-name rules need α_raw > 0 in both, and B fails. The mechanism check
does **not** support the name explanation: the selected names' median share
is above the rest's at two of four dates and below at the other two.

### What the numbers say, beyond the rule

1. **The canonical +3.74% does not replicate outside 2022–2024.** Raw α is
   about zero over ten folds in 2018–2021 and negative over five folds after
   October 2024, the period the paper session is drawing from. Fold α swings
   from −22% to +35% in A, so a median a few points from zero is well inside
   the spread.
2. **Drawdown fails out of window too.** DD ratio is 0.883 in A and 0.898 in B,
   against the 0.85 bar.
3. **#99's "edge moves with the name" reads better as "the in-sample α is
   fragile".** Name tokens are about 0.1% of the median 10-K, and selected
   names do not consistently say their own name more than the rest. That makes
   the name an unlikely driver for most selections, though not for every one
   (JPM's is 5%). Yet removing name forms, which changed a handful of
   selections, erased the canonical α. A result that a handful of
   swaps can erase is not a stable edge, whatever caused the swaps.
4. Sharpe vs SPY above 1.0 next to α ≤ 0 is not a contradiction worth reading
   into. The two metrics answer different questions, and the gate already
   requires both.

This does not falsify the "Lazy Prices" hypothesis in general. It says that
this implementation, on S&P 500 names at this selection depth, shows no edge
outside the window it was chosen on.

Raw output: the driver's JSON (`--out`), not committed.
