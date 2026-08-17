"""Read-only MCP access to CockroachDB Cloud."""

from __future__ import annotations

import json
import os
import ssl
from typing import Any

import certifi
import httpx2
from mcp import Client
from mcp.client.streamable_http import streamable_http_client

from backend.orchestration.config import get_config

READ_ONLY_MCP_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "select_query",
            "description": "Run a read-only SQL query. Only SELECT statements are allowed.",
            "parameters": {
                "type": "object",
                "properties": {
                    "database": {"type": "string"},
                    "query": {"type": "string", "description": "SELECT statement only"},
                },
                "required": ["database", "query"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_tables",
            "description": "List tables available in the current cluster.",
            "parameters": {
                "type": "object",
                "properties": {"database": {"type": "string"}},
                "required": ["database"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_table_schema",
            "description": "Get the schema for a named table.",
            "parameters": {
                "type": "object",
                "properties": {
                    "database": {"type": "string"},
                    "table": {"type": "string"},
                    "schema": {"type": "string", "description": "defaults to public"},
                },
                "required": ["database", "table"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "show_running_queries",
            "description": "Show currently running queries in the cluster.",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_cluster",
            "description": "Get live cluster metadata and status.",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        },
    },
]
READ_ONLY_TOOL_NAMES = {spec["function"]["name"] for spec in READ_ONLY_MCP_TOOLS}


async def call_mcp_tool(tool_name: str, arguments: dict) -> dict:
    """Call one MCP tool and decode its first JSON text content block."""
    api_key = os.environ.get("COCKROACH_MCP_API_KEY")
    cluster_id = os.environ.get("COCKROACH_MCP_CLUSTER_ID")
    if not api_key:
        raise RuntimeError("COCKROACH_MCP_API_KEY is required for MCP calls.")
    if not cluster_id:
        raise RuntimeError("COCKROACH_MCP_CLUSTER_ID is required for MCP calls.")

    ssl_context = ssl.create_default_context(cafile=certifi.where())
    headers = {
        "Authorization": f"Bearer {api_key}",
        "mcp-cluster-id": cluster_id,
    }
    async with httpx2.AsyncClient(
        headers=headers,
        verify=ssl_context,
        follow_redirects=True,
    ) as http_client:
        transport = streamable_http_client(get_config()["mcp"]["url"], http_client=http_client)
        async with Client(transport) as client:
            result = await client.call_tool(tool_name, arguments)

    content = getattr(result, "content", None) or []
    text = getattr(content[0], "text", None) if content else None
    if not text:
        return {}
    parsed: Any = json.loads(text)
    return parsed if isinstance(parsed, dict) else {"data": parsed}
