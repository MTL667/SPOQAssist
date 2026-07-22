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
        retrieved_snippets: list[str],
        learned_route: tuple[str, str | None] | None,
        include_draft: bool,
    ) -> AnalyzeSignals: ...

    def health(self) -> dict: ...


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
        retrieved_snippets: list[str],
        learned_route: tuple[str, str | None] | None,
        include_draft: bool,
    ) -> AnalyzeSignals:
        text = f"{subject} {body} {sender}".lower()
        if "urgent" in text or "asap" in text:
            priority, confidence = "high", Confidence.HIGH
        elif "fyi" in text or "newsletter" in text:
            priority, confidence = "low", Confidence.LOW
        else:
            priority, confidence = "normal", Confidence.MEDIUM

        category = "action_required"
        if "invoice" in text:
            category = "invoice"
        elif "meeting" in text:
            category = "meeting"

        route_email, route_name = None, None
        if learned_route:
            route_email, route_name = learned_route
            confidence = Confidence.HIGH
        elif "forward" in text or "route" in text:
            route_email, route_name = "desk@contoso.com", "Service Desk"

        why = [{"code": "keyword", "text": f"Matched category signals for {category}."}]
        if retrieved_snippets:
            why.append({"code": "history", "text": "Similar prior outbound style retrieved."})
        if learned_route:
            why.append({"code": "learned_route", "text": "Prior routing correction applied."})

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
                draft = (
                    f"Hi,\n\nThanks for your message regarding “{subject[:80]}”. "
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
        try:
            with httpx.Client(timeout=30.0) as client:
                resp = client.post(
                    f"{self.base}/api/embeddings",
                    json={"model": self.embed_model, "prompt": text[:8000]},
                )
                resp.raise_for_status()
                emb = resp.json().get("embedding") or []
        except httpx.HTTPError as exc:
            logger.info("ollama_embed_failed err_type=%s", type(exc).__name__)
            raise AppError(
                code="INFERENCE_UNAVAILABLE",
                message="Embedding model is unavailable on the hub.",
                status_code=503,
                retryable=True,
            ) from None
        if len(emb) != EMBEDDING_DIM:
            # Pad/truncate to pinned dim for pgvector(1024)
            if len(emb) > EMBEDDING_DIM:
                emb = emb[:EMBEDDING_DIM]
            else:
                emb = emb + [0.0] * (EMBEDDING_DIM - len(emb))
        return [float(x) for x in emb]

    def analyze_fast(
        self,
        *,
        subject: str,
        body: str,
        sender: str,
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
            retrieved_snippets=retrieved_snippets,
            learned_route=learned_route,
            include_draft=False,
        )
        draft = None
        if include_draft and stub.history_status != HistoryStatus.NONE:
            draft = self._generate_draft(subject, body, retrieved_snippets)
            stub.draft = draft
        elif include_draft:
            stub.draft = None
        # Touch rerank model name for ops visibility (ranking applied via retrieve order).
        logger.info("analyze_fast_local rerank_model=%s", self.rerank_model)
        return stub

    def _generate_draft(self, subject: str, body: str, snippets: list[str]) -> str | None:
        prompt = (
            "Write a short professional reply grounded in the style examples. "
            "Do not invent facts.\n"
            f"Subject: {subject[:200]}\n"
            f"Message: {body[:1500]}\n"
            f"Style examples: {' | '.join(s[:200] for s in snippets[:3])}\n"
            "Reply:"
        )
        try:
            with httpx.Client(timeout=30.0) as client:
                resp = client.post(
                    f"{self.base}/api/generate",
                    json={
                        "model": self.instruct_model,
                        "prompt": prompt,
                        "stream": False,
                    },
                )
                resp.raise_for_status()
                return str(resp.json().get("response") or "").strip() or None
        except httpx.HTTPError as exc:
            logger.info("ollama_draft_failed err_type=%s", type(exc).__name__)
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
