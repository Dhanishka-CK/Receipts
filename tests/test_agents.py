"""Tests for Extractor, Auditor, and Manager agent logic and error handling."""
import pytest
from datetime import datetime
from receipts import agents, mock


def test_extractor_commitment_extraction():
    payload = {
        "text": "I'll finish the authentication API by Friday.",
        "now": "2026-10-08T10:00:00",
    }
    res = mock.extractor(payload)
    items = res.get("items", [])
    assert len(items) == 1
    item = items[0]
    assert item["kind"] == "commitment"
    assert "authentication" in item["subject"]
    assert item["deadline_phrase"] == "friday"
    assert item["deadline_iso"] is not None


def test_extractor_decision_extraction():
    payload = {
        "text": "Let's use PostgreSQL for our primary database.",
        "now": "2026-10-08T10:00:00",
    }
    res = mock.extractor(payload)
    items = res.get("items", [])
    assert len(items) == 1
    assert items[0]["kind"] == "decision"
    assert items[0]["subject"] == "database"


def test_extractor_privacy_voice_commands():
    # Forget topic
    res1 = mock.extractor({"text": "Receipts, forget what I said about the backend", "now": "2026-10-08T10:00:00"})
    assert res1.get("command") is not None
    assert res1["command"]["type"] == "forget_topic"
    assert res1["command"]["topic"] == "the backend"

    # Forget recent
    res2 = mock.extractor({"text": "Receipts, forget the last 15 minutes", "now": "2026-10-08T10:00:00"})
    assert res2.get("command") is not None
    assert res2["command"]["type"] == "forget_recent"
    assert res2["command"]["minutes"] == 15

    # Private mode
    res3 = mock.extractor({"text": "Don't remember anything from this conversation.", "now": "2026-10-08T10:00:00"})
    assert res3.get("command") is not None
    assert res3["command"]["type"] == "private_on"


def test_auditor_decision_changed():
    payload = {
        "new": {
            "kind": "decision",
            "subject": "database",
            "text": "We're going with MongoDB.",
        },
        "related": [
            {
                "id": "mem_1",
                "kind": "decision",
                "subject": "database",
                "text": "Let's use PostgreSQL for the database.",
                "status": "ACTIVE",
            }
        ],
    }
    audit = mock.auditor(payload)
    assert audit["relation"] == "decision_changed"
    assert audit["target_id"] == "mem_1"
    assert audit["suggested_status"] == "SUPERSEDED"


def test_auditor_blocker_detection():
    payload = {
        "new": {
            "kind": "claim",
            "polarity": "negative",
            "subject": "authentication",
            "text": "The authentication API is blocking our demo.",
        },
        "related": [
            {
                "id": "mem_2",
                "kind": "commitment",
                "subject": "authentication",
                "text": "I'll finish the authentication API by Friday.",
                "status": "OPEN",
            }
        ],
    }
    audit = mock.auditor(payload)
    assert audit["relation"] == "blocker_detected"
    assert audit["target_id"] == "mem_2"
    assert audit["suggested_status"] == "BLOCKED"


def test_auditor_possible_contradiction():
    payload = {
        "new": {
            "kind": "claim",
            "polarity": "negative",
            "subject": "authentication",
            "text": "We're still blocked because authentication isn't ready.",
        },
        "related": [
            {
                "id": "mem_3",
                "kind": "claim",
                "polarity": "positive",
                "subject": "authentication",
                "text": "Authentication is fixed now.",
                "status": "RESOLVED",
            }
        ],
    }
    audit = mock.auditor(payload)
    assert audit["relation"] == "possible_contradiction"
    assert audit["target_id"] == "mem_3"
    assert "Earlier you said" in audit["explanation"]


def test_manager_alert_decision():
    payload = {
        "new": {"kind": "claim", "text": "We're still blocked."},
        "audit": {
            "relation": "possible_contradiction",
            "target_id": "mem_3",
            "confidence": 0.9,
            "explanation": "Earlier you said authentication was fixed.",
        },
        "target": {"id": "mem_3", "text": "Authentication is fixed now."},
        "recent_alerts": [],
    }
    decision = mock.manager(payload)
    assert decision["action"] == "alert"
    assert decision["importance"] == "high"
    assert "Possible contradiction" in decision["alert_message"]


def test_lyzr_json_parser_robustness():
    # Normal JSON
    assert agents._parse_json('{"status": "ok"}') == {"status": "ok"}
    # Wrapped in markdown fences
    assert agents._parse_json('```json\n{"relation": "none"}\n```') == {"relation": "none"}
    # Prose before and after
    assert agents._parse_json('Here is your answer: {"action": "alert"} Hope that helps!') == {"action": "alert"}

    # Malformed non-JSON throws AgentError
    with pytest.raises(agents.AgentError):
        agents._parse_json("No json at all here")
