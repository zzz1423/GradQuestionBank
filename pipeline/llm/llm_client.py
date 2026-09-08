"""
Generic LLM client for OpenAI-compatible APIs.

Decoupled from any specific provider. Works with:
- LM Studio (http://127.0.0.1:1234/v1)
- Ollama (http://127.0.0.1:11434/v1)
- OpenAI (https://api.openai.com/v1)
- vLLM, TGI, any OpenAI-compatible endpoint

Design:
- No provider-specific logic
- No structured output / json_schema support (for max compatibility)
- Just send messages, get content back
- Caller is responsible for parsing/validating the content
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any


@dataclass
class LLMConfig:
    """Configuration for an LLM API endpoint."""
    api_url: str = "http://127.0.0.1:1234/v1/chat/completions"
    model: str = "qwen/qwen3.5-9b"
    api_key: str = ""
    temperature: float = 0.1
    max_tokens: int = 4000
    timeout: int = 120
    supports_json_schema: bool = True
    json_schema: dict | None = None  # Pydantic model JSON schema for structured output
    extra_body: dict[str, Any] = field(default_factory=dict)


@dataclass
class LLMResponse:
    """Raw response from an LLM API call."""
    content: str
    reasoning_content: str = ""
    finish_reason: str = ""
    raw: dict[str, Any] = field(default_factory=dict)


class LLMClient:
    """Stateless client for OpenAI-compatible chat completion APIs.

    Usage:
        client = LLMClient(LLMConfig(model="qwen/qwen3.5-9b"))
        response = client.chat(system="...", user="...")
    """

    def __init__(self, config: LLMConfig | None = None):
        self.config = config or LLMConfig()

    def chat(
        self,
        system: str,
        user: Any,
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
        json_schema: dict | None = None,
    ) -> LLMResponse:
        """Send a chat completion request.

        Args:
            system: System message content.
            user: User message content.
            temperature: Override config temperature.
            max_tokens: Override config max_tokens.

        Returns:
            LLMResponse with content and metadata.

        Raises:
            ConnectionError: If the API is unreachable.
            RuntimeError: If the API returns an error.
        """
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]

        payload: dict[str, Any] = {
            "model": self.config.model,
            "messages": messages,
            "temperature": temperature if temperature is not None else self.config.temperature,
            "max_tokens": max_tokens if max_tokens is not None else self.config.max_tokens,
        }

        # Use JSON schema mode for structured output (per-call override or config default)
        schema = json_schema or self.config.json_schema
        if schema and self.config.supports_json_schema:
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": schema,
            }

        # Merge any extra body params (for provider-specific features)
        if self.config.extra_body:
            payload.update(self.config.extra_body)

        try:
            headers = {"Content-Type": "application/json"}
            if self.config.api_key:
                headers["Authorization"] = f"Bearer {self.config.api_key}"
            req = urllib.request.Request(
                self.config.api_url,
                data=json.dumps(payload).encode("utf-8"),
                headers=headers,
            )
            resp = urllib.request.urlopen(req, timeout=self.config.timeout)
            data = json.loads(resp.read())
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", errors="replace")[:500]
            raise RuntimeError(
                f"LLM API HTTP {e.code} at {self.config.api_url}: {detail}"
            ) from e
        except urllib.error.URLError as e:
            raise ConnectionError(
                f"Cannot reach LLM API at {self.config.api_url}: {e}"
            ) from e

        if "error" in data:
            raise RuntimeError(f"LLM API error: {data['error']}")

        choice = data.get("choices", [{}])[0]
        message = choice.get("message", {})

        return LLMResponse(
            content=message.get("content", ""),
            reasoning_content=message.get("reasoning_content", ""),
            finish_reason=choice.get("finish_reason", ""),
            raw=data,
        )
