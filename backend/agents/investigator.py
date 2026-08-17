"""Bounded LLM-led investigation using only read-only CockroachDB MCP tools."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from backend.agents.llm_client import LLMClient
from backend.agents.mcp_client import (
    READ_ONLY_MCP_TOOLS,
    READ_ONLY_TOOL_NAMES,
    call_mcp_tool,
)
from backend.schemas.alert import Alert

INVESTIGATOR_PROMPT_PATH = Path(__file__).with_name("prompts") / "investigator_system.md"
MAX_TOOL_CALL_ROUNDS = 5


def agentic_investigation(alert: Alert, signature: str) -> dict:
    """Synchronously run the bounded async investigation loop."""
    return asyncio.run(_investigate(alert, signature))


async def _investigate(alert: Alert, signature: str) -> dict:
    llm = LLMClient()
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": INVESTIGATOR_PROMPT_PATH.read_text(encoding="utf-8")},
        {
            "role": "user",
            "content": json.dumps(
                {"signature": signature, "alert": alert.model_dump()}, default=str
            ),
        },
    ]
    tool_calls_made: list[tuple[str, dict]] = []
    raw_results: list[dict] = []

    for _ in range(MAX_TOOL_CALL_ROUNDS):
        response = llm.client.chat.completions.create(
            model=llm.config["model"],
            messages=messages,
            tools=READ_ONLY_MCP_TOOLS,
            max_completion_tokens=llm.config["max_completion_tokens"],
            reasoning_effort=llm.config["reasoning_effort"],
        )
        message = response.choices[0].message
        tool_calls = message.tool_calls or []
        if not tool_calls:
            return {
                "source": "agentic",
                "findings": message.content or "",
                "tool_calls_made": tool_calls_made,
                "raw_results": raw_results,
                "service": alert.service,
            }

        messages.append(message.model_dump(exclude_none=True))
        for tool_call in tool_calls:
            tool_name = tool_call.function.name
            try:
                arguments = json.loads(tool_call.function.arguments)
                if not isinstance(arguments, dict):
                    raise ValueError("Tool arguments must be a JSON object.")
            except (json.JSONDecodeError, ValueError) as exc:
                result: dict = {"error": f"Invalid tool arguments: {exc}"}
            else:
                if tool_name not in READ_ONLY_TOOL_NAMES:
                    result = {"error": f"Tool {tool_name!r} is not permitted."}
                else:
                    result = await call_mcp_tool(tool_name, arguments)
                    tool_calls_made.append((tool_name, arguments))
                    raw_results.append(result)
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": json.dumps(result, default=str),
                }
            )

    messages.append(
        {
            "role": "user",
            "content": "The tool-call limit has been reached. Summarize the findings from the evidence above.",
        }
    )
    response = llm.client.chat.completions.create(
        model=llm.config["model"],
        messages=messages,
        max_completion_tokens=llm.config["max_completion_tokens"],
        reasoning_effort=llm.config["reasoning_effort"],
    )
    message = response.choices[0].message
    return {
        "source": "agentic",
        "findings": message.content or "",
        "tool_calls_made": tool_calls_made,
        "raw_results": raw_results,
        "service": alert.service,
    }
