# 설계: Streamlit ↔ Agent 백엔드 분리

- 날짜: 2026-07-08
- 상태: 승인됨
- 선행: [2026-07-08-litellm-streamlit-chatbot-design.md](2026-07-08-litellm-streamlit-chatbot-design.md), [2026-07-08-web-search-integration-design.md](2026-07-08-web-search-integration-design.md), [2026-07-08-multipage-sidebar-design.md](2026-07-08-multipage-sidebar-design.md)

## 목표

지금은 Streamlit 앱이 `openai` SDK로 LiteLLM Proxy에 직접 붙는다. 이를 둘로
분리한다:

- **Agent 백엔드(FastAPI)**: LLM 호출·웹검색·대화 로직을 담당하고 HTTP로 노출.
- **Streamlit 프론트엔드**: 사용자 입력을 받아 백엔드에 HTTP로 요청하고 응답을
  렌더. 더 이상 LLM에 직접 붙지 않는다.

범위는 **얕은 API** — 현재 챗 로직을 그대로 HTTP 뒤로 옮긴다. 새 기능은 없다.

## 아키텍처

```
[Streamlit app.py]  --HTTP(SSE)-->  [agent_server.py (FastAPI)]  --openai SDK-->  [LiteLLM Proxy]
  UI 클라이언트                        LLM 호출 + web_search_options        Claude 모델
```

## 파일 구조

```
muto_agent/
  agent_server.py     # 신규: FastAPI 앱. POST /chat → SSE 토큰 스트림
  app.py              # 수정: chat_page가 LLM 직접호출 대신 백엔드 /chat 호출
  pyproject.toml      # 수정: fastapi, uvicorn, httpx 추가
  run.sh              # 신규: 백엔드 + 프론트 동시 실행
  run_agent.sh        # 신규: 백엔드만 실행 (포트 지정 가능)
  run_app.sh          # 신규: 프론트만 실행 (포트 지정 가능)
  .env / .env.example # 수정: AGENT_HOST/AGENT_PORT/STREAMLIT_PORT 추가
  .streamlit/config.toml, README.md  # 유지 / README 갱신
```

## 통신 (stateless, SSE)

- 대화 히스토리는 **Streamlit이 계속 보유**(`st.session_state.messages`), 매 요청에
  전체를 백엔드로 보낸다 → 백엔드는 무상태(stateless).
- 엔드포인트: `POST /chat`, body `{"messages": [{"role","content"}, ...]}`.
- 응답: `text/event-stream`. 각 토큰을 `data: {"delta": "..."}\n\n`로 보내고,
  끝에 `data: [DONE]\n\n`. (JSON으로 감싸 개행/특수문자 안전.)
- 백엔드는 내부에서 기존 로직대로 openai SDK를 `stream=True`,
  `web_search_options={}`로 호출하고, 받은 `delta.content`를 위 SSE 형식으로
  재전송한다. `chunk.choices`가 비면 건너뛴다(기존 가드 유지).
- Streamlit은 `httpx.stream("POST", ...)`로 SSE를 받아 `delta`만 뽑아내는
  제너레이터를 만들고 `st.write_stream`에 넘긴다 → 현재 타이핑 UX 유지.

## 설정

- 백엔드 LLM 접속: 기존 `OPENAI_BASE_URL` / `OPENAI_API_KEY` / `MODEL_NAME`
  `.env` 그대로 사용.
- 프로세스 포트/호스트 (`.env`에 두고 스크립트·백엔드·프론트가 공유):
  - `AGENT_HOST` (기본 `127.0.0.1`), `AGENT_PORT` (기본 `8000`): 백엔드가 바인드하는
    주소이자, 프론트가 `http://{AGENT_HOST}:{AGENT_PORT}`로 조합해 접속하는 주소.
    **백엔드 포트는 이 한 곳에서 관리**한다(프론트가 같은 값을 읽으므로 이중 관리 없음).
  - `STREAMLIT_PORT` (기본 `8501`): 프론트 포트.
- 프론트 코드는 `AGENT_HOST`/`AGENT_PORT`를 읽어 백엔드 base URL을 조합한다.

## 실행

세 개의 스크립트를 둔다. 모두 `.env`의 포트/호스트 변수를 읽으며, 없으면 기본값을
쓴다. 환경변수로 오버라이드도 가능하다(예: `AGENT_PORT=9000 ./run.sh`).

```
./run_agent.sh    # 백엔드만 (AGENT_HOST:AGENT_PORT 바인드)
./run_app.sh      # 프론트만 (STREAMLIT_PORT)
./run.sh          # 둘 다 동시 실행
```

- `run_agent.sh`: `uv run uvicorn agent_server:app --host "${AGENT_HOST:-127.0.0.1}" --port "${AGENT_PORT:-8000}"`
- `run_app.sh`: `STREAMLIT_SERVER_PORT="${STREAMLIT_PORT:-8501}" uv run app.py`
- `run.sh`: `run_agent.sh`를 백그라운드로 띄우고 `run_app.sh`를 포그라운드로 실행하며,
  종료(Ctrl+C) 시 백엔드도 함께 정리한다(trap).

세 스크립트 모두 실행 권한을 부여한다(`chmod +x`).

## 유지되는 것 (회귀 방지)

- 멀티페이지 구조(`run_app`, `page_two`/`page_three`), 부트스트랩,
  `.streamlit/config.toml`은 그대로. `chat_page`의 **LLM 호출 부분만** 백엔드
  HTTP 호출로 교체한다.
- 웹검색·스트리밍·멀티턴 동작은 사용자 관점에서 동일하게 유지된다(로직이 백엔드로
  이동했을 뿐).
- 에러 처리: 백엔드 연결/응답 실패 시 `st.error`로 표시하고 실패한 턴의 사용자
  메시지를 히스토리에서 제거(기존 동작 유지).

## 범위 밖 (YAGNI)

- 인증/토큰, 여러 엔드포인트, tool 확장, Docker/compose, 배포 스크립트, 백엔드
  측 세션/히스토리 저장은 하지 않는다.

## 검증 (성공 기준)

CLAUDE.md 규칙상 실제 데이터 기반 자동 테스트는 작성하지 않으며, 수동 실행으로
확인한다.

1. 백엔드 기동: `./run_agent.sh` → 예외 없이 뜨고 `GET /` 또는 `/docs`가 응답(헬스 확인).
2. `./run.sh`(또는 개별 실행) 후 Streamlit 접속 → Chat 페이지에서 질문 시
   **스트리밍**으로 답이 출력됨(백엔드 경유).
3. 후속 질문 시 이전 맥락 유지(멀티턴), 최신 정보 질문 시 웹검색 동작(회귀 없음).
4. 사이드바 멀티페이지(Chat/페이지 2/페이지 3) 정상 동작(회귀 없음).
5. 백엔드를 끈 상태에서 질문 → Streamlit이 크래시 없이 `st.error`로 연결 실패 안내.
6. 포트 오버라이드: `AGENT_PORT=9000 ./run_agent.sh`로 백엔드를 9000에 띄우고,
   프론트도 같은 `AGENT_PORT`로 실행 → 프론트가 9000의 백엔드에 정상 접속.
