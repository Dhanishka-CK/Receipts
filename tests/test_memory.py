"""Tests for Qdrant memory layer (storage, retrieval, filtering, state)."""
import time
import pytest
from receipts import memory


@pytest.fixture(autouse=True)
def setup_memory():
    # Uses hash embedding backend and temporary/configured Qdrant client
    pass


def test_qdrant_health_check():
    health = memory.check_health()
    assert health["status"] in ("connected", "uninitialized")
    assert "collection" in health


def test_memory_add_and_get():
    uid = "test_mem_user"
    pid = memory.add(
        uid,
        {
            "text": "I'll finish the authentication API by Friday.",
            "kind": "commitment",
            "subject": "authentication",
            "status": "OPEN",
            "deadline_iso": "2026-10-15T18:00:00",
            "person": "you",
        },
    )
    assert pid is not None

    item = memory.get(pid)
    assert item is not None
    assert item["uid"] == uid
    assert item["status"] == "OPEN"
    assert item["kind"] == "commitment"
    assert item["created_at"] is not None
    assert item["deadline_ts"] is not None


def test_semantic_search_and_privacy_filtering():
    uid = "test_privacy_user"
    # Normal personal memory
    pid_public = memory.add(
        uid,
        {
            "text": "Let's use PostgreSQL for our database.",
            "kind": "decision",
            "subject": "database",
            "status": "ACTIVE",
            "visibility": "personal",
        },
    )
    # Private memory
    pid_private = memory.add(
        uid,
        {
            "text": "The secret database password is xyz.",
            "kind": "claim",
            "subject": "database",
            "status": "CURRENT",
            "visibility": "private",
        },
    )

    hits = memory.search(uid, "database")
    found_ids = [h["id"] for h in hits]
    assert pid_public in found_ids
    assert pid_private not in found_ids, "Private memory should NEVER be returned in agent search"


def test_memory_status_update():
    uid = "test_update_user"
    pid = memory.add(
        uid,
        {
            "text": "The API is blocked because auth isn't working.",
            "kind": "claim",
            "subject": "authentication",
            "status": "CURRENT",
            "polarity": "negative",
        },
    )
    item_before = memory.get(pid)
    assert item_before["status"] == "CURRENT"

    memory.update(pid, status="RESOLVED")
    item_after = memory.get(pid)
    assert item_after["status"] == "RESOLVED"
    assert item_after["updated_at"] is not None


def test_overdue_commitments_query():
    uid = "test_overdue_user"
    now_ts = time.time()
    # Past deadline
    pid_past = memory.add(
        uid,
        {
            "text": "Send the invoice yesterday.",
            "kind": "commitment",
            "subject": "invoice",
            "status": "OPEN",
            "deadline_iso": "2026-10-01T12:00:00",
        },
    )
    # Future deadline
    pid_future = memory.add(
        uid,
        {
            "text": "Send the report next month.",
            "kind": "commitment",
            "subject": "report",
            "status": "OPEN",
            "deadline_iso": "2026-12-01T12:00:00",
        },
    )

    overdue_list = memory.overdue(now_ts)
    overdue_ids = [m["id"] for m in overdue_list]
    assert pid_past in overdue_ids
    assert pid_future not in overdue_ids

    # Clean up to prevent side-effects in other test suites
    memory.delete([pid_past, pid_future])


def test_delete_and_delete_since():
    uid = "test_delete_user"
    old_ts = time.time() - 3600
    recent_ts = time.time() - 60

    pid1 = memory.add(uid, {"text": "Old note", "kind": "claim", "status": "CURRENT"}, ts=old_ts)
    pid2 = memory.add(uid, {"text": "Recent note", "kind": "claim", "status": "CURRENT"}, ts=recent_ts)

    # Delete since 5 minutes ago
    deleted_count = memory.delete_since(uid, time.time() - 300)
    assert deleted_count >= 1
    assert memory.get(pid2) is None
    assert memory.get(pid1) is not None

    # Delete specific memory
    memory.delete([pid1])
    assert memory.get(pid1) is None
