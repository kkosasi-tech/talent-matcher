import anthropic
from config import get_anthropic_api_key
from models.schemas import ParsedJD
from models.utils import parse_json_response

MODEL = "claude-sonnet-4-6"

SYSTEM = """You are a job description parser. Extract structured information from job descriptions.
Always respond with valid JSON matching the specified schema exactly."""

PROMPT = """Parse this job description and return a JSON object with these fields:
- company: string
- role: string
- required_skills: array of strings (must-have skills explicitly stated)
- preferred_skills: array of strings (nice-to-have or "bonus" skills)
- responsibilities: array of strings (key job duties, max 8)
- seniority_level: one of "junior", "mid", "senior", "staff", "principal"
- domain: one of "backend", "frontend", "fullstack", "data", "ml", "devops", "mobile", "other"
- keywords: array of strings (important domain terms, technologies, methodologies)
- location: string or null (work location, city/state, or "Remote" if stated; null if not mentioned)
- salary_advertised: string or null (the compensation/salary range ONLY if it is explicitly stated in the JD, e.g. "$160,000 - $200,000"; null if the JD does not state any salary)
- restrictions: array of strings (eligibility restrictions explicitly stated, e.g. "US Citizenship required", "Must be eligible for security clearance", "No visa sponsorship", "Onsite only"; empty array if none stated)

Do not include a raw_text field.

Job Description:
---
{jd_text}
---

Respond ONLY with the JSON object, no markdown fences."""


def parse_jd(jd_text: str) -> ParsedJD:
    client = anthropic.Anthropic(api_key=get_anthropic_api_key())

    with client.messages.stream(
        model=MODEL,
        max_tokens=4096,
        system=SYSTEM,
        messages=[{"role": "user", "content": PROMPT.format(jd_text=jd_text)}],
    ) as stream:
        response = stream.get_final_message()

    if response.stop_reason == "max_tokens":
        print("    WARNING: jd_parser response was truncated (hit max_tokens)")

    text_blocks = [b for b in response.content if b.type == "text"]
    if not text_blocks:
        raise RuntimeError(
            f"jd_parser got no text block. stop_reason={response.stop_reason!r}, "
            f"content types={[b.type for b in response.content]}"
        )

    data = parse_json_response(text_blocks[0].text)
    data["raw_text"] = jd_text
    return ParsedJD(**data)
