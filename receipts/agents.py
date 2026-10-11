"""Thin client for the three Lyzr agents (Extractor, Auditor, Manager)."""
import json
import logging
import re
import uuid
from typing import Any, Dict
import requests
from . import config as C

logger = logging.getLogger("receipts.agents")


class AgentError(Exception):
    pass


def _parse_json(text: str) -> dict:
    text = text or ""
    # Strip markdown code blocks if any
    text = re.sub(r"```(?:json)?", "", text)
    text = text.strip()
    a, b = text.find("{"), text.rfind("}")
    if a < 0 or b < a:
        raise AgentError(f"agent did not return JSON: {text[:120]!r}")
    try:
        return json.loads(text[a : b + 1])
    except json.JSONDecodeError as e:
        raise AgentError(f"agent JSON decode error: {e} in {text[a : b + 1][:120]!r}")


def run(role: str, payload: dict, uid: str = "receipts") -> dict:
    if C.use_mock():
        from . import mock
        return getattr(mock, role)(payload)

    agent_id = C.AGENT_IDS.get(role)
    if not agent_id or not C.LYZR_API_KEY:
        raise AgentError(f"Lyzr credentials missing for role '{role}'. Please set LYZR_API_KEY and LYZR_{role.upper()}_AGENT_ID.")

    try:
        logger.info("[LYZR] Calling Lyzr Agent API for role=%s agent_id=%s uid=%s", role, agent_id, uid)
        r = requests.post(
            C.LYZR_URL,
            headers={"Content-Type": "application/json", "x-api-key": C.LYZR_API_KEY},
            json={
                "user_id": uid,
                "agent_id": agent_id,
                "session_id": f"{role}-{uuid.uuid4().hex}",  # fresh session: no history bleed
                "message": json.dumps(payload),
            },
            timeout=60,
        )
        r.raise_for_status()
        data = r.json()
        raw = data.get("response") or data.get("message") or data.get("data") or data.get("reply") or ""
        if isinstance(raw, dict):
            return raw
        return _parse_json(str(raw))
    except requests.RequestException as e:
        raise AgentError(f"Lyzr API connection error for {role}: {e}") from e
    except Exception as e:
        raise AgentError(f"{role} failed: {e}") from e
