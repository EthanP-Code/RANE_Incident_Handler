import os
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Annotated, Literal

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .actions import ActionRepository
from .gemma import analyze_incident, provider_config
from .incidents import IncidentRepository
from .schemas import (
    ActionCreate,
    IncidentAction,
    IncidentDetail,
    IncidentQueue,
    TriageAnalysis,
)


def _configured_path(variable: str, fallback: str) -> Path:
    value = os.getenv(variable, fallback)
    path = Path(value).expanduser()
    return path if path.is_absolute() else Path.cwd() / path


@asynccontextmanager
async def lifespan(app: FastAPI):
    incident_path = _configured_path(
        "RANE_INCIDENTS_CSV", "data/incident_event_log.csv"
    )
    action_path = _configured_path(
        "RANE_ACTIONS_DB", "data/rane_actions.sqlite3"
    )
    try:
        app.state.incidents = IncidentRepository(incident_path)
    except (OSError, UnicodeError, ValueError) as exc:
        raise RuntimeError(f"Unable to load incident dataset {incident_path}: {exc}") from exc
    app.state.actions = ActionRepository(action_path)
    yield


app = FastAPI(title="RANE Incident Triage API", version="0.1.0", lifespan=lifespan)
_FRONTEND = Path(__file__).resolve().parents[1] / "frontend"
app.mount("/assets", StaticFiles(directory=_FRONTEND), name="assets")


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(_FRONTEND / "index.html")


@app.get("/api/config")
def config(request: Request):
    return {**request.app.state.incidents.metadata(), **provider_config()}


@app.get("/api/activity", response_model=list[IncidentAction])
def activity(request: Request, limit: Annotated[int, Query(ge=1, le=2000)] = 500):
    return request.app.state.actions.list(limit=limit)


@app.get("/health")
def health(request: Request) -> dict[str, object]:
    incidents: IncidentRepository = request.app.state.incidents
    return {
        "status": "ok",
        "dataset_loaded": incidents.available,
        "gemma_configured": provider_config()["gemma_configured"],
    }


@app.get("/api/incidents", response_model=IncidentQueue)
def list_incidents(
    request: Request,
    priority: Annotated[Literal["Critical", "High", "Moderate", "Low", "Planning"] | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    as_of: datetime | None = None,
    search: Annotated[str, Query(max_length=100)] = "",
) -> IncidentQueue:
    incidents: IncidentRepository = request.app.state.incidents
    rows, total, counts = incidents.queue(priority, limit, offset, as_of, search)
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
    mode: Literal["live", "demo"] = "live",
) -> TriageAnalysis:
    incidents: IncidentRepository = request.app.state.incidents
    context = incidents.replay_payload(incident_id, as_of)
    return await analyze_incident(context, mode)


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
    incidents.timeline(incident_id, action.replay_as_of)
    actions: ActionRepository = request.app.state.actions
    return actions.add(incident_id, action)
