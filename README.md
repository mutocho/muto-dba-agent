# LiteLLM Streamlit 챗봇

OpenAI 호환 LiteLLM Proxy에 붙는 간단한 웹 챗봇. 멀티턴 대화와 스트리밍 응답을 지원합니다.

## 설정

`.env` 파일에 Proxy 정보를 입력하세요:

```
OPENAI_BASE_URL=http://your-proxy-host/v1
OPENAI_API_KEY=your-proxy-api-key
MODEL_NAME=your-model-name
```

## 실행

[uv](https://docs.astral.sh/uv/)만 있으면 별도 설치 단계 없이 바로 실행됩니다. uv가 `pyproject.toml`의 의존성을 자동으로 준비합니다.

```
uv run app.py
```

`app.py`가 streamlit 런타임 밖에서 실행되면 자기 자신을 `streamlit run`으로 재실행하므로, 위 한 줄이면 됩니다.

`.streamlit/config.toml`에 `runOnSave = true`가 설정돼 있어 코드를 수정하고 저장하면 브라우저에 자동으로 반영됩니다(watchdog으로 변경 감지).

브라우저는 자동으로 열리지 않습니다(headless). 터미널에 표시되는 Local URL(예: http://localhost:8501)로 직접 접속하세요. 메시지를 입력하면 스트리밍으로 응답이 출력되고, 이어지는 질문은 이전 대화 맥락을 유지합니다.
