from datetime import date
from pathlib import Path
import anthropic
from jinja2 import Environment, FileSystemLoader
from models.schemas import MatchResult, Score, CoverLetterSlots, CoverLetterContext
from models.utils import parse_json_response

MODEL = "claude-sonnet-4-6"

SYSTEM = """You are an expert cover letter writer. You write compelling, specific, non-generic cover letters.
Each section must be concrete, referencing real accomplishments and the specific company/role.
Always respond with valid JSON."""

PROMPT = """Write cover letter sections for this application.

Role: {role} at {company}
Company domain: {domain}
Key requirements: {required_skills}
Top STAR stories to draw from:
{star_stories}

Score rationale: {score_rationale}

Return JSON with exactly these fields:
{{
  "opening_hook": string (1-2 sentences, company-specific, why THIS company/role excites the candidate),
  "fit_statement": string (2-3 sentences, map top skills/experience to the role's core needs),
  "star_paragraph_1": string (3-4 sentences, best matching STAR story told in narrative form),
  "star_paragraph_2": string or null (second STAR story if relevance_score > 0.6, else null),
  "closing": string (2-3 sentences, specific call to action referencing the role)
}}

Respond ONLY with the JSON object."""


def _generate_slots(match: MatchResult, score: Score) -> CoverLetterSlots:
    client = anthropic.Anthropic()

    star_stories = "\n".join(
        f"- {s.story_title} [{s.relevance_score:.2f}]: {s.star_summary}"
        for s in match.top_stories
    )

    prompt = PROMPT.format(
        role=match.jd.role,
        company=match.jd.company,
        domain=match.jd.domain,
        required_skills=", ".join(match.jd.required_skills[:8]),
        star_stories=star_stories,
        score_rationale=score.rationale,
    )

    with client.messages.stream(
        model=MODEL,
        max_tokens=2048,
        system=SYSTEM,
        messages=[{"role": "user", "content": prompt}],
    ) as stream:
        response = stream.get_final_message()

    if response.stop_reason == "max_tokens":
        print("    WARNING: cover_letter response was truncated (hit max_tokens)")

    text_blocks = [b for b in response.content if b.type == "text"]
    if not text_blocks:
        raise RuntimeError(
            f"cover_letter got no text block. stop_reason={response.stop_reason!r}, "
            f"content types={[b.type for b in response.content]}"
        )

    data = parse_json_response(text_blocks[0].text)
    return CoverLetterSlots(**data)


def generate_cover_letter(
    match: MatchResult,
    score: Score,
    candidate_name: str,
    candidate_email: str,
    candidate_phone: str,
    candidate_linkedin: str | None = None,
    hiring_manager: str | None = None,
    referral_name: str | None = None,
    referral_context: str | None = None,
    template_dir: Path | None = None,
) -> str:
    if template_dir is None:
        template_dir = Path(__file__).parent.parent / "templates"

    slots = _generate_slots(match, score)

    ctx = CoverLetterContext(
        date=date.today().strftime("%B %d, %Y"),
        candidate_name=candidate_name,
        candidate_email=candidate_email,
        candidate_phone=candidate_phone,
        candidate_linkedin=candidate_linkedin,
        hiring_manager=hiring_manager,
        referral_name=referral_name,
        referral_context=referral_context,
        slots=slots,
    )

    env = Environment(
        loader=FileSystemLoader(str(template_dir)),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    template = env.get_template("cover_letter.jinja")

    return template.render(
        **ctx.model_dump(exclude={"slots"}),
        **slots.model_dump(),
    )
