import csv
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from rane_api.main import app
from rane_api.incidents import IncidentRepository


def _write_dataset(path):
    rows = [
        {
            "incident_id": "INC001",
            "sys_updated_at": "2016-05-04 08:57:00",
            "priority": "3",
            "impact": "2",
            "urgency": "2",
            "group_id": "Group 72",
            "state": "New",
            "closed_at": "",
        },
        {
            "incident_id": "INC001",
            "sys_updated_at": "2016-05-04 08:59:00",
            "priority": "1",
            "impact": "1",
            "urgency": "1",
            "group_id": "Group 65",
            "state": "In Progress",
            "closed_at": "2016-05-05 11:00:00",
        },
        {
            "incident_id": "INC002",
            "sys_updated_at": "2016-05-04 08:58:00",
            "priority": "2",
            "impact": "1",
            "urgency": "2",
            "group_id": "Group 72",
            "state": "New",
            "closed_at": "",
        },
    ]
    with path.open("w", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)


def test_queue_aggregates_latest_snapshot_per_incident(tmp_path):
    csv_path = tmp_path / "incidents.csv"
    _write_dataset(csv_path)
    repository = IncidentRepository(csv_path)

    rows, total, counts = repository.queue(None, 50, 0)

    assert total == 2
    assert counts == {"critical": 1, "high": 1, "unique_incidents": 2}
    assert {incident.incident_id: incident.priority for incident in rows} == {
        "INC001": "Critical",
        "INC002": "High",
    }


def test_replay_and_timeline_exclude_future_events(tmp_path):
    csv_path = tmp_path / "incidents.csv"
    _write_dataset(csv_path)
    repository = IncidentRepository(csv_path)
    as_of = datetime(2016, 5, 4, 8, 57, tzinfo=timezone.utc)

    snapshot, timeline = repository.timeline("INC001", as_of)
    context = repository.replay_payload("INC001", as_of)

    assert snapshot.priority == "Moderate"
    assert len(timeline) == 1
    assert "closed_at" not in str(context)
    assert "Critical" not in str(context)


def test_timeline_records_priority_and_assignment_changes(tmp_path):
    csv_path = tmp_path / "incidents.csv"
    _write_dataset(csv_path)
    repository = IncidentRepository(csv_path)

    _, timeline = repository.timeline("INC001")

    assert timeline[-1].changes == {
        "priority": "Critical",
        "status": "In Progress",
        "assignment_group": "Group 65",
        "impact": "High",
        "urgency": "High",
    }


def test_api_replay_and_action_audit(tmp_path, monkeypatch):
    csv_path = tmp_path / "incidents.csv"
    _write_dataset(csv_path)
    monkeypatch.setenv("RANE_INCIDENTS_CSV", str(csv_path))
    monkeypatch.setenv("RANE_ACTIONS_DB", str(tmp_path / "actions.sqlite3"))
    monkeypatch.delenv("GEMMA_API_KEY", raising=False)

    with TestClient(app) as client:
        queue = client.get("/api/incidents?priority=Critical")
        replay = client.get(
            "/api/incidents/INC001?as_of=2016-05-04T08:57:00Z"
        )
        created = client.post(
            "/api/incidents/INC001/actions",
            json={
                "kind": "accept",
                "description": "Review change history",
                "recommendation": "Check recent changes",
            },
        )
        history = client.get("/api/incidents/INC001/actions")
        analysis = client.post("/api/incidents/INC001/analyze")

    assert queue.status_code == 200
    assert queue.json()["total"] == 1
    assert replay.json()["incident"]["priority"] == "Moderate"
    assert created.status_code == 201
    assert history.json()[0]["description"] == "Review change history"
    assert analysis.status_code == 503
    assert "GEMMA_API_KEY" in analysis.json()["detail"]
