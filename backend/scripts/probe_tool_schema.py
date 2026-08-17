# PROBE — throwaway. Dumps real MCP tool input schemas from the server. Run live.

import asyncio
import os
import ssl

import certifi
import httpx2
from mcp import Client
from mcp.client.streamable_http import streamable_http_client

from backend.orchestration.config import get_config


async def probe() -> None:
    api_key = os.environ.get("COCKROACH_MCP_API_KEY")
    cluster_id = os.environ.get("COCKROACH_MCP_CLUSTER_ID")
    if not api_key:
        raise RuntimeError("COCKROACH_MCP_API_KEY is required for the MCP schema probe.")
    if not cluster_id:
        raise RuntimeError("COCKROACH_MCP_CLUSTER_ID is required for the MCP schema probe.")

    ssl_context = ssl.create_default_context(cafile=certifi.where())
    async with httpx2.AsyncClient(
        headers={
            "Authorization": f"Bearer {api_key}",
            "mcp-cluster-id": cluster_id,
        },
        verify=ssl_context,
        follow_redirects=True,
    ) as http_client:
        transport = streamable_http_client(get_config()["mcp"]["url"], http_client=http_client)
        async with Client(transport) as client:
            tools = await client.list_tools()

    for tool in tools.tools:
        print(f"=== {tool.name} ===")
        schema = getattr(tool, "inputSchema", None) or getattr(tool, "input_schema", None)
        if schema is not None:
            print(schema)
        elif hasattr(tool, "model_dump"):
            print(tool.model_dump(by_alias=True))
        else:
            print(tool)


if __name__ == "__main__":
    asyncio.run(probe())
