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

<!-- filled in after the run -->
