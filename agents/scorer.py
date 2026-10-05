from llm import chat
from models.schemas import MatchReport, MatchResult, Score
from models.utils import parse_json_response

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
- Required skills match: {required_skills_score}/100 (missing: {required_skills_missing})
- Preferred skills match: {preferred_skills_score}/100 (missing: {preferred_skills_missing})
- Other keyword match: {keywords_score}/100 (missing: {keywords_missing})
- Job title match: {title_score}/100 ({title_notes})
- Degree match: {degree_score}/100 ({degree_notes})
- Resume length: {word_count} words ({length_verdict}; target {word_min}-{word_max})
- Accomplishments present: {accomplishments_present} ({accomplishments_notes})

When weighing the above into skill_match, required skills matter most, preferred skills matter less
(they are nice-to-haves, missing ones should only cost a few points), and the "other keyword match" is
the weakest signal of the three — it can include incidental JD phrasing, not just true requirements —
so let it nudge skill_match only slightly, never let it dominate over required/preferred skills.

Return JSON with:
{{
  "overall": int 0-100,
  "skill_match": int 0-100 (how well required/preferred skills are covered — weighted per the guidance above, not an unweighted average of required/preferred/keyword),
  "experience_relevance": int 0-100 (how relevant the STAR stories are to responsibilities),
  "seniority_fit": int 0-100 (does experience level match expectations, informed by the job title match),
  "resume_quality": int 0-100 (resume length within the {word_min}-{word_max} word target and presence of concrete accomplishments),
  "rationale": string (2-3 sentences explaining the score and key gaps)
}}

Respond ONLY with the JSON object."""


def score_match(match: MatchResult, match_report: MatchReport, threshold: int = THRESHOLD) -> Score:
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
        required_skills_score=match_report.required_skills.score,
        required_skills_missing=", ".join(match_report.required_skills.missing) or "none",
        preferred_skills_score=match_report.preferred_skills.score,
        preferred_skills_missing=", ".join(match_report.preferred_skills.missing) or "none",
        keywords_score=match_report.keywords.score,
        keywords_missing=", ".join(match_report.keywords.missing) or "none",
        title_score=match_report.job_title_match.score,
        title_notes=match_report.job_title_match.notes,
        degree_score=match_report.degree_match.score,
        degree_notes=match_report.degree_match.notes,
        word_count=match_report.resume_word_count,
        length_verdict="within target" if match_report.resume_word_count_ok else "outside target",
        word_min=match_report.resume_word_min,
        word_max=match_report.resume_word_max,
        accomplishments_present=match_report.accomplishments_present,
        accomplishments_notes=match_report.accomplishments_notes,
    )

    response = chat(
        system=SYSTEM,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=1024,
    )

    if response.truncated:
        print("    WARNING: scorer response was truncated (hit max_tokens)")

    data = parse_json_response(response.text)
    data["proceed"] = data["overall"] >= threshold
    data["missing_skills"] = match_report.missing_skills
    return Score(**data)
