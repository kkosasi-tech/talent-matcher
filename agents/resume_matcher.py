"""Matches the candidate's resume against a job description.

Reports category-by-category fit (soft skills, required skills, preferred skills,
other keywords, job title, degree), flags genuinely missing skills, and checks the resume
itself: word count (target configurable via pipeline.resume_word_count_min/max
in config.yaml, default 500-700) and presence of concrete, quantified
accomplishments rather than bare responsibilities.

Also cross-references the full STAR story bank (not just the resume text) —
a skill can be genuinely demonstrated in a story's action/result even if it
never made it onto the resume. Those are reported separately as
"recoverable_skills" so resume_tailor can truthfully surface them, instead of
being wrongly flagged as missing just because the resume doesn't mention them.
"""

import re
from pathlib import Path

import anthropic
import yaml
from config import get_anthropic_api_key, get_model, get_resume_word_count_range
from models.schemas import CategoryMatch, MatchReport, ParsedJD, RecoverableSkill
from models.utils import parse_json_response

SYSTEM = """You are an expert recruiter and ATS analyst. Compare a candidate's resume against a job
description, grounded only in what the resume and the candidate's STAR story bank actually state —
never assume a skill is present because it's plausible for the role, and never infer beyond what the
text says.
Always respond with valid JSON."""

PROMPT = """Compare this candidate's resume against the job description below. The candidate's full
STAR story bank is also included — it is real, verified experience, and sometimes contains detail
that never made it onto the resume itself (e.g. a specific tool or environment mentioned only in a
story's action/result text). Treat both the resume and the story bank as ground truth for what the
candidate has genuinely done.

Job: {role} at {company}
Required skills: {required_skills}
Preferred skills: {preferred_skills}
Other keywords: {keywords}
Seniority expected: {seniority_level}

Candidate Resume:
---
{resume_text}
---

Candidate's STAR Story Bank (YAML — situation/task/action/result per story, may contain detail not on the resume):
---
{stories_yaml}
---

For "matched", count a skill/keyword as matched if it is genuinely demonstrated in EITHER the resume
text OR the story bank — judge substance, not exact wording. For "missing", only list something with
no genuine evidence in either source; do not guess or infer beyond what is stated.

Separately, for any matched skill/keyword whose ONLY evidence is in the story bank (i.e. it is not
written anywhere in the resume text), add an entry to "recoverable_skills" citing exactly which story
demonstrates it and how — these are true things about the candidate that the resume simply omits.

In "matched"/"missing" lists, use short skill or keyword names only (e.g. "Linux", "EHR integration") —
put any explanation in the category's "notes" field, not inline in the list items.

Return JSON with exactly these fields:
{{
  "soft_skills": {{"score": int 0-100, "matched": [soft skills demonstrated in the resume or story bank, e.g. leadership, communication, mentoring], "missing": [soft skills the JD implies or requires with no evidence anywhere], "notes": string}},
  "required_skills": {{"score": int 0-100, "matched": [skills from Required skills demonstrated in the resume or story bank], "missing": [skills from Required skills with no evidence anywhere], "notes": string}},
  "preferred_skills": {{"score": int 0-100, "matched": [skills from Preferred skills demonstrated in the resume or story bank], "missing": [skills from Preferred skills with no evidence anywhere], "notes": string (these are nice-to-haves, not must-haves — do not score as harshly as required_skills)}},
  "keywords": {{"score": int 0-100, "matched": [other JD keywords/terms echoed in the resume or story bank], "missing": [JD keywords with no evidence anywhere], "notes": string}},
  "job_title_match": {{"score": int 0-100, "matched": [], "missing": [], "notes": string (does the candidate's current/past titles align with "{role}"?)}},
  "degree_match": {{"score": int 0-100, "matched": [], "missing": [], "notes": string (does the resume's education meet any degree requirement implied by the JD? if the JD states or implies no degree requirement, score 100 and say so)}},
  "accomplishments_present": bool (does the resume show concrete, quantified accomplishments/results rather than just listing responsibilities?),
  "accomplishments_notes": string (1-2 sentences on what's strong or missing about the accomplishments),
  "recoverable_skills": [{{"skill": string, "evidence": string (what the story text actually says), "story_id": string (the story's id field)}}]
}}

Respond ONLY with the JSON object."""


def _word_count(text: str) -> int:
    return len(re.findall(r"\S+", text))


def _load_stories(bank_path: Path) -> list[dict]:
    with open(bank_path) as f:
        return yaml.safe_load(f)["stories"]


def match_resume(
    jd: ParsedJD,
    resume_path: Path | None = None,
    bank_path: Path | None = None,
) -> MatchReport:
    if resume_path is None:
        resume_path = Path(__file__).parent.parent / "data" / "resume.md"
    if bank_path is None:
        bank_path = Path(__file__).parent.parent / "data" / "experience_bank.yaml"

    resume_text = resume_path.read_text()
    word_count = _word_count(resume_text)
    word_min, word_max = get_resume_word_count_range()
    stories = _load_stories(bank_path)

    client = anthropic.Anthropic(api_key=get_anthropic_api_key())

    prompt = PROMPT.format(
        role=jd.role,
        company=jd.company,
        required_skills=", ".join(jd.required_skills),
        preferred_skills=", ".join(jd.preferred_skills),
        keywords=", ".join(jd.keywords),
        seniority_level=jd.seniority_level,
        resume_text=resume_text,
        stories_yaml=yaml.dump(stories, default_flow_style=False),
    )

    with client.messages.stream(
        model=get_model(),
        max_tokens=4096,
        system=SYSTEM,
        messages=[{"role": "user", "content": prompt}],
    ) as stream:
        response = stream.get_final_message()

    if response.stop_reason == "max_tokens":
        print("    WARNING: resume_matcher response was truncated (hit max_tokens)")

    text_blocks = [b for b in response.content if b.type == "text"]
    if not text_blocks:
        raise RuntimeError(
            f"resume_matcher got no text block. stop_reason={response.stop_reason!r}, "
            f"content types={[b.type for b in response.content]}"
        )

    data = parse_json_response(text_blocks[0].text)
    stories_by_id = {s["id"]: s for s in stories}

    def _enrich_recoverable(r: dict) -> dict:
        source = stories_by_id.get(r["story_id"], {})
        return {
            **r,
            "company": source.get("company") or "",
            "role": source.get("role") or "",
            "year": str(source.get("year") or ""),
        }

    missing_skills = sorted(set(
        data["required_skills"]["missing"]
        + data["preferred_skills"]["missing"]
        + data["soft_skills"]["missing"]
        + data["keywords"]["missing"]
    ))

    return MatchReport(
        soft_skills=CategoryMatch(**data["soft_skills"]),
        required_skills=CategoryMatch(**data["required_skills"]),
        preferred_skills=CategoryMatch(**data["preferred_skills"]),
        keywords=CategoryMatch(**data["keywords"]),
        job_title_match=CategoryMatch(**data["job_title_match"]),
        degree_match=CategoryMatch(**data["degree_match"]),
        resume_word_count=word_count,
        resume_word_count_ok=word_min <= word_count <= word_max,
        resume_word_min=word_min,
        resume_word_max=word_max,
        accomplishments_present=data["accomplishments_present"],
        accomplishments_notes=data["accomplishments_notes"],
        missing_skills=missing_skills,
        recoverable_skills=[
            RecoverableSkill(**_enrich_recoverable(r)) for r in data.get("recoverable_skills", [])
        ],
    )
