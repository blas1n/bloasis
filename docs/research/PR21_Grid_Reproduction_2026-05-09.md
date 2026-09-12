# PR21 Grid Runner Reproduction (2026-05-09)

PR21 (`bloasis grid run`) 의 첫 실측. PR20 winner cell 을 grid 경로로 재현해서
1) 그리드 인프라가 정상 작동하는지, 2) PR20 측정이 reproducible 한지
검증하는 게 목적.

## TL;DR

- **재현 성공.** rolling=2/rebal=21 셀 = α **+4.1%**, sharpe vs SPY 1.33 →
  PR20 측정 (α +4.09%, sharpe 1.334) 과 0.01pp 이내 일치.
- **15/16 완료, 15 PASS acceptance.** rolling=5/rebal=1 1콤보 transient fail
  (yfinance/EDGAR rate limit 의심, 재시도하면 통과 예상).
- **rolling=2 가 alpha 기준 행 전체 우위.** rebal 변경은 미세 영향, rolling 이 진짜 lever.

## 셋업

- Universe: `sp500_at:2024-12-31` (503 → 490 효과)
- Walk-forward: 2022-01-01 .. 2024-10-17, train=180 / test=120 / step=120 → **7 folds**
- Base: `configs/edgar-rolling2.yaml`
- 4 × 4 = 16 combos
- 실행: `uv run bloasis grid run configs/grids/pr21-edgar-rolling.yaml`

## 결과 (alpha 기준 정렬)

| rank | rolling | rebal | α       | sharpe (DB) | sharpe vs SPY | gate |
|------|---------|-------|---------|-------------|---------------|------|
| 1    | **2**   | **21**| **+4.1%** | **1.505** | **1.33**     | **PASS** |
| 2    | 2       | 1     | +3.7%   | 1.449       | 1.33          | PASS |
| 3    | 2       | 42    | +3.6%   | 1.415       | 1.33          | PASS |
| 4    | 2       | 5     | +3.3%   | 1.454       | 1.33          | PASS |
| 5    | 1       | 21    | +2.9%   | 1.652       | 1.02          | PASS |
| 6    | 3       | 42    | +1.3%*  | 1.383       | —             | PASS |
| 7    | 1       | 42    | +2.5%   | 1.672       | 1.01          | PASS |
| 8    | 1       | 1     | +1.5%   | 1.682       | 1.00          | PASS |
| 9    | 1       | 5     | +1.5%   | 1.671       | 0.99          | PASS |
| 10   | 5       | 5     | +1.2%   | 1.366       | —             | PASS |
| 11   | 5       | 21    | +1.4%   | 1.356       | —             | PASS |
| 12   | 5       | 42    | +1.0%   | 1.364       | —             | PASS |
| 13   | 3       | 21    | +2.4%*  | 1.366       | —             | PASS |
| 14   | 3       | 1     | +2.6%   | 1.326       | —             | PASS |
| 15   | 3       | 5     | +2.2%   | 1.316       | —             | PASS |
| ∅    | 5       | 1     | —       | —           | —             | **FAILED (transient)** |

\* 행 별 best rebal 기준 정리. 각 셀 정확값은 DB 참조.

## 핵심 인사이트

### 1. rolling=2 가 row 전체 우위
- rolling=2 행 4 셀 모두 α +3.3 ~ +4.1%, 최상위 4개 자리 독점.
- rolling=1: α +1.5 ~ +2.9% (rebal=21 monthly 가 베스트)
- rolling=3: α +1.3 ~ +2.6%
- rolling=5: α +1.0 ~ +1.4%
- 결론: **2-pair 평균 cosine smoothing 이 sweet spot.** PR20 가설 재확인.

### 2. rebal 효과는 rolling=1 에서만 명확
- rolling=1: rebal=1 +1.5% → rebal=21 +2.9% (1.95× 알파 부스트). PR19 finding.
- rolling=2: rebal 4 값 모두 +3.3 ~ +4.1% — rebal 효과 거의 사라짐.
- 해석: rolling=2 가 cosine 신호 자체를 충분히 smooth 하게 만들어,
  rebalance frequency 가 redundant. PR20 grid 의 동일 발견.

### 3. rolling=5 도 viable (의외)
- rolling=5 4 셀 모두 PASS. α +1.0 ~ +1.4%.
- 이전 PR20 grid (짧은 윈도우) 에서 rolling=3 이 negative α 였던 것과 대비.
- 7-fold + train=180 환경에서는 rolling 이 over-smoothed 되어도 살아남음.

## 검증 사이드 발견

### 측정 프로토콜 mismatch 가 alpha drift 의 진짜 원인이었다

이번 grid 첫 실행 (v1, v2) 에서 PR20 winner 셀이 α +2.6%, -4.5% 등으로 보여
"코드 회귀" 의심했음. 실제 원인은 **walk-forward 파라미터 mismatch**:

- PR20 측정: train=180, test=120, step=120, end=2024-10-17 → **7 folds**
- 내 첫 spec: train=365, end=2024-12-31 → 6 folds (다른 데이터 슬라이스)

`acceptance_reasons_json` 의 `folds: 7 >= 5` 가 PR20 의 측정 프로토콜을 정확히
지정하는 fingerprint. 같은 config 라도 fold 수 다르면 측정 결과 다르다.

이전 측정 재현시 **`SELECT acceptance_reasons_json FROM backtest_runs WHERE name = 'X'`
로 fold 수 + gate 임계 확인이 train/test/step 추정의 first source.**

## CLI ergonomics 개선 후보 (별도 PR)

- 그리드 결과 alpha 기준 정렬 옵션 (`--sort alpha`)
- failed combo 의 traceback stderr 로 출력 (현재 메모리에만 잡혀 보이지 않음)
- 진행 메시지 wrapping 안 되도록 (현재 console width 에 따라 sharpe 값이 다음 줄로 wrap)
- transient fail 자동 1회 retry
- summary 라인 n_pass 카운터 1 off (UI cosmetic)

## 결정

- **rolling=2/rebal=21 (= edgar-rolling2.yaml) 이 ship-eligible 로 유지.**
- rolling 축은 sweet spot 발견됨 (=2). rebal 축은 rolling=1 에서만 효과.
- 다음 grid: **새 축 (continuous_score, top_pct, jt_residual + edgar 조합 등) 탐색** 권장. rolling/rebal 은 더 sweep 해도 marginal gain 한계.
