# RANE — Incident Triage Copilot

RANE is a local incident command center with a FastAPI backend and a responsive,
buildless HTML/CSS/JavaScript frontend. It supports historical incident replay,
Gemma-backed triage or explicitly labeled deterministic demo guidance, and
persistent engineer decisions. It does not autonomously resolve incidents.

## Run locally

From the repository root, with Python 3.11+:

```sh
python3 -m venv .venv
source .venv/bin/activate
pip install -e './backend[test]'
python run.py
```

Open <http://127.0.0.1:8000>; API documentation is at `/docs`. The backend
loads `incident_event_log.csv` from the repository root by default. Override
the path with `RANE_INCIDENTS_CSV`. The SQLite action database defaults to
`backend/data/rane_actions.sqlite3` and can be changed with `RANE_ACTIONS_DB`.

The supplied CSV contains 119,998 event records across 20,769 unique incidents.
`Incident_response.txt` documents its fields. The loader handles day-first
timestamps, numeric-labeled priority/impact/urgency, and anonymized fields.
Do not interpret category/symptom IDs as readable descriptions.

## Demo workflow

1. Filter/search the queue for `INC0025693` and open its incident detail.
2. Use the replay timestamp to compare incident state before and after priority
   escalation. The queue, detail, and analysis use the selected time cutoff.
3. Choose **Demo Mode** for deterministic investigation suggestions, or **Live
   Mode** when a model deployment is configured. Demo responses are explicitly
   labeled and do not represent model inference.
4. Review hypotheses, evidence, missing information, and recommended actions.
   Accept or dismiss actions, record an investigation note, and mark the replay
   point investigated.
5. Review persistent decisions in Activity History. Engineer actions never
   trigger infrastructure changes.

## Model configuration

The default is Demo Mode unless live provider configuration is complete. Copy
`.env.example` to `.env`, set server-side values, and restart the application.
`run.py` loads both the root `.env` and `backend/.env` (root values take
precedence).

| Variable | Purpose |
| --- | --- |
| `GEMMA_PROVIDER` | `google` (default) or `digitalocean` |
| `GEMMA_ENDPOINT` | Complete HTTPS chat-completions URL for the deployed model; required only for DigitalOcean |
| `GEMMA_API_KEY` | Server-side provider credential |
| `GEMMA_MODEL` | Model override; Google defaults to `gemma-4-31b-it`, verified available to the configured key. |
| `RANE_INCIDENTS_CSV` | Optional CSV path; defaults to `incident_event_log.csv` in the repository root |
| `RANE_ACTIONS_DB` | Optional SQLite database path |

For Google, the backend calls
`https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent`
with the API key on the server. The key was verified to list Gemma 4 models,
and `gemma-4-31b-it` completed a JSON-generation check. This is the default
model. Google generation may take up to 120 seconds. DigitalOcean's
[inference endpoint documentation](https://docs.digitalocean.com/products/inference/how-to/si-endpoints/)
describes its chat endpoint at
`https://inference.do-ai.run/v1/chat/completions`; DigitalOcean requires its
own authorized credential and a model ID supported by that account.

Configuration presence does not prove that inference succeeds; verify the
deployment before presenting it as live inference. Live provider failures are
explicit and never silently substituted with demo output.

## Replay and data integrity

- CSV rows are incident events. Queue counts and snapshots aggregate by
  incident ID at the selected replay time; equal-timestamp rows use
  `sys_mod_count` ordering.
- Day-first source timestamps have no timezone and are treated as UTC internally
  without changing their clock values.
- Only allowlisted metadata is supplied to the model. Resolution/closure
  timestamps, resolution codes, resolved-by values, SLA outcomes, and later
  events are excluded—even if outcome columns are already populated in earlier
  CSV rows.
- The data contains no application logs, metrics, service-name mappings, or
  runbooks. Causes remain hypotheses; recommended steps are investigations, not
  remediation instructions.
- Missing datasets produce an actionable empty state. No fabricated incidents
  are used by the application.

Dataset attribution: Amaral, C., Fantinato, M., and Peres, S., [Incident
management process enriched event log](https://archive.ics.uci.edu/dataset/498/incident+management+process+enriched+event+log),
UCI Machine Learning Repository, [DOI 10.24432/C57S4H](https://doi.org/10.24432/C57S4H),
CC BY 4.0.

## Verify

```sh
python -m pytest backend/tests -q
node --check backend/frontend/app.js
```

Live model inference has not been verified without deployment credentials.
This is a local hackathon MVP; authentication, production telemetry, and
automated remediation are outside its scope.
