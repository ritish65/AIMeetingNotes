"""FastAPI REST and WebSocket endpoints.

Implements real-time binary audio streaming over WebSocket with Whisper, 
and full CRUD control for meetings, action items, approvals, and search.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, List

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, WebSocket, WebSocketDisconnect
from loguru import logger
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..models import ActionItem as ActionItemModel
from ..models import ApprovalRequest as ApprovalModel
from ..models import ApprovalStatus, Meeting, MeetingStatus, TranscriptSegment
from ..schemas import (
    ActionItemOut,
    ApprovalOut,
    MeetingCreate,
    MeetingOut,
    SearchRequest,
    SearchResponse,
    TranscribeFinalize,
    TranscriptSegmentOut,
)
from ..search.index import get_search_index
from ..services.meeting_processor import process_meeting_pipeline
from ..stt.transcriber import get_transcriber
from ..tools.registry import execute_tool
from ..utils import create_transcript_segment, fetch_meeting

router = APIRouter()


# ---------- REST Endpoints ----------


@router.post("/meetings", response_model=MeetingOut)
async def create_meeting(payload: MeetingCreate, db: AsyncSession = Depends(get_session)) -> Meeting:
    title = payload.title
    if not title:
        title = f"Meeting - {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC"

    meeting = Meeting(title=title, status=MeetingStatus.recording)
    db.add(meeting)
    await db.commit()
    await db.refresh(meeting)
    return meeting


@router.get("/meetings", response_model=List[MeetingOut])
async def list_meetings(db: AsyncSession = Depends(get_session)) -> List[Meeting]:
    res = await db.execute(select(Meeting).order_by(Meeting.started_at.desc()))
    return list(res.scalars().all())


@router.get("/meetings/{meeting_id}", response_model=MeetingOut)
async def get_meeting(meeting_id: str, db: AsyncSession = Depends(get_session)) -> Meeting:
    meeting = await fetch_meeting(db, meeting_id)
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")
    return meeting


@router.delete("/meetings/{meeting_id}")
async def delete_meeting(meeting_id: str, db: AsyncSession = Depends(get_session)) -> Dict[str, Any]:
    # Verify the meeting exists before deleting
    res = await db.execute(select(Meeting).where(Meeting.id == meeting_id))
    meeting = res.scalar_one_or_none()
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")

    # Delete from Qdrant vector index
    idx = get_search_index()
    await idx.invalidate_meeting(meeting_id)

    # Delete from DB (cascades automatically to segments, action items, approvals)
    await db.execute(delete(Meeting).where(Meeting.id == meeting_id))
    await db.commit()
    return {"success": True, "message": f"Meeting {meeting_id} deleted successfully."}


@router.get("/meetings/{meeting_id}/segments", response_model=List[TranscriptSegmentOut])
async def get_meeting_segments(
    meeting_id: str, db: AsyncSession = Depends(get_session)
) -> List[TranscriptSegment]:
    res = await db.execute(
        select(TranscriptSegment)
        .where(TranscriptSegment.meeting_id == meeting_id)
        .order_by(TranscriptSegment.start_ms.asc())
    )
    return list(res.scalars().all())


@router.get("/meetings/{meeting_id}/action-items", response_model=List[ActionItemOut])
async def get_meeting_action_items(
    meeting_id: str, db: AsyncSession = Depends(get_session)
) -> List[ActionItemModel]:
    res = await db.execute(
        select(ActionItemModel).where(ActionItemModel.meeting_id == meeting_id)
    )
    return list(res.scalars().all())


@router.get("/meetings/{meeting_id}/approvals", response_model=List[ApprovalOut])
async def get_meeting_approvals(
    meeting_id: str, db: AsyncSession = Depends(get_session)
) -> List[ApprovalModel]:
    res = await db.execute(
        select(ApprovalModel).where(ApprovalModel.meeting_id == meeting_id)
    )
    return list(res.scalars().all())


@router.post("/meetings/{meeting_id}/finalize")
async def finalize_meeting(
    meeting_id: str,
    payload: TranscribeFinalize,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    meeting = await fetch_meeting(db, meeting_id)
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")

    if meeting.status in (MeetingStatus.processing, MeetingStatus.completed):
        return {"success": False, "message": "Meeting is already processed or processing."}

    meeting.status = MeetingStatus.processing

    # If transcript is manually uploaded/edited, set it
    if payload.transcript:
        meeting.transcript = payload.transcript
    else:
        # Construct raw transcript from segment records
        seg_res = await db.execute(
            select(TranscriptSegment)
            .where(TranscriptSegment.meeting_id == meeting_id)
            .order_by(TranscriptSegment.start_ms.asc())
        )
        segments = seg_res.scalars().all()
        assembled = []
        for s in segments:
            speaker_tag = f"{s.speaker or 'Speaker'}: "
            assembled.append(f"{speaker_tag}{s.text}")
        meeting.transcript = "\n".join(assembled)

    if not meeting.transcript or not meeting.transcript.strip():
        meeting.status = MeetingStatus.failed
        await db.commit()
        raise HTTPException(
            status_code=400,
            detail="Cannot finalize meeting: transcript is empty. Record audio or provide a transcript.",
        )

    await db.commit()

    # Trigger async orchestration flow
    background_tasks.add_task(process_meeting_pipeline, meeting_id, meeting.transcript)

    return {
        "success": True,
        "message": "Meeting workflow kicked off in the background.",
        "status": "processing",
    }


# ---------- Action Item Approval Routing ----------


@router.get("/action-items", response_model=List[ActionItemOut])
async def list_all_action_items(db: AsyncSession = Depends(get_session)) -> List[ActionItemModel]:
    res = await db.execute(select(ActionItemModel))
    return list(res.scalars().all())


@router.post("/approvals/{approval_id}/action")
async def handle_approval_action(
    approval_id: str, action: str, db: AsyncSession = Depends(get_session)
) -> Dict[str, Any]:
    """Approve or reject a staged autonomous tool action."""
    if action not in ("approve", "reject"):
        raise HTTPException(status_code=400, detail="Action must be 'approve' or 'reject'")

    res = await db.execute(select(ApprovalModel).where(ApprovalModel.id == approval_id))
    app_req = res.scalar_one_or_none()
    if not app_req:
        raise HTTPException(status_code=404, detail="Approval request not found")

    if app_req.status != ApprovalStatus.pending:
        raise HTTPException(
            status_code=400,
            detail=f"Approval is already in state: {app_req.status}",
        )

    if action == "reject":
        app_req.status = ApprovalStatus.rejected
        await db.commit()
        return {"success": True, "status": "rejected"}

    # Execute approved action
    app_req.status = ApprovalStatus.approved
    await db.commit()

    tool_res = await execute_tool(app_req.tool_name, app_req.payload)
    if tool_res.success:
        app_req.status = ApprovalStatus.executed
        app_req.result = tool_res.to_dict()
    else:
        app_req.status = ApprovalStatus.failed
        app_req.error = tool_res.message

    await db.commit()
    return {
        "success": tool_res.success,
        "status": app_req.status,
        "message": tool_res.message,
    }


# ---------- Hybrid Search Routing ----------


@router.post("/search", response_model=SearchResponse)
async def hybrid_search(req: SearchRequest) -> SearchResponse:
    idx = get_search_index()
    return await idx.search(req)


# ---------- Real-Time Audio Streaming WebSocket ----------


@router.websocket("/ws/stt")
async def ws_stt_endpoint(websocket: WebSocket) -> None:
    """Consumes 16kHz binary audio chunks, transcribes real-time partials, and saves."""
    await websocket.accept()
    logger.info("New WebSocket client connected for real-time STT streaming")

    meeting_id = None
    transcriber = get_transcriber()

    # Track audio chunks for transcription buffering
    audio_buffer = bytearray()
    acc_bytes = 0

    try:
        # First message expected: JSON handshake with meeting metadata
        init_data = await websocket.receive_json()
        meeting_id = init_data.get("meeting_id")
        if not meeting_id:
            await websocket.send_json({"error": "Missing meeting_id in handshake"})
            await websocket.close(code=1003)
            return

        logger.info("Streaming session linked to meeting_id: {}", meeting_id)
        # Inform client the socket is ready to receive audio bytes
        await websocket.send_json({"status": "ready", "meeting_id": meeting_id})

        while True:
            # Consume raw PCM binary chunk
            message = await websocket.receive()
            if "bytes" in message:
                raw_chunk = message["bytes"]
                audio_buffer.extend(raw_chunk)
                acc_bytes += len(raw_chunk)

                # Keep buffers manageable: transcribe roughly every ~1s (32KB @ 16kHz 16-bit mono)
                # 16kHz mono 16-bit PCM ~ 32000 bytes/sec
                if len(audio_buffer) >= 32000:
                    transcription = transcriber.transcribe_chunk(bytes(audio_buffer))

                    if transcription.strip():
                        from ..db import session_scope

                        async with session_scope() as db:
                            seg_dur_ms = int((len(audio_buffer) / 32000) * 1000)
                            segment = await create_transcript_segment(
                                db,
                                meeting_id=meeting_id,
                                text=transcription,
                                start_ms=max(0, int((acc_bytes / 32000) * 1000) - seg_dur_ms),
                                end_ms=int((acc_bytes / 32000) * 1000),
                            )

                            await websocket.send_json(
                                {
                                    "speaker": segment.speaker,
                                    "start_ms": segment.start_ms,
                                    "end_ms": segment.end_ms,
                                    "text": segment.text,
                                    "is_final": True,
                                }
                            )

                    # Flush buffer
                    audio_buffer.clear()

            elif "text" in message:
                # Handle control/heartbeat text frames if needed
                ctrl = message["text"]
                if ctrl == "ping":
                    await websocket.send_text("pong")

    except WebSocketDisconnect:
        logger.info("WebSocket connection closed normally (client disconnected)")
    except Exception as e:
        logger.error("Error in real-time STT WebSocket connection: {}", e)
        try:
            await websocket.send_json({"error": f"Internal server error: {e}"})
        except Exception:
            pass
    finally:
        # Flush remaining buffer at the end of recording
        if meeting_id and len(audio_buffer) >= 3200:
            transcription = transcriber.transcribe_chunk(bytes(audio_buffer))
            if transcription.strip():
                try:
                    from ..db import session_scope

                    async with session_scope() as db:
                        await create_transcript_segment(
                            db,
                            meeting_id=meeting_id,
                            text=transcription,
                            start_ms=max(0, int((acc_bytes / 32000) * 1000) - int((len(audio_buffer) / 32000) * 1000)),
                            end_ms=int((acc_bytes / 32000) * 1000),
                        )
                except Exception as db_err:
                    logger.error("Failed to commit final chunk: {}", db_err)
