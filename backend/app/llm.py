"""Provider-agnostic LLM accessor with stub fallback.

Returns a `langchain_core` chat model so it can be reused by every agent.
Falls back to a deterministic stub model when no API key is configured so
the system runs end-to-end offline.
"""
from __future__ import annotations

import json
import re
from typing import Any, List

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from loguru import logger

from .config import settings


class StubChatModel(BaseChatModel):
    """A tiny deterministic chat model used when no LLM credentials exist."""

    def _generate(
        self,
        messages: List[BaseMessage],
        stop: List[str] | None = None,
        run_manager: Any | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        text = self._fake_response(messages)
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=text))])

    async def _agenerate(
        self,
        messages: List[BaseMessage],
        stop: List[str] | None = None,
        run_manager: Any | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        return self._generate(messages, stop, run_manager, **kwargs)

    @property
    def _llm_type(self) -> str:
        return "stub"

    @staticmethod
    def _fake_response(messages: List[BaseMessage]) -> str:
        last = messages[-1].content if messages else ""
        text = last if isinstance(last, str) else json.dumps(last)
        if "JSON" in text or "json" in text:
            # Try to detect what schema was asked for; return a minimal valid one.
            if "ActionItem" in text or "action_items" in text:
                return json.dumps(
                    {
                        "action_items": [
                            {
                                "description": "Follow up on discussion points",
                                "assignee": None,
                                "due_date": None,
                                "priority": "medium",
                                "category": "general",
                            }
                        ]
                    }
                )
            if "MeetingSummary" in text or "summary" in text.lower():
                return json.dumps(
                    {
                        "title": "Meeting Summary",
                        "participants": [],
                        "key_decisions": [],
                        "action_items": [],
                        "next_steps": ["Review transcript"],
                        "duration_minutes": 0,
                    }
                )
            if "intent" in text.lower():
                return json.dumps(
                    {"intent": "search", "confidence": 0.6, "rationale": "stub"}
                )
            if "expand" in text.lower() or "queries" in text.lower():
                # extract last quoted phrase
                m = re.findall(r'"([^"]+)"', text)
                base = m[-1] if m else "topic"
                return json.dumps(
                    {"queries": [base, f"{base} discussion", f"about {base}"]}
                )
            return "{}"
        return "Stub response."


def get_llm(temperature: float = 0.2) -> BaseChatModel:
    provider = (settings.llm_provider or "stub").lower()
    try:
        if provider == "openai" and settings.openai_api_key:
            from langchain_openai import ChatOpenAI

            return ChatOpenAI(
                api_key=settings.openai_api_key,
                model=settings.openai_model,
                temperature=temperature,
            )
        if provider == "anthropic" and settings.anthropic_api_key:
            from langchain_anthropic import ChatAnthropic

            return ChatAnthropic(
                api_key=settings.anthropic_api_key,
                model=settings.anthropic_model,
                temperature=temperature,
            )
        if provider == "groq" and settings.groq_api_key:
            # Groq exposes an OpenAI-compatible API; reuse ChatOpenAI with base_url
            from langchain_openai import ChatOpenAI

            return ChatOpenAI(
                api_key=settings.groq_api_key,
                base_url=settings.groq_base_url,
                model=settings.groq_model,
                temperature=temperature,
            )
    except Exception as e:  # pragma: no cover
        logger.warning("LLM init failed, falling back to stub: {}", e)
    if provider not in ("stub",):
        logger.info("No LLM credentials for provider '{}', using stub.", provider)
    return StubChatModel()
