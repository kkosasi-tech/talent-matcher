# talent-matcher

Automated job application pipeline. Paste a job description, get a tailored resume, cover letter, gap analysis, and mock interview prep — all grounded in your own STAR stories.

```
JD Parser → Story Matcher → Scorer → Salary Researcher
                                   └─(score ≥ threshold)─┬─ Resume Tailor    ┐
                                                          ├─ Cover Letter     │
                                                          ├─ Gap Analyzer     ├─ jobs/<output-dir>/
                                                          └─ Interview Prep   ┘
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

### 1. API key

The pipeline reads your Anthropic API key from the `ANTHROPIC_API_KEY` environment variable (recommended), or from `anthropic.api_key` in `config.yaml` as a fallback.

```bash
export ANTHROPIC_API_KEY=sk-ant-...
```

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
  jd.txt                  original job description
  parsed_jd.json          structured extraction of the JD
  matches.json            STAR stories ranked by relevance
  score.json              fit scores (overall, skill_match, experience_relevance, seniority_fit)
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

If the fit score is below `threshold`, the pipeline stops after compensation research and skips generating outputs.

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
    salary_researcher.py       reports advertised salary or web-researches a range; surfaces eligibility restrictions
    resume_tailor.py           rewrites resume for the role (no fabrication)
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
- `ANTHROPIC_API_KEY` environment variable (or set in `config.yaml`)
- See `requirements.txt` for package dependencies

---

## VS Code

A `.vscode/launch.json` is included with run configurations:

- **Run Pipeline (example JD)** — hardcoded path, just press F5
- **Run Pipeline (prompt for JD path)** — prompts for path at launch
- **Run Pipeline (with hiring manager)** — prompts for path + manager name
- **Debug: JD Parser / Story Matcher / Cover Letter** — run individual agents in isolation
