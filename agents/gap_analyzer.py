from pathlib import Path
import yaml
import anthropic
from config import get_anthropic_api_key, get_model
from models.schemas import MatchResult, Score, GapAnalysis
from models.utils import parse_json_response

SYSTEM = """You are a career development advisor. Identify skill gaps between a candidate's experience
and a target role, then suggest actionable, specific learning resources.
Always respond with valid JSON."""

PROMPT = """Analyze gaps between this candidate's experience and the target role.

Role: {role} at {company}
Required skills: {required_skills}
Preferred skills: {preferred_skills}

Candidate's full resume:
---
{resume_text}
---

All skills and technologies across the candidate's complete experience history:
{all_skills}

IMPORTANT: Only list a skill as "missing" if it is genuinely absent from both the resume AND the full skills list above.
If a skill appears anywhere in the resume or skills list, do NOT list it as missing — at most list it as "partial" if the level or recency is insufficient for this role.

Return JSON:
{{
  "missing_skills": [skills clearly required but genuinely absent from the candidate's entire experience],
  "partial_skills": [skills the candidate has but not at the depth, recency, or level the role requires],
  "learning_resources": [
    {{
      "skill": string,
      "resource": string (specific book, course, project, or practice approach),
      "type": one of "course", "book", "project", "practice", "certification"
    }}
  ],
  "priority_order": [skills from missing_skills + partial_skills ordered highest impact first],
  "estimated_weeks": {{skill: weeks_to_competency}}
}}

Be specific with resources (e.g. "FastAPI official tutorial + build 2 side projects" not "learn FastAPI").
Respond ONLY with the JSON object."""


def _all_story_skills(bank_path: Path) -> set[str]:
    with open(bank_path) as f:
        stories = yaml.safe_load(f)["stories"]
    skills: set[str] = set()
    for s in stories:
        skills.update(s.get("tags", []))
        skills.update(s.get("seniority_signals", []))
    return skills


def analyze_gaps(match: MatchResult, score: Score, bank_path: Path | None = None) -> GapAnalysis:
    if bank_path is None:
        bank_path = Path(__file__).parent.parent / "data" / "experience_bank.yaml"

    resume_path = Path(__file__).parent.parent / "data" / "resume.md"
    resume_text = resume_path.read_text()
    all_skills = _all_story_skills(bank_path)

    client = anthropic.Anthropic(api_key=get_anthropic_api_key())

    prompt = PROMPT.format(
        role=match.jd.role,
        company=match.jd.company,
        required_skills=", ".join(match.jd.required_skills),
        preferred_skills=", ".join(match.jd.preferred_skills),
        resume_text=resume_text,
        all_skills=", ".join(sorted(all_skills)),
    )

    with client.messages.stream(
        model=get_model(),
        max_tokens=4096,
        system=SYSTEM,
        messages=[{"role": "user", "content": prompt}],
    ) as stream:
        response = stream.get_final_message()

    if response.stop_reason == "max_tokens":
        print("    WARNING: gap_analyzer response was truncated (hit max_tokens)")

    text_blocks = [b for b in response.content if b.type == "text"]
    if not text_blocks:
        raise RuntimeError(
            f"gap_analyzer got no text block. stop_reason={response.stop_reason!r}, "
            f"content types={[b.type for b in response.content]}"
        )

    data = parse_json_response(text_blocks[0].text)
    return GapAnalysis(**data)


def render_gaps_md(gaps: GapAnalysis, role: str = "", company: str = "") -> str:
    header = f"# Skill Gaps & Learning Plan"
    if role and company:
        header += f" — {role} @ {company}"
    lines = [header, ""]

    if gaps.missing_skills:
        lines += ["## Missing Skills", ""]
        lines += [f"- {s}" for s in gaps.missing_skills]
        lines += [""]

    if gaps.partial_skills:
        lines += ["## Partial Skills (Need Deepening)", ""]
        lines += [f"- {s}" for s in gaps.partial_skills]
        lines += [""]

    if gaps.priority_order:
        lines += ["## Priority Order", ""]
        for i, skill in enumerate(gaps.priority_order, 1):
            weeks = gaps.estimated_weeks.get(skill, "?")
            lines += [f"{i}. **{skill}** — ~{weeks} week{'s' if weeks != 1 else ''}"]
        lines += [""]

    if gaps.learning_resources:
        lines += ["## Learning Resources", ""]
        by_skill: dict[str, list] = {}
        for r in gaps.learning_resources:
            by_skill.setdefault(r["skill"], []).append(r)
        for skill, resources in by_skill.items():
            lines += [f"### {skill}", ""]
            for r in resources:
                lines += [f"- [{r['type']}] {r['resource']}"]
            lines += [""]

    return "\n".join(lines)
