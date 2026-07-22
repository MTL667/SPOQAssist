import logging
import sys

from app.core.config import get_settings

# Never log mailbox content or auth secrets (architecture pattern).
FORBIDDEN_LOG_KEYS = frozenset(
    {
        "subject",
        "body",
        "draft",
        "message_body",
        "email_body",
        "content",
        "authorization",
        "access_token",
        "refresh_token",
        "bearer",
        "token",
        "id_token",
        "client_secret",
        "password",
    }
)


def configure_logging() -> None:
    settings = get_settings()
    level = getattr(logging, settings.spoq_log_level.upper(), logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        stream=sys.stdout,
        force=True,
    )
