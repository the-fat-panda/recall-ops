# PROBE — throwaway. Shows raw select_query result shape. Run live.

import asyncio

from backend.agents.mcp_client import call_mcp_tool


def main() -> None:
    select_result = asyncio.run(
        call_mcp_tool(
            "select_query",
            {
                "database": "defaultdb",
                "query": "SELECT a.action, a.result FROM defaultdb.public.attempts a JOIN defaultdb.public.incidents i ON a.incident_id = i.id WHERE i.signature = 'CrashLoopBackOff' ORDER BY a.created_at DESC LIMIT 5",
            },
        )
    )
    print(f"select_query result: {select_result}")
    tables_result = asyncio.run(call_mcp_tool("list_tables", {"database": "defaultdb"}))
    print(f"list_tables result: {tables_result}")


if __name__ == "__main__":
    main()
