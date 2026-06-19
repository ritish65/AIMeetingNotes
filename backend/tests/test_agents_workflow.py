"""Unit tests for app.agents.workflow."""
from __future__ import annotations

import pytest

from app.agents.workflow import (
    AgentState,
    _parse_json_from_llm,
    action_item_agent,
    build_meeting_workflow,
    context_retrieval_agent,
    get_meeting_workflow,
    participant_agent,
    summarizer_agent,
    transcription_segmentation_agent,
)


# ---------- _parse_json_from_llm ----------


class TestParseJsonFromLlm:
    def test_plain_json(self):
        assert _parse_json_from_llm('{"key": "value"}') == {"key": "value"}

    def test_json_with_markdown_fences(self):
        text = '```json\n{"key": "value"}\n```'
        assert _parse_json_from_llm(text) == {"key": "value"}

    def test_json_with_bare_fences(self):
        text = '```\n{"key": 42}\n```'
        assert _parse_json_from_llm(text) == {"key": 42}

    def test_json_embedded_in_text(self):
        text = 'Here is the result: {"items": [1, 2, 3]} and that is all.'
        result = _parse_json_from_llm(text)
        assert result == {"items": [1, 2, 3]}

    def test_invalid_json_returns_empty(self):
        assert _parse_json_from_llm("not json at all") == {}

    def test_empty_string(self):
        assert _parse_json_from_llm("") == {}

    def test_nested_json(self):
        text = '{"outer": {"inner": [1, 2]}}'
        assert _parse_json_from_llm(text) == {"outer": {"inner": [1, 2]}}


# ---------- Agent nodes (using stub LLM) ----------


def _make_state(**overrides) -> AgentState:
    base: AgentState = {
        "meeting_id": "test-123",
        "raw_transcript": "",
        "formatted_transcript": "",
        "action_items": [],
        "summary": "",
        "key_decisions": [],
        "next_steps": [],
        "participants": [],
        "related_meetings": [],
        "errors": [],
    }
    base.update(overrides)
    return base


@pytest.mark.asyncio
class TestTranscriptionAgent:
    async def test_empty_transcript(self):
        state = _make_state(raw_transcript="")
        result = await transcription_segmentation_agent(state)
        assert result["formatted_transcript"] == "Empty meeting transcript."

    async def test_non_empty_transcript(self):
        state = _make_state(raw_transcript="Alice: Hello everyone.")
        result = await transcription_segmentation_agent(state)
        assert "formatted_transcript" in result
        assert len(result["formatted_transcript"]) > 0


@pytest.mark.asyncio
class TestActionItemAgent:
    async def test_empty_transcript(self):
        state = _make_state(formatted_transcript="")
        result = await action_item_agent(state)
        assert result["action_items"] == []

    async def test_with_transcript(self):
        state = _make_state(
            formatted_transcript="Alice: We need to finish the Q3 report by Friday."
        )
        result = await action_item_agent(state)
        assert "action_items" in result


@pytest.mark.asyncio
class TestSummarizerAgent:
    async def test_empty_transcript(self):
        state = _make_state(formatted_transcript="")
        result = await summarizer_agent(state)
        assert result["summary"] == "No summary available."
        assert result["key_decisions"] == []
        assert result["next_steps"] == []

    async def test_with_transcript(self):
        state = _make_state(
            formatted_transcript="Bob: We decided to migrate to Kubernetes."
        )
        result = await summarizer_agent(state)
        assert "summary" in result


@pytest.mark.asyncio
class TestParticipantAgent:
    async def test_empty_transcript(self):
        state = _make_state(formatted_transcript="")
        result = await participant_agent(state)
        assert result["participants"] == []

    async def test_with_transcript(self):
        state = _make_state(
            formatted_transcript="Alice: Hello. Bob: Hi everyone."
        )
        result = await participant_agent(state)
        assert "participants" in result


@pytest.mark.asyncio
class TestContextRetrievalAgent:
    async def test_returns_empty(self):
        state = _make_state()
        result = await context_retrieval_agent(state)
        assert result == {"related_meetings": []}


# ---------- Workflow builder ----------


class TestBuildWorkflow:
    def test_compiles_without_error(self):
        wf = build_meeting_workflow()
        assert wf is not None

    def test_get_meeting_workflow_singleton(self):
        wf1 = get_meeting_workflow()
        wf2 = get_meeting_workflow()
        assert wf1 is wf2
