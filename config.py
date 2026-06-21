"""Shared config.yaml loading."""

from pathlib import Path

import yaml

CONFIG_PATH = Path(__file__).parent / "config.yaml"

_config: dict | None = None


def load_config() -> dict:
    global _config
    if _config is None:
        with open(CONFIG_PATH) as f:
            _config = yaml.safe_load(f)
    return _config


def get_anthropic_api_key() -> str:
    api_key = load_config().get("anthropic", {}).get("api_key")
    if not api_key:
        raise ValueError(
            "anthropic.api_key is not set in config.yaml. "
            "Copy config.example.yaml to config.yaml and fill it in."
        )
    return api_key
