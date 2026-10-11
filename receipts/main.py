"""Receipts: Autonomous Voice Memory & Conflict Detection API."""
import asyncio
import logging
import time
from contextlib import asynccontextmanager
from datetime import timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import BackgroundTasks, Body, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from . import config as C, memory, notify, omi, pipeline
from .models import (
    AskRequest,
    DemoStepRequest,
    ForgetRequest,
    HealthResponse,
    IngestRequest,
    SeedRequest,
)

logger = logging.getLogger("receipts.main")

STATIC = Path(__file__).resolve().parent.parent / "static"
BUF: Dict[tuple, Dict[str, Any]] = {}          # (uid, session) -> {"text": [...], "last": ts}
LAST_REALTIME: Dict[str, float] = {}           # uid -> ts
LAST_ACTIVE_UID: str = "vQfvd1h9u2UH5eitNG5JwrPbIZW2"


async def _background_loop():
    """Background processor for debounced realtime speech and autonomous overdue commitments."""
    ticks = 0
    while True:
        try:
            await asyncio.sleep(2)
            ticks += 2
            now = time.time()

            # Flush idle realtime transcript buffers
            idle_keys = [k for k, b in BUF.items() if now - b["last"] >= C.REALTIME_IDLE_SECONDS]
            for key in idle_keys:
                b = BUF.pop(key, None)
                if b and b.get("text"):
                    combined_text = " ".join(b["text"]).strip()
                    if combined_text:
                        await asyncio.to_thread(pipeline.process, key[0], combined_text, key[1])

            # Periodic overdue commitment scan (every 30 seconds)
            if ticks % 30 == 0:
                await asyncio.to_thread(pipeline.check_overdue)
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error("Error in background worker loop: %s", e)


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(_background_loop())
    yield
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


app = FastAPI(
    title="Receipts",
    description="Your memory for what you said, decided, and promised. Listens through Omi, remembers via Qdrant, reasons via Lyzr multi-agent workflows.",
    version="1.0.0",
    lifespan=lifespan,
)

# Enable CORS for cross-origin access and webhook calls
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(STATIC / "index.html")


@app.get("/health", response_model=HealthResponse)
def health():
    qdrant_info = memory.check_health()
    return {
        "ok": qdrant_info.get("status") in ("connected", "uninitialized"),
        "status": "operational",
        "mock_agents": C.use_mock(),
        "embeddings": C.EMBED_BACKEND,
        "qdrant": qdrant_info,
        "lyzr_configured": bool(C.LYZR_API_KEY and all(C.AGENT_IDS.values())),
        "omi_configured": bool(C.OMI_APP_ID and C.OMI_APP_SECRET),
    }


@app.get("/status")
def system_status(uid: str = "demo"):
    """Comprehensive system status for monitoring and judges."""
    q_health = memory.check_health()
    all_mems = memory.list_all(uid)
    tel = pipeline.get_telemetry()
    return {
        "status": "healthy",
        "last_active_uid": LAST_ACTIVE_UID,
        "timestamp": time.time(),
        "components": {
            "omi": {
                "active_listeners": len(BUF),
                "last_realtime_activity": LAST_REALTIME.get(uid),
                "push_configured": bool(C.OMI_APP_ID and C.OMI_APP_SECRET),
            },
            "qdrant": q_health,
            "lyzr": {
                "mode": "mock" if C.use_mock() else "production_api",
                "agents": C.AGENT_IDS,
                "knowledge_base": "TEAM_COMMITMENT_PLAYBOOK.md (Active)",
            },
            "scheduler": {
                "status": "active",
                "interval_seconds": 30,
                "max_alerts_per_hour": C.MAX_ALERTS_PER_HOUR,
            },
        },
        "statistics": {
            "total_memories": len(all_mems),
            "commitments": sum(1 for m in all_mems if m.get("kind") == "commitment"),
            "decisions": sum(1 for m in all_mems if m.get("kind") == "decision"),
            "claims": sum(1 for m in all_mems if m.get("kind") == "claim"),
            "alerts": len(notify.list_for_user(uid)),
        },
        "telemetry": tel["summary"],
        "latencies": tel["latencies_ms"],
    }


@app.get("/metrics")
def get_metrics():
    """Returns detailed agent performance telemetry, latency percentiles, and hallucination suppression metrics."""
    return pipeline.get_telemetry()


# ==========================================
# OMI WEBHOOKS
# ==========================================
@app.get("/omi/realtime")
def omi_realtime_info():
    """Information endpoint for Omi realtime webhook verification."""
    return {"status": "ready", "endpoint": "/omi/realtime", "method": "POST", "message": "Omi realtime webhook is active. Send audio transcripts via POST."}


@app.get("/omi/conversation")
def omi_conversation_info():
    """Information endpoint for Omi conversation webhook verification."""
    return {"status": "ready", "endpoint": "/omi/conversation", "method": "POST", "message": "Omi conversation webhook is active. Send conversation payloads via POST."}


@app.post("/omi/realtime")
async def omi_realtime(
    request: Request,
    bg: BackgroundTasks,
    uid: Optional[str] = Query(default=None),
    session_id: Optional[str] = Query(default=None),
    payload: Any = Body(default={}),
):
    """Realtime speech webhook from Omi device or app."""
    header_uid = request.headers.get("x-omi-uid") or request.headers.get("x-user-id")
    target_uid, target_session, text, segments = omi.normalize_realtime_payload(
        payload=payload, query_uid=uid, query_session=session_id, header_uid=header_uid
    )

    if target_uid:
        global LAST_ACTIVE_UID
        LAST_ACTIVE_UID = target_uid

    if text:
        key = (target_uid, target_session)
        buf = BUF.setdefault(key, {"text": [], "last": 0.0})
        buf["text"].append(text)
        buf["last"] = time.time()
        LAST_REALTIME[target_uid] = time.time()
        pipeline.log("omi", "Omi Voice", "heard", f"Live voice transcript ({target_uid}): '{text}'")

    return {"status": "ok", "uid": target_uid, "buffered": bool(text)}


@app.post("/omi/conversation")
async def omi_conversation(
    request: Request,
    bg: BackgroundTasks,
    uid: Optional[str] = Query(default=None),
    payload: Any = Body(default={}),
):
    """Completed conversation/memory webhook from Omi."""
    header_uid = request.headers.get("x-omi-uid") or request.headers.get("x-user-id")
    target_uid, conv_id, text, metadata = omi.normalize_conversation_payload(
        payload=payload, query_uid=uid, header_uid=header_uid
    )

    if target_uid:
        global LAST_ACTIVE_UID
        LAST_ACTIVE_UID = target_uid

    if text:
        pipeline.log("omi", "Omi Voice", "heard", f"Conversation completed ({target_uid}): '{text}'")
        bg.add_task(pipeline.process, target_uid, text, conv_id)
        return {"status": "ok", "uid": target_uid, "conversation_id": conv_id, "processed": True}

    return {"status": "ok", "uid": target_uid, "conversation_id": conv_id, "processed": False, "reason": "empty_text"}


@app.post("/webhook")
@app.post("/omi")
@app.post("/omi/webhook")
@app.post("/")
async def omi_universal_webhook(
    request: Request,
    bg: BackgroundTasks,
    uid: Optional[str] = Query(default=None),
    payload: Any = Body(default={}),
):
    """Universal catch-all webhook for Omi mobile app / wearable."""
    header_uid = request.headers.get("x-omi-uid") or request.headers.get("x-user-id")
    target_uid, session_id, text, segments = omi.normalize_realtime_payload(
        payload=payload, query_uid=uid, header_uid=header_uid
    )
    if not text:
        target_uid, conv_id, text, meta = omi.normalize_conversation_payload(
            payload=payload, query_uid=uid, header_uid=header_uid
        )
        session_id = conv_id
    if not text and isinstance(payload, dict):
        text = str(payload.get("text") or payload.get("transcript") or payload.get("message") or "").strip()

    if target_uid:
        global LAST_ACTIVE_UID
        LAST_ACTIVE_UID = target_uid

    if text:
        pipeline.log("omi", "Omi Voice", "heard", f"Captured voice from Omi ({target_uid}): '{text}'")
        bg.add_task(pipeline.process, target_uid, text, session_id or "omi-live")
        return {"status": "ok", "uid": target_uid, "text": text, "processed": True}

    return {"status": "ok", "uid": target_uid, "processed": False}


# ==========================================
# INGESTION & INTERACTION
# ==========================================
@app.post("/ingest")
def ingest(body: IngestRequest):
    """Processes typed or simulated speech input through the full autonomous pipeline."""
    global LAST_ACTIVE_UID
    target_uid = body.uid or LAST_ACTIVE_UID
    LAST_ACTIVE_UID = target_uid
    return pipeline.process(uid=target_uid, text=body.text, session_id=body.session_id)


@app.post("/ask")
def ask(body: AskRequest):
    """Semantic question-answering over stored memories."""
    target_uid = body.uid or LAST_ACTIVE_UID
    return pipeline.ask(uid=target_uid, query=body.query, limit=body.limit)


# ==========================================
# MEMORY & RECEIPTS
# ==========================================
@app.get("/memories")
def get_memories(uid: Optional[str] = Query(default=None), kind: Optional[str] = Query(default=None)):
    """Lists memories, default returning all active user records."""
    target_uid = "" if (not uid or uid in ("all", "demo")) else uid
    return memory.list_all(target_uid, kind=kind)


@app.get("/commitments")
def get_commitments(uid: Optional[str] = Query(default=None)):
    """Returns commitment memories."""
    target_uid = "" if (not uid or uid in ("all", "demo")) else uid
    return memory.list_all(target_uid, kind="commitment")


@app.get("/decisions")
def get_decisions(uid: Optional[str] = Query(default=None)):
    """Returns decision memories."""
    target_uid = "" if (not uid or uid in ("all", "demo")) else uid
    return memory.list_all(target_uid, kind="decision")


@app.get("/claims")
def get_claims(uid: Optional[str] = Query(default=None)):
    """Returns claim memories."""
    target_uid = "" if (not uid or uid in ("all", "demo")) else uid
    return memory.list_all(target_uid, kind="claim")


@app.delete("/memories/{pid}")
def delete_memory(pid: str):
    """Deletes a specific memory by its ID."""
    memory.delete([pid])
    return {"deleted": pid, "status": "ok"}


@app.get("/alerts")
@app.get("/receipts")
def get_receipts(uid: Optional[str] = Query(default=None)):
    """Returns generated receipts/alerts."""
    target_uid = "" if (not uid or uid in ("all", "demo")) else uid
    return notify.list_for_user(target_uid)


@app.post("/alerts/{aid}/resolve")
def resolve_alert(aid: int):
    """Marks an alert/receipt resolved and updates target status."""
    a = notify.get(aid)
    if not a:
        raise HTTPException(status_code=404, detail="Alert not found")
    if a.get("target_id"):
        m = memory.get(a["target_id"])
        if m:
            status_map = {"claim": "RESOLVED", "commitment": "DONE", "decision": "SUPERSEDED"}
            new_status = status_map.get(m.get("kind"), "RESOLVED")
            memory.update(m["id"], status=new_status)
    notify.resolve(aid)
    return {"resolved": aid, "status": "ok"}


@app.post("/forget")
def forget(body: ForgetRequest):
    """Privacy forget action: by topic or time window."""
    if body.minutes:
        cmd = {"type": "forget_recent", "minutes": body.minutes}
        res = pipeline._command("manual", body.uid, "web", cmd, C.now())
        return res
    if body.topic:
        cmd = {"type": "forget_topic", "topic": body.topic}
        res = pipeline._command("manual", body.uid, "web", cmd, C.now())
        return res
    raise HTTPException(status_code=400, detail="Must provide either 'topic' or 'minutes'")


@app.get("/trace")
def get_trace(since: int = Query(default=0)):
    """Returns observable agent workflow events."""
    return [e for e in pipeline.TRACE if e["n"] > since]


# ==========================================
# DEMO MODE & JUDGE SEQUENCE
# ==========================================
DEMO_SCENARIO_STEPS = [
    {
        "step": 1,
        "title": "Day 1 — Commitment",
        "text": "I'll finish the authentication API by Friday.",
        "description": "User commits to completing the authentication API. Extractor detects commitment, Qdrant stores OPEN status.",
    },
    {
        "step": 2,
        "title": "Day 2 — Decision",
        "text": "Let's use PostgreSQL for the database.",
        "description": "User makes an architecture decision. Qdrant stores ACTIVE decision.",
    },
    {
        "step": 3,
        "title": "Day 3 — Blocker Dependency",
        "text": "The authentication API is blocking our demo.",
        "description": "User notes a blocker. Auditor links to Day 1 commitment, Manager marks it BLOCKED.",
    },
    {
        "step": 4,
        "title": "Day 4 — Blocker Resolution",
        "text": "Authentication is fixed now.",
        "description": "User resolves the issue. Blocker claim moves to RESOLVED, commitment moves back to OPEN/unblocked.",
    },
    {
        "step": 5,
        "title": "Day 5 — Autonomous Conflict / Consistency Warning",
        "text": "We're still blocked because authentication isn't ready.",
        "description": "User says auth isn't ready after just stating it was fixed. Auditor detects conflict, Manager issues Receipt with evidence!",
    },
    {
        "step": 6,
        "title": "Privacy — Forget Topic",
        "text": "Receipts, forget about authentication",
        "description": "Privacy command wipes all authentication memories and updates retrieval immediately.",
    },
]


@app.post("/demo/seed")
def seed_demo_data(body: SeedRequest):
    """Pre-seeds standard demo commitments and decisions."""
    uid = body.uid or "demo"
    day = 86400
    now = C.now()
    yesterday = (now - timedelta(days=1)).replace(hour=18, minute=0, second=0, microsecond=0, tzinfo=None).isoformat()
    base = {"person": "you", "visibility": "personal", "polarity": None, "deadline_iso": None, "deadline_phrase": None}

    items = [
        ("The API is blocked because authentication isn't working.", "claim", "authentication", "CURRENT", "negative", 7, {}),
        ("Let's use PostgreSQL for the database.", "decision", "database", "ACTIVE", None, 2, {}),
        ("I'll finish the API integration by Friday.", "commitment", "api", "OPEN", None, 3,
         {"deadline_phrase": "friday", "deadline_iso": (now + timedelta(days=3)).replace(tzinfo=None).isoformat()}),
        ("I'll send the report tomorrow.", "commitment", "report", "OPEN", None, 2,
         {"deadline_phrase": "tomorrow", "deadline_iso": yesterday}),
    ]

    for text, kind, subj, status, pol, age, extra in items:
        memory.add(
            uid,
            {**base, "text": text, "kind": kind, "subject": subj, "status": status, "polarity": pol, **extra},
            ts=time.time() - age * day,
        )

    return {"seeded": len(items), "uid": uid}


@app.post("/demo/overdue-check")
def trigger_overdue_check(uid: Optional[str] = Query(default=None)):
    """Manually triggers the autonomous overdue scheduler."""
    alerts_count = pipeline.check_overdue(uid=uid)
    return {"alerts": alerts_count, "status": "ok"}


@app.post("/demo/step")
def run_demo_step(body: DemoStepRequest):
    """Executes a specific step of the judge walkthrough scenario."""
    step_idx = body.step - 1
    if 0 <= step_idx < len(DEMO_SCENARIO_STEPS):
        scenario = DEMO_SCENARIO_STEPS[step_idx]
        res = pipeline.process(uid=body.uid, text=scenario["text"], session_id="demo-runner")
        return {
            "step": body.step,
            "title": scenario["title"],
            "text": scenario["text"],
            "description": scenario["description"],
            "pipeline_result": res,
        }
    raise HTTPException(status_code=400, detail="Step must be between 1 and 6")


@app.get("/demo/scenario")
def get_demo_scenario():
    """Returns the scenario steps definition for the UI."""
    return {"steps": DEMO_SCENARIO_STEPS}
