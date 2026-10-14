import asyncio
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


def test_stdio_protocol():
    async def run():
        parameters = StdioServerParameters(command=sys.executable, args=["-m", "rt_music.server"])
        async with (
            stdio_client(parameters) as (read, write),
            ClientSession(read, write) as session,
        ):
            await session.initialize()
            tools = await session.list_tools()
            names = {t.name for t in tools.tools}
            assert {"search_music", "play_music", "playback_status", "edit_queue", "auth_status", "import_simpmusic_auth"} <= names
            auth_tool = next(tool for tool in tools.tools if tool.name == "import_simpmusic_auth")
            assert set(auth_tool.inputSchema["properties"]) == {"force", "auth_user"}
            result = await session.call_tool("playback_status", {})
            assert not result.isError
            result = await session.call_tool("play_music", {"video_id": "../invalid"})
            assert result.isError
    asyncio.run(run())
