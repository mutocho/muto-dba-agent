import json
import os
from contextlib import AsyncExitStack, asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from openai import AsyncOpenAI
from pydantic import BaseModel

load_dotenv()

MODEL_NAME = os.getenv("MODEL_NAME")
MAX_TOOL_ITERATIONS = 8

client = AsyncOpenAI(
    base_url=os.getenv("OPENAI_BASE_URL"),
    api_key=os.getenv("OPENAI_API_KEY"),
)

# MCP 상태 (lifespan에서 채운다)
mcp_state = {"session": None, "tools": []}


def _to_openai_tools(mcp_tools):
    return [
        {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description or "",
                "parameters": tool.inputSchema,
            },
        }
        for tool in mcp_tools
    ]


@asynccontextmanager
async def lifespan(app: FastAPI):
    stack = AsyncExitStack()
    try:
        server_params = StdioServerParameters(
            command="npx",
            args=["-y", "@notionhq/notion-mcp-server"],
            env=os.environ.copy(),
        )
        read, write = await stack.enter_async_context(stdio_client(server_params))
        session = await stack.enter_async_context(ClientSession(read, write))
        await session.initialize()
        tools_result = await session.list_tools()
        mcp_state["session"] = session
        mcp_state["tools"] = tools_result.tools
        print(f"MCP 연결됨: 도구 {len(tools_result.tools)}개 로드")
    except Exception as error:
        print(f"MCP 연결 실패(도구 없이 계속): {error!r}")
    try:
        yield
    finally:
        await stack.aclose()


app = FastAPI(lifespan=lifespan)


class ChatRequest(BaseModel):
    messages: list[dict]


@app.get("/")
def health():
    return {"status": "ok", "mcp_tools": len(mcp_state["tools"])}


async def _call_mcp_tool(name, arguments):
    session = mcp_state["session"]
    result = await session.call_tool(name, arguments)
    return "".join(getattr(block, "text", "") for block in result.content)


@app.post("/chat")
async def chat(request: ChatRequest):
    tools = _to_openai_tools(mcp_state["tools"]) if mcp_state["tools"] else None

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
                if message.tool_calls:
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
                                for tc in message.tool_calls
                            ],
                        }
                    )
                    for tc in message.tool_calls:
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
