import csv
from collections import Counter
from bisect import bisect_right
from datetime import datetime, timezone
from functools import lru_cache
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
    "symptom": ("symptom", "u_symptom"),
    "subcategory": ("subcategory",),
    "opened_at": ("opened_at", "sys_created_at"),
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
    "reassignment_count",
    "category",
    "subcategory",
    "symptom",
)
_PRIORITIES = {
    "1": "Critical",
    "2": "High",
    "3": "Moderate",
    "4": "Low",
    "5": "Planning",
}
_LEVELS = {"1": "High", "2": "Medium", "3": "Low"}


@lru_cache(maxsize=100000)
def _parse_timestamp(value: str) -> datetime | None:
    value = value.strip()
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        # UCI dates are day/month/year, including ambiguous dates such as 4/5/2016.
        for pattern in ("%d/%m/%Y %H:%M", "%d/%m/%Y %H:%M:%S"):
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
        if value and value.lower() not in ("?", "null", "none", "nan", "n/a"):
            return value
    return None


def _priority(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return _PRIORITIES.get(normalized.split(" - ")[0], normalized)


def _level(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return _LEVELS.get(normalized.split(" - ")[0], normalized)


def _snapshot(row: dict[str, str], incident_id: str, observed_at: datetime) -> IncidentSnapshot:
    reassignment_count = _field(row, "reassignment_count")
    try:
        count = int(reassignment_count) if reassignment_count is not None else None
    except ValueError:
        count = None
    opened_at = _parse_timestamp(_field(row, "opened_at") or "")
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
        subcategory=_field(row, "subcategory"),
        opened_at=opened_at if opened_at and opened_at <= observed_at else None,
    )


class IncidentRepository:
    def __init__(self, csv_path: Path) -> None:
        self.csv_path = csv_path
        self._events: dict[str, list[IncidentSnapshot]] = {}
        self.skipped_rows = 0
        self._load()

    @property
    def available(self) -> bool:
        return bool(self._events)

    def _load(self) -> None:
        if not self.csv_path.is_file():
            return
        events: dict[str, list[tuple[int, IncidentSnapshot]]] = {}
        with self.csv_path.open(newline="", encoding="utf-8-sig") as csv_file:
            reader = csv.DictReader(csv_file)
            if not reader.fieldnames:
                raise ValueError(f"Incident CSV has no header: {self.csv_path}")
            columns = {name.strip().lower() for name in reader.fieldnames}
            if not columns.intersection(_ALIASES["incident_id"]) or not columns.intersection(_ALIASES["observed_at"]):
                raise ValueError("Incident CSV needs an incident identifier and an event timestamp column")
            for raw_row in reader:
                row = _normalize_row(raw_row)
                incident_id = _field(row, "incident_id")
                observed_at_value = _field(row, "observed_at")
                observed_at = _parse_timestamp(observed_at_value or "")
                if incident_id is None or observed_at is None:
                    self.skipped_rows += 1
                    continue
                snapshot = _snapshot(row, incident_id, observed_at)
                sequence = row.get("sys_mod_count", "")
                events.setdefault(incident_id, []).append((int(sequence) if sequence.isdigit() else 0, snapshot))
        self._events = {
            key: [event for _, event in sorted(history, key=lambda item: (item[1].observed_at, item[0]))]
            for key, history in events.items()
        }
        self._times = {key: [event.observed_at for event in history] for key, history in self._events.items()}

    def metadata(self) -> dict[str, Any]:
        if not self.available:
            return {"dataset_loaded": False, "dataset_file": self.csv_path.name}
        demo_id = "INC0025693" if "INC0025693" in self._events else next(
            (key for key, history in self._events.items() if len(history) > 2 and any(e.priority == "Critical" for e in history)),
            next(iter(self._events)),
        )
        history = self._events[demo_id]
        candidates = [e for e in history if e.priority == "Critical" and e.status not in ("Resolved", "Closed", "Canceled")]
        demo_event = candidates[min(7, len(candidates) - 1)] if candidates else history[0]
        return {
            "dataset_loaded": True,
            "dataset_file": self.csv_path.name,
            "total_events": sum(len(h) for h in self._events.values()),
            "total_incidents": len(self._events),
            "skipped_rows": self.skipped_rows,
            "first_event": min(h[0].observed_at for h in self._events.values()),
            "last_event": max(h[-1].observed_at for h in self._events.values()),
            "default_incident": demo_id,
            "default_as_of": demo_event.observed_at,
            "time_basis": "Source timestamps; timezone unspecified (treated as UTC for replay).",
        }

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
        as_of: datetime | None = None,
        search: str = "",
    ) -> tuple[list[IncidentSnapshot], int, dict[str, int]]:
        self._require_data()
        if as_of is not None and as_of.tzinfo is None:
            as_of = as_of.replace(tzinfo=timezone.utc)
        latest = []
        for key, history in self._events.items():
            index = len(history) if as_of is None else bisect_right(self._times[key], as_of)
            if index:
                latest.append(history[index - 1])
        counts = Counter(
            incident.priority
            for incident in latest
            if incident.priority in ("Critical", "High")
        )
        unique_count = len(latest)
        unresolved = sum(incident.status not in (None, "Resolved", "Closed", "Canceled", "Cancelled") for incident in latest)
        if priority:
            latest = [incident for incident in latest if incident.priority == priority]
        if search:
            latest = [incident for incident in latest if search.casefold() in incident.incident_id.casefold()]
        latest.sort(key=lambda incident: (
            list(_PRIORITIES.values()).index(incident.priority) if incident.priority in _PRIORITIES.values() else 9,
            incident.status in ("Resolved", "Closed", "Canceled"),
            -incident.observed_at.timestamp(), incident.incident_id,
        ))
        return latest[offset : offset + limit], len(latest), {
            "critical": counts["Critical"],
            "high": counts["High"],
            "unique_incidents": unique_count,
            "unresolved": unresolved,
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
                        changes[field] = str(current_value) if current_value is not None else None
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
            "replay_as_of": (as_of or snapshot.observed_at).isoformat(),
            "incident": snapshot.model_dump(mode="json"),
            "timeline": [event.model_dump(mode="json") for event in timeline],
            "limitations": [
                "The dataset contains incident metadata, not application logs or infrastructure metrics.",
                "Possible causes are hypotheses and must be verified by an engineer.",
            ],
        }
