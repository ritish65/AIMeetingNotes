"""MCP tool integrations.

Implements concrete tooling for Todoist, Gmail, Google Calendar, and the Local 
Filesystem. Provides clean stubs when integrations are not configured.
"""
from __future__ import annotations

import inspect
from datetime import datetime
from typing import Any, Dict, List, Optional

from loguru import logger

from ..config import settings
from ..utils import build_google_service


class ToolResponse:
    def __init__(self, success: bool, message: str, data: Optional[Dict[str, Any]] = None) -> None:
        self.success = success
        self.message = message
        self.data = data or {}

    def to_dict(self) -> Dict[str, Any]:
        return {"success": self.success, "message": self.message, "data": self.data}


# ---------- Pluggable Tools Implementation ----------


def add_to_todoist(task: str, due_date: Optional[str] = None, priority: str = "medium") -> ToolResponse:
    """Add a meeting action item to Todoist.

    Args:
        task: Description of the action item.
        due_date: Due date or deadline (e.g., 'tomorrow', '2026-05-25').
        priority: Task priority (high, medium, low).
    """
    if not settings.todoist_token:
        logger.info("[MOCK TODOIST] Created task: '{}' (due: {}, priority: {})", task, due_date, priority)
        return ToolResponse(
            success=True,
            message="[Mock Mode] Action item added to Todoist successfully.",
            data={"task": task, "due_date": due_date, "priority": priority, "id": "mock-todoist-id-123"},
        )

    try:
        from todoist_api_python.api import TodoistAPI

        # Map meeting priority to Todoist priorities (1-4, 4 is highest)
        p_map = {"high": 4, "medium": 3, "low": 1}
        p_val = p_map.get(priority.lower(), 1)

        api = TodoistAPI(settings.todoist_token)
        todo_args = {"content": task, "priority": p_val}
        if due_date:
            todo_args["due_string"] = due_date

        res = api.add_task(**todo_args)
        return ToolResponse(
            success=True,
            message=f"Action item '{task}' successfully added to Todoist.",
            data={"task_id": res.id, "url": res.url},
        )
    except Exception as e:
        logger.error("Todoist api error: {}", e)
        return ToolResponse(success=False, message=f"Todoist tool failed: {e}")


def send_summary_email(recipients: List[str], subject: str, body: str) -> ToolResponse:
    """Send meeting summary via email (Gmail).

    Args:
        recipients: List of recipient email addresses.
        subject: Email subject.
        body: HTML or plain text email body.
    """
    # Clean up input if string was supplied
    if isinstance(recipients, str):
        recipients = [r.strip() for r in recipients.split(",") if r.strip()]

    if not settings.gmail_refresh_token:
        logger.info("[MOCK GMAIL] Sent summary to: {} (subject: '{}')", recipients, subject)
        return ToolResponse(
            success=True,
            message=f"[Mock Mode] Email sent successfully to {', '.join(recipients)}.",
            data={"recipients": recipients, "subject": subject},
        )

    try:
        import base64
        from email.mime.text import MIMEText

        service = build_google_service("gmail")

        mime = MIMEText(body, "html" if "<html" in body.lower() else "plain")
        mime["to"] = ", ".join(recipients)
        mime["subject"] = subject
        if settings.gmail_from:
            mime["from"] = settings.gmail_from

        raw = base64.urlsafe_b64encode(mime.as_bytes()).decode()
        res = service.users().messages().send(userId="me", body={"raw": raw}).execute()

        return ToolResponse(
            success=True,
            message=f"Summary email successfully sent to {len(recipients)} recipients.",
            data={"message_id": res.get("id")},
        )
    except Exception as e:
        logger.error("Gmail tool error: {}", e)
        return ToolResponse(success=False, message=f"Gmail tool failed: {e}")


def schedule_followup(title: str, start_time: str, duration_minutes: int = 30) -> ToolResponse:
    """Schedule follow-up meeting in Google Calendar.

    Args:
        title: Title of the meeting.
        start_time: ISO timestamp format for start time (e.g., '2026-05-23T10:00:00').
        duration_minutes: Meeting duration in minutes.
    """
    if not settings.gcal_refresh_token:
        logger.info("[MOCK GCAL] Scheduled follow-up: '{}' (start: {}, duration: {}m)", title, start_time, duration_minutes)
        return ToolResponse(
            success=True,
            message=f"[Mock Mode] Scheduled follow-up '{title}' successfully.",
            data={"title": title, "start_time": start_time, "duration": duration_minutes},
        )

    try:
        from datetime import timedelta

        service = build_google_service("gcal")

        dt_start = datetime.fromisoformat(start_time)
        dt_end = dt_start + timedelta(minutes=duration_minutes)

        event = {
            "summary": title,
            "description": "Auto-scheduled meeting via Personal Meeting Assistant.",
            "start": {"dateTime": dt_start.isoformat(), "timeZone": "UTC"},
            "end": {"dateTime": dt_end.isoformat(), "timeZone": "UTC"},
        }

        res = (
            service.events()
            .insert(calendarId=settings.gcal_calendar_id, body=event)
            .execute()
        )
        return ToolResponse(
            success=True,
            message=f"Follow-up meeting '{title}' scheduled successfully.",
            data={"event_id": res.get("id"), "html_link": res.get("htmlLink")},
        )
    except Exception as e:
        logger.error("GCal tool error: {}", e)
        return ToolResponse(success=False, message=f"Google Calendar tool failed: {e}")


def store_recording_filesystem(meeting_id: str, file_name: str, file_bytes: bytes) -> ToolResponse:
    """Store raw meeting recording in the system workspace folder."""
    try:
        audio_dir = settings.data_path / "audio"
        p = audio_dir / f"{meeting_id}_{file_name}"
        p.write_bytes(file_bytes)
        return ToolResponse(
            success=True,
            message=f"Meeting recording stored locally at {p.name}.",
            data={"file_path": str(p), "file_size": len(file_bytes)},
        )
    except Exception as e:
        logger.error("Filesystem write error: {}", e)
        return ToolResponse(success=False, message=f"Filesystem storage tool failed: {e}")


# ---------- Unified Tool Executor ----------


def get_tool_map() -> Dict[str, Any]:
    return {
        "add_to_todoist": add_to_todoist,
        "send_summary_email": send_summary_email,
        "schedule_followup": schedule_followup,
    }


async def execute_tool(tool_name: str, payload: Dict[str, Any]) -> ToolResponse:
    t_map = get_tool_map()
    if tool_name not in t_map:
        return ToolResponse(success=False, message=f"Tool '{tool_name}' not found in registry.")

    try:
        fn = t_map[tool_name]
        # Resolve async/sync wrapper
        if inspect.iscoroutinefunction(fn):
            return await fn(**payload)
        return fn(**payload)
    except Exception as e:
        logger.error("Execution error on tool {}: {}", tool_name, e)
        return ToolResponse(success=False, message=f"Tool execution failed with exception: {e}")
