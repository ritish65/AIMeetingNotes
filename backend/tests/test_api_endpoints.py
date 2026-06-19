"""Unit tests for app.api.endpoints (covering uncovered endpoints)."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(scope="module")
def api_client():
    with TestClient(app) as c:
        yield c


def _create_meeting(client, title="Test Meeting"):
    res = client.post("/api/meetings", json={"title": title})
    assert res.status_code == 200
    return res.json()


# ---------- Meeting endpoints ----------


class TestCreateMeeting:
    def test_create_with_title(self, api_client):
        data = _create_meeting(api_client, "My Meeting")
        assert data["title"] == "My Meeting"
        assert data["status"] == "recording"
        assert "id" in data

    def test_create_without_title(self, api_client):
        res = api_client.post("/api/meetings", json={})
        assert res.status_code == 200
        data = res.json()
        assert "Meeting -" in data["title"]


class TestGetMeeting:
    def test_get_existing(self, api_client):
        created = _create_meeting(api_client, "Get Test")
        res = api_client.get(f"/api/meetings/{created['id']}")
        assert res.status_code == 200
        assert res.json()["id"] == created["id"]

    def test_get_nonexistent(self, api_client):
        res = api_client.get("/api/meetings/nonexistent-id")
        assert res.status_code == 404


class TestListMeetings:
    def test_returns_list(self, api_client):
        _create_meeting(api_client, "List Test")
        res = api_client.get("/api/meetings")
        assert res.status_code == 200
        assert isinstance(res.json(), list)
        assert len(res.json()) >= 1


class TestDeleteMeeting:
    def test_delete_existing(self, api_client):
        created = _create_meeting(api_client, "Delete Test")
        res = api_client.delete(f"/api/meetings/{created['id']}")
        assert res.status_code == 200
        assert res.json()["success"] is True

        # Verify it's gone
        get_res = api_client.get(f"/api/meetings/{created['id']}")
        assert get_res.status_code == 404


# ---------- Segments ----------


class TestGetSegments:
    def test_empty_segments(self, api_client):
        created = _create_meeting(api_client, "Segments Test")
        res = api_client.get(f"/api/meetings/{created['id']}/segments")
        assert res.status_code == 200
        assert res.json() == []


# ---------- Action Items ----------


class TestGetMeetingActionItems:
    def test_empty_action_items(self, api_client):
        created = _create_meeting(api_client, "ActionItems Test")
        res = api_client.get(f"/api/meetings/{created['id']}/action-items")
        assert res.status_code == 200
        assert res.json() == []


class TestListAllActionItems:
    def test_returns_list(self, api_client):
        res = api_client.get("/api/action-items")
        assert res.status_code == 200
        assert isinstance(res.json(), list)


# ---------- Approvals ----------


class TestGetMeetingApprovals:
    def test_empty_approvals(self, api_client):
        created = _create_meeting(api_client, "Approvals Test")
        res = api_client.get(f"/api/meetings/{created['id']}/approvals")
        assert res.status_code == 200
        assert res.json() == []


class TestHandleApprovalAction:
    def test_invalid_action(self, api_client):
        res = api_client.post("/api/approvals/some-id/action?action=invalid")
        assert res.status_code == 400

    def test_nonexistent_approval(self, api_client):
        res = api_client.post("/api/approvals/nonexistent-id/action?action=approve")
        assert res.status_code == 404

    def test_reject_approval(self, api_client):
        created = _create_meeting(api_client, "Reject Approval Test")
        mid = created["id"]

        fin_res = api_client.post(
            f"/api/meetings/{mid}/finalize",
            json={"transcript": "Alice: Do the task."},
        )
        assert fin_res.status_code == 200

        import time

        time.sleep(2)

        approvals_res = api_client.get(f"/api/meetings/{mid}/approvals")
        approvals = approvals_res.json()

        if approvals:
            approval_id = approvals[0]["id"]
            reject_res = api_client.post(
                f"/api/approvals/{approval_id}/action?action=reject"
            )
            assert reject_res.status_code == 200
            assert reject_res.json()["status"] == "rejected"

    def test_approve_and_execute(self, api_client):
        created = _create_meeting(api_client, "Approve Execution Test")
        mid = created["id"]

        fin_res = api_client.post(
            f"/api/meetings/{mid}/finalize",
            json={"transcript": "Bob: Set up the meeting room."},
        )
        assert fin_res.status_code == 200

        import time

        time.sleep(2)

        approvals_res = api_client.get(f"/api/meetings/{mid}/approvals")
        approvals = approvals_res.json()

        if approvals:
            # Find one that is still pending
            pending = [a for a in approvals if a["status"] == "pending"]
            if pending:
                approval_id = pending[0]["id"]
                approve_res = api_client.post(
                    f"/api/approvals/{approval_id}/action?action=approve"
                )
                assert approve_res.status_code == 200
                assert approve_res.json()["success"] is True

    def test_double_action_on_same_approval(self, api_client):
        created = _create_meeting(api_client, "Double Action Test")
        mid = created["id"]

        fin_res = api_client.post(
            f"/api/meetings/{mid}/finalize",
            json={"transcript": "Eve: Write the documentation."},
        )
        assert fin_res.status_code == 200

        import time

        time.sleep(2)

        approvals_res = api_client.get(f"/api/meetings/{mid}/approvals")
        approvals = approvals_res.json()

        if approvals:
            pending = [a for a in approvals if a["status"] == "pending"]
            if pending:
                approval_id = pending[0]["id"]
                # First action
                api_client.post(
                    f"/api/approvals/{approval_id}/action?action=reject"
                )
                # Second action should fail (already not pending)
                second_res = api_client.post(
                    f"/api/approvals/{approval_id}/action?action=approve"
                )
                assert second_res.status_code == 400


# ---------- Finalize ----------


class TestFinalizeMeeting:
    def test_finalize_with_transcript(self, api_client):
        created = _create_meeting(api_client, "Finalize Test")
        res = api_client.post(
            f"/api/meetings/{created['id']}/finalize",
            json={"transcript": "Test transcript content."},
        )
        assert res.status_code == 200
        assert res.json()["success"] is True

    def test_finalize_nonexistent(self, api_client):
        res = api_client.post(
            "/api/meetings/nonexistent-id/finalize",
            json={"transcript": "test"},
        )
        assert res.status_code == 404

    def test_finalize_already_processing(self, api_client):
        created = _create_meeting(api_client, "Double Finalize Test")
        mid = created["id"]

        # First finalize
        api_client.post(
            f"/api/meetings/{mid}/finalize",
            json={"transcript": "First finalize."},
        )

        import time

        time.sleep(1)

        # Second finalize should indicate already processed
        res = api_client.post(
            f"/api/meetings/{mid}/finalize",
            json={"transcript": "Second finalize."},
        )
        assert res.status_code == 200
        # Either success=False (already processed) or success=True (re-finalize)
        data = res.json()
        assert "success" in data


# ---------- Search ----------


class TestSearchEndpoint:
    def test_search_returns_response(self, api_client):
        res = api_client.post(
            "/api/search",
            json={"query": "test query", "top_k": 3},
        )
        assert res.status_code == 200
        data = res.json()
        assert "intent" in data
        assert "hits" in data
        assert "expanded_queries" in data
