from pathlib import Path

from llm import chat
from models.schemas import GapAnalysis, MatchReport, MatchResult, Score
from models.utils import parse_json_response

SYSTEM = """You are a career development advisor. Identify skill gaps between a candidate's experience
and a target role, then suggest actionable, specific learning resources.
Always respond with valid JSON."""

PROMPT = """Build a learning plan for closing this candidate's gaps for the target role.

Role: {role} at {company}
Required skills: {required_skills}
Preferred skills: {preferred_skills}

Candidate's full resume:
---
{resume_text}
---

The resume/JD match report already determined which skills are genuinely missing (no evidence anywhere
in the resume or the candidate's STAR story bank) — treat this as authoritative, do not add to it or
second-guess it:
Missing: {missing_skills}

These skills ARE demonstrated (in the resume or the candidate's STAR story bank) — do not flag them as
missing, and only flag one as "partial" below if the resume/story evidence clearly shows an outdated or
shallow level for this specific role:
Demonstrated: {demonstrated_skills}

Return JSON:
{{
  "partial_skills": [
    {{
      "skill": string (from the demonstrated list above),
      "reason": string (why this is only partial for this role — outdated, shallow, or below the level required; be conservative, only include with clear justification)
    }}
  ],
  "learning_resources": [
    {{
      "skill": string (drawn from the missing or partial skills above),
      "resource": string (specific book, course, project, or practice approach),
      "type": one of "course", "book", "project", "practice", "certification"
    }}
  ],
  "priority_order": [skills from the missing list + your partial_skills, ordered highest impact first],
  "estimated_weeks": {{skill: weeks_to_competency}}
}}

Be specific with resources (e.g. "FastAPI official tutorial + build 2 side projects" not "learn FastAPI").
Respond ONLY with the JSON object."""


def analyze_gaps(
    match: MatchResult,
    score: Score,
    match_report: MatchReport,
    resume_path: Path | None = None,
) -> GapAnalysis:
    if resume_path is None:
        resume_path = Path(__file__).parent.parent / "data" / "resume.md"

    resume_text = resume_path.read_text()
    demonstrated_skills = sorted(set(
        match_report.required_skills.matched
        + match_report.preferred_skills.matched
        + match_report.soft_skills.matched
        + match_report.keywords.matched
    ))


    prompt = PROMPT.format(
        role=match.jd.role,
        company=match.jd.company,
        required_skills=", ".join(match.jd.required_skills),
        preferred_skills=", ".join(match.jd.preferred_skills),
        resume_text=resume_text,
        missing_skills=", ".join(match_report.missing_skills) or "none",
        demonstrated_skills=", ".join(demonstrated_skills) or "none",
    )

    response = chat(
        system=SYSTEM,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=4096,
    )

    if response.truncated:
        print("    WARNING: gap_analyzer response was truncated (hit max_tokens)")

    data = parse_json_response(response.text)
    data["missing_skills"] = match_report.missing_skills
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
        lines += [f"- **{s.skill}** — {s.reason}" for s in gaps.partial_skills]
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
