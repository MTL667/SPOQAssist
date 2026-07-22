from __future__ import annotations

import logging
import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.models import RoutingEdge

logger = logging.getLogger(__name__)


def pattern_key_from_sender(sender: str) -> str:
    return re.sub(r"\s+", "", sender.strip().lower())[:512]


def apply_routing_correction(
    db: Session,
    *,
    mailbox_profile_id: str,
    pattern_key: str,
    route_email: str,
    route_name: str | None,
) -> RoutingEdge:
    """Shared-mailbox learning cycle (FR29) — scoped to profile only (FR30)."""
    stmt = select(RoutingEdge).where(
        RoutingEdge.mailbox_profile_id == mailbox_profile_id,
        RoutingEdge.pattern_key == pattern_key,
    )
    edge = db.execute(stmt).scalar_one_or_none()
    if edge is None:
        edge = RoutingEdge(
            mailbox_profile_id=mailbox_profile_id,
            pattern_key=pattern_key,
            route_email=route_email.lower(),
            route_name=route_name,
            weight=1.0,
        )
        db.add(edge)
    else:
        edge.route_email = route_email.lower()
        edge.route_name = route_name
        edge.weight = float(edge.weight) + 1.0
    db.commit()
    db.refresh(edge)
    logger.info(
        "routing_edge_upserted mailbox_profile_id=%s weight=%s",
        mailbox_profile_id,
        edge.weight,
    )
    return edge
