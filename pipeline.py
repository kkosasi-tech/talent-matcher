"""
Job application pipeline orchestrator.

Usage:
    python pipeline.py --jd path/to/jd.txt \
        [--hiring-manager "Alex Smith"] \
        [--referral-name "Jane Doe"] \
        [--referral-context "backend engineering"] \
        [--threshold 60] \
        [--result-json path/to/summary.json]

    python pipeline.py --url https://job-boards.greenhouse.io/acme/jobs/123

Runs that score below the threshold are filed under jobs/no/; passing runs
land in jobs/ for review. Candidate info (name, email, phone, linkedin) is
read from config.yaml.
"""

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from pathlib import Path

from config import load_config

from agents.cover_letter import generate_cover_letter
from agents.gap_analyzer import analyze_gaps, render_gaps_md
from agents.interview_prep import generate_interview_prep, render_interview_prep_md
from agents.jd_parser import parse_jd
from agents.cover_letter_docx import markdown_to_docx as cover_letter_to_docx
from agents.resume_docx import markdown_to_docx as resume_to_docx
from agents.resume_matcher import match_resume
from agents.resume_tailor import tailor_resume
from agents.salary_researcher import render_compensation_md, research_compensation
from agents.scorer import score_match
from agents.story_matcher import match_stories
from models.schemas import PipelineResult

def _make_job_dir(company: str, role: str, score: int, proceed: bool) -> Path:
    slug = f"{company}-{role}-score{score}-{date.today().isoformat()}"
    slug = "".join(c if c.isalnum() or c in "-_" else "-" for c in slug).lower()
    base = Path("jobs") if proceed else Path("jobs") / "no"
    job_dir = base / slug
    job_dir.mkdir(parents=True, exist_ok=True)
    return job_dir


def run(
    jd_text: str,
    hiring_manager: str | None = None,
    referral_name: str | None = None,
    referral_context: str | None = None,
    threshold: int | None = None,
) -> PipelineResult:
    cfg = load_config()
    candidate = cfg["candidate"]
    candidate_name = candidate["name"]
    candidate_email = candidate["email"]
    candidate_phone = candidate.get("phone", "")
    candidate_linkedin = candidate.get("linkedin")
    pipeline_cfg = cfg.get("pipeline", {})
    if threshold is None:
        threshold = pipeline_cfg.get("threshold", 60)
    top_n = pipeline_cfg.get("top_stories", 3)

    print("==> [1/6] Parsing job description...")
    parsed_jd = parse_jd(jd_text)
    print(f"    Role: {parsed_jd.role} @ {parsed_jd.company}")

    print("==> [2/6] Matching STAR stories to JD...")
    match = match_stories(parsed_jd, top_n=top_n)
    print(f"    Top match: {match.top_stories[0].story_title if match.top_stories else 'none'}")

    print("==> [3/6] Matching resume against JD...")
    match_report = match_resume(parsed_jd)
    print(f"    Resume: {match_report.resume_word_count} words "
          f"({'within' if match_report.resume_word_count_ok else 'outside'} 500-700 target)")
    if match_report.missing_skills:
        print(f"    Missing skills flagged: {', '.join(match_report.missing_skills)}")

    print("==> [4/6] Scoring fit...")
    score = score_match(match, match_report, threshold=threshold)
    print(f"    Score: {score.overall}/100 — proceed: {score.proceed}")
    print(f"    {score.rationale}")

    job_dir = _make_job_dir(parsed_jd.company, parsed_jd.role, score.overall, score.proceed)
    (job_dir / "jd.txt").write_text(jd_text)
    (job_dir / "parsed_jd.json").write_text(parsed_jd.model_dump_json(indent=2))
    (job_dir / "matches.json").write_text(match.model_dump_json(indent=2))
    (job_dir / "match_report.json").write_text(match_report.model_dump_json(indent=2))
    (job_dir / "score.json").write_text(score.model_dump_json(indent=2))
    print(f"    Output dir: {job_dir}")

    print("==> Researching compensation & eligibility restrictions...")
    if parsed_jd.salary_advertised:
        print(f"    Salary advertised in JD: {parsed_jd.salary_advertised}")
    else:
        print("    No salary in JD — searching the web for a typical range...")
    try:
        compensation = research_compensation(parsed_jd)
        (job_dir / "compensation.json").write_text(compensation.model_dump_json(indent=2))
        (job_dir / "compensation.md").write_text(render_compensation_md(compensation))
        print(f"    {compensation.salary_advertised or compensation.estimated_range or 'no estimate'}")
        if compensation.restrictions:
            print(f"    Restrictions: {', '.join(compensation.restrictions)}")
    except Exception as e:
        compensation = None
        print(f"    WARNING: compensation research failed: {e}")

    if not score.proceed:
        print(f"\n  Score {score.overall} is below threshold {threshold}. Stopping pipeline.")
        print(f"  Outputs filed under {job_dir}/ for the record.")
        print("  Run with --threshold lower to force generation, or address the gaps first.")
        return PipelineResult(
            job_dir=str(job_dir),
            parsed_jd=parsed_jd,
            matches=match,
            match_report=match_report,
            score=score,
            compensation=compensation,
        )

    print("==> [5/6] Generating tailored resume, cover letter, gap analysis, interview prep (parallel)...")

    tailored_resume = None
    cover_letter = None
    gaps = None
    interview_prep = None

    def _tailor():
        return tailor_resume(match, score, match_report=match_report)

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

    def _interview():
        return generate_interview_prep(match, score)

    tasks = {"tailor": _tailor, "cover": _cover, "gaps": _gaps, "interview": _interview}

    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {executor.submit(fn): name for name, fn in tasks.items()}
        for future in as_completed(futures):
            name = futures[future]
            try:
                result = future.result()
                if name == "tailor":
                    tailored_resume = result
                elif name == "cover":
                    cover_letter = result
                elif name == "gaps":
                    gaps = result
                elif name == "interview":
                    interview_prep = result
                print(f"    {name} done")
            except Exception as e:
                print(f"    WARNING: {name} failed: {e}")

    if tailored_resume:
        (job_dir / "resume.md").write_text(tailored_resume)
        resume_to_docx(tailored_resume, job_dir / "resume.docx")
    if cover_letter:
        (job_dir / "cover_letter.md").write_text(cover_letter)
        cover_letter_to_docx(cover_letter, job_dir / "cover_letter.docx")
    if gaps:
        (job_dir / "gaps.json").write_text(gaps.model_dump_json(indent=2))
        (job_dir / "gaps.md").write_text(render_gaps_md(gaps, parsed_jd.role, parsed_jd.company))
    if interview_prep:
        (job_dir / "interview_prep.json").write_text(interview_prep.model_dump_json(indent=2))
        interview_prep_md = render_interview_prep_md(interview_prep)
        (job_dir / "interview_prep.md").write_text(interview_prep_md)
        resume_to_docx(interview_prep_md, job_dir / "interview_prep.docx")

    print("==> [6/6] Done.")
    print(f"\nOutputs in {job_dir}/")
    print(f"  match_report.json     — resume/JD category match report")
    if compensation:
        print(f"  compensation.md       — salary estimate & eligibility restrictions")
    if tailored_resume:
        print(f"  resume.md             — tailored resume")
        print(f"  resume.docx           — tailored resume (Word)")
    if cover_letter:
        print(f"  cover_letter.md       — cover letter")
        print(f"  cover_letter.docx     — cover letter (Word)")
    if gaps:
        print(f"  gaps.md               — skill gap learning plan")
        print(f"  gaps.json             — structured gap data")
    if interview_prep:
        print(f"  interview_prep.md     — mock interview questions & sample answers")
        print(f"  interview_prep.docx   — interview prep (Word)")
        print(f"  interview_prep.json   — structured interview prep data")

    return PipelineResult(
        job_dir=str(job_dir),
        parsed_jd=parsed_jd,
        matches=match,
        match_report=match_report,
        score=score,
        compensation=compensation,
        tailored_resume=tailored_resume,
        cover_letter=cover_letter,
        gaps=gaps,
        interview_prep=interview_prep,
    )


def main():
    parser = argparse.ArgumentParser(description="Job application pipeline")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--jd", help="Path to job description text file")
    source.add_argument("--url", help="Job posting URL (ATS API or JobPosting JSON-LD)")
    parser.add_argument("--hiring-manager", help="Hiring manager name if known")
    parser.add_argument("--referral-name", help="Referral contact name")
    parser.add_argument("--referral-context", help="Context about the referral")
    parser.add_argument("--threshold", type=int, help="Minimum score to proceed (overrides config.yaml)")
    parser.add_argument("--result-json", help="Write a machine-readable run summary to this path")
    args = parser.parse_args()

    if args.url:
        from agents.jd_fetcher import fetch_jd

        print(f"==> Fetching JD from {args.url}")
        fetched = fetch_jd(args.url)
        print(f"    [{fetched.source}] {fetched.title} @ {fetched.company}")
        jd_text = fetched.text
    else:
        jd_path = Path(args.jd)
        if not jd_path.exists():
            print(f"Error: JD file not found: {args.jd}", file=sys.stderr)
            sys.exit(1)
        jd_text = jd_path.read_text()

    result = run(
        jd_text=jd_text,
        hiring_manager=args.hiring_manager,
        referral_name=args.referral_name,
        referral_context=args.referral_context,
        threshold=args.threshold,
    )

    if args.result_json:
        summary = {
            "job_dir": result.job_dir,
            "company": result.parsed_jd.company,
            "role": result.parsed_jd.role,
            "score": result.score.overall,
            "proceed": result.score.proceed,
            "missing_skills": result.score.missing_skills,
        }
        Path(args.result_json).write_text(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
