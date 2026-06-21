import yaml
from pathlib import Path
import anthropic
from config import get_anthropic_api_key
from models.schemas import ParsedJD, StoryMatch, MatchResult
from models.utils import parse_json_response

MODEL = "claude-sonnet-4-6"

SYSTEM = """You are an expert career advisor. You match a candidate's STAR stories to job requirements.
Do not invent anything new and do not combine STAR stories with resume bullets.
Always respond with valid JSON."""

PROMPT = """Given this job description and the candidate's STAR stories, score each story for relevance.

Job Requirements:
- Role: {role} at {company}
- Required skills: {required_skills}
- Key responsibilities: {responsibilities}
- Keywords: {keywords}

STAR Stories (YAML):
---
{stories_yaml}
---

For each story, return a JSON array of objects:
{{
  "story_id": string,
  "story_title": string,
  "relevance_score": float 0.0-1.0,
  "matched_keywords": [list of JD keywords this story demonstrates],
  "star_summary": string (1-2 sentence STAR summary optimized for this specific JD)
}}

Sort by relevance_score descending. Respond ONLY with the JSON array."""


def _load_stories(bank_path: Path) -> list[dict]:
    with open(bank_path) as f:
        return yaml.safe_load(f)["stories"]


def match_stories(jd: ParsedJD, bank_path: Path | None = None) -> MatchResult:
    if bank_path is None:
        bank_path = Path(__file__).parent.parent / "data" / "experience_bank.yaml"

    stories = _load_stories(bank_path)
    client = anthropic.Anthropic(api_key=get_anthropic_api_key())

    prompt = PROMPT.format(
        role=jd.role,
        company=jd.company,
        required_skills=", ".join(jd.required_skills),
        responsibilities="\n".join(f"- {r}" for r in jd.responsibilities),
        keywords=", ".join(jd.keywords),
        stories_yaml=yaml.dump(stories, default_flow_style=False),
    )

    with client.messages.stream(
        model=MODEL,
        max_tokens=4096,
        system=SYSTEM,
        messages=[{"role": "user", "content": prompt}],
    ) as stream:
        response = stream.get_final_message()

    if response.stop_reason == "max_tokens":
        print("    WARNING: story_matcher response was truncated (hit max_tokens)")

    text_blocks = [b for b in response.content if b.type == "text"]
    if not text_blocks:
        raise RuntimeError(
            f"story_matcher got no text block. stop_reason={response.stop_reason!r}, "
            f"content types={[b.type for b in response.content]}"
        )

    matches_data = parse_json_response(text_blocks[0].text)
    matches = [StoryMatch(**m) for m in matches_data]
    top_stories = matches[:3]

    return MatchResult(jd=jd, matches=matches, top_stories=top_stories)
