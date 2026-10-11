import os
import sys
from pathlib import Path

# Ensure project root is in sys.path
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Set test defaults for mock and embedding backend
os.environ["MOCK_AGENTS"] = "1"
os.environ["EMBED_BACKEND"] = "hash"
os.environ["QDRANT_URL"] = ""

try:
    import receipts.config as C
    C.MOCK_AGENTS = "1"
    C.EMBED_BACKEND = "hash"
    C.QDRANT_URL = ""
except ImportError:
    pass

