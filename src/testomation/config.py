"""Settings from the environment (TESTO_*, LANGFUSE_*). See .env.example."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ModelTiers:
    small: str
    large: str  # defaults to the small model until the benchmark earns it a place (D15)
    vision: str
    embed: str


@dataclass(frozen=True)
class Settings:
    database_url: str
    ollama_url: str
    models: ModelTiers
    budget_calls: int
    budget_seconds: int
    target_url: str
    trace_dir: Path
    langfuse_host: str | None

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> Settings:
        env = os.environ if env is None else env

        def get(name: str, default: str = "") -> str:
            return env.get(name) or default

        small = get("TESTO_MODEL_SMALL")
        return cls(
            database_url=get(
                "TESTO_DATABASE_URL",
                "postgresql://testomation:testomation@localhost:5432/testomation",
            ),
            ollama_url=get("TESTO_OLLAMA_URL", "http://localhost:11434/v1"),
            models=ModelTiers(
                small=small,
                large=get("TESTO_MODEL_LARGE", small),
                vision=get("TESTO_MODEL_VISION"),
                embed=get("TESTO_MODEL_EMBED", "nomic-embed-text"),
            ),
            budget_calls=int(get("TESTO_BUDGET_CALLS", "200")),
            budget_seconds=int(get("TESTO_BUDGET_SECONDS", "1800")),
            target_url=get("TESTO_TARGET_URL", "http://localhost:4100"),
            trace_dir=Path(get("TESTO_TRACE_DIR", "data/traces")),
            langfuse_host=get("LANGFUSE_HOST") or None,
        )
