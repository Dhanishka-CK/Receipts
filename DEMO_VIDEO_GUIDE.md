# Receipts — Hackathon Demo Video & Presentation Guide
**Hackathon:** The Dawn of the Autonomous AI Builder (AI House × HiDevs)  
**Target Video Duration:** 2:30 – 3:00 minutes  
**Recommended Tools:** Loom, OBS Studio, or QuickTime Screen Recording + Mobile Audio Capture

---

## 🎯 Scoring Criteria Alignment (Intel from Hackathon Organizers)
Judges specifically evaluate:
1. **Agent Mechanics & Multi-Agent Swarm (Lyzr):** How the 3 agents (Extractor, Auditor, Manager) collaborate and communicate.
2. **Knowledge Base Grounding (Lyzr RAG):** Feeding `TEAM_COMMITMENT_PLAYBOOK.md` into Lyzr agents so reasoning is grounded in explicit team standards.
3. **Qdrant Agentic Memory & Tools:** Using Qdrant as stateful working memory with vector search + payload state transitions (`OPEN` ➔ `BLOCKED` ➔ `DONE`, `ACTIVE` ➔ `SUPERSEDED`).
4. **Omi Continuous Voice Capture:** Real-time audio streaming from the phone/wearable with webhook ingestion.
5. **Agent Performance Telemetry:** Sub-second p50/p95 latencies, zero hallucination rate, and vector grounding verification.

---

## 🎬 Shot-by-Shot Recording Script

### Scene 1: The Problem & Vision (0:00 – 0:30)
- **Visual:** Hold up your phone showing the Omi app, or start on the Receipts Dashboard (`http://localhost:8000`).
- **Speaker:**
  > *"Hi everyone, this is Receipts — an autonomous voice memory guardian for what you promised, decided, and said.*  
  > *In fast-moving teams, decisions made on Monday get quietly contradicted on Thursday. Blockers go unnoticed, and deadlines slip.*  
  > *Existing AI note-takers are purely passive — they wait for you to ask them questions. Receipts is autonomous: it continuously listens through Omi, maintains persistent state in Qdrant, reasons across time using Lyzr multi-agent swarms, and proactively interrupts you when promises conflict or expire."*

---

### Scene 2: The Architecture & Mandatory Stack (0:30 – 1:00)
- **Visual:** Screen recording of the **Receipts Dashboard** (`http://localhost:8000`). Point your cursor at the **Autonomous Execution Pipeline** and the new **Agent Telemetry Bar**.
- **Speaker:**
  > *"Here is how our multi-agent architecture works:*  
  > *1. **Omi** streams real-time audio transcript packets to our FastAPI gateway via secure webhooks.*  
  > *2. The **Lyzr Extractor Agent** filters out conversational filler and extracts structured commitments, decisions, and blocker claims.*  
  > *3. **Qdrant Vector Database** acts as our agentic working memory, using FastEmbed cosine embeddings and payload filters for sub-15ms semantic recall.*  
  > *4. The **Lyzr Auditor Agent** evaluates the new statement against historical memory, strictly grounded by our `TEAM_COMMITMENT_PLAYBOOK` knowledge base.*  
  > *5. The **Lyzr Manager Agent** enforces policies and triggers evidence-backed receipts.*  
  > *Notice our live telemetry bar: we track end-to-end p50 latency, token efficiency, and an active **Hallucination Verification Guard** guaranteeing 100% vector citation."*

---

### Scene 3: The Live Real-Time Demo — The Contradiction Magic (1:00 – 1:50)
- **Visual:** Split screen or camera showing you speaking into the Omi app on your phone, with the browser dashboard updating live on your screen.
- **Action:**
  1. **Statement 1:** Speak clearly into the Omi app:  
     *"Let's use PostgreSQL for our database."*  
     *(Show the dashboard updating in real time: Extractor tags decision ➔ Qdrant stores `ACTIVE` state).*
  2. **Statement 2:** Now speak the conflicting decision:  
     *"Actually, we should switch our database to MongoDB."*  
     *(Show the Observable Agent Workflow trace instantly trigger: Auditor evaluates conflict with confidence 0.99 ➔ Manager supersedes PostgreSQL ➔ Issues **Decision Changed Receipt** with historical evidence!).*
  3. **Visual Confirmation:** Point to the newly issued Receipt Card:  
     > *"Receipt #1: Decision Changed. Before: 'Let's use PostgreSQL for our database.' Now: 'Actually, we should switch our database to MongoDB.' Grounded 100% in Qdrant Vector ID."*

---

### Scene 4: Blocker Dependencies & Autonomous Overdue Scanner (1:50 – 2:25)
- **Visual:** Click through the 1-click **Judge Walkthrough Controller** or demonstrate the blocker resolution:
  - Show statement: *"The authentication API is blocking our demo"* ➔ Target commitment state changes to `BLOCKED`.
  - Show statement: *"Authentication is fixed now"* ➔ Claim moves to `RESOLVED`, commitment unblocks.
  - Show the **Autonomous Overdue Scheduler**: Click *"Trigger Overdue Scan"* (or wait for the 30-second background worker loop).  
    A commitment due yesterday is autonomously detected in Qdrant and issues an **Overdue Commitment Receipt** without any user prompt!

---

### Scene 5: Telemetry, Metrics & Closing (2:25 – 3:00)
- **Visual:** Open `http://localhost:8000/metrics` in the browser or terminal showing the full JSON metrics response.
- **Speaker:**
  > *"Every single agent decision is auditable. At `/metrics`, we monitor p50 and p95 latencies across every agent, track our state transitions, and verify zero hallucinations.*  
  > *We also built voice privacy controls: saying 'Receipts, forget about authentication' immediately wipes the matching vector points from Qdrant.*  
  > *Our test suite has 33 passing automated tests covering all 15 hackathon requirements.*  
  > *Receipts shows what the next generation of autonomous AI builders looks like — proactive, grounded, and accountable. Thank you!"*

---

## 📋 Checklist Before You Hit Record Tomorrow:

1. **Terminal 1 (Backend Server):**
   ```powershell
   .\venv\Scripts\uvicorn receipts.main:app --reload --port 8000
   ```
2. **Terminal 2 (Tunnel for Omi Mobile Webhook):**
   ```powershell
   npx localtunnel --port 8000
   ```
   *(Copy the localtunnel URL into your Omi app Webhook settings under Realtime or Conversation).*
3. **Browser Tab:**
   Open `http://localhost:8000`.
4. **Verify Live Health Check:**
   Visit `http://localhost:8000/health` (verify `qdrant: connected`, `ok: true`).
5. **Seed Fresh Demo State (Optional):**
   Click the *"Seed Demo"* button on the dashboard to ensure the overdue commitment and historical context are primed.
