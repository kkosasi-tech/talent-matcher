from pathlib import Path
import anthropic
from config import get_anthropic_api_key, get_model
from models.schemas import InterviewPrep, InterviewQuestion, MatchResult, Score
from models.utils import parse_json_response

SYSTEM = """You are an expert technical interviewer and career coach. Generate realistic mock
interview questions and model answers grounded in the candidate's actual experience.
Always respond with valid JSON."""

PROMPT = """Generate mock interview questions and sample answers for this candidate.

Role: {role} at {company}
Seniority: {seniority_level}
Required skills: {required_skills}
Preferred skills: {preferred_skills}

Fit score: {overall}/100
Scoring rationale (reveals weak areas to probe): {rationale}

Candidate's top STAR stories:
{top_stories}

Candidate's resume:
---
{resume_text}
---

Generate 12-15 questions across these categories:
- behavioral (3-4): "Tell me about a time..." — answered with STAR structure
- technical (4-5): Depth calibrated to the seniority level (junior = implementation,
  mid = design + tradeoffs, senior/staff = architecture, scalability, org impact).
  Prioritize the weak areas identified in the scoring rationale.
- situational (2-3): "How would you handle..." hypotheticals relevant to the role.
  Include at least one that probes a gap from the scoring rationale.
- culture_fit (2-3): Motivation, team dynamics, growth, why this company

Rules:
- sample_answer MUST reference the candidate's real experience from the resume/stories above
- Do NOT invent projects or metrics that are not in the resume
- tips must be specific to this question — no generic advice
- technical questions must cover the required and preferred skills listed above
- bias harder questions toward the specific gaps called out in the scoring rationale

Return ONLY a JSON object (no markdown fences):
{{
  "role": string,
  "company": string,
  "seniority_level": string,
  "questions": [
    {{
      "category": "behavioral" | "technical" | "situational" | "culture_fit",
      "question": string,
      "sample_answer": string (2-5 sentences grounded in candidate's actual experience),
      "tips": [string, ...]  (1-3 concrete, question-specific tips)
    }}
  ]
}}"""


def generate_interview_prep(
    match: MatchResult,
    score: Score,
    resume_path: Path | None = None,
) -> InterviewPrep:
    if resume_path is None:
        resume_path = Path(__file__).parent.parent / "data" / "resume.md"

    resume_text = resume_path.read_text()
    client = anthropic.Anthropic(api_key=get_anthropic_api_key())

    top_stories = "\n".join(
        f"- {s.story_title}: {s.star_summary}"
        for s in match.top_stories
    )

    prompt = PROMPT.format(
        role=match.jd.role,
        company=match.jd.company,
        seniority_level=match.jd.seniority_level,
        required_skills=", ".join(match.jd.required_skills),
        preferred_skills=", ".join(match.jd.preferred_skills),
        overall=score.overall,
        rationale=score.rationale,
        top_stories=top_stories,
        resume_text=resume_text,
    )

    with client.messages.stream(
        model=get_model(),
        max_tokens=8096,
        system=SYSTEM,
        messages=[{"role": "user", "content": prompt}],
    ) as stream:
        response = stream.get_final_message()

    if response.stop_reason == "max_tokens":
        print("    WARNING: interview_prep response was truncated (hit max_tokens)")

    text_blocks = [b for b in response.content if b.type == "text"]
    if not text_blocks:
        raise RuntimeError(
            f"interview_prep got no text block. stop_reason={response.stop_reason!r}, "
            f"content types={[b.type for b in response.content]}"
        )

    data = parse_json_response(text_blocks[0].text)
    questions = [InterviewQuestion(**q) for q in data["questions"]]
    return InterviewPrep(
        role=data["role"],
        company=data["company"],
        seniority_level=data["seniority_level"],
        questions=questions,
    )


def render_interview_prep_md(prep: InterviewPrep) -> str:
    """Render an InterviewPrep as a structured markdown study guide."""
    lines = [
        f"# Mock Interview Prep — {prep.role} @ {prep.company}",
        f"**Level:** {prep.seniority_level}",
        "",
    ]

    categories = ["behavioral", "technical", "situational", "culture_fit"]
    headings = {
        "behavioral": "Behavioral",
        "technical": "Technical",
        "situational": "Situational",
        "culture_fit": "Culture & Fit",
    }

    for cat in categories:
        qs = [q for q in prep.questions if q.category == cat]
        if not qs:
            continue
        lines += [f"## {headings[cat]}", ""]
        for i, q in enumerate(qs, 1):
            lines += [
                f"### {i}. {q.question}",
                "",
                "**Sample answer:**",
                "",
                q.sample_answer,
                "",
            ]
            if q.tips:
                lines += ["**Tips:**", ""]
                lines += [f"- {tip}" for tip in q.tips]
                lines += [""]

    return "\n".join(lines)
