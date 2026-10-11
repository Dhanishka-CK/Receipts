import os, shutil, tempfile
os.environ.update(MOCK_AGENTS="1", EMBED_BACKEND="hash", QDRANT_URL="",
                  QDRANT_PATH=tempfile.mkdtemp(), MAX_ALERTS_PER_HOUR="50")
from fastapi.testclient import TestClient
from receipts.main import app
from receipts import memory, notify

c = TestClient(app)
U = "t1"


def statuses():
    return {m["text"]: m["status"] for m in memory.list_all(U)}


def test_demo_story():
    for m in memory.list_all(U):
        memory.delete([m["id"]])
    notify.ALERTS.clear()
    assert c.post("/demo/seed", json={"uid": U}).json()["seeded"] == 4
    # 1. overdue commitment is surfaced autonomously
    assert c.post("/demo/overdue-check").json()["alerts"] == 1
    assert any(a["kind"] == "overdue" for a in notify.ALERTS)
    # 2. fixed -> resolves the old blocked claim, stores a new commitment
    c.post("/ingest", json={"uid": U, "text": "Authentication is fixed now. We'll ship Friday."})
    s = statuses()
    assert s["The API is blocked because authentication isn't working."] == "RESOLVED"
    # 3. still blocked -> possible contradiction alert
    c.post("/ingest", json={"uid": U, "text": "We're still blocked because authentication isn't ready."})
    assert any(a["kind"] == "possible_contradiction" for a in notify.ALERTS)
    # 4. decision changed supersedes PostgreSQL
    c.post("/ingest", json={"uid": U, "text": "We're going with MongoDB."})
    assert statuses()["Let's use PostgreSQL for the database."] == "SUPERSEDED"
    assert any(a["kind"] == "decision_changed" for a in notify.ALERTS)


def test_resolve_alert():
    a = next(a for a in notify.ALERTS if a["kind"] == "possible_contradiction")
    assert c.post(f"/alerts/{a['id']}/resolve").status_code == 200


def test_privacy_commands():
    c.post("/ingest", json={"uid": U, "text": "Receipts, forget about the report", "session_id": "p"})
    assert "I'll send the report tomorrow." not in statuses()
    before = len(memory.list_all(U))
    c.post("/ingest", json={"uid": U, "text": "Don't remember anything from this conversation.", "session_id": "p2"})
    c.post("/ingest", json={"uid": U, "text": "I'll email Rahul tomorrow.", "session_id": "p2"})
    assert len(memory.list_all(U)) == before


def test_omi_webhook_shapes():
    assert c.post("/omi/realtime?uid=u9&session_id=s", json=[{"text": "hi"}]).status_code == 200
    assert c.post("/omi/conversation?uid=u9", json={"transcript_segments": [{"text": "hi"}]}).status_code == 200
