# CLAUDE.md — muto_agent

## 아키텍처
- 3-서비스: Streamlit 프론트(`ui/app.py`) ↔ FastAPI 백엔드(`agent/main.py`) ↔ FastAPI MCP Router(`mcp-router/main.py`) ↔ OpenAI 호환 LiteLLM Proxy(Claude 모델).
- Agent는 MCP에 직접 붙지 않는다. Notion MCP stdio 연결(`npx @notionhq/notion-mcp-server`)은 `mcp-router/main.py`의 lifespan에 있고, Agent는 Router의 `GET /tools`·`POST /call`로 도구 조회/실행을 위임한다.
- SSE 계약(UI ↔ Agent): `data: {"delta":...}` / `data: [DONE]` / `data: {"error":...}`.
- 대화 히스토리는 프론트(`st.session_state.messages`)가 보유하고 매 요청 전체 전송 → Agent 무상태.
- 각 앱(`ui/`, `agent/`, `mcp-router/`)은 자체 `pyproject.toml`/`uv.lock`을 가진 독립 uv 프로젝트다. 루트 `pyproject.toml`/`uv.lock`/`.venv`는 없다. 루트 `.env` 하나를 세 앱이 `load_dotenv(Path(__file__).resolve().parents[1] / ".env")`로 공유한다.

## 실행 (uv, 설치 불필요)
- 전체 동시 기동: `scripts/run.sh` / 개별 기동: `scripts/run_router.sh`·`scripts/run_agent.sh`·`scripts/run_app.sh`.
- 각 앱 폴더에서 직접: `cd mcp-router && uv run main.py` / `cd agent && uv run main.py` / `cd ui && uv run app.py`. uv가 각 앱의 pyproject 의존성을 자동 준비.
- 포트/호스트: 루트 `.env`의 `STREAMLIT_PORT`/`AGENT_HOST`/`AGENT_PORT`/`MCP_ROUTER_HOST`/`MCP_ROUTER_PORT`, 환경변수 오버라이드 우선.

## 검증 (lint/test 대체 — 매번 반복하는 명령)
> 별도 lint 도구(ruff 등)·테스트 러너(pytest)는 없다. 자동 테스트는 프로젝트 규칙상 작성하지 않으며(실제 데이터 기반 금지), 아래 실행 관찰로 검증한다. 각 명령은 해당 앱 폴더(`ui/`, `agent/`, `mcp-router/`) 기준으로 실행한다.
- 구문 검증: `uv run python -c "import ast; ast.parse(open('main.py').read()); print('syntax ok')"` (파일명은 `app.py`/`main.py`로 교체)
- 의존성 import 확인: 앱별로 필요한 패키지만 (예: `mcp-router`는 `uv run python -c "import fastapi, mcp; print('deps ok')"`, `agent`는 `import fastapi, openai, httpx`, `ui`는 `import streamlit, httpx`)
- UI 기동 확인(headless): `cd ui && STREAMLIT_PORT=8612 timeout 40 uv run app.py > /tmp/f.log 2>&1 || true; grep -E "You can now view|Traceback" /tmp/f.log` (종료 시점 트레이스백은 무시 — 기동 성공이면 통과)
- MCP Router 기동+헬스: `cd mcp-router && MCP_ROUTER_PORT=8610 uv run main.py > /tmp/r.log 2>&1 & sleep 12; curl -s http://127.0.0.1:8610/; kill %1` (헬스 `{"status":"ok","mcp_tools":N}`, MCP 연결 로그 확인)
- Agent 기동+헬스: `cd agent && AGENT_PORT=8600 uv run main.py > /tmp/a.log 2>&1 & sleep 5; curl -s http://127.0.0.1:8600/; kill %1` (헬스 `{"status":"ok"}`) — Router가 먼저 떠 있어야 도구 목록을 정상 조회한다.

## Gotchas
- `.env`/`.env.example` 편집은 보안 훅(block-sensitive.py)이 차단 — 도구로 못 만듦. 사용자가 `!` 명령으로 직접 생성/수정.
- Streamlit 부트스트랩: `ui/app.py`가 `runtime.exists()`로 판별해 `streamlit run`으로 자기 재실행. `.streamlit/config.toml`에 `headless=true`, `runOnSave=true`.
- 멀티페이지는 `st.navigation`+`st.Page`(app.py 내 함수, `pages/` 디렉토리 아님).
- 웹검색은 `web_search_options={}` (Anthropic tool 버전 문자열 하드코딩 금지 — LiteLLM이 모델에 맞게 변환).
- Notion MCP: `mcp-router/main.py`의 lifespan에서 `npx @notionhq/notion-mcp-server` stdio 연결, `env=os.environ.copy()`로 토큰 전달(변수명 비의존). node 필요. Agent는 이 연결에 직접 접근하지 않고 Router HTTP API로만 통신한다.
- 설계/계획 문서: `docs/superpowers/specs/`, `docs/superpowers/plans/`. 이 프로젝트는 git 저장소이며(origin/main 존재) `docs/`는 `.gitignore`로 비추적 처리되어 있다(파일은 디스크에 유지, git 이력에는 없음).
