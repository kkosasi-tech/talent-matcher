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


class MatchResult(BaseModel):
    jd: ParsedJD
    matches: list[StoryMatch]
    top_stories: list[StoryMatch]  # top 3 by relevance_score


class Score(BaseModel):
    overall: int = Field(ge=0, le=100)
    skill_match: int = Field(ge=0, le=100)
    experience_relevance: int = Field(ge=0, le=100)
    seniority_fit: int = Field(ge=0, le=100)
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


class GapAnalysis(BaseModel):
    missing_skills: list[str]
    partial_skills: list[str]
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


class PipelineResult(BaseModel):
    job_dir: str
    parsed_jd: ParsedJD
    matches: MatchResult
    score: Score
    compensation: Optional[CompensationReport] = None
    tailored_resume: Optional[str] = None
    cover_letter: Optional[str] = None
    gaps: Optional[GapAnalysis] = None
