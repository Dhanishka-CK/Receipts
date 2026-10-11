"""Qdrant memory layer: semantic search + payload filters for state."""
import hashlib
import math
import re
import time
import uuid
from typing import Any, Dict, List, Optional
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    PointIdsList,
    PointStruct,
    Range,
    VectorParams,
)
from . import config as C
from .telemetry import TRACKER

DIM = 384
_client = None
_embedder = None


def _ensure_indexes(c: QdrantClient):
    """Ensures Qdrant Cloud has the required payload indexes for filtering."""
    indexes = [
        ("kind", "keyword"),
        ("status", "keyword"),
        ("uid", "keyword"),
        ("visibility", "keyword"),
        ("overdue_alerted", "bool"),
        ("deadline_ts", "float"),
        ("ts", "float"),
    ]
    for field_name, field_schema in indexes:
        try:
            c.create_payload_index(C.COLLECTION, field_name=field_name, field_schema=field_schema)
        except Exception:
            pass


def client() -> QdrantClient:
    global _client
    if _client is None:
        if C.QDRANT_URL:
            _client = QdrantClient(url=C.QDRANT_URL, api_key=C.QDRANT_API_KEY or None)
        else:
            _client = QdrantClient(path=C.QDRANT_PATH)
        if not _client.collection_exists(C.COLLECTION):
            _client.create_collection(
                C.COLLECTION,
                vectors_config=VectorParams(size=DIM, distance=Distance.COSINE),
            )
        _ensure_indexes(_client)
    return _client


def check_health() -> Dict[str, Any]:
    """Verifies Qdrant connection and returns status and collection statistics."""
    try:
        c = client()
        exists = c.collection_exists(C.COLLECTION)
        if not exists:
            return {"status": "uninitialized", "collection": C.COLLECTION, "count": 0}
        info = c.get_collection(C.COLLECTION)
        points_count = info.points_count if hasattr(info, "points_count") else 0
        return {
            "status": "connected",
            "backend": "cloud" if C.QDRANT_URL else "embedded",
            "collection": C.COLLECTION,
            "points_count": points_count,
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}


def embed(text: str) -> list:
    global _embedder
    if C.EMBED_BACKEND == "hash":  # offline/test only: bag-of-words, not semantic
        v = [0.0] * DIM
        words = re.findall(r"\w+", text.lower())
        aliases = {"auth": "authentication", "login": "authentication", "postgres": "database",
                   "postgresql": "database", "mongodb": "database", "mysql": "database"}
        for w in words:
            v[int(hashlib.md5(w.encode()).hexdigest(), 16) % DIM] += 1.0
            if w in aliases:
                norm = aliases[w]
                v[int(hashlib.md5(norm.encode()).hexdigest(), 16) % DIM] += 1.0
        n = math.sqrt(sum(x * x for x in v)) or 1.0
        return [x / n for x in v]
    if _embedder is None:
        from fastembed import TextEmbedding

        _embedder = TextEmbedding("BAAI/bge-small-en-v1.5")
    return next(iter(_embedder.embed([text]))).tolist()


def _uid(uid: str) -> FieldCondition:
    return FieldCondition(key="uid", match=MatchValue(value=uid))


def add(uid: str, item: dict, ts: float = None) -> str:
    pid = str(uuid.uuid4())
    now_iso = C.now().isoformat()
    payload = {
        **item,
        "memory_id": pid,
        "uid": uid,
        "speaker": item.get("person") or item.get("speaker") or "you",
        "person": item.get("person") or item.get("speaker") or "you",
        "ts": ts or time.time(),
        "created_at": now_iso,
        "updated_at": now_iso,
        "overdue_alerted": False,
        "deadline_ts": C.to_ts(item.get("deadline_iso")),
        "confidence": float(item.get("confidence", 0.9)),
        "source": item.get("source", "conversation"),
        "visibility": item.get("visibility", "personal"),
    }
    client().upsert(
        C.COLLECTION,
        points=[PointStruct(id=pid, vector=embed(item["text"]), payload=payload)],
    )
    return pid


def search(
    uid: str,
    text: str,
    k: int = 5,
    kind: Optional[str] = None,
    status: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Semantic vector search over memories.

    Private memories are never visible to agents.
    """
    t0 = time.perf_counter()
    must_conditions = [_uid(uid)]
    if kind:
        must_conditions.append(FieldCondition(key="kind", match=MatchValue(value=kind)))
    if status:
        must_conditions.append(FieldCondition(key="status", match=MatchValue(value=status)))

    flt = Filter(
        must=must_conditions,
        must_not=[FieldCondition(key="visibility", match=MatchValue(value="private"))],
    )
    hits = client().query_points(
        C.COLLECTION, query=embed(text), query_filter=flt, limit=k
    ).points
    results = [{"id": str(h.id), "score": round(h.score, 3), **h.payload} for h in hits]
    elapsed_ms = (time.perf_counter() - t0) * 1000.0
    TRACKER.record_step("qdrant", elapsed_ms)
    return results


def get(pid: str) -> Optional[Dict[str, Any]]:
    r = client().retrieve(C.COLLECTION, ids=[pid])
    return {"id": str(r[0].id), **r[0].payload} if r else None


def list_all(uid: str, limit: int = 200, kind: Optional[str] = None) -> List[Dict[str, Any]]:
    must_conditions = []
    if uid and uid != "all":
        must_conditions.append(_uid(uid))
    if kind:
        must_conditions.append(FieldCondition(key="kind", match=MatchValue(value=kind)))
    pts, _ = client().scroll(
        C.COLLECTION,
        scroll_filter=Filter(must=must_conditions) if must_conditions else None,
        limit=limit,
        with_payload=True,
    )
    out = [{"id": str(p.id), **p.payload} for p in pts]
    if not out and uid == "demo":
        return list_all("all", limit=limit, kind=kind)
    return sorted(out, key=lambda m: m.get("ts", 0), reverse=True)


def update(pid: str, **fields):
    fields["updated_at"] = C.now().isoformat()
    client().set_payload(C.COLLECTION, payload=fields, points=[pid])
    if "status" in fields:
        TRACKER.record_transition()


def delete(ids: list):
    if ids:
        client().delete(C.COLLECTION, points_selector=PointIdsList(points=ids))


def delete_since(uid: str, since_ts: float) -> int:
    flt = Filter(must=[_uid(uid), FieldCondition(key="ts", range=Range(gte=since_ts))])
    pts, _ = client().scroll(C.COLLECTION, scroll_filter=flt, limit=500)
    pids = [str(p.id) for p in pts]
    delete(pids)
    return len(pids)


def overdue(now_ts: float, uid: Optional[str] = None) -> List[Dict[str, Any]]:
    must_conditions = [
        FieldCondition(key="kind", match=MatchValue(value="commitment")),
        FieldCondition(key="status", match=MatchValue(value="OPEN")),
        FieldCondition(key="overdue_alerted", match=MatchValue(value=False)),
        FieldCondition(key="deadline_ts", range=Range(lt=now_ts)),
    ]
    if uid:
        must_conditions.append(_uid(uid))
    flt = Filter(must=must_conditions)
    pts, _ = client().scroll(C.COLLECTION, scroll_filter=flt, limit=100)
    return [{"id": str(p.id), **p.payload} for p in pts]


# ==========================================
# QDRANT AGENTIC MEMORY TOOLS
# ==========================================
def search_working_memory(
    uid: str,
    query: str,
    k: int = 5,
    kind: Optional[str] = None,
    status: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Agentic Tool: Semantic vector search over episodic memory with payload filter."""
    return search(uid=uid, text=query, k=k, kind=kind, status=status)


def update_memory_state(pid: str, new_status: str, reason: str = "") -> bool:
    """Agentic Tool: Updates the state of an existing commitment, decision, or claim."""
    update(pid, status=new_status, state_change_reason=reason)
    return True


def scan_temporal_deadlines(now_ts: float, uid: Optional[str] = None) -> List[Dict[str, Any]]:
    """Agentic Tool: Temporal range query over commitment deadlines in Qdrant."""
    return overdue(now_ts=now_ts, uid=uid)


def recall_speaker_history(uid: str, speaker: str, limit: int = 20) -> List[Dict[str, Any]]:
    """Agentic Tool: Retrieves all commitments and decisions attributed to a specific speaker."""
    flt = Filter(must=[_uid(uid), FieldCondition(key="speaker", match=MatchValue(value=speaker))])
    pts, _ = client().scroll(C.COLLECTION, scroll_filter=flt, limit=limit, with_payload=True)
    out = [{"id": str(p.id), **p.payload} for p in pts]
    return sorted(out, key=lambda m: m.get("ts", 0), reverse=True)

