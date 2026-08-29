from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class SourceCreate(BaseModel):
    name: str
    domain: str
    source_type: str = "news"
    feed_url: str | None = None
    trust_score: float = Field(0.5, ge=0, le=1)


class SourceOut(SourceCreate):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    enabled: bool


class ArticleInsight(BaseModel):
    entities: list[str] = []
    industries: list[str] = []
    affected_groups: list[str] = []
    problems: list[str] = []
    changes: list[str] = []
    claims: list[str] = []
    metrics: list[str] = []
    regulations: list[str] = []


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
