# 설계: Streamlit 사이드바 멀티페이지

- 날짜: 2026-07-08
- 상태: 승인됨
- 선행: [2026-07-08-litellm-streamlit-chatbot-design.md](2026-07-08-litellm-streamlit-chatbot-design.md), [2026-07-08-web-search-integration-design.md](2026-07-08-web-search-integration-design.md)

## 목표

기존 단일 챗봇 앱에 **왼쪽 사이드바 네비게이션**을 추가해, 사이드바 항목을
누르면 해당 페이지로 이동하는 멀티페이지 구조를 만든다. 지금은 **골격만**
세운다 — 챗봇 페이지 + 빈 페이지 2개(총 3개). 빈 페이지 내용은 나중에 채운다.

## 방식 결정: `st.navigation` + `st.Page`

- Streamlit 1.36+의 `st.navigation` / `st.Page` API를 쓴다 (설치된 1.59에서 지원).
- 진입점 `app.py` 하나에서 페이지 목록을 선언하므로, 기존 `uv run app.py`
  부트스트랩(단일 진입점, `streamlit run` 자기 재실행)과 자연스럽게 맞는다.
- 페이지를 `app.py` 내 함수로 두어 **단일 파일 원칙**을 유지한다.
- 대안인 `pages/` 디렉토리 방식은 페이지마다 파일이 쪼개져 단일 파일 원칙과
  어긋나므로 채택하지 않는다.

## 구조 (app.py 리팩터)

기존 `main()`(챗봇 전체 로직)을 `chat_page()`로 이름만 바꿔 페이지 함수로 삼고,
빈 페이지 함수 2개와 페이지를 묶는 `run_app()`을 추가한다.

```python
def chat_page():
    # 기존 main()의 챗봇 로직 전체 (env 검증, web_search_options, 스트리밍,
    # 멀티턴, 에러 처리) — 내용 변경 없이 함수 이름만 chat_page로.
    ...

def page_two():
    st.title("페이지 2")
    st.write("준비 중입니다.")

def page_three():
    st.title("페이지 3")
    st.write("준비 중입니다.")

def run_app():
    pages = [
        st.Page(chat_page,  title="Chat",    icon="💬", default=True),
        st.Page(page_two,   title="페이지 2", icon="📄"),
        st.Page(page_three, title="페이지 3", icon="📄"),
    ]
    st.navigation(pages).run()
```

부트스트랩(`if __name__ == "__main__"`)은 런타임 안에서 `main()` 대신
`run_app()`을 호출하도록만 바꾼다. `streamlit run` 자기 재실행 분기는 그대로 둔다.

```python
if __name__ == "__main__":
    from streamlit import runtime
    from streamlit.web import cli as stcli

    if runtime.exists():
        run_app()
    else:
        sys.argv = ["streamlit", "run", __file__]
        sys.exit(stcli.main())
```

## 동작 & 상태

- 왼쪽 사이드바에 3개 페이지(Chat / 페이지 2 / 페이지 3)가 나열되고, 클릭하면
  해당 페이지로 이동한다. `st.navigation`이 사이드바 네비게이션을 자동 생성한다.
- 첫 진입 시 `default=True`인 **Chat** 페이지가 열린다.
- 페이지를 전환해도 `st.session_state`는 유지되므로, 다른 페이지에 갔다 와도
  챗 히스토리(`st.session_state.messages`)가 보존된다.
- env 검증/`st.stop()`은 `chat_page` 안에서만 동작한다 → env 미설정 상태에서도
  빈 페이지는 정상 접근된다(빈 페이지는 LLM이 필요 없으므로 합리적).

## 유지되는 것 (회귀 방지)

- 챗봇 로직 전체(env 검증, `web_search_options={}`, 스트리밍, 멀티턴, 예외 처리)는
  `chat_page`로 그대로 옮겨진다. 함수 이름만 바뀐다.
- 부트스트랩의 `streamlit run` 재실행 분기, `.streamlit/config.toml`(headless,
  runOnSave)은 변경하지 않는다.

## 범위 밖 (YAGNI)

- 빈 페이지 이름은 임시("페이지 2"/"페이지 3")이며 내용도 플레이스홀더다.
  실제 이름/내용은 나중에 채운다.
- 페이지 그룹핑, URL 라우팅 커스터마이징, 페이지별 접근 제어는 하지 않는다.

## 검증 (성공 기준)

CLAUDE.md 규칙상 실제 데이터 기반 자동 테스트는 작성하지 않으며, 수동 실행으로
확인한다.

1. `uv run app.py` 실행 후 접속 → 왼쪽 사이드바에 Chat / 페이지 2 / 페이지 3 표시.
2. 각 사이드바 항목 클릭 시 해당 페이지로 이동.
3. Chat 페이지에서 대화 후 다른 페이지로 갔다가 돌아와도 대화 히스토리 유지.
4. 챗봇 기능(스트리밍·웹검색·멀티턴) 회귀 없음.
