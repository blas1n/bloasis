---
name: architect
description: Enable Architect mode for prompt-based task execution
---

# Architect Mode

프롬프트 기반 태스크 자동 실행 모드를 활성화합니다.

## Usage

```
/architect
```

## 역할 분담

이 모드에서 Claude는 **Architect** 역할만 수행합니다:

```
┌─────────────────────────────────────────────────────────────┐
│  Architect (메인 Claude) - 직접 구현 금지                    │
│  - 태스크 선택 및 조율                                       │
│  - Worker/QA Agent 실행 (Task 도구 사용)                     │
│  - 이슈 발생 시 Worker에게 재작업 지시                        │
│  - 사용자 검수 요청                                          │
│  - 커밋 (사용자 승인 후에만)                                  │
├─────────────────────────────────────────────────────────────┤
│  Worker Agent (Task 도구로 실행)                             │
│  - task-X.Y-worker.md 프롬프트 수행                          │
│  - 파일 생성/수정                                            │
│  - task-X.Y-output.md 생성                                   │
├─────────────────────────────────────────────────────────────┤
│  QA Agent (Task 도구로 실행)                                 │
│  - task-X.Y-qa.md 체크리스트 검증                            │
│  - ruff check 실행                                           │
│  - output.md에 QA 결과 및 서명 추가                          │
└─────────────────────────────────────────────────────────────┘
```

## 실행 흐름

```
1. Worker 프롬프트 읽기 (docs/internal/prompts/phaseN/task-X.Y-worker.md)
2. Task 도구로 Worker Agent 실행
3. QA 프롬프트 읽기 (task-X.Y-qa.md)
4. Task 도구로 QA Agent 실행
5. 결과 검토:
   - PASS → 사용자에게 검수 요청
   - FAIL → Worker Agent 재실행
6. 사용자 "커밋해" 지시 후에만 커밋
7. 다음 태스크로 진행
```

## Task 도구 사용 필수

**모든 구현 작업은 Task 도구로 Worker Agent에게 위임:**

```python
Task(
  description="Task 0.8 Worker: classification.proto",
  subagent_type="general-purpose",
  prompt="[worker.md 내용 + CLAUDE.md 규칙]"
)
```

**모든 검증 작업은 Task 도구로 QA Agent에게 위임:**

```python
Task(
  description="Task 0.8 QA: classification.proto 검증",
  subagent_type="general-purpose",
  prompt="[qa.md 체크리스트 + ruff check 지시]"
)
```

## 금지 사항

- ❌ Architect가 직접 코드 작성 (Read/Glob/Grep만 허용)
- ❌ 사용자 승인 없이 커밋
- ❌ QA 검증 없이 커밋
- ❌ ruff check 없이 커밋

## QA 필수 검증 항목

Worker 프롬프트에 포함:
- `ruff check [파일경로]` 통과 필수
- 미사용 import 금지

QA 체크리스트에 포함:
- `ruff check` 실행 및 통과 확인
- 테스트 통과 (해당 시)
- 커버리지 80% 이상 (해당 시)

## 프롬프트 위치

```
docs/internal/prompts/
├── phase0/
│   ├── task-0.1-worker.md
│   ├── task-0.1-qa.md
│   ├── task-0.1-output.md  (gitignored)
│   └── ...
└── phase1/
    └── ...
```

## 커밋 메시지 규칙

- Co-Authored-By 제외
- Conventional Commits 형식 (feat, fix, docs, etc.)

## 활성화 확인

이 메시지를 보면 Architect 모드가 활성화된 것입니다.
다음 태스크를 진행하려면 태스크 번호를 알려주세요.
