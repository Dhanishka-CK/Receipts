"""Tests for Omi webhook normalization layer."""
import pytest
from receipts import omi


def test_normalize_realtime_list_payload():
    payload = [
        {"text": "Hello world", "speaker": "SPEAKER_00"},
        {"text": "I'll ship the feature tomorrow.", "speaker": "SPEAKER_00"},
    ]
    uid, session, text, segs = omi.normalize_realtime_payload(payload, query_uid="user123")
    assert uid == "user123"
    assert "Hello world I'll ship the feature tomorrow." in text
    assert len(segs) == 2


def test_normalize_realtime_dict_with_segments():
    payload = {
        "uid": "omi_device_99",
        "sessionId": "sess_abc",
        "segments": [{"text": "We are going with PostgreSQL"}],
    }
    uid, session, text, segs = omi.normalize_realtime_payload(payload)
    assert uid == "omi_device_99"
    assert session == "sess_abc"
    assert text == "We are going with PostgreSQL"


def test_normalize_realtime_raw_text():
    payload = {"text": "Authentication is fixed now."}
    uid, session, text, segs = omi.normalize_realtime_payload(payload, query_uid="u1")
    assert uid == "u1"
    assert text == "Authentication is fixed now."


def test_normalize_conversation_structured():
    payload = {
        "id": "conv_987",
        "uid": "user_omi",
        "transcript_segments": [
            {"text": "We talked about the database."},
            {"text": "Let's use PostgreSQL for our database."},
        ],
        "structured": {
            "title": "Database Architecture",
            "overview": "Selected PostgreSQL",
            "action_items": ["Setup schema"],
        },
    }
    uid, conv_id, text, meta = omi.normalize_conversation_payload(payload)
    assert uid == "user_omi"
    assert conv_id == "conv_987"
    assert "Let's use PostgreSQL for our database." in text
    assert meta["title"] == "Database Architecture"


def test_normalize_malformed_and_empty_payloads():
    # Empty dict
    uid, session, text, segs = omi.normalize_realtime_payload({})
    assert uid == "demo"
    assert text == ""
    assert segs == []

    # Non-dict / non-list input
    uid, session, text, segs = omi.normalize_realtime_payload("unexpected string")
    assert uid == "demo"
    assert text == ""

    # Header-based UID fallback
    uid, session, text, segs = omi.normalize_realtime_payload(
        {"text": "test"}, header_uid="header_user_42"
    )
    assert uid == "header_user_42"
    assert text == "test"
