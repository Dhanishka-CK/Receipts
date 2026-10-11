"""Omi webhook payload normalization layer.

Supports varied Omi firmware/app webhook formats:
- Realtime transcript chunks (lists, segment dicts, raw text)
- Conversation memory events (structured overview, transcript segments)
- Flexible user identification (query param, headers, or payload body)
"""
import logging
import time
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("receipts.omi")


def extract_user_id(
    payload: Any,
    query_uid: Optional[str] = None,
    header_uid: Optional[str] = None,
    default: str = "demo",
) -> str:
    """Extracts UID with cascading fallback: query param -> header -> payload body -> default."""
    if query_uid and query_uid.strip():
        return query_uid.strip()
    if header_uid and header_uid.strip():
        return header_uid.strip()
    if isinstance(payload, dict):
        for key in ("uid", "user_id", "userId", "speaker_id", "speaker"):
            val = payload.get(key)
            if val and isinstance(val, str) and val.strip():
                return val.strip()
    return default


def normalize_realtime_payload(
    payload: Any,
    query_uid: Optional[str] = None,
    query_session: Optional[str] = None,
    header_uid: Optional[str] = None,
) -> Tuple[str, str, str, List[Dict[str, Any]]]:
    """Normalizes an incoming Omi realtime transcript payload.

    Returns:
        (uid, session_id, combined_text, segments_list)
    """
    uid = extract_user_id(payload, query_uid, header_uid, default="demo")
    session_id = query_session or "omi-live"
    segments: List[Dict[str, Any]] = []

    if isinstance(payload, list):
        for item in payload:
            if isinstance(item, dict):
                segments.append(item)
            elif isinstance(item, str) and item.strip():
                segments.append({"text": item.strip()})
    elif isinstance(payload, dict):
        session_id = str(payload.get("session_id") or payload.get("sessionId") or session_id)
        if "segments" in payload and isinstance(payload["segments"], list):
            segments.extend(payload["segments"])
        elif "transcript_segments" in payload and isinstance(payload["transcript_segments"], list):
            segments.extend(payload["transcript_segments"])
        elif "conversation" in payload and isinstance(payload["conversation"], dict):
            conv = payload["conversation"]
            segments.extend(conv.get("segments") or conv.get("transcript_segments") or [])
        elif "text" in payload and isinstance(payload["text"], str):
            segments.append({"text": payload["text"]})
        elif "transcript" in payload and isinstance(payload["transcript"], str):
            segments.append({"text": payload["transcript"]})

    text_parts = []
    for s in segments:
        if isinstance(s, dict):
            t = s.get("text", "").strip()
            if t:
                text_parts.append(t)
        elif isinstance(s, str) and s.strip():
            text_parts.append(s.strip())

    combined_text = " ".join(text_parts).strip()
    logger.info("[OMI] Realtime transcript received for uid=%s: '%s'", uid, combined_text[:80])
    return uid, session_id, combined_text, segments


def normalize_conversation_payload(
    payload: Any,
    query_uid: Optional[str] = None,
    header_uid: Optional[str] = None,
) -> Tuple[str, str, str, Dict[str, Any]]:
    """Normalizes an Omi conversation/memory completion webhook.

    Returns:
        (uid, conversation_id, combined_text, metadata)
    """
    uid = extract_user_id(payload, query_uid, header_uid, default="demo")
    conv_id = f"conv-{int(time.time())}"
    metadata: Dict[str, Any] = {}
    text_parts: List[str] = []

    if isinstance(payload, dict):
        conv_id = str(payload.get("id") or payload.get("conversation_id") or conv_id)
        structured = payload.get("structured") or {}
        if isinstance(structured, dict):
            metadata["title"] = structured.get("title", "")
            metadata["overview"] = structured.get("overview", "")
            metadata["action_items"] = structured.get("action_items", [])

        # Check transcript segments
        segs = (
            payload.get("transcript_segments")
            or payload.get("segments")
            or (payload.get("conversation", {}).get("transcript_segments") if isinstance(payload.get("conversation"), dict) else None)
            or []
        )
        for s in segs:
            if isinstance(s, dict) and s.get("text"):
                text_parts.append(s["text"].strip())
            elif isinstance(s, str) and s.strip():
                text_parts.append(s.strip())

        # Direct text or transcript fallback
        if not text_parts:
            raw_text = payload.get("transcript") or payload.get("text") or ""
            if raw_text:
                text_parts.append(str(raw_text).strip())

    combined_text = " ".join(text_parts).strip()
    logger.info("[OMI] Conversation webhook received for uid=%s conv_id=%s: '%s'", uid, conv_id, combined_text[:80])
    return uid, conv_id, combined_text, metadata
