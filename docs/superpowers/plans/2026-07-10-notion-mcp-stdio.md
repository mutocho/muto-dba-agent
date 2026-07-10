# Notion MCP (stdio) 통합 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** agent 백엔드에 Notion MCP 서버를 stdio로 연결해, LLM이 tool calling으로 Notion 도구를 사용하게 한다.

**Architecture:** `agent_server.py`를 async로 전환하고, FastAPI lifespan에서 `npx -y @notionhq/notion-mcp-server`를 stdio로 1회 연결해 도구 목록을 캐시한다. `/chat`은 비스트리밍 tool 루프(LLM→tool_use→MCP 실행→반복)를 돌린 뒤, 최종 텍스트를 단어 단위 SSE로 흘린다(fake-stream). 프론트(`app.py`)는 SSE 계약이 그대로라 변경 없다.

**Tech Stack:** FastAPI + uvicorn, AsyncOpenAI, mcp(Python MCP SDK, stdio), Notion MCP 서버(npx/node)

## Global Constraints

- 변경 대상은 `agent_server.py`와 `pyproject.toml`뿐. 프론트/스크립트/멀티페이지/포트 변수는 변경 없음.
- MCP 서버가 노출하는 **모든 도구**를 LLM에 제공(필터·승인 게이트 없음).
- MCP 연결은 lifespan에서 1회, `AsyncExitStack`으로 수명 유지. **연결 실패 시 graceful** — 도구 없이 웹검색+일반 챗은 동작하고 백엔드는 크래시하지 않는다.
- MCP 서버에 `env=os.environ.copy()`를 전달한다 → 토큰 변수명(`NOTION_TOKEN`/`OPENAPI_MCP_HEADERS` 등)에 코드가 의존하지 않는다. 사용자는 `.env`에 서버가 요구하는 변수를 넣는다.
- SSE 계약 유지: `data: {"delta": ...}\n\n` / `data: [DONE]\n\n` / `data: {"error": ...}\n\n`.
- 웹검색(`web_search_options={}`)은 tool 루프 안에서 유지.
- tool 루프 무한 방지: 최대 8회 반복.
- 이 프로젝트는 git 저장소가 아니다. 커밋하지 않으며, 각 태스크는 실행 검증으로 마무리한다.
- 실제 데이터 기반 자동 테스트는 작성하지 않는다. 검증은 실제 실행 관찰로 한다.
- `.env` 파일은 보안 훅이 도구 편집을 차단한다. 토큰 설정은 사용자가 직접 반영한다.
- 프로젝트 루트: `/Users/kakaogames/workspace/branch/muto_agent`

---

### Task 1: mcp 의존성 추가 + 환경 요건 확인

**Files:**
- Modify: `/Users/kakaogames/workspace/branch/muto_agent/pyproject.toml`

**Interfaces:**
- Consumes: 기존 pyproject dependencies.
- Produces: `mcp` 패키지 사용 가능. Task 2가 `from mcp import ...`를 쓴다.

- [ ] **Step 1: `pyproject.toml` dependencies에 `mcp` 추가**

기존 배열을 찾는다:
```toml
dependencies = [
    "streamlit",
    "openai",
    "python-dotenv",
    "watchdog",
    "fastapi",
    "uvicorn",
    "httpx",
]
```
다음으로 교체한다 (`mcp` 추가):
```toml
dependencies = [
    "streamlit",
    "openai",
    "python-dotenv",
    "watchdog",
    "fastapi",
    "uvicorn",
    "httpx",
    "mcp",
]
```

- [ ] **Step 2: node/npx 존재 확인 + mcp import 검증**

Run:
```bash
cd /Users/kakaogames/workspace/branch/muto_agent
node -v && npx -v
uv run python -c "import mcp; from mcp.client.stdio import stdio_client; print('mcp ok')"
```
Expected: node/npx 버전이 출력되고(설치돼 있어야 함), `mcp ok`가 출력된다. node가 없으면 이 사실을 보고하고 사용자에게 node 설치가 필요함을 알린다(구현은 계속 진행 가능하나 실제 MCP 연결은 node 필요).

---

### Task 2: agent_server.py를 async + MCP tool 루프로 개편

**Files:**
- Modify: `/Users/kakaogames/workspace/branch/muto_agent/agent_server.py` (전체 교체)

**Interfaces:**
- Consumes: `.env`의 `OPENAI_BASE_URL`/`OPENAI_API_KEY`/`MODEL_NAME`/`AGENT_HOST`/`AGENT_PORT`, Notion 토큰 변수(os.environ 경유), Task 1의 `mcp` 패키지.
- Produces: `POST /chat`(SSE, tool 루프), `GET /`(헬스 `{"status":"ok","mcp_tools":N}`). 프론트가 소비하는 SSE 형식은 기존과 동일.

- [ ] **Step 1: `agent_server.py` 전체를 아래 내용으로 교체**

```python
import json
import os
from contextlib import AsyncExitStack, asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from openai import AsyncOpenAI
from pydantic import BaseModel

load_dotenv()

MODEL_NAME = os.getenv("MODEL_NAME")
MAX_TOOL_ITERATIONS = 8

client = AsyncOpenAI(
    base_url=os.getenv("OPENAI_BASE_URL"),
    api_key=os.getenv("OPENAI_API_KEY"),
)

# MCP 상태 (lifespan에서 채운다)
mcp_state = {"session": None, "tools": []}


def _to_openai_tools(mcp_tools):
    return [
        {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description or "",
                "parameters": tool.inputSchema,
            },
        }
        for tool in mcp_tools
    ]


@asynccontextmanager
async def lifespan(app: FastAPI):
    stack = AsyncExitStack()
    try:
        server_params = StdioServerParameters(
            command="npx",
            args=["-y", "@notionhq/notion-mcp-server"],
            env=os.environ.copy(),
        )
        read, write = await stack.enter_async_context(stdio_client(server_params))
        session = await stack.enter_async_context(ClientSession(read, write))
        await session.initialize()
        tools_result = await session.list_tools()
        mcp_state["session"] = session
        mcp_state["tools"] = tools_result.tools
        print(f"MCP 연결됨: 도구 {len(tools_result.tools)}개 로드")
    except Exception as error:
        print(f"MCP 연결 실패(도구 없이 계속): {error!r}")
    try:
        yield
    finally:
        await stack.aclose()


app = FastAPI(lifespan=lifespan)


class ChatRequest(BaseModel):
    messages: list[dict]


@app.get("/")
def health():
    return {"status": "ok", "mcp_tools": len(mcp_state["tools"])}


async def _call_mcp_tool(name, arguments):
    session = mcp_state["session"]
    result = await session.call_tool(name, arguments)
    return "".join(getattr(block, "text", "") for block in result.content)


@app.post("/chat")
async def chat(request: ChatRequest):
    tools = _to_openai_tools(mcp_state["tools"]) if mcp_state["tools"] else None

    async def event_stream():
        try:
            messages = list(request.messages)
            final_text = ""
            for _ in range(MAX_TOOL_ITERATIONS):
                kwargs = {
                    "model": MODEL_NAME,
                    "messages": messages,
                    "web_search_options": {},
                    "stream": False,
                }
                if tools:
                    kwargs["tools"] = tools
                resp = await client.chat.completions.create(**kwargs)
                message = resp.choices[0].message
                if message.tool_calls:
                    messages.append(
                        {
                            "role": "assistant",
                            "content": message.content or "",
                            "tool_calls": [
                                {
                                    "id": tc.id,
                                    "type": "function",
                                    "function": {
                                        "name": tc.function.name,
                                        "arguments": tc.function.arguments,
                                    },
                                }
                                for tc in message.tool_calls
                            ],
                        }
                    )
                    for tc in message.tool_calls:
                        try:
                            arguments = json.loads(tc.function.arguments or "{}")
                            content = await _call_mcp_tool(tc.function.name, arguments)
                        except Exception as tool_error:
                            content = f"tool error: {tool_error}"
                        messages.append(
                            {
                                "role": "tool",
                                "tool_call_id": tc.id,
                                "content": content,
                            }
                        )
                    continue
                final_text = message.content or ""
                break

            for piece in final_text.split(" "):
                yield f"data: {json.dumps({'delta': piece + ' '})}\n\n"
            yield "data: [DONE]\n\n"
        except Exception as error:
            yield f"data: {json.dumps({'error': str(error)})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


if __name__ == "__main__":
    import uvicorn

    host = os.getenv("AGENT_HOST", "127.0.0.1")
    port = int(os.getenv("AGENT_PORT", "8000"))
    uvicorn.run(app, host=host, port=port)
```

- [ ] **Step 2: 구문 검증**

Run:
```bash
cd /Users/kakaogames/workspace/branch/muto_agent
uv run python -c "import ast; ast.parse(open('agent_server.py').read()); print('syntax ok')"
```
Expected: `syntax ok`.

- [ ] **Step 3: 기동 + 헬스 체크 (graceful 확인)**

Run:
```bash
cd /Users/kakaogames/workspace/branch/muto_agent
AGENT_PORT=8600 uv run agent_server.py > /tmp/mcp_boot.log 2>&1 &
sleep 12
curl -s http://127.0.0.1:8600/ ; echo
kill %1 2>/dev/null; wait 2>/dev/null
cat /tmp/mcp_boot.log
```
Expected: `{"status":"ok","mcp_tools":N}` 가 출력된다(N은 토큰/노드 환경에 따라 0 이상). 로그에 `MCP 연결됨: 도구 N개 로드`(성공) 또는 `MCP 연결 실패(도구 없이 계속): ...`(graceful) 중 하나가 보이고, **어느 쪽이든 서버는 기동해 헬스가 응답한다**(크래시 없음). 로그를 보고서에 기록한다. (MCP 서버가 npx 첫 실행이라 다운로드로 sleep이 부족하면 `mcp_tools:0`일 수 있음 — 그래도 크래시 없이 헬스가 응답하면 graceful 통과.)

---

### Task 3: 최종 수동 검증 (사용자)

**Files:** (없음 — 실행 검증만)

**Interfaces:**
- Consumes: Task 1~2 산출물, 실제 Proxy 값 + Notion 토큰이 담긴 `.env`, 시스템 node.
- Produces: 성공 기준 충족 확인.

> 실제 Proxy·Notion 토큰·브라우저가 필요해 자동화할 수 없다. 사용자가 실행한다.

- [ ] **Step 1: `.env`에 Notion 토큰 설정 (사용자 직접)**

보안 훅이 도구 편집을 막으므로 사용자가 직접 `.env`에 Notion MCP 서버가 요구하는
변수를 추가한다. 서버 버전에 따라 둘 중 하나(서버 문서 확인):
```
# 최신 버전
NOTION_TOKEN=ntn_...
# 또는 구버전
OPENAPI_MCP_HEADERS={"Authorization":"Bearer ntn_...","Notion-Version":"2022-06-28"}
```

- [ ] **Step 2: 실행**

Run:
```bash
cd /Users/kakaogames/workspace/branch/muto_agent
./run.sh
```
백엔드 로그에 `MCP 연결됨: 도구 N개 로드`(N>0)가 보이는지 확인하고, 프론트 URL로 접속한다.

- [ ] **Step 3: 동작 확인 (성공 기준)**

브라우저에서 확인:
1. "내 Notion에서 (아는 페이지/키워드) 검색해줘" → 도구 사용 후 답변이 스트리밍됨.
2. 최신 정보 질문 → 웹검색 동작(회귀 없음). 후속 질문 → 멀티턴 유지.
3. 사이드바 멀티페이지 정상(회귀 없음).
4. (graceful) `.env`에서 Notion 토큰을 지우고 재기동 → 백엔드는 `mcp_tools:0`으로
   뜨고, 일반 챗·웹검색은 여전히 동작(크래시 없음).

모든 항목 통과 시 완료.

---

## Self-Review

**Spec coverage:**
- Notion MCP stdio 연결 → Task 2 Step 1 (lifespan `stdio_client` + npx) ✅
- 모든 도구 노출, 게이트 없음 → Task 2 (`_to_openai_tools`로 전체 변환, 필터 없음) ✅
- lifespan 1회 연결 + 캐시 + AsyncExitStack → Task 2 Step 1 ✅
- graceful degradation → Task 2 Step 1 (try/except로 실패 시 도구 없이), Step 3 검증, Task 3 Step 3 항목 4 ✅
- 토큰 변수명 비의존(os.environ.copy) → Task 2 Step 1, Global Constraints ✅
- async 전환(AsyncOpenAI + async 엔드포인트) → Task 2 Step 1 ✅
- tool 루프 non-stream + 최종 fake-stream + web_search 유지 + 8회 제한 → Task 2 Step 1 ✅
- SSE 계약 유지(프론트 무변경) → Task 2 Step 1 (delta/[DONE]/error 동일) ✅
- mcp 의존성 + node 요건 → Task 1 ✅
- 검증(헬스/graceful/대화/회귀) → Task 1 Step 2, Task 2 Step 3, Task 3 Step 3 ✅

**Placeholder scan:** "TBD/TODO" 없음. 코드 스텝에 완전한 파일 내용 포함. `.env`의 토큰 예시는 사용자가 채우는 설정값(서버 문서로 확정)이며 의도된 것. 명령마다 기대 출력 명시.

**Type consistency:** SSE 키(`delta`/`error`, `[DONE]`)가 백엔드 생성부와 프론트(기존 `app.py`) 파서에서 일치. `mcp_state` 딕셔너리 키(`session`/`tools`)가 lifespan·health·`_call_mcp_tool`·chat에서 일관. openai 메시지 스키마(`role`/`content`/`tool_calls`/`tool_call_id`)가 루프 전 구간 일관. `ChatRequest.messages` ↔ 프론트 `{"messages": ...}` 일치.
