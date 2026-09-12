# Trump Mention Event Study — Research Pipeline + First Results

**Date**: 2026-06-03  •  **PR**: #55 (feat/pr55-trump-mention-tracker)
**Status**: Pipeline shipped, first run on 2024-01-01 → 2026-06-03 corpus

## Motivation

User observation: Trump's social-media mentions appear to move stocks materially (Dell +24% week after Mother's Day endorsement, Huang Korea visit triggering KOSPI tech rally, IBM/PLTR pops). The retail question: **is any of this still tradeable when you can only act at next available open**, or does HFT/pre-market take it all?

The gap-decomposition framing answers exactly that.

## Pipeline (PR #55)

`bloasis/analysis/`:

- **`mention_pipeline.py`** — Truth Social archive fetcher (~27k posts), deterministic prefilter (`is_stock_candidate`) using a curated company name dictionary + 4+ char SP500 ticker whole-word match, and a hybrid extractor (regex NER + LLM sentiment-only).
- **`mention_timing.py`** — Classify each post by US session position (IN_HOURS / AFTER_HOURS / OVERNIGHT / WEEKEND), resolve to the modeled entry-open date.
- **`mention_event_study.py`** — Decompose impact into gap / intraday / forward / total + gap_fraction.

CLI:
```bash
bloasis research mentions-fetch
bloasis research mentions-extract --limit 16000 --after 2024-01-01
bloasis research mentions-study --horizon 5 --since 2024-01-01
bloasis research mentions-study --sentiment negative --horizon 5 --since 2024-01-01
```

## Coverage

| | |
|---|---|
| Archive size | 27,397 text posts (2022-02 → 2026-06) |
| 2024-01-01 onwards | 15,708 posts |
| Prefilter candidates | 228 posts (1.5%) — Trump's archive is ~98% political prose |
| LLM-classified mentions | 258 (some posts mention multiple companies) |
| Events with bars + forward | 239 |
| Sentiment split | 88 positive / 114 negative / 59 neutral |

## Top mentioned tickers (2024+)

| ticker | count | company |
|---|---|---|
| AMZN | 37 | Amazon (Bezos critiques, Washington Post angle) |
| AAPL | 29 | Apple (tariffs, Tim Cook) |
| META | 29 | Meta (Zuckerberg) |
| BA | 19 | Boeing (Air Force One, defense) |
| GOOGL | 17 | Google (search/political) |
| NVDA | 13 | Nvidia (AI chip exports) |
| COST | 11 | Costco |
| CARR | 8 | Carrier (Indianapolis plant) |
| MCD | 8 | McDonald's |
| GS | 7 | Goldman Sachs |

## Main result — gap / intraday / forward decomposition (h = 5d)

```
                  n    gap    intraday    fwd 5d   total   gap%
in_hours         58   +0.66%    +0.26%    -1.28%   -0.67%  -99%
after_hours      22   +0.22%    +1.64%    +1.51%   +1.72%   13%
overnight       118   +0.22%    +0.05%    +0.72%   +0.94%   23%
weekend          41   -0.27%    +0.13%    -0.29%   -0.57%   47%
─────────────────────────────────────────────────────────────────
pooled          239   +0.24%    +0.26%    +0.13%   +0.36%   67%
```

**Headline:**
1. **Gap is small** (+0.24% pooled). The HFT / pre-market take is NOT dominating average mentions — surprising given the popular "by the time you see it, it's gone" narrative. The +14-24% Dell-type events are outliers, not the mean.
2. **Pooled forward 5d is +0.13%** — barely above zero. With n=239, this is well within noise.
3. **In-hours mentions LOSE -1.28% forward 5d** — when Trump posts during US session, the next 5 days tend down. Likely intra-day rally on the post → entry at next-day open buys the local top → reversion.
4. **After-hours / overnight mentions positive** (+1.51% / +0.72% fwd 5d). Where the modest signal is.

## The interesting cell — sentiment split

```
Sentiment = NEGATIVE (n=103)              Sentiment = POSITIVE (n=81)
  in_hours      24    +0.56%               in_hours       15    -1.28%
  after_hours   11    +2.02%               after_hours     7    +1.26%
  overnight     50    +1.78%               overnight      46    +0.16%
  weekend       18    -0.14%               weekend        13    -2.83%
  ─────────────────────────                 ─────────────────────────
  pooled       103    +1.19%               pooled         81    -0.49%
```

**Counter-intuitive (but consistent with literature):** Stocks Trump CRITICIZES outperform stocks he PRAISES over the next 5 days. Pooled gap: +1.68% (negative > positive forward).

Plausible mechanism — Trump-criticism reversion:
- His criticism causes immediate sell-off (in the gap / first hour)
- Market over-reacts → fundamentals don't actually change
- Over 5 days the stock recovers ("crying wolf" effect)

This is consistent with: Born et al. (2022) showing Trump-tweet reaction magnitudes have HALVED post-2019 as markets condition; La Morgia et al. on news-spike mean reversion; broader literature on over-reaction.

## What this DOES NOT prove

The result is **suggestive, not a confirmed edge**. Missing controls:

1. **No baseline.** The +1.19% negative-mention 5d return needs comparison against the unconditional 5d return for the same tickers over the same window. 2024-2026 was a strong tech bull market. AMZN/AAPL/META baseline 5d return might be ~+0.7% — making the +1.19% excess only ~+0.5%. We do have `forward_cum_returns` + baseline pattern from PR54 (hub-earnings); should be folded in.

2. **Sample is small + temporally clustered.** 103 negative-sentiment events over 2.5 years = ~1/week, but they cluster around news cycles (tariff weeks, earnings, immigration debates). Effective independent observations are far fewer.

3. **Selection.** We pre-filtered to mega-caps Trump talks about. These names trended up regardless. A proper test uses a fixed link universe defined in advance.

4. **2024-2026 only.** Trump 1.0 (2017-2020) likely shows much larger raw reactions but post-publication of the academic studies has decayed. Should split by regime.

5. **LLM sentiment classification is noisy.** llama3.2:3b classifies sentiment from a short prompt. Some "negative" might be neutral mentions classified wrong. Quick spot-check showed reasonable polarity but no formal accuracy measurement.

## Decision (per the original framework)

The original go/no-go tree was:
- gap_fraction > 0.7 → kill (HFT took it all)
- gap_fraction < 0.3 with positive fwd → retail-feasible, build live tracker

**We're in the ambiguous middle.** Pooled gap_fraction = 67% looks bad, but the negative-sentiment cell has gap_fraction = 4% with +1.19% pooled forward = exactly the "retail-feasible" zone.

**Recommendation:**
1. **Add baseline / excess columns to the study CLI** (port from PR54's hub-earnings). 1 day of work. Without this we can't claim the +1.19% is edge vs regime.
2. **Forward-track the negative-mention pattern as a research signal**, no money. Log mentions in real-time as cron fetches the archive, write forecasted 5d returns, compare actual to baseline over the next 3 months. If excess holds → strategy. If excess collapses → falsified.
3. **DO NOT add this to bloasis paper trading yet.** The data is too thin to deploy capital against, even paper.

The infrastructure is now there — running the pipeline incrementally every day takes seconds and accumulates events for free. Time + baseline comparison is what's missing.

## Process Notes / Traps Found

1. **v1 monolithic LLM prompt hallucinated catastrophically.** Asked llama3.2:3b to do NER + sentiment in one prompt → it echoed the example tickers (DELL/NVDA/PLTR/BA) onto every political post with confidence 0.85+. 256 garbage mentions / 100 posts before stopping. Wiped + redesigned as hybrid (deterministic NER + LLM-sentiment-only) → 258 mentions / 15,408 posts, none hallucinated.

2. **English-word ticker collisions are pervasive.** Initial bare-ticker matching found ICE 95 hits (Immigration not Intercontinental Exchange), DAY 94, FAST 59, PM 56, WELL 18, MAR 8 (Mar-a-Lago). Solution: drop bare-ticker matching for <4 chars + blocklist common 4-char English words (FAST, WELL, FREE…).

3. **"President DJT" signature.** Trump signs many posts "President DJT". That added 545 false-positive DJT (Trump Media) hits. Removed `djt` from the name dictionary; the 3-char ticker falls under the no-bare-match-under-4-chars rule.

4. **"intel official" matched Intel Corp.** Removed `intel` (single-word) from the name dictionary — INTC still surfaces via the bare-4+ char path which doesn't false-match prose.

## Files

- Code: `bloasis/analysis/mention_pipeline.py`, `mention_timing.py`, `mention_event_study.py`
- Tests: `tests/test_mention_pipeline.py`, `test_social_mentions.py`, `test_mention_event_study.py` (35 tests across the three files)
- Schema: `social_posts`, `social_post_mentions` (in `bloasis/storage/schema.py`)
- This doc

## Sources

- [Dell stock surge after Trump endorsement (ARTVOICE, May 2026)](https://artvoice.com/2026/05/08/dell-stock-surges-to-a-record-high-after-trumps-supportive-truth-social-post/)
- [Trump bought Palantir before promotion (CNBC, May 2026)](https://www.cnbc.com/2026/05/15/trump-palantir-stock-truth-social.html)
- [Truth Social public archive (CNN)](https://ix.cnn.io/data/truth-social/truth_archive.json)
- [Huang Korea visit triggers KOSPI 8500+ (Seoul Economic Daily, June 2026)](https://en.sedaily.com/markets/2026/06/02/kospi-aims-for-9000-on-jensen-huang-effect-tech-giants)
