"""Local inference clients — stub (CI) or Ollama on Mac Studio (NFR-S1)."""

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

logger = logging.getLogger(__name__)

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
    ) -> AnalyzeSignals: ...

    def health(self) -> dict: ...


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
    ) -> AnalyzeSignals:
        del mailbox_email
        text = f"{subject} {body} {sender}".lower()
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
        category = "action_required"
        if "invoice" in text:
            category = "invoice"
        elif meeting_intent:
            category = "meeting"
        elif forward_intent:
            category = "forward"

        # Routes only from learned edges — never invent demo recipients (e.g. Contoso).
        route_email, route_name = None, None
        if learned_route:
            route_email, route_name = learned_route
            if route_email and "@contoso.com" in route_email.lower():
                route_email, route_name = None, None
            else:
                confidence = Confidence.HIGH

        why = [{"code": "keyword", "text": f"Matched category signals for {category}."}]
        if retrieved_snippets:
            why.append({"code": "history", "text": "Similar prior outbound style retrieved."})
        if route_email:
            why.append({"code": "learned_route", "text": "Prior routing correction applied."})
        elif forward_intent:
            why.append(
                {
                    "code": "route_unknown",
                    "text": "Forward may help, but no learned route exists for this sender yet.",
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
                greet = _display_name_from_email(sender) or "there"
                draft = (
                    f"Hi {greet},\n\nThanks for your message regarding “{subject[:80]}”. "
                    "I will follow up shortly.\n\nBest regards"
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
    ) -> AnalyzeSignals:
        # Fast path: heuristic + retrieved/learned context; draft via instruct when needed.
        # Never send mailbox content to external LLM APIs — only local Ollama.
        stub = StubInferenceClient().analyze_fast(
            subject=subject,
            body=body,
            sender=sender,
            mailbox_email=mailbox_email,
            retrieved_snippets=retrieved_snippets,
            learned_route=learned_route,
            include_draft=False,
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
            )
            stub.draft = draft
        elif include_draft:
            stub.draft = None
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
    ) -> str | None:
        owner = mailbox_email or "the mailbox owner"
        owner_name = _display_name_from_email(mailbox_email) or owner
        counterpart = sender or "the other person"
        counterpart_name = _display_name_from_email(sender) or counterpart
        style = " --- ".join(s[:250] for s in snippets[:3]) or "(none)"
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
            intent_block = "Intent: normal REPLY. Answer helpfully without inventing facts."
        prompt = (
            "You draft an email REPLY that the mailbox owner will send.\n"
            f"Author of the reply (mailbox owner / YOU): {owner_name} <{owner}>\n"
            f"Incoming mail FROM (the person you reply TO): {counterpart_name} <{counterpart}>\n"
            f"Subject: {subject[:200]}\n"
            f"Incoming message:\n{body[:1500]}\n\n"
            f"{intent_block}\n\n"
            "Style examples from the mailbox owner's previously SENT mail "
            "(match tone only; do not reuse as if you are that other person):\n"
            f"{style}\n\n"
            "Hard rules:\n"
            f"1) Write ONLY as {owner_name} ({owner}).\n"
            f"2) Address {counterpart_name} ({counterpart}) — never greet or address {owner_name}.\n"
            "3) Never write from the incoming sender's perspective; never sign as them.\n"
            "4) Do not invent facts, attachments, recipients, or commitments.\n"
            "5) Match the language of the incoming message (e.g. Dutch if Dutch).\n"
            "6) Output only the reply body, no preamble.\n\n"
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
                        "keep_alive": "2m",
                        "options": {
                            "temperature": 0.3,
                            "num_predict": 280,
                            "num_ctx": 4096,
                        },
                    },
                )
                resp.raise_for_status()
                draft = str(resp.json().get("response") or "").strip() or None
                return self._reject_inverted_perspective(
                    draft,
                    mailbox_email=mailbox_email,
                    sender=sender,
                )
        except httpx.TimeoutException:
            logger.info("ollama_draft_timeout_fallback")
            greet = _display_name_from_email(sender) or "there"
            return (
                f"Hi {greet},\n\nThanks for your message — I will look into this and follow up shortly.\n\n"
                "Best regards"
            )
        except httpx.HTTPError as exc:
            logger.info("ollama_draft_failed err_type=%s", type(exc).__name__)
            raise AppError(
                code="INFERENCE_UNAVAILABLE",
                message="Instruct model is unavailable on the hub.",
                status_code=503,
                retryable=True,
            ) from None

    def _reject_inverted_perspective(
        self,
        draft: str | None,
        *,
        mailbox_email: str,
        sender: str,
    ) -> str | None:
        """Drop drafts that greet the mailbox owner or sign as the incoming sender."""
        if not draft:
            return None
        owner_first = (_display_name_from_email(mailbox_email) or "").split(" ")[0].lower()
        sender_first = (_display_name_from_email(sender) or "").split(" ")[0].lower()
        head = draft.strip().splitlines()[0].lower() if draft.strip() else ""
        # e.g. "Hoi Kevin," when Kevin is the mailbox owner
        if owner_first and len(owner_first) >= 3 and re.search(
            rf"\b(hoi|hallo|hi|dear|beste)\s+{re.escape(owner_first)}\b",
            head,
        ):
            logger.info("draft_rejected_greets_owner")
            greet = _display_name_from_email(sender) or "there"
            return (
                f"Hi {greet},\n\nThanks for your message — I will look into this and follow up shortly.\n\n"
                f"Best regards"
            )
        # Signature line looks like the incoming sender
        if sender_first and len(sender_first) >= 3:
            if re.search(
                rf"(?im)^(met vriendelijke groeten|kind regards|best regards|regards).{{0,40}}\b{re.escape(sender_first)}\b",
                draft,
            ) or re.search(rf"(?im)^{re.escape(sender_first)}\s+\w+\s*$", draft):
                logger.info("draft_rejected_signs_as_sender")
                greet = _display_name_from_email(sender) or "there"
                return (
                    f"Hi {greet},\n\nThanks for your message — I will look into this and follow up shortly.\n\n"
                    f"Best regards"
                )
        return draft

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


_client: InferenceClient | None = None


def get_inference_client() -> InferenceClient:
    global _client
    if _client is None:
        mode = get_settings().inference_mode.lower()
        _client = OllamaInferenceClient() if mode == "ollama" else StubInferenceClient()
    return _client


def set_inference_client(client: InferenceClient | None) -> None:
    global _client
    _client = client
