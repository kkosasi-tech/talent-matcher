"""Zero-token keyword prefilter.

Checks a JD's text against the tags in your experience bank locally — no API
calls — so batch runs can skip postings that clearly don't match before any
tokens are spent. Also runnable as a CLI emitting JSON, so external callers
(e.g. talent-dashboard) can reuse it:

    python prefilter.py --jd path/to/jd.txt [--min-matches 3]
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import yaml
from pydantic import BaseModel

from config import load_config

BANK_PATH = Path(__file__).parent / "data" / "experience_bank.yaml"

DEFAULT_MIN_MATCHES = 3


class PrefilterResult(BaseModel):
    matched_keywords: list[str]
    matched_count: int
    total_keywords: int
    min_required: int
    passed: bool


def _normalize(term: str) -> str:
    return re.sub(r"[-_/]+", " ", term.lower()).strip()


def load_bank_keywords(bank_path: Path = BANK_PATH) -> set[str]:
    """Distinct normalized tags across all STAR stories."""
    data = yaml.safe_load(bank_path.read_text())
    keywords = set()
    for story in data.get("stories", []):
        for tag in story.get("tags", []):
            normalized = _normalize(str(tag))
            if normalized:
                keywords.add(normalized)
    return keywords


def min_matches_from_config() -> int:
    return load_config().get("prefilter", {}).get("min_keyword_matches", DEFAULT_MIN_MATCHES)


def prefilter_jd(jd_text: str, min_matches: int | None = None,
                 bank_path: Path = BANK_PATH) -> PrefilterResult:
    if min_matches is None:
        min_matches = min_matches_from_config()
    keywords = load_bank_keywords(bank_path)
    normalized_text = _normalize(jd_text)
    matched = sorted(
        kw for kw in keywords
        if re.search(rf"\b{re.escape(kw)}\b", normalized_text)
    )
    return PrefilterResult(
        matched_keywords=matched,
        matched_count=len(matched),
        total_keywords=len(keywords),
        min_required=min_matches,
        passed=len(matched) >= min_matches,
    )


def main():
    parser = argparse.ArgumentParser(description="Keyword prefilter (no API calls)")
    parser.add_argument("--jd", required=True,
                        help="Path to a JD text file, or a directory of *.txt files "
                             "(directory mode emits a {filename: result} JSON map)")
    parser.add_argument("--min-matches", type=int, help="Overrides prefilter.min_keyword_matches from config.yaml")
    args = parser.parse_args()

    path = Path(args.jd)
    if path.is_dir():
        results = {
            f.name: prefilter_jd(f.read_text(), min_matches=args.min_matches).model_dump()
            for f in sorted(path.glob("*.txt"))
        }
        print(json.dumps(results, indent=2))
    else:
        result = prefilter_jd(path.read_text(), min_matches=args.min_matches)
        print(result.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
