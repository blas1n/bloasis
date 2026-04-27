# BLOASIS Roadmap

This roadmap is bounded by [`mission.md`](./mission.md). Each phase has a
machine-verifiable gate; we do not advance phases on vibes.

---

## Phase 1 — M2 Foundation (current)

**Mission**: Match SPY return with lower max drawdown.
**Cost**: $0 (yfinance + Finnhub free).
**Time**: 4-6 weeks of evening/weekend work.

### Scope

- [ ] **PR1** — Skeleton (CLI, config, DB schema, docs)
- [ ] **PR2** — Data layer (Universe loaders, Fetcher Protocols, yfinance, Finnhub)
- [ ] **PR3** — FeatureExtractor (pure, look-ahead protected) + 18 raw features + 7 composites
- [ ] **PR4** — RuleBasedScorer + Rationale + SignalGenerator + RiskEvaluator + ML stub
- [ ] **PR5** — Backtest engine + walk-forward + metrics + statistical tests stub + acceptance gates
- [ ] **PR6** — CLI commands (`runs list/compare/explain`) + Alpaca paper adapter + composer

### Phase 1 Exit Gate

```yaml
walk_forward_min_folds: 5
median_alpha_annualized: -0.005
median_sharpe_vs_spy: 1.0
median_max_dd_ratio_to_spy: 0.85
```

If we cannot meet this on 5+ years of S&P 500 data, the strategy is not
worth deploying. Reset, simplify, or halt.

---

## Phase 2 — M2+ Signal Edge (within free data)

**Mission**: Modest sustained alpha (~+1%) through known but underexploited
signals.
**Cost**: $0.
**Time**: 4-6 weeks after Phase 1 gate clears.

### Additions

- **Earnings calendar + PEAD** — Finnhub provides earnings dates;
  post-earnings drift is a documented anomaly.
- **Analyst rating changes** — Finnhub recommendation trends as a feature.
- **Cross-asset regime context** — TLT (bonds), GLD (gold), HYG (high yield)
  as additional regime inputs beyond VIX/SPY.
- **Walk-forward optimization** — Optuna or grid search bounded to OOS folds.
- **Sector relative strength** — cross-sectional momentum within sector.

### Phase 2 Exit Gate

```yaml
median_alpha_annualized: 0.015
bootstrap_alpha_p_value: 0.10
```

---

## Phase 3 — M1 Attempt (low-cost paid data)

**Mission**: Credible alpha (+1.5% to +3%) backed by clean data.
**Cost**: ~$30/month (EODHD or equivalent).
**Time**: 6-8 weeks after Phase 2 gate clears.

### Additions

- **Point-in-time fundamentals** — eliminates fundamentals look-ahead bias
- **Delisted equity history** — eliminates survivorship bias
- **Russell 1000 universe** — broader, less efficient names
- **LightGBM scorer activated** — replaces RuleBasedScorer once enough OOS
  features are logged
- **SHAP-based per-trade explainability**

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
**Time**: indefinite — this is a research program, not a sprint.

### Candidate directions (one or more)

- Polygon options chain (unusual activity, IV skew)
- Alternative data (Google Trends, Reddit sentiment with ML)
- International / emerging markets expansion
- Cross-asset macro overlay (full TAA framework)
- Online ML with regime-conditional retraining

This phase is intentionally vague — by the time we reach it, we will know
much more about which direction has the best evidence.

---

## Stage progression rules

1. **No phase advance without gate clearance.** A failing gate means "stay,
   improve, or halt" — never "skip to next phase".
2. **Backtests use walk-forward only.** Full-history optimization is forbidden.
3. **Each phase ends with documented retrospective** in
   `docs/retrospectives/phase-N.md`: what worked, what didn't, what changed
   in the mission.
4. **Mission can revise downward but not upward without evidence.** If
   Phase 1 keeps failing M2, downgrade to "match SPY return only" before
   reaching for M1.
