# DD-reduction sweep — pre-registration and result (2026-10-01)

Point-in-time record. Per `docs/research/README.md`, measurement logs are not
updated after the fact.

Issue: [#85](https://github.com/blas1n/bloasis/issues/85), fourth acceptance
item. Prior record of the failure:
`docs/research/EDGAR_Rolling2_Gate_Remeasurement_2026-10-01.md`.

## Question

`configs/edgar-rolling2.yaml` fails the Phase 1 exit gate on exactly one
criterion — median max-DD ratio to SPY 0.873 against a 0.85 bar — while
sharpe (1.013) and α (+3.74%/yr) pass. **Can DD be brought to ≤ 0.85 without
losing the sharpe ≥ 1.0 and α ≥ −0.5% that currently pass?**

`docs/roadmap.md` records the regime overlay as falsified, but it was
falsified on *returns*. It has never been measured against drawdown, which is
the only criterion now failing.

## Pre-registration

Written and committed **before** any arm was run. This is a sweep whose
explicit aim is to make a gate pass, which is the multiple-testing trap this
project has already been burned by — `docs/roadmap.md` lists PEAD, the knob
sweep / EDGAR∩JT intersect (12 combos) and the regime overlay itself as
falsified after exactly this kind of search. The arm list, the protocol and the
decision rule are therefore fixed up front, and the full table is reported, not
the best arm.

### Knobs and grids

Two blocks, full factorial within each block, no cross-block arms.

**Block A — regime overlay** (8 arms). `regime_overlay.enabled: true` plus:

| knob | values | why |
|---|---|---|
| `sigma_target` | 0.08, 0.12 | 0.12 is the config default; 0.08 de-risks harder. This is the Barroso–Santa-Clara vol-targeting lever, the one mechanism that cuts exposure *only* in high-vol periods — i.e. the one that can cut DD without cutting exposure in calm periods. |
| `bear_scale` | 0.25, 0.50 | 0.50 is the default; 0.25 is a harsher Daniel–Moskowitz bear gate. Bear states are where the losing drawdowns happen. |
| `scale_clip` upper | 1.0, 1.5 | 1.5 is the default and lets the overlay **lever up** in calm markets (`runner.py` applies the scale *after* `max_single_order_pct`, so >1.0 really does exceed the order cap). A 1.0 ceiling makes the overlay de-risk-only. This directly tests the roadmap's hypothesis that the overlay hurt returns. |

**Block B — position sizing / concentration** (9 arms, one of which is the
baseline).

| knob | values | why |
|---|---|---|
| `signal.position_size_max_pct` | 0.01, 0.02, 0.03 | 0.02 is live. Gross exposure is the crudest DD lever; it is in the grid to be measured, not because it is expected to qualify. |
| `risk.max_single_order_pct` | tracks the position cap | Effective size is `min(position_size_max_pct, max_single_order_pct)` (`signal.py:136`, `risk.py:93`). Sweeping the two independently would only re-measure the smaller of them, so they move together — a deliberate grid reduction, not an omission. |
| `risk.max_sector_concentration` | 0.20, 0.40, 1.0 | 1.0 is live (no cap). Sector concentration is the other DD lever that does *not* require cutting gross exposure, so it is the second candidate that could cut DD without cutting α. |

**Deliberately not swept**: the scorer, `entry_threshold` / `exit_threshold`,
`edgar_rolling_window`, and `rebalance_days`. Those are what the gate already
passes on; touching them would re-open criteria that are not failing.

**Arm count: 17** (1 control + 8 block A + 8 novel block B). No third stage,
no cross-block arms, and no widening of the grid after seeing results.

### Protocol

Identical for every arm:

- Canonical 7-fold walk-forward from `configs/grids/pr21-edgar-rolling.yaml`:
  2022-01-01 .. 2024-10-17, train 180 / test 120 / step 120. The driver
  aborts if the fold count is not 7.
- Universe `sp500_at:2024-12-31`.
- **One prefetch, one process, one `BacktestData` panel shared by all 17
  arms** (`scripts/dd-sweep-85.py`). Two separate `bloasis grid run`
  invocations would re-enter the cache and could drift between blocks; this
  cannot. Cached OHLCV parquet is served regardless of age for the same
  reason.
- Cloned `~/.cache/bloasis`; the shared cache and the live paper session are
  untouched. Nothing is written to the run DB.

### Decision rule (fixed in advance)

An arm **qualifies** only if, on the 7 folds:

```
median max-DD ratio to SPY <= 0.85
AND median sharpe vs SPY    >= 1.0
AND median alpha annualized >= -0.005
AND folds                   >= 5
```

Every arm run is reported, pass or fail. If an arm qualifies it is an
**in-sample selection over 17 arms** and requires out-of-sample confirmation
before it goes anywhere near the live config. "No setting clears DD without
breaking sharpe" is an acceptable outcome and is to be stated plainly.

## Reproduction

```bash
cp -Rc ~/.cache/bloasis /tmp/bloasis-cache-clone
uv run python scripts/dd-sweep-85.py \
    --cache-dir /tmp/bloasis-cache-clone \
    --out /tmp/dd-sweep-85.json
```

The first run re-extracts Item 1A into `edgar/risk_factors/v2/` (the #83
parser version), ~3k 10-K downloads, ~30 min.

## Harness findings (found while wiring the sweep, before any arm was scored)

Two of the pre-registered knobs do not mean in this system what their names
say. Both are recorded here because they change how the arm table must be
read, and neither was found by looking at results.

### F1 — The regime overlay cannot act in paper or live trading

`compute_regime_scale()` returns `1.0` whenever it is handed fewer than
`vol_lookback_days` (126) SPY returns. The live path
(`bloasis/cli.py`, the `trade` command) constructs
`spy_returns_to_date = pd.Series([], dtype=float)` — an empty series — so the
overlay is a pass-through there no matter what the config says. Measured
directly with the most aggressive parameters the config can express:

```
sigma_target=0.01, bear_scale=0.01, scale_clip=(0.0, 1.0)
  empty series (the live path)  -> scale 1.0
  125 bars                      -> scale 1.0
  600 noisy bars                -> scale 0.0003
```

The same call site also passes `vix=0.0`, so the VIX risk gates are inert
live as well. Consequence for this sweep: **any block-A arm that qualified in
backtest would be a no-op in paper trading** until that wiring is fixed. The
overlay is, today, a backtest-only knob.

### F2 — `max_sector_concentration` is a gross-exposure cap in backtest and inert live

`RiskEvaluator` buckets a position under `signal.sector or "_unknown"`
(`bloasis/risk.py:99`). `prefetch_backtest_data()` never populates
`BacktestData.sectors` — the only place in the repo that fills it is
`tests/test_backtest_engine.py:70`. So in every real backtest every holding
lands in one `_unknown` bucket and the "sector" cap limits **total invested
fraction**, not sector mix. Live is the mirror image: `cli.py` passes
`sector_concentrations={}`, so `existing` is always 0 and the cap can only
clip one order's size.

Consequence: block B's sector axis measures gross exposure, i.e. the same
mechanism as its position-cap axis, and it cannot test the hypothesis it was
chosen for ("diversify across sectors to cut DD without cutting exposure").
The arms are still reported as pre-registered and are still informative —
together the two axes map the exposure/DD/α frontier — but they are not a
test of sector diversification.

## Results

<!-- filled in after the run -->
