# 설계: LiteLLM Proxy 기반 Streamlit 챗봇

- 날짜: 2026-07-08
- 상태: 승인됨

## 목표

사내/자체 **LiteLLM Proxy 서버**(OpenAI 호환)에 붙어 멀티턴 대화를
스트리밍으로 렌더링하는 **간단한 웹 챗봇**을 만든다. 데모/개인용 수준의
최소 기능에 집중한다.

## 범위

포함:
- 멀티턴 대화 히스토리 유지
- 스트리밍 응답 출력

제외 (YAGNI):
- 모델 선택 UI
- system prompt / temperature / max_tokens 등 파라미터 조정 UI
- 대화 저장/불러오기, 인증, 다중 세션 관리

## 아키텍처

단일 `app.py` Streamlit 앱. 클라이언트는 OpenAI 호환 스펙이므로
`litellm` 패키지 대신 가벼운 `openai` SDK를 사용해 `base_url` + `api_key`만
지정한다.

```
사용자 입력 ─▶ session_state.messages 누적 ─▶ openai SDK (stream=True)
                                                    │
   st.chat_message ◀─ st.write_stream ◀─ 스트리밍 청크
```

## 파일 구조

```
muto_agent/
  app.py            # 전체 앱 (UI + LLM 호출 + 히스토리)
  .env              # 실제 설정값 (gitignore 대상, 커밋하지 않음)
  .env.example      # 설정 템플릿
  requirements.txt  # streamlit, openai, python-dotenv
  .gitignore
  README.md         # 실행법
```

> 참고: 본 프로젝트는 git 저장소로 초기화하지 않는다. `.gitignore`는
> 추후 git 사용 시를 대비한 안전장치로만 포함한다.

## 설정 (.env)

```
OPENAI_BASE_URL=<Proxy BaseUrl, 예: http://your-proxy/v1>
OPENAI_API_KEY=<Proxy API 키>
MODEL_NAME=<사용할 모델명>
```

- `python-dotenv`로 로드한다.
- 세 값 중 하나라도 비어 있으면 앱 시작 시 `st.error`로 어떤 값이
  누락됐는지 안내하고 `st.stop()`으로 정지한다.

## 데이터 흐름 & 상태

- `st.session_state.messages`: `[{"role": "user"|"assistant", "content": str}]`
  리스트로 대화 히스토리를 유지한다.
- 앱 재실행(rerun) 시 기존 메시지를 순서대로 다시 그린다.
- 사용자가 입력하면:
  1. 입력을 `messages`에 append하고 화면에 표시
  2. **전체** `messages`를 Proxy로 전송 (멀티턴 맥락 유지)
  3. `client.chat.completions.create(model=MODEL_NAME, messages=..., stream=True)`
  4. 스트리밍 청크의 `delta.content`를 `st.write_stream`으로 실시간 출력
  5. 완성된 응답 텍스트를 `messages`에 append

## 에러 처리

- 필수 env 누락 → 앱 상단에 설정 안내 표시 후 `st.stop()`.
- API 호출 실패(연결/인증 등 예외) → `st.error`로 메시지를 표시하고 앱은
  계속 살아 있어 재시도 가능. 실패한 턴의 사용자 메시지는 히스토리에서
  제거해 다음 요청이 깨진 상태로 나가지 않도록 한다.

## 검증 (성공 기준)

CLAUDE.md 규칙상 실제 데이터 기반 자동 테스트는 작성하지 않으며, 수동
검증으로 확인한다.

1. `streamlit run app.py` 실행 → 브라우저 로드 성공
2. 메시지 입력 → 응답이 스트리밍으로 실시간 출력됨
3. 이어서 후속 질문 → 이전 대화 맥락을 기억함 (멀티턴 확인)
4. env 누락 상태로 실행 → 친절한 설정 안내가 표시되고 정지됨

## 의존성

- `streamlit`
- `openai`
- `python-dotenv`
