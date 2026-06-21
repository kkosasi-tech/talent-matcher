import anthropic
from config import get_anthropic_api_key
from models.schemas import MatchResult, Score
from models.utils import parse_json_response

MODEL = "claude-sonnet-4-6"
THRESHOLD = 60

SYSTEM = """You are an expert recruiter and career advisor. Score candidate-job fit objectively.
Always respond with valid JSON."""

PROMPT = """Score this candidate's fit for the role on a scale of 0-100.

Job: {role} at {company}
Required skills: {required_skills}
Preferred skills: {preferred_skills}
Seniority expected: {seniority_level}

Top matched stories:
{story_summaries}

Return JSON with:
{{
  "overall": int 0-100,
  "skill_match": int 0-100 (how well required/preferred skills are covered),
  "experience_relevance": int 0-100 (how relevant the STAR stories are to responsibilities),
  "seniority_fit": int 0-100 (does experience level match expectations),
  "rationale": string (2-3 sentences explaining the score and key gaps)
}}

Respond ONLY with the JSON object."""


def score_match(match: MatchResult, threshold: int = THRESHOLD) -> Score:
    client = anthropic.Anthropic(api_key=get_anthropic_api_key())

    story_summaries = "\n".join(
        f"- [{s.relevance_score:.2f}] {s.story_title}: {s.star_summary}"
        for s in match.top_stories
    )

    prompt = PROMPT.format(
        role=match.jd.role,
        company=match.jd.company,
        required_skills=", ".join(match.jd.required_skills),
        preferred_skills=", ".join(match.jd.preferred_skills),
        seniority_level=match.jd.seniority_level,
        story_summaries=story_summaries,
    )

    with client.messages.stream(
        model=MODEL,
        max_tokens=1024,
        system=SYSTEM,
        messages=[{"role": "user", "content": prompt}],
    ) as stream:
        response = stream.get_final_message()

    if response.stop_reason == "max_tokens":
        print("    WARNING: scorer response was truncated (hit max_tokens)")

    text_blocks = [b for b in response.content if b.type == "text"]
    if not text_blocks:
        raise RuntimeError(
            f"scorer got no text block. stop_reason={response.stop_reason!r}, "
            f"content types={[b.type for b in response.content]}"
        )

    data = parse_json_response(text_blocks[0].text)
    data["proceed"] = data["overall"] >= threshold
    return Score(**data)
