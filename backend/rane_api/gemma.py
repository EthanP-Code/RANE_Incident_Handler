import json
import os
from typing import Any

import httpx
from fastapi import HTTPException

from .schemas import TriageAnalysis

_DEFAULT_MODEL = "gemma-3-12b-it"


async def analyze_incident(context: dict[str, Any]) -> TriageAnalysis:
    api_key = os.getenv("GEMMA_API_KEY")
    if not api_key:
        raise HTTPException(
            status_code=503,
            detail="Gemma analysis is not configured. Set GEMMA_API_KEY to enable it.",
        )
    model = os.getenv("GEMMA_MODEL", _DEFAULT_MODEL)
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    prompt = f"""
You are Gemma assisting a platform engineer during historical incident replay.
Use only the supplied snapshot and timeline. Never infer later outcomes or claim a
confirmed root cause. Treat possible causes as hypotheses; state evidence and how
to verify each. The dataset has no logs, metrics, or runbooks. Mark absent
information as missing. Recommend investigation, not autonomous remediation.
Return only a JSON object with exactly these fields:
summary (string), severity (string), possible_causes (array of objects with
hypothesis, evidence, verification strings), missing_information (array of
strings), recommended_actions (array of strings), human_review_required (true).
Set human_review_required to true.

Incident context:
{json.dumps(context, ensure_ascii=True)}
""".strip()
    try:
        async with httpx.AsyncClient(timeout=45) as client:
            response = await client.post(
                url,
                headers={"x-goog-api-key": api_key},
                json={"contents": [{"parts": [{"text": prompt}]}]},
            )
    except httpx.TimeoutException as exc:
        raise HTTPException(status_code=504, detail="Gemma analysis timed out") from exc
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=502, detail="Could not connect to the Gemma analysis provider"
        ) from exc
    if response.is_error:
        raise HTTPException(
            status_code=502,
            detail=f"Gemma provider returned HTTP {response.status_code}",
        )
    try:
        response_data = response.json()
        text = response_data["candidates"][0]["content"]["parts"][0]["text"]
        result = TriageAnalysis.model_validate_json(text)
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=502,
            detail="Gemma returned an invalid analysis response",
        ) from exc
    return result
