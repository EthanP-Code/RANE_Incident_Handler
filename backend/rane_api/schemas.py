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
    hypothesis: str
    evidence: str
    verification: str


class TriageAnalysis(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary: str
    severity: str
    possible_causes: list[PossibleCause]
    missing_information: list[str]
    recommended_actions: list[str]
    human_review_required: Literal[True]


class ActionCreate(BaseModel):
    kind: Literal["accept", "dismiss", "investigated", "note"]
    description: str = Field(min_length=1, max_length=2000)
    recommendation: str | None = Field(default=None, max_length=1000)


class IncidentAction(BaseModel):
    id: int
    incident_id: str
    kind: Literal["accept", "dismiss", "investigated", "note"]
    description: str
    recommendation: str | None
    created_at: datetime
