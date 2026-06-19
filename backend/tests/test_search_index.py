"""Unit tests for app.search.index (fallback / in-memory mode)."""
from __future__ import annotations

import pytest

from app.schemas import SearchRequest
from app.search.index import HybridSearchIndex, get_search_index


@pytest.fixture
def idx() -> HybridSearchIndex:
    """Fresh in-memory search index (no Qdrant)."""
    index = HybridSearchIndex()
    index.use_fallback = True
    index.local_docs = []
    return index


# ---------- Indexing ----------


@pytest.mark.asyncio
class TestIndexMeeting:
    async def test_index_empty_transcript(self, idx):
        ok = await idx.index_meeting(
            meeting_id="m1",
            title="Empty",
            transcript="",
            started_at=__import__("datetime").datetime.now(),
            segments=[],
        )
        assert ok is False

    async def test_index_valid_meeting(self, idx):
        from datetime import datetime

        ok = await idx.index_meeting(
            meeting_id="m1",
            title="Standup",
            transcript="Alice discussed Q3 planning.",
            started_at=datetime(2026, 6, 19),
            segments=[
                {"id": "s1", "text": "Alice discussed Q3 planning."},
                {"id": "s2", "text": "Bob mentioned budget review."},
            ],
        )
        assert ok is True
        assert len(idx.local_docs) == 2

    async def test_no_duplicate_indexing(self, idx):
        from datetime import datetime

        segs = [{"id": "s1", "text": "Some text."}]
        await idx.index_meeting("m1", "T", "Some text.", datetime(2026, 1, 1), segs)
        await idx.index_meeting("m1", "T", "Some text.", datetime(2026, 1, 1), segs)
        assert len(idx.local_docs) == 1


# ---------- Invalidation ----------


@pytest.mark.asyncio
class TestInvalidateMeeting:
    async def test_removes_docs(self, idx):
        from datetime import datetime

        await idx.index_meeting(
            "m1", "T", "text", datetime(2026, 1, 1), [{"id": "s1", "text": "text"}]
        )
        assert len(idx.local_docs) == 1
        await idx.invalidate_meeting("m1")
        assert len(idx.local_docs) == 0

    async def test_no_error_on_missing_meeting(self, idx):
        await idx.invalidate_meeting("nonexistent")
        assert len(idx.local_docs) == 0


# ---------- Intent routing ----------


@pytest.mark.asyncio
class TestRouteIntent:
    async def test_returns_intent(self, idx):
        intent = await idx.route_intent("Who attended the last meeting?")
        assert intent.intent in ("search", "action", "summary", "qa")
        assert 0.0 <= intent.confidence <= 1.0


# ---------- Query amplification ----------


@pytest.mark.asyncio
class TestAmplifyQuery:
    async def test_returns_original_query_first(self, idx):
        queries = await idx.amplify_query("budget review")
        assert queries[0] == "budget review"
        assert len(queries) >= 1

    async def test_max_four_queries(self, idx):
        queries = await idx.amplify_query("test query")
        assert len(queries) <= 4


# ---------- Search ----------


@pytest.mark.asyncio
class TestSearch:
    async def test_empty_index_returns_no_hits(self, idx):
        req = SearchRequest(query="anything", top_k=5)
        resp = await idx.search(req)
        assert resp.hits == []
        assert resp.intent is not None

    async def test_search_finds_matching_docs(self, idx):
        from datetime import datetime

        await idx.index_meeting(
            "m1",
            "Planning",
            "Alice discussed Q3 planning.",
            datetime(2026, 6, 19),
            [{"id": "s1", "text": "Alice discussed Q3 planning."}],
        )
        await idx.index_meeting(
            "m2",
            "Budget",
            "Bob talked about the budget.",
            datetime(2026, 6, 18),
            [{"id": "s2", "text": "Bob talked about the budget."}],
        )

        req = SearchRequest(query="planning", top_k=5, multi_query=False)
        resp = await idx.search(req)
        assert len(resp.hits) >= 1
        assert any("planning" in h.text.lower() for h in resp.hits)

    async def test_search_top_k_limit(self, idx):
        from datetime import datetime

        for i in range(10):
            await idx.index_meeting(
                f"m{i}",
                f"Meeting {i}",
                f"Topic {i} discussion.",
                datetime(2026, 6, 1),
                [{"id": f"s{i}", "text": f"Topic {i} discussion."}],
            )
        req = SearchRequest(query="discussion", top_k=3, multi_query=False)
        resp = await idx.search(req)
        assert len(resp.hits) <= 3

    async def test_search_with_multi_query(self, idx):
        from datetime import datetime

        await idx.index_meeting(
            "m1",
            "Planning",
            "Alice discussed Q3 planning.",
            datetime(2026, 6, 19),
            [{"id": "s1", "text": "Alice discussed Q3 planning."}],
        )
        req = SearchRequest(query="planning", top_k=5, multi_query=True)
        resp = await idx.search(req)
        assert resp.expanded_queries is not None
        assert len(resp.expanded_queries) >= 1


# ---------- Singleton ----------


class TestGetSearchIndex:
    def test_returns_instance(self):
        idx = get_search_index()
        assert isinstance(idx, HybridSearchIndex)
