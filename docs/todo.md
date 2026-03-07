# TODO

## Deferred Items

### 1. Registration Endpoint
- `POST /v1/auth/register` — 현재 토큰 발급만 구현됨, 회원가입 플로우 추가 필요
- 이메일 검증, 비밀번호 해싱, 중복 체크 등

### 2. Prometheus Metrics / Observability
- `/metrics` 엔드포인트 추가 (prometheus-fastapi-instrumentator)
- 요청 지연시간, 에러율, LLM 호출 횟수/비용 추적
- Grafana 대시보드 구성
