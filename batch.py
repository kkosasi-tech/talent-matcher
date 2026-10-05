"""Batch runner: fetch posting URLs, prefilter locally, then pipeline in parallel.

Usage:
    python batch.py URL [URL ...]
    python batch.py --urls-file urls.txt [--threshold 60] [--min-matches 3] \
        [--workers 3] [--dry-run] [--yes]

Flow (token spend only happens in step 3):
    1. Fetch every URL in parallel via ATS APIs / JSON-LD (free).
    2. Prefilter each JD against your experience-bank keywords (free) and
       report how many postings match before anything is sent to the API.
    3. After confirmation, run matching postings through the pipeline in
       parallel subprocesses. Runs scoring below the threshold are filed in
       jobs/unfit/, passing runs in jobs/candidate/. Postings that fail the
       prefilter are filed in jobs/unfit/ immediately without spending any
       tokens.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from agents.jd_fetcher import FetchedJob, FetchError, fetch_jd
from config import load_config
from prefilter import PrefilterResult, prefilter_jd

ROOT = Path(__file__).parent
FETCH_WORKERS = 8


@dataclass
class BatchItem:
    url: str
    fetched: FetchedJob | None = None
    fetch_error: str | None = None
    prefilter: PrefilterResult | None = None
    score: int | None = None
    proceed: bool | None = None
    resume_quality: int | None = None
    missing_skills: list[str] = field(default_factory=list)
    job_dir: str | None = None
    run_error: str | None = None
    output: str = ""

    @property
    def label(self) -> str:
        if self.fetched and self.fetched.title:
            return f"{self.fetched.title} @ {self.fetched.company or '?'}"
        return self.url


def _slugify(text: str) -> str:
    return "".join(c if c.isalnum() or c in "-_" else "-" for c in text).lower()


def _fetch_all(urls: list[str]) -> list[BatchItem]:
    items = [BatchItem(url=u) for u in urls]
    with ThreadPoolExecutor(max_workers=min(FETCH_WORKERS, len(items))) as pool:
        futures = {pool.submit(fetch_jd, item.url): item for item in items}
        for future in as_completed(futures):
            item = futures[future]
            try:
                item.fetched = future.result()
            except Exception as e:  # requests errors, FetchError, bad JSON...
                item.fetch_error = str(e)
    return items


def _file_rejected(item: BatchItem) -> Path:
    """Record a prefilter-rejected posting under jobs/unfit/ (no tokens spent)."""
    fetched, pf = item.fetched, item.prefilter
    slug = _slugify(
        f"{fetched.company or 'unknown'}-{fetched.title or 'unknown'}"
        f"-prefilter{pf.matched_count}-{date.today().isoformat()}"
    )
    out = ROOT / "jobs" / "unfit" / slug
    out.mkdir(parents=True, exist_ok=True)
    (out / "jd.txt").write_text(fetched.text)
    (out / "prefilter.json").write_text(json.dumps(
        {
            "url": item.url,
            "source": fetched.source,
            "title": fetched.title,
            "company": fetched.company,
            "location": fetched.location,
            "reason": "below keyword prefilter — pipeline not run, no tokens spent",
            **pf.model_dump(),
        },
        indent=2,
    ))
    return out


def _run_pipeline(item: BatchItem, threshold: int | None) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        jd_file = Path(tmp) / "jd.txt"
        result_file = Path(tmp) / "result.json"
        jd_file.write_text(item.fetched.text)
        cmd = [sys.executable, str(ROOT / "pipeline.py"),
               "--jd", str(jd_file), "--result-json", str(result_file)]
        if threshold is not None:
            cmd += ["--threshold", str(threshold)]
        proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
        item.output = proc.stdout + proc.stderr
        if proc.returncode != 0 or not result_file.exists():
            item.run_error = f"pipeline exited {proc.returncode}"
            return
        summary = json.loads(result_file.read_text())
        item.score = summary["score"]
        item.proceed = summary["proceed"]
        item.resume_quality = summary.get("resume_quality")
        item.missing_skills = summary.get("missing_skills", [])
        item.job_dir = summary["job_dir"]


def main():
    parser = argparse.ArgumentParser(description="Batch job application runner")
    parser.add_argument("urls", nargs="*", help="Job posting URLs")
    parser.add_argument("--urls-file", help="File with one URL per line (# for comments)")
    parser.add_argument("--threshold", type=int, help="Minimum pipeline score (overrides config.yaml)")
    parser.add_argument("--min-matches", type=int, help="Keyword overlaps required to run the pipeline")
    parser.add_argument("--workers", type=int, help="Parallel pipeline runs (default: batch.max_workers or 3)")
    parser.add_argument("--dry-run", action="store_true", help="Fetch + prefilter only; spend no tokens")
    parser.add_argument("--yes", action="store_true", help="Skip the confirmation prompt")
    args = parser.parse_args()

    urls: list[str] = list(args.urls)
    if args.urls_file:
        for line in Path(args.urls_file).read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                urls.append(line)
    urls = list(dict.fromkeys(urls))  # dedupe, keep order
    if not urls:
        parser.error("no URLs given (pass them as arguments or via --urls-file)")

    cfg = load_config()
    workers = args.workers or cfg.get("batch", {}).get("max_workers", 3)

    print(f"==> Fetching {len(urls)} posting(s) in parallel...")
    items = _fetch_all(urls)
    fetched = [i for i in items if i.fetched]
    failed = [i for i in items if i.fetch_error]
    for item in failed:
        print(f"    FAILED  {item.url}\n            {item.fetch_error}")

    print("==> Prefiltering against experience-bank keywords (no tokens spent)...")
    for item in fetched:
        item.prefilter = prefilter_jd(item.fetched.text, min_matches=args.min_matches)

    matching = [i for i in fetched if i.prefilter.passed]
    rejected = [i for i in fetched if not i.prefilter.passed]

    for item in fetched:
        pf = item.prefilter
        mark = "MATCH " if pf.passed else "skip  "
        kws = ", ".join(pf.matched_keywords[:6]) + ("..." if pf.matched_count > 6 else "")
        print(f"    {mark}[{pf.matched_count:>2} kw] {item.label}")
        if pf.matched_count:
            print(f"           {kws}")

    print(f"\n==> {len(matching)} of {len(fetched)} fetched posting(s) match your keywords "
          f"(>= {matching[0].prefilter.min_required if matching else rejected[0].prefilter.min_required if rejected else '?'} overlaps)."
          + (f" {len(failed)} URL(s) failed to fetch." if failed else ""))

    for item in rejected:
        out = _file_rejected(item)
        print(f"    Filed under {out.relative_to(ROOT)} (pipeline not run)")

    if args.dry_run:
        print("\n--dry-run: stopping before the pipeline. No tokens were spent.")
        return

    if not matching:
        print("\nNothing to run.")
        return

    if not args.yes:
        if not sys.stdin.isatty():
            print("\nNot a terminal and --yes not given — aborting before spending tokens.",
                  file=sys.stderr)
            sys.exit(2)
        answer = input(f"\nRun the pipeline on {len(matching)} posting(s)? "
                       f"(~$0.01-0.05 each) [y/N] ").strip().lower()
        if answer not in ("y", "yes"):
            print("Aborted.")
            return

    print(f"\n==> Running {len(matching)} pipeline(s), {workers} in parallel...")
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_run_pipeline, item, args.threshold): item for item in matching}
        for future in as_completed(futures):
            item = futures[future]
            future.result()  # _run_pipeline stores everything on the item
            if item.run_error:
                print(f"\n--- {item.label}: ERROR ({item.run_error}) ---")
                print(item.output.strip())
            else:
                verdict = "PASS" if item.proceed else "below threshold"
                gaps = f", {len(item.missing_skills)} gap(s)" if item.missing_skills else ""
                print(f"    done  [{item.score:>3}] {verdict:<16} "
                      f"resume_quality={item.resume_quality}{gaps}  {item.label}")

    print("\n==> Batch summary")
    for item in sorted(matching, key=lambda i: -(i.score or -1)):
        if item.run_error:
            print(f"    ERROR   {item.label}")
        else:
            arrow = "jobs/candidate/" if item.proceed else "jobs/unfit/"
            rq = str(item.resume_quality) if item.resume_quality is not None else "?"
            skills_note = f" (missing: {', '.join(item.missing_skills[:4])}" + \
                (", ..." if len(item.missing_skills) > 4 else "") + ")" if item.missing_skills else ""
            print(f"    {item.score:>3}  ->  {arrow:<9} resume_quality={rq:<3} "
                  f"{item.job_dir}{skills_note}")
    for item in rejected:
        print(f"    skip ->  jobs/unfit/   {item.label} (prefilter {item.prefilter.matched_count} kw)")
    for item in failed:
        print(f"    fetch failed        {item.url}")


if __name__ == "__main__":
    main()
