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


class InferenceMode(StrEnum):
    STUB = "stub"
    OLLAMA = "ollama"
