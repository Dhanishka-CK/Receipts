"""Rule-based stand-ins for the three Lyzr agents (Extractor, Auditor, Manager).

Used for deterministic tests, local development, and judge demo workflows.
Real runs invoke the Lyzr agents defined in prompts/.
"""
import re
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
ALIASES = {
    "auth": "authentication",
    "login": "authentication",
    "postgres": "database",
    "postgresql": "database",
    "mongodb": "database",
    "mysql": "database",
    "sqlite": "database",
    "deployment": "deploy",
}
SUBJECTS = [
    "authentication",
    "auth",
    "login",
    "api",
    "report",
    "demo",
    "backend",
    "frontend",
    "venue",
    "invoice",
    "deploy",
    "deployment",
    "postgresql",
    "postgres",
    "mongodb",
    "mysql",
    "sqlite",
    "database",
]

NEG = re.compile(
    r"\b(blocked|blocking|not ready|isn't ready|isnt ready|waiting|broken|failing|stuck|not working|not fixed|preventing)\b",
    re.I,
)
POS = re.compile(
    r"\b(fixed|ready|done|finished|working|resolved|completed|unblocked)\b",
    re.I,
)
DECIDE = re.compile(
    r"(let's use|lets use|we're going with|we are going with|we decided|going with|we'll use|let's go with|decision is to)",
    re.I,
)
COMMIT = re.compile(
    r"\b(i'll|i will|we'll|we will|i need to|i have to|i'm going to|let's ship|lets ship|we should ship|promise to)\b",
    re.I,
)
DATE = re.compile(r"\b(today|tomorrow|" + "|".join(DAYS) + r")\b", re.I)
FORGET_RECENT = re.compile(r"forget (?:the )?last (\d+) minutes?", re.I)
FORGET_TOPIC = re.compile(
    r"forget (?:what i said )?(?:about |everything about )?(.+)", re.I
)
PRIVATE = re.compile(
    r"(don't|do not) remember (anything )?(from )?(this|the) conversation|this is private|go private",
    re.I,
)


def _subject(s: str) -> str:
    for w in SUBJECTS:
        if re.search(rf"\b{w}\b", s, re.I):
            return ALIASES.get(w, w)
    return "general"


def _deadline(s: str, now: datetime) -> Tuple[Optional[str], Optional[str]]:
    m = DATE.search(s)
    if not m:
        return None, None
    p = m.group(1).lower()
    if p == "today":
        d = now
    elif p == "tomorrow":
        d = now + timedelta(days=1)
    else:
        target_day = DAYS.index(p)
        days_ahead = (target_day - now.weekday()) % 7
        d = now + timedelta(days=days_ahead if days_ahead > 0 else 7)
    iso = d.replace(hour=23, minute=59, second=0, microsecond=0, tzinfo=None).isoformat()
    return iso, p


def extractor(p: Dict[str, Any]) -> Dict[str, Any]:
    text = p.get("text", "").strip()
    now_raw = p.get("now")
    try:
        now = datetime.fromisoformat(now_raw) if now_raw else datetime.now()
    except Exception:
        now = datetime.now()

    # Strip conversational prefix if user explicitly addresses "Receipts"
    t = re.sub(r"^\s*receipts[,:]?\s*", "", text, flags=re.I)

    # Privacy voice commands
    if PRIVATE.search(t):
        return {"items": [], "command": {"type": "private_on"}}
    if (m := FORGET_RECENT.search(t)):
        return {"items": [], "command": {"type": "forget_recent", "minutes": int(m.group(1))}}
    if re.match(r"forget\b", t, re.I) and (m := FORGET_TOPIC.search(t)):
        return {"items": [], "command": {"type": "forget_topic", "topic": m.group(1).strip(" .")}}

    items = []
    # Split sentences cleanly
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", t) if s.strip()]
    if not sentences and t:
        sentences = [t]

    for s in sentences:
        subj = _subject(s)
        base = {
            "text": s,
            "person": "you",
            "visibility": "personal",
            "deadline_iso": None,
            "deadline_phrase": None,
            "polarity": None,
            "confidence": 0.92,
        }

        if DECIDE.search(s):
            items.append({**base, "kind": "decision", "subject": subj})
        elif COMMIT.search(s):
            iso, ph = _deadline(s, now)
            items.append({**base, "kind": "commitment", "deadline_iso": iso, "deadline_phrase": ph, "subject": subj})
        elif NEG.search(s) or POS.search(s):
            polarity = "negative" if NEG.search(s) else "positive"
            items.append({**base, "kind": "claim", "polarity": polarity, "subject": subj})
        else:
            # Check if it has a recognized subject worth retaining
            if subj != "general":
                items.append({**base, "kind": "claim", "subject": subj, "polarity": "positive"})

    return {"items": items}


def _topics_related(subj1: str, text1: str, subj2: str, text2: str) -> bool:
    """Checks if two items share semantic context."""
    if subj1 != "general" and subj1 == subj2:
        return True
    t1_lower, t2_lower = text1.lower(), text2.lower()
    for w in SUBJECTS:
        norm = ALIASES.get(w, w)
        if (w in t1_lower or norm in t1_lower) and (w in t2_lower or norm in t2_lower):
            return True
    return False


def auditor(p: Dict[str, Any]) -> Dict[str, Any]:
    n = p.get("new") or {}
    related = p.get("related") or []
    n_kind = n.get("kind")
    n_text = n.get("text", "")
    n_subj = n.get("subject", "general")
    n_pol = n.get("polarity")

    for r in related:
        r_id = r.get("id")
        r_kind = r.get("kind")
        r_text = r.get("text", "")
        r_subj = r.get("subject", "general")
        r_status = r.get("status", "")
        r_pol = r.get("polarity")

        if not _topics_related(n_subj, n_text, r_subj, r_text):
            continue

        base = {"target_id": r_id, "confidence": 0.9}

        # 1. Decision changed / duplicate
        if n_kind == "decision" and r_kind == "decision" and r_status == "ACTIVE":
            if r_text.lower().strip() == n_text.lower().strip():
                return {**base, "relation": "duplicate", "explanation": "Identical active decision already recorded."}
            return {
                **base,
                "relation": "decision_changed",
                "suggested_status": "SUPERSEDED",
                "explanation": f"Earlier decision: \"{r_text}\"",
            }

        # 2. Blocker detected (e.g. "The auth API is blocking our demo" vs open commitment or claim)
        if (n_kind == "claim" and n_pol == "negative") and NEG.search(n_text):
            if r_kind == "commitment" and r_status == "OPEN":
                return {
                    **base,
                    "relation": "blocker_detected",
                    "suggested_status": "BLOCKED",
                    "explanation": f"Commitment is now blocked: \"{r_text}\"",
                }
            if r_kind == "claim" and r_status == "RESOLVED":
                return {
                    **base,
                    "relation": "possible_contradiction",
                    "explanation": f"Earlier you said this was resolved: \"{r_text}\"",
                }

        # 3. Status update / Blocker resolved (e.g. "Authentication is fixed now")
        if n_kind == "claim" and n_pol == "positive":
            if r_kind == "claim" and r_status == "CURRENT" and r_pol == "negative":
                return {
                    **base,
                    "relation": "status_update",
                    "suggested_status": "RESOLVED",
                    "explanation": f"New statement resolves: \"{r_text}\"",
                }
            if r_kind == "commitment" and r_status == "BLOCKED":
                return {
                    **base,
                    "relation": "blocker_resolved",
                    "suggested_status": "OPEN",
                    "explanation": f"Unblocks earlier commitment: \"{r_text}\"",
                }
            if r_kind == "commitment" and r_status == "OPEN":
                return {
                    **base,
                    "relation": "status_update",
                    "suggested_status": "DONE",
                    "explanation": f"Fulfills open commitment: \"{r_text}\"",
                }

        # 4. Possible contradiction between claims
        if n_kind == "claim" and r_kind == "claim" and r_pol and n_pol:
            if r_status in ("CURRENT", "RESOLVED") and r_pol != n_pol:
                return {
                    **base,
                    "relation": "possible_contradiction",
                    "explanation": f"Earlier you said: \"{r_text}\"",
                }

        # 5. Contradiction / Prerequisite conflict: Shipping while blocked or conflicting
        if n_kind == "commitment" and ("ship" in n_text.lower() or "demo" in n_text.lower()):
            if r_kind == "claim" and (r_status == "CURRENT" and r_pol == "negative"):
                return {
                    **base,
                    "relation": "possible_contradiction",
                    "explanation": f"Earlier you noted the demo was blocked: \"{r_text}\"",
                }
            if r_kind == "commitment" and r_status == "BLOCKED":
                return {
                    **base,
                    "relation": "possible_contradiction",
                    "explanation": f"Related prerequisite commitment is currently BLOCKED: \"{r_text}\"",
                }

        # 6. Duplicate commitment
        if n_kind == "commitment" and r_kind == "commitment" and r_status == "OPEN":
            if r_text.lower().strip() == n_text.lower().strip():
                return {**base, "relation": "duplicate", "explanation": "Identical open commitment already stored."}

    return {"relation": "none", "target_id": None, "confidence": 0.0, "explanation": "Nothing contradictory or related found."}


def manager(p: Dict[str, Any]) -> Dict[str, Any]:
    a = p.get("audit") or {}
    t = p.get("target") or {}
    n = p.get("new") or {}
    rel = a.get("relation")

    out = {
        "action": "store_only",
        "update_target_status": None,
        "alert_message": None,
        "importance": "low",
        "reason": f"relation={rel}",
    }

    if rel == "decision_changed":
        out.update(
            action="alert",
            update_target_status="SUPERSEDED",
            importance="high",
            alert_message=f"Decision changed. Before: \"{t.get('text', '')}\". Now: \"{n.get('text', '')}\".",
        )
    elif rel == "possible_contradiction":
        out.update(
            action="alert",
            importance="high",
            alert_message=f"Possible contradiction. Earlier: \"{t.get('text', '')}\". Now: \"{n.get('text', '')}\". Still current?",
        )
    elif rel == "blocker_detected":
        out.update(
            action="alert",
            update_target_status="BLOCKED",
            importance="high",
            alert_message=f"Work blocked. Commitment \"{t.get('text', '')}\" is now marked BLOCKED by: \"{n.get('text', '')}\".",
        )
    elif rel == "blocker_resolved":
        out.update(
            action="store_only",
            update_target_status="OPEN",
            importance="medium",
            reason=f"Unblocked target: {t.get('text', '')}",
        )
    elif rel == "status_update":
        out.update(
            action="store_only",
            update_target_status=a.get("suggested_status"),
            importance="medium",
            reason=f"Status updated to {a.get('suggested_status')}",
        )
    elif rel == "overdue":
        out.update(
            action="alert",
            importance="high",
            alert_message=f"Open commitment is overdue: \"{t.get('text', '')}\"",
        )

    return out
