# 설계: Notion MCP (stdio) 통합

- 날짜: 2026-07-09
- 상태: 승인됨
- 선행: [2026-07-08-streamlit-agent-split-design.md](2026-07-08-streamlit-agent-split-design.md)

## 목표

agent 백엔드(`agent_server.py`)에 **Notion MCP 서버를 stdio로 연결**해, LLM이
Notion 도구(검색/조회/생성/수정 등 서버가 노출하는 전부)를 tool calling으로
사용하게 한다. 챗봇이 Notion 데이터를 반영해 답하거나 Notion을 조작할 수 있다.

## 대상 범위

**`agent_server.py`만 변경**한다. 프론트(`app.py`)는 그대로 둔다 — SSE 계약
(`data: {"delta"}` / `[DONE]` / `{"error"}`)이 유지되므로 프론트 변경이 없다.

## 도구 범위

MCP 서버가 노출하는 **모든 도구**를 LLM에 제공한다. 별도 필터·승인 게이트는
두지 않는다(쓰기 도구 포함 시 LLM이 승인 없이 Notion을 수정할 수 있음 — 의도된 선택).

## MCP 연결 (stdio, 수명 관리)

- FastAPI **lifespan**에서 서버 startup 시 `npx -y @notionhq/notion-mcp-server`를
  stdio로 **한 번 연결**하고, 도구 목록을 캐시해 앱 수명 동안 재사용한다(요청마다
  npx 부팅 지연 회피). 연결/세션은 `AsyncExitStack`으로 lifespan 동안 유지하고
  shutdown에서 정리한다.
- MCP 연결 실패(토큰 없음/node 없음/서버 오류) 시 **graceful degradation**:
  도구 없이도 챗(웹검색 + 일반 대화)은 정상 동작한다.
- 인증: `.env`의 Notion 통합 토큰을 MCP 서버 프로세스 환경변수로 전달한다.
  정확한 변수명(버전에 따라 `NOTION_TOKEN` 또는 `OPENAPI_MCP_HEADERS` JSON 등)은
  구현 단계에서 서버 문서로 확정한다.

## async 전환

MCP Python SDK(`mcp`)가 async 기반이므로 백엔드를 async로 바꾼다:
`AsyncOpenAI` + `async def` 엔드포인트 + async 제너레이터 SSE.

## tool 루프 (non-stream) + 최종 답변 스트리밍

```
messages = 요청 히스토리 복사본
while True:
    resp = await client.chat.completions.create(
        model=MODEL_NAME, messages=messages,
        tools=<MCP 도구(openai function 형식)>,   # 도구 없으면 생략
        web_search_options={}, stream=False,
    )
    choice = resp.choices[0].message
    if choice.tool_calls:
        messages.append(assistant(tool_calls))
        for tc in choice.tool_calls:
            result = await session.call_tool(tc.function.name, json.loads(tc.function.arguments))
            messages.append({"role": "tool", "tool_call_id": tc.id, "content": <결과 텍스트>})
        continue
    final_text = choice.content or ""
    break
# 최종 텍스트를 단어 단위로 SSE delta로 흘림(fake-stream) → 프론트 계약 그대로
```

- MCP 도구(`name`/`description`/`inputSchema`)를 openai function 형식
  (`{"type": "function", "function": {name, description, parameters}}`)으로 변환해
  `tools`로 전달한다.
- `tool_use` 응답 시 `session.call_tool(name, args)`를 실행하고 결과를 `role: "tool"`
  메시지로 회신한다.
- 웹검색(`web_search_options={}`)과 MCP function 도구를 함께 요청에 포함한다.
- 최종(도구 호출 없는) 텍스트는 백엔드가 단어 단위로 잘라 SSE `delta`로 흘린다.
  추가 LLM 호출 없이 fake-stream이며, 프론트 SSE 계약을 그대로 만족한다.
- 루프 무한 방지: 최대 반복 횟수(예: 8회)를 두고 초과 시 마지막 텍스트로 종료한다.

## 설정 / 의존성

- `.env` / `.env.example`: Notion 토큰 변수 추가.
- `pyproject.toml`: `mcp` 패키지 추가.
- 시스템 요건: `node`/`npx` 설치 필요(구현·검증 단계에서 존재 확인).

## 유지되는 것 (회귀 방지)

- 프론트(`app.py`)·스크립트·`.streamlit/config.toml`·멀티페이지·포트 변수는 변경 없음.
- 기존 웹검색·멀티턴 동작은 tool 루프 안에서 그대로 유지된다.
- 백엔드 에러 처리: 예외 시 `data: {"error": ...}` SSE로 전달(기존 계약 유지).

## 범위 밖 (YAGNI)

- tool 실행 중 상태 표시 UI, 승인 게이트, 완전 토큰 스트리밍(중간 tool 상태 실시간 전송).
- 여러 MCP 서버 동시 연결, 도구 allowlist, HTTP transport MCP.

## 검증 (성공 기준)

CLAUDE.md 규칙상 실제 데이터 기반 자동 테스트는 작성하지 않으며, 수동 실행으로
확인한다.

1. `node -v`로 node 존재 확인.
2. 백엔드 기동(`./run_agent.sh`) 시 MCP 연결 + 도구 목록 로드 로그가 보인다.
3. Notion 관련 질문("내 Notion에서 X 검색해줘") → 도구 사용 후 답변이 스트리밍됨.
4. MCP 연결 실패(토큰 없음 또는 node 없음) 시에도 일반 챗·웹검색은 정상(graceful),
   백엔드가 크래시하지 않는다.
5. 기존 멀티턴·웹검색·멀티페이지 회귀 없음.
