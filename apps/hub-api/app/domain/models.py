from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class MailboxProfile(Base):
    __tablename__ = "mailbox_profiles"
    __table_args__ = (UniqueConstraint("tenant_id", "email", name="uq_mailbox_profiles_tenant_email"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    email: Mapped[str] = mapped_column(String(320))
    kind: Mapped[str] = mapped_column(String(32))
    owner_oid: Mapped[str] = mapped_column(String(64), index=True)
    graph_mailbox_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    connection_status: Mapped[str] = mapped_column(String(32), default="pending")
    connection_error: Mapped[str | None] = mapped_column(String(512), nullable=True)
    # Sent Items embedding profile lifecycle (RAG style index — not a LoRA).
    history_status: Mapped[str] = mapped_column(String(32), default="not_started")
    history_sync_error: Mapped[str | None] = mapped_column(String(512), nullable=True)
    history_sync_started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_history_sync_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Mid-sync progress for poll-based UI (phase + message counts).
    history_sync_phase: Mapped[str] = mapped_column(String(32), default="not_started")
    history_messages_fetched: Mapped[int] = mapped_column(Integer, default=0)
    history_messages_target: Mapped[int] = mapped_column(Integer, default=0)
    # Cached persona / behavior prompt for draft generation (not LoRA).
    behavior_summary_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    behavior_summary_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    entitlements: Mapped[list[MailboxEntitlement]] = relationship(
        back_populates="mailbox_profile", cascade="all, delete-orphan"
    )


class MailboxEntitlement(Base):
    __tablename__ = "mailbox_entitlements"
    __table_args__ = (
        UniqueConstraint(
            "mailbox_profile_id",
            "principal_oid",
            name="uq_mailbox_entitlements_profile_principal",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    mailbox_profile_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("mailbox_profiles.id", ondelete="CASCADE"), index=True
    )
    principal_oid: Mapped[str] = mapped_column(String(64), index=True)
    role: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    mailbox_profile: Mapped[MailboxProfile] = relationship(back_populates="entitlements")


class OpsConnectorConfig(Base):
    __tablename__ = "ops_connector_configs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    graph_scopes: Mapped[str] = mapped_column(String(1024), default="")
    notes: Mapped[str] = mapped_column(String(1024), default="")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )


class SharedAiSettings(Base):
    """Admin-configurable AI settings — shared mailboxes only (FR4)."""

    __tablename__ = "shared_ai_settings"

    mailbox_profile_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("mailbox_profiles.id", ondelete="CASCADE"), primary_key=True
    )
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    auto_analyze: Mapped[bool] = mapped_column(Boolean, default=True)
    default_forward_hint: Mapped[str | None] = mapped_column(String(320), nullable=True)
    notes: Mapped[str] = mapped_column(String(1024), default="")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )


class Suggestion(Base):
    __tablename__ = "suggestions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    mailbox_profile_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("mailbox_profiles.id", ondelete="CASCADE"), index=True
    )
    message_id: Mapped[str] = mapped_column(String(256), index=True)
    sender: Mapped[str] = mapped_column(String(320), default="")
    category: Mapped[str] = mapped_column(String(128), default="")
    priority: Mapped[str] = mapped_column(String(64), default="normal")
    confidence: Mapped[str] = mapped_column(String(32), default="medium")
    suggested_route_email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    suggested_route_name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    draft: Mapped[str | None] = mapped_column(Text, nullable=True)
    why_json: Mapped[str] = mapped_column(Text, default="[]")
    history_status: Mapped[str] = mapped_column(String(32), default="none")
    attachment_warnings_json: Mapped[str] = mapped_column(Text, default="[]")
    created_by_oid: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class FeedbackEvent(Base):
    __tablename__ = "feedback_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    suggestion_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("suggestions.id", ondelete="CASCADE"), index=True
    )
    mailbox_profile_id: Mapped[str] = mapped_column(String(36), index=True)
    outcome: Mapped[str] = mapped_column(String(32))
    edited_draft: Mapped[str | None] = mapped_column(Text, nullable=True)
    corrected_route_email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    teach: Mapped[bool] = mapped_column(Boolean, default=False)
    actor_oid: Mapped[str] = mapped_column(String(64), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    mailbox_profile_id: Mapped[str] = mapped_column(String(36), index=True)
    suggestion_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    decision: Mapped[str] = mapped_column(String(64))
    actor_oid: Mapped[str] = mapped_column(String(64), index=True)
    detail: Mapped[str] = mapped_column(String(1024), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class OutboundIdempotency(Base):
    __tablename__ = "outbound_idempotency"
    __table_args__ = (
        UniqueConstraint("mailbox_profile_id", "idempotency_key", name="uq_outbound_idempotency"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    mailbox_profile_id: Mapped[str] = mapped_column(String(36), index=True)
    idempotency_key: Mapped[str] = mapped_column(String(128))
    suggestion_id: Mapped[str] = mapped_column(String(36))
    action: Mapped[str] = mapped_column(String(32))
    request_fingerprint: Mapped[str] = mapped_column(String(128), default="")
    graph_message_id: Mapped[str | None] = mapped_column(String(256), nullable=True)
    actor_oid: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class MailChunk(Base):
    """Historical sent/forwarded chunk with native pgvector embedding.

    - `embedding_vec`: native pgvector column for fast cosine search (primary)
    - `embedding_json`: TEXT fallback for SQLite/test mode and backward compat
    - `embedding_dim`: tracks dimensionality (1024 Ollama, 4096 vLLM)

    Chunks with mismatched dim are skipped during retrieval and eligible for
    re-embedding via the reembed management command.
    """

    __tablename__ = "mail_chunks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    mailbox_profile_id: Mapped[str] = mapped_column(String(36), index=True)
    source_message_id: Mapped[str] = mapped_column(String(256), index=True)
    chunk_text: Mapped[str] = mapped_column(Text)
    embedding_json: Mapped[str] = mapped_column(Text, default="[]")
    embedding_dim: Mapped[int] = mapped_column(Integer, default=1024)
    # Native pgvector column — populated alongside embedding_json for fast retrieval.
    # Column created via schema_ensure (not in create_all for SQLite compat).
    # embedding_vec: vector(4096) — added by ensure_pgvector_column()
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class RoutingEdge(Base):
    """Shared-mailbox routing knowledge (graph-as-table). Never from personal leakage."""

    __tablename__ = "routing_edges"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    mailbox_profile_id: Mapped[str] = mapped_column(String(36), index=True)
    pattern_key: Mapped[str] = mapped_column(String(512), index=True)
    route_email: Mapped[str] = mapped_column(String(320))
    route_name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    weight: Mapped[float] = mapped_column(Float, default=1.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )


class RetentionPolicy(Base):
    __tablename__ = "retention_policies"

    mailbox_profile_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("mailbox_profiles.id", ondelete="CASCADE"), primary_key=True
    )
    retain_days: Mapped[int] = mapped_column(Integer, default=365)
    purge_audit_with_indexes: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )


class PrecomputeJob(Base):
    """Pre-compute pipeline state per message — classify, embed, extract actions in background."""

    __tablename__ = "precompute_jobs"
    __table_args__ = (
        UniqueConstraint("mailbox_profile_id", "message_id", name="uq_precompute_jobs_profile_msg"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    mailbox_profile_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("mailbox_profiles.id", ondelete="CASCADE"), index=True
    )
    message_id: Mapped[str] = mapped_column(String(256), index=True)
    status: Mapped[str] = mapped_column(String(32), default="pending")
    priority: Mapped[int] = mapped_column(Integer, default=0)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(String(512), nullable=True)
    suggestion_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )


class ExtractedAction(Base):
    """Structured actions extracted from mail content (deadlines, todos, meetings, questions)."""

    __tablename__ = "extracted_actions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    suggestion_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("suggestions.id", ondelete="CASCADE"), index=True
    )
    mailbox_profile_id: Mapped[str] = mapped_column(String(36), index=True)
    message_id: Mapped[str] = mapped_column(String(256), index=True)
    action_type: Mapped[str] = mapped_column(String(32))
    description: Mapped[str] = mapped_column(Text)
    due_date: Mapped[str | None] = mapped_column(String(32), nullable=True)
    dismissed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
