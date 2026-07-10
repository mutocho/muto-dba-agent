import os
from contextlib import AsyncExitStack, asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from pydantic import BaseModel

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

# MCP 상태 (lifespan에서 채운다)
mcp_state = {"session": None, "tools": []}


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


class CallRequest(BaseModel):
    name: str
    arguments: dict = {}


@app.get("/")
def health():
    return {"status": "ok", "mcp_tools": len(mcp_state["tools"])}


@app.get("/tools")
def list_tools():
    return [
        {
            "name": tool.name,
            "description": tool.description or "",
            "inputSchema": tool.inputSchema,
        }
        for tool in mcp_state["tools"]
    ]


@app.post("/call")
async def call_tool(request: CallRequest):
    session = mcp_state["session"]
    if session is None:
        return {"content": "tool error: MCP 세션을 사용할 수 없습니다"}
    result = await session.call_tool(request.name, request.arguments)
    content = "".join(getattr(block, "text", "") for block in result.content)
    return {"content": content}


if __name__ == "__main__":
    import uvicorn

    host = os.getenv("MCP_ROUTER_HOST", "127.0.0.1")
    port = int(os.getenv("MCP_ROUTER_PORT", "8010"))
    uvicorn.run(app, host=host, port=port)
