# talent-matcher

Automated job application pipeline. Paste a job description, get a tailored resume, cover letter, and gap analysis — all grounded in your own STAR stories.

```
JD Parser → Story Matcher → Scorer
                                 └─(score ≥ threshold)─┬─ Resume Tailor  ┐
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

# With hiring manager name (personalises cover letter salutation)
python pipeline.py --jd path/to/job.txt --hiring-manager "Alex Smith"

# With a referral
python pipeline.py --jd path/to/job.txt \
  --referral-name "Jordan Lee" \
  --referral-context "distributed systems"

# Override the score threshold for a stretch role
python pipeline.py --jd path/to/job.txt --threshold 45
```

### Output files

Each run creates a folder under `jobs/`:

```
jobs/acme-corp-senior-backend-engineer-score82-2026-06-16/
  jd.txt              original job description
  parsed_jd.json      structured extraction of the JD
  matches.json        STAR stories ranked by relevance
  score.json          fit scores (overall, skill_match, experience_relevance, seniority_fit)
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

If the fit score is below `threshold`, the pipeline stops after scoring and skips generating outputs.

---

## Project structure

```
talent-matcher/
  pipeline.py                  CLI orchestrator
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
    jd_parser.py               extracts structured data from the JD
    story_matcher.py           scores each STAR story against the JD
    scorer.py                  produces 0–100 fit score with rationale
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
