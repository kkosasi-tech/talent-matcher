import json
import re


def parse_json_response(raw: str) -> dict | list:
    """Parse JSON from a model response, stripping markdown fences if present."""
    text = raw.strip()

    if not text:
        raise ValueError("Model returned an empty response")

    # Strip ```json ... ``` or ``` ... ``` fences
    fenced = re.match(r"^```(?:json)?\s*\n?(.*?)\n?```\s*$", text, re.DOTALL)
    if fenced:
        text = fenced.group(1).strip()

    if not text:
        raise ValueError("Model returned empty content (response was likely truncated by max_tokens)")

    return json.loads(text)
