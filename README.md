# muto_agent

OpenAI 호환 LiteLLM Proxy(Claude 모델)에 붙는 3-서비스 챗봇.

## 구조

- `ui/` — Streamlit 프론트엔드
- `agent/` — LLM 오케스트레이션 백엔드(FastAPI, `/chat` SSE)
- `mcp-router/` — MCP(Notion) 연결·도구 라우팅(FastAPI, `/tools` `/call`)
- `scripts/` — 기동 스크립트
- 루트 `.env` — 세 서비스가 공유하는 설정

```
UI ─http SSE→ Agent ─http→ MCP Router ─stdio→ Notion MCP
```

## 실행 (uv, 설치 불필요)

- 전체 동시 기동: `scripts/run.sh`
- 개별 기동: `scripts/run_router.sh` / `scripts/run_agent.sh` / `scripts/run_app.sh`

각 앱은 자체 `pyproject.toml`을 가진 독립 uv 프로젝트다.

## 설정 (.env)

루트 `.env`에 다음을 둔다(포트/호스트는 모두 오버라이드 가능):

```
STREAMLIT_PORT=8501
AGENT_HOST=127.0.0.1
AGENT_PORT=8000
MCP_ROUTER_HOST=127.0.0.1
MCP_ROUTER_PORT=8010
OPENAI_BASE_URL=...
OPENAI_API_KEY=...
MODEL_NAME=...
```

MCP Router는 `npx @notionhq/notion-mcp-server`를 stdio로 띄우므로 node가 필요하다.
