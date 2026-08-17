"""Thin OpenAI-compatible client for the Bedrock Mantle endpoint."""

from __future__ import annotations

import os

from openai import OpenAI

from backend.orchestration.config import get_config


class LLMClient:
    def __init__(self) -> None:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is required for LLM calls.")
        self.config = get_config()["llm"]
        self.client = OpenAI(
            base_url=self.config["base_url"],
            api_key=api_key,
            default_headers={"OpenAI-Project": self.config["project_id"]},
        )

    def complete(self, system_prompt: str, user_content: str) -> str:
        request = {
            "model": self.config["model"],
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
        }
        try:
            response = self.client.chat.completions.create(
                **request,
                max_completion_tokens=self.config["max_completion_tokens"],
                reasoning_effort=self.config["reasoning_effort"],
            )
        except TypeError:
            try:
                response = self.client.chat.completions.create(
                    **request,
                    max_completion_tokens=self.config["max_completion_tokens"],
                )
                print("LLM client request succeeded without reasoning_effort.")
            except TypeError:
                response = self.client.chat.completions.create(
                    **request,
                    max_tokens=self.config["max_completion_tokens"],
                )
                print("LLM client request succeeded with max_tokens and without reasoning_effort.")
        message = response.choices[0].message
        return message.content or getattr(message, "reasoning", None) or ""
