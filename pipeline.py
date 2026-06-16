"""
Job application pipeline orchestrator.

Usage:
    python pipeline.py --jd path/to/jd.txt \
        [--hiring-manager "Alex Smith"] \
        [--referral-name "Jane Doe"] \
        [--referral-context "backend engineering"] \
        [--threshold 60]

Candidate info (name, email, phone, linkedin) is read from config.yaml.
"""

import argparse
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from pathlib import Path

import yaml

from agents.cover_letter import generate_cover_letter
from agents.gap_analyzer import analyze_gaps
from agents.jd_parser import parse_jd
from agents.resume_tailor import tailor_resume
from agents.scorer import score_match
from agents.story_matcher import match_stories
from models.schemas import PipelineResult

CONFIG_PATH = Path(__file__).parent / "config.yaml"


def _load_config() -> dict:
    with open(CONFIG_PATH) as f:
        return yaml.safe_load(f)


def _make_job_dir(company: str, role: str, score: int) -> Path:
    slug = f"{company}-{role}-score{score}-{date.today().isoformat()}"
    slug = "".join(c if c.isalnum() or c in "-_" else "-" for c in slug).lower()
    job_dir = Path("jobs") / slug
    job_dir.mkdir(parents=True, exist_ok=True)
    return job_dir


def run(
    jd_text: str,
    hiring_manager: str | None = None,
    referral_name: str | None = None,
    referral_context: str | None = None,
    threshold: int | None = None,
) -> PipelineResult:
    cfg = _load_config()
    candidate = cfg["candidate"]
    candidate_name = candidate["name"]
    candidate_email = candidate["email"]
    candidate_phone = candidate.get("phone", "")
    candidate_linkedin = candidate.get("linkedin")
    if threshold is None:
        threshold = cfg.get("pipeline", {}).get("threshold", 60)
    print("==> [1/5] Parsing job description...")
    parsed_jd = parse_jd(jd_text)
    print(f"    Role: {parsed_jd.role} @ {parsed_jd.company}")

    print("==> [2/5] Matching STAR stories to JD...")
    match = match_stories(parsed_jd)
    print(f"    Top match: {match.top_stories[0].story_title if match.top_stories else 'none'}")

    print("==> [3/5] Scoring fit...")
    score = score_match(match, threshold=threshold)
    print(f"    Score: {score.overall}/100 — proceed: {score.proceed}")
    print(f"    {score.rationale}")

    job_dir = _make_job_dir(parsed_jd.company, parsed_jd.role, score.overall)
    (job_dir / "jd.txt").write_text(jd_text)
    (job_dir / "parsed_jd.json").write_text(parsed_jd.model_dump_json(indent=2))
    (job_dir / "matches.json").write_text(match.model_dump_json(indent=2))
    (job_dir / "score.json").write_text(score.model_dump_json(indent=2))
    print(f"    Output dir: {job_dir}")

    if not score.proceed:
        print(f"\n  Score {score.overall} is below threshold {threshold}. Stopping pipeline.")
        print("  Run with --threshold lower to force generation, or address the gaps first.")
        return PipelineResult(
            job_dir=str(job_dir),
            parsed_jd=parsed_jd,
            matches=match,
            score=score,
        )

    print("==> [4/5] Generating tailored resume, cover letter, gap analysis (parallel)...")

    tailored_resume = None
    cover_letter = None
    gaps = None

    def _tailor():
        return tailor_resume(match, score)

    def _cover():
        return generate_cover_letter(
            match=match,
            score=score,
            candidate_name=candidate_name,
            candidate_email=candidate_email,
            candidate_phone=candidate_phone,
            candidate_linkedin=candidate_linkedin,
            hiring_manager=hiring_manager,
            referral_name=referral_name,
            referral_context=referral_context,
        )

    def _gaps():
        return analyze_gaps(match, score)

    tasks = {"tailor": _tailor, "cover": _cover, "gaps": _gaps}

    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {executor.submit(fn): name for name, fn in tasks.items()}
        for future in as_completed(futures):
            name = futures[future]
            result = future.result()
            if name == "tailor":
                tailored_resume = result
            elif name == "cover":
                cover_letter = result
            elif name == "gaps":
                gaps = result
            print(f"    {name} done")

    (job_dir / "resume.md").write_text(tailored_resume)
    (job_dir / "cover_letter.md").write_text(cover_letter)
    (job_dir / "gaps.json").write_text(gaps.model_dump_json(indent=2))

    print("==> [5/5] Done.")
    print(f"\nOutputs in {job_dir}/")
    print(f"  resume.md        — tailored resume")
    print(f"  cover_letter.md  — cover letter")
    print(f"  gaps.json        — learning recommendations")

    return PipelineResult(
        job_dir=str(job_dir),
        parsed_jd=parsed_jd,
        matches=match,
        score=score,
        tailored_resume=tailored_resume,
        cover_letter=cover_letter,
        gaps=gaps,
    )


def main():
    parser = argparse.ArgumentParser(description="Job application pipeline")
    parser.add_argument("--jd", required=True, help="Path to job description text file")
    parser.add_argument("--hiring-manager", help="Hiring manager name if known")
    parser.add_argument("--referral-name", help="Referral contact name")
    parser.add_argument("--referral-context", help="Context about the referral")
    parser.add_argument("--threshold", type=int, help="Minimum score to proceed (overrides config.yaml)")
    args = parser.parse_args()

    jd_path = Path(args.jd)
    if not jd_path.exists():
        print(f"Error: JD file not found: {args.jd}", file=sys.stderr)
        sys.exit(1)

    run(
        jd_text=jd_path.read_text(),
        hiring_manager=args.hiring_manager,
        referral_name=args.referral_name,
        referral_context=args.referral_context,
        threshold=args.threshold,
    )


if __name__ == "__main__":
    main()
