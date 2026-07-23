from enum import StrEnum


class MailboxKind(StrEnum):
    PERSONAL = "personal"
    SHARED = "shared"


class MailboxRole(StrEnum):
    OWNER = "owner"
    SHARED_DELEGATE = "shared_delegate"
    ADMIN = "admin"
    OPS = "ops"


class ConnectionStatus(StrEnum):
    PENDING = "pending"
    CONNECTED = "connected"
    FAILED = "failed"


class Confidence(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class FeedbackOutcome(StrEnum):
    ACCEPT = "accept"
    EDIT = "edit"
    REJECT = "reject"
    REROUTE = "reroute"


class OutboundAction(StrEnum):
    SEND = "send"
    FORWARD = "forward"
    NONE = "none"


class HistoryStatus(StrEnum):
    SUFFICIENT = "sufficient"
    LIMITED = "limited"
    NONE = "none"


class HistoryProfileStatus(StrEnum):
    """Lifecycle of the per-mailbox Sent Items embedding profile."""

    NOT_STARTED = "not_started"
    SYNCING = "syncing"
    READY = "ready"
    FAILED = "failed"


class HistorySyncPhase(StrEnum):
    """Finer-grained sync progress for UI status updates."""

    NOT_STARTED = "not_started"
    FETCHING = "fetching"
    INDEXING = "indexing"
    READY = "ready"
    FAILED = "failed"


class InferenceMode(StrEnum):
    STUB = "stub"
    OLLAMA = "ollama"
    VLLM = "vllm"


class PrecomputeStatus(StrEnum):
    """Pre-compute pipeline state for a message."""

    PENDING = "pending"
    PROCESSING = "processing"
    DONE = "done"
    FAILED = "failed"


class ActionType(StrEnum):
    DEADLINE = "deadline"
    TODO = "todo"
    MEETING = "meeting"
    QUESTION = "question"
