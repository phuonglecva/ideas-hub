from datetime import datetime
from uuid import UUID

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class SourceCreate(BaseModel):
    name: str
    domain: str
    source_type: str = "news"
    feed_url: str | None = None
    trust_score: float = Field(0.5, ge=0, le=1)

    @field_validator("name", "domain", "source_type")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be empty")
        return value

    @field_validator("feed_url")
    @classmethod
    def normalize_feed_url(cls, value: str | None) -> str | None:
        return value.strip() or None if value is not None else None


class SourceUpdate(BaseModel):
    name: str | None = None
    domain: str | None = None
    source_type: str | None = None
    feed_url: str | None = None
    trust_score: float | None = Field(None, ge=0, le=1)
    enabled: bool | None = None

    @field_validator("name", "domain", "source_type")
    @classmethod
    def strip_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("must not be empty")
        return value

    @field_validator("feed_url")
    @classmethod
    def normalize_optional_feed_url(cls, value: str | None) -> str | None:
        return value.strip() or None if value is not None else None


class SourceOut(SourceCreate):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    enabled: bool
    created_at: datetime


class SourceCandidateCreate(BaseModel):
    name: str | None = None
    homepage_url: str
    feed_url: str | None = None


class SourceCandidateEvidenceOut(BaseModel):
    article_id: UUID
    article_title: str
    article_url: str
    source_name: str
    discovered_url: str


class SourceCandidateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    name: str | None
    domain: str
    homepage_url: str
    feed_url: str | None
    discovery_url: str | None
    discovery_method: str
    status: str
    score: float
    score_breakdown: dict
    entry_count: int
    extraction_rate: float
    mention_count: int
    source_count: int
    sample_headlines: list
    latest_entry_at: datetime | None
    last_checked_at: datetime | None
    failure_reason: str | None
    retry_count: int
    source_id: UUID | None
    created_at: datetime
    evidence: list[SourceCandidateEvidenceOut] = Field(default_factory=list)


class CrawlRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    source_id: UUID
    task_id: str | None
    trigger: str
    status: str
    limit: int
    discovered: int
    created: int
    events_updated: int
    opportunities: int
    failures: list
    error: str | None
    queued_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    duration_ms: int | None


class ArticleInsight(BaseModel):
    entities: list[str] = []
    industries: list[str] = []
    affected_groups: list[str] = []
    problems: list[str] = []
    changes: list[str] = []
    claims: list[str] = []
    metrics: list[str] = []
    regulations: list[str] = []


class ArticleUpdate(BaseModel):
    title: str | None = None
    canonical_url: str | None = None
    author: str | None = None
    published_at: datetime | None = None
    extracted: ArticleInsight | None = None

    @field_validator("title", "canonical_url")
    @classmethod
    def strip_article_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("must not be empty")
        return value


class EventUpdate(BaseModel):
    title: str | None = None
    summary: str | None = None

    @field_validator("title")
    @classmethod
    def strip_event_title(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("must not be empty")
        return value


class OpportunityUpdate(BaseModel):
    title: str | None = None
    customer: str | None = None
    problem: str | None = None
    solution: str | None = None
    status: Literal["candidate", "reviewing", "validated", "rejected", "archived"] | None = None

    @field_validator("title", "customer", "problem", "solution")
    @classmethod
    def strip_opportunity_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("must not be empty")
        return value


class OpportunityThesis(BaseModel):
    title: str
    customer: str
    problem: str
    current_workarounds: list[str] = []
    proposed_solution: str
    why_now: list[str] = []
    why_existing_solutions_fail: list[str] = []
    wedge: str
    distribution: list[str] = []
    monetization: list[str] = []
    reason_to_win: list[str] = []
    risks: list[str] = []
    assumptions: list[str] = []
    evidence_ids: list[str] = []


class SkepticReview(BaseModel):
    fatal_risks: list[str] = []
    counter_evidence: list[str] = []
    substitutes: list[str] = []
    validation_tests: list[str] = []
    kill_criteria: list[str] = []


class OpportunityScore(BaseModel):
    pain: float = Field(ge=0, le=100)
    market_change: float = Field(ge=0, le=100)
    willingness_to_pay: float = Field(ge=0, le=100)
    why_now: float = Field(ge=0, le=100)
    competition_gap: float = Field(ge=0, le=100)
    distribution: float = Field(ge=0, le=100)
    buildability: float = Field(ge=0, le=100)
    reason_to_win: float = Field(ge=0, le=100)
    regulatory_risk: float = Field(ge=0, le=100)
    confidence: float = Field(ge=0, le=1)

    def weighted_score(self) -> float:
        positive = (
            0.18 * self.pain
            + 0.15 * self.market_change
            + 0.13 * self.willingness_to_pay
            + 0.12 * self.why_now
            + 0.10 * self.competition_gap
            + 0.10 * self.distribution
            + 0.08 * self.buildability
            + 0.07 * self.reason_to_win
        )
        penalty = 0.07 * self.regulatory_risk
        return max(0.0, min(100.0, positive - penalty))


class ArticleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    source_id: UUID
    canonical_url: str
    title: str
    author: str | None
    published_at: datetime | None
    extracted: dict | None


class EventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    title: str
    summary: str | None
    article_count: int
    source_count: int
    last_seen_at: datetime


class SignalOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    event_id: UUID
    score: float
    features: dict


class OpportunityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    signal_id: UUID
    title: str
    customer: str
    problem: str
    solution: str
    thesis: dict
    skeptic: dict | None
    score_breakdown: dict | None
    score: float
    confidence: float
    status: str
