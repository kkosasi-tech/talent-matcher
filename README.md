# talent-matcher

Automated job application pipeline. Paste a job description, get a tailored resume, cover letter, gap analysis, and mock interview prep — all grounded in your own STAR stories.

```
URL/file → JD Fetcher → Keyword Prefilter (free) → JD Parser → Story Matcher → Resume Matcher → Scorer → Salary Researcher
                              │                                                                              ├─(score < threshold)── jobs/unfit/
                              └─(too few keyword matches)── jobs/unfit/                                      └─(score ≥ threshold)─┬─ Resume Tailor    ┐
                                                                                                                                     ├─ Cover Letter     │
                                                                                                                                     ├─ Gap Analyzer      ├─ jobs/candidate/<output-dir>/
                                                                                                                                     └─ Interview Prep    ┘
```

Backed by [Claude](https://anthropic.com) (Anthropic API) or any local LLM via [Ollama](https://ollama.com) — you pick in `config.yaml`. With the Anthropic API each run costs roughly $0.01–0.05 depending on the size of your experience bank; local models are free.

---

## Quick start

```bash
# 1. Clone and install dependencies
git clone https://github.com/yourhandle/talent-matcher.git
cd talent-matcher
pip install -r requirements.txt

# 2. Set your Anthropic API key (default provider), or skip straight to a local LLM:
export ANTHROPIC_API_KEY=sk-ant-...
# ...or with Ollama: install https://ollama.com, run `ollama pull qwen2.5:14b`,
# and set `llm.provider: ollama` in config.yaml (see Setup below)

# 3. Copy and fill in the example files (see Setup below)
cp config.example.yaml config.yaml
cp data/resume.example.md data/resume.md
cp data/experience_bank.example.yaml data/experience_bank.yaml

# 4. Run against a job description
python pipeline.py --jd path/to/job.txt
```

Outputs land in `jobs/candidate/<company>-<role>-score<N>-<date>/`.

---

## Setup

### 1. Choose an LLM provider

The default backend is the Anthropic API. To use a **local LLM via [Ollama](https://ollama.com)** instead, install Ollama, pull a model, and switch one setting:

```bash
ollama pull qwen2.5:14b     # or any model you like
```

```yaml
# config.yaml
llm:
  provider: ollama           # default is: anthropic
  ollama_base_url: "http://localhost:11434"
  ollama_model: "qwen2.5:14b"
  ollama_timeout: 600        # seconds, for slow local models
```

With the **Anthropic API** provider (default), the key is read from the `ANTHROPIC_API_KEY` environment variable (recommended) or from `anthropic.api_key` in `config.yaml` as a fallback:

```bash
export ANTHROPIC_API_KEY=sk-ant-...
```

> Note: the Salary Researcher's live web lookups use Anthropic's `web_search` tool, which is only available on the `anthropic` provider. With `ollama`, salary estimates come from the model's own knowledge.

### 2. `config.yaml`

Copy `config.example.yaml` → `config.yaml` and fill in your details:

```yaml
candidate:
  name: "Your Name"
  email: "you@example.com"
  phone: "+1 555 000 0000"
  linkedin: "linkedin.com/in/yourprofile/"

pipeline:
  threshold: 60              # minimum fit score (0–100) required to generate outputs
  model: "claude-sonnet-4-6" # Claude model used by all agents
  top_stories: 3             # number of top STAR stories passed into each prompt
```

`config.yaml` is gitignored — your personal info never leaves your machine.

### 3. `data/resume.md`

Copy `data/resume.example.md` → `data/resume.md` and replace with your actual resume in Markdown. The resume tailor agent rewrites this file for each application without fabricating experience.

### 4. `data/experience_bank.yaml`

Copy `data/experience_bank.example.yaml` → `data/experience_bank.yaml` and replace the examples with your real STAR stories.

This is the **single source of truth** for all pipeline outputs. The same stories power resume bullets, cover letter paragraphs, gap analysis, and interview prep. The more stories you add, the better the matching.

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
- Write full detail into `situation`/`action`/`result` even if it's more than you'd put on a resume —
  `resume_matcher` reads the whole story bank, not just `resume.md`. A skill only mentioned here (e.g.
  a specific tool or environment used) is still counted as matched and surfaced to `resume_tailor` as
  a `recoverable_skill`, instead of being wrongly flagged as missing just because it isn't on the resume

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

Postings that fail the keyword prefilter are filed under `jobs/unfit/` immediately
without any API calls. `prefilter.min_keyword_matches` and `batch.max_workers`
in `config.yaml` control the cutoff and parallelism (`--min-matches` /
`--workers` override per run).

`urls.example.txt` documents the supported URL shapes with live examples. To
*discover* postings automatically instead of hand-collecting URLs, use the
companion [talent-dashboard](../talent-dashboard) project — its poller watches
company boards and keyword-search APIs, and `poller.py --export-urls`
regenerates `urls.txt` here from everything that cleared the prefilter.

### Output files

Each run creates a folder under `jobs/candidate/`:

```
jobs/candidate/acme-corp-senior-backend-engineer-score82-2026-06-16/
  jd.txt                  original job description
  parsed_jd.json          structured extraction of the JD
  matches.json            STAR stories ranked by relevance
  match_report.json       resume vs. JD match: soft/hard skills, keywords, job title, degree,
                          resume word count (target 500-700), accomplishments check, missing skills,
                          and recoverable_skills (demonstrated in your STAR stories but not yet on the resume)
  score.json              fit scores (overall, skill_match, experience_relevance, seniority_fit,
                          resume_quality, missing_skills)
  compensation.md         salary (advertised or web-researched) + eligibility restrictions
  compensation.json       same data, structured
  resume.md               tailored resume
  resume.docx             tailored resume (Word)
  cover_letter.md         generated cover letter
  cover_letter.docx       generated cover letter (Word)
  gaps.md                 skill gap learning plan (missing skills, resources, priority order)
  gaps.json               same data, structured
  interview_prep.md       mock interview questions & sample answers
  interview_prep.docx     interview prep (Word)
  interview_prep.json     same data, structured
```

**Compensation research** runs right after scoring regardless of whether the score clears `threshold` — so you always know the pay range and any eligibility restrictions (US Citizenship, security clearance, no visa sponsorship, onsite-only, etc.) even for roles you decide not to pursue.

**Interview prep** is calibrated to the JD's seniority level and the candidate's specific fit gaps. Questions span four categories: behavioral (STAR format), technical (depth matched to level), situational, and culture/fit. Sample answers are grounded in the candidate's actual experience from the resume and STAR stories.

If the fit score is below `threshold`, the pipeline stops after compensation research, skips generating outputs, and files the run under `jobs/unfit/` instead of `jobs/candidate/` — so `jobs/candidate/` only holds applications worth reviewing.

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
    resume_matcher.py          matches resume vs. JD by category (skills/keywords/title/degree), checks word count + accomplishments, cross-references the STAR story bank for skills the resume omits
    scorer.py                  produces 0–100 fit score with rationale, informed by the resume match report
    salary_researcher.py       reports advertised salary, or web-researches a range; surfaces eligibility restrictions
    resume_tailor.py           rewrites resume for the role (no fabrication beyond what's evidenced in the resume or story bank)
    resume_docx.py             renders markdown to .docx (used by resume and interview prep)
    cover_letter.py            LLM fills slots → Jinja renders final letter
    cover_letter_docx.py       renders cover letter markdown to .docx
    gap_analyzer.py            missing/partial skills + prioritised learning resources
    interview_prep.py          mock questions & sample answers calibrated to seniority and fit gaps
  models/
    schemas.py                 Pydantic types for all pipeline data
    utils.py                   shared JSON parsing helper
  jobs/                        generated outputs (gitignored)
```

---

## Requirements

- Python 3.11+
- An LLM backend: `ANTHROPIC_API_KEY` (default provider, or `llm.provider: anthropic` in `config.yaml`), or a running Ollama instance (`llm.provider: ollama`)
- See `requirements.txt` for package dependencies

---

## VS Code

A `.vscode/launch.json` is included with run configurations:

- **Run Pipeline (example JD)** — hardcoded path, just press F5
- **Run Pipeline (prompt for JD path)** — prompts for path at launch
- **Run Pipeline (with hiring manager)** — prompts for path + manager name
- **Debug: JD Parser / Story Matcher / Resume Matcher / Cover Letter** — run individual agents in isolation
