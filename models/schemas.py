from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Optional


class ParsedJD(BaseModel):
    company: str
    role: str
    required_skills: list[str]
    preferred_skills: list[str]
    responsibilities: list[str]
    seniority_level: str  # junior / mid / senior / staff / principal
    domain: str  # e.g. backend, data, fullstack, ml
    keywords: list[str]
    location: Optional[str] = None  # work location / remote, if stated
    salary_advertised: Optional[str] = None  # comp range if stated in the JD, else None
    restrictions: list[str] = Field(default_factory=list)  # e.g. "US Citizenship required", "Security clearance"
    raw_text: str


class StoryMatch(BaseModel):
    story_id: str
    story_title: str
    relevance_score: float = Field(ge=0.0, le=1.0)
    matched_keywords: list[str]
    star_summary: str  # condensed STAR for use in prompts
    company: str = ""  # from the experience bank entry, not the LLM — pins the story to a resume job entry
    role: str = ""
    year: str = ""


class MatchResult(BaseModel):
    jd: ParsedJD
    matches: list[StoryMatch]
    top_stories: list[StoryMatch]  # top 3 by relevance_score


class CategoryMatch(BaseModel):
    score: int = Field(ge=0, le=100)
    matched: list[str] = Field(default_factory=list)
    missing: list[str] = Field(default_factory=list)
    notes: str = ""


class RecoverableSkill(BaseModel):
    skill: str
    evidence: str  # what the story text actually says that demonstrates this skill
    story_id: str  # id of the grounding STAR story
    company: str = ""  # from the experience bank entry, not the LLM — pins the story to a resume job entry
    role: str = ""
    year: str = ""


class MatchReport(BaseModel):
    soft_skills: CategoryMatch
    required_skills: CategoryMatch  # hard skills from the JD's required_skills list
    preferred_skills: CategoryMatch  # hard skills from the JD's preferred_skills ("nice-to-have") list
    keywords: CategoryMatch
    job_title_match: CategoryMatch
    degree_match: CategoryMatch
    resume_word_count: int
    resume_word_count_ok: bool  # True if within [resume_word_min, resume_word_max]
    resume_word_min: int
    resume_word_max: int
    accomplishments_present: bool
    accomplishments_notes: str
    missing_skills: list[str] = Field(default_factory=list)  # union of hard/soft/keyword gaps, evidenced nowhere
    recoverable_skills: list[RecoverableSkill] = Field(default_factory=list)  # demonstrated in stories, absent from resume text


class Score(BaseModel):
    overall: int = Field(ge=0, le=100)
    skill_match: int = Field(ge=0, le=100)
    experience_relevance: int = Field(ge=0, le=100)
    seniority_fit: int = Field(ge=0, le=100)
    resume_quality: int = Field(ge=0, le=100)  # resume length + accomplishments
    missing_skills: list[str] = Field(default_factory=list)
    rationale: str
    proceed: bool  # True if overall >= threshold


class CoverLetterSlots(BaseModel):
    opening_hook: str
    fit_statement: str
    star_paragraph_1: str
    star_paragraph_2: Optional[str] = None
    closing: str


class CoverLetterContext(BaseModel):
    date: str
    candidate_name: str
    candidate_email: str
    candidate_phone: str
    candidate_linkedin: Optional[str] = None
    hiring_manager: Optional[str] = None
    referral_name: Optional[str] = None
    referral_context: Optional[str] = None
    slots: CoverLetterSlots


class PartialSkill(BaseModel):
    skill: str
    reason: str


class GapAnalysis(BaseModel):
    missing_skills: list[str]
    partial_skills: list[PartialSkill]
    learning_resources: list[dict]  # [{"skill": str, "resource": str, "type": str}]
    priority_order: list[str]
    estimated_weeks: dict[str, int]  # {"skill": weeks_to_competency}


class CompensationReport(BaseModel):
    company: str
    role: str
    location: Optional[str] = None
    salary_advertised: Optional[str] = None  # set when the JD stated a range
    estimated_range: Optional[str] = None  # set when researched from the web
    research_summary: str  # human-readable explanation of the figure / sources
    sources: list[str] = Field(default_factory=list)  # URLs backing the estimate
    restrictions: list[str] = Field(default_factory=list)  # citizenship / clearance / work-auth limits


class InterviewQuestion(BaseModel):
    category: str  # behavioral / technical / situational / culture_fit
    question: str
    sample_answer: str
    tips: list[str]


class InterviewPrep(BaseModel):
    role: str
    company: str
    seniority_level: str
    questions: list[InterviewQuestion]


class PipelineResult(BaseModel):
    job_dir: str
    parsed_jd: ParsedJD
    matches: MatchResult
    match_report: MatchReport
    score: Score
    compensation: Optional[CompensationReport] = None
    tailored_resume: Optional[str] = None
    cover_letter: Optional[str] = None
    gaps: Optional[GapAnalysis] = None
    interview_prep: Optional[InterviewPrep] = None
