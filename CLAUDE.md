# CLAUDE.md — muto_agent

## 아키텍처
- Streamlit 프론트(`app.py`) ↔ FastAPI 백엔드(`agent_server.py`) ↔ OpenAI 호환 LiteLLM Proxy(Claude 모델). 프론트는 httpx로 백엔드 `/chat`(SSE), 백엔드는 openai SDK로 Proxy 호출.
- SSE 계약: `data: {"delta":...}` / `data: [DONE]` / `data: {"error":...}`.
- 대화 히스토리는 프론트(`st.session_state.messages`)가 보유하고 매 요청 전체 전송 → 백엔드 무상태.

## 실행 (uv, 설치 불필요)
- `uv run app.py`(프론트) / `uv run agent_server.py`(백엔드) / `./run.sh`(동시). uv가 pyproject 의존성을 자동 준비.
- 포트/호스트: `.env`의 `AGENT_HOST`/`AGENT_PORT`/`STREAMLIT_PORT`, 환경변수 오버라이드 우선 (예: `AGENT_PORT=9000 ./run.sh`).

## 검증 (lint/test 대체 — 매번 반복하는 명령)
> 별도 lint 도구(ruff 등)·테스트 러너(pytest)는 없다. 자동 테스트는 프로젝트 규칙상 작성하지 않으며(실제 데이터 기반 금지), 아래 실행 관찰로 검증한다.
- 구문 검증: `uv run python -c "import ast; ast.parse(open('app.py').read()); print('syntax ok')"` (파일명만 교체)
- 의존성 import 확인: `uv run python -c "import streamlit, openai, httpx, fastapi, mcp; print('deps ok')"`
- 프론트 기동 확인(headless): `STREAMLIT_PORT=8612 timeout 40 uv run app.py > /tmp/f.log 2>&1 || true; grep -E "You can now view|Traceback" /tmp/f.log` (종료 시점 트레이스백은 무시 — 기동 성공이면 통과)
- 백엔드 기동+헬스: `AGENT_PORT=8600 uv run agent_server.py > /tmp/a.log 2>&1 & sleep 12; curl -s http://127.0.0.1:8600/; kill %1` (헬스 `{"status":"ok","mcp_tools":N}`, MCP 연결 로그 확인)

## Gotchas
- `.env`/`.env.example` 편집은 보안 훅(block-sensitive.py)이 차단 — 도구로 못 만듦. 사용자가 `!` 명령으로 직접 생성/수정.
- Streamlit 부트스트랩: `app.py`가 `runtime.exists()`로 판별해 `streamlit run`으로 자기 재실행. `.streamlit/config.toml`에 `headless=true`, `runOnSave=true`.
- 멀티페이지는 `st.navigation`+`st.Page`(app.py 내 함수, `pages/` 디렉토리 아님).
- 웹검색은 `web_search_options={}` (Anthropic tool 버전 문자열 하드코딩 금지 — LiteLLM이 모델에 맞게 변환).
- Notion MCP: `agent_server.py` lifespan에서 `npx @notionhq/notion-mcp-server` stdio 연결, `env=os.environ.copy()`로 토큰 전달(변수명 비의존). node 필요.
- 설계/계획 문서: `docs/superpowers/specs/`, `docs/superpowers/plans/`. 이 프로젝트는 git 저장소가 아님(커밋 없음).
