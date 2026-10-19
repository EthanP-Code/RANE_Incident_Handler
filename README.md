# RANE Incident Triage API

The backend serves incident queue, replay, analysis, and engineer action
history. It reads the ServiceNow event dataset as a CSV with one row per update.

## Run locally

```sh
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[test]'
RANE_ACTIONS_DB=data/rane_actions.sqlite3 \
GEMMA_API_KEY=your_google_ai_studio_key \
uvicorn rane_api.main:app --reload
```

By default, the backend loads `incident_event_log.csv` from the repository root.
Set `RANE_INCIDENTS_CSV` to point to another copy of the CSV. `RANE_ACTIONS_DB`
defaults to `backend/data/rane_actions.sqlite3`. Set `GEMMA_MODEL` to override
the default `gemma-3-12b-it`.

The supplied event log has 36 columns and uses `number` as the incident ID,
`sys_updated_at` as the event timestamp, and day/month/year timestamps such as
`4/5/2016 08:57`. Numeric prefixes in values such as `1 - Critical` and
`2 - Medium` are normalized into their readable labels. `Incident_response.txt`
describes the CSV attributes.

The dataset contains incident metadata rather than application logs, metrics,
or runbooks. Category and symptom values are anonymized identifiers. The API
does not send `resolved_at`, `closed_at`, or later events to Gemma during
historical replay.

## Endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/health` | Dataset, event, and incident counts plus Gemma configuration |
| `GET` | `/api/incidents?priority=Critical&limit=50&offset=0` | Latest incident snapshots and priority counts |
| `GET` | `/api/incidents/{id}?as_of=2016-05-04T08:57:00Z` | Point-in-time snapshot and event timeline |
| `POST` | `/api/incidents/{id}/analyze?as_of=...` | Structured Gemma analysis from replay-visible data |
| `GET` | `/api/incidents/{id}/actions` | Engineer action history |
| `POST` | `/api/incidents/{id}/actions` | Record `accept`, `dismiss`, `investigated`, or `note` |

Run tests from `backend` with `pytest`.