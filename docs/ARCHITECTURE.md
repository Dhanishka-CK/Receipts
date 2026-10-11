# Receipts Architecture Specification

```mermaid
flowchart TD
    subgraph INPUT["1. Continuous Voice Ingestion"]
        OMI["🎙️ Omi Wearable / App"] -->|"Realtime Webhook (/omi/realtime)\nConversation Webhook (/omi/conversation)"| FASTAPI["⚡ FastAPI Webhook Gateway"]
        MIC["💬 Web Audio / Ingest Box"] -->|"/ingest"| FASTAPI
    end

    subgraph PIPELINE["2. Autonomous Multi-Agent Reasoning"]
        FASTAPI -->|"Debounced Utterance"| EXT["🧠 1. Lyzr Extractor Agent\n(Identifies Commitments, Decisions, Claims, Commands)"]
        
        EXT -->|"Search Related History\n(Filters: uid, visibility != private)"| QDRANT_SEARCH["🔍 Qdrant Semantic Retrieval\n(384-d Cosine Similarity)"]
        
        QDRANT_SEARCH -->|"Candidate Items + Related Memories"| AUD["⚖️ 2. Lyzr Auditor Agent\n(Detects Contradictions, Blockers, Superseded Decisions)"]
        
        AUD -->|"Audit Relation + Confidence + Evidence"| MGR["🎯 3. Lyzr Manager Agent\n(Decides Action: Alert, Update State, Store Only)"]
    end

    subgraph GUARDS["3. Deterministic Code Guards"]
        MGR --> GUARDS_EVAL["🛡️ Guard Engine\n• Valid State Machine Transitions\n• Confidence Floor (>= 0.70)\n• Deduplication & Rate Limits"]
    end

    subgraph STORAGE["4. Persistent State & Storage"]
        GUARDS_EVAL -->|"Store New Vectors & Update Target States"| QDRANT_STORE[("🗄️ Qdrant Vector Database\n(OPEN, BLOCKED, RESOLVED,\nACTIVE, SUPERSEDED)")]
    end

    subgraph OUTPUT["5. Autonomous Proactive Action"]
        GUARDS_EVAL -->|"Generate Evidence Receipt"| RECEIPT_ENGINE["🧾 Receipts Engine"]
        RECEIPT_ENGINE -->|"WebSocket / Polling"| DASHBOARD["🖥️ Interactive Live Dashboard"]
        RECEIPT_ENGINE -->|"Proactive Push API"| OMI_NOTIFY["📱 Omi Mobile Notification"]
    end

    subgraph AUTONOMY["6. Autonomous Background Services"]
        SCHED["⏰ Overdue Commitment Scanner\n(Runs every 30s)"] -->|"Filter: status=OPEN AND deadline < now"| QDRANT_STORE
        SCHED -->|"Overdue Items"| MGR
        
        PRIVACY["🔒 Privacy & Forgetting Controller"] -->|"Voice Command: 'Forget about X'\nManual UI Delete"| QDRANT_STORE
    end

    style INPUT fill:#1e293b,stroke:#38bdf8,stroke-width:2px,color:#fff
    style PIPELINE fill:#1e293b,stroke:#a78bfa,stroke-width:2px,color:#fff
    style GUARDS fill:#1e293b,stroke:#fbbf24,stroke-width:2px,color:#fff
    style STORAGE fill:#1e293b,stroke:#34d399,stroke-width:2px,color:#fff
    style OUTPUT fill:#1e293b,stroke:#f87171,stroke-width:2px,color:#fff
    style AUTONOMY fill:#1e293b,stroke:#e879f9,stroke-width:2px,color:#fff
```

---

## 1. Core Technological Integration

Receipts genuinely leverages the hackathon's three mandatory technologies:

1. **Omi (Continuous Voice Input & Notifications)**
   - Real-time transcript chunks and completed conversation summaries arrive through `/omi/realtime` and `/omi/conversation`.
   - Normalization layer handles varied schema shapes and extracts user identity (`uid`).
   - Non-blocking architecture: returns HTTP 200 within <20ms while processing heavy reasoning asynchronously.
   - When supported, evidence-backed receipts are pushed directly back to the user's phone via the Omi Notification API.

2. **Qdrant (Persistent Vector Memory & State Engine)**
   - Single vector collection (`receipts_memory`) with 384-dimensional cosine distance vectors (`BAAI/bge-small-en-v1.5`).
   - Semantic retrieval finds historically related commitments, decisions, and blockers even across days or semantic phrasing shifts.
   - Rich payload metadata tracking: `uid`, `memory_id`, `kind`, `subject`, `status`, `speaker`, `deadline_iso`, `deadline_ts`, `polarity`, `visibility`, `created_at`, `updated_at`, `confidence`.
   - Memory survives application restarts (via Qdrant Cloud or persistent embedded volume).

3. **Lyzr (Specialized Multi-Agent Swarm)**
   - **Extractor Agent**: Extracts structured primitives (`commitment`, `decision`, `claim`, `command`).
   - **Auditor Agent**: Reasons over new statements against retrieved vector memories to detect contradictions, blocker dependencies, and duplicate commitments.
   - **Manager Agent**: Coordinates policy, enforces conservative alerting, prevents alert spam, and instructs state changes.

---

## 2. Memory State Machine

Memory items evolve over time rather than remaining static text rows:

```mermaid
stateDiagram-v2
    [*] --> OPEN: Commitment Created
    OPEN --> BLOCKED: Auditor detects blocker ("Auth API blocks demo")
    BLOCKED --> OPEN: Blocker resolved ("Auth is fixed")
    OPEN --> DONE: Commitment completed ("Demo ready")
    
    [*] --> ACTIVE: Decision Created ("Let's use PostgreSQL")
    ACTIVE --> SUPERSEDED: Decision changed ("We're going with MongoDB")
    
    [*] --> CURRENT: Claim Created ("The API is blocked")
    CURRENT --> RESOLVED: Status resolved ("Auth is fixed now")
```

---

## 3. Privacy & Forgetting Architecture

Privacy is built directly into vector retrieval:
- **Private Sessions**: When "Don't remember this conversation" is detected, incoming utterances are completely ignored until "resume" is spoken.
- **Private Memories**: Memories tagged `visibility: "private"` are excluded at the Qdrant filter level (`must_not: visibility=private`).
- **Selective Forgetting**: "Forget what I said about X" executes semantic search and deletes matching vector points without deleting unrelated commitments.
