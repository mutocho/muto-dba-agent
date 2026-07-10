# 사이드바 멀티페이지 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 챗봇 앱에 왼쪽 사이드바 네비게이션을 추가해 Chat + 빈 페이지 2개(총 3개)로 이동할 수 있게 한다.

**Architecture:** `st.navigation` + `st.Page` API로 `app.py` 단일 파일 안에 페이지 함수들을 선언한다. 기존 챗봇 로직 `main()`을 `chat_page()`로 이름만 바꿔 한 페이지로 삼고, 빈 페이지 함수 2개와 페이지를 묶는 `run_app()`을 추가한다. 부트스트랩은 런타임 안에서 `main()` 대신 `run_app()`을 호출하도록만 바꾼다.

**Tech Stack:** Python, Streamlit 1.36+ (`st.navigation`/`st.Page`), openai SDK

## Global Constraints

- `st.navigation` + `st.Page` 방식으로 구현한다 (`pages/` 디렉토리 방식 아님).
- 앱 로직은 단일 `app.py`에 유지한다.
- 기존 챗봇 로직(env 검증, `web_search_options={}`, 스트리밍, 멀티턴, 예외 처리)은 내용 변경 없이 `chat_page`로 옮긴다 — 함수 이름만 바뀐다.
- 부트스트랩의 `streamlit run` 자기 재실행 분기, `.streamlit/config.toml`은 변경하지 않는다.
- 빈 페이지 이름은 임시("페이지 2"/"페이지 3"), 내용은 플레이스홀더.
- 이 프로젝트는 git 저장소가 아니다. 커밋하지 않으며, 각 태스크는 실행 검증으로 마무리한다.
- 실제 데이터 기반 자동 테스트는 작성하지 않는다. 검증은 실제 실행 관찰로 한다.
- 프로젝트 루트: `/Users/kakaogames/workspace/branch/muto_agent` / 실행: `uv run app.py`

---

### Task 1: app.py 멀티페이지 리팩터

**Files:**
- Modify: `/Users/kakaogames/workspace/branch/muto_agent/app.py`

**Interfaces:**
- Consumes: 기존 `app.py`의 챗봇 로직(현재 `main()`), `st.session_state.messages`.
- Produces: `chat_page()`, `page_two()`, `page_three()`, `run_app()` 함수. 부트스트랩이 `run_app()`을 호출.

- [ ] **Step 1: `main` 함수 이름을 `chat_page`로 변경**

`app.py`에서 함수 정의 한 줄을 바꾼다. 함수 본문(챗봇 로직)은 건드리지 않는다.

찾기:
```python
def main():
    load_dotenv()
```
교체:
```python
def chat_page():
    load_dotenv()
```

- [ ] **Step 2: 빈 페이지 함수 2개와 `run_app()` 추가**

`chat_page()` 함수 본문이 끝난 직후(부트스트랩 `if __name__ == "__main__":` 바로 앞)에 아래를 삽입한다. 현재 `chat_page`의 마지막 줄은 예외 처리 블록의 `st.session_state.messages.pop()`이다.

찾기 (chat_page 끝 → 부트스트랩 시작 경계):
```python
            except Exception as error:
                st.error(f"응답 생성 중 오류가 발생했습니다: {error}")
                # 실패한 턴의 사용자 메시지를 히스토리에서 제거
                st.session_state.messages.pop()


if __name__ == "__main__":
```
교체:
```python
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
```

- [ ] **Step 3: 부트스트랩이 `run_app()`을 호출하도록 변경**

런타임 안에서 `main()` 대신 `run_app()`을 호출한다. 재실행 분기는 그대로 둔다.

찾기:
```python
    if runtime.exists():
        # streamlit 런타임 안 → 앱 로직 실행
        main()
    else:
```
교체:
```python
    if runtime.exists():
        # streamlit 런타임 안 → 페이지 네비게이션 실행
        run_app()
    else:
```

- [ ] **Step 4: 구문/임포트 검증**

Run:
```bash
cd /Users/kakaogames/workspace/branch/muto_agent
uv run python -c "import ast; ast.parse(open('app.py').read()); print('syntax ok')"
```
Expected: `syntax ok` 출력. `main` 이라는 이름이 더 이상 정의/호출되지 않는지도 확인:
```bash
cd /Users/kakaogames/workspace/branch/muto_agent
grep -nE "def main|[^_]main\(\)" app.py || echo "no stray main"
```
Expected: `no stray main` (또는 grep 결과 없음).

- [ ] **Step 5: headless 기동 검증**

Run:
```bash
cd /Users/kakaogames/workspace/branch/muto_agent
STREAMLIT_SERVER_PORT=8611 timeout 40 uv run app.py > /tmp/multipage_boot.log 2>&1 || true
grep -E "You can now view|Traceback" /tmp/multipage_boot.log
```
Expected: `You can now view your Streamlit app` 라인이 보이고, 기동 단계 `Traceback`은 없어야 한다. (timeout 종료 시점의 종료 트레이스백은 무시 — 서버 기동 성공이면 통과.) 로그 내용을 보고서에 기록한다.

---

### Task 2: 최종 수동 검증 (사용자)

**Files:** (없음 — 실행 검증만)

**Interfaces:**
- Consumes: Task 1이 리팩터한 `app.py`, 실제 Proxy 값이 담긴 `.env`.
- Produces: 성공 기준 충족 확인.

> 이 태스크는 브라우저 상호작용이 필요해 자동화할 수 없다. 사용자가 실행한다.

- [ ] **Step 1: 앱 실행**

Run:
```bash
cd /Users/kakaogames/workspace/branch/muto_agent
uv run app.py
```
표시된 Local URL로 접속한다.

- [ ] **Step 2: 멀티페이지 동작 확인 (성공 기준)**

브라우저에서 확인:
1. 왼쪽 **사이드바에 Chat / 페이지 2 / 페이지 3** 세 항목이 보인다.
2. 각 항목 클릭 시 해당 페이지로 이동한다 (페이지 2/3은 제목 + "준비 중입니다.").
3. Chat 페이지에서 대화한 뒤 페이지 2로 갔다가 Chat으로 돌아와도 **대화 히스토리가 유지**된다.
4. 챗봇 기능(스트리밍·웹검색·멀티턴)에 회귀가 없다.

모든 항목 통과 시 완료.

---

## Self-Review

**Spec coverage:**
- `st.navigation`+`st.Page` 방식 → Task 1 Step 2 (`run_app`) ✅
- 단일 app.py 유지 → Task 1 (모든 함수 app.py 내) ✅
- main→chat_page 이름만 변경, 챗봇 로직 불변 → Task 1 Step 1 ✅
- 빈 페이지 2개 + Chat 3개 구성, Chat default → Task 1 Step 2 (`st.Page(..., default=True)`) ✅
- 부트스트랩 run_app 호출, 재실행 분기 유지 → Task 1 Step 3 ✅
- 사이드바 이동 / session_state 히스토리 유지 → Task 2 Step 2 (항목 1~3) ✅
- 챗봇 기능 회귀 방지 → Task 1 Step 5(기동) + Task 2 Step 2(항목 4) ✅

**Placeholder scan:** "TBD/TODO" 없음. 빈 페이지의 "준비 중입니다."는 spec이 명시한 의도적 플레이스홀더 내용(미완성 지시가 아님). 모든 코드 스텝에 완전한 before/after 코드 포함.

**Type consistency:** 함수명 `chat_page`/`page_two`/`page_three`/`run_app`가 Step 1~3에서 일관. Step 1에서 `main`→`chat_page`로 바꾼 뒤 Step 3에서 `run_app()` 호출 — Step 2에서 정의한 `run_app`과 일치. `st.Page`에 넘기는 함수 참조(`chat_page` 등)도 정의된 이름과 일치.
