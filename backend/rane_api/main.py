import os
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Annotated, Literal

from fastapi import FastAPI, HTTPException, Query, Request

from .actions import ActionRepository
from .gemma import analyze_incident
from .incidents import IncidentRepository
from .schemas import (
    ActionCreate,
    IncidentAction,
    IncidentDetail,
    IncidentQueue,
    TriageAnalysis,
)


def _configured_path(variable: str, fallback: Path) -> Path:
    value = os.getenv(variable)
    path = Path(value).expanduser() if value else fallback
    return path if path.is_absolute() else Path.cwd() / path


@asynccontextmanager
async def lifespan(app: FastAPI):
    backend_dir = Path(__file__).resolve().parents[1]
    repository_root = backend_dir.parent
    incident_path = _configured_path(
        "RANE_INCIDENTS_CSV", repository_root / "incident_event_log.csv"
    )
    action_path = _configured_path(
        "RANE_ACTIONS_DB", backend_dir / "data" / "rane_actions.sqlite3"
    )
    try:
        app.state.incidents = IncidentRepository(incident_path)
    except (OSError, UnicodeError, ValueError) as exc:
        raise RuntimeError(f"Unable to load incident dataset {incident_path}: {exc}") from exc
    app.state.actions = ActionRepository(action_path)
    yield


app = FastAPI(title="RANE Incident Triage API", version="0.1.0", lifespan=lifespan)


@app.get("/health")
def health(request: Request) -> dict[str, object]:
    incidents: IncidentRepository = request.app.state.incidents
    return {
        "status": "ok",
        "dataset_loaded": incidents.available,
        "dataset_path": str(incidents.csv_path),
        "events_loaded": incidents.event_count,
        "unique_incidents": incidents.unique_incident_count,
        "gemma_configured": bool(os.getenv("GEMMA_API_KEY")),
    }


@app.get("/api/incidents", response_model=IncidentQueue)
def list_incidents(
    request: Request,
    priority: Annotated[Literal["Critical", "High"] | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> IncidentQueue:
    incidents: IncidentRepository = request.app.state.incidents
    rows, total, counts = incidents.queue(priority, limit, offset)
    return IncidentQueue(incidents=rows, total=total, counts=counts)


@app.get("/api/incidents/{incident_id}", response_model=IncidentDetail)
def get_incident(
    incident_id: str,
    request: Request,
    as_of: datetime | None = None,
) -> IncidentDetail:
    incidents: IncidentRepository = request.app.state.incidents
    incident, timeline = incidents.timeline(incident_id, as_of)
    return IncidentDetail(incident=incident, timeline=timeline)


@app.post("/api/incidents/{incident_id}/analyze", response_model=TriageAnalysis)
async def analyze(
    incident_id: str,
    request: Request,
    as_of: datetime | None = None,
) -> TriageAnalysis:
    incidents: IncidentRepository = request.app.state.incidents
    context = incidents.replay_payload(incident_id, as_of)
    return await analyze_incident(context)


@app.get(
    "/api/incidents/{incident_id}/actions",
    response_model=list[IncidentAction],
)
def list_actions(incident_id: str, request: Request) -> list[IncidentAction]:
    incidents: IncidentRepository = request.app.state.incidents
    incidents.timeline(incident_id)
    actions: ActionRepository = request.app.state.actions
    return actions.list(incident_id)


@app.post(
    "/api/incidents/{incident_id}/actions",
    response_model=IncidentAction,
    status_code=201,
)
def create_action(
    incident_id: str,
    action: ActionCreate,
    request: Request,
) -> IncidentAction:
    incidents: IncidentRepository = request.app.state.incidents
    incidents.timeline(incident_id)
    actions: ActionRepository = request.app.state.actions
    return actions.add(incident_id, action)
