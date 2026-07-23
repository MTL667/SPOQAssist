---
title: 'Architecture Addendum: DGX Spark Migration'
status: 'draft'
created: '2026-07-23'
supersedes_section: 'Local Model Stack (pinned) in architecture.md'
input_documents:
  - '_bmad-output/brainstorming/brainstorming-session-2026-07-23-0941.md'
  - '_bmad-output/planning-artifacts/architecture.md'
---

# Architecture Addendum: DGX Spark Migration

This document extends the existing architecture with decisions for migrating from the Mac Studio (48 GB, Apple Silicon, Ollama) to the Nvidia DGX Spark (128 GB unified, Blackwell, vLLM).

## Hardware Change

| Property | Mac Studio (current) | DGX Spark (target) |
|----------|---------------------|-------------------|
| Memory | 48 GB unified (Apple Silicon) | 128 GB unified (LPDDR5x) |
| Compute | Apple Neural Engine | Blackwell Tensor Cores, 1 PFLOP FP4 |
| Architecture | ARM64 (macOS) | ARM64 (DGX OS / Linux) |
| CUDA | N/A | SM121, CUDA 13.0+ |
| Storage | 1 TB NVMe | 4 TB NVMe |
| Network | 1 GbE + Wi-Fi | 10 GbE + ConnectX-7 200 Gbps + Wi-Fi 7 |

## Model Stack (replaces "Local Model Stack (pinned)")

| Role | Model | Params | Quantization | Memory | Context | Notes |
|------|-------|--------|--------------|--------|---------|-------|
| Classify / triage (pre-compute) | **Qwen3.6-27B** | 27B dense | Q4 | ~15 GB | 262K native | Fast (<2s/mail), newest generation, 262K context |
| Draft / deep analysis (on-demand) | **Qwen3-72B** | 72B dense | Q4 | ~40 GB | 128K | Complex NL drafts, thread summaries, attachment analysis |
| Embedding | **Qwen3-Embedding-8B** | 8B | FP16 | ~9 GB | 32K | 4096-dim dense; MRL supports truncation if needed |
| Reranker | **Qwen3-Reranker-4B** | 4B | FP16 | ~4 GB | 32K | Instruction-aware, 100+ languages |
| Vision (lazy-load) | **TBD ~7B VL model** | ~7B | Q4 | ~5 GB | — | Only loaded when scan/image attachment present |

### Memory Budget

| Component | Memory |
|-----------|--------|
| Qwen3.6-27B (Q4) | ~15 GB |
| Qwen3-72B (Q4) | ~40 GB |
| Qwen3-Embedding-8B (FP16) | ~9 GB |
| Qwen3-Reranker-4B (FP16) | ~4 GB |
| Vision model (lazy, Q4) | ~5 GB |
| **Subtotal models** | **~73 GB** |
| KV-cache + vLLM runtime | ~30 GB |
| OS + system overhead | ~10 GB |
| **Total** | **~113 GB** |
| **Buffer** | **~15 GB** |

### Memory Management Rules

1. Vision model is **lazy-loaded** — only activated when a scan/image attachment is detected; otherwise memory stays free.
2. Draft context is hard-limited to **32K tokens** — even though Qwen3-72B supports 128K, mail replies never need more.
3. `--gpu-memory-utilization 0.85` in vLLM — leave headroom for unified memory OS needs.
4. If memory pressure detected: evict vision model first, then reduce KV-cache before OOM.

## Inference Engine

| Decision | Choice | Notes |
|----------|--------|-------|
| Runtime | **vLLM** (≥0.13, cu130 aarch64) | Replaces Ollama; OpenAI-compatible API preserved |
| API interface | OpenAI-compatible `/v1/chat/completions` | Hub code changes minimally (swap base URL) |
| Batching | Continuous batching (PagedAttention) | Enables concurrent classify + draft without blocking |
| Quantization | NVFP4 kernels on Blackwell | Maximum throughput on Tensor Cores |
| Process isolation | Separate vLLM instances per model group | Crash isolation: 27B+embed+rerank / 72B / vision |
| Model load order | 1) 27B + Embedding + Reranker → 2) 72B → 3) Vision (on-demand) | Pre-compute resumes first |

### vLLM Configuration (DGX Spark specific)

```bash
# Classify service (Qwen3.6-27B + embedding + reranker)
vllm serve Qwen/Qwen3.6-27B \
  --port 8001 \
  --gpu-memory-utilization 0.25 \
  --max-model-len 32768 \
  --reasoning-parser qwen3

# Draft service (Qwen3-72B)
vllm serve Qwen/Qwen3-72B \
  --port 8002 \
  --gpu-memory-utilization 0.45 \
  --max-model-len 32768

# Embedding + Reranker via separate lightweight services (sentence-transformers or vLLM embed endpoint)
```

**DGX Spark flags:**
- `TRITON_PTXAS_PATH=/usr/local/cuda/bin/ptxas`
- `VLLM_MARLIN_USE_ATOMIC_ADD=1` (for MoE if used)
- No `--enforce-eager` (throughput loss)

## Batch Strategy: Hybrid Pre-compute + On-demand

### Pre-compute (background, Qwen3.6-27B)

Triggered on mail arrival (push notification or poll):
- Embed mail body + subject (Qwen3-Embedding-8B, 4096d)
- Retrieve + Rerank similar history (Qwen3-Reranker-4B)
- Classify: category, priority, routing suggestion
- Extract actions (deadlines, to-do's, commitments)
- Summarize attachments (text-extraction; vision if scan)

Results stored in DB; available instantly when user opens mail.

### On-demand (user-initiated)

Triggered when user clicks "Generate response" or opens mail without pre-computed draft:
- Draft generation (Qwen3-72B) in detected language + mailbox style
- Thread summarization (if long chain)
- Multiple draft variants (optional, user-selectable)

### Priority Queue

- User-opened mail gets **priority** in the pre-compute queue
- Bulk background pre-compute runs at lower priority
- If mail opened before pre-compute completes: on-demand classify via 27B (~2s), draft available after generation

## Vector Store Changes

| Property | Current | Target |
|----------|---------|--------|
| Embedding model | Qwen3-Embedding-0.6B | Qwen3-Embedding-8B |
| Dimension | `vector(1024)` | **`vector(4096)`** |
| Context length | 8K tokens | 32K tokens |
| Migration | — | Re-embed all indexed chunks |

**Migration approach:** New Alembic migration to alter column type. Background job re-embeds all existing chunks. Old 1024-dim vectors are incompatible — full reindex required.

## Attachment Processing (new capability)

| Attachment type | Processing | Model used |
|-----------------|-----------|------------|
| PDF (text-based) | PyMuPDF → plaintext → feed to 27B/72B | Qwen3.6-27B (summarize) |
| DOCX/XLSX | python-docx/openpyxl → plaintext | Qwen3.6-27B (summarize) |
| Image/scan (PNG, JPG) | Direct to vision model | Vision 7B (lazy-loaded) |
| Unsupported types | Skip with logged warning | N/A |

## Action Extraction (new capability)

Part of the pre-compute classify step (Qwen3.6-27B):

```json
{
  "actions": [
    {"type": "deadline", "description": "Aanleveren voor vrijdag", "due": "2026-07-25"},
    {"type": "todo", "description": "Contract reviewen"},
    {"type": "meeting", "description": "Volgende week bellen"}
  ]
}
```

Actions are stored alongside the suggestion; surfaced in the add-in UI.

## Language Handling

| Scenario | Behavior |
|----------|----------|
| NL inbound mail | Reply in NL (detect from LATEST message) |
| EN inbound mail | Reply in EN |
| FR inbound mail | Reply in FR (72B is multilingual; no dedicated markers needed) |
| Mixed thread | Follow LATEST message language |
| Relationship history | If 10+ prior mails to contact in EN, prefer EN even if this mail is NL |

Language detection (`draft_language.py`) remains the base; 72B's multilingual capability reduces wrong-language incidents significantly vs 14B.

## Infrastructure Changes

| Component | Current (Mac Studio) | Target (DGX Spark) |
|-----------|---------------------|-------------------|
| OS | macOS + Docker Desktop | DGX OS (Ubuntu-based Linux ARM64) |
| Container runtime | Docker Desktop | Native Docker / Podman |
| Inference | Ollama (host process) | vLLM (multiple systemd services) |
| DB | Docker Compose pgvector | Docker Compose pgvector (unchanged) |
| Hub API | Docker container | Docker container (unchanged) |
| Remote access | Tailscale | Tailscale (unchanged) |
| Monitoring | `/health` endpoint | `/health` + Prometheus (vLLM native) |

### Service Topology

```
DGX Spark
├── systemd: vllm-classify (port 8001) — Qwen3.6-27B
├── systemd: vllm-draft (port 8002) — Qwen3-72B
├── systemd: vllm-embed (port 8003) — Qwen3-Embedding-8B + Reranker-4B
├── systemd: vllm-vision (port 8004) — Vision 7B [on-demand]
├── docker: spoqsense-api (port 8000) — FastAPI hub
├── docker: spoqsense-db (port 5432) — PostgreSQL + pgvector
├── systemd: spoqsense-precompute — Background worker (priority queue)
└── tailscale: ts0 — Remote access
```

## Hub API Changes

| Change | Impact | Effort |
|--------|--------|--------|
| Ollama client → OpenAI-compatible client | Swap `base_url` + minor prompt format | Low |
| Dual-model routing (27B classify, 72B draft) | New service layer to route by task | Medium |
| Pre-compute worker + priority queue | New background service + DB state | Medium |
| Embedding dim 1024 → 4096 | Alembic migration + reindex job | Medium |
| Action extraction schema | New DB table + API field | Low |
| Attachment processing pipeline | New service (PyMuPDF + python-docx + vision client) | Medium |

## Performance Targets (revised)

| Metric | Current (Mac Studio) | Target (DGX Spark) |
|--------|---------------------|-------------------|
| Classify latency | 10-15s | **<2s** |
| Draft latency | 30-45s (timeout) | **5-8s** |
| Pre-compute throughput | N/A | **50 mails in <20s** (batched) |
| Embedding throughput | ~100 chunks/min | **1000+ chunks/min** |

## Graceful Degradation

| Failure | Behavior |
|---------|----------|
| 72B service down | "Generate response" unavailable; classify/priority still works |
| 27B service down | On-demand fallback: 72B handles classify (slower, ~5s) |
| Embedding service down | New mails not embedded; existing suggestions still served |
| Vision service down | Image attachments skipped; text attachments still processed |
| Full vLLM crash | Health endpoint returns unhealthy; add-in shows "Hub unavailable" |
| DGX Spark reboot | systemd auto-restart; load order: 27B → 72B → vision |

## Migration Sequence

1. **Hardware setup** — DGX Spark rack, network, DGX OS, Tailscale
2. **vLLM install** — cu130 wheels, model downloads, systemd services
3. **Hub API refactor** — OpenAI-compatible client, dual-model routing
4. **Vector store migration** — pgvector 4096, re-embed all chunks
5. **Pre-compute worker** — Background service + priority queue
6. **Attachment pipeline** — Text extraction + vision integration
7. **Action extraction** — Classify prompt extension + schema + UI
8. **Testing & cutover** — Parallel run, verify latency targets, switch DNS/Tailscale
