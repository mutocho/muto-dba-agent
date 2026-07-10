# muto_agent 3-서비스 분리 리팩터링 설계

**날짜**: 2026-07-10
**브랜치**: `refactor/split-apps`

## 목표

단일 저장소에 뒤섞인 프론트/백엔드/MCP 연결 코드를 3개의 독립 실행 서비스로 분리하고,
운영 편의를 위한 저장소 정리를 함께 수행한다.

1. `docs/`를 git 버전 관리에서 제거(파일은 로컬 유지).
2. `*.sh` 스크립트를 `scripts/` 폴더로 이동해 관리.
3. 앱을 각각 독립 폴더 + 개별 `uv` 프로젝트로 분리.
4. 앱을 UI(Streamlit) / Agent / MCP Router 3개의 독립 HTTP 서비스로 나눈다.

## 최종 디렉토리 구조

```
muto_agent/
├─ ui/                      # ① UI (Streamlit)
│  ├─ pyproject.toml + uv.lock
│  ├─ app.py                # 현재 app.py 이동 (self re-exec 패턴 유지)
│  └─ .streamlit/config.toml
├─ agent/                   # ② Agent (LLM 오케스트레이션)
│  ├─ pyproject.toml + uv.lock
│  └─ main.py               # 현재 agent_server.py에서 MCP 직접연결 제거
├─ mcp-router/              # ③ MCP Router (신규)
│  ├─ pyproject.toml + uv.lock
│  └─ main.py               # Notion MCP stdio 연결 + /tools /call API
├─ scripts/                 # run.sh, run_app.sh, run_agent.sh, run_router.sh
├─ docs/                    # git 비추적 (파일은 디스크에 유지)
├─ .env / .env.example      # 루트 단일 공유
├─ .gitignore               # docs/ 추가
├─ README.md / CLAUDE.md    # 갱신
└─ (루트 pyproject.toml / uv.lock / .venv 제거)
```

## 아키텍처 / 데이터 흐름

```
UI(streamlit) ──http SSE──▶ Agent ──http──▶ MCP Router ──stdio──▶ Notion MCP
   :STREAMLIT_PORT            :AGENT_PORT       :MCP_ROUTER_PORT
```

- **UI**: 현재 `/chat` SSE 소비 로직 그대로 유지. 대화 히스토리를 `st.session_state`가 보유하고 매 요청 전체 전송(백엔드 무상태)하는 계약 유지. Agent URL은 `.env`의 `AGENT_HOST/PORT`로 구성.
- **Agent**: `/chat` SSE 계약(`data: {"delta":...}` / `data: [DONE]` / `data: {"error":...}`) **그대로 유지**. LLM tool 루프 유지하되, MCP를 직접 붙지 않고 MCP Router를 HTTP로 호출. Router URL은 `.env`의 `MCP_ROUTER_HOST/PORT`로 구성.
- **MCP Router (신규)**: Notion MCP stdio 연결을 FastAPI lifespan에서 관리(현재 `agent_server.py`의 lifespan 코드 이관). 아래 HTTP API 노출.

## MCP Router HTTP 계약 (신규)

| 메서드 | 경로 | 응답 |
|---|---|---|
| GET | `/` | `{"status":"ok","mcp_tools":N}` (헬스) |
| GET | `/tools` | `[{"name","description","inputSchema"}, ...]` (MCP 도구 원형) |
| POST | `/call` | 요청 `{"name","arguments":{...}}` → 응답 `{"content":"..."}` (텍스트 블록 병합) |

- Agent는 `/chat` 요청 처리 시 `/tools`를 가져와 OpenAI tool 포맷으로 변환한다. 결과는 모듈 레벨에 캐시하여 최초 1회만 조회한다.
- Router 미기동/조회 실패 시 **도구 없이 진행**(현재의 graceful degradation 유지). 즉 Router가 죽어 있어도 Agent는 순수 챗 응답을 계속한다.
- Agent의 기존 `_call_mcp_tool`은 Router `/call` POST 호출로 대체한다. 호출 실패 시 tool 결과를 `"tool error: ..."` 문자열로 채워 루프를 계속하는 현재 동작을 유지한다.

## 설정 (루트 `.env` 단일 공유)

각 앱은 CWD가 자기 폴더이므로 루트 `.env`를 경로 지정으로 로드한다:
`load_dotenv(Path(__file__).resolve().parents[1] / ".env")`.

모든 포트·호스트·URL 구성 요소를 `.env`로 설정 가능하게 하고, 코드에는 최소한의 폴백 기본값만 둔다.

```
STREAMLIT_PORT=8501
AGENT_HOST=127.0.0.1
AGENT_PORT=8000
MCP_ROUTER_HOST=127.0.0.1
MCP_ROUTER_PORT=8010
OPENAI_BASE_URL=...
OPENAI_API_KEY=...
MODEL_NAME=...
NOTION_TOKEN=...   # (기존 Notion MCP용 변수 유지)
```

`.env`/`.env.example` 편집은 보안 훅(block-sensitive.py)이 차단하므로, 신규 변수(`MCP_ROUTER_HOST/PORT`)는 **사용자가 `!` 명령으로 직접 추가**한다. 구현 단계에서 안내한다.

## 앱별 의존성 (개별 pyproject.toml)

- **ui/**: `streamlit`, `python-dotenv`, `httpx`, `watchdog`
- **agent/**: `fastapi`, `uvicorn`, `openai`, `python-dotenv`, `httpx`
- **mcp-router/**: `fastapi`, `uvicorn`, `mcp`, `python-dotenv`

각 폴더에서 `uv lock`으로 개별 `uv.lock` 생성. 루트의 통합 `pyproject.toml`/`uv.lock`/`.venv`는 제거한다.

## scripts/

- `run.sh`: mcp-router → agent → ui 순서로 3개 기동. 각 앱은 `(cd <app> && uv run main.py)` (ui는 `app.py`). `trap`으로 종료 시 백그라운드 프로세스 일괄 kill.
- `run_router.sh` (신규) / `run_agent.sh` / `run_app.sh`: 각 앱 개별 기동.
- 스크립트는 저장소 루트를 기준으로 각 앱 폴더로 이동해 실행한다.

## 저장소 정리

- **docs 비추적**: `git rm -r --cached docs`로 추적만 해제(파일은 디스크 유지) + `.gitignore`에 `docs/` 추가.
- **루트 잔여물 제거**: 앱 분리 후 루트 `pyproject.toml`, `uv.lock`, `.venv/` 제거.
- **문서 갱신**: `CLAUDE.md`의 아키텍처/실행/검증/Gotchas 섹션을 3-서비스 구조로 갱신하고, "이 프로젝트는 git 저장소가 아님" 오류 문구를 바로잡는다. `README.md`도 새 실행 방법으로 갱신.

## 검증

별도 lint/test 러너 없음. 실행 관찰로 검증한다(자동 테스트는 프로젝트 규칙상 작성하지 않음).

| 요청 | 검증 방법 |
|---|---|
| docs 비추적 | `git ls-files docs/` 결과가 비어 있음 |
| sh → scripts/ | `ls scripts/*.sh`, 각 스크립트 기동 확인 |
| 앱별 uv 분리 | 각 폴더에서 `uv run python -c "import <deps>"` 성공 |
| 구문 검증 | 각 `main.py`/`app.py`에 대해 `ast.parse` |
| MCP Router | 기동 후 `GET /` 헬스 `{"status":"ok","mcp_tools":N}`, `GET /tools` 도구 목록 |
| Agent | Router 기동 상태에서 `GET /` 헬스, `/chat` SSE 한 턴 왕복 |
| UI | headless 기동 로그에 `You can now view` 확인 |
| 전체 | `scripts/run.sh`로 3개 동시 기동 후 `/chat` 한 턴 왕복 |

## 범위 밖 (YAGNI)

- MCP 서버 다중 등록/동적 라우팅: 현재 Notion 하나만 유지. Router 구조는 추후 추가 가능하도록 두되 지금은 단일 서버.
- 인증/인가, 서비스 디스커버리, 컨테이너화 등은 다루지 않는다.
- UI의 `page_two`/`page_three` 플레이스홀더는 그대로 이동만 한다.
