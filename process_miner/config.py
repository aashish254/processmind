"""Configuration: LLM provider selection, engine choice, output locations.

Everything is driven by environment variables so the pipeline can run
fully offline (deterministic rule engine) or with a hosted LLM without
any code changes.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field


class LLMConfig(BaseModel):
    provider: str = "none"  # "openai" | "anthropic" | "none"
    model: str = ""
    api_key: str = ""
    base_url: str = ""
    temperature: float = 0.0
    max_retries: int = 2
    timeout_seconds: int = 180

    @property
    def enabled(self) -> bool:
        return self.provider in ("openai", "anthropic") and bool(self.api_key)


class Settings(BaseModel):
    engine: str = "auto"  # "auto" | "builtin" | "langgraph"
    output_dir: Path = Path("outputs")
    llm: LLMConfig = Field(default_factory=LLMConfig)
    apply_optimizations: bool = True
    dfg_threshold_ratio: float = 0.1  # min share of max edge freq kept in DFG
    max_repair_attempts: int = 2


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def load_settings() -> Settings:
    """Build settings from the environment (PM_* / provider standard vars)."""
    provider = _env("PM_LLM_PROVIDER", "").lower()
    api_key = _env("OPENAI_API_KEY") or _env("ANTHROPIC_API_KEY")

    if not provider:
        if _env("OPENAI_API_KEY"):
            provider = "openai"
        elif _env("ANTHROPIC_API_KEY"):
            provider = "anthropic"
        else:
            provider = "none"

    model = _env("PM_LLM_MODEL", "")
    if not model:
        model = {"openai": "gpt-4o-mini", "anthropic": "claude-3-5-haiku-latest"}.get(provider, "")
    base_url = _env("PM_LLM_BASE_URL") or _env("OPENAI_BASE_URL")
    if provider == "anthropic" and not base_url:
        base_url = "https://api.anthropic.com"

    engine = _env("PM_ENGINE", "auto").lower()
    out_dir = Path(_env("PM_OUTPUT_DIR", "outputs"))

    return Settings(
        engine=engine,
        output_dir=out_dir,
        llm=LLMConfig(
            provider=provider,
            model=model,
            api_key=_env("OPENAI_API_KEY") if provider == "openai" else _env("ANTHROPIC_API_KEY"),
            base_url=base_url,
        ),
    )


def resolve_engine(engine: str) -> str:
    """Resolve 'auto' to the best available orchestration engine."""
    if engine != "auto":
        return engine
    try:
        import langgraph  # noqa: F401

        return "langgraph"
    except ImportError:
        return "builtin"
