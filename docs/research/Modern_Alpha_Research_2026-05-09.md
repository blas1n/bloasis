# Modern Alpha Research for Bloasis (2026-05-09)

Scope: post-2018 academic alpha signals appropriate for a long-only, US large-cap (S&P 500 universe), monthly-rebalanced CLI research platform. Excludes signals already in Bloasis (JT 12-1, AQR QMJ, DM crash filter, Cohen-Malloy lazy-prices cosine, PEAD, Lopez-Lira-style ChatGPT-on-headlines).

Already-measured baseline (for comparison): EDGAR cosine clean SP500 2022-2024 sharpe 0.997, JT clean sharpe 0.860 (DD fail), PEAD decayed to 0.057-0.725, LLM-fundamental Ollama sharpe 0.600-0.898 with negative alpha.

---

## Executive Summary (5 most actionable bullets)

1. **Residual / idiosyncratic momentum (Blitz-Hanauer-Vidojevic)** is the single strongest "easy upgrade" path: same JT plumbing but regress out FF3 / market beta first. Documented monthly Sharpe 0.48 vs 0.25 for plain JT (ex-US sample 1925-2015), half the volatility, and works through 2024 unlike vanilla JT. Drop-in replacement for our DD-failed JT. **Very likely fixes the JT DD 1.46 fail.**

2. **Intangible Value (Eisfeldt-Kim-Papanikolaou 2022)** revives the value factor on the S&P 500 era when traditional B/M is dead — adds capitalized SG&A and R&D to book equity, sorts within industry. Outperforms classical value especially 2010-2020. Free Compustat data, ~50 lines of Python, long-only friendly. Best chance at a non-momentum, non-text alpha that survives 2024.

3. **Earnings Call Q&A NLP (FinBERT / SubjECTive-QA, 2023-2024)** — the prepared-remarks-vs-Q&A delta and analyst-tone-dispersion signals are the highest-quality recent text alphas. Reported Sharpe 0.6-1.28 in 2010-2023 simulation, factor-neutralized vendor (ExtractAlpha) claims 13.7% / 2.57 SR over 2006-2024. Requires transcripts (Seeking Alpha scrape, FMP, or paid). FinBERT is free + Python-native. **Strong candidate, but data acquisition is the main cost.**

4. **Smoothing / tolerance-band rebalancing (Chitsiripanich-Paolella 2024 "Smoothing Out Momentum and Reversal")** — orthogonal to signal choice, just better portfolio construction. Reported 95-99% turnover reduction with monthly-equivalent returns; 20% tolerance bands monthly add ~0.24% CAGR + Sharpe + DD improvement. **Cheapest sharpe-improvement we can ship**: ~30 lines of changes to the rebalance loop. Apply to whichever signal we ship.

5. **Insider buying clusters (Form 4, 3+ unique insiders within 10 days)** — alpha-architect-replicated 6-month alpha ~5.2%, broadly stable through 2023. Free SEC data, simple parser, monthly long-only friendly. Best "new orthogonal signal" candidate beside Intangible Value.

Defer / skip: WSB sentiment (no risk-adjusted alpha post-GME), trend / time-series momentum (designed for cross-asset, not S&P long-only), Numerai-style transformers / AlphaPortfolio (long-short, infra rewrite), short-interest signals (most alpha is on the short side which we don't have).

---

## Per-Paper Notes

### Group A — Modern text-based alpha beyond 10-K Item 1A

#### A1. Earnings call Q&A subjectivity / defensiveness — SubjECTive-QA (Pareek et al, NeurIPS 2024) + FinBERT (Huang et al, CAR 2023)
- **URL**: https://arxiv.org/html/2410.20651v1 (SubjECTive-QA), https://onlinelibrary.wiley.com/doi/abs/10.1111/1911-3846.12832 (FinBERT)
- **Claim**: Six-dimensional Q&A scoring (assertive, clear, optimistic, specific, relevant, hedged) on earnings calls; FinBERT-based sentiment outperforms LM dictionary on financial text. Vendor (ExtractAlpha) reports factor-neutralized US Transcripts model 13.7% annual return / 2.57 SR over 2006-2024.
- **Replication**: Active 2023-2024 literature. Multiple academic groups confirm Q&A section carries more signal than prepared remarks. Lopez-Lira ChatGPT decay is on news headlines, not Q&A — Q&A signal hasn't decayed equivalently.
- **Data**: Earnings call transcripts. Free options: Seeking Alpha scrape (TOS issue), FMP transcript API ($30-50/mo), Refinitiv (paid). Bloasis already has Ollama → FinBERT or local LLM scoring is feasible.
- **Difficulty**: 4/5 (transcript ingestion + per-firm Q&A segmentation + LLM scoring loop is non-trivial; debug long-tail formatting bugs).
- **Long-only friendly**: Yes — buy top tercile of Q&A clarity / non-defensive scores within S&P 500.
- **Fits Bloasis**: Yes if transcript source secured. Aligns with our existing LLM-on-text pipeline.

#### A2. 8-K trading gap / specific-item event alpha — Cohen-Jackson-Mitts "8-K Trading Gap" + Lerman-Livnat "New 8-K Disclosures"
- **URL**: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2657877, https://link.springer.com/article/10.1007/s11142-009-9114-7
- **Claim**: 8-K Item 1.01 (material agreement) and Item 5.02 (officer change) drive abnormal returns and post-filing drift. Cohen-Jackson-Mitts find 35.4 bp avg around insider 8-K window. Notre Dame "Who Pays Attention to 8-K" shows attention-driven drift.
- **Replication**: Cited 100+ times, robust 2008-2020. Decay status uncertain post-2022.
- **Data**: SEC EDGAR (free) — 8-K filings parseable by item number. Bloasis already does EDGAR.
- **Difficulty**: 2/5 — pure metadata parse, no NLP needed for item-trigger version. Add LLM tone scoring on the 8-K body for v2.
- **Long-only friendly**: Yes — buy on positive item triggers (e.g., Item 1.01 material agreement, Item 8.01 other material events) within S&P 500, hold 1-3 months.
- **Fits Bloasis**: Strong yes. Reuses EDGAR plumbing. Event-driven monthly rebalance fits.

#### A3. WSB / Reddit sentiment — Bradley-Hanousek-Jame "Place Your Bets" (RFS 2024) + Long et al. (PMC 2023)
- **URL**: http://russelljame.com/wsb_10_19_23.pdf
- **Claim**: WSB recommendations had short-term predictive power pre-2021 but post-GME the signal degrades; long buy-recs + short sell-recs is **not** profitable on risk-adjusted basis at any horizon 1d-1y in academic replication.
- **Replication**: Multiple 2023-2024 papers confirm decay; ScienceDirect paper shows -8.5% HPR for high-attention positions.
- **Verdict**: **Skip.** Even if we could ingest, retail-attention crowding kills it for long-only large-cap.

#### A4. SEC comment letter response — Bushee et al (Mgmt Sci 2024)
- **URL**: https://pubsonline.informs.org/doi/10.1287/mnsc.2023.02065
- **Claim**: Less readable comment letter responses → longer SEC review → higher restatement probability. Information-leakage paper finds abnormal returns around comment letter resolution.
- **Verdict**: **Skip for v1** — sample is small (only firms that get comment letters, ~5-10% of S&P 500/yr), event timing is poorly defined (months between letter and resolution). Defer to "long tail" candidate.

### Group B — Cross-sectional anomalies discovered post-2018 that survive

#### B1. Residual / Idiosyncratic Momentum — Blitz, Hanauer, Vidojevic (JBF 2020 + 2022 update)
- **URL**: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2947044, https://www.sciencedirect.com/science/article/abs/pii/S1059056020300927
- **Claim**: Run JT 12-1 on FF3-residualized returns instead of raw returns. Half the vol of vanilla JT, no return drop. Monthly SR 0.48 vs 0.25 (1925-2015 US, vol-adjusted). Not subsumed by other factors. Confirmed in 2024 momentum-attribution work that idiosyncratic risk drove 2024 momentum outperformance.
- **Replication**: Jensen-Kelly-Pedersen (JF 2023) "Is There a Replication Crisis" includes momentum-cluster as one of 13 surviving factor themes.
- **Data**: Same as JT (CRSP/yfinance). FF3 factors free from Ken French data library.
- **Difficulty**: 2/5 — add a rolling 36m FF3 regression per stock, momentum on residuals.
- **Long-only friendly**: Yes — top quintile or top decile S&P 500 residual-12-1.
- **Fits Bloasis**: **Strongest yes.** Drop-in replacement for our JT DD-fail.

#### B2. Intangible Value — Eisfeldt, Kim, Papanikolaou (CFR 2022 / NBER 28056)
- **URL**: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3720983, https://www.nber.org/papers/w28056
- **Claim**: Adjust book equity by capitalized SG&A (perpetual inventory method). Sort within industry. Outperforms classical B/M, especially 2010-2020 when value died. Survives in independent replications (Bongaerts FM 2024).
- **Replication**: Yes — 200+ citations, multiple confirming replications.
- **Data**: Compustat (paid) or yfinance + SEC XBRL fundamentals (free, slightly noisier).
- **Difficulty**: 3/5 — perpetual inventory accumulator + within-industry sort. ~100 lines.
- **Long-only friendly**: Yes — long top quintile by intangible-adjusted B/M within S&P 500.
- **Fits Bloasis**: Yes. **2nd-strongest candidate** (after residual momentum). Adds a non-momentum, non-text dimension.

#### B3. Betting Against (Bad) Beta (BABB) — 2024 update of Frazzini-Pedersen
- **URL**: https://arxiv.org/abs/2409.00416
- **Claim**: Double-sort on beta and "bad beta" (cash-flow shock exposure). Annualized SR 1.09 vs 1.01 for original BAB; +75 bp/mo alpha post trading costs.
- **Long-only friendly**: **Marginal.** BAB is fundamentally a long-low-beta / short-high-beta construction. Long-only version (just buy low-beta S&P 500) is well-known SPLV / USMV territory and gives ~SPY-equivalent returns with lower vol — sharpe improvement modest, alpha small.
- **Verdict**: **Defer.** Useful as a vol-control overlay, not as primary signal.

#### B4. Hidden Neighbors industry momentum — Bertasiute-Burda 2024
- **URL**: https://link.springer.com/article/10.1007/s11408-024-00455-4
- **Claim**: Industry momentum via stock-correlation + 10-K text-similarity networks. 2013-2022 annual return 18.16%, SR 0.85.
- **Difficulty**: 4/5 — graph construction + text-similarity matrix, weekly recompute.
- **Long-only friendly**: Yes (described as long-only).
- **Fits Bloasis**: Maybe, but expensive. SR 0.85 is comparable to our JT clean (0.86) — **not clearly better**. Skip unless we want graph features anyway.

#### B5. Jensen-Kelly-Pedersen "Is There a Replication Crisis" themes — meta-result
- **URL**: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3774514
- **Use**: Reference doc, not a signal. The 13 factor themes list (momentum, profitability, investment, value, quality, low-risk, accruals, size, debt issuance, ...) tells us **which factor families survive joint testing**. Use to prioritize which AQR-style score components to add.

### Group C — LLM-augmented alpha

#### C1. AlphaPortfolio (Cong-Tang-Wang-Zhang, 2021/2022) + transformer asset pricing
- **URL**: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3554486
- **Claim**: Transformer + cross-asset attention + RL portfolio construction. SR > 2, alpha > 13% in US equities OOS.
- **Verdict**: **Skip — infra mismatch.** Long-short, deep RL, monthly retrain on ~50 features. Bloasis is long-only CLI. The result is impressive but not portable to our stack without a full rewrite. Note also that Yuan-Zhang AFA 2024 paper "Optimizing portfolio weights with ML" finds that the ML alpha shrinks dramatically once realistic constraints (long-only, large-cap, transaction costs) are imposed.

#### C2. Instrumented PCA — Kelly-Pruitt-Su (JFE 2019, ongoing 2024)
- **URL**: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2983919, https://github.com/bkelly-lab/ipca
- **Claim**: Latent factors with characteristic-instrumented loadings. Strong in-sample fit; OOS alpha modest.
- **Verdict**: **Skip for v1.** Useful as a research benchmark but doesn't directly produce a long-only S&P 500 stock-picking signal without further engineering. Public Python lib exists (`bkelly-lab/ipca`).

#### C3. ChatGPT-on-headlines decay (Lopez-Lira-Tang updated through 2024Q1)
- **URL**: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4412788, https://arxiv.org/html/2304.07619v6
- **Update**: Annualized SR 6.54 (2021Q4) → 3.68 (2022) → 2.33 (2023) → 1.22 (Jan-May 2024). **Decay confirmed.** GPT-4 still beats GPT-3.5 / FinBERT, but the gap narrows.
- **Bloasis status**: Already attempted via Ollama, failed. Match: this paper says **only complex frontier LLMs (GPT-4 / Claude Opus level)** sustain alpha — local Ollama models are not enough. Either accept the API cost ($$$) or skip.
- **Verdict**: Skip headline-news LLM scoring. Pivot LLM budget to **A1 (Q&A on earnings calls)** where signal is more durable.

#### C4. Foundation models for finance / TimeFM (2024-2025)
- **URL**: https://arxiv.org/html/2511.18578v1
- **Verdict**: Too early. SR claims not yet replicated cross-period. Skip.

### Group D — Long-only large-cap survivors

#### D1. Jensen-Kelly-Pedersen "13 themes" applied long-only (already covered B1, B2)
The two themes that most clearly survive long-only large-cap testing per their paper are: **Momentum (residualized)** and **Quality / Profitability (which we have via QMJ)**. Value also survives but only in the **Intangible Value** form (B2).

#### D2. Form 4 insider buying clusters
- **URL**: https://alphaarchitect.com/following-what-insiders-dont-trade/, https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2657877
- **Claim**: Cluster-detected opportunistic insider buying (3+ insiders, 10-day window, open market only) → 6-month alpha ~5.2%. Original Cohen-Malloy-Pomorski 2012 "Decoding Inside Information" predates this but is updated through 2023 in alpha-architect. Implementable trading strategy "buy not-sold stocks following disclosure of a sale" earns ~4.8% net alpha (Cohen et al).
- **Data**: SEC Form 4 free via EDGAR.
- **Difficulty**: 2/5 — parse Form 4 transactions, group by ticker × 10-day window, count unique reporting persons.
- **Long-only friendly**: Yes by construction.
- **Fits Bloasis**: Strong yes.

### Group E — Trade execution / portfolio construction

#### E1. Smoothing Out Momentum and Reversal — Chitsiripanich, Paolella, Polak, Walker (2024)
- **URL**: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4955388
- **Claim**: Combined turnover-management mechanisms (signal smoothing + tolerance bands + position-decay) on daily-rebalanced momentum cut turnover 95-99% to monthly-equivalent levels with no return loss. Equivalently: standard monthly rebal + 20% tolerance band adds ~0.24%/yr CAGR, improves SR, reduces max DD.
- **Difficulty**: 1/5 — tolerance band logic is ~20 lines.
- **Verdict**: **Ship in v1, applied to whichever signal we use.**

#### E2. Time-Series Efficient Factors — Ehsani-Linnainmaa (2020)
- **URL**: https://rodneywhitecenter.wharton.upenn.edu/wp-content/uploads/2020/02/EhsaniLinnainmaa_TimeSeriesEfficientFactors_Dec2019.pdf
- **Claim**: Smoothing factor expected returns by their own past returns improves SR. HML SR up 0.22 units.
- **Difficulty**: 2/5 — exponential smoothing of factor signals.
- **Verdict**: Apply to ML scorer signal smoothing; cheap upgrade.

#### E3. Nonlinear Time-Series Momentum — Moskowitz, Sabbatucci, Tamoni, Uhl (SSRN 2025)
- **URL**: https://papers.ssrn.com/sol3/Delivery.cfm/5933974.pdf
- **Claim**: ML-discovered nonlinear price-trend → return relationship. Significant OOS gains over linear TSMOM.
- **Verdict**: TSMOM is asset-class trend-following, not stock-picking. **Out of scope** for long-only S&P 500. Skip.

---

## Top 5 Actionable Signals to Implement Next

Ranked by (alpha potential × ease × data accessibility):

| Rank | Signal | Paper | Score |
|---|---|---|---|
| 1 | **Residual Momentum (12-1 on FF3 residuals)** | Blitz-Hanauer-Vidojevic 2020 | Alpha hi · Ease 2/5 · Data free |
| 2 | **Tolerance-band rebalance overlay** | Chitsiripanich et al 2024 | Alpha mid · Ease 1/5 · Data N/A — ship on whatever signal we pick |
| 3 | **Intangible Value (within-industry, capitalized SG&A)** | Eisfeldt-Kim-Papanikolaou 2022 | Alpha hi · Ease 3/5 · Data semi-free (XBRL) |
| 4 | **Form 4 insider buying clusters (3+ insiders / 10d)** | Cohen-Jackson-Mitts + alpha-architect | Alpha mid-hi · Ease 2/5 · Data free |
| 5 | **8-K item-trigger event drift (Item 1.01, 5.02, 8.01)** | Cohen-Jackson-Mitts 2015 + Lerman-Livnat 2010 | Alpha mid · Ease 2/5 · Data free |

**Also-rans (defer to v2):**

- 6: Earnings Call Q&A FinBERT (alpha hi, but data acquisition + LLM cost = ease 4/5)
- 7: Time-series factor smoothing on ML scorer (ease 2/5, alpha mid, applies inside Phase 2 ML stack)
- 8: Hidden Neighbors industry momentum (alpha unclear vs JT, ease 4/5)

**Recommended sequencing for Bloasis Phase 3:**

1. **Week 1**: Ship residual momentum as a JT replacement. Re-run measurement gate. If SR > 0.99 and DD < 1.0, this alone may close the JT gap.
2. **Week 1–2**: Add tolerance-band rebalance overlay to the residual-momentum signal. Cheap.
3. **Week 3**: Implement Form 4 cluster signal as a separate factor; blend with residual-mom + EDGAR cosine in score-combine framework (AQR-style integrated, per existing Research_AQR_Factor_Blend.md).
4. **Week 4**: Implement Intangible Value if XBRL fundamentals plumbing is already in place; otherwise defer.
5. **Phase 4+**: Earnings Call Q&A only after transcript data source is decided.

---

## Sources

- [Blitz-Hanauer-Vidojevic — The Idiosyncratic Momentum Anomaly (SSRN)](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2947044)
- [Idiosyncratic Momentum Anomaly — JBF 2020](https://www.sciencedirect.com/science/article/abs/pii/S1059056020300927)
- [Eisfeldt-Kim-Papanikolaou — Intangible Value (SSRN)](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3720983)
- [Intangible Value — NBER 28056](https://www.nber.org/papers/w28056)
- [Bongaerts — Revisiting Asset Pricing: Intangibles Factor (FM 2024)](https://onlinelibrary.wiley.com/doi/full/10.1111/fima.70001)
- [Jensen-Kelly-Pedersen — Is There a Replication Crisis in Finance? (SSRN)](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3774514)
- [Replication Crisis code (bkelly-lab)](https://github.com/bkelly-lab/ReplicationCrisis)
- [Hou-Xue-Zhang — Replicating Anomalies (SSRN)](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2961979)
- [Lopez-Lira-Tang — Can ChatGPT Forecast Stock Price Movements? (arXiv v6)](https://arxiv.org/html/2304.07619v6)
- [Cong-Tang-Wang-Zhang — AlphaPortfolio (SSRN)](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3554486)
- [Kelly-Pruitt-Su — Instrumented PCA (SSRN)](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2983919)
- [bkelly-lab/ipca Python library](https://github.com/bkelly-lab/ipca)
- [Cohen-Jackson-Mitts — The 8-K Trading Gap (SSRN)](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2657877)
- [Lerman-Livnat — The New Form 8-K Disclosures (SSRN)](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=1126816)
- [Niessner — Who Pays Attention to SEC Form 8-K? (Notre Dame)](https://www3.nd.edu/~zda/8k.pdf)
- [Cohen-Malloy-Pomorski — alpha-architect insider trading replication](https://alphaarchitect.com/following-what-insiders-dont-trade/)
- [Huang et al — FinBERT (CAR 2023)](https://onlinelibrary.wiley.com/doi/abs/10.1111/1911-3846.12832)
- [SubjECTive-QA — Earnings Call Q&A subjectivity (arXiv 2024)](https://arxiv.org/html/2410.20651v1)
- [ExtractAlpha — US Transcripts Model factsheet](https://extractalpha.com/fact-sheet/transcripts-model-us/)
- [Bushee et al — SEC Comment Letters & Earnings Calls (Mgmt Sci 2024)](https://pubsonline.informs.org/doi/10.1287/mnsc.2023.02065)
- [Loughran-McDonald — Measuring Firm Complexity (JFQA 2024)](https://www.cambridge.org/core/journals/journal-of-financial-and-quantitative-analysis/article/measuring-firm-complexity/D737FD0A697AF699C5AADD62842ACAB8)
- [Bradley-Hanousek-Jame — Place Your Bets WSB (working paper)](http://russelljame.com/wsb_10_19_23.pdf)
- [WSB sentiment & retail returns — ScienceDirect 2024](https://www.sciencedirect.com/science/article/pii/S1057521924006537)
- [BABB — Betting Against (Bad) Beta (arXiv 2024)](https://arxiv.org/abs/2409.00416)
- [Hidden Neighbors industry momentum — FMPM 2024](https://link.springer.com/article/10.1007/s11408-024-00455-4)
- [Chitsiripanich et al — Smoothing Out Momentum and Reversal (SSRN 2024)](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4955388)
- [Ehsani-Linnainmaa — Time-Series Efficient Factors (Wharton WP)](https://rodneywhitecenter.wharton.upenn.edu/wp-content/uploads/2020/02/EhsaniLinnainmaa_TimeSeriesEfficientFactors_Dec2019.pdf)
- [Moskowitz-Sabbatucci-Tamoni-Uhl — Nonlinear Time Series Momentum (SSRN 2025)](https://papers.ssrn.com/sol3/Delivery.cfm/5933974.pdf?abstractid=5933974)
- [Beyond the last surprise: Reviving PEAD with ML (Finance Research Letters 2025)](https://www.sciencedirect.com/science/article/abs/pii/S1544612325020057)
- [alpha-architect — short-term signals replication](https://alphaarchitect.com/alpha-from-short-term-signals-may-survive-market-frictions/)
