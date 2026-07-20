import anthropic
from config import get_anthropic_api_key
from models.schemas import MatchReport, MatchResult, Score
from models.utils import parse_json_response

MODEL = "claude-sonnet-4-6"
THRESHOLD = 60

SYSTEM = """You are an expert recruiter and career advisor. Score candidate-job fit objectively.
Always respond with valid JSON."""

PROMPT = """Score this candidate's fit for the role on a scale of 0-100, using both the STAR story
matches and the resume match report below.

Job: {role} at {company}
Required skills: {required_skills}
Preferred skills: {preferred_skills}
Seniority expected: {seniority_level}

Top matched stories:
{story_summaries}

Resume match report:
- Soft skills match: {soft_skills_score}/100 (missing: {soft_skills_missing})
- Hard skills match: {hard_skills_score}/100 (missing: {hard_skills_missing})
- Other keyword match: {keywords_score}/100 (missing: {keywords_missing})
- Job title match: {title_score}/100 ({title_notes})
- Degree match: {degree_score}/100 ({degree_notes})
- Resume length: {word_count} words ({length_verdict}; target 500-700)
- Accomplishments present: {accomplishments_present} ({accomplishments_notes})

Return JSON with:
{{
  "overall": int 0-100,
  "skill_match": int 0-100 (how well required/preferred skills are covered, informed by the hard/soft/keyword match above),
  "experience_relevance": int 0-100 (how relevant the STAR stories are to responsibilities),
  "seniority_fit": int 0-100 (does experience level match expectations, informed by the job title match),
  "resume_quality": int 0-100 (resume length within the 500-700 word target and presence of concrete accomplishments),
  "rationale": string (2-3 sentences explaining the score and key gaps)
}}

Respond ONLY with the JSON object."""


def score_match(match: MatchResult, match_report: MatchReport, threshold: int = THRESHOLD) -> Score:
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
        soft_skills_score=match_report.soft_skills.score,
        soft_skills_missing=", ".join(match_report.soft_skills.missing) or "none",
        hard_skills_score=match_report.hard_skills.score,
        hard_skills_missing=", ".join(match_report.hard_skills.missing) or "none",
        keywords_score=match_report.keywords.score,
        keywords_missing=", ".join(match_report.keywords.missing) or "none",
        title_score=match_report.job_title_match.score,
        title_notes=match_report.job_title_match.notes,
        degree_score=match_report.degree_match.score,
        degree_notes=match_report.degree_match.notes,
        word_count=match_report.resume_word_count,
        length_verdict="within target" if match_report.resume_word_count_ok else "outside target",
        accomplishments_present=match_report.accomplishments_present,
        accomplishments_notes=match_report.accomplishments_notes,
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
    data["missing_skills"] = match_report.missing_skills
    return Score(**data)
