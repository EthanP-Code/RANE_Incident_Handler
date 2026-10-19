import csv
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import HTTPException

from .schemas import IncidentSnapshot, TimelineEvent

_ALIASES: dict[str, tuple[str, ...]] = {
    "incident_id": ("incident_id", "incident_number", "number", "incident"),
    "observed_at": (
        "event_timestamp",
        "sys_updated_at",
        "updated_at",
        "sys_created_at",
        "timestamp",
        "opened_at",
    ),
    "priority": ("priority", "u_priority"),
    "category": ("category", "u_category"),
    "symptom": ("symptom", "subcategory", "u_symptom"),
    "assignment_group": ("assignment_group", "group", "group_id"),
    "assigned_to": ("assigned_to", "assignee"),
    "status": ("status", "state", "incident_state"),
    "impact": ("impact", "u_impact"),
    "urgency": ("urgency", "u_urgency"),
    "reassignment_count": ("reassignment_count", "reassignments"),
}
_TIMELINE_FIELDS = (
    "priority",
    "status",
    "assignment_group",
    "assigned_to",
    "impact",
    "urgency",
)
_PRIORITIES = {
    "1": "Critical",
    "2": "High",
    "3": "Moderate",
    "4": "Low",
    "5": "Planning",
}
_LEVELS = {"1": "High", "2": "Medium", "3": "Low"}


def _parse_timestamp(value: str) -> datetime | None:
    value = value.strip()
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        for pattern in ("%m/%d/%Y %H:%M:%S", "%Y-%m-%d %H:%M:%S"):
            try:
                parsed = datetime.strptime(value, pattern)
                break
            except ValueError:
                continue
        else:
            return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def _normalize_row(row: dict[str, str]) -> dict[str, str]:
    return {
        key.strip().lower(): value.strip()
        for key, value in row.items()
        if key and value is not None
    }


def _field(row: dict[str, str], name: str) -> str | None:
    for alias in _ALIASES[name]:
        value = row.get(alias)
        if value:
            return value
    return None


def _priority(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return _PRIORITIES.get(normalized, normalized)


def _level(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return _LEVELS.get(normalized, normalized)


def _snapshot(row: dict[str, str], incident_id: str, observed_at: datetime) -> IncidentSnapshot:
    reassignment_count = _field(row, "reassignment_count")
    try:
        count = int(reassignment_count) if reassignment_count is not None else None
    except ValueError:
        count = None
    return IncidentSnapshot(
        incident_id=incident_id,
        observed_at=observed_at,
        priority=_priority(_field(row, "priority")),
        category=_field(row, "category"),
        symptom=_field(row, "symptom"),
        assignment_group=_field(row, "assignment_group"),
        assigned_to=_field(row, "assigned_to"),
        status=_field(row, "status"),
        impact=_level(_field(row, "impact")),
        urgency=_level(_field(row, "urgency")),
        reassignment_count=count,
    )


class IncidentRepository:
    def __init__(self, csv_path: Path) -> None:
        self.csv_path = csv_path
        self._events: dict[str, list[IncidentSnapshot]] = {}
        self._load()

    @property
    def available(self) -> bool:
        return bool(self._events)

    def _load(self) -> None:
        if not self.csv_path.is_file():
            return
        events: dict[str, list[IncidentSnapshot]] = {}
        with self.csv_path.open(newline="", encoding="utf-8-sig") as csv_file:
            reader = csv.DictReader(csv_file)
            if not reader.fieldnames:
                raise ValueError(f"Incident CSV has no header: {self.csv_path}")
            for raw_row in reader:
                row = _normalize_row(raw_row)
                incident_id = _field(row, "incident_id")
                observed_at_value = _field(row, "observed_at")
                observed_at = _parse_timestamp(observed_at_value or "")
                if incident_id is None or observed_at is None:
                    continue
                snapshot = _snapshot(row, incident_id, observed_at)
                events.setdefault(incident_id, []).append(snapshot)
        for history in events.values():
            history.sort(key=lambda event: event.observed_at)
        self._events = events

    def _require_data(self) -> None:
        if not self.available:
            raise HTTPException(
                status_code=503,
                detail=f"Incident dataset is unavailable or empty: {self.csv_path}",
            )

    def queue(
        self,
        priority: str | None,
        limit: int,
        offset: int,
    ) -> tuple[list[IncidentSnapshot], int, dict[str, int]]:
        self._require_data()
        latest = [history[-1] for history in self._events.values()]
        counts = Counter(
            incident.priority
            for incident in latest
            if incident.priority in ("Critical", "High")
        )
        if priority:
            latest = [incident for incident in latest if incident.priority == priority]
        latest.sort(key=lambda incident: (incident.observed_at, incident.incident_id), reverse=True)
        return latest[offset : offset + limit], len(latest), {
            "critical": counts["Critical"],
            "high": counts["High"],
            "unique_incidents": len(self._events),
        }

    def timeline(
        self, incident_id: str, as_of: datetime | None = None
    ) -> tuple[IncidentSnapshot, list[TimelineEvent]]:
        self._require_data()
        if as_of is not None and as_of.tzinfo is None:
            as_of = as_of.replace(tzinfo=timezone.utc)
        history = self._events.get(incident_id)
        if not history:
            raise HTTPException(status_code=404, detail="Incident not found")
        visible = [event for event in history if as_of is None or event.observed_at <= as_of]
        if not visible:
            raise HTTPException(
                status_code=404,
                detail="No incident data was recorded at or before the requested replay time",
            )
        previous: IncidentSnapshot | None = None
        timeline: list[TimelineEvent] = []
        for snapshot in visible:
            changes: dict[str, str | None] = {}
            if previous is not None:
                for field in _TIMELINE_FIELDS:
                    current_value = getattr(snapshot, field)
                    if current_value != getattr(previous, field):
                        changes[field] = current_value
            timeline.append(
                TimelineEvent(
                    observed_at=snapshot.observed_at,
                    changes=changes,
                    snapshot=snapshot,
                )
            )
            previous = snapshot
        return visible[-1], timeline

    def replay_payload(self, incident_id: str, as_of: datetime | None) -> dict[str, Any]:
        snapshot, timeline = self.timeline(incident_id, as_of)
        return {
            "incident": snapshot.model_dump(mode="json"),
            "timeline": [event.model_dump(mode="json") for event in timeline],
            "limitations": [
                "The dataset contains incident metadata, not application logs or infrastructure metrics.",
                "Possible causes are hypotheses and must be verified by an engineer.",
            ],
        }
