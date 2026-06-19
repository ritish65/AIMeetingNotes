"""Unit tests for app.llm."""
from __future__ import annotations

import json

import pytest
from langchain_core.messages import HumanMessage

from app.llm import StubChatModel, get_llm


class TestStubChatModel:
    def setup_method(self):
        self.model = StubChatModel()

    def test_llm_type(self):
        assert self.model._llm_type == "stub"

    def test_plain_text_response(self):
        result = self.model._generate([HumanMessage(content="Hello")])
        assert result.generations[0].message.content == "Stub response."

    def test_action_item_json(self):
        msg = HumanMessage(content="Return JSON with ActionItem schema")
        result = self.model._generate([msg])
        data = json.loads(result.generations[0].message.content)
        assert "action_items" in data
        assert len(data["action_items"]) == 1
        assert "description" in data["action_items"][0]

    def test_summary_json(self):
        msg = HumanMessage(content="Return JSON with MeetingSummary schema")
        result = self.model._generate([msg])
        data = json.loads(result.generations[0].message.content)
        assert "title" in data
        assert "next_steps" in data

    def test_intent_json(self):
        msg = HumanMessage(content="Classify intent in JSON format")
        result = self.model._generate([msg])
        data = json.loads(result.generations[0].message.content)
        assert data["intent"] == "search"

    def test_query_expansion_json(self):
        msg = HumanMessage(content='Expand this JSON: "budget review" into queries')
        result = self.model._generate([msg])
        data = json.loads(result.generations[0].message.content)
        assert "queries" in data
        assert len(data["queries"]) == 3

    def test_generic_json(self):
        msg = HumanMessage(content="Give me some JSON data")
        result = self.model._generate([msg])
        assert result.generations[0].message.content == "{}"

    def test_empty_messages(self):
        result = self.model._generate([])
        assert result.generations[0].message.content == "Stub response."

    @pytest.mark.asyncio
    async def test_agenerate(self):
        result = await self.model._agenerate([HumanMessage(content="Hi")])
        assert result.generations[0].message.content == "Stub response."

    def test_non_string_content(self):
        msg = HumanMessage(content=[{"type": "text", "text": "JSON data"}])
        result = self.model._generate([msg])
        content = result.generations[0].message.content
        assert isinstance(content, str)


class TestGetLlm:
    def test_stub_provider(self, monkeypatch):
        monkeypatch.setattr("app.llm.settings.llm_provider", "stub")
        llm = get_llm()
        assert isinstance(llm, StubChatModel)

    def test_no_credentials_falls_to_stub(self, monkeypatch):
        monkeypatch.setattr("app.llm.settings.llm_provider", "openai")
        monkeypatch.setattr("app.llm.settings.openai_api_key", None)
        llm = get_llm()
        assert isinstance(llm, StubChatModel)

    def test_anthropic_no_key_falls_to_stub(self, monkeypatch):
        monkeypatch.setattr("app.llm.settings.llm_provider", "anthropic")
        monkeypatch.setattr("app.llm.settings.anthropic_api_key", None)
        llm = get_llm()
        assert isinstance(llm, StubChatModel)

    def test_groq_no_key_falls_to_stub(self, monkeypatch):
        monkeypatch.setattr("app.llm.settings.llm_provider", "groq")
        monkeypatch.setattr("app.llm.settings.groq_api_key", None)
        llm = get_llm()
        assert isinstance(llm, StubChatModel)

    def test_custom_temperature(self, monkeypatch):
        monkeypatch.setattr("app.llm.settings.llm_provider", "stub")
        llm = get_llm(temperature=0.8)
        assert isinstance(llm, StubChatModel)
