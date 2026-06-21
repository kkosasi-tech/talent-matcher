"""
Compensation researcher.

If the job description already advertises a salary, we report it directly. If
it does not, we use Claude's server-side web_search tool to estimate a typical
market range for the role at that company and location, and cite the sources.

Eligibility restrictions (US Citizenship, security clearance, no visa
sponsorship, onsite-only, etc.) are pulled from the parsed JD and carried into
the report so they surface in one place alongside compensation.
"""

import anthropic

from config import get_anthropic_api_key
from models.schemas import CompensationReport, ParsedJD
from models.utils import parse_json_response

MODEL = "claude-sonnet-4-6"

SYSTEM = """You are a compensation research analyst. You estimate realistic market salary
ranges for software roles using current web sources (Levels.fyi, Glassdoor, Built In,
LinkedIn Salary, company pay-transparency postings, state-mandated salary disclosures).
Prefer recent, location-specific, company-specific data. Always cite the URLs you used."""

PROMPT = """The following job did NOT advertise a salary. Research a realistic market
compensation range for it using web search, then respond.

Role: {role}
Company: {company}
Seniority: {seniority_level}
Location: {location}

Job context (for level/scope; do not quote salary from here, there is none):
---
{jd_excerpt}
---

Search the web for current (prefer last ~2 years) salary data for this role at this
company and location. If company-specific data is unavailable, fall back to comparable
companies in the same market and tier, and say so.

After researching, respond with ONLY a JSON object (no markdown fences):
{{
  "estimated_range": "string, e.g. \\"$180,000 - $240,000 base, plus equity\\"; include base and note equity/bonus if known",
  "research_summary": "2-4 sentences explaining the estimate, the basis (company-specific vs comparable), and any caveats",
  "sources": ["url1", "url2", ...]
}}"""


def _research_market_range(jd: ParsedJD) -> dict:
    client = anthropic.Anthropic(api_key=get_anthropic_api_key())

    prompt = PROMPT.format(
        role=jd.role,
        company=jd.company,
        seniority_level=jd.seniority_level,
        location=jd.location or "Not specified",
        jd_excerpt=jd.raw_text[:2500],
    )

    with client.messages.stream(
        model=MODEL,
        max_tokens=3072,
        system=SYSTEM,
        messages=[{"role": "user", "content": prompt}],
        tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": 5}],
    ) as stream:
        response = stream.get_final_message()

    if response.stop_reason == "max_tokens":
        print("    WARNING: salary_researcher response was truncated (hit max_tokens)")

    text_blocks = [b for b in response.content if b.type == "text"]
    if not text_blocks:
        raise RuntimeError(
            f"salary_researcher got no text block. stop_reason={response.stop_reason!r}, "
            f"content types={[b.type for b in response.content]}"
        )

    # The final answer is the last text block; earlier text blocks are the model's
    # narration between web searches.
    data = parse_json_response(text_blocks[-1].text)

    # Backfill sources from web_search citations if the model omitted them.
    if not data.get("sources"):
        urls = []
        for block in response.content:
            for citation in getattr(block, "citations", None) or []:
                url = getattr(citation, "url", None)
                if url and url not in urls:
                    urls.append(url)
        data["sources"] = urls

    return data


def research_compensation(jd: ParsedJD) -> CompensationReport:
    """Return a compensation report, researching the market range only if the JD
    did not advertise one."""
    if jd.salary_advertised:
        return CompensationReport(
            company=jd.company,
            role=jd.role,
            location=jd.location,
            salary_advertised=jd.salary_advertised,
            research_summary="Salary range was advertised in the job description; no web research was performed.",
            restrictions=jd.restrictions,
        )

    data = _research_market_range(jd)
    return CompensationReport(
        company=jd.company,
        role=jd.role,
        location=jd.location,
        estimated_range=data.get("estimated_range"),
        research_summary=data.get("research_summary", ""),
        sources=data.get("sources", []),
        restrictions=jd.restrictions,
    )


def render_compensation_md(report: CompensationReport) -> str:
    """Render a CompensationReport as a human-readable markdown file."""
    lines = [
        f"# Compensation & Eligibility — {report.role} @ {report.company}",
        "",
    ]
    if report.location:
        lines += [f"**Location:** {report.location}", ""]

    lines += ["## Salary", ""]
    if report.salary_advertised:
        lines += [
            f"**Advertised in job description:** {report.salary_advertised}",
            "",
        ]
    else:
        lines += [
            "_Not advertised in the job description — estimated from market research below._",
            "",
            f"**Estimated market range:** {report.estimated_range or 'Unable to determine'}",
            "",
        ]

    if report.research_summary:
        lines += ["### Basis", "", report.research_summary, ""]

    if report.sources:
        lines += ["### Sources", ""]
        lines += [f"- {url}" for url in report.sources]
        lines += [""]

    lines += ["## Eligibility Restrictions", ""]
    if report.restrictions:
        lines += [f"- {r}" for r in report.restrictions]
    else:
        lines += ["- None stated in the job description."]
    lines += [""]

    return "\n".join(lines)
