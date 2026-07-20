# talent-matcher

Automated job application pipeline. Paste a job description, get a tailored resume, cover letter, and gap analysis — all grounded in your own STAR stories.

```
URL/file → JD Fetcher → Keyword Prefilter (free) → JD Parser → Story Matcher → Resume Matcher → Scorer
                              │                                                                     ├─(score < threshold)── jobs/no/
                              └─(too few keyword matches)── jobs/no/                                └─(score ≥ threshold)─┬─ Resume Tailor  ┐
                                                                                                                           ├─ Cover Letter   ├─ jobs/<output-dir>/
                                                                                                                           └─ Gap Analyzer   ┘
```

Uses [Claude](https://anthropic.com) via the Anthropic Python SDK. Each run costs roughly $0.01–0.05 depending on the size of your experience bank.

---

## Quick start

```bash
# 1. Clone and install dependencies
git clone https://github.com/yourhandle/talent-matcher.git
cd talent-matcher
pip install -r requirements.txt

# 2. Set your Anthropic API key
export ANTHROPIC_API_KEY=sk-ant-...

# 3. Copy and fill in the example files (see Setup below)
cp config.example.yaml config.yaml
cp data/resume.example.md data/resume.md
cp data/experience_bank.example.yaml data/experience_bank.yaml

# 4. Run against a job description
python pipeline.py --jd path/to/job.txt
```

Outputs land in `jobs/<company>-<role>-score<N>-<date>/`.

---

## Setup

### 1. `config.yaml`

Copy `config.example.yaml` → `config.yaml` and fill in your details:

```yaml
candidate:
  name: "Your Name"
  email: "you@example.com"
  phone: "+1 555 000 0000"
  linkedin: "linkedin.com/in/yourprofile/"

pipeline:
  threshold: 60       # minimum fit score (0–100) required to generate outputs
  model: "claude-sonnet-4-6"
```

`config.yaml` is gitignored — your personal info never leaves your machine.

### 2. `data/resume.md`

Copy `data/resume.example.md` → `data/resume.md` and replace with your actual resume in Markdown. The resume tailor agent rewrites this file for each application without fabricating experience.

### 3. `data/experience_bank.yaml`

Copy `data/experience_bank.example.yaml` → `data/experience_bank.yaml` and replace the examples with your real STAR stories.

This is the **single source of truth** for all pipeline outputs. The same stories power resume bullets, cover letter paragraphs, and interview prep. The more stories you add, the better the matching.

Each story follows this structure:

```yaml
stories:
  - id: unique-kebab-case-id
    title: One-line description of what you did
    company: Employer name
    role: Your title
    year: 2023
    tags:
      - python
      - architecture
      - cross-team
    situation: What was the context and problem?
    task: What were you specifically responsible for?
    action: What did you do, and how?
    result: What was the measurable outcome?
    metrics:
      - "Specific number: before → after"
    seniority_signals:
      - led
      - architected
      - mentored
```

Tips:
- Use past tense with concrete metrics in `result`
- `tags` drive keyword matching — include technologies, practices, and domain terms
- `seniority_signals` help the scorer assess level fit
- Add as many stories as you have; the matcher ranks them per JD

---

## Usage

```bash
# Basic run
python pipeline.py --jd path/to/job.txt

# Straight from a posting URL — Greenhouse, Lever, Ashby, SmartRecruiters and
# Workable via their official public APIs; any other page via its embedded
# schema.org JobPosting JSON-LD (plain-text extraction as a last resort)
python pipeline.py --url https://job-boards.greenhouse.io/acme/jobs/123

# With hiring manager name (personalises cover letter salutation)
python pipeline.py --jd path/to/job.txt --hiring-manager "Alex Smith"

# With a referral
python pipeline.py --jd path/to/job.txt \
  --referral-name "Jordan Lee" \
  --referral-context "distributed systems"

# Override the score threshold for a stretch role
python pipeline.py --jd path/to/job.txt --threshold 45
```

### Batch mode

Point `batch.py` at several posting URLs and it fetches them in parallel,
prefilters each against your experience-bank tags locally (zero tokens), tells
you how many match, and — after you confirm — runs the matching ones through
the pipeline in parallel:

```bash
python batch.py \
  https://job-boards.greenhouse.io/acme/jobs/123 \
  https://jobs.lever.co/someco/uuid-here

# or from a file (one URL per line, # for comments)
python batch.py --urls-file urls.txt

# fetch + prefilter only, spend nothing
python batch.py --urls-file urls.txt --dry-run

# non-interactive (cron, scripts): --yes is required to spend tokens
python batch.py --urls-file urls.txt --yes
```

Postings that fail the keyword prefilter are filed under `jobs/no/` immediately
without any API calls. `prefilter.min_keyword_matches` and `batch.max_workers`
in `config.yaml` control the cutoff and parallelism (`--min-matches` /
`--workers` override per run).

`urls.example.txt` documents the supported URL shapes with live examples. To
*discover* postings automatically instead of hand-collecting URLs, use the
companion [talent-dashboard](../talent-dashboard) project — its poller watches
company boards and keyword-search APIs, and `poller.py --export-urls`
regenerates `urls.txt` here from everything that cleared the prefilter.

### Output files

Each run creates a folder under `jobs/`:

```
jobs/acme-corp-senior-backend-engineer-score82-2026-06-16/
  jd.txt              original job description
  parsed_jd.json      structured extraction of the JD
  matches.json        STAR stories ranked by relevance
  match_report.json   resume vs. JD match: soft/hard skills, keywords, job title, degree,
                       resume word count (target 500-700), accomplishments check, missing skills
  score.json          fit scores (overall, skill_match, experience_relevance, seniority_fit,
                       resume_quality, missing_skills)
  compensation.md     salary (advertised, or web-researched if not) + eligibility restrictions
  compensation.json   same data, structured
  resume.md           tailored resume
  resume.docx         tailored resume (Word)
  cover_letter.md     generated cover letter
  cover_letter.docx   generated cover letter (Word)
  gaps.json           missing/partial skills + specific learning resources
```

Compensation research runs right after scoring, regardless of whether the score clears
`threshold` — so you always know the pay range and any eligibility restrictions (US
Citizenship, security clearance, no visa sponsorship, onsite-only, etc.) even for roles
you decide not to pursue.

If the fit score is below `threshold`, the pipeline stops after scoring, skips generating outputs, and files the run under `jobs/no/` instead of `jobs/` — so `jobs/` only holds applications worth reviewing.

---

## Project structure

```
talent-matcher/
  pipeline.py                  CLI orchestrator (file or URL input)
  batch.py                     multi-URL runner: parallel fetch → prefilter → parallel pipelines
  prefilter.py                 zero-token keyword filter vs experience-bank tags (also a CLI)
  config.yaml                  your personal config (gitignored)
  config.example.yaml          template to copy
  data/
    resume.md                  your resume (gitignored)
    resume.example.md          template to copy
    experience_bank.yaml       your STAR stories (gitignored)
    experience_bank.example.yaml  template to copy
  templates/
    cover_letter.jinja         Jinja template — structure + 5 LLM-filled slots
  agents/
    jd_fetcher.py              posting URL → JD text (ATS public APIs, JSON-LD fallback)
    jd_parser.py               extracts structured data from the JD
    story_matcher.py           scores each STAR story against the JD
    resume_matcher.py          matches resume vs. JD by category (skills/keywords/title/degree), checks word count + accomplishments
    scorer.py                  produces 0–100 fit score with rationale, informed by the resume match report
    salary_researcher.py       reports advertised salary, or web-researches a range; surfaces eligibility restrictions
    resume_tailor.py           rewrites resume for the role (no fabrication)
    resume_docx.py             renders tailored resume markdown to .docx
    cover_letter.py            LLM fills slots → Jinja renders final letter
    cover_letter_docx.py       renders cover letter markdown to .docx
    gap_analyzer.py            missing/partial skills + learning resources
  models/
    schemas.py                 Pydantic types for all pipeline data
    utils.py                   shared JSON parsing helper
  jobs/                        generated outputs (gitignored)
```

---

## Requirements

- Python 3.11+
- `ANTHROPIC_API_KEY` environment variable
- See `requirements.txt` for package dependencies

---

## VS Code

A `.vscode/launch.json` is included with run configurations:

- **Run Pipeline (example JD)** — hardcoded path, just press F5
- **Run Pipeline (prompt for JD path)** — prompts for path at launch
- **Run Pipeline (with hiring manager)** — prompts for path + manager name
- **Debug: JD Parser / Story Matcher / Cover Letter** — run individual agents in isolation
