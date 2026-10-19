# RANE — Incident Triage Copilot

A functional local incident command center: real historical incident snapshots, point-in-time investigation, Gemma or explicitly labeled deterministic demo guidance, and persistent engineer decisions. FastAPI serves both the API and the responsive, buildless HTML/CSS/JavaScript frontend. There is no separate frontend server or Node installation step.

## Run on this computer

From `C:\Users\ethan\Documents\RANE_Incident_Handler`:

```powershell
.\.venv\Scripts\python.exe run.py
```

Open **http://127.0.0.1:8000**. API documentation is at `/docs`. Stop the server with Ctrl+C.

The local virtual environment is installed and the actual CSV has been copied from `C:\Users\ethan\Documents\Incident_log\incident_event_log.csv` to `data/incident_event_log.csv`. The CSV and SQLite database are ignored by Git. This copy contains **119,998 event records across 20,769 unique incidents**; all UI totals are calculated from the loaded data. The default replay point is **4 May 2016, 12:15** for **INC0025693**. Its snapshot is Critical / Active, with four recorded reassignments.

For a fresh checkout with Python 3.11+:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e "./backend[test]"
# Put your actual incident_event_log.csv in data/ before starting.
.\.venv\Scripts\python.exe run.py
```

Alternatively, the equivalent direct server command from the repository root is:

```powershell
.\.venv\Scripts\python.exe -m uvicorn rane_api.main:app --host 127.0.0.1 --port 8000
```

Use `run.py` to load a root `.env` file automatically. The direct uvicorn command uses shell environment variables unless you add `--env-file .env`.

## 90-second demonstration

1. Open the app. Keep **Demo Mode** active unless a deployed model is configured. Explain that incidents are real historical data and demo recommendations are deterministic.
2. In the queue, choose **Critical** and search **INC0025693**, then click its ID. **Open demo incident** is also a shortcut that restores the default replay point.
3. Show its recorded severity, owner, impact, and the ten visible timeline events. No later resolution is included.
4. Click **Analyze with Gemma**. In Demo Mode the result is prominently labeled **DEMO ANALYSIS — no model inference**.
5. Review the triage summary and evidence for the unverified hypotheses. Scroll to Recommended Actions.
6. **Accept** the ownership investigation step and **Dismiss** another step. Both cards reflect the decision; neither triggers infrastructure changes.
7. Enter a short investigation note and click **Save Note**. Optionally click **Mark Investigated**.
8. Open **Activity History**. Show the accepted/dismissed actions, note, replay timestamp, and decision timestamp. Reload to demonstrate persistence.

Optional replay demonstration: set the replay time to **4 May 2016, 08:57**, then **Apply snapshot**. The same incident becomes Moderate / New, unassigned, with zero reassignments and one visible event. Use **Reset demo point** to return.

For the clearest two-column presentation, use a browser window at least 1,000 pixels wide. Smaller windows stack the investigation sections.

## Inference configuration

**Current default: Demo Mode.** No deployed DigitalOcean endpoint, model ID, or credential was supplied. Demo analysis uses deterministic investigation guidance based on the selected real snapshot. Switching modes is available in the AI triage panel. A failed live request produces an error and never silently substitutes demo output.

Copy `.env.example` to `.env`, then set server-side values:

| Variable | Purpose |
| --- | --- |
| `GEMMA_PROVIDER` | `digitalocean` (default); `google` preserves the original integration as an explicit option. |
| `GEMMA_ENDPOINT` | Full HTTPS chat-completions endpoint for your actual DigitalOcean Gemma deployment. Required for DigitalOcean. |
| `GEMMA_API_KEY` | Model or endpoint access key. Remains on the server. |
| `GEMMA_MODEL` | Actual deployed Gemma model ID; no assumed model name or automatic deployment. |
| `RANE_INCIDENTS_CSV` | Optional CSV path; defaults to `data/incident_event_log.csv`. |
| `RANE_ACTIONS_DB` | Optional SQLite path; defaults to `data/rane_actions.sqlite3`. |

Restart the server after changing these values. When all required values are present, the UI defaults to Live mode. Configuration presence does not prove that the endpoint works or hosts Gemma; verify your deployment before presenting it as live inference.

DigitalOcean's [inference endpoint documentation](https://docs.digitalocean.com/products/inference/how-to/si-endpoints/) describes the OpenAI-compatible chat-completions protocol used here. Use the endpoint, credential type, and model ID provided by your actual deployment; this application does not assume Gemma is available in a serverless catalog. The retained Google option requires `GEMMA_PROVIDER=google`, `GEMMA_API_KEY`, and `GEMMA_MODEL`.

The backend sends a selected snapshot and its visible timeline, validates/normalizes the model JSON, and returns structured hypotheses and 3–5 investigation actions. Missing credentials, HTTP failures, connection errors, timeouts, malformed JSON, and incomplete results have explicit error responses. Provider error bodies and keys are never returned to the browser. Provider timeout is 45 seconds; the browser request timeout is 55 seconds.

## Replay and data integrity

- One incident row per replay point; search, priority filters, pagination, counts, detail, timeline, and analysis use the same cutoff.
- Day-first UCI timestamps, labeled priorities (`1 - Critical`), labeled impact/urgency, and `?` unknown values are normalized.
- Equal-timestamp events use `sys_mod_count` ordering when present. The cutoff includes all events recorded at that timestamp.
- Only allowlisted metadata is sent to inference. Resolution/closure dates, resolution codes, resolved-by, eventual SLA outcomes, and future assignments are excluded, including outcome columns already populated in early CSV rows.
- Source timestamps have no timezone. The app uses UTC internally to keep their source clock values unchanged and labels this limitation. Audit timestamps are actual UTC timestamps.
- Summary cards count all incidents visible at the replay point; search and priority filters affect the table only. “Require investigation” counts nonterminal recorded states, not completion of local review. **Mark Investigated** records the engineer's review for that specific replay point; it does not rewrite historical incident state.
- Notes and decisions persist in SQLite and are scoped to incident plus replay timestamp. The Activity History screen shows the latest 500 entries across incidents; per-incident history also loads up to 500 entries. Unsaved note drafts and generated analyses are held in page memory; rerun analysis after a refresh.
- No application logs, metrics, service-name mappings, or real runbooks are supplied. Hypotheses remain unverified, and runbook guidance is labeled **Suggested Investigation Checklist**.

Dataset format/source attribution: Amaral, C., Fantinato, M., and Peres, S., [Incident management process enriched event log](https://archive.ics.uci.edu/dataset/498/incident+management+process+enriched+event+log), UCI Machine Learning Repository, [DOI 10.24432/C57S4H](https://doi.org/10.24432/C57S4H), CC BY 4.0. RANE uses the supplied local CSV; its record count may differ from the complete public release. Missing datasets produce an actionable empty state; no fabricated incidents are supplied.

## Verification

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests -q
node --check backend/frontend/app.js
```

Tests cover dataset normalization, same-time event ordering, replay exclusion, queue aggregation/filtering, full demo analysis and persistent audit actions, blank-note validation, missing data, mocked live provider requests, secret non-disclosure, and provider errors/timeouts/invalid responses. Synthetic records exist only as isolated test fixtures, never as the application dataset.

The complete workflow was exercised in the actual browser, including filtering, selection, Demo Mode analysis, Accept/Dismiss, Save Note, Mark Investigated, Activity History, reload persistence, pre-escalation replay, and the unconfigured live-inference error. **An actual DigitalOcean Gemma request has not been verified without deployment credentials.**

This is a local hackathon MVP, bound to loopback. Authentication, deployment, production telemetry, and automated remediation are outside this implementation.
