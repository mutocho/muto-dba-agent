# Streamlit ↔ Agent 백엔드 분리 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 챗 로직을 FastAPI 백엔드(agent_server.py)로 분리하고, Streamlit은 HTTP(SSE)로 백엔드에 붙는 순수 클라이언트로 바꾼다.

**Architecture:** `agent_server.py`(FastAPI)가 `POST /chat`에서 openai SDK를 `stream=True`+`web_search_options={}`로 호출하고 토큰을 SSE(`data: {"delta": ...}`)로 흘린다. `app.py`의 `chat_page`는 LLM 직접 호출 대신 백엔드 `/chat`에 `httpx.stream`으로 붙어 SSE를 소비한다. 대화 히스토리는 Streamlit이 계속 보유하고 매 요청에 전체를 보낸다(백엔드 무상태).

**Tech Stack:** Python, FastAPI + uvicorn (백엔드), Streamlit + httpx (프론트), openai SDK, python-dotenv

## Global Constraints

- 얕은 API: 기존 챗 로직을 그대로 백엔드로 옮긴다. 새 기능 없음.
- 백엔드는 무상태. 히스토리는 프론트(`st.session_state.messages`)가 보유하고 매 요청에 전체 전송.
- SSE 형식: 토큰은 `data: {"delta": "..."}\n\n`, 종료는 `data: [DONE]\n\n`, 에러는 `data: {"error": "..."}\n\n`.
- 포트/호스트는 `AGENT_HOST`(기본 127.0.0.1) / `AGENT_PORT`(기본 8000) / `STREAMLIT_PORT`(기본 8501)로 관리. 환경변수 오버라이드가 `.env`보다 우선(python-dotenv `override=False` 기본).
- 멀티페이지 구조(`run_app`, `page_two`/`page_three`), 부트스트랩의 `streamlit run` 재실행, `.streamlit/config.toml`은 유지.
- 이 프로젝트는 git 저장소가 아니다. 커밋하지 않으며, 각 태스크는 실행 검증으로 마무리한다.
- 실제 데이터 기반 자동 테스트는 작성하지 않는다. 검증은 실제 실행 관찰로 한다.
- 프로젝트 루트: `/Users/kakaogames/workspace/branch/muto_agent`
- `.env` 파일은 사용자 환경 보안 훅이 생성/수정을 차단한다. 설정 변경은 `.env.example`에만 하고, `.env`는 사용자가 직접 반영한다.

> 설계 note: spec의 실행 예시는 `uv run uvicorn agent_server:app --port ...`(uvicorn CLI)였으나, 이 계획은 `agent_server.py`의 `__main__`에서 `uvicorn.run(...)`을 호출하는 방식으로 구현한다. 그래야 포트를 python-dotenv가 읽어 환경변수 오버라이드 우선순위를 깔끔하게 처리하고, 스크립트가 단순해진다. spec의 요구(스크립트 3종 + 포트 변경 가능)는 그대로 충족한다.

---

### Task 1: agent_server.py (FastAPI 백엔드) + 의존성

**Files:**
- Create: `/Users/kakaogames/workspace/branch/muto_agent/agent_server.py`
- Modify: `/Users/kakaogames/workspace/branch/muto_agent/pyproject.toml`

**Interfaces:**
- Consumes: `.env`의 `OPENAI_BASE_URL`/`OPENAI_API_KEY`/`MODEL_NAME`, `AGENT_HOST`/`AGENT_PORT`.
- Produces: `POST /chat` (body `{"messages": [...]}`, SSE 응답), `GET /` (헬스 `{"status": "ok"}`). 프론트(Task 2)가 이 SSE 형식을 소비한다.

- [ ] **Step 1: `pyproject.toml`에 백엔드/HTTP 의존성 추가**

기존 `dependencies` 배열을 찾는다:
```toml
dependencies = [
    "streamlit",
    "openai",
    "python-dotenv",
    "watchdog",
]
```
다음으로 교체한다 (`fastapi`, `uvicorn`, `httpx` 추가):
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

- [ ] **Step 2: `agent_server.py` 작성**

`/Users/kakaogames/workspace/branch/muto_agent/agent_server.py`를 아래 내용으로 생성한다.

```python
import json
import os

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from openai import OpenAI
from pydantic import BaseModel

load_dotenv()

MODEL_NAME = os.getenv("MODEL_NAME")

client = OpenAI(
    base_url=os.getenv("OPENAI_BASE_URL"),
    api_key=os.getenv("OPENAI_API_KEY"),
)

app = FastAPI()


class ChatRequest(BaseModel):
    messages: list[dict]


@app.get("/")
def health():
    return {"status": "ok"}


@app.post("/chat")
def chat(request: ChatRequest):
    def event_stream():
        try:
            stream = client.chat.completions.create(
                model=MODEL_NAME,
                messages=request.messages,
                stream=True,
                web_search_options={},
            )
            for chunk in stream:
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta.content
                if delta:
                    yield f"data: {json.dumps({'delta': delta})}\n\n"
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

- [ ] **Step 3: 구문/의존성 검증**

Run:
```bash
cd /Users/kakaogames/workspace/branch/muto_agent
uv run python -c "import ast; ast.parse(open('agent_server.py').read()); print('syntax ok')"
uv run python -c "import fastapi, uvicorn, httpx; print('deps ok')"
```
Expected: `syntax ok` 와 `deps ok` 출력 (uv가 pyproject의 새 의존성을 설치).

- [ ] **Step 4: 백엔드 기동 + 헬스 체크**

Run:
```bash
cd /Users/kakaogames/workspace/branch/muto_agent
AGENT_PORT=8600 uv run agent_server.py > /tmp/agent_boot.log 2>&1 &
sleep 6
curl -s http://127.0.0.1:8600/ ; echo
kill %1 2>/dev/null; wait 2>/dev/null
cat /tmp/agent_boot.log
```
Expected: `{"status":"ok"}` 가 출력된다. 로그에 `Uvicorn running on http://127.0.0.1:8600` 가 보인다. (기동 단계에서 `.env`의 `OPENAI_API_KEY` 값이 비어 있지 않아야 `OpenAI(...)` 생성이 성공한다 — `.env.example` 기본 템플릿 값이면 충분.)

---

### Task 2: app.py 프론트를 HTTP 클라이언트로 전환 + .env.example

**Files:**
- Modify: `/Users/kakaogames/workspace/branch/muto_agent/app.py` (전체 교체)
- Modify: `/Users/kakaogames/workspace/branch/muto_agent/.env.example`

**Interfaces:**
- Consumes: Task 1의 `POST /chat` SSE 엔드포인트, `AGENT_HOST`/`AGENT_PORT`, `STREAMLIT_PORT`.
- Produces: 백엔드에 붙는 Streamlit 앱 (다른 태스크가 소비하는 심볼 없음).

- [ ] **Step 1: `app.py` 전체를 아래 내용으로 교체**

`openai` 대신 `httpx`+`json`을 쓰고, `load_dotenv()`를 모듈 상단으로 올려 부트스트랩에서도 `STREAMLIT_PORT`를 읽게 한다. `chat_page`의 LLM 호출부를 백엔드 SSE 소비로 바꾼다. 나머지(멀티페이지, 부트스트랩 재실행)는 유지한다.

```python
import json
import os
import sys

import httpx
import streamlit as st
from dotenv import load_dotenv

load_dotenv()


def chat_page():
    agent_host = os.getenv("AGENT_HOST", "127.0.0.1")
    agent_port = os.getenv("AGENT_PORT", "8000")
    agent_url = f"http://{agent_host}:{agent_port}/chat"

    st.title("💬 LiteLLM Chatbot")

    # --- 대화 히스토리 초기화 ---
    if "messages" not in st.session_state:
        st.session_state.messages = []

    # --- 기존 대화 다시 그리기 (rerun 대응) ---
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    # --- 입력 처리 ---
    if prompt := st.chat_input("메시지를 입력하세요"):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            try:
                def token_stream():
                    with httpx.stream(
                        "POST",
                        agent_url,
                        json={"messages": st.session_state.messages},
                        timeout=None,
                    ) as resp:
                        resp.raise_for_status()
                        for line in resp.iter_lines():
                            if not line or not line.startswith("data: "):
                                continue
                            payload = line[len("data: "):]
                            if payload == "[DONE]":
                                break
                            data = json.loads(payload)
                            if "error" in data:
                                raise RuntimeError(data["error"])
                            delta = data.get("delta")
                            if delta:
                                yield delta

                response = st.write_stream(token_stream())
                st.session_state.messages.append(
                    {"role": "assistant", "content": response}
                )
            except Exception as error:
                st.error(f"응답 생성 중 오류가 발생했습니다: {error}")
                # 실패한 턴의 사용자 메시지를 히스토리에서 제거
                st.session_state.messages.pop()


def page_two():
    st.title("페이지 2")
    st.write("준비 중입니다.")


def page_three():
    st.title("페이지 3")
    st.write("준비 중입니다.")


def run_app():
    pages = [
        st.Page(chat_page, title="Chat", icon="💬", default=True),
        st.Page(page_two, title="페이지 2", icon="📄"),
        st.Page(page_three, title="페이지 3", icon="📄"),
    ]
    st.navigation(pages).run()


if __name__ == "__main__":
    from streamlit import runtime
    from streamlit.web import cli as stcli

    if runtime.exists():
        # streamlit 런타임 안 → 페이지 네비게이션 실행
        run_app()
    else:
        # `uv run app.py`로 직접 실행됨 → streamlit run으로 자기 재실행
        port = os.getenv("STREAMLIT_PORT", "8501")
        sys.argv = ["streamlit", "run", __file__, "--server.port", port]
        sys.exit(stcli.main())
```

- [ ] **Step 2: `.env.example`에 포트/호스트 변수 추가**

`/Users/kakaogames/workspace/branch/muto_agent/.env.example`를 아래 내용으로 교체한다.

```
OPENAI_BASE_URL=http://your-proxy-host/v1
OPENAI_API_KEY=your-proxy-api-key
MODEL_NAME=your-model-name
AGENT_HOST=127.0.0.1
AGENT_PORT=8000
STREAMLIT_PORT=8501
```

- [ ] **Step 3: 구문 검증 + openai 잔재 확인**

Run:
```bash
cd /Users/kakaogames/workspace/branch/muto_agent
uv run python -c "import ast; ast.parse(open('app.py').read()); print('syntax ok')"
grep -nE "from openai|import openai|OpenAI\(" app.py && echo "FOUND openai (문제)" || echo "no openai in frontend"
```
Expected: `syntax ok`, 그리고 `no openai in frontend` (프론트는 더 이상 openai를 쓰지 않음).

- [ ] **Step 4: 프론트 headless 기동 검증**

Run:
```bash
cd /Users/kakaogames/workspace/branch/muto_agent
STREAMLIT_PORT=8612 timeout 40 uv run app.py > /tmp/front_boot.log 2>&1 || true
grep -E "You can now view|:8612|Traceback" /tmp/front_boot.log
```
Expected: `You can now view your Streamlit app` 와 `8612` 포트가 로그에 보이고, 기동 단계 `Traceback`은 없어야 한다. (백엔드가 없어도 UI 기동 자체는 성공 — 실제 대화 시에만 백엔드 필요. timeout 종료 시점 트레이스백은 무시.)

---

### Task 3: 실행 스크립트 3종

**Files:**
- Create: `/Users/kakaogames/workspace/branch/muto_agent/run_agent.sh`
- Create: `/Users/kakaogames/workspace/branch/muto_agent/run_app.sh`
- Create: `/Users/kakaogames/workspace/branch/muto_agent/run.sh`

**Interfaces:**
- Consumes: Task 1의 `agent_server.py`, Task 2의 `app.py`, 포트 env 변수.
- Produces: 실행 스크립트 3종.

- [ ] **Step 1: `run_agent.sh` 작성 (백엔드만)**

```bash
#!/usr/bin/env bash
cd "$(dirname "$0")"
exec uv run agent_server.py
```

- [ ] **Step 2: `run_app.sh` 작성 (프론트만)**

```bash
#!/usr/bin/env bash
cd "$(dirname "$0")"
exec uv run app.py
```

- [ ] **Step 3: `run.sh` 작성 (동시 실행)**

```bash
#!/usr/bin/env bash
cd "$(dirname "$0")"
uv run agent_server.py &
AGENT_PID=$!
trap "kill $AGENT_PID 2>/dev/null" EXIT
uv run app.py
```

- [ ] **Step 4: 실행 권한 부여**

Run:
```bash
cd /Users/kakaogames/workspace/branch/muto_agent
chmod +x run_agent.sh run_app.sh run.sh
ls -l run_agent.sh run_app.sh run.sh
```
Expected: 세 파일 모두 `-rwxr-xr-x`(실행 비트 `x`)가 보인다.

- [ ] **Step 5: `run_agent.sh`로 백엔드 기동 + 포트 오버라이드 확인**

Run:
```bash
cd /Users/kakaogames/workspace/branch/muto_agent
AGENT_PORT=8601 ./run_agent.sh > /tmp/run_agent.log 2>&1 &
sleep 6
curl -s http://127.0.0.1:8601/ ; echo
kill %1 2>/dev/null; wait 2>/dev/null
grep -E "Uvicorn running on|:8601" /tmp/run_agent.log
```
Expected: `{"status":"ok"}` 출력, 로그에 `:8601` 바인드 확인 → 환경변수 포트 오버라이드가 동작함.

---

### Task 4: 최종 수동 검증 (사용자)

**Files:** (없음 — 실행 검증만)

**Interfaces:**
- Consumes: Task 1~3 산출물, 실제 Proxy 값이 담긴 `.env`.
- Produces: 성공 기준 충족 확인.

> 브라우저 상호작용 + 실제 Proxy가 필요해 자동화할 수 없다. 사용자가 실행한다.

- [ ] **Step 1: `.env`에 포트 변수 반영 (필요 시)**

`.env`에 `AGENT_HOST=127.0.0.1`, `AGENT_PORT=8000`, `STREAMLIT_PORT=8501`을 추가한다(기본값이 있으므로 생략해도 동작). 보안 훅이 도구 편집을 막으므로 사용자가 직접 편집한다.

- [ ] **Step 2: 동시 실행**

Run:
```bash
cd /Users/kakaogames/workspace/branch/muto_agent
./run.sh
```
백엔드가 백그라운드로 뜨고, 프론트가 표시하는 Local URL로 접속한다.

- [ ] **Step 3: 동작 확인 (성공 기준)**

브라우저에서 확인:
1. Chat 페이지에서 질문 → **스트리밍**으로 답이 출력됨(백엔드 경유).
2. 후속 질문 → 이전 맥락 유지(멀티턴). 최신 정보 질문 → 웹검색 동작(회귀 없음).
3. 사이드바 멀티페이지(Chat/페이지 2/페이지 3) 정상 동작(회귀 없음).
4. 백엔드를 끈 채 질문 → Streamlit이 크래시 없이 `st.error`로 연결 실패 안내.
5. (선택) 포트 오버라이드: `AGENT_PORT=9000 ./run.sh` → 백엔드 9000, 프론트도 9000으로 접속되어 정상 대화.

모든 항목 통과 시 완료.

---

## Self-Review

**Spec coverage:**
- 백엔드 분리(FastAPI, /chat SSE) → Task 1 ✅
- 프론트를 HTTP 클라이언트로 → Task 2 Step 1 ✅
- SSE 형식(delta/[DONE]/error) → Task 1 Step 2(생성) + Task 2 Step 1(소비) ✅
- stateless, 히스토리 프론트 보유 → Task 2 Step 1 (`{"messages": st.session_state.messages}` 전체 전송) ✅
- 포트/호스트 변수(AGENT_HOST/PORT/STREAMLIT_PORT) + 오버라이드 → Task 1 Step 2, Task 2 Step 1, Task 3, `.env.example`(Task 2 Step 2) ✅
- 스크립트 3종 + chmod → Task 3 ✅
- fastapi/uvicorn/httpx 의존성 → Task 1 Step 1 ✅
- 멀티페이지/부트스트랩/config.toml 유지 → Task 2 Step 1 (해당 부분 보존) ✅
- 에러 처리(연결 실패 st.error + pop) → Task 2 Step 1 (try/except), Task 4 Step 3 항목 4 ✅
- 검증(백엔드 헬스 / 프론트 기동 / 포트 오버라이드 / 대화·회귀) → Task 1 Step 4, Task 2 Step 3~4, Task 3 Step 5, Task 4 Step 3 ✅

**Placeholder scan:** "TBD/TODO" 없음. 코드 스텝에 완전한 파일 내용/before-after 포함. 명령마다 기대 출력 명시. spec의 uvicorn-CLL 예시와의 차이는 계획 상단 note에 근거를 밝힘.

**Type consistency:** SSE 키가 백엔드(`delta`/`error`, `[DONE]`)와 프론트 파서(`data.get("delta")`, `"error" in data`, `payload == "[DONE]"`)에서 일치. 포트 변수명 `AGENT_HOST`/`AGENT_PORT`/`STREAMLIT_PORT`가 agent_server.py·app.py·스크립트·.env.example 전 구간 일치. `POST /chat` body 키 `messages`가 백엔드 `ChatRequest.messages`와 프론트 전송 `{"messages": ...}`에서 일치.
