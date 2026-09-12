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
