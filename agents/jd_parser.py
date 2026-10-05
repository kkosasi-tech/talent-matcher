from llm import chat
from models.schemas import ParsedJD
from models.utils import parse_json_response

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
- keywords: array of strings (important domain terms, technologies, or methodologies the CANDIDATE is
  expected to know or have used — exclude terms that only describe the product's own feature set,
  supported platforms, or customer environment, e.g. an OS/device list describing what the product
  manages rather than what the engineer must have built for. Also exclude the employer's own
  project/product codenames and marketing/vision taglines for the thing being built — e.g. "you will
  help build Project X" means Project X cannot be prior experience any external candidate could have)
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
    response = chat(
        system=SYSTEM,
        messages=[{"role": "user", "content": PROMPT.format(jd_text=jd_text)}],
        max_tokens=4096,
    )

    if response.truncated:
        print("    WARNING: jd_parser response was truncated (hit max_tokens)")

    data = parse_json_response(response.text)
    data["raw_text"] = jd_text
    return ParsedJD(**data)
