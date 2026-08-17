# PROBE — throwaway. Tests the Bedrock mantle client alone. Run live.

from backend.agents.llm_client import LLMClient


def main() -> None:
    client = LLMClient()
    print(client.complete("You are a concise assistant.", "Reply with the single word: pong"))


if __name__ == "__main__":
    main()
