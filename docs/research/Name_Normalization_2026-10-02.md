# Registrant-name normalization — pre-registration and result (2026-10-02)

Point-in-time record. Per `docs/research/README.md`, measurement logs are not
updated after the fact.

Issue: [#99](https://github.com/blas1n/bloasis/issues/99).

## Finding that prompted this

JPM's rolling (w2) risk-factor cosine was 0.704, the lowest of 485 eligible S&P
500 names. The Item 1A extraction is fine: every year ends at Item 1B. The cause
is the cosine itself. It is a raw term-frequency cosine, and a company's own
name is usually its most frequent token. In its FY2024 10-K, JPM began writing
"JPMorganChase" as one word:

```
FY2023 top tokens: jpmorgan 538, chase 536, ...
FY2024 top tokens: jpmorganchase 533, ...
FY2024 vs FY2023 cosine 0.4255   (every other JPM year pair ≥ 0.994)
```

Any rebrand or re-spelling of a registrant's name (Facebook → Meta, a merger
renaming, a style change like JPM's) depresses the "Lazy Prices" cosine without
any change in the risk language it is meant to measure.

## Question

Does removing each registrant's **distinctive** name forms before the cosine
remove this artefact without otherwise changing what the strategy measures?

## Pre-registration

Written and committed **before** the variant was run.

### Variant (fixed)

`scripts/name-norm-99.py`, `name_forms()` / `strip_forms()`:

- Names come from the registrant's SEC submissions: the `name`, every
  `formerNames[].name`, and the same for a declared successor's predecessor.
- Drop legal forms (`inc`, `corp`, `co`, …). Of the remaining words, remove
  every distinctive word of 4+ letters. A word is distinctive if it is not in
  the fixed `GENERIC_NAME_WORDS` list (legal form, industry and geography
  words such as `energy`, `financial`, `bank`, `southern`). Also remove every
  joined run of 2+ adjacent name words (`jpmorganchase`, `metaplatforms`).
- Matching is case-insensitive and letter-bounded. Removal happens before the
  unchanged tokenizer, so nothing else about the cosine changes.

An earlier exploratory pass that also dropped generic name words (`energy`,
`financial`, `health`, …) moved names near the selection cutoff for reasons
unrelated to rebrands (3 of 48 swapped). That pass is why the generic list
exists. It was not measured on the backtest and is not an arm here.

### Protocol

- **Validity check**: JPM FY2024 vs FY2023 pairwise cosine, raw vs normalized.
- **Backtest**: canonical 7-fold walk-forward
  (`configs/grids/pr21-edgar-rolling.yaml`: 2022-01-01..2024-10-17, train 180
  / test 120 / step 120), universe `sp500_at:2024-12-31`, `edgar-rolling2`.
  One prefetch, one panel; the normalized arm differs only in its
  `risk_factors_history` texts.
- **Live**: today's (2026-10-02) sp500 rolling cosines with the engine's rule
  (filing lag, w2). Report the top-10% selection raw vs normalized.
- Cloned cache; nothing is written to the run DB.

### Decision rule (fixed in advance)

The variant is **adopted** only if all of these hold:

```
validity:  JPM FY2024-vs-FY2023 normalized cosine >= 0.95
backtest:  median sharpe vs SPY  >= raw - 0.02
           median alpha          >= raw - 0.005
           median max-DD ratio   <= raw + 0.01
           folds = 7
```

This is a measurement-correctness fix, not a performance search. An
improvement is neither required nor a reason to adopt it, and no second
variant is tried if this one fails. If it is adopted and today's live
selection changes, the paper session is rotated, as #86 did for #83.

## Results

Run 2026-10-02, one process, cloned cache.

**Validity: passes.** JPM FY2024 vs FY2023 is 0.4255 raw and **0.9964**
normalized, back in line with its other year pairs (≥ 0.994).

**Backtest (7 folds): fails all three tolerances.**

| arm | DD ratio | sharpe vs SPY | α/yr | trades |
|---|---|---|---|---|
| raw (live config) | 0.873 | 1.013 | +3.74% | 398 |
| normalized | 0.933 | 0.951 | +0.01% | 406 |
| tolerance | ≤ 0.883 | ≥ 0.993 | ≥ +3.24% | |

```
per-fold DD  raw         0.873 0.768 1.478 1.063 0.772 1.004 0.626
             normalized  0.933 0.776 1.405 1.065 0.820 0.982 0.756
```

**Live (2026-10-02):** 485 eligible; 6 names move by more than 0.01 (JPM
0.704 → 0.981, WMB 0.790 → 0.877, OXY 0.839 → 0.915, ETN, FITB, ABT); the
cutoff goes from 0.99669 to 0.99645; 46 of 48 selected names are kept (+SYF,
+TTWO / −EVRG, −SOLV).

### Verdict

**Not adopted.** The variant fixes the artefact it targets, but costs 0.06
sharpe and 3.7pp of α and adds 0.06 to DD on the canonical protocol. Per the
pre-registration, no second variant is tried, and the live scorer and the
paper session are unchanged.

### What this implies — read before trusting the edge

The variant changes only one thing: the registrant's own name no longer
counts toward the cosine. That removing it erases nearly all of the backtest
α (+3.74% → +0.01%) means **a large part of `edgar-rolling2`'s measured edge
moves with name-token frequency, not with risk-factor language**.

The mechanism is plausible. A name repeated hundreds of times is a large,
nearly constant component of both years' vectors, and it pulls the cosine
toward 1. It does so most for registrants that repeat their own name: FITB's
name is 11.6% of its tokens, and its cosine drops from 0.9941 to 0.9808 once the
name is removed. Which selected names owe their place to this was not broken
down here.

This is one in-sample protocol, 7 folds, and α differences of a few points
are within what the project has called noise before. It is not proof that the
edge is an artefact, but it is the first measurement that ties the edge to
something other than the hypothesis it was shipped on. It bears directly on
the 6-month paper record (#85, #88) that the real-money decision will rest
on.

Raw output: the driver's JSON (`--out`), not committed.
