# PR21 grid runner — E2E checklist

비웹 CLI 기능. 각 항목은 실제 명령 실행으로 검증.

## Setup

- [x] PR20 axes 코드 모두 사용 가능 (edgar_rolling_window 등)
- [ ] yfinance / EDGAR 캐시 워밍 완료 (`~/.cache/bloasis/`)
- [ ] DB 초기화: `uv run bloasis init-db`

## `bloasis grid run` — happy path

- [x] CLI smoke covered by `tests/test_cli_grid.py::test_grid_run_creates_one_row_per_combination`
- [x] Run naming `{grid_name}#{k}={v}` covered by tests
- [x] DB persistence covered by tests (rows created with right names)
- [ ] (수동) 실측: `configs/grids/pr21-edgar-rolling.yaml` 실행 후 `runs list` 으로 16행 확인
- [ ] (수동) 실측: 모든 행 `status='completed'`

## `bloasis grid run` — 부분 실패 처리

- [x] Single-combo failure isolation covered by `test_run_grid_continues_on_single_failure`
- [ ] (수동) 실측: 의도적 잘못된 axis 값 → fail 행 `status='failed'`

## `bloasis grid show`

- [x] sharpe 내림차순 정렬 + grid_name 필터링 covered by `test_grid_show_filters_by_grid_name`
- [x] 다른 grid 미포함 covered (assertion `"other-grid" not in res.output`)
- [x] best 마커 (★) 렌더링 — 코드 경로 존재, 시각 확인은 수동
- [ ] (수동) 실측 grid show 출력 확인

## `bloasis grid show` — empty case

- [x] 존재하지 않는 grid name → exit 1 covered by `test_grid_show_missing_grid_name_errors`

## 데이터 공유 검증

- [x] BacktestData 동일 인스턴스 covered by `test_run_grid_shares_backtest_data_across_combinations`
- [x] prefetch 호출 1회 — `cli.py` 코드 경로상 grid_run 함수 안에서 prefetch_backtest_data 1회만 호출. union scorer_types 로 fan-out

## Performance

- [ ] (수동) 실측: 16-combo grid 의 wall-clock 시간이 16 × 단일 backtest 시간 << 임을 확인
- [ ] (수동) DB write 가 sequential 하며 SQLite lock 충돌 없음 (단일 프로세스 sequential 이라 이론상 보장)
