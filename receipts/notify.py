import itertools
import json
from pathlib import Path
import time
from typing import Any, Dict, List, Optional
import requests
from . import config as C

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DATA_DIR.mkdir(exist_ok=True)
ALERTS_FILE = DATA_DIR / "receipts_store.json"

def _load_alerts() -> List[Dict[str, Any]]:
    if ALERTS_FILE.exists():
        try:
            return json.loads(ALERTS_FILE.read_text(encoding="utf-8"))
        except Exception:
            return []
    return []

def _save_alerts():
    try:
        ALERTS_FILE.write_text(json.dumps(ALERTS, indent=2), encoding="utf-8")
    except Exception:
        pass

ALERTS: List[Dict[str, Any]] = _load_alerts()
_max_id = max((a.get("id", 0) for a in ALERTS), default=0)
_ids = itertools.count(_max_id + 1)

HEADLINES = {
    "possible_contradiction": "⚠ Possible Contradiction",
    "contradiction": "⚠ Contradiction Detected",
    "decision_changed": "🔄 Decision Changed",
    "blocker_detected": "🚫 Blocker Detected",
    "blocker_resolved": "✅ Blocker Resolved",
    "overdue": "⏰ Overdue Commitment",
    "status_update": "ℹ Status Updated",
    "duplicate": "📎 Duplicate Statement",
}


def send(
    uid: str,
    kind: str,
    message: str,
    target_id: Optional[str] = None,
    key: Optional[str] = None,
    statement: Optional[str] = None,
    evidence: Optional[str] = None,
    confidence: Optional[float] = None,
    importance: str = "medium",
    action_taken: str = "alert",
    groundedness: float = 1.0,
    grounding_source: Optional[str] = None,
    telemetry: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    """Generates an evidence-backed Receipt/Alert.

    Returns the created receipt, or None if suppressed by deduplication or rate limits.
    """
    now = time.time()
    key = key or f"{kind}:{target_id}:{message}"

    # Deduplication
    if any(a["key"] == key for a in ALERTS):
        return None

    # Rate limiting
    if sum(1 for a in ALERTS if a["uid"] == uid and now - a["ts"] < 3600) >= C.MAX_ALERTS_PER_HOUR:
        return None

    headline = HEADLINES.get(kind, f"Receipt: {kind.replace('_', ' ').title()}")
    receipt = {
        "id": next(_ids),
        "uid": uid,
        "kind": kind,
        "headline": headline,
        "message": message,
        "statement": statement,
        "evidence": evidence,
        "confidence": confidence if confidence is not None else 0.85,
        "groundedness": groundedness,
        "grounding_source": grounding_source or (f"Qdrant Vector ID {target_id[:8]}" if target_id else "Verified Voice History"),
        "telemetry": telemetry or {},
        "importance": importance,
        "action_taken": action_taken,
        "target_id": target_id,
        "key": key,
        "ts": now,
        "resolved": False,
        "pushed": False,
    }
    ALERTS.append(receipt)
    _save_alerts()
    receipt["pushed"] = _push_to_omi(uid, message)
    return receipt


def _push_to_omi(uid: str, message: str) -> bool:
    if not (C.OMI_APP_ID and C.OMI_APP_SECRET) or uid == "demo":
        return False
    try:
        r = requests.post(
            f"https://api.omi.me/v2/integrations/{C.OMI_APP_ID}/notification",
            params={"uid": uid, "message": message[:300]},
            headers={"Authorization": f"Bearer {C.OMI_APP_SECRET}"},
            timeout=10,
        )
        return r.ok
    except requests.RequestException:
        return False


def get(aid: int) -> Optional[Dict[str, Any]]:
    return next((a for a in ALERTS if a["id"] == aid), None)


def list_for_user(uid: str = "") -> List[Dict[str, Any]]:
    if not uid or uid == "all":
        return list(reversed(ALERTS))
    matched = [a for a in reversed(ALERTS) if a["uid"] == uid]
    if not matched and ALERTS:
        return list(reversed(ALERTS))
    return matched


def resolve(aid: int) -> bool:
    a = get(aid)
    if a:
        a["resolved"] = True
        _save_alerts()
        return True
    return False
