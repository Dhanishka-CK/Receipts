import os
from datetime import datetime
from zoneinfo import ZoneInfo
from dotenv import load_dotenv

load_dotenv()
env = lambda k, d="": os.getenv(k, d)

LYZR_URL = "https://agent-prod.studio.lyzr.ai/v3/inference/chat/"
LYZR_API_KEY = env("LYZR_API_KEY")
AGENT_IDS = {
    "extractor": env("LYZR_EXTRACTOR_AGENT_ID"),
    "auditor": env("LYZR_AUDITOR_AGENT_ID"),
    "manager": env("LYZR_MANAGER_AGENT_ID"),
}
MOCK_AGENTS = env("MOCK_AGENTS", "auto")

QDRANT_URL = env("QDRANT_URL")
QDRANT_API_KEY = env("QDRANT_API_KEY")
QDRANT_PATH = env("QDRANT_PATH", "./qdrant_data")
COLLECTION = env("QDRANT_COLLECTION", "receipts_memory")
EMBED_BACKEND = env("EMBED_BACKEND", "fastembed")

OMI_APP_ID = env("OMI_APP_ID")
OMI_APP_SECRET = env("OMI_APP_SECRET")

TZ = ZoneInfo(env("TZ", "Asia/Kolkata"))
MIN_CONFIDENCE = float(env("MIN_CONFIDENCE", "0.7"))
MAX_ALERTS_PER_HOUR = int(env("MAX_ALERTS_PER_HOUR", "10"))
FORGET_MIN_SCORE = float(env("FORGET_MIN_SCORE", "0.45"))
REALTIME_IDLE_SECONDS = float(env("REALTIME_IDLE_SECONDS", "4"))


def use_mock() -> bool:
    if MOCK_AGENTS == "1":
        return True
    if MOCK_AGENTS == "0":
        return False
    return not (LYZR_API_KEY and all(AGENT_IDS.values()))


def now() -> datetime:
    return datetime.now(TZ)


def to_ts(iso):
    if not iso:
        return None
    try:
        dt = datetime.fromisoformat(iso)
    except ValueError:
        return None
    return (dt if dt.tzinfo else dt.replace(tzinfo=TZ)).timestamp()
