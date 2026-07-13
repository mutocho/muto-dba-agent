import json
import os
from pathlib import Path

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from openai import AsyncOpenAI
from pydantic import BaseModel

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

MODEL_NAME = os.getenv("MODEL_NAME")
MAX_TOOL_ITERATIONS = 8

MCP_ROUTER_HOST = os.getenv("MCP_ROUTER_HOST", "127.0.0.1")
MCP_ROUTER_PORT = os.getenv("MCP_ROUTER_PORT", "8010")
MCP_ROUTER_URL = f"http://{MCP_ROUTER_HOST}:{MCP_ROUTER_PORT}"

client = AsyncOpenAI(
    base_url=os.getenv("OPENAI_BASE_URL"),
    api_key=os.getenv("OPENAI_API_KEY"),
)

# MCP Router에서 받아온 도구 목록 캐시 (최초 1회 조회)
_tools_cache = {"tools": None}


async def _get_openai_tools():
    if _tools_cache["tools"] is not None:
        return _tools_cache["tools"]
    try:
        async with httpx.AsyncClient() as http:
            resp = await http.get(f"{MCP_ROUTER_URL}/tools", timeout=10)
            resp.raise_for_status()
            mcp_tools = resp.json()
        tools = [
            {
                "type": "function",
                "function": {
                    "name": tool["name"],
                    "description": tool["description"],
                    "parameters": tool["inputSchema"],
                },
            }
            for tool in mcp_tools
        ]
    except Exception as error:
        print(f"MCP Router 도구 조회 실패(도구 없이 계속): {error!r}")
        tools = []
    _tools_cache["tools"] = tools
    return tools


async def _call_mcp_tool(name, arguments):
    async with httpx.AsyncClient() as http:
        resp = await http.post(
            f"{MCP_ROUTER_URL}/call",
            json={"name": name, "arguments": arguments},
            timeout=None,
        )
        resp.raise_for_status()
        return resp.json()["content"]


app = FastAPI()


class ChatRequest(BaseModel):
    messages: list[dict]


@app.get("/")
def health():
    return {"status": "ok"}


@app.post("/chat")
async def chat(request: ChatRequest):
    tools = await _get_openai_tools()
    mcp_tool_names = {tool["function"]["name"] for tool in tools}

    async def event_stream():
        try:
            messages = list(request.messages)
            final_text = ""
            for _ in range(MAX_TOOL_ITERATIONS):
                kwargs = {
                    "model": MODEL_NAME,
                    "messages": messages,
                    "web_search_options": {},
                    "stream": False,
                }
                if tools:
                    kwargs["tools"] = tools
                resp = await client.chat.completions.create(**kwargs)
                message = resp.choices[0].message
                # web_search 등 프록시가 서버에서 실행하는 툴(id: srvtoolu_)은 이미 답변에
                # 반영돼 되돌아온다. 우리가 등록한 MCP 툴만 클라이언트가 실행한다.
                client_tool_calls = [
                    tc
                    for tc in (message.tool_calls or [])
                    if tc.function.name in mcp_tool_names
                ]
                if client_tool_calls:
                    messages.append(
                        {
                            "role": "assistant",
                            "content": message.content or "",
                            "tool_calls": [
                                {
                                    "id": tc.id,
                                    "type": "function",
                                    "function": {
                                        "name": tc.function.name,
                                        "arguments": tc.function.arguments,
                                    },
                                }
                                for tc in client_tool_calls
                            ],
                        }
                    )
                    for tc in client_tool_calls:
                        try:
                            arguments = json.loads(tc.function.arguments or "{}")
                            content = await _call_mcp_tool(tc.function.name, arguments)
                        except Exception as tool_error:
                            content = f"tool error: {tool_error}"
                        messages.append(
                            {
                                "role": "tool",
                                "tool_call_id": tc.id,
                                "content": content,
                            }
                        )
                    continue
                final_text = message.content or ""
                break

            for piece in final_text.split(" "):
                yield f"data: {json.dumps({'delta': piece + ' '})}\n\n"
            yield "data: [DONE]\n\n"
        except Exception as error:
            yield f"data: {json.dumps({'error': str(error)})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


if __name__ == "__main__":
    import uvicorn

    host = os.getenv("AGENT_HOST", "127.0.0.1")
    port = int(os.getenv("AGENT_PORT", "8000"))
    uvicorn.run(app, host=host, port=port)
