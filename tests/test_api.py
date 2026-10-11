"""Tests for FastAPI endpoints and validation models."""
import pytest
from fastapi.testclient import TestClient
from receipts.main import app

client = TestClient(app)
U = "test_api_user"


def test_health_endpoint():
    res = client.get("/health")
    assert res.status_code == 200
    data = res.json()
    assert data["ok"] is True
    assert "mock_agents" in data
    assert "embeddings" in data
    assert "qdrant" in data


def test_system_status_endpoint():
    res = client.get(f"/status?uid={U}")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "healthy"
    assert "components" in data
    assert "statistics" in data


def test_ingest_and_memories_filtered():
    # Ingest a commitment
    res1 = client.post(
        "/ingest",
        json={"uid": U, "text": "I will deliver the design mockups by Friday.", "session_id": "test"},
    )
    assert res1.status_code == 200
    assert res1.json()["items"] >= 1

    # Ingest a decision
    res2 = client.post(
        "/ingest",
        json={"uid": U, "text": "Let's use PostgreSQL for our database.", "session_id": "test"},
    )
    assert res2.status_code == 200

    # Query /memories
    res_mems = client.get(f"/memories?uid={U}")
    assert res_mems.status_code == 200
    mems = res_mems.json()
    assert len(mems) >= 2

    # Query /commitments
    res_comm = client.get(f"/commitments?uid={U}")
    assert res_comm.status_code == 200
    commitments = res_comm.json()
    assert all(m["kind"] == "commitment" for m in commitments)

    # Query /decisions
    res_dec = client.get(f"/decisions?uid={U}")
    assert res_dec.status_code == 200
    decisions = res_dec.json()
    assert all(m["kind"] == "decision" for m in decisions)


def test_ask_endpoint():
    # Ask about database decision
    res = client.post(
        "/ask",
        json={"uid": U, "query": "What database did we decide to use?"},
    )
    assert res.status_code == 200
    data = res.json()
    assert "database" in data["query"].lower()
    assert data["count"] >= 1
    assert "PostgreSQL" in data["answer"]


def test_receipts_and_alert_resolve():
    from receipts import memory, notify
    notify.ALERTS.clear()
    for m in memory.list_all(U):
        memory.delete([m["id"]])

    # Ensure an active prior decision exists
    client.post(
        "/ingest",
        json={"uid": U, "text": "Let's use PostgreSQL for our database."},
    )
    # Ingest a contradicting or changing statement
    client.post(
        "/ingest",
        json={"uid": U, "text": "We're going with MongoDB."},
    )

    # Query /receipts or /alerts
    res_receipts = client.get(f"/receipts?uid={U}")
    assert res_receipts.status_code == 200
    receipts = res_receipts.json()
    assert len(receipts) >= 1

    alert = receipts[0]
    aid = alert["id"]

    # Resolve receipt
    res_resolve = client.post(f"/alerts/{aid}/resolve")
    assert res_resolve.status_code == 200
    assert res_resolve.json()["status"] == "ok"


def test_privacy_forget_endpoint():
    # Add a memory to forget
    client.post(
        "/ingest",
        json={"uid": U, "text": "I will prepare the presentation slides tomorrow."},
    )
    res_forget = client.post(
        "/forget",
        json={"uid": U, "topic": "presentation slides"},
    )
    assert res_forget.status_code == 200
    assert res_forget.json()["deleted"] >= 1


def test_demo_step_runner():
    res_step1 = client.post("/demo/step", json={"uid": U, "step": 1})
    assert res_step1.status_code == 200
    data = res_step1.json()
    assert data["step"] == 1
    assert "authentication API" in data["text"]


def test_metrics_endpoint():
    res = client.get("/metrics")
    assert res.status_code == 200
    data = res.json()
    assert "summary" in data
    assert "latencies_ms" in data
    assert "guards" in data
    assert data["summary"]["groundedness_rate_percent"] >= 0.0
    assert "knowledge_base_grounding" in data["summary"]

