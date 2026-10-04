# E2E checklist — skill-relative paper gate (#88)

`bloasis.backtest.skill_gate` judges a candidate against random books with
matching turnover in its own frame. `scripts/skill-gate.py` produces those
books and the verdict.

## Pre-merge
- [x] `scripts/skill-gate.py --config configs/edgar-rolling2.yaml --window dev`
      reproduces the corrected #108 development baseline exactly (R2 DD p10
      0.865, α p90 +5.29%; R1 DD p10 0.891), because the frame and seeds are
      the same. Run 2026-10-04 on a sector-populated panel: R1 DD p10/median/p90
      0.891 / 0.989 / 1.116, R2 0.865 / 0.952 / 1.108, R2 α p90 +5.29%. These
      are identical to the post-#109 re-run of the #108 driver. The first
      attempt hit the 2 h background limit while the random books recomputed
      10-K cosines they do not use; the baselines now run on a panel without
      10-K text.
- [x] Its verdict on `edgar-rolling2` is the one #108 implies: matched kind
      R2, fail on both DD and α. The script exits 1. Verdict: `passed=False`,
      `baseline_kind=R2`, reasons "dd 0.873 not below random R2 p10 0.865" and
      "alpha +0.0374 not above random R2 p90 +0.0529". The detached run's exit
      code was not captured; `main()` returns 1 whenever `passed` is False.
- [x] The candidate row equals the recorded `edgar-rolling2` development
      result (DD 0.873 / α +3.74% / 398 trades). DD 0.87335, α +3.7424%,
      398 trades.
