"""Unified LLM interface for all agents.

The backend is selected via config.yaml:

    llm:
      provider: anthropic        # or: ollama
      # ollama only (ignored when provider: anthropic):
      ollama_base_url: "http://localhost:11434"
      ollama_model: "qwen2.5:14b"

anthropic:
  api_key: "..."                 # or set ANTHROPIC_API_KEY
pipeline:
  model: "claude-sonnet-4-6"     # used when provider: anthropic

Every agent calls chat() instead of talking to a provider directly, so agents
stay provider-agnostic.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import anthropic
import requests

from config import (
    get_anthropic_api_key,
    get_llm_provider,
    get_model,
    get_ollama_base_url,
    get_ollama_model,
    get_ollama_timeout,
)


@dataclass
class ChatResponse:
    """Provider-agnostic result of a chat completion.

    - text:  the model's answer (what most agents parse JSON out of)
    - blocks: the answer split into text blocks (multi-block answers only
      happen with tool-calling providers, where earlier blocks are narration)
    - truncated: the response was cut off by the token limit
    - provider_content: provider-specific content blocks (Anthropic-only;
      used for web-search citations). Empty for Ollama.
    """

    text: str
    blocks: list[str] = field(default_factory=list)
    truncated: bool = False
    provider: str = ""
    provider_content: list = field(default_factory=list)


def chat(
    system: str,
    messages: list[dict],
    max_tokens: int = 4096,
    tools: list[dict] | None = None,
) -> ChatResponse:
    """Run a chat completion against the configured provider and return the text."""
    provider = get_llm_provider()
    if provider == "ollama":
        return _chat_ollama(system, messages, max_tokens, tools)
    return _chat_anthropic(system, messages, max_tokens, tools)


def _chat_anthropic(
    system: str,
    messages: list[dict],
    max_tokens: int,
    tools: list[dict] | None,
) -> ChatResponse:
    client = anthropic.Anthropic(api_key=get_anthropic_api_key())

    with client.messages.stream(
        model=get_model(),
        max_tokens=max_tokens,
        system=system,
        messages=messages,
        **({"tools": tools} if tools else {}),
    ) as stream:
        response = stream.get_final_message()

    blocks = [b.text for b in response.content if b.type == "text"]
    if not blocks:
        raise RuntimeError(
            f"Anthropic returned no text. stop_reason={response.stop_reason!r}, "
            f"content types={[b.type for b in response.content]}"
        )

    return ChatResponse(
        text="\n".join(blocks),
        blocks=blocks,
        truncated=response.stop_reason == "max_tokens",
        provider="anthropic",
        provider_content=list(response.content),
    )


def _chat_ollama(
    system: str,
    messages: list[dict],
    max_tokens: int,
    tools: list[dict] | None,
) -> ChatResponse:
    if tools:
        print(
            "    NOTE: provider is ollama — Anthropic web-search tools are not "
            "available, the model will answer from its own knowledge."
        )

    url = f"{get_ollama_base_url()}/api/chat"
    payload = {
        "model": get_ollama_model(),
        "system": system,
        "messages": messages,
        "stream": False,
        "options": {"num_predict": max_tokens},
    }

    try:
        resp = requests.post(url, json=payload, timeout=(10, get_ollama_timeout()))
    except requests.ConnectionError as e:
        raise RuntimeError(
            f"Could not reach Ollama at {url}. Is it running? ({e})"
        ) from e
    except requests.Timeout as e:
        raise RuntimeError(
            f"Ollama at {url} timed out after {get_ollama_timeout()}s "
            f"(increase llm.ollama_timeout in config.yaml for slow local models). ({e})"
        ) from e

    if resp.status_code >= 400:
        raise RuntimeError(f"Ollama request failed ({resp.status_code}): {resp.text}")

    data = resp.json()
    text = (data.get("message") or {}).get("content", "").strip()
    if not text:
        raise RuntimeError(
            f"Ollama ({get_ollama_model()}) returned no text: "
            f"{data.get('error') or 'unknown error — check `ollama ps` / `ollama list`'}"
        )

    return ChatResponse(
        text=text,
        blocks=[text],
        truncated=data.get("done_reason") == "length",
        provider="ollama",
    )
