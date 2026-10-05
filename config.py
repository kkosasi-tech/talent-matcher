"""Shared config.yaml loading."""

import os
from pathlib import Path

import yaml

CONFIG_PATH = Path(__file__).parent / "config.yaml"

_DEFAULT_MODEL = "claude-sonnet-4-6"
_DEFAULT_RESUME_WORD_MIN = 500
_DEFAULT_RESUME_WORD_MAX = 700
_DEFAULT_OLLAMA_BASE_URL = "http://localhost:11434"
_DEFAULT_OLLAMA_MODEL = "qwen2.5:14b"
_DEFAULT_OLLAMA_TIMEOUT = 600

_config: dict | None = None


def load_config() -> dict:
    global _config
    if _config is None:
        with open(CONFIG_PATH) as f:
            _config = yaml.safe_load(f)
    return _config


def get_anthropic_api_key() -> str:
    env_key = os.environ.get("ANTHROPIC_API_KEY")
    if env_key:
        return env_key
    api_key = load_config().get("anthropic", {}).get("api_key")
    if not api_key:
        raise ValueError(
            "No Anthropic API key found. Set the ANTHROPIC_API_KEY environment variable "
            "or set anthropic.api_key in config.yaml."
        )
    return api_key


def get_model() -> str:
    return load_config().get("pipeline", {}).get("model", _DEFAULT_MODEL)


def get_llm_provider() -> str:
    provider = (load_config().get("llm", {}).get("provider") or "anthropic").lower()
    if provider not in ("anthropic", "ollama"):
        raise ValueError(
            f"llm.provider must be 'anthropic' or 'ollama', got {provider!r}"
        )
    return provider


def get_ollama_base_url() -> str:
    return load_config().get("llm", {}).get(
        "ollama_base_url", _DEFAULT_OLLAMA_BASE_URL
    ).rstrip("/")


def get_ollama_model() -> str:
    env_model = os.environ.get("OLLAMA_MODEL")
    if env_model:
        return env_model
    return load_config().get("llm", {}).get("ollama_model", _DEFAULT_OLLAMA_MODEL)


def get_ollama_timeout() -> int:
    return int(
        load_config()
        .get("llm", {})
        .get("ollama_timeout", _DEFAULT_OLLAMA_TIMEOUT)
    )


def get_resume_word_count_range() -> tuple[int, int]:
    pipeline_cfg = load_config().get("pipeline", {})
    return (
        pipeline_cfg.get("resume_word_count_min", _DEFAULT_RESUME_WORD_MIN),
        pipeline_cfg.get("resume_word_count_max", _DEFAULT_RESUME_WORD_MAX),
    )
