import uuid
import time
from datetime import timedelta
import pytest
from fastapi.testclient import TestClient
from receipts import config as C, memory, notify, pipeline
from receipts.main import app

client = TestClient(app)


def test_full_autonomous_hackathon_scenario():
    """Validates the exact 5-day story required by the hackathon organizers."""
    U = f"judge_{uuid.uuid4().hex[:8]}"
    notify.ALERTS.clear()

    # --- DAY 1: User promises to finish authentication API by Friday ---
    res1 = client.post(
        "/ingest",
        json={"uid": U, "text": "I'll finish the authentication API by Friday."},
    )
    assert res1.status_code == 200
    mems = memory.list_all(U)
    day1_mem = next(m for m in mems if "authentication API" in m["text"])
    assert day1_mem["kind"] == "commitment"
    assert day1_mem["status"] == "OPEN"

    # --- DAY 2: User makes architectural decision ---
    res2 = client.post(
        "/ingest",
        json={"uid": U, "text": "Let's use PostgreSQL for the database."},
    )
    assert res2.status_code == 200
    mems = memory.list_all(U)
    day2_mem = next(m for m in mems if "PostgreSQL" in m["text"])
    assert day2_mem["kind"] == "decision"
    assert day2_mem["status"] == "ACTIVE"

    # --- DAY 3: Authentication API is reported as blocking the demo ---
    res3 = client.post(
        "/ingest",
        json={"uid": U, "text": "The authentication API is blocking our demo."},
    )
    assert res3.status_code == 200
    mems = memory.list_all(U)
    day1_mem_updated = memory.get(day1_mem["id"])
    assert day1_mem_updated["status"] == "BLOCKED", "Day 1 commitment should now be marked BLOCKED"

    # --- DAY 4: Authentication is fixed ---
    res4 = client.post(
        "/ingest",
        json={"uid": U, "text": "Authentication is fixed now."},
    )
    assert res4.status_code == 200
    mems = memory.list_all(U)
    day3_claim = next((m for m in mems if "blocking our demo" in m["text"]), None)
    if day3_claim:
        assert day3_claim["status"] == "RESOLVED"

    # --- DAY 5: Contradiction / Consistency conflict ---
    res5 = client.post(
        "/ingest",
        json={"uid": U, "text": "We're still blocked because authentication isn't ready."},
    )
    assert res5.status_code == 200
    # Receipts should produce a possible contradiction alert citing evidence!
    user_receipts = notify.list_for_user(U)
    contradiction_receipt = next(
        (r for r in user_receipts if r["kind"] == "possible_contradiction"), None
    )
    assert contradiction_receipt is not None, "System must generate an evidence-backed contradiction receipt"
    assert "Earlier you said" in contradiction_receipt["message"] or "Authentication is fixed" in str(contradiction_receipt.get("evidence", ""))

    # --- PRIVACY: Forget authentication memories ---
    res_privacy = client.post(
        "/ingest",
        json={"uid": U, "text": "Receipts, forget about authentication"},
    )
    assert res_privacy.status_code == 200
    remaining_mems = memory.list_all(U)
    # Ensure authentication memories are deleted from retrieval
    auth_mems = [m for m in remaining_mems if "authentication" in m.get("text", "").lower()]
    assert len(auth_mems) == 0, "Authentication memories must be completely wiped after forget command"

    # Database decision should still remain
    assert any("PostgreSQL" in m["text"] for m in remaining_mems)


def test_autonomous_overdue_scheduler():
    """Validates that the overdue scheduler autonomously triggers without user prompt."""
    U_SCHED = "sched_test_user"
    now = C.now()
    yesterday = (now - timedelta(days=2)).isoformat()

    # Add open commitment with past deadline
    pid = memory.add(
        U_SCHED,
        {
            "text": "I'll submit the final project proposal yesterday.",
            "kind": "commitment",
            "subject": "proposal",
            "status": "OPEN",
            "deadline_iso": yesterday,
            "deadline_phrase": "yesterday",
        },
    )

    # Trigger scheduler
    res = client.post("/demo/overdue-check")
    assert res.status_code == 200
    assert res.json()["alerts"] >= 1

    # Verify receipt generated
    alerts = notify.list_for_user(U_SCHED)
    overdue_alert = next((a for a in alerts if a["kind"] == "overdue"), None)
    assert overdue_alert is not None
    assert "overdue" in overdue_alert["headline"].lower()
    assert pid == overdue_alert["target_id"]
