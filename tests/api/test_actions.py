"""Tests for action extraction — stub mode heuristics and JSON parsing."""

from __future__ import annotations

import pytest

from app.services.actions import ExtractedActionItem, extract_actions, _parse_action_json


@pytest.fixture(autouse=True)
def _stub_mode(monkeypatch):
    monkeypatch.setenv("INFERENCE_MODE", "stub")
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    from app.core.config import get_settings

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


class TestStubExtraction:
    def test_detects_deadline_keyword(self):
        actions = extract_actions(
            subject="Contract review",
            body="Graag aanleveren voor vrijdag. Bedankt!",
        )
        types = [a.action_type for a in actions]
        assert "deadline" in types

    def test_detects_meeting_keyword(self):
        actions = extract_actions(
            subject="Overleg volgende week",
            body="Kunnen we een vergadering plannen volgende week dinsdag?",
        )
        types = [a.action_type for a in actions]
        assert "meeting" in types

    def test_detects_question(self):
        actions = extract_actions(
            subject="Vraag over factuur",
            body="Heb je de factuur al ontvangen? Laat het me weten als er iets ontbreekt.",
        )
        types = [a.action_type for a in actions]
        assert "question" in types

    def test_no_actions_for_trivial_mail(self):
        actions = extract_actions(
            subject="FYI",
            body="OK",
        )
        assert len(actions) == 0


class TestActionJsonParsing:
    def test_valid_json_array(self):
        raw = '[{"type": "deadline", "description": "Review contract", "due": "2026-07-25"}]'
        result = _parse_action_json(raw)
        assert len(result) == 1
        assert result[0].action_type == "deadline"
        assert result[0].description == "Review contract"
        assert result[0].due_date == "2026-07-25"

    def test_json_in_markdown_fences(self):
        raw = '```json\n[{"type": "todo", "description": "Send invoice"}]\n```'
        result = _parse_action_json(raw)
        assert len(result) == 1
        assert result[0].action_type == "todo"

    def test_empty_array(self):
        result = _parse_action_json("[]")
        assert result == []

    def test_invalid_json_returns_empty(self):
        result = _parse_action_json("this is not json")
        assert result == []

    def test_invalid_type_filtered_out(self):
        raw = '[{"type": "invalid_type", "description": "x"}, {"type": "todo", "description": "y"}]'
        result = _parse_action_json(raw)
        assert len(result) == 1
        assert result[0].action_type == "todo"

    def test_caps_at_10_items(self):
        items = [{"type": "todo", "description": f"item {i}"} for i in range(15)]
        import json

        result = _parse_action_json(json.dumps(items))
        assert len(result) == 10

    def test_null_due_date_handled(self):
        raw = '[{"type": "meeting", "description": "Team sync", "due": null}]'
        result = _parse_action_json(raw)
        assert result[0].due_date is None
