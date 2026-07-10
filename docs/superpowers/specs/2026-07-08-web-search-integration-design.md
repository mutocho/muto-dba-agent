# 설계: Streamlit 챗봇 웹 검색 통합

- 날짜: 2026-07-08
- 상태: 승인됨
- 선행: [2026-07-08-litellm-streamlit-chatbot-design.md](2026-07-08-litellm-streamlit-chatbot-design.md)

## 배경 / 문제

실제 Proxy에 붙여 대화해보니, LLM이 "2024년 4월 이후 정보에 접근할 수 없다"며
웹 검색 없이 답하는 현상을 확인했다. 챗봇이 최신 정보를 반영해 답하도록
**웹 검색 능력**을 추가한다.

## 진단으로 확정한 사실

- Proxy가 제공하는 모델은 전부 **Anthropic Claude** 계열(+임베딩 모델).
  검색 전용 모델(sonar 등)은 없다.
- Claude 모델은 웹 검색을 **서버 도구(server tool)로 네이티브 지원**한다.
  → 외부 검색 API(Tavily 등)나 tool-calling 루프를 직접 구현할 필요가 없다.
- 앱은 OpenAI 호환 `openai` SDK로 LiteLLM Proxy에 붙는다. 진단 결과 이 Proxy는
  OpenAI 호환 인터페이스에서 웹 검색을 켜는 방법 세 가지(A: `web_search_options`,
  B: `web_search_20250305` tool passthrough, B2: `web_search_20260209`)를
  모두 수용한다.

## 결정: 방법 A (`web_search_options`)

세 방법 중 **A**를 채택한다.

- OpenAI 호환 표준 파라미터라, LiteLLM이 **현재 모델에 맞는 web search tool을
  자동 선택**한다. `.env`의 `MODEL_NAME`을 신형/구형 어느 Claude로 바꿔도 앱 코드
  수정 없이 웹 검색이 따라온다.
- B/B2는 Anthropic 전용 tool 버전 문자열(`web_search_20260209` 등)을 앱에 박아야
  하고, 모델을 구형으로 바꾸면 400이 난다. "모델명만 바꿔 쓰는 간단한 챗봇"이라는
  기존 설계 목표와 어긋난다.

## 변경점

`app.py`의 `main()` 안, 스트리밍 요청 생성 호출에 `web_search_options={}`만 추가한다.

```python
stream = client.chat.completions.create(
    model=MODEL_NAME,
    messages=st.session_state.messages,
    stream=True,
    web_search_options={},   # 모델이 필요할 때 웹 검색 수행 (LiteLLM이 tool로 변환)
)
```

## 동작 & 상태

- 모델(Claude)이 최신 정보가 필요하다고 판단하면 서버 측에서 웹을 검색한 뒤 그
  결과를 근거로 답을 생성한다. 검색 여부는 모델이 자동 결정한다.
- 스트리밍/멀티턴/에러 처리는 기존 구조를 그대로 재사용한다.
- 히스토리 스키마 `{"role", "content"}`는 변경 없다. 검색은 서버가 처리하고,
  우리 히스토리에는 최종 답변 텍스트만 쌓인다.

## 범위 밖 (YAGNI)

- 출처(citation) 별도 UI: 모델이 답변 텍스트 안에 출처를 녹여 반환하므로,
  응답의 `annotation`을 따로 파싱해 각주로 렌더하지 않는다.
- 검색 도메인 필터 / 검색 컨텍스트 크기 조정 등 세부 옵션: 기본값(`{}`)으로 간다.

## 검증 (성공 기준)

CLAUDE.md 규칙상 실제 데이터 기반 자동 테스트는 작성하지 않으며, 수동 실행으로
확인한다.

1. `uv run app.py` 실행 후 표시된 Local URL로 접속.
2. "오늘 날짜와 이번 주 주요 뉴스"처럼 최신 정보를 물으면, 2024년 4월 컷오프
   안내 없이 **검색 기반 최신 답변**이 스트리밍으로 출력된다.
3. 최신 정보가 필요 없는 일반 질문은 기존처럼 검색 없이 즉답한다(회귀 없음).
4. 후속 질문 시 이전 대화 맥락을 유지한다(멀티턴 회귀 없음).

## 정리 대상

설계 확정을 위해 만든 일회성 진단 스크립트 `probe.py`, `probe2.py`는 구현 완료
후 제거한다(기능 코드 아님).
