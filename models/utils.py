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

    # Models sometimes prefix/suffix the JSON with narration despite instructions
    # not to. Locate the first object/array start and decode from there, ignoring
    # any trailing text after the matching close.
    if text[0] not in "{[":
        match = re.search(r"[{\[]", text)
        if not match:
            raise ValueError(f"No JSON object or array found in model response: {text[:200]!r}")
        text = text[match.start():]

    return json.JSONDecoder().raw_decode(text)[0]
