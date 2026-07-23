---
stepsCompleted: [1, 2]
inputDocuments: []
session_topic: 'Opschalen SpoqSense AI-stack op Nvidia DGX Spark (128GB Blackwell) — grotere modellen, betere drafts, nieuwe analyse-capabilities'
session_goals: 'Bepalen welke modellen, architectuur en features optimaal zijn voor de DGX Spark; vervanging Mac Studio 48GB + Qwen3 14B'
selected_approach: 'ai-recommended'
techniques_used: ['First Principles Thinking', 'Morphological Analysis', 'Chaos Engineering']
ideas_generated: []
context_file: ''
---

## Session Overview

**Topic:** Opschalen SpoqSense AI-stack op Nvidia DGX Spark
**Goals:** Betere modellen, slimmere classificatie, nieuwe capabilities — hardware plafond verschuift van 48GB Mac Studio naar 128GB Blackwell

### Hardware Context

**Was:** Mac Studio 48 GB unified (Apple Silicon) — Qwen3 14B was het plafond
**Wordt:** Nvidia DGX Spark — 128 GB unified, Blackwell Tensor Cores, 1 PFLOP FP4, tot 200B inference / 70B fine-tune

### Session Setup

Pragmatische technische brainstorm. Kevin wil concrete opties voor model-upgrade en nieuwe features.

## Technique Selection

**Approach:** AI-Recommended Techniques
**Analysis Context:** Hardware-upgrade van 48GB naar 128GB Blackwell; focus op model-kwaliteit en nieuwe capabilities

**Recommended Techniques:**

- **First Principles Thinking:** Strip Mac Studio-era aannames weg, herbouw vanuit fundamentele SpoqSense-behoeften
- **Morphological Analysis:** Systematische matrix van modellen × architecturen × features × resources
- **Chaos Engineering:** Stress-test topkandidaten op edge cases en risico's

**AI Rationale:** De constraint-shift (48→128GB, Apple→Blackwell) maakt legacy-aannames ongeldig. First Principles voorkomt dat we gewoon "een groter model" kiezen zonder na te denken over wat écht nodig is. Morphological Analysis brengt combinatorische mogelijkheden in beeld. Chaos Engineering voorkomt dat we een configuratie kiezen die in productie faalt.

## Technique Execution: First Principles Thinking

### Fundamentele Inzichten

**Kernbeperking Mac Studio-era:** Snelheid. Zelfs na profielcache was analyse van 1 mail te traag voor goede UX.

**First Principles — wat SpoqSense fundamenteel moet doen:**
1. Classificeren — wat is dit voor mail
2. Stijl matchen — hoe reageert de eigenaar normaal
3. Drafts genereren — antwoord produceren
4. Routing — wie moet dit krijgen
5. **Prioriteit bepalen** — op basis van bredere context (nieuw)
6. **Bijlages begrijpen** — PDF's, documenten (nieuw)
7. **Acties extraheren** — deadlines, to-do's, beloftes (nieuw)

**Positionering:** Copilot-niveau mail-assistent, volledig on-prem, op eigen data.

**Architectuurbeslissing:** Multi-model stack (snel classificatie-model + diep draft-model + embedding + reranker)

### Gekozen Stack

| Rol | Model | Params | Geheugen (Q4) | Context |
|-----|-------|--------|---------------|---------|
| Snelle classificatie | Qwen3.6-27B | 27B dense | ~15 GB | 262K |
| Diepe drafts & analyse | Qwen3-72B | 72B dense | ~40 GB | 128K |
| Embedding | Qwen3-Embedding-8B | 8B | ~9 GB (FP16) | 32K |
| Reranker | Qwen3-Reranker-4B | 4B | ~4 GB (FP16) | 32K |
| **Totaal modellen** | | | **~68 GB** | |
| KV-cache + runtime | | | ~30 GB | |
| OS + overhead | | | ~10 GB | |
| **Grand total** | | | **~108 / 128 GB** | |

### Verwachte verbeteringen vs. Mac Studio

| Aspect | Mac Studio (48 GB) | DGX Spark (128 GB) |
|--------|-------------------|-------------------|
| Instruct-model | Qwen3 14B | Qwen3.6-27B + Qwen3-72B |
| Classify latency | ~10-15s | <2s |
| Draft latency | ~30-45s (timeout) | ~5-8s |
| Context window | ~8K tokens | 128-262K tokens |
| Embedding | 0.6B | 8B (13× groter) |
| Reranker | 0.6B | 4B (7× groter) |
| Bijlages | ❌ | ✅ |
| Acties extraheren | ❌ | ✅ |
| Batch pre-compute | ❌ (te traag) | ✅ |
| Multi-draft opties | ❌ | ✅ |

### Nieuwe capabilities

1. Proactieve suggesties — inbox pre-analyseren bij binnenkomst
2. Meerdere draft-varianten (formeel/informeel)
3. Bijlage-samenvatting → context voor draft
4. Actie-extractie (deadlines, to-do's, beloftes)
5. Intelligente prioriteit (afzender-relatie + inhoud + urgentie)
6. Lange thread-begrip (262K = volledige mailgeschiedenis in één pass)
7. Fine-tuning op eigen stijl (later, DGX Spark kan tot 70B fine-tunen)

## Technique Execution: Morphological Analysis

### Dimensie-matrix — gekozen configuratie

| Dimensie | Keuze | Rationale |
|----------|-------|-----------|
| Classify-model | Qwen3.6-27B (dense) | Snel (<2s), 262K context, nieuwste generatie |
| Draft-model | Qwen3-72B (dense) | Diep, nuance in NL, complexe threads |
| Inference engine | **vLLM** (cu130, sm_121) | OpenAI-compatible API, continuous batching, NVFP4, PagedAttention |
| Batch strategie | **Hybride** | Pre-compute triage (27B bij binnenkomst); draft on-demand (72B bij openen) |
| Embedding | Qwen3-Embedding-8B @ **4096 dim** | Maximale retrieval-kwaliteit; re-embed bij migratie |
| Reranker | Qwen3-Reranker-4B | Sweet spot kwaliteit/snelheid, 32K context |
| Bijlage-aanpak | **Hybrid** | Tekst-extractie voor PDF/docx + vision-model voor scans/afbeeldingen |

### Geheugenbudget (definitief)

| Component | Geheugen |
|-----------|----------|
| Qwen3.6-27B (Q4) | ~15 GB |
| Qwen3-72B (Q4) | ~40 GB |
| Qwen3-Embedding-8B (FP16) | ~9 GB |
| Qwen3-Reranker-4B (FP16) | ~4 GB |
| Vision-model 7B (Q4) | ~5 GB |
| **Subtotaal modellen** | **~73 GB** |
| KV-cache + vLLM runtime | ~30 GB |
| OS + overhead | ~10 GB |
| **Totaal** | **~113 / 128 GB** |
| **Buffer** | **~15 GB** |

### Architectuur-flow (definitief)

```
Mail binnenkomst (push/poll)
     │
     ▼ PRE-COMPUTE (achtergrond, Qwen3.6-27B)
┌─────────────────────────────────────────┐
│  Embed (Qwen3-Embedding-8B, 4096d)     │
│  Retrieve + Rerank (Qwen3-Reranker-4B) │
│  Classify + Prioriteit + Routing       │
│  Acties extraheren                      │
│  Bijlage-samenvatting (tekst/vision)   │
└─────────────────────────────────────────┘
     │
     ▼ Gebruiker opent mail → triage INSTANT klaar
     │
     ▼ ON-DEMAND (bij "Generate response")
┌─────────────────────────────────────────┐
│  Qwen3-72B → Draft in juiste taal/stijl│
│  + Thread samenvatting                  │
│  + Meerdere varianten (optioneel)       │
└─────────────────────────────────────────┘
     │
     ▼
   Outlook add-in → Review → Accept/Edit → Send
```

### Migratie-impact

| Onderdeel | Wijziging |
|-----------|-----------|
| Inference engine | Ollama → vLLM (OpenAI-compatible, minimale API-wijziging) |
| Vector store | pgvector(1024) → pgvector(4096), re-embed all |
| OS | macOS (Docker) → DGX OS (Linux ARM64, native vLLM) |
| Modellen | 1 model (14B) → 5 modellen (27B + 72B + 8B embed + 4B rerank + 7B vision) |
| Hub API | Ollama client → OpenAI-compatible client (vLLM endpoint) |
| Batch worker | Nieuw: achtergrond pre-compute service |

## Technique Execution: Chaos Engineering

### Stress-test resultaten & mitigaties

**Scenario 1: Geheugen onder druk (~113/128 GB)**

| Risico | Mitigatie |
|--------|-----------|
| KV-cache explodeert bij mega-thread | Hard context-limiet: max 32K tokens voor draft (72B) |
| Alle modellen tegelijk actief | Vision-model alleen on-demand laden (spaart ~5 GB) |
| Concurrent draft-requests | vLLM PagedAttention + gpu-memory-utilization 0.85 |

**Scenario 2: Latency — bulk inbox**

| Risico | Mitigatie |
|--------|-----------|
| 50 mails tegelijk, pre-compute achter | vLLM continuous batching → ~15-20s hele inbox |
| Gebruiker opent mail vóór pre-compute klaar | **Priority queue** — geopende mail krijgt voorrang |
| Race condition pre-compute vs on-demand | UI toont "analyseren..." → instant zodra klaar |

**Scenario 3: Model-kwaliteit — taal**

| Risico | Mitigatie |
|--------|-----------|
| Model antwoordt in verkeerde taal | Taaldetectie uit LATEST message (bestaande draft_language.py) |
| Frans niet ondersteund | 72B is multilingual — FR gratis mee, geen markers nodig |
| Relatie-taal mismatch | History-based: "ik mail altijd in EN met Jean" → default EN |
| Mixed-language threads | Volg LATEST; 72B kan subtiel schakelen |

**Scenario 4: Infrastructuur — vLLM crasht**

| Risico | Mitigatie |
|--------|-----------|
| OOM-kill → alles weg | Separate vLLM instances per model-groep |
| Welk model eerst laden? | Volgorde: 27B + embed + rerank → 72B → vision |
| 72B down | Graceful degradation: "Generate response niet beschikbaar" |
| DGX reboot | Auto-restart via systemd; health-check endpoint |

### Robuustheid-beslissingen

1. Vision-model = lazy-load (alleen bij scan/afbeelding-bijlage)
2. Draft context hard gelimiteerd op 32K tokens
3. Priority queue voor user-initiated requests
4. Separate vLLM processes per model-groep (crash-isolatie)
5. Taaldetectie volgt inkomende mail, niet profiel/mailbox-default
6. Geen canned fallbacks — liever "niet beschikbaar" dan een leugen
