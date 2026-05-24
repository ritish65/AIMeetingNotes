# Personal Meeting Intelligence Agent - Architecture Diagram

## System Architecture

```mermaid
graph TB
    subgraph "Frontend - React Dashboard"
        UI[React Dashboard]
        UI_Mic[Mic Button]
        UI_Live[Live Transcript]
        UI_Search[Search Interface]
        UI_Approvals[Approval Queue]
        UI_Meetings[Meeting List]
    end

    subgraph "Backend - FastAPI"
        API[REST API Endpoints]
        WS[WebSocket STT Endpoint]
        DB[SQLite Database]
        QDRANT[Qdrant Vector Store]
    end

    subgraph "LangGraph Multi-Agent Workflow"
        AGENT_TRANS[Transcriber Agent]
        AGENT_ACTION[Action Item Extractor]
        AGENT_SUMM[Summarizer Agent]
        AGENT_PART[Participant Analyzer]
        AGENT_CTX[Context Retriever]
    end

    subgraph "MCP Tool Integrations"
        MCP_TODO[Todoist]
        MCP_GMAIL[Gmail]
        MCP_CAL[Google Calendar]
        MCP_FS[Filesystem]
    end

    subgraph "External Services"
        STT[Speech-to-Text]
        LLM[LLM Provider]
        EMBED[Embedding Model]
    end

    %% Frontend to Backend Connections
    UI -->|HTTP REST| API
    UI_Mic -->|WebSocket Audio| WS
    UI_Live -->|WebSocket Text| WS
    UI_Search -->|Search Query| API
    UI_Approvals -->|Approve/Reject| API
    UI_Meetings -->|CRUD Operations| API

    %% Backend to Database
    API -->|SQLAlchemy Async| DB
    WS -->|SQLAlchemy Async| DB

    %% Backend to Vector Store
    API -->|Hybrid Search| QDRANT
    API -->|Index/Update| QDRANT

    %% Backend to LangGraph
    API -->|Trigger Workflow| AGENT_TRANS
    WS -->|Finalize Transcript| AGENT_TRANS

    %% LangGraph Agent Flow
    AGENT_TRANS -->|Clean Transcript| AGENT_ACTION
    AGENT_TRANS -->|Clean Transcript| AGENT_SUMM
    AGENT_TRANS -->|Clean Transcript| AGENT_PART
    AGENT_TRANS -->|Clean Transcript| AGENT_CTX

    %% Agents to MCP Tools
    AGENT_ACTION -->|Create Tasks| MCP_TODO
    AGENT_SUMM -->|Send Summary| MCP_GMAIL
    AGENT_CTX -->|Query Calendar| MCP_CAL
    AGENT_CTX -->|Store Reports| MCP_FS

    %% Backend to External Services
    WS -->|Audio Stream| STT
    AGENT_TRANS -->|Transcribe| STT
    AGENT_ACTION -->|Extract Items| LLM
    AGENT_SUMM -->|Generate Summary| LLM
    AGENT_PART -->|Analyze Speakers| LLM
    AGENT_CTX -->|Context Queries| LLM
    API -->|Generate Embeddings| EMBED
    QDRANT -->|Vector Search| EMBED

    %% Styling
    classDef frontend fill:#e1f5ff,stroke:#01579b,stroke-width:2px
    classDef backend fill:#fff3e0,stroke:#e65100,stroke-width:2px
    classDef agent fill:#f3e5f5,stroke:#4a148c,stroke-width:2px
    classDef mcp fill:#e8f5e9,stroke:#1b5e20,stroke-width:2px
    classDef external fill:#ffebee,stroke:#b71c1c,stroke-width:2px

    class UI,UI_Mic,UI_Live,UI_Search,UI_Approvals,UI_Meetings frontend
    class API,WS,DB,QDRANT backend
    class AGENT_TRANS,AGENT_ACTION,AGENT_SUMM,AGENT_PART,AGENT_CTX agent
    class MCP_TODO,MCP_GMAIL,MCP_CAL,MCP_FS mcp
    class STT,LLM,EMBED external
```

## Data Flow

### Real-Time Transcription Flow

```mermaid
sequenceDiagram
    participant User
    participant Frontend
    participant WebSocket
    participant STT
    participant Database

    User->>Frontend: Click Mic Button
    Frontend->>Frontend: Request Mic Permission
    Frontend->>WebSocket: Connect (ws://host/ws/stt)
    WebSocket-->>Frontend: Handshake ACK {"status": "ready"}
    
    loop Audio Streaming
        User->>Frontend: Speaking
        Frontend->>Frontend: Capture Audio (16kHz mono)
        Frontend->>WebSocket: Send Audio Chunks
        WebSocket->>WebSocket: Buffer (~1s / 32KB)
        WebSocket->>STT: Transcribe Chunk
        STT-->>WebSocket: Text Result
        WebSocket->>Database: Save Transcript Segment
        WebSocket-->>Frontend: Send Transcribed Text
        Frontend->>Frontend: Update Live Transcript UI
    end

    User->>Frontend: Stop Recording
    Frontend->>WebSocket: Close Connection
    WebSocket->>WebSocket: Flush Remaining Buffer
    WebSocket->>Database: Finalize Transcript
```

### Meeting Processing Workflow

```mermaid
sequenceDiagram
    participant API
    participant Workflow
    participant Transcriber
    participant ActionAgent
    participant Summarizer
    participant ParticipantAgent
    participant ContextAgent
    participant Database
    participant Qdrant
    participant MCP

    API->>Workflow: Trigger Processing (meeting_id)
    Workflow->>Transcriber: Load Transcript Segments
    Transcriber->>Transcriber: Segment & Clean Text
    Transcriber-->>Workflow: Clean Transcript

    par Parallel Agent Execution
        Workflow->>ActionAgent: Extract Action Items
        ActionAgent->>ActionAgent: LLM Extraction
        ActionAgent-->>Workflow: Action Items
        and
        Workflow->>Summarizer: Generate Summary
        Summarizer->>Summarizer: LLM Summarization
        Summarizer-->>Workflow: Meeting Summary
        and
        Workflow->>ParticipantAgent: Analyze Speakers
        ParticipantAgent->>ParticipantAgent: LLM Analysis
        ParticipantAgent-->>Workflow: Speaker Insights
        and
        Workflow->>ContextAgent: Retrieve Context
        ContextAgent->>Qdrant: Hybrid Search
        ContextAgent->>MCP: Query Calendar/Files
        ContextAgent-->>Workflow: Context Results
    end

    Workflow->>Database: Save Action Items
    Workflow->>Database: Save Summary
    Workflow->>Database: Save Speaker Analysis
    Workflow->>Qdrant: Index Meeting (Embeddings)
    Workflow->>MCP: Stage Approval Requests
    Workflow-->>API: Processing Complete
```

### Search Flow

```mermaid
sequenceDiagram
    participant User
    participant Frontend
    participant API
    participant Qdrant
    participant LLM

    User->>Frontend: Enter Search Query
    Frontend->>API: POST /api/search {query}
    API->>LLM: Classify Intent
    LLM-->>API: Intent (semantic/factual/temporal)
    API->>LLM: Multi-Query Amplification
    LLM-->>API: Expanded Queries
    
    par Hybrid Search
        API->>Qdrant: Dense Vector Search
        and
        API->>Qdrant: Sparse BM25 Search
    end
    
    Qdrant-->>API: Ranked Results
    API->>API: Re-rank & Filter
    API-->>Frontend: Search Results
    Frontend->>Frontend: Display Results
```

## Component Details

### Frontend (React + Vite + Tailwind)
- **Live Transcription**: Real-time display of transcribed text via WebSocket
- **Meeting Management**: Create, view, list, and finalize meetings
- **Search Interface**: Hybrid search with intent-aware queries
- **Approval Queue**: Human-in-the-loop for autonomous actions
- **Tech Stack**: React 18, Vite, TailwindCSS, Lucide Icons

### Backend (FastAPI + SQLAlchemy)
- **REST API**: CRUD operations for meetings, transcripts, action items
- **WebSocket Endpoint**: Real-time audio streaming and transcription
- **Database**: SQLite with async SQLAlchemy ORM
- **Middleware**: CORS (permissive in dev), health checks

### LangGraph Multi-Agent Workflow
- **Transcriber**: Segments and cleans raw transcript
- **Action Item Extractor**: Extracts tasks with owners/deadlines
- **Summarizer**: Generates meeting summaries and key decisions
- **Participant Analyzer**: Identifies speakers and their contributions
- **Context Retriever**: Searches past meetings and external context

### MCP Tool Integrations
- **Todoist**: Create/manage tasks from action items
- **Gmail**: Send meeting summaries via email
- **Google Calendar**: Query calendar for context
- **Filesystem**: Store reports and documents

### External Services
- **STT**: faster-whisper (local) or OpenAI Whisper API
- **LLM**: OpenAI GPT-4 or Anthropic Claude (with stub fallback)
- **Embeddings**: BGE-small-en-v1.5 via fastembed
- **Vector Store**: Qdrant for hybrid dense+sparse search

## Deployment Architecture

```mermaid
graph LR
    subgraph "Docker Compose"
        QDRANT[Qdrant<br/>Port: 6335/6336]
        BACKEND[Backend<br/>FastAPI<br/>Port: 8000]
        FRONTEND[Frontend<br/>Vite Dev Server<br/>Port: 5173]
    end

    subgraph "Host Machine"
        BROWSER[Web Browser]
    end

    BROWSER -->|HTTP:5173| FRONTEND
    FRONTEND -->|Proxy: /api, /ws| BACKEND
    BACKEND -->|TCP:6335| QDRANT
```

## Hybrid Search Architecture

```mermaid
graph TB
    subgraph "HybridSearchIndex Class"
        INIT[__init__]
        ENSURE[_ensure_collection]
        INDEX[index_meeting]
        INVALIDATE[invalidate_meeting]
        ROUTE[route_intent]
        AMPLIFY[amplify_query]
        SEARCH[search]
        LOCAL[local_docs]
    end

    subgraph "External Services"
        QDRANT[Qdrant Vector Store]
        FASTEMBED[fastembed BGE Embeddings]
        LLM[LLM Provider]
    end

    subgraph "Configuration"
        SETTINGS[Settings]
    end

    subgraph "Schemas"
        INTENT[Intent]
        SEARCHREQ[SearchRequest]
        SEARCHRES[SearchResponse]
        SEARCHHIT[SearchHit]
    end

    %% Initialization Flow
    INIT -->|Read config| SETTINGS
    INIT -->|Connect| QDRANT
    INIT -->|Initialize| FASTEMBED
    INIT -->|Ensure collection| ENSURE
    ENSURE -->|Create if not exists| QDRANT
    INIT -->|Fallback flag| LOCAL

    %% Indexing Flow
    INDEX -->|Always store| LOCAL
    INDEX -->|If Qdrant available| QDRANT
    INDEX -->|Generate embeddings| FASTEMBED
    INDEX -->|Upsert points| QDRANT

    %% Invalidation Flow
    INVALIDATE -->|Remove from| LOCAL
    INVALIDATE -->|Delete points| QDRANT

    %% Intent Routing Flow
    ROUTE -->|Classify query| LLM
    LLM -->|Return JSON| ROUTE
    ROUTE -->|Return| INTENT

    %% Query Amplification Flow
    AMPLIFY -->|Expand query| LLM
    LLM -->|Return variations| AMPLIFY
    AMPLIFY -->|Return queries| SEARCH

    %% Search Flow
    SEARCH -->|Route intent| ROUTE
    SEARCH -->|Amplify query| AMPLIFY
    SEARCH -->|If fallback| LOCAL
    SEARCH -->|If Qdrant| QDRANT
    SEARCH -->|Embed queries| FASTEMBED
    SEARCH -->|Vector search| QDRANT
    SEARCH -->|Return| SEARCHRES

    %% Styling
    classDef class fill:#e1f5ff,stroke:#01579b,stroke-width:2px
    classDef external fill:#ffebee,stroke:#b71c1c,stroke-width:2px
    classDef config fill:#fff3e0,stroke:#e65100,stroke-width:2px
    classDef schema fill:#f3e5f5,stroke:#4a148c,stroke-width:2px

    class INIT,ENSURE,INDEX,INVALIDATE,ROUTE,AMPLIFY,SEARCH,LOCAL class
    class QDRANT,FASTEMBED,LLM external
    class SETTINGS config
    class INTENT,SEARCHREQ,SEARCHRES,SEARCHHIT schema
```

### Hybrid Search Data Flow

```mermaid
sequenceDiagram
    participant API as API Endpoint
    participant HSI as HybridSearchIndex
    participant LLM as LLM Provider
    participant FE as fastembed
    participant Qdrant as Qdrant
    participant Local as local_docs

    API->>HSI: search(SearchRequest)
    
    Note over HSI,LLM: Intent Routing
    HSI->>LLM: route_intent(query)
    LLM-->>HSI: Intent (search/action/summary/qa)
    
    Note over HSI,LLM: Query Amplification
    HSI->>LLM: amplify_query(query)
    LLM-->>HSI: Expanded queries [original + 3 variations]
    
    alt Qdrant Available
        Note over HSI,FE: Dense Vector Search
        loop For each query
            HSI->>FE: embed(query)
            FE-->>HSI: Dense vector
            HSI->>Qdrant: search(vector, limit=top_k)
            Qdrant-->>HSI: Ranked results
        end
        HSI->>HSI: Deduplicate & re-rank
    else Fallback Mode
        Note over HSI,Local: In-Memory BM25
        HSI->>Local: Token match in local_docs
        Local-->>HSI: Scored results
    end
    
    HSI-->>API: SearchResponse(intent, expanded_queries, hits)
```

### Hybrid Search Class Methods

| Method | Purpose | Key Operations |
|--------|---------|----------------|
| `__init__()` | Initialize search index | Connect to Qdrant, init fastembed encoder, create collection |
| `_ensure_collection()` | Ensure Qdrant collection exists | Create collection with dense + sparse vector configs |
| `index_meeting()` | Index meeting segments | Generate embeddings, upsert to Qdrant, store in local_docs |
| `invalidate_meeting()` | Remove outdated meeting | Delete from Qdrant by meeting_id, remove from local_docs |
| `route_intent()` | Classify user query intent | LLM classification (search/action/summary/qa) |
| `amplify_query()` | Expand search query | LLM generates 3 semantic variations |
| `search()` | Main search orchestration | Route intent, amplify query, execute search, return results |

### Key Design Patterns

1. **Event-Driven**: WebSocket for real-time audio streaming
2. **Multi-Agent DAG**: LangGraph parallel agent execution
3. **Hybrid Search**: Dense (embeddings) + Sparse (BM25) vector search
4. **Human-in-the-Loop**: Approval queue for autonomous actions
5. **Mock-Safe Fallbacks**: Graceful degradation when APIs unavailable
6. **Type-Safe Schemas**: Pydantic for structured LLM outputs
7. **Async-First**: Full async/await stack for scalability
8. **Dual Indexing**: Always store in memory + Qdrant for resilience
9. **LLM-Enhanced Search**: Intent classification and query expansion for better relevance
10. **Singleton Pattern**: Single search index instance per application lifecycle
