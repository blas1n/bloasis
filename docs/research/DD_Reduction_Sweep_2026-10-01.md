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

Run 2026-10-01, one process, cloned cache. Sensors printed by the driver:
7 folds; universe 503 symbols, 493 with bars, 478 with 10-K history;
**sector map 0 entries** (F2 confirmed on the run itself, not only by
reading code). The baseline reproduces the gate re-measurement exactly
(DD 0.873 / sharpe 1.013 / α +3.74% / 398 trades), so the panel matches the
one #85 was filed on.

**14 of 17 arms ran. The three `pos=0.03` arms could not be measured** —
the backtester raised on the first of them (see F3). They are reported as
not measured, not dropped.

| arm | DD ratio | sharpe vs SPY | α/yr | trades | qualifies |
|---|---|---|---|---|---|
| baseline (live config) | 0.873 | 1.013 | +3.74% | 398 | no (DD) |
| A σ=0.08 bear=0.25 clip=1.0 | 0.464 | 0.974 | −3.12% | 398 | no (sharpe, α) |
| A σ=0.08 bear=0.25 clip=1.5 | 0.464 | 0.974 | −3.12% | 398 | no (sharpe, α) |
| A σ=0.08 bear=0.50 clip=1.0 | 0.464 | 0.990 | −3.11% | 398 | no (sharpe, α) |
| A σ=0.08 bear=0.50 clip=1.5 | 0.464 | 0.990 | −3.11% | 398 | no (sharpe, α) |
| A σ=0.12 bear=0.25 clip=1.0 | 0.626 | 0.978 | −1.54% | 398 | no (sharpe, α) |
| A σ=0.12 bear=0.25 clip=1.5 | 0.662 | 0.978 | −1.54% | 398 | no (sharpe, α) |
| A σ=0.12 bear=0.50 clip=1.0 | 0.626 | 0.996 | −1.53% | 398 | no (sharpe, α) |
| A σ=0.12 bear=0.50 clip=1.5 | 0.662 | 0.996 | −1.53% | 398 | no (sharpe, α) |
| B pos=0.01 sector=0.20 | 0.435 | 1.002 | −2.36% | 357 | no (α) |
| B pos=0.01 sector=0.40 | 0.435 | 1.002 | −2.36% | 357 | no (α) |
| B pos=0.01 sector=1.00 | 0.459 | 0.999 | −2.77% | 398 | no (sharpe, α) |
| B pos=0.02 sector=0.20 | 0.828 | 1.015 | +6.01% | 357 | **yes** |
| B pos=0.02 sector=0.40 | 0.828 | 1.015 | +6.01% | 357 | **yes** |
| B pos=0.03 sector=0.20 | — | — | — | — | not measured (F3) |
| B pos=0.03 sector=0.40 | — | — | — | — | not measured (F3) |
| B pos=0.03 sector=1.00 | — | — | — | — | not measured (F3) |

Per-fold DD ratios, baseline vs the qualifying arm:

```
baseline          0.873 0.768 1.478 1.063 0.772 1.004 0.626   median 0.873
pos=0.02 sec=0.2  0.828 0.772 1.478 1.002 0.772 0.977 0.606   median 0.828
```

### Reading

**Block A — the overlay cuts DD hard and pays for it in α, every arm.**
DD falls to 0.46–0.66, but α goes negative (−1.5% to −3.1%) and sharpe drops
under 1.0. Same trade count as the baseline in every arm: the overlay does not
change *what* is bought, only how much, so this is the exposure/return
trade-off and nothing else. It is also inert live (F1). The roadmap's
"overlay hurts returns" verdict now holds against DD as well. `clip` 1.0 vs
1.5 changes nothing at σ=0.08 — the scale never rises above 1 there.

**Block B, `pos=0.01` — halving size halves DD and makes α negative.** Pure
gross exposure, as expected.

**Block B, `pos=0.02 sector∈{0.2, 0.4}` — two arms qualify, and they should
not be read as a DD fix.**

1. **They are not a sector test** (F2: zero sectors, everything is
   `_unknown`).
2. **They are not even a gross-exposure cap in the sense F2 assumed.** The
   risk check compares against `PortfolioState.sector_concentrations`, which
   the engine snapshots once per rebalance step (`engine.py:267`) and does not
   update as the step's BUYs are placed. So the rule is "reject every new BUY
   in a step whose *opening* invested fraction is already ≥ cap (clip each
   one to the remaining room if it is just under)"; below that, any number of
   2% buys in the same step go through, because the snapshot never grows. 0.20 and 0.40 give byte-identical
   results, i.e. the opening invested fraction never landed between them at
   a buying step. What qualified is a step-start exposure gate with a one-step
   lag — a mechanism nobody designed.
3. **It is inert live** (F2: `cli.py` passes `sector_concentrations={}`).
4. **It is an in-sample pick over 17 pre-registered arms with a 0.022
   margin**, and it moves DD in only four of seven folds (1, 4, 6, 7); the
   worst fold (3, 1.478) is untouched.

Per the decision rule, any qualifying arm needs out-of-sample confirmation
before it goes near the live config. Here there is nothing coherent to
confirm: the qualifying behaviour comes from an unintended snapshot artefact
of a knob that does not exist in paper trading.

### F3 — The backtester has no cash check on BUY sizing

`execute_strategy_step` sizes a BUY as `equity × size_pct × regime_scale`
(`runner.py`) with no reference to available cash, and `BacktestPortfolio.apply`
raises `ValueError("insufficient cash: need 297.00, have 199.00")` when the
step's BUYs exceed it. At `pos=0.02` the step's buys happen to fit; at
`pos=0.03` the first arm aborts the process. This also means the overlay's
`clip > 1.0` lever-up path can only ever have run where it did not need more
cash than was there. Making the `pos=0.03` arms measurable requires an engine
change (clip or skip on insufficient cash); that is a behaviour change to the
backtester, so it is not made inside this sweep.

### Verdict

**No pre-registered setting clears the DD gate through a mechanism that exists
in paper trading.** The two qualifying arms are an in-sample artefact of an
inert live knob. Block A and `pos=0.01` buy DD only by giving up the α and
sharpe that currently pass. The #85 founder decision (continue paper under a
failing DD gate as evidence, or stop) should be taken on that basis, not on
the two "yes" rows.

### Addendum — the `pos=0.03` arms, after the F3 fix

Measured the same day on the same cloned cache, after the simulator was changed
to reject a BUY it cannot pay for instead of raising. All 14 earlier arms were
re-run in the same process and reproduce the table above field for field, so
these rows are on the same panel.

| arm | DD ratio | sharpe vs SPY | α/yr | filled | cash-rejected | qualifies |
|---|---|---|---|---|---|---|
| B pos=0.03 sector=0.20 | 0.859 | 1.020 | +11.05% | 259 | 91 | no (DD) |
| B pos=0.03 sector=0.40 | 0.859 | 1.020 | +11.05% | 259 | 91 | no (DD) |
| B pos=0.03 sector=1.00 | 0.912 | 1.004 | +9.30% | 367 | 235 | no (DD) |

None qualifies, so the verdict stands. Read the α with care: at 3% per name the
runner's targets exceed cash, and between a quarter and two fifths of BUY
orders are rejected. Which names get bought is then decided by the order
signals arrive in, not by the sizing rule — the α is a property of that
ordering, not of "3% positions".

### Decision (founder, 2026-10-01, after the result)

- Paper trading on `edgar-rolling2` continues as evidence accumulation under a
  failing DD criterion; real money stays blocked.
- The 0.85 DD bar itself is to be reviewed (#88).
- F3 is fixed first (TDD, separate PR) so the three `pos=0.03` arms can be
  measured and the pre-registered table completed (addendum above).

Raw rows: the driver's JSON output (`--out`), not committed.
