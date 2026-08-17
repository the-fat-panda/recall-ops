# PROBE — throwaway. Proves non-interactive MCP auth to CockroachDB Cloud. Run live.

import asyncio
import os
import ssl

import certifi
import httpx2
from mcp import Client
from mcp.client.streamable_http import streamable_http_client

MCP_URL = "https://cockroachlabs.cloud/mcp"


async def probe() -> None:
    api_key = os.environ.get("COCKROACH_MCP_API_KEY")
    cluster_id = os.environ.get("COCKROACH_MCP_CLUSTER_ID")
    if not api_key:
        raise RuntimeError("COCKROACH_MCP_API_KEY is required for the MCP auth probe.")
    if not cluster_id:
        raise RuntimeError("COCKROACH_MCP_CLUSTER_ID is required for the MCP auth probe.")

    headers = {
        "Authorization": f"Bearer {api_key}",
        "mcp-cluster-id": cluster_id,
    }
    ssl_context = ssl.create_default_context(cafile=certifi.where())
    try:
        async with httpx2.AsyncClient(
            headers=headers,
            verify=ssl_context,
            follow_redirects=True,
        ) as http_client:
            transport = streamable_http_client(MCP_URL, http_client=http_client)
            async with Client(transport) as client:
                tools = await client.list_tools()
                print(f"available_tools: {[tool.name for tool in tools.tools]}")
                result = await client.call_tool("list_databases", {})
                print(f"list_databases result: {result}")
    except Exception as exc:
        response = getattr(exc, "response", None)
        status_code = getattr(response, "status_code", None)
        print(f"MCP probe failed (status={status_code}): {exc}")
        if status_code in (401, 403):
            print("Auth failed: the service account may need Cluster Operator or Cluster Admin.")


if __name__ == "__main__":
    asyncio.run(probe())
