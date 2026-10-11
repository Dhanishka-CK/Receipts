"""Pydantic schemas for Receipts API endpoints."""
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class IngestRequest(BaseModel):
    uid: Optional[str] = Field(default=None, description="User ID or speaker identifier")
    text: str = Field(..., description="Transcript or spoken text to process")
    session_id: str = Field(default="web", description="Session or channel identifier")


class AskRequest(BaseModel):
    uid: Optional[str] = Field(default=None, description="User ID to query memories for")
    query: str = Field(..., description="Question to ask past memories")
    limit: int = Field(default=5, ge=1, le=20, description="Max memories to retrieve")


class ForgetRequest(BaseModel):
    uid: str = Field(default="demo", description="User ID")
    topic: Optional[str] = Field(default=None, description="Topic phrase to forget")
    minutes: Optional[int] = Field(default=None, description="Forget memories in the last N minutes")


class SeedRequest(BaseModel):
    uid: str = Field(default="demo", description="Target user ID to seed with demo data")


class DemoStepRequest(BaseModel):
    uid: str = Field(default="demo", description="User ID")
    step: int = Field(..., ge=1, le=6, description="Step number (1-6) in the demo scenario")


class MemoryItem(BaseModel):
    id: str
    uid: str
    kind: str
    subject: str
    text: str
    status: str
    person: Optional[str] = "you"
    deadline_iso: Optional[str] = None
    deadline_phrase: Optional[str] = None
    polarity: Optional[str] = None
    visibility: str = "personal"
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    ts: float


class AlertItem(BaseModel):
    id: int
    uid: str
    kind: str
    message: str
    headline: Optional[str] = None
    statement: Optional[str] = None
    evidence: Optional[str] = None
    confidence: Optional[float] = None
    target_id: Optional[str] = None
    key: str
    ts: float
    resolved: bool = False
    pushed: bool = False


class HealthResponse(BaseModel):
    ok: bool
    status: str
    mock_agents: bool
    embeddings: str
    qdrant: Dict[str, Any]
    lyzr_configured: bool
    omi_configured: bool
