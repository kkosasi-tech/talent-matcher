from pathlib import Path
import anthropic
from config import get_anthropic_api_key, get_model
from models.schemas import MatchReport, MatchResult, Score

SYSTEM = """You are an expert resume writer. You tailor resumes to specific job descriptions
without fabricating experience. You reorder, emphasize, and reword existing content only."""

PROMPT = """Tailor this resume for the target role. Rules:
- Do NOT invent experience, skills, or metrics that don't exist in the original resume or in the
  recoverable skills evidence below
- Do NOT combine bullets since they may reflect diffeerent projects
- Do NOT elevate experience and level too much 
- The headline under the candidate's name and the opening words of the summary must use the
  candidate's own highest actual title as it appears in the Employment History below — NEVER the
  target role's title, even if it sounds more senior or is a closer match. "Target Role" below is
  given only so you can emphasize relevant scope, skills, and keywords in the summary — it is not a
  title the candidate holds and must not be self-applied.
- Reorder bullet points so the most JD-relevant ones appear first
- Rewrite bullets to use keywords from the JD where truthfully applicable
- Rephrase the matching bullets with more senior sounding words matching the JD
- Add/adjust the summary section to target this specific role, without changing the candidate's
  stated title/level
- Keep the same Markdown structure and length (±10%)'
- The resume has multiple job entries with the same company/title but different date ranges (e.g.
  several "Software Developer | Ericsson" entries). Each story/skill below is tagged with the company,
  role, and year it actually happened. When emphasizing or weaving in a story or skill, place it under
  the resume entry whose date range actually covers that year — never default to the most recent entry
  just because the company matches.
- Remove past experience in the resume that is not relevant to the job descriptions, keep the resume 
  shorter in a sliding windows, do not remove in the middle experience as this will cause gaps in the 
  resume. Keep the experience level not too long between 10-20 years and adjust the headline (number of years)
  accordingly.

Target Role: {role} at {company}
Key JD requirements: {required_skills}
Top matched stories to emphasize: {top_stories}
{recoverable_section}
Original Resume:
---
{resume_text}
---

Return ONLY the tailored resume in Markdown, no explanation."""

RECOVERABLE_SECTION_TEMPLATE = """
Skills genuinely demonstrated in the candidate's STAR story bank but missing from the resume text —
weave these in truthfully (e.g. into the skills line or a relevant bullet), strictly limited to what
the evidence actually supports, do not overstate beyond it:
{recoverable_lines}
"""


def tailor_resume(
    match: MatchResult,
    score: Score,
    match_report: MatchReport | None = None,
    resume_path: Path | None = None,
) -> str:
    if resume_path is None:
        resume_path = Path(__file__).parent.parent / "data" / "resume.md"

    resume_text = resume_path.read_text()
    client = anthropic.Anthropic(api_key=get_anthropic_api_key())

    top_stories = "\n".join(
        f"- {s.story_title} [{s.company} — {s.role}, {s.year}] (matched: {', '.join(s.matched_keywords[:4])})"
        for s in match.top_stories
    )

    recoverable_section = ""
    if match_report and match_report.recoverable_skills:
        recoverable_lines = "\n".join(
            f"- {r.skill}: {r.evidence} (from story: {r.story_id}, [{r.company} — {r.role}, {r.year}])"
            for r in match_report.recoverable_skills
        )
        recoverable_section = RECOVERABLE_SECTION_TEMPLATE.format(recoverable_lines=recoverable_lines)

    prompt = PROMPT.format(
        role=match.jd.role,
        company=match.jd.company,
        required_skills=", ".join(match.jd.required_skills[:8]),
        top_stories=top_stories,
        recoverable_section=recoverable_section,
        resume_text=resume_text,
    )

    with client.messages.stream(
        model=get_model(),
        max_tokens=4096,
        system=SYSTEM,
        messages=[{"role": "user", "content": prompt}],
    ) as stream:
        response = stream.get_final_message()

    return next(b for b in response.content if b.type == "text").text
