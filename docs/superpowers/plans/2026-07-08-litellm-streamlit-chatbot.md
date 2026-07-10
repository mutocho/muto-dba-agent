# LiteLLM Streamlit 챗봇 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** OpenAI 호환 LiteLLM Proxy에 붙어 멀티턴 대화를 스트리밍으로 보여주는 단일 파일 Streamlit 챗봇을 만든다.

**Architecture:** 단일 `app.py` Streamlit 앱. `openai` SDK로 Proxy의 `base_url`+`api_key`에 붙어 `chat.completions.create(stream=True)`를 호출하고, `st.session_state.messages`로 대화 히스토리를 유지하며, `st.write_stream`으로 실시간 렌더링한다.

**Tech Stack:** Python, Streamlit, openai SDK, python-dotenv

## Global Constraints

- LLM 호출은 `litellm` 패키지가 아니라 `openai` SDK로 한다 (Proxy가 OpenAI 호환).
- 설정값(`OPENAI_BASE_URL`, `OPENAI_API_KEY`, `MODEL_NAME`)은 `.env` + `python-dotenv`로만 주입한다.
- 앱 로직은 단일 `app.py`에 담는다 (모듈 분리 금지 — YAGNI).
- 이 프로젝트는 git 저장소로 초기화하지 않는다. 커밋 단계는 없으며, 각 태스크는 실행 검증으로 마무리한다.
- CLAUDE.md 규칙에 따라 실제 데이터 기반 자동 테스트는 작성하지 않는다. 검증은 실제 실행 관찰로 한다.
- 프로젝트 루트: `/Users/kakaogames/workspace/branch/muto_agent`

---

### Task 1: 프로젝트 스캐폴딩 & 의존성

**Files:**
- Create: `/Users/kakaogames/workspace/branch/muto_agent/requirements.txt`
- Create: `/Users/kakaogames/workspace/branch/muto_agent/.env.example`
- Create: `/Users/kakaogames/workspace/branch/muto_agent/.gitignore`
- Create: `/Users/kakaogames/workspace/branch/muto_agent/.env`

**Interfaces:**
- Consumes: (없음 — 첫 태스크)
- Produces: `.env`에서 읽을 3개 환경변수 이름을 확정한다 — `OPENAI_BASE_URL`, `OPENAI_API_KEY`, `MODEL_NAME` (Task 2가 이 이름을 그대로 사용).

- [ ] **Step 1: `requirements.txt` 작성**

```
streamlit
openai
python-dotenv
```

- [ ] **Step 2: `.env.example` 작성 (커밋 가능한 템플릿)**

```
OPENAI_BASE_URL=http://your-proxy-host/v1
OPENAI_API_KEY=your-proxy-api-key
MODEL_NAME=your-model-name
```

- [ ] **Step 3: `.gitignore` 작성 (추후 git 사용 대비 안전장치)**

```
.env
__pycache__/
*.pyc
.venv/
venv/
```

- [ ] **Step 4: `.env` 작성 (실제 값은 사용자가 채움 — 우선 템플릿 복사)**

`.env.example`과 동일한 내용으로 `.env`를 생성한다. 실제 Proxy 주소/키/모델명은 사용자가 채워 넣어야 하며, 비어 있으면 Task 2의 검증 단계에서 안내 메시지가 뜬다.

```
OPENAI_BASE_URL=http://your-proxy-host/v1
OPENAI_API_KEY=your-proxy-api-key
MODEL_NAME=your-model-name
```

- [ ] **Step 5: 가상환경 생성 및 의존성 설치**

Run:
```bash
cd /Users/kakaogames/workspace/branch/muto_agent
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```
Expected: `streamlit`, `openai`, `python-dotenv` 및 의존성이 오류 없이 설치됨. 마지막에 `Successfully installed ...` 출력.

- [ ] **Step 6: 설치 검증**

Run:
```bash
cd /Users/kakaogames/workspace/branch/muto_agent
.venv/bin/python -c "import streamlit, openai, dotenv; print('deps ok')"
```
Expected: `deps ok` 출력 (import 오류 없음).

---

### Task 2: `app.py` 챗봇 구현

**Files:**
- Create: `/Users/kakaogames/workspace/branch/muto_agent/app.py`

**Interfaces:**
- Consumes: Task 1이 정한 환경변수 `OPENAI_BASE_URL`, `OPENAI_API_KEY`, `MODEL_NAME`, 그리고 설치된 `streamlit` / `openai` / `python-dotenv`.
- Produces: `streamlit run app.py`로 실행되는 완성된 챗봇 (다른 태스크가 소비하는 함수 시그니처는 없음).

- [ ] **Step 1: `app.py` 전체 작성**

아래 코드를 그대로 작성한다. 설정 로드 → 검증 → 히스토리 렌더 → 입력 처리(스트리밍) → 에러 처리까지 전부 포함한다.

```python
import os

import streamlit as st
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

BASE_URL = os.getenv("OPENAI_BASE_URL")
API_KEY = os.getenv("OPENAI_API_KEY")
MODEL_NAME = os.getenv("MODEL_NAME")

st.title("💬 LiteLLM Chatbot")

# --- 설정 검증: 누락된 환경변수가 있으면 안내 후 정지 ---
missing = [
    name
    for name, value in [
        ("OPENAI_BASE_URL", BASE_URL),
        ("OPENAI_API_KEY", API_KEY),
        ("MODEL_NAME", MODEL_NAME),
    ]
    if not value
]
if missing:
    st.error(
        "다음 환경변수가 설정되지 않았습니다: "
        + ", ".join(missing)
        + "\n\n.env 파일을 확인하세요."
    )
    st.stop()

client = OpenAI(base_url=BASE_URL, api_key=API_KEY)

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
            stream = client.chat.completions.create(
                model=MODEL_NAME,
                messages=st.session_state.messages,
                stream=True,
            )

            def token_stream():
                for chunk in stream:
                    delta = chunk.choices[0].delta.content
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
```

- [ ] **Step 2: 구문/임포트 검증**

Run:
```bash
cd /Users/kakaogames/workspace/branch/muto_agent
.venv/bin/python -c "import ast; ast.parse(open('app.py').read()); print('syntax ok')"
```
Expected: `syntax ok` 출력 (구문 오류 없음).

- [ ] **Step 3: env 누락 처리 검증 (수동)**

`.env`의 값들이 아직 `your-proxy-host` 같은 플레이스홀더거나 비어 있는 상태에서 앱을 실행한다.

Run:
```bash
cd /Users/kakaogames/workspace/branch/muto_agent
.venv/bin/streamlit run app.py
```
확인:
- 브라우저가 열리고 "💬 LiteLLM Chatbot" 제목이 보인다.
- (env 값을 아예 비워둔 경우) "다음 환경변수가 설정되지 않았습니다..." 안내가 표시되고 채팅 입력창이 나타나지 않는다.
- 확인 후 터미널에서 `Ctrl+C`로 종료.

---

### Task 3: README & 최종 수동 검증

**Files:**
- Create: `/Users/kakaogames/workspace/branch/muto_agent/README.md`

**Interfaces:**
- Consumes: Task 1, 2의 결과물 (`requirements.txt`, `.env`, `app.py`).
- Produces: 실행 문서와 최종 동작 확인.

- [ ] **Step 1: `README.md` 작성**

```markdown
# LiteLLM Streamlit 챗봇

OpenAI 호환 LiteLLM Proxy에 붙는 간단한 웹 챗봇. 멀티턴 대화와 스트리밍 응답을 지원합니다.

## 설정

`.env` 파일에 Proxy 정보를 입력하세요:

\`\`\`
OPENAI_BASE_URL=http://your-proxy-host/v1
OPENAI_API_KEY=your-proxy-api-key
MODEL_NAME=your-model-name
\`\`\`

## 실행

\`\`\`bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/streamlit run app.py
\`\`\`

브라우저가 자동으로 열립니다. 메시지를 입력하면 스트리밍으로 응답이 출력되고, 이어지는 질문은 이전 대화 맥락을 유지합니다.
```

- [ ] **Step 2: 실제 Proxy 값으로 `.env` 채우기 (사용자 확인 필요)**

`.env`의 `OPENAI_BASE_URL`, `OPENAI_API_KEY`, `MODEL_NAME`을 실제 사내 LiteLLM Proxy 값으로 교체한다. (이 값은 사용자가 제공)

- [ ] **Step 3: 최종 수동 검증 (성공 기준)**

Run:
```bash
cd /Users/kakaogames/workspace/branch/muto_agent
.venv/bin/streamlit run app.py
```
확인 체크리스트 (설계 문서의 성공 기준과 일치):
1. 브라우저 로드 성공, 제목 표시.
2. 메시지 입력 → 응답이 **스트리밍**으로 실시간 출력된다.
3. 후속 질문 → 이전 대화 **맥락을 기억**한다 (멀티턴).
4. (선택) 잘못된 `OPENAI_API_KEY`로 실행 후 메시지 전송 → `st.error`로 오류가 표시되고 앱이 죽지 않는다.

모든 항목이 통과하면 완료.

---

## Self-Review

**Spec coverage:**
- 멀티턴 히스토리 → Task 2 (`st.session_state.messages` 누적 + 전체 전송) ✅
- 스트리밍 응답 → Task 2 (`stream=True` + `st.write_stream`) ✅
- .env 설정 관리 → Task 1 (파일 생성) + Task 2 (`load_dotenv` 로드) ✅
- env 누락 에러 처리 → Task 2 Step 1 (`missing` 검사 + `st.stop`), Task 2 Step 3 (검증) ✅
- API 실패 에러 처리 + 실패 턴 메시지 제거 → Task 2 Step 1 (`try/except` + `pop`), Task 3 Step 3 항목 4 (검증) ✅
- 단일 파일 구조 → Task 2 (`app.py` 하나) ✅
- 검증(수동, 자동테스트 없음) → Task 2/3의 실행 검증 스텝 ✅

**Placeholder scan:** "TBD/TODO/나중에 구현" 없음. 모든 코드 스텝에 완전한 코드 포함. `.env`의 `your-proxy-host` 등은 사용자가 채우는 설정 템플릿 값이며, 이는 설계에서 의도된 것.

**Type consistency:** 환경변수 이름 `OPENAI_BASE_URL`/`OPENAI_API_KEY`/`MODEL_NAME`이 Task 1~3에서 일관됨. `st.session_state.messages`의 스키마 `{"role", "content"}`가 렌더·전송·append 전 구간에서 일관됨.
