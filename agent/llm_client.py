"""Thin OpenAI-compatible client for the LLM gateway.

Usage (same interface as the course snippet):

    from llm_client import build_llm_client
    llm = build_llm_client()                  # reads LLM_BASE_URL / LLM_API_KEY
    text = llm.complete(MODEL, messages, max_tokens=300, timeout=60)
    for token in llm.chat_stream(MODEL, messages, max_tokens=300): ...
    print(llm.last_usage)

`chat_tools` adds OpenAI-style function calling, used by the LangGraph agent.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Iterator

from openai import OpenAI


@dataclass
class LLMClient:
    client: OpenAI
    last_usage: dict | None = field(default=None)

    def _record_usage(self, usage: Any) -> None:
        if usage is None:
            return
        self.last_usage = {
            "prompt_tokens": getattr(usage, "prompt_tokens", None),
            "completion_tokens": getattr(usage, "completion_tokens", None),
            "total_tokens": getattr(usage, "total_tokens", None),
        }

    def complete(self, model: str, messages: list[dict], max_tokens: int = 800,
                 timeout: float = 60, temperature: float = 0.2, **kwargs) -> str:
        resp = self.client.chat.completions.create(
            model=model, messages=messages, max_tokens=max_tokens,
            temperature=temperature, timeout=timeout, **kwargs)
        self._record_usage(resp.usage)
        return resp.choices[0].message.content or ""

    def chat_tools(self, model: str, messages: list[dict], tools: list[dict],
                   max_tokens: int = 800, timeout: float = 60, temperature: float = 0.0):
        """One function-calling turn. Returns the assistant message object."""
        resp = self.client.chat.completions.create(
            model=model, messages=messages, tools=tools, tool_choice="auto",
            max_tokens=max_tokens, temperature=temperature, timeout=timeout)
        self._record_usage(resp.usage)
        return resp.choices[0].message

    def chat_stream(self, model: str, messages: list[dict], max_tokens: int = 800,
                    timeout: float = 120, temperature: float = 0.2) -> Iterator[str]:
        stream = self.client.chat.completions.create(
            model=model, messages=messages, max_tokens=max_tokens,
            temperature=temperature, timeout=timeout, stream=True,
            stream_options={"include_usage": True})
        for chunk in stream:
            if getattr(chunk, "usage", None):
                self._record_usage(chunk.usage)
            if chunk.choices and chunk.choices[0].delta and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content


def build_llm_client() -> LLMClient:
    base_url = os.environ["LLM_BASE_URL"].rstrip("/")
    if not base_url.endswith("/v1"):
        base_url = base_url + "/v1"
    return LLMClient(client=OpenAI(base_url=base_url, api_key=os.environ["LLM_API_KEY"], max_retries=2))
