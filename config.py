"""Shared config.yaml loading."""

import os
from pathlib import Path

import yaml

CONFIG_PATH = Path(__file__).parent / "config.yaml"

_DEFAULT_MODEL = "claude-sonnet-4-6"

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
