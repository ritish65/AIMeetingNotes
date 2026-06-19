"""LangGraph multi-agent meeting analysis workflow.

Uses a 5-node agent topology:
- Agent 1: Transcription & Segmentation (formats transcript cleanly)
- Agent 2: Action Item Extraction (extracts action items matching Pydantic schema)
- Agent 3: Summary Node (summarizes core arguments, structure and key points)
- Agent 4: Participant Analyzer (identifies speaker roster + speaker metrics)
- Agent 5: Context Retriever (queries past meetings to link related context)
"""
from __future__ import annotations

from typing import Any, Dict, List, TypedDict

from langchain_core.messages import SystemMessage
from langgraph.graph import StateGraph, END
from loguru import logger

from ..llm import get_llm
from ..utils import invoke_llm_json, parse_json_from_llm


class AgentState(TypedDict):
    meeting_id: str
    raw_transcript: str
    formatted_transcript: str
    action_items: List[Dict[str, Any]]
    summary: str
    key_decisions: List[str]
    next_steps: List[str]
    participants: List[str]
    related_meetings: List[str]
    errors: List[str]


# ---------- Nodes / Agents ----------


async def transcription_segmentation_agent(state: AgentState) -> Dict[str, Any]:
    """Agent 1: Clean and format the raw transcript into standard structure."""
    raw = state.get("raw_transcript", "")
    if not raw.strip():
        return {"formatted_transcript": "Empty meeting transcript."}

    llm = get_llm()
    prompt = (
        "You are an expert transcriber. Take this rough meeting transcript (which might contain "
        "timestamp headers or raw unstructured fragments) and format it into a clean, highly readable, "
        "and properly structured meeting transcript. Retain all original semantics, details, "
        "speaker tags (if present), and direct statements. Do not summarize yet.\n\n"
        f"Raw Transcript:\n{raw}"
    )
    try:
        res = await llm.ainvoke([SystemMessage(content=prompt)])
        return {"formatted_transcript": str(res.content).strip()}
    except Exception as e:
        return {"errors": [f"Transcription node error: {e}"], "formatted_transcript": raw}



async def action_item_agent(state: AgentState) -> Dict[str, Any]:
    """Agent 2: Extract key action items matching type-safe Pydantic schema."""
    transcript = state.get("formatted_transcript", "")
    if not transcript:
        return {"action_items": []}

    prompt = (
        "You are an expert Project Manager. Analyze the meeting transcript below and extract a list "
        "of all action items, deliverables, and tasks explicitly or implicitly assigned. "
        "For each action item, identify the task description, target assignee (if identifiable), "
        "any specified or suggested due dates (in ISO format), priority (high, medium, low), and category.\n\n"
        "Return your analysis strictly in valid JSON format matching this Pydantic schema:\n"
        "{\n"
        '  "action_items": [\n'
        '    {"description": string, "assignee": string or null, "due_date": string or null, "priority": "high"|"medium"|"low", "category": string}\n'
        "  ]\n"
        "}\n\n"
        f"Transcript:\n{transcript}"
    )
    try:
        data = await invoke_llm_json(prompt)
        items = data.get("action_items", [])
        return {"action_items": items}
    except Exception as e:
        return {"errors": [f"Action item node error: {e}"], "action_items": []}


async def summarizer_agent(state: AgentState) -> Dict[str, Any]:
    """Agent 3: Synthesize meeting into a comprehensive high-level summary."""
    transcript = state.get("formatted_transcript", "")
    if not transcript:
        return {"summary": "No summary available.", "key_decisions": [], "next_steps": []}

    prompt = (
        "You are an executive assistant. Synthesize the meeting transcript below into a professional, "
        "concise, yet comprehensive meeting record.\n"
        "Provide:\n"
        "1. A narrative paragraph summary of the meeting.\n"
        "2. A JSON list of core decisions made ('key_decisions').\n"
        "3. A JSON list of explicit immediate next steps ('next_steps').\n\n"
        "Return your analysis strictly in valid JSON matching this schema:\n"
        "{\n"
        '  "summary": "narrative paragraph summary text",\n'
        '  "key_decisions": ["decision A", "decision B"],\n'
        '  "next_steps": ["step A", "step B"]\n'
        "}\n\n"
        f"Transcript:\n{transcript}"
    )
    try:
        data = await invoke_llm_json(prompt)
        return {
            "summary": data.get("summary", "Summary generation failed."),
            "key_decisions": data.get("key_decisions", []),
            "next_steps": data.get("next_steps", []),
        }
    except Exception as e:
        return {
            "errors": [f"Summarizer node error: {e}"],
            "summary": "Error generating summary.",
            "key_decisions": [],
            "next_steps": [],
        }


async def participant_agent(state: AgentState) -> Dict[str, Any]:
    """Agent 4: Perform participant and attribution analysis."""
    transcript = state.get("formatted_transcript", "")
    if not transcript:
        return {"participants": []}

    prompt = (
        "Identify all distinct participants and speakers active in the following meeting transcript.\n"
        "Return a JSON array of participant names.\n\n"
        "Format: {\"participants\": [\"Name 1\", \"Name 2\"]}\n\n"
        f"Transcript:\n{transcript}"
    )
    try:
        data = await invoke_llm_json(prompt)
        return {"participants": data.get("participants", [])}
    except Exception as e:
        return {"errors": [f"Participant node error: {e}"], "participants": []}


async def context_retrieval_agent(state: AgentState) -> Dict[str, Any]:
    """Agent 5: Search for related context across historical database."""
    # Note: Search integration happens directly or is populated prior/post flow.
    # Here we outline the node signature to pull in historical connections.
    return {"related_meetings": []}


# ---------- Helper utilities ----------


# Kept as a thin re-export for backward compatibility
_parse_json_from_llm = parse_json_from_llm


# ---------- Graph Compilation ----------


def build_meeting_workflow() -> StateGraph:
    workflow = StateGraph(AgentState)

    # Add agents
    workflow.add_node("transcriber", transcription_segmentation_agent)
    workflow.add_node("extractor", action_item_agent)
    workflow.add_node("summarizer", summarizer_agent)
    workflow.add_node("analyzer", participant_agent)
    workflow.add_node("retriever", context_retrieval_agent)

    # Connect nodes (run standard DAG flow)
    workflow.set_entry_point("transcriber")

    # Flow parallel-like mapping from transcription clean node (parallel fan-out)
    workflow.add_edge("transcriber", "extractor")
    workflow.add_edge("transcriber", "summarizer")
    workflow.add_edge("transcriber", "analyzer")
    workflow.add_edge("transcriber", "retriever")

    # Endpoints map cleanly
    workflow.add_edge("extractor", END)
    workflow.add_edge("summarizer", END)
    workflow.add_edge("analyzer", END)
    workflow.add_edge("retriever", END)

    return workflow.compile()


_compiled_workflow = None


def get_meeting_workflow():
    global _compiled_workflow
    if _compiled_workflow is None:
        _compiled_workflow = build_meeting_workflow()
    return _compiled_workflow
