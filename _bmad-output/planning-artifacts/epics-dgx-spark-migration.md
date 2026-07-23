---
title: 'Epics & Stories: DGX Spark Migration'
status: 'draft'
created: '2026-07-23'
references:
  - '_bmad-output/planning-artifacts/architecture-dgx-spark-addendum.md'
  - '_bmad-output/brainstorming/brainstorming-session-2026-07-23-0941.md'
---

# DGX Spark Migration — Epics & Stories

## Epic 1: Hardware & Infrastructure Setup

> **Goal:** DGX Spark operational with network, OS, and remote access.

### Story 1.1: DGX Spark Physical Setup & DGX OS
- **As** an operator, **I want** the DGX Spark racked, powered, and running DGX OS **so that** I can deploy workloads.
- **Acceptance Criteria:**
  - DGX Spark booted with DGX OS (Ubuntu-based ARM64)
  - 10 GbE LAN connected and reachable on local network
  - SSH access configured (key-based, no password)
  - NVMe storage verified (4 TB)
  - `nvidia-smi` reports Blackwell GPU healthy

### Story 1.2: Tailscale Migration
- **As** a developer, **I want** Tailscale configured on the DGX Spark **so that** I can reach it from home.
- **Acceptance Criteria:**
  - Tailscale installed and authenticated to existing tailnet
  - DGX Spark reachable at stable tailnet hostname (e.g. `dgx-spark`)
  - Mac Studio tailscale route retired or aliased
  - Firewall rules: only Tailscale + LAN; no public exposure
  - Hub API reachable over Tailscale from developer MacBooks

### Story 1.3: Docker & Container Runtime
- **As** an operator, **I want** Docker installed on DGX Spark **so that** I can run the hub API and database.
- **Acceptance Criteria:**
  - Docker Engine (not Desktop) installed on DGX OS
  - Docker Compose v2 available
  - GPU passthrough tested (`docker run --gpus all nvidia/cuda:13.0-base nvidia-smi`)
  - Storage driver configured for NVMe
  - Existing `docker-compose.yml` deploys (api + db) without modification

---

## Epic 2: vLLM Inference Engine Setup

> **Goal:** Replace Ollama with vLLM; all models loaded and serving.

### Story 2.1: vLLM Installation & CUDA 13.0 Setup
- **As** an operator, **I want** vLLM installed with CUDA 13.0 support **so that** it can leverage Blackwell Tensor Cores.
- **Acceptance Criteria:**
  - CUDA 13.0 toolkit installed and verified
  - vLLM ≥0.13 installed (cu130 aarch64 wheel or built from source)
  - `vllm serve` starts without errors on a test model
  - NVFP4 quantization kernels functional
  - Environment variables set: `TRITON_PTXAS_PATH`, etc.

### Story 2.2: Qwen3.6-27B Classify Service
- **As** the system, **I want** Qwen3.6-27B loaded via vLLM on port 8001 **so that** classify/triage runs in <2s.
- **Acceptance Criteria:**
  - Model downloaded from HuggingFace (`Qwen/Qwen3.6-27B`)
  - vLLM serves on port 8001 with `--gpu-memory-utilization 0.25`
  - OpenAI-compatible `/v1/chat/completions` responds correctly
  - Classify prompt returns valid JSON within 2s on single mail
  - systemd service (`vllm-classify.service`) with auto-restart
  - Logs to journald

### Story 2.3: Qwen3-72B Draft Service
- **As** the system, **I want** Qwen3-72B loaded via vLLM on port 8002 **so that** drafts generate in 5–8s.
- **Acceptance Criteria:**
  - Model downloaded (`Qwen/Qwen3-72B`)
  - vLLM serves on port 8002 with `--gpu-memory-utilization 0.45`
  - Q4 quantization applied (GPTQ or AWQ)
  - Draft prompt returns coherent NL reply in ≤8s
  - systemd service (`vllm-draft.service`) with auto-restart
  - Max context hard-limited to 32K tokens

### Story 2.4: Qwen3-Embedding-8B + Qwen3-Reranker-4B Service
- **As** the system, **I want** embedding and reranker models served **so that** retrieval + ranking works.
- **Acceptance Criteria:**
  - Both models downloaded and loaded (shared port 8003 or split)
  - Embedding returns 4096-dim vectors via `/v1/embeddings`
  - Reranker scores candidate documents accurately
  - FP16 inference (no quantization needed at 8B/4B)
  - systemd service with auto-restart

### Story 2.5: Vision Model Service (Lazy-Load)
- **As** the system, **I want** a vision model available on-demand **so that** image/scan attachments can be analyzed.
- **Acceptance Criteria:**
  - Vision model (e.g. Qwen2.5-VL-7B or successor) downloaded
  - vLLM serves on port 8004 in a lazy-load/on-demand pattern
  - Service starts within 30s when triggered
  - Processes a scan image and returns text description
  - Unloads after 5-min idle (or stays loaded if memory allows)
  - systemd service (socket-activated or manual start)

### Story 2.6: Model Startup Orchestration
- **As** an operator, **I want** models to load in priority order on boot **so that** classify is available first.
- **Acceptance Criteria:**
  - systemd dependencies: vllm-classify → vllm-draft → vllm-vision
  - After DGX Spark reboot: classify available within 60s
  - Draft available within 120s
  - Vision only started when first attachment triggers it
  - Health endpoint reflects per-model readiness

---

## Epic 3: Hub API Refactor (Inference Layer)

> **Goal:** Hub API talks to vLLM (OpenAI-compatible) instead of Ollama; dual-model routing in place.

### Story 3.1: Swap Ollama Client → OpenAI-Compatible Client
- **As** a developer, **I want** the inference client to use the OpenAI-compatible API **so that** it works with vLLM.
- **Acceptance Criteria:**
  - `inference.py` uses `httpx` or `openai` SDK with configurable `base_url`
  - `INFERENCE_BASE_URL` env var replaces hardcoded Ollama URL
  - Existing draft generation works unchanged (same prompt, same output format)
  - Tests pass with mocked OpenAI-format responses
  - Ollama support remains available via config (backward compatible)

### Story 3.2: Dual-Model Routing (Classify vs Draft)
- **As** the system, **I want** classify requests routed to 27B and draft requests to 72B **so that** each model handles its strength.
- **Acceptance Criteria:**
  - New config: `CLASSIFY_MODEL_URL` (port 8001) + `DRAFT_MODEL_URL` (port 8002)
  - `analyze_fast()` calls 27B; `generate_draft()` calls 72B
  - If 27B is down, fallback to 72B for classify (degraded, ~5s)
  - If 72B is down, draft returns `None` (UI shows "unavailable")
  - Metrics/logs distinguish which model handled which request

### Story 3.3: Language-Aware Prompts for 72B
- **As** the system, **I want** draft prompts optimized for Qwen3-72B's multilingual capabilities **so that** NL/EN/FR drafts are higher quality.
- **Acceptance Criteria:**
  - `detect_reply_language()` result feeds into prompt (existing behavior preserved)
  - 72B prompt leverages longer context (include more thread history)
  - A/B comparison: 10 test mails produce better drafts than 14B
  - No hardcoded fallbacks (as per recent decision)

### Story 3.4: Health & Readiness per Model
- **As** ops, **I want** `/health` to report per-model status **so that** I know which capabilities are degraded.
- **Acceptance Criteria:**
  - `/health` response includes: `classify: ok|down`, `draft: ok|down`, `embed: ok|down`, `vision: idle|ready|down`
  - Health check calls each vLLM `/health` endpoint
  - Add-in can show granular status ("draft unavailable" vs "fully down")
  - Prometheus metrics exposed at `/metrics` (vLLM native)

---

## Epic 4: Vector Store Migration (4096-dim)

> **Goal:** Upgrade embeddings from 1024-dim to 4096-dim with full reindex.

### Story 4.1: Alembic Migration — vector(1024) → vector(4096)
- **As** a developer, **I want** the pgvector column to support 4096 dimensions **so that** Qwen3-Embedding-8B vectors fit.
- **Acceptance Criteria:**
  - New Alembic migration alters embedding column to `vector(4096)`
  - Migration is reversible (downgrade back to 1024 possible with data loss warning)
  - Existing rows set to NULL or marked for re-embedding
  - HNSW index recreated for 4096-dim (tune `m` and `ef_construction`)
  - Migration tested on dev DB with sample data

### Story 4.2: Background Re-embedding Job
- **As** the system, **I want** all existing chunks re-embedded with the 8B model **so that** search quality improves.
- **Acceptance Criteria:**
  - Background job iterates all chunks, calls Qwen3-Embedding-8B
  - Progress tracked (% complete, ETA)
  - Batched calls (100 chunks per batch) for throughput
  - Idempotent: can be re-run if interrupted
  - Old 1024-dim vectors not served until row re-embedded
  - Estimated completion: <1h for pilot data volume

### Story 4.3: Embedding Service Integration
- **As** the system, **I want** new mails embedded with the 8B model on ingestion **so that** retrieval uses the upgraded vectors.
- **Acceptance Criteria:**
  - Mail ingestion calls embedding service (port 8003) for new chunks
  - 4096-dim vector stored in pgvector
  - Retrieval queries use same embedding model for query vector
  - Reranker receives top-N candidates and re-scores
  - E2E test: ingest mail → embed → retrieve similar → rerank → verify relevance

---

## Epic 5: Pre-compute Worker & Priority Queue

> **Goal:** Classify + embed mails in background; instant suggestions when user opens mail.

### Story 5.1: Pre-compute Worker Service
- **As** the system, **I want** a background worker that processes new mails **so that** suggestions are ready before the user looks.
- **Acceptance Criteria:**
  - Separate process/container: `spoqsense-precompute`
  - Polls for new/unprocessed mails (or receives push notification)
  - For each mail: embed → retrieve similar → rerank → classify → extract actions
  - Results written to `suggestions` table
  - Handles errors gracefully (skip, log, retry later)
  - Configurable concurrency (default: 4 mails in parallel)

### Story 5.2: Priority Queue Logic
- **As** the system, **I want** user-opened mails prioritized in the pre-compute queue **so that** active users get instant results.
- **Acceptance Criteria:**
  - When user opens a mail without pre-computed suggestion: boost priority
  - Queue ordering: user-triggered > recent mails > older mails
  - If mail already pre-computed: serve immediately (no re-compute)
  - If pre-compute in progress when user opens: wait for completion (<2s typical)
  - Stale suggestions (>1h) can be refreshed on open

### Story 5.3: Pre-compute State Machine
- **As** the system, **I want** each mail's pre-compute status tracked **so that** I never duplicate work.
- **Acceptance Criteria:**
  - DB column: `precompute_status` enum: `pending | processing | done | failed`
  - Timestamp: `precomputed_at`
  - Failed items retried up to 3x with exponential backoff
  - API can report "analyzing..." if status is `processing`
  - Dashboard/metrics show queue depth and throughput

---

## Epic 6: Attachment Processing Pipeline

> **Goal:** Understand PDF, DOCX, and image attachments as part of mail analysis.

### Story 6.1: Text Extraction Service
- **As** the system, **I want** to extract text from PDF and DOCX attachments **so that** their content can be included in analysis.
- **Acceptance Criteria:**
  - PDF extraction via PyMuPDF (pymupdf4llm for structured markdown)
  - DOCX extraction via python-docx
  - XLSX extraction via openpyxl (first sheet summary)
  - Extracted text truncated to 8K tokens (configurable)
  - Unsupported file types: skip with log + UI indicator
  - Size limit: 25 MB per attachment (align with Exchange)

### Story 6.2: Vision Model Integration (Scans/Images)
- **As** the system, **I want** scanned PDFs and images analyzed by a vision model **so that** non-OCR content is understood.
- **Acceptance Criteria:**
  - Detect "is this a scanned PDF?" heuristic (no text layer or very sparse text)
  - Route scanned PDFs + images (PNG, JPG) to vision model (port 8004)
  - Vision model returns structured description/transcription
  - Result fed to classify and draft prompts as context
  - Lazy-load: first image request triggers model start (~30s cold start)
  - After 5-min idle with no images: consider model for eviction

### Story 6.3: Attachment Summary in Suggestions
- **As** a user, **I want** to see a summary of attachments in the suggestion **so that** I know what's attached without opening files.
- **Acceptance Criteria:**
  - Suggestion payload includes `attachments[]` array
  - Each attachment: `{filename, type, summary, page_count}`
  - Summary generated by 27B (short: 1–2 sentences)
  - Displayed in Outlook add-in below the main suggestion
  - If extraction failed: show filename + "could not be analyzed"

---

## Epic 7: Action Extraction

> **Goal:** Detect deadlines, to-do's, and required actions from mail content.

### Story 7.1: Action Extraction Prompt & Schema
- **As** the system, **I want** to extract structured actions from classified mails **so that** users see what needs doing.
- **Acceptance Criteria:**
  - Classify prompt (27B) extended to also extract actions
  - Action schema: `{type: deadline|todo|meeting|question, description: str, due?: date}`
  - At least 3 action types detected reliably
  - Actions extracted from both mail body and attachment summaries
  - JSON output validated against schema

### Story 7.2: Action Storage & API
- **As** a developer, **I want** actions stored in the DB and served via API **so that** the add-in can display them.
- **Acceptance Criteria:**
  - `actions` table or JSONB column on `suggestions`
  - API includes actions in suggestion response
  - Actions linked to source mail + suggestion
  - Actions deduped if same mail re-analyzed
  - Deletable/dismissable by user (feedback endpoint)

### Story 7.3: Action Display in Add-in
- **As** a user, **I want** to see extracted actions in the Outlook pane **so that** I don't miss deadlines.
- **Acceptance Criteria:**
  - Actions shown as chips/badges below suggestion
  - Deadline actions highlighted if due within 2 days
  - Tapping action shows full context (which mail, what text)
  - "Not relevant" dismiss button records negative feedback
  - Accessible (WCAG AA): proper ARIA labels

---

## Epic 8: Testing, Cutover & Validation

> **Goal:** Validate the DGX Spark stack matches/exceeds Mac Studio quality before switching.

### Story 8.1: Parallel Run Setup
- **As** a developer, **I want** both Mac Studio and DGX Spark running simultaneously **so that** I can compare outputs.
- **Acceptance Criteria:**
  - DGX Spark serves on separate Tailscale hostname
  - Test harness sends same mails to both systems
  - Responses logged side-by-side for comparison
  - No user-facing traffic goes to DGX Spark yet
  - Duration: minimum 3 days with production mail volume

### Story 8.2: Quality Validation — NL/EN Drafts
- **As** a developer, **I want** to verify 72B drafts are higher quality than 14B **so that** migration is justified.
- **Acceptance Criteria:**
  - 20 test mails (10 NL, 10 EN) run through both systems
  - Evaluate: language correctness, style match, relevance, length
  - 72B must be ≥ as good on all dimensions (regression-free)
  - At least 2 dimensions measurably improved (e.g. longer coherent NL)
  - Results documented in validation report

### Story 8.3: Latency Validation
- **As** an operator, **I want** to confirm latency targets are met **so that** user experience improves.
- **Acceptance Criteria:**
  - Classify p95 < 2s (target: 10x faster than Mac Studio)
  - Draft p95 < 8s (target: 4x faster than Mac Studio)
  - Embedding throughput > 500 chunks/min
  - Pre-compute: 50 mails batch < 20s
  - Under concurrent load (3 users): no latency degradation > 20%

### Story 8.4: Cutover & Mac Studio Retirement
- **As** an operator, **I want** to switch production traffic to DGX Spark **so that** users benefit from the upgrade.
- **Acceptance Criteria:**
  - DNS/Tailscale hostname `spoqsense-hub` pointed to DGX Spark
  - Mac Studio services stopped (or kept as cold standby for 1 week)
  - All users confirmed working on new stack
  - Monitoring alerts configured for DGX Spark health
  - Rollback plan documented (re-point to Mac Studio within 5 min)
  - Mac Studio fully decommissioned after 1-week stabilization

---

## Dependency Graph

```
Epic 1 (Hardware)
  └── Epic 2 (vLLM)
        ├── Epic 3 (Hub API Refactor)
        │     └── Epic 5 (Pre-compute Worker)
        │           └── Epic 7 (Action Extraction)
        ├── Epic 4 (Vector Store Migration)
        │     └── Epic 5 (Pre-compute Worker)
        └── Epic 6 (Attachment Processing)
              └── Epic 7 (Action Extraction)

Epic 8 (Testing & Cutover) depends on all above
```

## Effort Estimates

| Epic | Effort | Notes |
|------|--------|-------|
| 1. Hardware & Infra | 1–2 days | Physical setup, Tailscale, Docker |
| 2. vLLM Setup | 2–3 days | Model downloads, systemd, tuning |
| 3. Hub API Refactor | 3–4 days | Client swap, dual routing, health |
| 4. Vector Store Migration | 2 days | Migration + re-embed job |
| 5. Pre-compute Worker | 3–4 days | Worker, queue, state machine |
| 6. Attachment Processing | 3 days | Text extraction + vision |
| 7. Action Extraction | 2–3 days | Prompt + schema + UI |
| 8. Testing & Cutover | 3–4 days | Parallel run, validation, switch |
| **Total** | **~20–25 days** | Sequential; parallelizable to ~15 days |
