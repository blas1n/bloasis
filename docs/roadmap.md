# BLOASIS Roadmap

This roadmap is bounded by [`mission.md`](./mission.md). Each phase has a
machine-verifiable gate; we do not advance phases on vibes.

---

## Phase 1 — M2 Foundation (✅ SHIPPED)

**Mission**: Match SPY return with lower max drawdown.
**Cost**: $0 (yfinance + Finnhub free).
**Outcome**: shipped in ~2 months (PR1 → PR20).

### Scope (all done)

- [x] **PR1** — Skeleton (CLI, config, DB schema, docs)
- [x] **PR2** — Data layer (Universe loaders, Fetcher Protocols, yfinance, Finnhub)
- [x] **PR3** — FeatureExtractor (pure, look-ahead protected) + raw features + composites
- [x] **PR4** — RuleBasedScorer + Rationale + SignalGenerator + RiskEvaluator + ML stub
- [x] **PR5** — Backtest engine + walk-forward + metrics + statistical tests + acceptance gates
- [x] **PR6** — CLI (`runs list/compare/explain`) + Alpaca paper adapter + composer
- [x] **PR20** — `edgar-rolling2` shipped (sharpe 1.334 / α +4.09%/yr / DD 0.80) —
      first config to clear the live-trading gate
- [x] **PR21-23** — Grid runner + 41 combo sweep. Confirmed `edgar-rolling2`
      is the uncontested winner; PEAD / knob sweeps / EDGAR∩JT intersect
      all falsified against baseline
- [x] **PR45-49** — Paper trading layer (schema/writers/SELL rotation/scorer
      factory/unified backtest+live runner). Alpaca paper + launchd cron
      Mon-Fri 08:00 KST since 2026-05-10
- [x] **PR51-52** — Fill reconciliation + `friction` → `entry-gap` honest
      renaming (gap drift is regime, not execution slippage)

### Phase 1 Exit Gate (met by `configs/edgar-rolling2.yaml`)

```yaml
walk_forward_min_folds: 5
median_alpha_annualized: -0.005      # measured +4.09% (PR20)
median_sharpe_vs_spy: 1.0            # measured 1.334 (PR20)
median_max_dd_ratio_to_spy: 0.85     # measured 0.80 (PR20)
```

---

## Phase 2 — M2+ Signal Edge (in progress)

**Mission**: Modest sustained alpha (~+1%) through underexploited signals.
**Cost**: $0.
**Status**: Multiple research tracks — one shipped, several falsified,
one live-tracking.

### Research tracks

- ✅ **EDGAR text-diff scorer** (Cohen-Malloy-Nguyen "Lazy Prices") —
      shipped as `edgar-rolling2`. Buys names whose 10-K language
      changes least YoY.
- ❌ **PEAD** (post-earnings announcement drift) — falsified in PR22-23
      grid measurement. Signal did not survive walk-forward on the
      universe we use.
- ❌ **Regime overlay** — hurt EDGAR-rolling2 performance in grid measurement.
- ❌ **Knob sweep / EDGAR∩JT intersect** — 12 combos measured, none
      beat baseline. Hypothesis falsified (PR22).
- ✅ **Position size 0.03/0.05** — α +4.2% variant shipped-adjacent
      (small lift from PR23 grid).
- ❌ **`fundamental_llm` scorer** — llama3.2:3b too weak; documented
      but not promoted.
- ~ **Correlation clustering / event-study CLIs** (PR53-54) — research
      tooling, not scorers. Support hypothesis generation.
- 🔄 **Trump mention pipeline** (PR55-60) — Truth Social → hybrid
      extractor → per-ticker baseline-corrected excess study.
      Retrospective on 2024-2026 corpus: pooled excess −0.51% (mention
      average trails baseline), but negative + out-of-hours cell shows
      +1.32% pooled edge (n=129, corrected +0.50% at n=52 after tz
      fix). Currently forward-tracked via daily cron (PR57 + PR60);
      real prospective signal accumulating from 2026-06-05. Falsify or
      confirm target: end of 2026-Q3.
- 🔄 **LightGBM ML scorer** (PR13-17) — trained end-to-end but only
      +0.28 sharpe shift vs rule scorer, still failed acceptance.
      Available in `bloasis ml` if we accumulate more OOS features.

### Phase 2 Exit Gate

```yaml
median_alpha_annualized: 0.015       # +1.5%
bootstrap_alpha_p_value: 0.10
```

`edgar-rolling2` alone likely won't pass. A confirmed mention edge or
another additive signal is what we're hunting for.

### Living issues surfaced during Phase 2

- **L001** — Survivorship bias (universe). `sp500_historical` mode
  mitigates for 2024+ backtests.
- **Upstream data-source rename risk** (surfaced PR59) —
  `fja05680/sp500` renamed files in mid-2026, silently degrading the
  loader to `whitelist=0` for 4 weeks. Fix landed in PR59 with
  rank-and-order auto-discovery; a downstream sanity floor (raise if
  whitelist < 400) is still pending.
- **tz-strip bucket misclassification** (PR57 fix) — SQLite +
  SQLAlchemy `DateTime(timezone=True)` round-trip loses tzinfo. On a
  non-UTC host, downstream `.astimezone()` silently shifted every
  mention-timing bucket by ~13 hours until PR57's defensive
  normalization.

---

## Phase 3 — M1 Attempt (low-cost paid data)

**Mission**: Credible alpha (+1.5% to +3%) backed by clean data.
**Cost**: ~$30/month (EODHD or equivalent).
**Status**: not started. Gated on Phase 2 clearance.

### Planned additions

- **Point-in-time fundamentals** — eliminates fundamentals look-ahead bias
- **Delisted equity history** — eliminates survivorship bias (closes L001)
- **Russell 1000 universe** — broader, less efficient names
- **LightGBM scorer promotion** — replaces RuleBasedScorer once enough
  OOS features are logged; the trained pipeline already exists
- **SHAP-based per-trade explainability** (PR16 tooling, currently unused)

### Phase 3 Exit Gate

```yaml
median_alpha_annualized: 0.03
white_reality_check_p: 0.05
forward_test_alpha_6mo: 0.01
```

---

## Phase 4 — Real M1 (research territory)

**Mission**: Sustained, statistically significant alpha.
**Cost**: $200+/month or independent research effort.
**Status**: intentionally undefined until Phase 3 evidence lands.

### Candidate directions (one or more)

- Polygon options chain (unusual activity, IV skew)
- Alternative data (Google Trends, Reddit sentiment with ML)
- International / emerging markets expansion
- Cross-asset macro overlay (full TAA framework)
- Online ML with regime-conditional retraining

---

## Stage progression rules

1. **No phase advance without gate clearance.** A failing gate means
   "stay, improve, or halt" — never "skip to next phase".
2. **Backtests use walk-forward only.** Full-history optimization is
   forbidden.
3. **Each phase ends with documented retrospective**. Phase 1 → PR20
   measurement + Phase 2 postmortem sit under `docs/research/`.
   Phase 2 will close with a written "did the mention edge replicate?"
   answer once forward data has accumulated.
4. **Mission can revise downward but not upward without evidence.** If
   Phase 2 keeps failing +1% alpha, downgrade to "edgar-rolling2
   parity" before reaching further.
