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

<!-- filled in after the run -->
