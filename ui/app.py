import json
import os
import sys
from pathlib import Path

import httpx
import streamlit as st
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")


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
