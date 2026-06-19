"""Pydantic schemas (API + agent contracts)."""
from __future__ import annotations

from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


# ---------- Agent / domain schemas ----------


class ActionItem(BaseModel):
    """Action item extracted from a meeting transcript."""

    description: str = Field(..., description="What needs to be done")
    assignee: Optional[str] = Field(None, description="Person responsible")
    due_date: Optional[datetime] = Field(None, description="Due date if specified")
    priority: Literal["high", "medium", "low"] = "medium"
    category: str = Field("general", description="e.g. engineering, sales, ops")


class MeetingSummary(BaseModel):
    """Final structured meeting summary."""

    title: str
    participants: List[str] = Field(default_factory=list)
    key_decisions: List[str] = Field(default_factory=list)
    action_items: List[ActionItem] = Field(default_factory=list)
    next_steps: List[str] = Field(default_factory=list)
    duration_minutes: int = 0


class Intent(BaseModel):
    """LLM-classified user query intent."""

    intent: Literal["search", "action", "summary", "qa"] = "search"
    confidence: float = 0.5
    rationale: str = ""


# ---------- Search ----------


class SearchHit(BaseModel):
    meeting_id: str
    segment_id: Optional[str] = None
    score: float
    text: str
    title: Optional[str] = None
    started_at: Optional[datetime] = None


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000)
    top_k: int = Field(default=8, ge=1, le=100)
    multi_query: bool = True
    alpha: float = Field(default=0.5, ge=0.0, le=1.0)


class SearchResponse(BaseModel):
    intent: Intent
    expanded_queries: List[str] = Field(default_factory=list)
    hits: List[SearchHit] = Field(default_factory=list)


# ---------- API ----------


class MeetingCreate(BaseModel):
    title: Optional[str] = Field(default=None, max_length=512)


class MeetingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    title: str
    started_at: datetime
    ended_at: Optional[datetime] = None
    duration_seconds: int
    status: str
    transcript: str
    summary: Optional[str] = None
    key_decisions: Optional[list] = None
    next_steps: Optional[list] = None
    participants: Optional[list] = None
    related_meeting_ids: Optional[list] = None


class TranscriptSegmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    speaker: Optional[str] = None
    start_ms: int
    end_ms: int
    text: str
    is_final: bool


class ActionItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    meeting_id: str
    description: str
    assignee: Optional[str] = None
    due_date: Optional[datetime] = None
    priority: str
    category: str
    approved: bool
    completed: bool
    external_id: Optional[str] = None


class ApprovalOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    meeting_id: str
    tool_name: str
    payload: dict
    status: str
    result: Optional[dict] = None
    error: Optional[str] = None
    created_at: datetime


class TranscribeFinalize(BaseModel):
    """Body for /meetings/{id}/finalize."""

    transcript: Optional[str] = Field(default=None, max_length=500_000)
    autopilot: Optional[bool] = None
