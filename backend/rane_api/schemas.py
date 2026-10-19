from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class IncidentSnapshot(BaseModel):
    incident_id: str
    observed_at: datetime
    priority: str | None = None
    category: str | None = None
    symptom: str | None = None
    assignment_group: str | None = None
    assigned_to: str | None = None
    status: str | None = None
    impact: str | None = None
    urgency: str | None = None
    reassignment_count: int | None = None
    subcategory: str | None = None
    opened_at: datetime | None = None


class IncidentQueue(BaseModel):
    incidents: list[IncidentSnapshot]
    total: int
    counts: dict[str, int]


class TimelineEvent(BaseModel):
    observed_at: datetime
    changes: dict[str, str | None]
    snapshot: IncidentSnapshot


class IncidentDetail(BaseModel):
    incident: IncidentSnapshot
    timeline: list[TimelineEvent]


class PossibleCause(BaseModel):
    cause: str = Field(min_length=1, max_length=2000)
    evidence: str = Field(min_length=1, max_length=3000)
    verification: str = Field(min_length=1, max_length=3000)


class RecommendedAction(BaseModel):
    id: str = Field(min_length=1, max_length=100)
    title: str = Field(min_length=1, max_length=500)
    reason: str = Field(min_length=1, max_length=2000)
    priority: int = Field(ge=1, le=5)


class TriageAnalysis(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary: str = Field(min_length=1, max_length=6000)
    severity: str = Field(min_length=1, max_length=500)
    hypotheses: list[PossibleCause] = Field(min_length=1, max_length=5)
    missing_information: list[str] = Field(min_length=1, max_length=15)
    recommended_actions: list[RecommendedAction] = Field(min_length=3, max_length=5)
    human_review_required: Literal[True]
    mode: Literal["live", "demo"] = "live"
    provider: str = "DigitalOcean / Gemma"


class ActionCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    kind: Literal["accept", "dismiss", "investigated", "note"]
    description: str = Field(min_length=1, max_length=2000)
    recommendation: str | None = Field(default=None, max_length=1000)
    replay_as_of: datetime | None = None
    analysis_mode: Literal["live", "demo"] | None = None


class IncidentAction(BaseModel):
    id: int
    incident_id: str
    kind: Literal["accept", "dismiss", "investigated", "note"]
    description: str
    recommendation: str | None
    created_at: datetime
    replay_as_of: datetime | None = None
    analysis_mode: Literal["live", "demo"] | None = None
