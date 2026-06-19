"""Meeting process pipeline orchestrator.

Runs the multi-agent graph pipeline on finished transcripts, writes results to the 
DB, generates approval action entries for Todoist/GCal/Gmail, and indexes in Qdrant.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, List

from loguru import logger
from sqlalchemy import select

from ..agents.workflow import get_meeting_workflow
from ..db import session_scope
from ..models import ActionItem, ApprovalRequest, ApprovalStatus, Meeting, MeetingStatus, Priority
from ..search.index import get_search_index
from ..tools.registry import execute_tool
from ..utils import fetch_meeting


async def process_meeting_pipeline(meeting_id: str, raw_transcript: str) -> None:
    """Takes finished transcript, runs LangGraph DAG, and indexes results."""
    logger.info("Starting processing pipeline for meeting: {}", meeting_id)

    async with session_scope() as db:
        meeting = await fetch_meeting(db, meeting_id)
        if not meeting:
            logger.error("Meeting {} not found in DB; abandoning pipeline.", meeting_id)
            return

        meeting.status = MeetingStatus.processing
        await db.commit()

    # Step 1: Execute 5-agent LangGraph workflow
    workflow = get_meeting_workflow()
    initial_state = {
        "meeting_id": meeting_id,
        "raw_transcript": raw_transcript,
        "formatted_transcript": "",
        "action_items": [],
        "summary": "",
        "key_decisions": [],
        "next_steps": [],
        "participants": [],
        "related_meetings": [],
        "errors": [],
    }

    try:
        final_state = await workflow.ainvoke(initial_state)
    except Exception as e:
        logger.error("LangGraph DAG failed for meeting {}: {}", meeting_id, e)
        async with session_scope() as db:
            meeting = await fetch_meeting(db, meeting_id)
            if meeting:
                meeting.status = MeetingStatus.failed
            await db.commit()
        return

    # Step 2: Write analysis back to Database
    async with session_scope() as db:
        meeting = await fetch_meeting(db, meeting_id)
        if not meeting:
            logger.error("Meeting {} not found after workflow completion; cannot persist results.", meeting_id)
            return

        meeting.transcript = final_state.get("formatted_transcript") or raw_transcript
        meeting.summary = final_state.get("summary")
        meeting.key_decisions = final_state.get("key_decisions") or []
        meeting.next_steps = final_state.get("next_steps") or []
        meeting.participants = final_state.get("participants") or []
        meeting.ended_at = datetime.now(timezone.utc)
        meeting.status = MeetingStatus.completed

        # Clean old items if re-processing
        # Write Action Items
        extracted_items = final_state.get("action_items") or []
        action_item_objs = []
        for item in extracted_items:
            priority_val = item.get("priority", "medium").lower()
            if priority_val not in ("high", "medium", "low"):
                priority_val = "medium"

            ai = ActionItem(
                meeting_id=meeting_id,
                description=item.get("description", "Unnamed task"),
                assignee=item.get("assignee"),
                due_date=None,  # Parse date safely if string present
                priority=Priority(priority_val),
                category=item.get("category", "general"),
            )
            # Try to parse iso date safely if present
            if item.get("due_date"):
                try:
                    ai.due_date = datetime.fromisoformat(item["due_date"].replace("Z", "+00:00"))
                except (ValueError, TypeError) as e:
                    logger.warning(
                        "Could not parse due_date '{}' for action item '{}': {}",
                        item["due_date"],
                        item.get("description", "unknown"),
                        e,
                    )

            db.add(ai)
            action_item_objs.append(ai)

        # Stage Autonomous Actions / Approval requests
        # 1. Todoist tasks for action items
        from ..config import settings

        for idx, item in enumerate(extracted_items):
            app_req = ApprovalRequest(
                meeting_id=meeting_id,
                tool_name="add_to_todoist",
                payload={
                    "task": item.get("description"),
                    "due_date": item.get("due_date"),
                    "priority": item.get("priority", "medium"),
                },
                status=ApprovalStatus.pending,
            )
            db.add(app_req)

        # 2. Gmail Summary followup (stage automatic draft or send)
        if meeting.summary:
            email_to = settings.gmail_from or "team@myorganization.com"
            app_req_email = ApprovalRequest(
                meeting_id=meeting_id,
                tool_name="send_summary_email",
                payload={
                    "recipients": [email_to],
                    "subject": f"Meeting Summary: {meeting.title}",
                    "body": f"<h3>{meeting.title} Summary</h3><p>{meeting.summary}</p>"
                    f"<h4>Key Decisions:</h4><ul>"
                    + "".join(f"<li>{d}</li>" for d in (meeting.key_decisions or []))
                    + "</ul>",
                },
                status=ApprovalStatus.pending,
            )
            db.add(app_req_email)

        await db.commit()

        # Gather segments mapping for search indexing
        # For simple chunk-based searching, divide transcript into sentence blocks/paragraphs
        paragraphs = [p.strip() for p in meeting.transcript.split("\n\n") if p.strip()]
        segments_for_index = []
        for idx, p in enumerate(paragraphs):
            segments_for_index.append(
                {
                    "id": f"{meeting_id}-seg-{idx}",
                    "text": p,
                }
            )

        # Step 3: Index in Qdrant Hybrid search
        index = get_search_index()
        indexed = await index.index_meeting(
            meeting_id=meeting.id,
            title=meeting.title,
            transcript=meeting.transcript,
            started_at=meeting.started_at,
            segments=segments_for_index,
        )

        # If autopilot is ON, execute approval requests directly
        if settings.autopilot:
            logger.info("Autopilot enabled; auto-executing staged approval actions.")
            await _auto_execute_approvals(meeting_id)

        # Mark meeting as indexed if indexing succeeded
        meeting.indexed = indexed
        await db.commit()

    logger.info("Finished processing pipeline successfully for meeting: {}", meeting_id)


async def _auto_execute_approvals(meeting_id: str) -> None:
    """Helper to auto-trigger pending tools if autopilot is set."""
    async with session_scope() as db:
        res = await db.execute(
            select(ApprovalRequest).where(
                ApprovalRequest.meeting_id == meeting_id,
                ApprovalRequest.status == ApprovalStatus.pending,
            )
        )
        reqs = res.scalars().all()
        for r in reqs:
            r.status = ApprovalStatus.approved
            # execute
            tool_res = await execute_tool(r.tool_name, r.payload)
            if tool_res.success:
                r.status = ApprovalStatus.executed
                r.result = tool_res.to_dict()
            else:
                r.status = ApprovalStatus.failed
                r.error = tool_res.message
        await db.commit()
