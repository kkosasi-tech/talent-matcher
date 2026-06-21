from pathlib import Path
import anthropic
from config import get_anthropic_api_key
from models.schemas import MatchResult, Score

MODEL = "claude-sonnet-4-6"

SYSTEM = """You are an expert resume writer. You tailor resumes to specific job descriptions
without fabricating experience. You reorder, emphasize, and reword existing content only."""

PROMPT = """Tailor this resume for the target role. Rules:
- Do NOT invent experience, skills, or metrics that don't exist in the original
- Do NOT combine bullets since they may reflect diffeerent projects
- Do NOT elevate experience and level too much
- Reorder bullet points so the most JD-relevant ones appear first
- Rewrite bullets to use keywords from the JD where truthfully applicable
- Add/adjust the summary section to target this specific role
- Keep the same Markdown structure and length (±10%)'

Target Role: {role} at {company}
Key JD requirements: {required_skills}
Top matched stories to emphasize: {top_stories}

Original Resume:
---
{resume_text}
---

Return ONLY the tailored resume in Markdown, no explanation."""


def tailor_resume(
    match: MatchResult,
    score: Score,
    resume_path: Path | None = None,
) -> str:
    if resume_path is None:
        resume_path = Path(__file__).parent.parent / "data" / "resume.md"

    resume_text = resume_path.read_text()
    client = anthropic.Anthropic(api_key=get_anthropic_api_key())

    top_stories = "\n".join(
        f"- {s.story_title} (matched: {', '.join(s.matched_keywords[:4])})"
        for s in match.top_stories
    )

    prompt = PROMPT.format(
        role=match.jd.role,
        company=match.jd.company,
        required_skills=", ".join(match.jd.required_skills[:8]),
        top_stories=top_stories,
        resume_text=resume_text,
    )

    with client.messages.stream(
        model=MODEL,
        max_tokens=4096,
        system=SYSTEM,
        messages=[{"role": "user", "content": prompt}],
    ) as stream:
        response = stream.get_final_message()

    return next(b for b in response.content if b.type == "text").text
