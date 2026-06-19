"""Unit tests for app.tools.registry."""
from __future__ import annotations

import pytest

from app.tools.registry import (
    ToolResponse,
    add_to_todoist,
    execute_tool,
    get_tool_map,
    schedule_followup,
    send_summary_email,
    store_recording_filesystem,
)


# ---------- ToolResponse ----------


class TestToolResponse:
    def test_success_response(self):
        r = ToolResponse(success=True, message="ok")
        assert r.success is True
        assert r.message == "ok"
        assert r.data == {}

    def test_failure_response_with_data(self):
        r = ToolResponse(success=False, message="fail", data={"key": "val"})
        assert r.success is False
        assert r.data == {"key": "val"}

    def test_to_dict(self):
        r = ToolResponse(success=True, message="done", data={"id": 1})
        d = r.to_dict()
        assert d == {"success": True, "message": "done", "data": {"id": 1}}

    def test_to_dict_default_data(self):
        r = ToolResponse(success=True, message="ok")
        d = r.to_dict()
        assert d["data"] == {}


# ---------- Tool functions (mock mode, no tokens configured) ----------


class TestAddToTodoist:
    def test_mock_mode_returns_success(self):
        res = add_to_todoist("Write tests", due_date="tomorrow", priority="high")
        assert res.success is True
        assert "Mock Mode" in res.message
        assert res.data["task"] == "Write tests"
        assert res.data["due_date"] == "tomorrow"
        assert res.data["priority"] == "high"
        assert res.data["id"] == "mock-todoist-id-123"

    def test_default_priority(self):
        res = add_to_todoist("Simple task")
        assert res.success is True
        assert res.data["priority"] == "medium"

    def test_no_due_date(self):
        res = add_to_todoist("No deadline task")
        assert res.success is True
        assert res.data["due_date"] is None


class TestSendSummaryEmail:
    def test_mock_mode_with_list(self):
        res = send_summary_email(
            recipients=["a@b.com", "c@d.com"],
            subject="Meeting Summary",
            body="Some body text",
        )
        assert res.success is True
        assert "Mock Mode" in res.message
        assert res.data["recipients"] == ["a@b.com", "c@d.com"]
        assert res.data["subject"] == "Meeting Summary"

    def test_mock_mode_with_string_recipients(self):
        res = send_summary_email(
            recipients="a@b.com, c@d.com",
            subject="Test",
            body="body",
        )
        assert res.success is True
        assert res.data["recipients"] == ["a@b.com", "c@d.com"]

    def test_mock_mode_empty_string_recipients(self):
        res = send_summary_email(recipients="", subject="Test", body="body")
        assert res.success is True


class TestScheduleFollowup:
    def test_mock_mode(self):
        res = schedule_followup(
            title="Standup",
            start_time="2026-06-20T10:00:00",
            duration_minutes=15,
        )
        assert res.success is True
        assert "Mock Mode" in res.message
        assert res.data["title"] == "Standup"
        assert res.data["duration"] == 15

    def test_default_duration(self):
        res = schedule_followup(title="Sync", start_time="2026-06-20T10:00:00")
        assert res.success is True
        assert res.data["duration"] == 30


class TestStoreRecordingFilesystem:
    def test_stores_file(self, tmp_path, monkeypatch):
        monkeypatch.setattr("app.tools.registry.settings.data_dir", str(tmp_path))
        # Force data_path to recreate dirs under tmp_path
        audio_dir = tmp_path / "audio"
        audio_dir.mkdir(parents=True, exist_ok=True)

        res = store_recording_filesystem("m-123", "rec.wav", b"\x00\x01\x02")
        assert res.success is True
        assert res.data["file_size"] == 3
        assert "m-123_rec.wav" in res.data["file_path"]


# ---------- Tool map and executor ----------


class TestGetToolMap:
    def test_contains_expected_tools(self):
        m = get_tool_map()
        assert "add_to_todoist" in m
        assert "send_summary_email" in m
        assert "schedule_followup" in m
        assert callable(m["add_to_todoist"])


@pytest.mark.asyncio
class TestExecuteTool:
    async def test_unknown_tool(self):
        res = await execute_tool("nonexistent_tool", {})
        assert res.success is False
        assert "not found" in res.message

    async def test_execute_todoist_mock(self):
        res = await execute_tool("add_to_todoist", {"task": "Test task"})
        assert res.success is True

    async def test_execute_email_mock(self):
        res = await execute_tool(
            "send_summary_email",
            {"recipients": ["test@test.com"], "subject": "Hi", "body": "Content"},
        )
        assert res.success is True

    async def test_execute_followup_mock(self):
        res = await execute_tool(
            "schedule_followup",
            {"title": "Test", "start_time": "2026-06-20T10:00:00"},
        )
        assert res.success is True

    async def test_bad_payload_returns_failure(self):
        # Missing required params
        res = await execute_tool("add_to_todoist", {})
        assert res.success is False
        assert "exception" in res.message.lower() or "failed" in res.message.lower()
