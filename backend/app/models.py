"""SQLAlchemy ORM models."""
from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import List, Optional

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class MeetingStatus(str, enum.Enum):
    recording = "recording"
    processing = "processing"
    completed = "completed"
    failed = "failed"


class ApprovalStatus(str, enum.Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"
    executed = "executed"
    failed = "failed"


class Priority(str, enum.Enum):
    high = "high"
    medium = "medium"
    low = "low"


class Meeting(Base):
    __tablename__ = "meetings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    title: Mapped[str] = mapped_column(String(512), default="Untitled meeting")
    started_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )
    ended_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    duration_seconds: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[MeetingStatus] = mapped_column(
        Enum(MeetingStatus), default=MeetingStatus.recording
    )
    audio_path: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    transcript: Mapped[str] = mapped_column(Text, default="")
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    key_decisions: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    next_steps: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    participants: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    related_meeting_ids: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    indexed: Mapped[bool] = mapped_column(Boolean, default=False)

    segments: Mapped[List["TranscriptSegment"]] = relationship(
        back_populates="meeting", cascade="all, delete-orphan"
    )
    action_items: Mapped[List["ActionItem"]] = relationship(
        back_populates="meeting", cascade="all, delete-orphan"
    )
    approvals: Mapped[List["ApprovalRequest"]] = relationship(
        back_populates="meeting", cascade="all, delete-orphan"
    )


class TranscriptSegment(Base):
    __tablename__ = "transcript_segments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    meeting_id: Mapped[str] = mapped_column(
        ForeignKey("meetings.id", ondelete="CASCADE"), index=True
    )
    speaker: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    start_ms: Mapped[int] = mapped_column(Integer, default=0)
    end_ms: Mapped[int] = mapped_column(Integer, default=0)
    text: Mapped[str] = mapped_column(Text, default="")
    is_final: Mapped[bool] = mapped_column(Boolean, default=True)

    meeting: Mapped[Meeting] = relationship(back_populates="segments")


class ActionItem(Base):
    __tablename__ = "action_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    meeting_id: Mapped[str] = mapped_column(
        ForeignKey("meetings.id", ondelete="CASCADE"), index=True
    )
    description: Mapped[str] = mapped_column(Text)
    assignee: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    due_date: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    priority: Mapped[Priority] = mapped_column(Enum(Priority), default=Priority.medium)
    category: Mapped[str] = mapped_column(String(128), default="general")
    approved: Mapped[bool] = mapped_column(Boolean, default=False)
    completed: Mapped[bool] = mapped_column(Boolean, default=False)
    external_id: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)

    meeting: Mapped[Meeting] = relationship(back_populates="action_items")


class ApprovalRequest(Base):
    __tablename__ = "approval_requests"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    meeting_id: Mapped[str] = mapped_column(
        ForeignKey("meetings.id", ondelete="CASCADE"), index=True
    )
    tool_name: Mapped[str] = mapped_column(String(128))
    payload: Mapped[dict] = mapped_column(JSON)
    status: Mapped[ApprovalStatus] = mapped_column(
        Enum(ApprovalStatus), default=ApprovalStatus.pending
    )
    result: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    meeting: Mapped[Meeting] = relationship(back_populates="approvals")
