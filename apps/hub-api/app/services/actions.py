"""Action extraction from mail content — deadlines, todos, meetings, questions."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)


@dataclass
class ExtractedActionItem:
    action_type: str  # deadline | todo | meeting | question
    description: str
    due_date: str | None = None


_ACTION_SCHEMA = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {
            "type": {"type": "string", "enum": ["deadline", "todo", "meeting", "question"]},
            "description": {"type": "string"},
            "due": {"type": ["string", "null"]},
        },
        "required": ["type", "description"],
    },
}

_EXTRACT_SYSTEM_PROMPT = """\
You extract structured actions from email content for an assistant.
Return a JSON array of action items found in the email.
Each item has: type (deadline|todo|meeting|question), description (short, in the email's language), due (ISO date if mentioned, else null).
If no actions are found, return an empty array [].
Only extract CLEAR, EXPLICIT actions — do not invent or infer vague commitments.
Output ONLY valid JSON, no markdown fences or explanation."""


def extract_actions(
    *,
    subject: str,
    body: str,
    attachment_summaries: list[str] | None = None,
) -> list[ExtractedActionItem]:
    """Extract structured actions from mail content using the classify model (27B)."""
    settings = get_settings()

    # Build the user message
    content_parts = [f"Subject: {subject[:200]}"]
    content_parts.append(f"\nBody:\n{body[:4000]}")
    if attachment_summaries:
        content_parts.append("\nAttachments:\n" + "\n".join(attachment_summaries[:5]))

    user_msg = "\n".join(content_parts)

    if settings.inference_mode.lower() == "vllm":
        return _extract_via_vllm(user_msg, settings)
    elif settings.inference_mode.lower() == "ollama":
        return _extract_via_ollama(user_msg, settings)
    else:
        # Stub mode: heuristic extraction for tests
        return _extract_stub(subject, body)


def _extract_via_vllm(user_msg: str, settings) -> list[ExtractedActionItem]:
    """Call vLLM classify model (27B) for action extraction."""
    try:
        with httpx.Client(timeout=settings.vllm_classify_timeout) as client:
            resp = client.post(
                f"{settings.vllm_classify_url.rstrip('/')}/chat/completions",
                json={
                    "model": settings.vllm_classify_model,
                    "messages": [
                        {"role": "system", "content": _EXTRACT_SYSTEM_PROMPT},
                        {"role": "user", "content": user_msg},
                    ],
                    "temperature": 0.1,
                    "max_tokens": 512,
                },
            )
            if resp.status_code >= 400:
                logger.info("action_extract_http_error status=%s", resp.status_code)
                return []
            data = resp.json()
            content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            return _parse_action_json(content)
    except httpx.TimeoutException:
        logger.info("action_extract_timeout")
        return []
    except Exception as exc:
        logger.info("action_extract_failed err=%s", type(exc).__name__)
        return []


def _extract_via_ollama(user_msg: str, settings) -> list[ExtractedActionItem]:
    """Call Ollama instruct model for action extraction."""
    prompt = f"{_EXTRACT_SYSTEM_PROMPT}\n\n{user_msg}\n\nJSON:\n"
    try:
        with httpx.Client(timeout=30.0) as client:
            resp = client.post(
                f"{settings.ollama_base_url.rstrip('/')}/api/generate",
                json={
                    "model": settings.ollama_instruct_model,
                    "prompt": prompt,
                    "stream": False,
                    "think": False,
                    "options": {"temperature": 0.1, "num_predict": 400, "num_ctx": 4096},
                },
            )
            if resp.status_code >= 400:
                return []
            text = str(resp.json().get("response") or "").strip()
            return _parse_action_json(text)
    except Exception as exc:
        logger.info("action_extract_ollama_failed err=%s", type(exc).__name__)
        return []


def _extract_stub(subject: str, body: str) -> list[ExtractedActionItem]:
    """Heuristic action extraction for stub/CI mode."""
    actions: list[ExtractedActionItem] = []
    text = f"{subject} {body}".lower()

    # Deadline patterns
    deadline_patterns = [
        r"(?:voor|before|by|deadline|uiterlijk)\s+(\w+dag|\d{1,2}[-/]\d{1,2})",
        r"\b(?:vrijdag|maandag|dinsdag|woensdag|donderdag)\b",
    ]
    for pattern in deadline_patterns:
        match = re.search(pattern, text)
        if match:
            actions.append(ExtractedActionItem(
                action_type="deadline",
                description=f"Deadline detected: {match.group(0)}",
            ))
            break

    # Meeting patterns
    if re.search(
        r"\b(?:meeting|vergadering|afspraak|bellen|call|overleg|volgende\s+week|next\s+week|morgen|tomorrow)\b",
        text,
    ):
        actions.append(ExtractedActionItem(
            action_type="meeting",
            description="Meeting or call detected in mail.",
        ))

    # Question patterns
    if "?" in body and len(body.strip()) > 20:
        actions.append(ExtractedActionItem(
            action_type="question",
            description="Question requiring response detected.",
        ))

    return actions


def _parse_action_json(raw: str) -> list[ExtractedActionItem]:
    """Parse the model's JSON output into action items."""
    # Strip markdown fences if present
    cleaned = re.sub(r"```(?:json)?\s*", "", raw).strip()
    cleaned = re.sub(r"```\s*$", "", cleaned).strip()

    if not cleaned:
        return []

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        # Try to find a JSON array — use non-greedy + bracket matching
        match = re.search(r"\[.*?\]", cleaned, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group(0))
            except json.JSONDecodeError:
                # Fallback: try greedy for deeply nested arrays
                match2 = re.search(r"\[[\s\S]*\]", cleaned)
                if match2:
                    try:
                        data = json.loads(match2.group(0))
                    except json.JSONDecodeError:
                        logger.info("action_extract_json_parse_failed")
                        return []
                else:
                    logger.info("action_extract_json_parse_failed")
                    return []
        else:
            return []

    if not isinstance(data, list):
        return []

    actions: list[ExtractedActionItem] = []
    valid_types = {"deadline", "todo", "meeting", "question"}
    for item in data[:10]:  # Cap at 10 actions
        if not isinstance(item, dict):
            continue
        action_type = str(item.get("type", "")).lower()
        if action_type not in valid_types:
            continue
        description = str(item.get("description", "")).strip()
        if not description:
            continue
        due = item.get("due")
        actions.append(ExtractedActionItem(
            action_type=action_type,
            description=description[:256],
            due_date=str(due) if due else None,
        ))

    return actions
