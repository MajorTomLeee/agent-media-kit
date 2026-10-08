import asyncio
import json
import sys

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from test_core import media  # noqa: F401

from media_eyes.download import PublicSocket, media_filter


def test_private_socket_blocked():
    with PublicSocket() as sock, pytest.raises(OSError, match="Private"):
        sock.connect(("127.0.0.1", 80))


def test_download_protocols():
    assert media_filter({"protocol": "https"}) is None
    assert media_filter({"protocol": "m3u8_native"}) is None
    for protocol in ("rtmp", "rtsp", "m3u8", "file"):
        assert media_filter({"protocol": protocol}) is not None
    assert media_filter({"is_live": True}) is not None


def test_real_mcp_images(media, tmp_path):  # noqa: F811
    _, _, path = media

    async def observe():
        params = StdioServerParameters(
            command=sys.executable,
            args=[
                "-m",
                "media_eyes.server",
                "--cache-dir",
                str(tmp_path / "mcp-cache"),
                "--allow-root",
                str(tmp_path),
            ],
        )
        async with stdio_client(params) as (reader, writer):  # noqa: SIM117
            async with ClientSession(reader, writer) as session:
                await session.initialize()
                tools = await session.list_tools()
                assert len(tools.tools) == 6
                opened = await session.call_tool("open_media", {"source": str(path)})
                assert not opened.isError
                identity = json.loads(opened.content[0].text)["media_id"]
                result = await session.call_tool(
                    "inspect_segment", {"media_id": identity, "start": 0, "end": 2, "count": 2}
                )
                assert not result.isError
                assert [item.type for item in result.content] == ["text", "image", "text", "image"]

    asyncio.run(observe())
