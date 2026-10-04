from pathlib import Path

from testomation.config import Settings


def test_defaults():
    s = Settings.from_env({})
    assert s.ollama_url == "http://localhost:11434/v1"
    assert s.models.embed == "nomic-embed-text"
    assert s.trace_dir == Path("data/traces")
    assert s.langfuse_host is None


def test_large_tier_falls_back_to_small():
    s = Settings.from_env({"TESTO_MODEL_SMALL": "qwen3:4b"})
    assert s.models.large == "qwen3:4b"


def test_large_tier_can_be_set():
    s = Settings.from_env({"TESTO_MODEL_SMALL": "a", "TESTO_MODEL_LARGE": "b"})
    assert s.models.large == "b"
