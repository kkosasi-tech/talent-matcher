"""Fetch job description text from a posting URL.

Uses official public ATS APIs where the URL identifies one (Greenhouse, Lever,
Ashby, SmartRecruiters, Workable). For any other page, falls back to the
schema.org JobPosting JSON-LD that most career pages embed, then to plain
HTML text extraction as a last resort.
"""

from __future__ import annotations

import html as html_lib
import json
import re
import sys
from dataclasses import dataclass
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

TIMEOUT = 20
API_HEADERS = {
    "User-Agent": "talent-matcher/0.1 (job application assistant)",
    "Accept": "application/json",
}
# Some career pages refuse non-browser user agents outright.
PAGE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml",
}


@dataclass
class FetchedJob:
    url: str
    source: str  # greenhouse | lever | ashby | smartrecruiters | workable | json-ld | html
    title: str | None
    company: str | None
    location: str | None
    text: str  # full JD text to feed the pipeline


class FetchError(Exception):
    pass


def _get_json(url: str) -> dict | list:
    resp = requests.get(url, headers=API_HEADERS, timeout=TIMEOUT)
    resp.raise_for_status()
    return resp.json()


def _html_to_text(html_str: str) -> str:
    soup = BeautifulSoup(html_str, "html.parser")
    for tag in soup(["script", "style"]):
        tag.decompose()
    lines = [ln.strip() for ln in soup.get_text("\n").splitlines()]
    return "\n".join(ln for ln in lines if ln)


def _compose(title: str | None, company: str | None, location: str | None, body: str) -> str:
    header = [f"{title or 'Unknown role'} at {company or 'Unknown company'}"]
    if location:
        header.append(f"Location: {location}")
    return "\n".join(header) + "\n\n" + body


# --- ATS handlers ------------------------------------------------------------

def _fetch_greenhouse(url: str, parsed) -> FetchedJob:
    m = re.search(r"^/([^/]+)/jobs/(\d+)", parsed.path)
    if not m:
        raise FetchError("unrecognised Greenhouse URL shape")
    board, job_id = m.group(1), m.group(2)
    data = _get_json(f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs/{job_id}")
    body = _html_to_text(html_lib.unescape(data.get("content", "")))
    title = data.get("title")
    company = data.get("company_name") or board
    location = (data.get("location") or {}).get("name")
    return FetchedJob(url, "greenhouse", title, company, location,
                      _compose(title, company, location, body))


def _fetch_lever(url: str, parsed) -> FetchedJob:
    parts = [p for p in parsed.path.split("/") if p]
    if len(parts) < 2:
        raise FetchError("unrecognised Lever URL shape")
    company, posting_id = parts[0], parts[1]
    data = _get_json(f"https://api.lever.co/v0/postings/{company}/{posting_id}")
    sections = [data.get("descriptionPlain") or _html_to_text(data.get("description", ""))]
    for lst in data.get("lists", []):
        sections.append(lst.get("text", ""))
        sections.append(_html_to_text(lst.get("content", "")))
    extra = data.get("additionalPlain") or _html_to_text(data.get("additional", ""))
    if extra:
        sections.append(extra)
    title = data.get("text")
    location = (data.get("categories") or {}).get("location")
    body = "\n\n".join(s for s in sections if s)
    return FetchedJob(url, "lever", title, company, location,
                      _compose(title, company, location, body))


def _fetch_ashby(url: str, parsed) -> FetchedJob:
    parts = [p for p in parsed.path.split("/") if p]
    if len(parts) < 2:
        raise FetchError("unrecognised Ashby URL shape")
    org, posting_id = parts[0], parts[1]
    data = _get_json(f"https://api.ashbyhq.com/posting-api/job-board/{org}?includeCompensation=true")
    job = next((j for j in data.get("jobs", []) if j.get("id") == posting_id), None)
    if job is None:
        raise FetchError(f"posting {posting_id} not found on Ashby board {org!r}")
    body = _html_to_text(job.get("descriptionHtml", ""))
    comp = job.get("compensation") or {}
    summary = comp.get("compensationTierSummary")
    if summary:
        body += f"\n\nCompensation: {summary}"
    title = job.get("title")
    location = job.get("location")
    return FetchedJob(url, "ashby", title, org, location,
                      _compose(title, org, location, body))


def _fetch_smartrecruiters(url: str, parsed) -> FetchedJob:
    parts = [p for p in parsed.path.split("/") if p]
    if len(parts) < 2:
        raise FetchError("unrecognised SmartRecruiters URL shape")
    company = parts[0]
    m = re.match(r"(\d+)", parts[1])
    if not m:
        raise FetchError("no posting id in SmartRecruiters URL")
    data = _get_json(f"https://api.smartrecruiters.com/v1/companies/{company}/postings/{m.group(1)}")
    sections = []
    for sec in (data.get("jobAd") or {}).get("sections", {}).values():
        if isinstance(sec, dict):
            sections.append(sec.get("title", ""))
            sections.append(_html_to_text(sec.get("text", "")))
    title = data.get("name")
    company_name = (data.get("company") or {}).get("name") or company
    location = (data.get("location") or {}).get("city")
    body = "\n\n".join(s for s in sections if s)
    return FetchedJob(url, "smartrecruiters", title, company_name, location,
                      _compose(title, company_name, location, body))


def _fetch_workable(url: str, parsed) -> FetchedJob:
    m = re.search(r"^/([^/]+)/j/([^/]+)", parsed.path)
    if not m:
        raise FetchError("unrecognised Workable URL shape")
    account, shortcode = m.group(1), m.group(2)
    data = _get_json(f"https://apply.workable.com/api/v2/accounts/{account}/jobs/{shortcode}")
    parts = [_html_to_text(data.get(k, "")) for k in ("description", "requirements", "benefits")]
    title = data.get("title")
    location = (data.get("location") or {}).get("city")
    body = "\n\n".join(p for p in parts if p)
    return FetchedJob(url, "workable", title, account, location,
                      _compose(title, account, location, body))


_ATS_HANDLERS = [
    (re.compile(r"(^|\.)greenhouse\.io$"), _fetch_greenhouse),
    (re.compile(r"(^|\.)lever\.co$"), _fetch_lever),
    (re.compile(r"(^|\.)ashbyhq\.com$"), _fetch_ashby),
    (re.compile(r"(^|\.)smartrecruiters\.com$"), _fetch_smartrecruiters),
    (re.compile(r"(^|\.)workable\.com$"), _fetch_workable),
]


# --- Generic fallback ---------------------------------------------------------

def _iter_jsonld_nodes(raw):
    """Yield every JSON-LD node, unwrapping lists and @graph containers."""
    stack = [raw]
    while stack:
        node = stack.pop()
        if isinstance(node, list):
            stack.extend(node)
        elif isinstance(node, dict):
            yield node
            stack.extend(node.get("@graph", []))


def _is_job_posting(node: dict) -> bool:
    node_type = node.get("@type", "")
    types = node_type if isinstance(node_type, list) else [node_type]
    return any(t == "JobPosting" for t in types)


def _fetch_generic(url: str) -> FetchedJob:
    resp = requests.get(url, headers=PAGE_HEADERS, timeout=TIMEOUT)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    for script in soup.find_all("script", type="application/ld+json"):
        try:
            raw = json.loads(script.string or "")
        except (json.JSONDecodeError, TypeError):
            continue
        for node in _iter_jsonld_nodes(raw):
            if not _is_job_posting(node):
                continue
            title = node.get("title")
            org = node.get("hiringOrganization")
            company = org.get("name") if isinstance(org, dict) else org if isinstance(org, str) else None
            location = None
            loc = node.get("jobLocation")
            if isinstance(loc, list) and loc:
                loc = loc[0]
            if isinstance(loc, dict):
                addr = loc.get("address")
                if isinstance(addr, dict):
                    location = ", ".join(
                        str(addr[k]) for k in ("addressLocality", "addressRegion", "addressCountry")
                        if addr.get(k)
                    ) or None
            body = _html_to_text(node.get("description", ""))
            salary = node.get("baseSalary")
            if isinstance(salary, dict):
                val = salary.get("value")
                if isinstance(val, dict):
                    lo, hi, unit = val.get("minValue"), val.get("maxValue"), val.get("unitText", "")
                    if lo or hi:
                        body += f"\n\nAdvertised salary: {lo or '?'} - {hi or '?'} {salary.get('currency', '')} {unit}".rstrip()
            if body:
                return FetchedJob(url, "json-ld", title, company, location,
                                  _compose(title, company, location, body))

    # Last resort: strip the page chrome and hand over the raw text.
    for tag in soup(["script", "style", "nav", "header", "footer", "noscript"]):
        tag.decompose()
    text = _html_to_text(str(soup))
    if len(text) < 200:
        raise FetchError(
            "page has no JobPosting JSON-LD and too little text — "
            "it is probably rendered by JavaScript; paste the JD into a file instead"
        )
    title = soup.title.string.strip() if soup.title and soup.title.string else None
    return FetchedJob(url, "html", title, None, None, text)


# --- Entry point --------------------------------------------------------------

def fetch_jd(url: str) -> FetchedJob:
    """Fetch a job posting URL and return its text plus basic metadata."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise FetchError(f"not an http(s) URL: {url}")
    host = parsed.netloc.lower().split(":")[0]
    for pattern, handler in _ATS_HANDLERS:
        if pattern.search(host):
            try:
                return handler(url, parsed)
            except (requests.RequestException, FetchError, KeyError, ValueError) as e:
                print(f"    NOTE: ATS API lookup failed ({e}); falling back to page fetch",
                      file=sys.stderr)
                break
    return _fetch_generic(url)


if __name__ == "__main__":
    import argparse
    from dataclasses import asdict

    ap = argparse.ArgumentParser(description="Fetch a job posting URL as text")
    ap.add_argument("url")
    ap.add_argument("--json", action="store_true", help="emit the result as JSON on stdout")
    cli_args = ap.parse_args()

    job = fetch_jd(cli_args.url)
    if cli_args.json:
        print(json.dumps(asdict(job)))
    else:
        print(f"# source={job.source} company={job.company!r} title={job.title!r} location={job.location!r}\n")
        print(job.text)
