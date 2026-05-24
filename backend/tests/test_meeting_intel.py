"""Smoke and Integration tests for Meeting Intelligence Agent."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def test_health_check(client) -> None:
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json() == {"status": "healthy", "service": "pmia-backend"}


def test_meeting_crud_and_flows(client) -> None:
    # 1. Create a meeting
    res = client.post("/api/meetings", json={"title": "Team Engineering Sync"})
    assert res.status_code == 200
    data = res.json()
    meeting_id = data["id"]
    assert data["title"] == "Team Engineering Sync"
    assert data["status"] == "recording"

    # 2. Query meeting list
    list_res = client.get("/api/meetings")
    assert list_res.status_code == 200
    meetings = list_res.json()
    assert len(meetings) >= 1
    assert any(m["id"] == meeting_id for m in meetings)

    # 3. Finalize the meeting
    fin_res = client.post(
        f"/api/meetings/{meeting_id}/finalize",
        json={"transcript": "Sarah: Complete work on Q3 planning. John: Set up the GCP bucket."},
    )
    assert fin_res.status_code == 200
    assert fin_res.json()["success"] is True

    # 4. Search endpoint smoke verification
    search_res = client.post(
        "/api/search",
        json={"query": "Who is working on planning?", "top_k": 3},
    )
    assert search_res.status_code == 200
    s_data = search_res.json()
    assert "intent" in s_data
    assert "hits" in s_data

