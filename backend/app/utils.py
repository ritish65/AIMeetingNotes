"""Shared utilities for the PMIA backend.

Consolidates common patterns used across agents, search, API endpoints,
and tool integrations to reduce code duplication.
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

from langchain_core.messages import SystemMessage
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .config import settings
from .llm import get_llm


# ---------- JSON Parsing ----------


def parse_json_from_llm(content: str) -> Dict[str, Any]:
    """Safely extract and parse JSON from LLM responses (handles markdown wrappers)."""
    cleaned = content.strip()
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        cleaned = "\n".join(lines).strip()
    try:
        return json.loads(cleaned)
    except Exception:
        m = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0))
            except Exception:
                pass
        return {}


# ---------- LLM Invocation ----------


async def invoke_llm_json(prompt: str, temperature: float = 0.2) -> Dict[str, Any]:
    """Invoke the configured LLM with a system prompt and parse JSON from the response.

    Returns a parsed dict on success, or an empty dict on failure.
    """
    llm = get_llm(temperature=temperature)
    res = await llm.ainvoke([SystemMessage(content=prompt)])
    return parse_json_from_llm(str(res.content))


# ---------- Database Helpers ----------


async def fetch_meeting(
    db: AsyncSession, meeting_id: str
) -> Optional[Any]:
    """Look up a Meeting by ID. Returns None if not found."""
    from .models import Meeting

    res = await db.execute(select(Meeting).where(Meeting.id == meeting_id))
    return res.scalar_one_or_none()


# ---------- Transcript Segment Creation ----------


async def create_transcript_segment(
    db: AsyncSession,
    meeting_id: str,
    text: str,
    start_ms: int,
    end_ms: int,
    speaker: str = "Speaker 1",
    is_final: bool = True,
) -> Any:
    """Create and persist a TranscriptSegment record."""
    from .models import TranscriptSegment

    segment = TranscriptSegment(
        meeting_id=meeting_id,
        speaker=speaker,
        start_ms=start_ms,
        end_ms=end_ms,
        text=text,
        is_final=is_final,
    )
    db.add(segment)
    await db.commit()
    return segment


# ---------- Google OAuth Helpers ----------


def build_google_credentials(
    service_name: str,
) -> Optional[Any]:
    """Build Google OAuth2 credentials for the specified service.

    Args:
        service_name: One of 'gmail' or 'gcal'.

    Returns:
        A google.oauth2.credentials.Credentials instance, or None if not configured.
    """
    if service_name == "gmail":
        refresh_token = settings.gmail_refresh_token
        client_id = settings.gmail_client_id
        client_secret = settings.gmail_client_secret
    elif service_name == "gcal":
        refresh_token = settings.gcal_refresh_token
        client_id = settings.gcal_client_id
        client_secret = settings.gcal_client_secret
    else:
        logger.warning("Unknown Google service: {}", service_name)
        return None

    if not refresh_token:
        return None

    from google.oauth2.credentials import Credentials

    return Credentials(
        token=None,
        refresh_token=refresh_token,
        client_id=client_id,
        client_secret=client_secret,
        token_uri="https://oauth2.googleapis.com/token",
    )


def build_google_service(service_name: str) -> Optional[Any]:
    """Build and return a Google API service client.

    Args:
        service_name: One of 'gmail' or 'gcal'.

    Returns:
        A googleapiclient Resource object, or None if credentials are missing.
    """
    creds = build_google_credentials(service_name)
    if creds is None:
        return None

    from googleapiclient.discovery import build

    service_map = {
        "gmail": ("gmail", "v1"),
        "gcal": ("calendar", "v3"),
    }
    api_name, version = service_map[service_name]
    return build(api_name, version, credentials=creds)
