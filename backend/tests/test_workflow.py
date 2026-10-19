import csv
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from rane_api import gemma
from rane_api.actions import ActionRepository
from rane_api.incidents import IncidentRepository, _parse_timestamp
from rane_api.main import app


@pytest.fixture
def dataset(tmp_path, monkeypatch):
    path = tmp_path / "incidents.csv"
    base = dict(number="INC0025693", incident_state="New", priority="3 - Moderate", impact="2 - Medium", urgency="2 - Medium", assignment_group="Group 70", assigned_to="?", category="Category 20", subcategory="Subcategory 174", u_symptom="?", opened_at="4/5/2016 08:57", reassignment_count="0", sys_mod_count="0", sys_updated_at="4/5/2016 08:57", resolved_at="6/5/2016 10:35", resolved_by="Future resolver", closed_at="11/5/2016 11:07", closed_code="Future resolution", made_sla="true")
    rows = [base, {**base, "priority": "1 - Critical", "sys_mod_count": "2", "assignment_group": "Group 72", "sys_updated_at": "4/5/2016 08:59"}, {**base, "sys_mod_count": "1", "sys_updated_at": "4/5/2016 08:59"}, {**base, "sys_mod_count": "3", "incident_state": "Resolved", "assigned_to": "Future engineer", "assignment_group": "Future group", "sys_updated_at": "6/5/2016 10:35"}, {**base, "number": "INC_LATER", "sys_updated_at": "5/5/2016 10:00"}]
    with path.open("w", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=base.keys())
        writer.writeheader()
        writer.writerows(rows)
    monkeypatch.setenv("RANE_INCIDENTS_CSV", str(path))
    monkeypatch.setenv("RANE_ACTIONS_DB", str(tmp_path / "audit.sqlite3"))
    for key in ("GEMMA_API_KEY", "GEMMA_ENDPOINT", "GEMMA_MODEL", "GEMMA_PROVIDER"):
        monkeypatch.delenv(key, raising=False)
    return path


def test_real_csv_formats_and_replay_boundary(dataset):
    repo = IncidentRepository(dataset)
    cutoff = _parse_timestamp("4/5/2016 08:59")
    assert cutoff.month == 5 and cutoff.day == 4
    rows, total, counts = repo.queue(None, 50, 0, cutoff)
    assert total == counts["unique_incidents"] == 1
    assert rows[0].priority == "Critical"  # sys_mod_count breaks equal-timestamp ties
    assert rows[0].assigned_to is None and rows[0].symptom is None
    assert rows[0].subcategory == "Subcategory 174"
    context = repo.replay_payload("INC0025693", cutoff)
    assert len(context["timeline"]) == 3
    for forbidden in ("resolved_at", "closed_at", "resolved_by", "closed_code", "made_sla", "Future", "INC_LATER"):
        assert forbidden not in json.dumps(context)
    assert repo.queue(None, 50, 0, cutoff, "inc002")[1] == 1
    assert repo.queue("High", 50, 0, cutoff)[1] == 0


def test_demo_decisions_notes_and_persistence(dataset):
    cutoff = "2016-05-04T08:59:00Z"
    with TestClient(app) as client:
        assert client.get("/").status_code == 200
        config = client.get("/api/config").json()
        assert config["default_mode"] == "demo"
        assert config["total_incidents"] == 2
        assert client.get(f"/api/incidents/INC0025693?as_of={cutoff}").json()["incident"]["assignment_group"] == "Group 72"
        analysis = client.post(f"/api/incidents/INC0025693/analyze?as_of={cutoff}&mode=demo").json()
        assert analysis["mode"] == "demo" and analysis["human_review_required"]
        assert 3 <= len(analysis["recommended_actions"]) <= 5
        assert analysis == client.post(f"/api/incidents/INC0025693/analyze?as_of={cutoff}&mode=demo").json()
        for kind in ("accept", "dismiss", "note", "investigated"):
            response = client.post("/api/incidents/INC0025693/actions", json={"kind": kind, "description": "Reviewed available evidence", "recommendation": "Confirm ownership" if kind in ("accept", "dismiss") else None, "replay_as_of": cutoff, "analysis_mode": "demo"})
            assert response.status_code == 201
        assert client.post("/api/incidents/INC0025693/actions", json={"kind":"note","description":"   "}).status_code == 422
        assert client.post("/api/incidents/INC0025693/actions", json={"kind":"note","description":"test","replay_as_of":"2010-01-01T00:00:00Z"}).status_code == 404
        assert client.get("/api/incidents/INC0025693?as_of=2010-01-01T00:00:00Z").status_code == 404
        assert client.post("/api/incidents/INC0025693/analyze").status_code == 503
    with TestClient(app) as client:
        history = client.get("/api/activity").json()
        assert len(history) == 4
        assert history[0]["kind"] == "investigated"
        assert history[-1]["kind"] == "accept"
        assert all(a["replay_as_of"] for a in history)


def configure_mock(monkeypatch, handler):
    monkeypatch.setenv("GEMMA_PROVIDER", "digitalocean")
    monkeypatch.setenv("GEMMA_ENDPOINT", "https://example.invalid/v1/chat/completions")
    monkeypatch.setenv("GEMMA_API_KEY", "test-secret-never-public")
    monkeypatch.setenv("GEMMA_MODEL", "configured-gemma-deployment")
    original = httpx.AsyncClient
    monkeypatch.setattr(gemma.httpx, "AsyncClient", lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs))


def test_google_default_model_is_configured_by_key_alone(monkeypatch):
    monkeypatch.setenv("GEMMA_API_KEY", "test-google-key")
    monkeypatch.delenv("GEMMA_PROVIDER", raising=False)
    monkeypatch.delenv("GEMMA_MODEL", raising=False)
    monkeypatch.delenv("GEMINI_MODEL", raising=False)
    monkeypatch.delenv("GEMMA_ENDPOINT", raising=False)

    config = gemma.provider_config()

    assert config["provider"] == "google"
    assert config["model"] == "gemma-4-31b-it"
    assert config["gemma_configured"] is True
    assert config["default_mode"] == "live"


def test_google_live_request_uses_model_generate_content_endpoint(dataset, monkeypatch):
    monkeypatch.setenv("GEMMA_API_KEY", "test-google-key")
    monkeypatch.delenv("GEMMA_PROVIDER", raising=False)
    monkeypatch.delenv("GEMMA_MODEL", raising=False)
    monkeypatch.delenv("GEMINI_MODEL", raising=False)
    monkeypatch.delenv("GEMMA_ENDPOINT", raising=False)
    original = httpx.AsyncClient

    def google(request):
        assert request.url == "https://generativelanguage.googleapis.com/v1beta/models/gemma-4-31b-it:generateContent"
        assert request.headers["x-goog-api-key"] == "test-google-key"
        body = json.loads(request.content)
        assert body["generationConfig"]["responseMimeType"] == "application/json"
        context = json.loads(body["contents"][0]["parts"][0]["text"].split("Incident context:\n", 1)[1])
        assert "Future" not in json.dumps(context)
        assert "resolved_at" not in json.dumps(context)
        result = gemma.demo_analysis(context).model_dump(exclude={"mode", "provider"})
        return httpx.Response(
            200,
            json={"candidates": [{"content": {"parts": [{"text": json.dumps(result)}]}}]},
        )

    monkeypatch.setattr(gemma.httpx, "AsyncClient", lambda **kwargs: original(transport=httpx.MockTransport(google), **kwargs))

    with TestClient(app) as client:
        response = client.post("/api/incidents/INC0025693/analyze?mode=live&as_of=2016-05-04T08:59:00Z")

    assert response.status_code == 200
    assert response.json()["mode"] == "live"
    assert response.json()["provider"] == "Google / Gemma"


def test_live_provider_contract_and_no_future_information(dataset, monkeypatch):
    def provider(request):
        assert request.headers["Authorization"] == "Bearer test-secret-never-public"
        body = json.loads(request.content)
        assert body["model"] == "configured-gemma-deployment"
        context = json.loads(body["messages"][1]["content"])
        assert "Future" not in json.dumps(context)
        assert "resolved_at" not in json.dumps(context)
        result = gemma.demo_analysis(context).model_dump(exclude={"mode", "provider"})
        return httpx.Response(200, json={"choices":[{"message":{"content":"```json\n" + json.dumps(result) + "\n```"}}]})
    configure_mock(monkeypatch, provider)
    with TestClient(app) as client:
        response = client.post("/api/incidents/INC0025693/analyze?mode=live&as_of=2016-05-04T08:59:00Z")
        assert response.status_code == 200
        assert response.json()["mode"] == "live"
        assert response.json()["provider"] == "DigitalOcean / Gemma"
        for path in ("/api/config", "/health", "/", "/assets/app.js"):
            assert "test-secret-never-public" not in client.get(path).text


@pytest.mark.parametrize("failure", ["http", "timeout", "connection", "json", "missing_fields", "empty_choices"])
def test_provider_failures_are_clear_and_never_silently_demo(dataset, monkeypatch, failure):
    def provider(request):
        if failure == "timeout":
            raise httpx.ReadTimeout("private provider detail")
        if failure == "connection":
            raise httpx.ConnectError("private provider detail")
        if failure == "http":
            return httpx.Response(401, text="test-secret-never-public")
        if failure == "empty_choices":
            return httpx.Response(200, json={"choices":[]})
        return httpx.Response(200, json={"choices":[{"message":{"content":"not JSON" if failure == "json" else '{"summary":"missing everything else"}'}}]})
    configure_mock(monkeypatch, provider)
    with TestClient(app) as client:
        response = client.post("/api/incidents/INC0025693/analyze?mode=live")
        assert response.status_code == (504 if failure == "timeout" else 502)
        assert "detail" in response.json()
        assert "test-secret-never-public" not in response.text
        assert "private provider detail" not in response.text


def test_missing_dataset_still_launches(tmp_path, monkeypatch):
    monkeypatch.setenv("RANE_INCIDENTS_CSV", str(tmp_path / "absent.csv"))
    monkeypatch.setenv("RANE_ACTIONS_DB", str(tmp_path / "actions.sqlite3"))
    with TestClient(app) as client:
        assert client.get("/").status_code == 200
        assert client.get("/api/config").json()["dataset_loaded"] is False
        assert client.get("/api/incidents").status_code == 503
