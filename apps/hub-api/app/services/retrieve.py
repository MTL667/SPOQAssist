from __future__ import annotations

import json
import math

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.models import MailChunk, RoutingEdge
from app.services.inference import InferenceClient


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(x * x for x in b)) or 1.0
    return dot / (na * nb)


def retrieve_similar(
    db: Session,
    *,
    mailbox_profile_id: str,
    query_text: str,
    client: InferenceClient,
    limit: int = 5,
) -> list[str]:
    """Return chunk texts for this profile only — never crosses mailbox_profile_id."""
    q = client.embed(query_text)
    rows = list(
        db.execute(
            select(MailChunk).where(MailChunk.mailbox_profile_id == mailbox_profile_id)
        ).scalars()
    )
    scored: list[tuple[float, str]] = []
    for row in rows:
        try:
            emb = json.loads(row.embedding_json)
        except json.JSONDecodeError:
            continue
        if not isinstance(emb, list):
            continue
        scored.append((_cosine(q, [float(x) for x in emb]), row.chunk_text))
    scored.sort(key=lambda t: t[0], reverse=True)
    return [text for score, text in scored[:limit] if score > 0]


def lookup_learned_route(
    db: Session, *, mailbox_profile_id: str, pattern_key: str
) -> tuple[str, str | None] | None:
    stmt = select(RoutingEdge).where(
        RoutingEdge.mailbox_profile_id == mailbox_profile_id,
        RoutingEdge.pattern_key == pattern_key,
    )
    edge = db.execute(stmt).scalar_one_or_none()
    if edge is None:
        return None
    return edge.route_email, edge.route_name
