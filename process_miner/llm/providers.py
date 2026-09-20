"""LLM provider abstraction.

Design goals:
* The pipeline must run fully offline - providers are optional.
* Any OpenAI-compatible endpoint works (OpenAI, Azure-style gateways,
  OpenRouter, LM Studio, Ollama's /v1 shim, ...).
* Anthropic's native Messages API is supported directly.
* JSON extraction is defensive: strips code fences, finds the outermost
  JSON object, repairs trailing commas.
"""

from __future__ import annotations

import json
import re
import ssl
import urllib.error
import urllib.request
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

from pydantic import BaseModel

from process_miner.config import LLMConfig


class LLMError(RuntimeError):
    pass


def extract_json(text: str) -> Dict[str, Any]:
    """Pull the outermost JSON object out of an LLM response defensively."""
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass
    start = cleaned.find("{")
    if start == -1:
        raise LLMError("No JSON object found in model response")
    depth = 0
    end = -1
    for i in range(start, len(cleaned)):
        ch = cleaned[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                break
    candidate = cleaned[start:end]
    candidate = re.sub(r",\s*([}\]])", r"\1", candidate)  # trailing commas
    try:
        return json.loads(candidate)
    except json.JSONDecodeError as exc:
        raise LLMError(f"Model returned unparseable JSON: {exc}") from exc


class LLMProvider(ABC):
    name: str = "base"

    @abstractmethod
    def complete_json(self, system: str, user: str) -> Dict[str, Any]:
        """Return a parsed JSON object for the given prompt."""

    def health(self) -> str:
        return f"{self.name}: ready"


class OpenAICompatProvider(LLMProvider):
    """Works with any OpenAI-compatible /chat/completions endpoint."""

    name = "openai-compatible"

    def __init__(self, cfg: LLMConfig):
        self.cfg = cfg

    def complete_json(self, system: str, user: str) -> Dict[str, Any]:
        payload = {
            "model": self.cfg.model,
            "temperature": self.cfg.temperature,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        body = json.dumps(payload).encode()
        url = (self.cfg.base_url or "https://api.openai.com/v1").rstrip("/") + "/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.cfg.api_key}",
        }
        last_err: Optional[Exception] = None
        for attempt in range(self.cfg.max_retries + 1):
            try:
                req = urllib.request.Request(url, data=body, headers=headers, method="POST")
                with urllib.request.urlopen(req, timeout=self.cfg.timeout_seconds) as resp:
                    data = json.loads(resp.read().decode())
                content = data["choices"][0]["message"]["content"]
                return extract_json(content)
            except (urllib.error.URLError, urllib.error.HTTPError, KeyError, IndexError, json.JSONDecodeError, ssl.SSLError, TimeoutError) as exc:
                last_err = exc
                continue
        raise LLMError(f"OpenAI-compatible request failed after retries: {last_err}")


class AnthropicProvider(LLMProvider):
    """Anthropic native Messages API."""

    name = "anthropic"

    def __init__(self, cfg: LLMConfig):
        self.cfg = cfg

    def complete_json(self, system: str, user: str) -> Dict[str, Any]:
        payload = {
            "model": self.cfg.model,
            "max_tokens": 4096,
            "temperature": self.cfg.temperature,
            "system": system,
            "messages": [{"role": "user", "content": user}],
        }
        body = json.dumps(payload).encode()
        url = (self.cfg.base_url or "https://api.anthropic.com").rstrip("/") + "/v1/messages"
        headers = {
            "Content-Type": "application/json",
            "x-api-key": self.cfg.api_key,
            "anthropic-version": "2023-06-01",
        }
        last_err: Optional[Exception] = None
        for attempt in range(self.cfg.max_retries + 1):
            try:
                req = urllib.request.Request(url, data=body, headers=headers, method="POST")
                with urllib.request.urlopen(req, timeout=self.cfg.timeout_seconds) as resp:
                    data = json.loads(resp.read().decode())
                content = data["content"][0]["text"]
                return extract_json(content)
            except (urllib.error.URLError, urllib.error.HTTPError, KeyError, IndexError, json.JSONDecodeError, ssl.SSLError, TimeoutError) as exc:
                last_err = exc
                continue
        raise LLMError(f"Anthropic request failed after retries: {last_err}")


def build_provider(cfg: LLMConfig) -> Optional[LLMProvider]:
    """Factory: returns None when no usable provider is configured."""
    if not cfg.enabled:
        return None
    if cfg.provider == "openai":
        return OpenAICompatProvider(cfg)
    if cfg.provider == "anthropic":
        return AnthropicProvider(cfg)
    return None


__all__ = [
    "LLMProvider",
    "LLMError",
    "OpenAICompatProvider",
    "AnthropicProvider",
    "build_provider",
    "extract_json",
]
