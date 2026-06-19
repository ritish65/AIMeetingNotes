"""Unit tests for app.services.meeting_processor."""
from __future__ import annotations

import pytest
from sqlalchemy import select

from app.db import session_scope
from app.models import (
    ActionItem,
    ApprovalRequest,
    ApprovalStatus,
    Meeting,
    MeetingStatus,
)
from app.services.meeting_processor import (
    _auto_execute_approvals,
    process_meeting_pipeline,
)


async def _create_meeting(title: str = "Test Meeting") -> str:
    async with session_scope() as db:
        m = Meeting(title=title, status=MeetingStatus.recording)
        db.add(m)
        await db.commit()
        await db.refresh(m)
        return m.id


@pytest.mark.asyncio
class TestProcessMeetingPipeline:
    async def test_pipeline_completes(self):
        mid = await _create_meeting("Pipeline Test")
        transcript = "Sarah: We need to finish the report. John: I'll handle the deployment."
        await process_meeting_pipeline(mid, transcript)

        async with session_scope() as db:
            res = await db.execute(select(Meeting).where(Meeting.id == mid))
            meeting = res.scalar_one_or_none()
            assert meeting is not None
            assert meeting.status == MeetingStatus.completed
            assert meeting.summary is not None
            assert meeting.ended_at is not None

    async def test_pipeline_creates_action_items(self):
        mid = await _create_meeting("Action Items Test")
        transcript = "Alice: Complete the migration by Friday."
        await process_meeting_pipeline(mid, transcript)

        async with session_scope() as db:
            res = await db.execute(
                select(ActionItem).where(ActionItem.meeting_id == mid)
            )
            items = list(res.scalars().all())
            assert len(items) >= 1

    async def test_pipeline_creates_approval_requests(self):
        mid = await _create_meeting("Approvals Test")
        transcript = "Bob: Fix the bug in the auth module."
        await process_meeting_pipeline(mid, transcript)

        async with session_scope() as db:
            res = await db.execute(
                select(ApprovalRequest).where(ApprovalRequest.meeting_id == mid)
            )
            approvals = list(res.scalars().all())
            # Should have at least todoist + email approvals
            assert len(approvals) >= 1

    async def test_pipeline_missing_meeting(self):
        # Should return gracefully without error
        await process_meeting_pipeline("nonexistent-id", "some transcript")

    async def test_pipeline_indexes_meeting(self):
        # Force search index to pure-fallback mode to avoid Qdrant connection errors
        from app.search.index import get_search_index

        idx = get_search_index()
        idx.use_fallback = True
        idx.qdrant_client = None

        mid = await _create_meeting("Index Test")
        transcript = "Discussion about indexing search."
        await process_meeting_pipeline(mid, transcript)

        async with session_scope() as db:
            res = await db.execute(select(Meeting).where(Meeting.id == mid))
            meeting = res.scalar_one_or_none()
            assert meeting is not None
            assert meeting.indexed is True


@pytest.mark.asyncio
class TestAutoExecuteApprovals:
    async def test_auto_execute_pending(self):
        mid = await _create_meeting("Auto Execute Test")

        async with session_scope() as db:
            req = ApprovalRequest(
                meeting_id=mid,
                tool_name="add_to_todoist",
                payload={"task": "Auto task", "priority": "medium"},
                status=ApprovalStatus.pending,
            )
            db.add(req)
            await db.commit()
            await db.refresh(req)
            req_id = req.id

        await _auto_execute_approvals(mid)

        async with session_scope() as db:
            res = await db.execute(
                select(ApprovalRequest).where(ApprovalRequest.id == req_id)
            )
            updated = res.scalar_one_or_none()
            assert updated is not None
            assert updated.status == ApprovalStatus.executed
            assert updated.result is not None

    async def test_auto_execute_no_pending(self):
        mid = await _create_meeting("No Pending Test")
        # Should not raise
        await _auto_execute_approvals(mid)
