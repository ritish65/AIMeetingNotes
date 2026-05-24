# Personal Meeting Intelligence Agent (PMIA)

Production-ready autonomous agent that records meetings, transcribes them in real-time, extracts action items, performs hybrid semantic search across all past meetings, and triggers downstream actions via MCP-style tool integrations (Todoist, Gmail, Google Calendar, Filesystem).

## Highlights

- **Real-time STT** over WebSocket: streams 16kHz PCM from the browser to `faster-whisper` (local) or OpenAI Whisper API. Sub-second incremental partials.
- **LangGraph multi-agent workflow** (5 agents): Transcription → Action Item Extraction → Summarization → Participant Analysis → Past-Context Retrieval. Type-safe outputs via Pydantic.
- **Hybrid retrieval**: Qdrant dense (BGE) + sparse (BM25) fusion with multi-query amplification and LLM intent routing (`search` | `action` | `summary`).
- **MCP tool layer**: pluggable tool registry mapping cleanly to MCP servers (`@mcp/server-todoist`, `@mcp/server-gmail`, `@mcp/server-calendar`, `@mcp/server-filesystem`). Native HTTP fallbacks ship out of the box.
- **Human-in-the-loop**: every autonomous action is staged as an `ApprovalRequest` and executed only after user approval (configurable autopilot).
- **React + Vite + Tailwind dashboard**: live transcript, action-item review, hybrid search, autonomous-action approval queue.

## Architecture

```
 Browser (PCM audio)
       │  WebSocket /ws/stt
       ▼
 FastAPI ── faster-whisper / OpenAI Whisper
       │
       ▼
 LangGraph workflow (5 agents) ── Pydantic schemas
       │
       ├── Qdrant hybrid index (dense + sparse)
       └── Tool Registry (MCP-compatible)
              ├── Todoist
              ├── Gmail
              ├── Google Calendar
              └── Filesystem
```

## Quick start (Docker)

```bash
cp .env.example .env       # fill in OPENAI_API_KEY, TODOIST_TOKEN, etc.
docker compose up --build
# UI:      http://localhost:5173
# API:     http://localhost:8000/docs
# Qdrant:  http://localhost:6333/dashboard
```

## Local dev

```bash
# Backend
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# Frontend
cd frontend
npm install
npm run dev
```

## Required env vars

See `.env.example`. Minimum to boot: nothing — the system will use a stub LLM and stub MCP tools so the entire UI works offline. To unlock real intelligence:

- `OPENAI_API_KEY` (or `ANTHROPIC_API_KEY`) — agent LLM
- `STT_BACKEND=faster-whisper` (default) or `openai`
- `QDRANT_URL=http://localhost:6333`
- `TODOIST_TOKEN`, `GMAIL_*`, `GCAL_*` — to enable real MCP actions

## Project layout

```
backend/
  app/
    main.py
    config.py
    db.py
    models.py
    schemas.py
    api/                # REST routers
    stt/                # streaming STT
    agents/             # LangGraph nodes + workflow
    search/             # Qdrant hybrid + multi-query + router
    tools/              # MCP-compatible tool registry
    services/           # orchestration glue
  tests/
frontend/
  src/
docker-compose.yml
```

## License

MIT
```

