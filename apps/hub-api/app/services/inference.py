"""Local inference clients — stub (CI), Ollama, or vLLM on DGX Spark (NFR-S1)."""

from __future__ import annotations

import logging
import math
import re
from dataclasses import dataclass
from typing import Protocol

import httpx

from app.core.config import get_settings
from app.core.errors import AppError
from app.domain.enums import Confidence, HistoryStatus
from app.services.draft_language import (
    detect_reply_language,
    is_thread_parrot,
    stub_reply_draft,
)
from app.services.thread_split import draft_context_blocks, split_thread_body

logger = logging.getLogger(__name__)

def _resolve_embedding_dim() -> int:
    """Resolve embedding dimension from config — 4096 for vLLM/8B, 1024 for Ollama/0.6B."""
    try:
        settings = get_settings()
        if settings.inference_mode.lower() == "vllm":
            return 4096
    except Exception:
        pass
    return 1024


# Lazily resolved once at first access (avoids import-time settings parse in tests).
_embedding_dim: int | None = None


def get_embedding_dim() -> int:
    global _embedding_dim
    if _embedding_dim is None:
        _embedding_dim = _resolve_embedding_dim()
    return _embedding_dim


# Legacy constant for backward compat — prefer get_embedding_dim() in new code.
EMBEDDING_DIM = 1024


def plain_text_for_embed(text: str, *, max_chars: int = 2000) -> str:
    """Strip HTML/MIME noise so local embedding servers do not crash on mail bodies."""
    cleaned = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", text or "")
    cleaned = re.sub(r"(?s)<[^>]+>", " ", cleaned)
    cleaned = re.sub(r"&\w+;", " ", cleaned)
    # Quoted-printable / MIME soft breaks crash some local embed runtimes when dense.
    cleaned = re.sub(r"=\r?\n", "", cleaned)
    cleaned = re.sub(r"=[0-9A-Fa-f]{2}", " ", cleaned)
    cleaned = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned[:max_chars]


@dataclass
class AnalyzeSignals:
    category: str
    priority: str
    confidence: Confidence
    route_email: str | None
    route_name: str | None
    why: list[dict]
    draft: str | None
    history_status: HistoryStatus
    draft_error: str | None = None


class InferenceClient(Protocol):
    def embed(self, text: str) -> list[float]: ...

    def analyze_fast(
        self,
        *,
        subject: str,
        body: str,
        sender: str,
        mailbox_email: str,
        retrieved_snippets: list[str],
        learned_route: tuple[str, str | None] | None,
        include_draft: bool,
        behavior_summary: str | None = None,
        classification: AnalyzeSignals | None = None,
    ) -> AnalyzeSignals: ...

    def summarize_mailbox_behavior(
        self,
        *,
        mailbox_email: str,
        kind: str,
        chunk_count: int,
        route_lines: list[str],
        sample_snippets: list[str],
    ) -> str: ...

    def health(self) -> dict: ...


def _lang_code_to_name(lang: str) -> str:
    """Map ISO 639-1 language code to full name for prompts."""
    _LANG_MAP = {
        "nl": "Dutch",
        "en": "English",
        "fr": "French",
        "de": "German",
        "es": "Spanish",
        "it": "Italian",
        "pt": "Portuguese",
    }
    return _LANG_MAP.get(lang, f"the same language as the latest message (detected: {lang})")


def _display_name_from_email(email: str) -> str:
    local = (email or "").split("@", 1)[0].strip()
    if not local:
        return ""
    parts = [p for p in re.split(r"[._+-]+", local) if p]
    if not parts:
        return local
    return " ".join(p[:1].upper() + p[1:] for p in parts)


def _hash_embed(text: str, dim: int = EMBEDDING_DIM) -> list[float]:
    """Deterministic pseudo-embedding for stub/tests (dim=1024)."""
    vec = [0.0] * dim
    tokens = re.findall(r"[a-z0-9@._-]+", text.lower())
    if not tokens:
        vec[0] = 1.0
        return vec
    for i, tok in enumerate(tokens):
        h = hash(tok) % dim
        vec[h] += 1.0 + (i % 7) * 0.01
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


class StubInferenceClient:
    def embed(self, text: str) -> list[float]:
        return _hash_embed(text)

    def analyze_fast(
        self,
        *,
        subject: str,
        body: str,
        sender: str,
        mailbox_email: str,
        retrieved_snippets: list[str],
        learned_route: tuple[str, str | None] | None,
        include_draft: bool,
        behavior_summary: str | None = None,
        classification: AnalyzeSignals | None = None,
    ) -> AnalyzeSignals:
        del mailbox_email
        if classification is not None:
            signals = AnalyzeSignals(
                category=classification.category,
                priority=classification.priority,
                confidence=classification.confidence,
                route_email=classification.route_email,
                route_name=classification.route_name,
                why=list(classification.why),
                draft=None,
                history_status=classification.history_status,
            )
            if include_draft and signals.history_status != HistoryStatus.NONE:
                parts = split_thread_body(body)
                greet = _display_name_from_email(sender) or ""
                latest = parts.latest_message.strip() or subject
                lang = detect_reply_language(latest, behavior_summary)
                signals.draft = stub_reply_draft(
                    lang=lang,
                    greet_name=greet,
                    latest_snippet=latest,
                )
            elif include_draft:
                signals.draft = None
            return signals
        parts = split_thread_body(body)
        # Classify on the latest segment so quoted history does not dominate.
        text = f"{subject} {parts.latest_message} {sender}".lower()
        if "urgent" in text or "asap" in text:
            priority, confidence = "high", Confidence.HIGH
        elif "fyi" in text or "newsletter" in text:
            priority, confidence = "low", Confidence.LOW
        else:
            priority, confidence = "normal", Confidence.MEDIUM

        forward_intent = any(
            k in text for k in ("forward", "doorsturen", "please route", "gelieve door")
        )
        meeting_intent = any(
            k in text for k in ("meeting", "call", "afspraak", "uitnodiging", "calendar")
        )

        # Routes only from learned edges — never invent demo recipients (e.g. Contoso).
        route_email, route_name = None, None
        if learned_route:
            route_email, route_name = learned_route
            if route_email and "@contoso.com" in route_email.lower():
                route_email, route_name = None, None
            else:
                confidence = Confidence.HIGH

        # Primary category: never "forward" without a real route (directed mail → reply path).
        category = "action_required"
        if "invoice" in text:
            category = "invoice"
        elif meeting_intent:
            category = "meeting"
        elif forward_intent and route_email:
            category = "forward"

        why = [{"code": "keyword", "text": f"Matched category signals for {category}."}]
        if retrieved_snippets:
            why.append({"code": "history", "text": "Similar prior outbound style retrieved."})
        if route_email:
            why.append({"code": "learned_route", "text": "Prior routing correction applied."})
        elif forward_intent:
            why.append(
                {
                    "code": "route_unknown",
                    "text": "Forward wording detected, but no learned route exists — treat as a reply for the mailbox owner.",
                }
            )
        if meeting_intent or category == "meeting":
            why.append(
                {
                    "code": "meeting_intent",
                    "text": "Meeting/call intent detected — draft may propose next steps (no calendar booking).",
                }
            )

        history_status = (
            HistoryStatus.SUFFICIENT
            if len(retrieved_snippets) >= 2
            else HistoryStatus.LIMITED
            if retrieved_snippets
            else HistoryStatus.NONE
        )

        draft = None
        if include_draft:
            if history_status == HistoryStatus.NONE:
                draft = None
            else:
                greet = _display_name_from_email(sender) or ""
                latest = parts.latest_message.strip() or subject
                lang = detect_reply_language(latest, behavior_summary)
                # Answer the latest ask — never paste lines from quoted thread history.
                draft = stub_reply_draft(
                    lang=lang,
                    greet_name=greet,
                    latest_snippet=latest,
                )
                if parts.split:
                    why.append(
                        {
                            "code": "thread_latest",
                            "text": "Draft answers the latest message; full mail thread used as context only.",
                        }
                    )
                if behavior_summary and behavior_summary.strip():
                    # Testable marker that draft path consumed the cached profile prompt.
                    draft += "\n\n[mailbox-profile-applied]"
                    why.append(
                        {
                            "code": "mailbox_profile",
                            "text": "Draft guided by cached mailbox behavior summary.",
                        }
                    )

        return AnalyzeSignals(
            category=category,
            priority=priority,
            confidence=confidence,
            route_email=route_email,
            route_name=route_name,
            why=why,
            draft=draft,
            history_status=history_status,
        )

    def summarize_mailbox_behavior(
        self,
        *,
        mailbox_email: str,
        kind: str,
        chunk_count: int,
        route_lines: list[str],
        sample_snippets: list[str],
    ) -> str:
        del sample_snippets  # never echo bodies; stub uses counts + routes only
        routes = "; ".join(route_lines[:6]) if route_lines else "(none learned)"
        return (
            f"Mailbox: {mailbox_email} ({kind})\n"
            f"Style: grounded in {chunk_count} indexed Sent chunk(s); "
            "prefers concise, factual replies (stub summary).\n"
            f"Routing: {routes}\n"
            f"History: {chunk_count} chunks indexed."
        )

    def health(self) -> dict:
        return {"status": "ok", "mode": "stub", "embedding_dim": EMBEDDING_DIM}


class OllamaInferenceClient:
    def __init__(self) -> None:
        settings = get_settings()
        self.base = settings.ollama_base_url.rstrip("/")
        self.embed_model = settings.ollama_embed_model
        self.rerank_model = settings.ollama_rerank_model
        self.instruct_model = settings.ollama_instruct_model

    def embed(self, text: str) -> list[float]:
        prompt = plain_text_for_embed(text)
        emb = self._embed_once(prompt or " ")
        if emb is None and len(prompt) > 400:
            emb = self._embed_once(prompt[:400])
        if emb is None:
            raise AppError(
                code="INFERENCE_UNAVAILABLE",
                message="Embedding model is unavailable on the hub.",
                status_code=503,
                retryable=True,
            )
        if len(emb) != EMBEDDING_DIM:
            # Pad/truncate to pinned dim for pgvector(1024)
            if len(emb) > EMBEDDING_DIM:
                emb = emb[:EMBEDDING_DIM]
            else:
                emb = emb + [0.0] * (EMBEDDING_DIM - len(emb))
        return [float(x) for x in emb]

    def _embed_once(self, prompt: str) -> list[float] | None:
        try:
            with httpx.Client(timeout=60.0) as client:
                resp = client.post(
                    f"{self.base}/api/embeddings",
                    json={"model": self.embed_model, "prompt": prompt},
                )
                if resp.status_code >= 400:
                    resp = client.post(
                        f"{self.base}/api/embed",
                        json={"model": self.embed_model, "input": [prompt]},
                    )
                if resp.status_code >= 400:
                    logger.info("ollama_embed_http status=%s", resp.status_code)
                    return None
                data = resp.json()
                emb = data.get("embedding")
                if emb is None and data.get("embeddings"):
                    emb = (data.get("embeddings") or [[]])[0]
                return [float(x) for x in (emb or [])] or None
        except httpx.HTTPError as exc:
            logger.info("ollama_embed_failed err_type=%s", type(exc).__name__)
            return None

    def analyze_fast(
        self,
        *,
        subject: str,
        body: str,
        sender: str,
        mailbox_email: str,
        retrieved_snippets: list[str],
        learned_route: tuple[str, str | None] | None,
        include_draft: bool,
        behavior_summary: str | None = None,
        classification: AnalyzeSignals | None = None,
    ) -> AnalyzeSignals:
        # Fast path: heuristic + retrieved/learned context; draft via instruct when needed.
        # Never send mailbox content to external LLM APIs — only local Ollama.
        stub = classification or StubInferenceClient().analyze_fast(
            subject=subject,
            body=body,
            sender=sender,
            mailbox_email=mailbox_email,
            retrieved_snippets=retrieved_snippets,
            learned_route=learned_route,
            include_draft=False,
            behavior_summary=behavior_summary,
        )
        draft = None
        if include_draft and stub.history_status != HistoryStatus.NONE:
            draft = self._generate_draft(
                subject=subject,
                body=body,
                sender=sender,
                mailbox_email=mailbox_email,
                snippets=retrieved_snippets,
                category=stub.category,
                route_email=stub.route_email,
                behavior_summary=behavior_summary,
            )
            stub.draft = draft
            stub.draft_error = (
                None
                if draft
                else "Draft unavailable — try Generate response again."
            )
            if behavior_summary and behavior_summary.strip():
                stub.why.append(
                    {
                        "code": "mailbox_profile",
                        "text": "Draft guided by cached mailbox behavior summary.",
                    }
                )
        elif include_draft:
            stub.draft = None
            stub.draft_error = None
        # Touch rerank model name for ops visibility (ranking applied via retrieve order).
        logger.info("analyze_fast_local rerank_model=%s", self.rerank_model)
        return stub

    def _generate_draft(
        self,
        *,
        subject: str,
        body: str,
        sender: str,
        mailbox_email: str,
        snippets: list[str],
        category: str,
        route_email: str | None,
        behavior_summary: str | None = None,
    ) -> str | None:
        owner = mailbox_email or "the mailbox owner"
        owner_name = _display_name_from_email(mailbox_email) or owner
        counterpart = sender or "the other person"
        counterpart_name = _display_name_from_email(sender) or counterpart
        parts = split_thread_body(body)
        latest_raw, full_raw = draft_context_blocks(body)
        latest = latest_raw[:2000]
        # Full original body as context (not only the quoted slice after the split).
        full_thread = full_raw
        if len(full_thread) > 8000:
            full_thread = full_thread[:8000] + "\n…[truncated]"
        if not full_thread:
            full_thread = "(none)"
        style = " --- ".join(s[:250] for s in snippets[:3]) or "(none)"
        profile_block = (behavior_summary or "").strip() or "(none cached)"
        lang = detect_reply_language(latest, behavior_summary)
        lang_name = _lang_code_to_name(lang)
        if category == "meeting":
            intent_block = (
                "Intent: MEETING/CALL follow-up. Propose next steps or ask for times. "
                "Do NOT invent a confirmed calendar hold, Teams link, or booked slot."
            )
        elif category == "forward" and route_email:
            intent_block = (
                f"Intent: FORWARD. Write a short reply acknowledging you will forward "
                f"internally to {route_email}. Do not invent other recipients."
            )
        elif category == "forward":
            intent_block = (
                "Intent: possible FORWARD, but no known internal route yet. "
                "Reply politely; ask a clarifying question if needed. Do not invent recipients."
            )
        else:
            intent_block = (
                "Intent: normal REPLY. Answer ONLY the LATEST message. "
                "Use the full mail thread as background context (topic, prior facts); "
                "do not answer older messages and do not repeat prior replies."
            )
        prompt = (
            "You draft an email REPLY that the mailbox owner will send.\n"
            f"Author of the reply (mailbox owner / YOU): {owner_name} <{owner}>\n"
            f"Incoming mail FROM (the person you reply TO): {counterpart_name} <{counterpart}>\n"
            f"Subject: {subject[:200]}\n\n"
            "=== LATEST message to answer (ONLY answer this) ===\n"
            f"{latest or '(empty)'}\n\n"
            "=== Full mail thread (CONTEXT ONLY — understand topic/history; "
            "do NOT answer older parts; do NOT copy prior replies) ===\n"
            f"{full_thread}\n\n"
            f"{intent_block}\n\n"
            "Mailbox owner prompt (cached behavior profile — follow tone/habits; "
            "do not invent facts beyond the latest message + thread context):\n"
            f"{profile_block[:2000]}\n\n"
            "Style examples from the mailbox owner's previously SENT mail "
            "(match tone/length only; NEVER copy their wording verbatim):\n"
            f"{style}\n\n"
            "Hard rules:\n"
            f"1) Write ONLY as {owner_name} ({owner}).\n"
            f"2) Address {counterpart_name} ({counterpart}) — never greet or address {owner_name}.\n"
            "3) Answer ONLY the LATEST message block above.\n"
            "4) Use the full mail thread only as context (who/what/why); never paste prior replies from it.\n"
            "5) Never write from the incoming sender's perspective; never sign as them.\n"
            "6) Do not invent facts, attachments, recipients, or commitments.\n"
            f"7) Write the entire reply in {lang_name} (language of the LATEST message / mailbox habits).\n"
            "8) Prefer the mailbox owner prompt for tone/habits when it conflicts with generic style.\n"
            "9) Output only the reply body, no preamble.\n\n"
            "Reply:\n"
        )
        try:
            # Keep drafts short so the 14B model cannot pin the hub for minutes.
            with httpx.Client(timeout=45.0) as client:
                resp = client.post(
                    f"{self.base}/api/generate",
                    json={
                        "model": self.instruct_model,
                        "prompt": prompt,
                        "stream": False,
                        # qwen3:14b otherwise fills `thinking` and leaves `response` empty.
                        "think": False,
                        "keep_alive": "2m",
                        "options": {
                            "temperature": 0.3,
                            "num_predict": 280,
                            # Room for full-thread context + latest + profile.
                            "num_ctx": 8192,
                        },
                    },
                )
                resp.raise_for_status()
                draft = str(resp.json().get("response") or "").strip() or None
                cleaned = self._reject_inverted_perspective(
                    draft,
                    mailbox_email=mailbox_email,
                    sender=sender,
                )
                cleaned = self._reject_thread_parrot(
                    cleaned,
                    # Parrot check against quoted history + style, not the latest ask.
                    thread_context=parts.thread_context or "",
                    style_snippets=snippets,
                )
                if cleaned:
                    return cleaned
                # No canned stub — UI shows Generate response when draft is absent.
                logger.info("ollama_draft_empty lang=%s", lang)
                return None
        except httpx.TimeoutException:
            logger.info("ollama_draft_timeout lang=%s", lang)
            return None
        except (httpx.HTTPError, httpx.RequestError) as exc:
            # Soft-fail like vLLM — classify must still return 200 without a draft.
            logger.info("ollama_draft_failed err_type=%s", type(exc).__name__)
            return None

    def _reject_thread_parrot(
        self,
        draft: str | None,
        *,
        thread_context: str,
        style_snippets: list[str],
    ) -> str | None:
        """Drop drafts that mostly paste prior thread/style wording."""
        if not (draft or "").strip():
            return None
        if is_thread_parrot(
            draft,
            thread_context=thread_context,
            style_snippets=style_snippets,
        ):
            logger.info(
                "draft_rejected_thread_parrot draft_chars=%s thread_chars=%s",
                len(draft or ""),
                len(thread_context or ""),
            )
            return None
        return draft

    def _reject_inverted_perspective(
        self,
        draft: str | None,
        *,
        mailbox_email: str,
        sender: str,
    ) -> str | None:
        """Drop drafts that greet the mailbox owner or sign as the incoming sender."""
        if not (draft or "").strip():
            return None
        owner_first = (_display_name_from_email(mailbox_email) or "").split(" ")[0].lower()
        sender_first = (_display_name_from_email(sender) or "").split(" ")[0].lower()
        head = draft.strip().splitlines()[0].lower() if draft.strip() else ""
        # e.g. "Hoi Kevin," / "Dag Kevin," when Kevin is the mailbox owner
        if owner_first and len(owner_first) >= 3 and re.search(
            rf"\b(hoi|hallo|hi|dear|beste|dag)\s+{re.escape(owner_first)}\b",
            head,
        ):
            logger.info("draft_rejected_greets_owner")
            return None
        # Signature line looks like the incoming sender
        if sender_first and len(sender_first) >= 3:
            if re.search(
                rf"(?im)^(met vriendelijke groet(?:en)?|kind regards|best regards|regards).{{0,40}}\b{re.escape(sender_first)}\b",
                draft,
            ) or re.search(rf"(?im)^{re.escape(sender_first)}\s+\w+\s*$", draft):
                logger.info("draft_rejected_signs_as_sender")
                return None
        return draft

    def summarize_mailbox_behavior(
        self,
        *,
        mailbox_email: str,
        kind: str,
        chunk_count: int,
        route_lines: list[str],
        sample_snippets: list[str],
    ) -> str:
        routes = "\n".join(f"- {r}" for r in route_lines[:12]) or "- (none)"
        # Truncate samples for the model only — never returned to clients.
        samples = "\n---\n".join(s[:400] for s in sample_snippets[:6]) or "(none)"
        prompt = (
            "Summarize this mailbox owner's email behavior for an internal assistant.\n"
            f"Mailbox: {mailbox_email} ({kind})\n"
            f"Indexed Sent chunks: {chunk_count}\n"
            f"Learned routing patterns:\n{routes}\n\n"
            "Style samples from previously SENT mail (tone only; do not quote long passages):\n"
            f"{samples}\n\n"
            "Write 4–8 short lines covering: typical reply style/tone/language, "
            "how they handle requests, and any forwarding/routing habits.\n"
            "Do not invent recipients, facts, or habits not supported by the inputs.\n"
            "If history is thin, say so. Output plain text only.\n"
        )
        try:
            with httpx.Client(timeout=45.0) as client:
                resp = client.post(
                    f"{self.base}/api/generate",
                    json={
                        "model": self.instruct_model,
                        "prompt": prompt,
                        "stream": False,
                        # qwen3:14b otherwise fills `thinking` and leaves `response` empty.
                        "think": False,
                        "keep_alive": "2m",
                        "options": {
                            "temperature": 0.2,
                            "num_predict": 220,
                            "num_ctx": 4096,
                        },
                    },
                )
                resp.raise_for_status()
                text = str(resp.json().get("response") or "").strip()
                if text:
                    return text
                logger.info("ollama_behavior_summary_empty_response")
                raise AppError(
                    code="INFERENCE_UNAVAILABLE",
                    message="Behavior summary was empty on the hub.",
                    status_code=503,
                    retryable=True,
                )
        except httpx.TimeoutException:
            logger.info("ollama_behavior_summary_timeout")
            raise AppError(
                code="INFERENCE_UNAVAILABLE",
                message="Behavior summary timed out on the hub.",
                status_code=503,
                retryable=True,
            ) from None
        except httpx.HTTPError as exc:
            logger.info("ollama_behavior_summary_failed err_type=%s", type(exc).__name__)
            raise AppError(
                code="INFERENCE_UNAVAILABLE",
                message="Instruct model is unavailable on the hub.",
                status_code=503,
                retryable=True,
            ) from None

    def health(self) -> dict:
        try:
            with httpx.Client(timeout=3.0) as client:
                resp = client.get(f"{self.base}/api/tags")
                ok = resp.status_code == 200
        except httpx.HTTPError:
            ok = False
        return {
            "status": "ok" if ok else "down",
            "mode": "ollama",
            "embedding_dim": EMBEDDING_DIM,
            "embed_model": self.embed_model,
            "rerank_model": self.rerank_model,
            "instruct_model": self.instruct_model,
        }


class VLLMInferenceClient:
    """OpenAI-compatible client for vLLM on DGX Spark — dual-model routing."""

    def __init__(self) -> None:
        settings = get_settings()
        self.classify_url = settings.vllm_classify_url.rstrip("/")
        self.draft_url = settings.vllm_draft_url.rstrip("/")
        self.embed_url = settings.vllm_embed_url.rstrip("/")
        self.classify_model = settings.vllm_classify_model
        self.draft_model = settings.vllm_draft_model
        self.embed_model = settings.vllm_embed_model
        self.draft_timeout = settings.vllm_draft_timeout
        self.classify_timeout = settings.vllm_classify_timeout
        self.embedding_dim = get_embedding_dim()
        self._attachment_context: list[str] = []

    def set_attachment_context(self, summaries: list[str]) -> None:
        """Set attachment summaries to be injected into draft/classify prompts."""
        self._attachment_context = summaries or []

    def embed(self, text: str) -> list[float]:
        dim = self.embedding_dim
        prompt = plain_text_for_embed(text)
        try:
            with httpx.Client(timeout=60.0) as client:
                resp = client.post(
                    f"{self.embed_url}/embeddings",
                    json={"model": self.embed_model, "input": prompt or " "},
                )
                if resp.status_code >= 400:
                    logger.info("vllm_embed_http status=%s body=%s", resp.status_code, resp.text[:200])
                    raise AppError(
                        code="INFERENCE_UNAVAILABLE",
                        message="Embedding model is unavailable on the hub.",
                        status_code=503,
                        retryable=True,
                    )
                data = resp.json()
                try:
                    emb = data["data"][0]["embedding"]
                except (KeyError, IndexError, TypeError) as parse_err:
                    logger.info("vllm_embed_malformed_response keys=%s", list(data.keys()) if isinstance(data, dict) else type(data).__name__)
                    raise AppError(
                        code="INFERENCE_UNAVAILABLE",
                        message="Embedding model returned malformed response.",
                        status_code=503,
                        retryable=True,
                    ) from parse_err
                if len(emb) != dim:
                    if len(emb) > dim:
                        emb = emb[:dim]
                    else:
                        emb = emb + [0.0] * (dim - len(emb))
                return [float(x) for x in emb]
        except httpx.HTTPError as exc:
            logger.info("vllm_embed_failed err_type=%s", type(exc).__name__)
            raise AppError(
                code="INFERENCE_UNAVAILABLE",
                message="Embedding model is unavailable on the hub.",
                status_code=503,
                retryable=True,
            ) from None

    def analyze_fast(
        self,
        *,
        subject: str,
        body: str,
        sender: str,
        mailbox_email: str,
        retrieved_snippets: list[str],
        learned_route: tuple[str, str | None] | None,
        include_draft: bool,
        behavior_summary: str | None = None,
        classification: AnalyzeSignals | None = None,
    ) -> AnalyzeSignals:
        # Classify via 27B (fast); draft via 72B (on-demand). Skip classify when cached.
        if classification is not None:
            signals = AnalyzeSignals(
                category=classification.category,
                priority=classification.priority,
                confidence=classification.confidence,
                route_email=classification.route_email,
                route_name=classification.route_name,
                why=list(classification.why),
                draft=None,
                history_status=classification.history_status,
            )
        else:
            signals = self._classify_via_27b(
                subject=subject,
                body=body,
                sender=sender,
                mailbox_email=mailbox_email,
                retrieved_snippets=retrieved_snippets,
                learned_route=learned_route,
                behavior_summary=behavior_summary,
            )
            if signals is None:
                # Fallback to stub heuristics if 27B is down
                logger.info("vllm_classify_fallback_to_stub reason=27b_unavailable")
                signals = StubInferenceClient().analyze_fast(
                    subject=subject,
                    body=body,
                    sender=sender,
                    mailbox_email=mailbox_email,
                    retrieved_snippets=retrieved_snippets,
                    learned_route=learned_route,
                    include_draft=False,
                    behavior_summary=behavior_summary,
                )

        if include_draft and signals.history_status != HistoryStatus.NONE:
            draft, draft_error = self._generate_draft(
                subject=subject,
                body=body,
                sender=sender,
                mailbox_email=mailbox_email,
                snippets=retrieved_snippets,
                category=signals.category,
                route_email=signals.route_email,
                behavior_summary=behavior_summary,
            )
            signals.draft = draft
            signals.draft_error = draft_error
            if behavior_summary and behavior_summary.strip():
                signals.why.append(
                    {
                        "code": "mailbox_profile",
                        "text": "Draft guided by cached mailbox behavior summary.",
                    }
                )
        elif include_draft:
            signals.draft = None
            signals.draft_error = None
        return signals

    def _classify_via_27b(
        self,
        *,
        subject: str,
        body: str,
        sender: str,
        mailbox_email: str,
        retrieved_snippets: list[str],
        learned_route: tuple[str, str | None] | None,
        behavior_summary: str | None = None,
    ) -> AnalyzeSignals | None:
        """Call 27B classify model for category/priority/routing. Returns None if unavailable."""
        import json as _json

        parts = split_thread_body(body)
        latest = parts.latest_message[:1200]

        route_context = ""
        if learned_route:
            route_context = f"\nPreviously learned route: {learned_route[0]} ({learned_route[1] or 'unnamed'})"

        history_context = ""
        if retrieved_snippets:
            history_context = "\nSimilar prior mails from this mailbox:\n" + "\n---\n".join(
                s[:200] for s in retrieved_snippets[:2]
            )

        system_msg = (
            "You are an email classification assistant. Analyze the email and return a JSON object with:\n"
            '- "category": one of "action_required", "forward", "invoice", "meeting", "fyi", "spam"\n'
            '- "priority": one of "high", "normal", "low"\n'
            '- "confidence": one of "high", "medium", "low"\n'
            '- "route_email": email address to forward to (null if not forwarding)\n'
            '- "route_name": display name for route (null if not forwarding)\n'
            '- "why": array of {code, text} explaining your reasoning (max 3 items)\n'
            "Output ONLY valid JSON. No markdown fences, no explanation."
        )
        attachment_context = ""
        if self._attachment_context:
            attachment_context = "\nAttachment summaries:\n" + "\n".join(
                f"- {s}" for s in self._attachment_context[:5]
            )

        user_msg = (
            f"Mailbox: {mailbox_email}\n"
            f"From: {sender}\n"
            f"Subject: {subject[:200]}\n\n"
            f"Latest message:\n{latest}\n"
            f"{route_context}"
            f"{history_context}"
            f"{attachment_context}"
        )

        try:
            with httpx.Client(timeout=self.classify_timeout) as client:
                resp = client.post(
                    f"{self.classify_url}/chat/completions",
                    json={
                        "model": self.classify_model,
                        "messages": [
                            {"role": "system", "content": system_msg},
                            {"role": "user", "content": user_msg},
                        ],
                        "temperature": 0.1,
                        "max_tokens": 180,
                        "chat_template_kwargs": {"enable_thinking": False},
                    },
                )
                if resp.status_code >= 400:
                    logger.info("vllm_classify_http_error status=%s", resp.status_code)
                    return None

                data = resp.json()
                content = (
                    data.get("choices", [{}])[0]
                    .get("message", {})
                    .get("content", "")
                    .strip()
                )
                return self._parse_classify_response(
                    content,
                    learned_route=learned_route,
                    retrieved_snippets=retrieved_snippets,
                )
        except httpx.TimeoutException:
            logger.info("vllm_classify_timeout")
            return None
        except Exception as exc:
            logger.info("vllm_classify_failed err=%s", type(exc).__name__)
            return None

    def _parse_classify_response(
        self,
        raw: str,
        *,
        learned_route: tuple[str, str | None] | None,
        retrieved_snippets: list[str],
    ) -> AnalyzeSignals | None:
        """Parse 27B classify JSON response into AnalyzeSignals."""
        import json as _json

        # Strip markdown fences if present
        cleaned = re.sub(r"```(?:json)?\s*", "", raw).strip()
        cleaned = re.sub(r"```\s*$", "", cleaned).strip()

        try:
            result = _json.loads(cleaned)
        except _json.JSONDecodeError:
            # Try to extract JSON object
            match = re.search(r"\{.*\}", cleaned, re.DOTALL)
            if match:
                try:
                    result = _json.loads(match.group(0))
                except _json.JSONDecodeError:
                    logger.info("vllm_classify_parse_failed")
                    return None
            else:
                return None

        if not isinstance(result, dict):
            return None

        # Extract fields with safe defaults
        category = str(result.get("category", "action_required")).lower()
        valid_categories = {"action_required", "forward", "invoice", "meeting", "fyi", "spam"}
        if category not in valid_categories:
            category = "action_required"

        priority = str(result.get("priority", "normal")).lower()
        if priority not in {"high", "normal", "low"}:
            priority = "normal"

        conf_str = str(result.get("confidence", "medium")).lower()
        confidence = {"high": Confidence.HIGH, "medium": Confidence.MEDIUM, "low": Confidence.LOW}.get(
            conf_str, Confidence.MEDIUM
        )

        route_email = result.get("route_email") or None
        route_name = result.get("route_name") or None

        # Override with learned route if model didn't suggest one but learned exists
        if not route_email and learned_route:
            route_email, route_name = learned_route

        why_raw = result.get("why", [])
        why = []
        if isinstance(why_raw, list):
            for item in why_raw[:3]:
                if isinstance(item, dict) and "text" in item:
                    why.append({"code": item.get("code", "model"), "text": str(item["text"])[:200]})
        if not why:
            why = [{"code": "model_classify", "text": f"27B classified as {category}/{priority}."}]

        history_status = (
            HistoryStatus.SUFFICIENT
            if len(retrieved_snippets) >= 2
            else HistoryStatus.LIMITED
            if retrieved_snippets
            else HistoryStatus.NONE
        )

        return AnalyzeSignals(
            category=category,
            priority=priority,
            confidence=confidence,
            route_email=route_email,
            route_name=route_name,
            why=why,
            draft=None,
            history_status=history_status,
        )

    def _generate_draft(
        self,
        *,
        subject: str,
        body: str,
        sender: str,
        mailbox_email: str,
        snippets: list[str],
        category: str,
        route_email: str | None,
        behavior_summary: str | None = None,
    ) -> tuple[str | None, str | None]:
        """Return (draft, draft_error). Soft-fail never raises for analyze."""
        owner = mailbox_email or "the mailbox owner"
        owner_name = _display_name_from_email(mailbox_email) or owner
        counterpart = sender or "the other person"
        counterpart_name = _display_name_from_email(sender) or counterpart
        parts = split_thread_body(body)
        latest_raw, full_raw = draft_context_blocks(body)
        latest = latest_raw[:1500]
        full_thread = full_raw
        if len(full_thread) > 2500:
            full_thread = full_thread[:2500] + "\n…[truncated]"
        if not full_thread:
            full_thread = "(none)"
        style = " --- ".join(s[:220] for s in snippets[:3]) or "(none)"
        profile_block = (behavior_summary or "").strip() or "(none cached)"
        lang = detect_reply_language(latest, behavior_summary)
        lang_name = _lang_code_to_name(lang)
        if category == "meeting":
            intent_block = (
                "Intent: MEETING/CALL follow-up. Propose next steps or ask for times. "
                "Do NOT invent a confirmed calendar hold, Teams link, or booked slot."
            )
        elif category == "forward" and route_email:
            intent_block = (
                f"Intent: FORWARD. Write a short reply acknowledging you will forward "
                f"internally to {route_email}. Do not invent other recipients."
            )
        elif category == "forward":
            intent_block = (
                "Intent: possible FORWARD, but no known internal route yet. "
                "Reply politely; ask a clarifying question if needed. Do not invent recipients."
            )
        else:
            intent_block = (
                "Intent: normal REPLY. Answer ONLY the LATEST message. "
                "Use the full mail thread as background context (topic, prior facts); "
                "do not answer older messages and do not repeat prior replies."
            )
        system_msg = (
            "You draft an email REPLY that the mailbox owner will send.\n"
            f"Author of the reply (mailbox owner / YOU): {owner_name} <{owner}>\n"
            f"Incoming mail FROM (the person you reply TO): {counterpart_name} <{counterpart}>\n\n"
            "Hard rules:\n"
            f"1) Write ONLY as {owner_name} ({owner}).\n"
            f"2) Address {counterpart_name} ({counterpart}) — never greet or address {owner_name}.\n"
            "3) Answer ONLY the LATEST message block.\n"
            "4) Use the full mail thread only as context; never paste prior replies from it.\n"
            "5) Never write from the incoming sender's perspective; never sign as them.\n"
            "6) Do not invent facts, attachments, recipients, or commitments.\n"
            f"7) Write the entire reply in {lang_name} (language of the LATEST message / mailbox habits).\n"
            "8) Prefer the mailbox owner prompt for tone/habits when it conflicts with generic style.\n"
            "9) Output only the reply body, no preamble.\n"
        )
        # Include attachment summaries if provided
        attachment_block = ""
        if hasattr(self, '_attachment_context') and self._attachment_context:
            attachment_block = (
                "\n=== Attachment summaries (context for your reply) ===\n"
                + "\n".join(f"- {s}" for s in self._attachment_context[:5])
                + "\n"
            )

        user_msg = (
            f"Subject: {subject[:200]}\n\n"
            "=== LATEST message to answer (ONLY answer this) ===\n"
            f"{latest or '(empty)'}\n\n"
            "=== Full mail thread (CONTEXT ONLY — understand topic/history; "
            "do NOT answer older parts; do NOT copy prior replies) ===\n"
            f"{full_thread}\n\n"
            f"{attachment_block}"
            f"{intent_block}\n\n"
            "Mailbox owner prompt (cached behavior profile — follow tone/habits; "
            "do not invent facts beyond the latest message + thread context):\n"
            f"{profile_block[:1200]}\n\n"
            "Style examples from the mailbox owner's previously SENT mail "
            "(match tone/length only; NEVER copy their wording verbatim):\n"
            f"{style}\n\n"
            "Reply:\n"
        )
        try:
            with httpx.Client(timeout=self.draft_timeout) as client:
                resp = client.post(
                    f"{self.draft_url}/chat/completions",
                    json={
                        "model": self.draft_model,
                        "messages": [
                            {"role": "system", "content": system_msg},
                            {"role": "user", "content": user_msg},
                        ],
                        "temperature": 0.3,
                        "max_tokens": 220,
                        # Qwen3 thinking burns the whole timeout before any reply text.
                        "chat_template_kwargs": {"enable_thinking": False},
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                content = (
                    data.get("choices", [{}])[0]
                    .get("message", {})
                    .get("content", "")
                )
                if not isinstance(content, str):
                    logger.info("vllm_draft_malformed_content")
                    return None, "Draft model returned empty or malformed content."
                draft = content.strip() or None
                if not draft:
                    logger.info("vllm_draft_empty lang=%s", lang)
                    return None, "Draft model returned empty content."
                after_perspective = self._reject_inverted_perspective(
                    draft,
                    mailbox_email=mailbox_email,
                    sender=sender,
                )
                if after_perspective is None:
                    return None, "Draft rejected: inverted perspective (filtered)."
                cleaned = self._reject_thread_parrot(
                    after_perspective,
                    thread_context=parts.thread_context or "",
                    style_snippets=snippets,
                )
                if cleaned is None:
                    return None, "Draft rejected: too similar to thread (filtered)."
                return cleaned, None
        except httpx.TimeoutException:
            logger.info("vllm_draft_timeout lang=%s model=%s", lang, self.draft_model)
            return None, "Draft timed out — try Generate response again."
        except httpx.HTTPError as exc:
            # Soft-fail: analyze stays 200 with draft=null (Generate response retry).
            logger.info("vllm_draft_failed err_type=%s", type(exc).__name__)
            return None, "Draft model unavailable — try Generate response again."
        except httpx.RequestError as exc:
            logger.info("vllm_draft_transport_failed err_type=%s", type(exc).__name__)
            return None, "Draft model unavailable — try Generate response again."
        except (TypeError, ValueError, AttributeError, KeyError, IndexError) as exc:
            logger.info("vllm_draft_malformed err_type=%s", type(exc).__name__)
            return None, "Draft model returned empty or malformed content."
        except Exception as exc:
            logger.info("vllm_draft_unexpected err_type=%s", type(exc).__name__)
            return None, "Draft unavailable — try Generate response again."

    def _reject_thread_parrot(
        self,
        draft: str | None,
        *,
        thread_context: str,
        style_snippets: list[str],
    ) -> str | None:
        if not (draft or "").strip():
            return None
        if is_thread_parrot(
            draft,
            thread_context=thread_context,
            style_snippets=style_snippets,
        ):
            logger.info(
                "draft_rejected_thread_parrot draft_chars=%s thread_chars=%s",
                len(draft or ""),
                len(thread_context or ""),
            )
            return None
        return draft

    def _reject_inverted_perspective(
        self,
        draft: str | None,
        *,
        mailbox_email: str,
        sender: str,
    ) -> str | None:
        if not (draft or "").strip():
            return None
        owner_first = (_display_name_from_email(mailbox_email) or "").split(" ")[0].lower()
        sender_first = (_display_name_from_email(sender) or "").split(" ")[0].lower()
        head = draft.strip().splitlines()[0].lower() if draft.strip() else ""
        if owner_first and len(owner_first) >= 3 and re.search(
            rf"\b(hoi|hallo|hi|dear|beste|dag)\s+{re.escape(owner_first)}\b",
            head,
        ):
            logger.info("draft_rejected_greets_owner")
            return None
        if sender_first and len(sender_first) >= 3:
            if re.search(
                rf"(?im)^(met vriendelijke groet(?:en)?|kind regards|best regards|regards).{{0,40}}\b{re.escape(sender_first)}\b",
                draft,
            ) or re.search(rf"(?im)^{re.escape(sender_first)}\s+\w+\s*$", draft):
                logger.info("draft_rejected_signs_as_sender")
                return None
        return draft

    def summarize_mailbox_behavior(
        self,
        *,
        mailbox_email: str,
        kind: str,
        chunk_count: int,
        route_lines: list[str],
        sample_snippets: list[str],
    ) -> str:
        routes = "\n".join(f"- {r}" for r in route_lines[:12]) or "- (none)"
        samples = "\n---\n".join(s[:400] for s in sample_snippets[:6]) or "(none)"
        system_msg = (
            "You summarize a mailbox owner's email behavior for an internal assistant. "
            "Write 4–8 short lines covering: typical reply style/tone/language, "
            "how they handle requests, and any forwarding/routing habits. "
            "Do not invent recipients, facts, or habits not supported by the inputs. "
            "If history is thin, say so. Output plain text only."
        )
        user_msg = (
            f"Mailbox: {mailbox_email} ({kind})\n"
            f"Indexed Sent chunks: {chunk_count}\n"
            f"Learned routing patterns:\n{routes}\n\n"
            "Style samples from previously SENT mail (tone only; do not quote long passages):\n"
            f"{samples}\n"
        )
        try:
            with httpx.Client(timeout=self.classify_timeout) as client:
                resp = client.post(
                    f"{self.classify_url}/chat/completions",
                    json={
                        "model": self.classify_model,
                        "messages": [
                            {"role": "system", "content": system_msg},
                            {"role": "user", "content": user_msg},
                        ],
                        "temperature": 0.2,
                        "max_tokens": 256,
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                text = (
                    data.get("choices", [{}])[0]
                    .get("message", {})
                    .get("content", "")
                    .strip()
                )
                if text:
                    return text
                logger.info("vllm_behavior_summary_empty_response")
                raise AppError(
                    code="INFERENCE_UNAVAILABLE",
                    message="Behavior summary was empty on the hub.",
                    status_code=503,
                    retryable=True,
                )
        except httpx.TimeoutException:
            logger.info("vllm_behavior_summary_timeout")
            raise AppError(
                code="INFERENCE_UNAVAILABLE",
                message="Behavior summary timed out on the hub.",
                status_code=503,
                retryable=True,
            ) from None
        except httpx.HTTPError as exc:
            logger.info("vllm_behavior_summary_failed err_type=%s", type(exc).__name__)
            raise AppError(
                code="INFERENCE_UNAVAILABLE",
                message="Classify model is unavailable on the hub.",
                status_code=503,
                retryable=True,
            ) from None

    def health(self) -> dict:
        settings = get_settings()
        vision_url = getattr(settings, "vllm_vision_url", None)

        statuses = {}
        for name, url in [
            ("classify", self.classify_url),
            ("draft", self.draft_url),
            ("embed", self.embed_url),
        ]:
            try:
                with httpx.Client(timeout=3.0) as client:
                    resp = client.get(f"{url}/health")
                    if resp.status_code == 200:
                        statuses[name] = "ok"
                    else:
                        # Fallback to /models if /health not available
                        resp2 = client.get(f"{url}/models")
                        statuses[name] = "ok" if resp2.status_code == 200 else "down"
            except httpx.HTTPError:
                statuses[name] = "down"

        # Vision model: idle (not loaded), ready, or down
        if vision_url:
            try:
                with httpx.Client(timeout=3.0) as client:
                    resp = client.get(f"{vision_url.rstrip('/')}/health")
                    statuses["vision"] = "ready" if resp.status_code == 200 else "down"
            except httpx.HTTPError:
                statuses["vision"] = "idle"  # Not started = idle (lazy-load)
        else:
            statuses["vision"] = "idle"

        core_statuses = [statuses[k] for k in ("classify", "draft", "embed")]
        if all(v == "ok" for v in core_statuses):
            overall = "ok"
        elif all(v == "down" for v in core_statuses):
            overall = "down"
        else:
            overall = "degraded"

        return {
            "status": overall,
            "mode": "vllm",
            "embedding_dim": self.embedding_dim,
            "services": statuses,
            "classify_model": self.classify_model,
            "draft_model": self.draft_model,
            "embed_model": self.embed_model,
        }


_client: InferenceClient | None = None


def get_inference_client() -> InferenceClient:
    global _client
    if _client is None:
        mode = get_settings().inference_mode.lower()
        if mode == "vllm":
            _client = VLLMInferenceClient()
        elif mode == "ollama":
            _client = OllamaInferenceClient()
        else:
            _client = StubInferenceClient()
    return _client


def set_inference_client(client: InferenceClient | None) -> None:
    global _client
    _client = client
