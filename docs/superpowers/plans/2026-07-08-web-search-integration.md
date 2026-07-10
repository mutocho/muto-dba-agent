# 웹 검색 통합 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Streamlit 챗봇이 최신 정보를 웹 검색으로 답하도록, LLM 요청에 `web_search_options`를 추가한다.

**Architecture:** `app.py`의 스트리밍 요청 생성 호출에 OpenAI 호환 `web_search_options={}` 파라미터 한 줄을 추가한다. LiteLLM Proxy가 이를 현재 Claude 모델의 web search server tool로 변환한다. 스트리밍·멀티턴·에러 처리는 기존 구조 그대로 재사용한다.

**Tech Stack:** Python, Streamlit, openai SDK (OpenAI 호환 LiteLLM Proxy)

## Global Constraints

- LLM 호출은 `openai` SDK로 한다 (Anthropic SDK로 갈아엎지 않는다 — Proxy가 OpenAI 호환).
- 웹 검색은 방법 A(`web_search_options`)로 켠다. Anthropic 전용 tool 버전 문자열(`web_search_20260209` 등)을 앱에 하드코딩하지 않는다.
- 앱 로직은 단일 `app.py`에 유지한다.
- 이 프로젝트는 git 저장소가 아니다. 커밋하지 않으며, 각 태스크는 실행 검증으로 마무리한다.
- 실제 데이터 기반 자동 테스트는 작성하지 않는다. 검증은 실제 실행 관찰로 한다.
- 프로젝트 루트: `/Users/kakaogames/workspace/branch/muto_agent`
- 실행: `uv run app.py`

---

### Task 1: `web_search_options` 추가 및 진단 스크립트 정리

**Files:**
- Modify: `/Users/kakaogames/workspace/branch/muto_agent/app.py` (`main()` 내 `client.chat.completions.create(...)` 호출)
- Delete: `/Users/kakaogames/workspace/branch/muto_agent/probe.py`
- Delete: `/Users/kakaogames/workspace/branch/muto_agent/probe2.py`

**Interfaces:**
- Consumes: 기존 `app.py`의 `client`(openai `OpenAI`), `MODEL_NAME`, `st.session_state.messages`.
- Produces: 다른 태스크가 소비하는 함수 시그니처 없음 (앱 동작 변경뿐).

- [ ] **Step 1: `app.py`의 스트림 생성 호출에 `web_search_options={}` 추가**

`app.py`의 `main()` 안에서 아래 기존 코드를 찾는다:

```python
                stream = client.chat.completions.create(
                    model=MODEL_NAME,
                    messages=st.session_state.messages,
                    stream=True,
                )
```

다음으로 교체한다 (`web_search_options={}` 한 줄만 추가):

```python
                stream = client.chat.completions.create(
                    model=MODEL_NAME,
                    messages=st.session_state.messages,
                    stream=True,
                    web_search_options={},
                )
```

다른 부분(히스토리 렌더, `token_stream`, 예외 처리, `st.write_stream`)은 건드리지 않는다.

- [ ] **Step 2: 구문/임포트 검증**

Run:
```bash
cd /Users/kakaogames/workspace/branch/muto_agent
uv run python -c "import ast; ast.parse(open('app.py').read()); print('syntax ok')"
```
Expected: `syntax ok` 출력.

- [ ] **Step 3: headless 기동 검증 (트레이스백 없이 서버가 뜨는지)**

Run:
```bash
cd /Users/kakaogames/workspace/branch/muto_agent
STREAMLIT_SERVER_PORT=8610 timeout 40 uv run app.py > /tmp/websearch_boot.log 2>&1 || true
grep -E "You can now view|Traceback" /tmp/websearch_boot.log
```
Expected: `You can now view your Streamlit app` 라인이 보이고, `Traceback`(기동 단계 예외)은 없어야 한다. (종료 시 SIGTERM으로 인한 종료 트레이스백은 무시 — 서버 기동 자체가 성공이면 통과.)

- [ ] **Step 4: 진단 스크립트 제거**

설계 확정용 일회성 스크립트이므로 제거한다.

Run:
```bash
cd /Users/kakaogames/workspace/branch/muto_agent
rm probe.py probe2.py && echo "removed"
```
Expected: `removed` 출력, `probe.py`/`probe2.py`가 더 이상 존재하지 않음.

---

### Task 2: 최종 수동 검증 (사용자)

**Files:** (없음 — 실행 검증만)

**Interfaces:**
- Consumes: Task 1이 수정한 `app.py`, 실제 Proxy 값이 담긴 `.env`.
- Produces: 성공 기준 충족 확인.

> 이 태스크는 실제 LiteLLM Proxy와 브라우저 대화가 필요해 자동화할 수 없다. 사용자가 실행한다.

- [ ] **Step 1: 앱 실행**

Run:
```bash
cd /Users/kakaogames/workspace/branch/muto_agent
uv run app.py
```
표시된 Local URL(예: `http://localhost:8501`)로 접속한다.

- [ ] **Step 2: 웹 검색 동작 확인 (성공 기준)**

브라우저에서 확인:
1. "오늘 날짜와 이번 주 주요 뉴스 헤드라인 한 개"를 물음 → 2024년 4월 컷오프 안내 없이 **검색 기반 최신 답변**이 스트리밍으로 출력됨.
2. 최신 정보가 필요 없는 일반 질문(예: "파이썬 리스트 컴프리헨션 예시") → 기존처럼 검색 없이 즉답 (회귀 없음).
3. 후속 질문 → 이전 대화 맥락 유지 (멀티턴 회귀 없음).

모든 항목 통과 시 완료.

---

## Self-Review

**Spec coverage:**
- 웹 검색 통합(방법 A `web_search_options`) → Task 1 Step 1 ✅
- OpenAI SDK 유지 / tool 버전 하드코딩 금지 → Task 1 Step 1 (파라미터만 추가, tool 문자열 없음) ✅
- 스트리밍/멀티턴/에러/히스토리 스키마 불변 → Task 1 Step 1 (해당 부분 미변경) ✅
- 진단 스크립트 정리 → Task 1 Step 4 ✅
- 검증(수동, 자동테스트 없음): 최신 정보 답변 / 일반 질문 회귀 / 멀티턴 → Task 1 Step 2~3(구문·기동) + Task 2 Step 2(대화 검증) ✅
- 범위 밖(citation UI, 검색 세부 옵션) → 계획에 추가 태스크 없음(의도적) ✅

**Placeholder scan:** "TBD/TODO/나중에" 없음. 코드 변경 스텝에 정확한 before/after 코드 포함. 모든 명령에 기대 출력 명시.

**Type consistency:** 파라미터명 `web_search_options`, 환경변수 `MODEL_NAME`, 상태 `st.session_state.messages`가 spec 및 기존 `app.py`와 일치. 새로 도입한 심볼 없음.
