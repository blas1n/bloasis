# Research & Measurement Log

Phase 1~3 의 측정 로그·리서치·설계 lock-in. **코드가 이 문서들을 spec 으로 인용한다**
(`scoring/regime_overlay.py` · `ml/training.py` · `data/fetchers/*` · `configs/*.yaml` 등).

## 왜 레포 안에 있나

2026-09-12 까지 이 문서들은 레포 **밖**(`~/Docs/bloasis/`)에 있었다. 원격/클라우드
세션은 clone 하나만 갖기 때문에, spec 이 레포 밖이면 그 세션은 **인용만 보고 내용은
못 본다.** 코드 주석 인용 6종은 전부 살아 있었다(생존율 6/6) — 실제로 쓰이는
문서라서 안으로 들어왔다.

## 무엇이 있나

| 묶음 | 파일 |
|---|---|
| **Phase 1** | `Phase1_Measurement_2026-05-05.md` · `Phase1_Exit_Gate_Handoff_2026-05-05.md` |
| **Phase 2 (rule + LightGBM)** | `Phase2_ML_Design_Lockin_2026-05-07.md` · `Phase2_Final_Measurement_2026-05-07.md` · **`Phase2_Postmortem_2026-05-07.md`** |
| **Phase 3 (modern candidates)** | `Phase3_Modern_Candidates_2026-05-08.md` · `Phase3D_Final_Measurement_2026-05-09.md` |
| **PR 측정 로그** | `PR12_*` · `PR18_*` · `PR19_*` · `PR20_*` · `PR21_*` · `PR22_*` · `PR23_*` |
| **게이트 재산정** | `EDGAR_Rolling2_Gate_Remeasurement_2026-10-01.md` |
| **리서치 (spec 원본)** | `Research_DM_Dynamic_Momentum.md` · `Research_AQR_Factor_Blend.md` · `Research_Qlib_Features.md` · `Quant_References.md` · `Quant_Robustness_2026-05-07.md` · `Modern_Alpha_Research_2026-05-09.md` · `Modern_AI_Investing_References_2026-05-07.md` |
| **재설계** | `Redesign_Brief_2026-05-07.md` |
| **이벤트 스터디** | `Trump_Mention_Event_Study_2026-06-03.md` · `Trump_Mention_Baseline_Correction_2026-06-03.md` |
| **백로그** | `Strategy_Backlog.md` |

## 읽는 순서

막 들어왔다면 **`Phase2_Postmortem_2026-05-07.md` → `Redesign_Brief_2026-05-07.md`**.
왜 rule+LightGBM 을 접고 지금 구조로 왔는지가 거기 있다. 진 경로를 다시 걷지 않으려면
`docs/limitations.md` 도 같이 읽어라.

## 성격

**측정 로그는 그 시점의 기록이다 — 갱신하지 않는다.** 결과가 달라졌으면 새 측정
문서를 쓰고, 낡은 결론을 근거로 쓰기 전에 다시 재라.

## 사전등록 규칙 (2026-10-02 채택, #103)

전략 후보·설정 변경·신호 교정은 **측정 전에** 아래를 커밋한다. 템플릿:
`DD_Reduction_Sweep_2026-10-01.md`, `Name_Normalization_2026-10-02.md`,
`Edge_Robustness_2026-10-02.md`.

1. **질문**: 무엇을 판정하려는가.
2. **arm 목록**: 고정한다. 결과를 본 뒤 arm 을 더하지 않는다.
3. **프로토콜**: 구간, fold, 유니버스, 패널 공유 방식.
4. **판정 규칙**: 채택·기각·결론 불가의 조건을 숫자로 적는다.
5. 결과는 같은 문서의 `## Results` 에 **전부** 적는다(최고 arm 만 적지 않는다).
   규칙상 결론과 그 밖의 해석은 따로 적는다.

페이퍼 진입 조건(개발 구간 관문 + 홀드아웃 H1·H2 + 취약성 검사)은
`docs/mission.md` 의 Paper-trading gate 에 있다. 홀드아웃은 후보당 한 번만 돌린다.

## 다중검정 장부 — 개발 구간(2022-01..2024-10)에서 돌린 arm

새 후보의 개발 구간 결과를 읽을 때 이 수를 같이 본다. 많이 돌린 구간에서 나온
최고값은 그만큼 운이 섞여 있다. 행 단위로만 추가한다.

| 날짜 | 기록 | arm 수 | 비고 |
|---|---|---|---|
| 2026-05-09 | PR20 | 7 | `edgar-rolling2`(A) 가 이 중 최고로 선택됨 |
| 2026-05-09 | PR21–23 | 41 | roadmap 기재 수. PEAD·overlay·position size·fundamental LLM·knobs·intersect |
| 2026-10-01 | #85 DD sweep | 17 | 사전등록. 통과 0 (#92·#93 재측정 후) |
| 2026-10-02 | #99 이름 정규화 | 1 | 사전등록. 미채택 |
| 2026-10-02 | #95 position size 재현 | 5 | 기존 그리드 재현. 선택 없음 |
| **누계** | | **71+** | PR19 이전 측정은 이 표에 없다 |

홀드아웃 사용 기록: H2(2018–2021)는 #102 에서 `edgar-rolling2` raw/normalized
2 arm 으로 한 번 사용했다.
