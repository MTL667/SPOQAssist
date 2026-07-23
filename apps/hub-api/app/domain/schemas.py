from __future__ import annotations

from pydantic import BaseModel, Field

from app.domain.enums import (
    Confidence,
    ConnectionStatus,
    FeedbackOutcome,
    HistoryProfileStatus,
    HistoryStatus,
    HistorySyncPhase,
    MailboxKind,
    MailboxRole,
    OutboundAction,
)


class MailboxProfileOut(BaseModel):
    id: str
    tenant_id: str
    email: str
    kind: MailboxKind
    owner_oid: str
    connection_status: ConnectionStatus
    connection_error: str | None = None
    graph_mailbox_id: str | None = None
    history_status: HistoryProfileStatus = HistoryProfileStatus.NOT_STARTED
    last_history_sync_at: str | None = None
    history_sync_error: str | None = None
    history_chunk_count: int | None = None
    history_sync_phase: HistorySyncPhase = HistorySyncPhase.NOT_STARTED
    history_messages_fetched: int = 0
    history_messages_target: int = 0
    history_sync_started_at: str | None = None


class ConnectMailboxRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    kind: MailboxKind


class ConnectMailboxResponse(BaseModel):
    mailbox_profile: MailboxProfileOut
    role: MailboxRole


class ContentStubOut(BaseModel):
    mailbox_profile_id: str
    kind: MailboxKind
    allowed: bool = True
    note: str = "Entitlement gate passed; mail read arrives in Story 2.2."


class OpsConnectorConfigIn(BaseModel):
    tenant_id: str
    graph_scopes: str = Field(default="", max_length=1024)
    notes: str = Field(default="", max_length=1024)


class OpsConnectorConfigOut(BaseModel):
    tenant_id: str
    graph_scopes: str
    notes: str


class RouteOut(BaseModel):
    display_name: str | None = None
    email: str
    graph_id: str | None = None


class WhyItem(BaseModel):
    code: str
    text: str


class AttachmentWarning(BaseModel):
    name: str
    reason: str


class ActionItem(BaseModel):
    id: str | None = None
    action_type: str  # deadline | todo | meeting | question
    description: str
    due_date: str | None = None
    dismissed: bool = False


class AttachmentSummary(BaseModel):
    filename: str
    mime_type: str
    summary: str
    page_count: int | None = None
    is_scan: bool = False


class SuggestionOut(BaseModel):
    suggestion_id: str
    mailbox_profile_id: str
    message_id: str
    category: str
    priority: str
    confidence: Confidence
    suggested_route: RouteOut | None = None
    draft: str | None = None
    why: list[WhyItem] = Field(default_factory=list)
    history_status: HistoryStatus = HistoryStatus.NONE
    attachment_warnings: list[AttachmentWarning] = Field(default_factory=list)
    attachment_summaries: list[AttachmentSummary] = Field(default_factory=list)
    actions: list[str] = Field(default_factory=list)
    extracted_actions: list[ActionItem] = Field(default_factory=list)
    precompute_status: str | None = None
    timings: dict[str, int] = Field(default_factory=dict)


class AnalyzeRequest(BaseModel):
    # Outlook itemIds often contain '/' — keep in body, not path, to avoid route 404s.
    message_id: str = Field(min_length=1, max_length=2048)
    include_draft: bool = True
    subject: str | None = None
    body: str | None = None
    sender: str | None = None
    # Optional client-provided attachment metadata (Office.js); hub also reads via Graph when configured
    attachment_names: list[str] = Field(default_factory=list)


class FeedbackIn(BaseModel):
    suggestion_id: str
    outcome: FeedbackOutcome
    edited_draft: str | None = None
    corrected_route_email: str | None = None
    corrected_route_name: str | None = None
    teach: bool = False


class FeedbackOut(BaseModel):
    feedback_id: str
    suggestion_id: str
    outcome: FeedbackOutcome
    audit_id: str


class ConfirmOutboundIn(BaseModel):
    suggestion_id: str
    idempotency_key: str = Field(min_length=8, max_length=128)
    action: OutboundAction
    recipients: list[str] = Field(min_length=1)
    subject: str | None = None
    body: str | None = None
    ai_assisted: bool = True


class ConfirmOutboundOut(BaseModel):
    status: str
    graph_message_id: str | None = None
    idempotent_replay: bool = False
    ai_disclosure_applied: bool = False


class IndexRequest(BaseModel):
    items: list[dict] = Field(default_factory=list)
    # each: {message_id, text} — no full bodies in logs


class SyncIndexRequest(BaseModel):
    max_messages: int = Field(default=3000, ge=1, le=3000)
    # False = start background sync and return immediately (Outlook open path).
    wait: bool = True


class IndexResponse(BaseModel):
    mailbox_profile_id: str
    indexed_count: int
    embedding_dim: int | None = None  # Resolved dynamically via get_embedding_dim()
    total_chunks: int | None = None
    history_status: HistoryProfileStatus = HistoryProfileStatus.NOT_STARTED
    last_history_sync_at: str | None = None
    history_sync_error: str | None = None
    started: bool = True
    history_sync_phase: HistorySyncPhase = HistorySyncPhase.NOT_STARTED
    history_messages_fetched: int = 0
    history_messages_target: int = 0
    history_sync_started_at: str | None = None


class SharedAiSettingsIn(BaseModel):
    enabled: bool = True
    auto_analyze: bool = True
    default_forward_hint: str | None = None
    notes: str = ""


class SharedAiSettingsOut(BaseModel):
    mailbox_profile_id: str
    enabled: bool
    auto_analyze: bool
    default_forward_hint: str | None = None
    notes: str


class RetentionPolicyIn(BaseModel):
    retain_days: int = Field(ge=1, le=3650, default=365)
    purge_audit_with_indexes: bool = False


class RetentionPolicyOut(BaseModel):
    mailbox_profile_id: str
    retain_days: int
    purge_audit_with_indexes: bool


class RetentionRunOut(BaseModel):
    mailbox_profile_id: str
    purged_chunks: int
    purged_suggestions: int
    purged_audit: int


class LearnedRouteOut(BaseModel):
    pattern_key: str
    route_email: str
    route_name: str | None = None
    weight: float = 1.0


class BehaviorSummaryOut(BaseModel):
    text: str | None = None
    status: str = "ok"  # ok | empty | error | skipped
    error: str | None = None


class ProfileInspectOut(BaseModel):
    id: str
    email: str
    kind: MailboxKind
    connection_status: ConnectionStatus
    connection_error: str | None = None
    history_status: HistoryProfileStatus = HistoryProfileStatus.NOT_STARTED
    last_history_sync_at: str | None = None
    history_sync_error: str | None = None
    history_chunk_count: int = 0
    indexed_message_count: int = 0
    history_sync_phase: HistorySyncPhase = HistorySyncPhase.NOT_STARTED
    history_messages_fetched: int = 0
    history_messages_target: int = 0
    routes: list[LearnedRouteOut] = Field(default_factory=list)
    behavior_summary: BehaviorSummaryOut = Field(default_factory=BehaviorSummaryOut)
