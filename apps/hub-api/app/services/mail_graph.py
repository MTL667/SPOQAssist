"""Microsoft Graph mail connector — tokens/secrets stay on the hub (Story 1.4)."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol
from urllib.parse import quote
from zoneinfo import ZoneInfo

import httpx

from app.core.config import Settings, get_settings
from app.core.errors import AppError
from app.domain.enums import MailboxKind
from app.services.scheduling import BusyInterval

logger = logging.getLogger(__name__)

AI_DISCLOSURE_FOOTER = (
    "\n\n—\nThis message was prepared with assistance from SpoqSense (company AI)."
)
_BRUSSELS = ZoneInfo("Europe/Brussels")


@dataclass(frozen=True)
class GraphMailboxInfo:
    graph_mailbox_id: str
    email: str
    display_name: str | None = None


@dataclass(frozen=True)
class GraphMessage:
    message_id: str
    subject: str
    body: str
    sender: str
    attachment_names: list[str] = field(default_factory=list)
    attachment_sizes: list[int] = field(default_factory=list)
    to_recipients: list[str] = field(default_factory=list)
    cc_recipients: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class GraphSendResult:
    graph_message_id: str


@dataclass(frozen=True)
class GraphEventResult:
    graph_event_id: str


def _mailbox_root(
    *,
    mailbox_kind: MailboxKind,
    mailbox_email: str,
    graph_mailbox_id: str | None,
) -> str:
    if mailbox_kind == MailboxKind.PERSONAL:
        return "https://graph.microsoft.com/v1.0/me"
    key = graph_mailbox_id or mailbox_email
    return f"https://graph.microsoft.com/v1.0/users/{quote(key, safe='')}"


class MailGraphClient(Protocol):
    def connect_mailbox(
        self,
        *,
        user_assertion: str,
        tenant_id: str,
        email: str,
        kind: MailboxKind,
    ) -> GraphMailboxInfo: ...

    def get_message(
        self,
        *,
        user_assertion: str,
        tenant_id: str,
        message_id: str,
        mailbox_kind: MailboxKind,
        mailbox_email: str,
        graph_mailbox_id: str | None,
    ) -> GraphMessage: ...

    def send_mail(
        self,
        *,
        user_assertion: str,
        tenant_id: str,
        recipients: list[str],
        subject: str,
        body: str,
        mailbox_kind: MailboxKind,
        mailbox_email: str,
        graph_mailbox_id: str | None,
    ) -> GraphSendResult: ...

    def forward_mail(
        self,
        *,
        user_assertion: str,
        tenant_id: str,
        message_id: str,
        recipients: list[str],
        comment: str,
        mailbox_kind: MailboxKind,
        mailbox_email: str,
        graph_mailbox_id: str | None,
    ) -> GraphSendResult: ...

    def list_sent_messages(
        self,
        *,
        user_assertion: str,
        tenant_id: str,
        mailbox_kind: MailboxKind,
        mailbox_email: str,
        graph_mailbox_id: str | None,
        max_messages: int = 100,
        on_progress: Callable[[int], None] | None = None,
    ) -> list[GraphMessage]: ...

    def get_calendar_busy(
        self,
        *,
        user_assertion: str,
        tenant_id: str,
        mailbox_kind: MailboxKind,
        mailbox_email: str,
        graph_mailbox_id: str | None,
        start_iso: str,
        end_iso: str,
    ) -> list[BusyInterval]: ...

    def create_calendar_event(
        self,
        *,
        user_assertion: str,
        tenant_id: str,
        mailbox_kind: MailboxKind,
        mailbox_email: str,
        graph_mailbox_id: str | None,
        subject: str,
        start_iso: str,
        end_iso: str,
        attendees: list[str],
        body: str | None = None,
    ) -> GraphEventResult: ...


class StubMailGraphClient:
    """Dev/test connector — no network; never stores client-side secrets."""

    def __init__(self) -> None:
        self.send_calls: list[dict] = []
        self.forward_calls: list[dict] = []
        self.create_event_calls: list[dict] = []
        self.get_busy_calls: list[dict] = []
        # Optional per-message recipient overrides for scheduling tests.
        self.message_recipients: dict[str, dict[str, list[str]]] = {}
        # Test flags
        self.stub_busy_ranges: bool = False
        self.stub_calendar_consent_fail: bool = False

    def connect_mailbox(
        self,
        *,
        user_assertion: str,
        tenant_id: str,
        email: str,
        kind: MailboxKind,
    ) -> GraphMailboxInfo:
        del user_assertion, tenant_id
        normalized = email.strip().lower()
        if normalized.endswith("@consent-required.example"):
            raise AppError(
                code="CONSENT_REQUIRED",
                message="Microsoft Graph admin or user consent is required for this mailbox.",
                status_code=403,
                retryable=False,
            )
        if normalized.endswith("@bad-scopes.example"):
            raise AppError(
                code="BAD_SCOPES",
                message="Configured Graph scopes are insufficient for this mailbox.",
                status_code=403,
                retryable=False,
            )
        if normalized.endswith("@connector-fail.example"):
            raise AppError(
                code="CONNECTOR_FAILURE",
                message="Graph connector failed while verifying the mailbox.",
                status_code=502,
                retryable=True,
            )
        prefix = "shared" if kind == MailboxKind.SHARED else "personal"
        return GraphMailboxInfo(
            graph_mailbox_id=f"{prefix}:{normalized}",
            email=normalized,
            display_name=normalized.split("@")[0],
        )

    def get_message(
        self,
        *,
        user_assertion: str,
        tenant_id: str,
        message_id: str,
        mailbox_kind: MailboxKind = MailboxKind.PERSONAL,
        mailbox_email: str = "",
        graph_mailbox_id: str | None = None,
    ) -> GraphMessage:
        del user_assertion, tenant_id, mailbox_kind, mailbox_email, graph_mailbox_id
        recip = self.message_recipients.get(message_id) or {}
        return GraphMessage(
            message_id=message_id,
            subject=f"Stub subject {message_id}",
            body="Stub body for analysis.",
            sender="sender@contoso.com",
            attachment_names=[],
            attachment_sizes=[],
            to_recipients=list(recip.get("to") or []),
            cc_recipients=list(recip.get("cc") or []),
        )

    def send_mail(
        self,
        *,
        user_assertion: str,
        tenant_id: str,
        recipients: list[str],
        subject: str,
        body: str,
        mailbox_kind: MailboxKind = MailboxKind.PERSONAL,
        mailbox_email: str = "",
        graph_mailbox_id: str | None = None,
    ) -> GraphSendResult:
        del user_assertion, tenant_id, mailbox_kind, mailbox_email, graph_mailbox_id
        self.send_calls.append({"recipients": recipients, "subject": subject, "body": body})
        return GraphSendResult(graph_message_id=f"sent-{len(self.send_calls)}")

    def forward_mail(
        self,
        *,
        user_assertion: str,
        tenant_id: str,
        message_id: str,
        recipients: list[str],
        comment: str,
        mailbox_kind: MailboxKind = MailboxKind.PERSONAL,
        mailbox_email: str = "",
        graph_mailbox_id: str | None = None,
    ) -> GraphSendResult:
        del user_assertion, tenant_id, mailbox_kind, mailbox_email, graph_mailbox_id
        self.forward_calls.append(
            {"message_id": message_id, "recipients": recipients, "comment": comment}
        )
        return GraphSendResult(graph_message_id=f"fwd-{len(self.forward_calls)}")

    def list_sent_messages(
        self,
        *,
        user_assertion: str,
        tenant_id: str,
        mailbox_kind: MailboxKind = MailboxKind.PERSONAL,
        mailbox_email: str = "",
        graph_mailbox_id: str | None = None,
        max_messages: int = 100,
        on_progress: Callable[[int], None] | None = None,
    ) -> list[GraphMessage]:
        del user_assertion, tenant_id, mailbox_kind, graph_mailbox_id
        if on_progress is not None:
            try:
                on_progress(0)
            except Exception:
                logger.info("graph_list_sent_progress_callback_failed")
        sender = mailbox_email or "me@contoso.com"
        samples = [
            (
                "stub-sent-1",
                "Re: invoice",
                "Thanks for sending the invoice. I have processed it and will confirm shortly.",
            ),
            (
                "stub-sent-2",
                "Re: schedule",
                "Happy to schedule a call next week — please share a couple of slots.",
            ),
            (
                "stub-sent-3",
                "Re: update",
                "Thanks for the update. I have noted this on our side and will follow up.",
            ),
        ]
        out = [
            GraphMessage(
                message_id=mid,
                subject=subj,
                body=body,
                sender=sender,
            )
            for mid, subj, body in samples[: max(0, max_messages)]
        ]
        if on_progress is not None:
            on_progress(len(out))
        return out

    def _calendar_consent_trap(self, mailbox_email: str) -> None:
        normalized = (mailbox_email or "").strip().lower()
        if self.stub_calendar_consent_fail or normalized.endswith(
            "@calendar-consent.example"
        ):
            raise AppError(
                code="CONSENT_REQUIRED",
                message="Microsoft Graph calendar consent is required.",
                status_code=403,
                retryable=False,
            )
        if normalized.endswith("@calendar-bad-scopes.example"):
            raise AppError(
                code="BAD_SCOPES",
                message="Configured Graph calendar scopes are insufficient.",
                status_code=403,
                retryable=False,
            )

    def get_calendar_busy(
        self,
        *,
        user_assertion: str,
        tenant_id: str,
        mailbox_kind: MailboxKind = MailboxKind.PERSONAL,
        mailbox_email: str = "",
        graph_mailbox_id: str | None = None,
        start_iso: str,
        end_iso: str,
    ) -> list[BusyInterval]:
        del user_assertion, tenant_id, mailbox_kind, graph_mailbox_id
        self.get_busy_calls.append(
            {
                "mailbox_email": mailbox_email,
                "start_iso": start_iso,
                "end_iso": end_iso,
            }
        )
        self._calendar_consent_trap(mailbox_email)
        normalized = (mailbox_email or "").strip().lower()
        if self.stub_busy_ranges or "busy-august" in normalized:
            # All-day busy for August 2026 (Europe/Brussels).
            start = datetime(2026, 8, 1, 0, 0, tzinfo=_BRUSSELS)
            end = datetime(2026, 9, 1, 0, 0, tzinfo=_BRUSSELS)
            return [BusyInterval(start=start, end=end)]
        return []

    def create_calendar_event(
        self,
        *,
        user_assertion: str,
        tenant_id: str,
        mailbox_kind: MailboxKind = MailboxKind.PERSONAL,
        mailbox_email: str = "",
        graph_mailbox_id: str | None = None,
        subject: str,
        start_iso: str,
        end_iso: str,
        attendees: list[str],
        body: str | None = None,
    ) -> GraphEventResult:
        del user_assertion, tenant_id, mailbox_kind, graph_mailbox_id
        self._calendar_consent_trap(mailbox_email)
        self.create_event_calls.append(
            {
                "mailbox_email": mailbox_email,
                "subject": subject,
                "start_iso": start_iso,
                "end_iso": end_iso,
                "attendees": list(attendees),
                "body": body,
            }
        )
        return GraphEventResult(graph_event_id=f"stub-event-{len(self.create_event_calls)}")


class OboMailGraphClient:
    """Confidential-client OBO → Graph. Client secret never leaves the hub."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()

    def _acquire_obo_token(self, *, user_assertion: str, tenant_id: str) -> str:
        try:
            import msal  # type: ignore[import-untyped]
        except ImportError as exc:  # pragma: no cover
            raise AppError(
                code="CONNECTOR_FAILURE",
                message="MSAL is not installed on the hub.",
                status_code=503,
                retryable=True,
            ) from exc

        if not self._settings.entra_client_id or not self._settings.entra_client_secret:
            raise AppError(
                code="AUTH_MISCONFIGURED",
                message="Hub Graph connector credentials are not configured.",
                status_code=503,
                retryable=True,
            )

        app = msal.ConfidentialClientApplication(
            self._settings.entra_client_id,
            authority=f"https://login.microsoftonline.com/{tenant_id}",
            client_credential=self._settings.entra_client_secret,
        )
        scopes = [
            s.strip() for s in self._settings.graph_scopes.split(",") if s.strip()
        ] or ["https://graph.microsoft.com/Mail.Read"]
        result = app.acquire_token_on_behalf_of(user_assertion, scopes=scopes)
        if "access_token" not in result:
            error = result.get("error", "unknown")
            desc = str(result.get("error_description", ""))
            logger.info("graph_obo_failed error=%s", error)
            if "consent" in desc.lower() or error == "invalid_grant":
                raise AppError(
                    code="CONSENT_REQUIRED",
                    message="Microsoft Graph consent is required.",
                    status_code=403,
                    retryable=False,
                )
            if "scope" in desc.lower():
                raise AppError(
                    code="BAD_SCOPES",
                    message="Graph scopes are insufficient or not consented.",
                    status_code=403,
                    retryable=False,
                )
            raise AppError(
                code="CONNECTOR_FAILURE",
                message="Failed to acquire Graph token on behalf of the user.",
                status_code=502,
                retryable=True,
            )
        return str(result["access_token"])

    def connect_mailbox(
        self,
        *,
        user_assertion: str,
        tenant_id: str,
        email: str,
        kind: MailboxKind,
    ) -> GraphMailboxInfo:
        token = self._acquire_obo_token(user_assertion=user_assertion, tenant_id=tenant_id)
        headers = {"Authorization": f"Bearer {token}"}
        try:
            with httpx.Client(timeout=20.0) as client:
                if kind == MailboxKind.PERSONAL:
                    resp = client.get("https://graph.microsoft.com/v1.0/me", headers=headers)
                else:
                    resp = client.get(
                        f"https://graph.microsoft.com/v1.0/users/{quote(email, safe='')}",
                        headers=headers,
                    )
                    if resp.status_code < 400:
                        # Prove mail access, not only directory resolve.
                        uid = str(resp.json().get("id") or email)
                        probe = client.get(
                            f"https://graph.microsoft.com/v1.0/users/{quote(uid, safe='')}/mailFolders/inbox",
                            headers=headers,
                            params={"$select": "id"},
                        )
                        if probe.status_code in (401, 403):
                            raise AppError(
                                code="CONSENT_REQUIRED",
                                message="Shared mailbox mail access denied — check Mail.Read.Shared / delegate rights.",
                                status_code=403,
                                retryable=False,
                            )
                        if probe.status_code >= 400:
                            raise AppError(
                                code="CONNECTOR_FAILURE",
                                message="Could not verify shared mailbox mail access.",
                                status_code=502,
                                retryable=True,
                            )
        except AppError:
            raise
        except httpx.HTTPError:
            logger.info("graph_http_failed kind=%s", kind.value)
            raise AppError(
                code="CONNECTOR_FAILURE",
                message="Graph connector failed while verifying the mailbox.",
                status_code=502,
                retryable=True,
            ) from None

        if resp.status_code in (401, 403):
            raise AppError(
                code="CONSENT_REQUIRED",
                message="Graph denied access — check consent and mailbox permissions.",
                status_code=403,
                retryable=False,
            )
        if resp.status_code >= 400:
            logger.info("graph_verify_failed status=%s kind=%s", resp.status_code, kind.value)
            raise AppError(
                code="CONNECTOR_FAILURE",
                message="Graph could not verify this mailbox.",
                status_code=502,
                retryable=True,
            )

        data = resp.json()
        resolved_email = str(data.get("mail") or data.get("userPrincipalName") or email).lower()
        return GraphMailboxInfo(
            graph_mailbox_id=str(data.get("id") or resolved_email),
            email=resolved_email,
            display_name=data.get("displayName"),
        )

    def get_message(
        self,
        *,
        user_assertion: str,
        tenant_id: str,
        message_id: str,
        mailbox_kind: MailboxKind,
        mailbox_email: str,
        graph_mailbox_id: str | None,
    ) -> GraphMessage:
        token = self._acquire_obo_token(user_assertion=user_assertion, tenant_id=tenant_id)
        # Prefer plain text — HTML bodies can crash local embedding runtimes.
        headers = {
            "Authorization": f"Bearer {token}",
            "Prefer": 'outlook.body-content-type="text"',
        }
        root = _mailbox_root(
            mailbox_kind=mailbox_kind,
            mailbox_email=mailbox_email,
            graph_mailbox_id=graph_mailbox_id,
        )
        try:
            with httpx.Client(timeout=20.0) as client:
                resp = client.get(
                    f"{root}/messages/{quote(message_id, safe='')}",
                    headers=headers,
                    params={
                        "$select": "id,subject,body,from,hasAttachments,toRecipients,ccRecipients"
                    },
                )
                if resp.status_code >= 400:
                    logger.info(
                        "graph_get_message_failed status=%s",
                        resp.status_code,
                    )
                    raise AppError(
                        code="CONNECTOR_FAILURE",
                        message=(
                            "Graph could not read the message. "
                            "Ensure the add-in sends a REST item id (convertToRestId)."
                            if resp.status_code == 400
                            else "Graph could not read the message."
                        ),
                        status_code=502,
                        retryable=True,
                    )
                data = resp.json()
                frm = data.get("from") or {}
                email_addr = (frm.get("emailAddress") or {}) if isinstance(frm, dict) else {}
                sender = str(email_addr.get("address") or "")
                body_obj = data.get("body") or {}
                body = str(body_obj.get("content") or "") if isinstance(body_obj, dict) else ""
                names: list[str] = []
                sizes: list[int] = []
                if data.get("hasAttachments"):
                    att = client.get(
                        f"{root}/messages/{quote(message_id, safe='')}/attachments",
                        headers=headers,
                        params={"$select": "name,size"},
                    )
                    if att.status_code < 400:
                        for item in att.json().get("value") or []:
                            names.append(str(item.get("name") or "attachment"))
                            try:
                                sizes.append(int(item.get("size") or 0))
                            except (TypeError, ValueError):
                                sizes.append(0)
        except AppError:
            raise
        except httpx.HTTPError:
            logger.info("graph_get_message_transport_failed")
            raise AppError(
                code="CONNECTOR_FAILURE",
                message="Graph connector failed while reading the message.",
                status_code=502,
                retryable=True,
            ) from None

        return GraphMessage(
            message_id=str(data.get("id") or message_id),
            subject=str(data.get("subject") or ""),
            body=body,
            sender=sender,
            attachment_names=names,
            attachment_sizes=sizes,
            to_recipients=_recipient_addresses(data.get("toRecipients")),
            cc_recipients=_recipient_addresses(data.get("ccRecipients")),
        )

    def send_mail(
        self,
        *,
        user_assertion: str,
        tenant_id: str,
        recipients: list[str],
        subject: str,
        body: str,
        mailbox_kind: MailboxKind,
        mailbox_email: str,
        graph_mailbox_id: str | None,
    ) -> GraphSendResult:
        token = self._acquire_obo_token(user_assertion=user_assertion, tenant_id=tenant_id)
        root = _mailbox_root(
            mailbox_kind=mailbox_kind,
            mailbox_email=mailbox_email,
            graph_mailbox_id=graph_mailbox_id,
        )
        payload = {
            "message": {
                "subject": subject,
                "body": {"contentType": "Text", "content": body},
                "toRecipients": [{"emailAddress": {"address": r}} for r in recipients],
            },
            "saveToSentItems": True,
        }
        try:
            with httpx.Client(timeout=30.0) as client:
                resp = client.post(
                    f"{root}/sendMail",
                    headers={"Authorization": f"Bearer {token}"},
                    json=payload,
                )
        except httpx.HTTPError:
            logger.info("graph_send_transport_failed")
            raise AppError(
                code="CONNECTOR_FAILURE",
                message="Graph sendMail transport failed.",
                status_code=502,
                retryable=True,
            ) from None
        if resp.status_code >= 400:
            raise AppError(
                code="CONNECTOR_FAILURE",
                message="Graph sendMail failed.",
                status_code=502,
                retryable=True,
            )
        return GraphSendResult(graph_message_id=f"graph-send-{message_id_hash(subject)}")

    def forward_mail(
        self,
        *,
        user_assertion: str,
        tenant_id: str,
        message_id: str,
        recipients: list[str],
        comment: str,
        mailbox_kind: MailboxKind,
        mailbox_email: str,
        graph_mailbox_id: str | None,
    ) -> GraphSendResult:
        token = self._acquire_obo_token(user_assertion=user_assertion, tenant_id=tenant_id)
        root = _mailbox_root(
            mailbox_kind=mailbox_kind,
            mailbox_email=mailbox_email,
            graph_mailbox_id=graph_mailbox_id,
        )
        payload = {
            "comment": comment,
            "toRecipients": [{"emailAddress": {"address": r}} for r in recipients],
        }
        try:
            with httpx.Client(timeout=30.0) as client:
                resp = client.post(
                    f"{root}/messages/{quote(message_id, safe='')}/forward",
                    headers={"Authorization": f"Bearer {token}"},
                    json=payload,
                )
        except httpx.HTTPError:
            logger.info("graph_forward_transport_failed")
            raise AppError(
                code="CONNECTOR_FAILURE",
                message="Graph forward transport failed.",
                status_code=502,
                retryable=True,
            ) from None
        if resp.status_code >= 400:
            raise AppError(
                code="CONNECTOR_FAILURE",
                message="Graph forward failed.",
                status_code=502,
                retryable=True,
            )
        return GraphSendResult(graph_message_id=f"graph-fwd-{message_id}")

    def list_sent_messages(
        self,
        *,
        user_assertion: str,
        tenant_id: str,
        mailbox_kind: MailboxKind,
        mailbox_email: str,
        graph_mailbox_id: str | None,
        max_messages: int = 100,
        on_progress: Callable[[int], None] | None = None,
    ) -> list[GraphMessage]:
        token = self._acquire_obo_token(user_assertion=user_assertion, tenant_id=tenant_id)
        # Heartbeat after OBO so poll UI can distinguish a live fetch from a dead worker.
        if on_progress is not None:
            try:
                on_progress(0)
            except Exception:
                logger.info("graph_list_sent_progress_callback_failed")
        root = _mailbox_root(
            mailbox_kind=mailbox_kind,
            mailbox_email=mailbox_email,
            graph_mailbox_id=graph_mailbox_id,
        )
        headers = {"Authorization": f"Bearer {token}"}
        # bodyPreview only — full body per message makes 3000-item sync far too slow.
        page_size = min(50, max(1, max_messages))
        url: str | None = f"{root}/mailFolders/sentitems/messages"
        params: dict[str, str] | None = {
            "$top": str(page_size),
            "$orderby": "sentDateTime desc",
            "$select": "id,subject,bodyPreview,from",
        }
        out: list[GraphMessage] = []
        try:
            with httpx.Client(timeout=120.0) as client:
                while url and len(out) < max_messages:
                    resp = client.get(url, headers=headers, params=params)
                    params = None  # nextLink already includes query string
                    if resp.status_code >= 400:
                        logger.info(
                            "graph_list_sent_failed status=%s",
                            resp.status_code,
                        )
                        raise AppError(
                            code="CONNECTOR_FAILURE",
                            message="Graph could not list Sent Items for indexing.",
                            status_code=502,
                            retryable=True,
                        )
                    data = resp.json()
                    for row in data.get("value") or []:
                        if len(out) >= max_messages:
                            break
                        body = str(row.get("bodyPreview") or "")
                        frm = row.get("from") or {}
                        email_addr = (
                            (frm.get("emailAddress") or {}) if isinstance(frm, dict) else {}
                        )
                        out.append(
                            GraphMessage(
                                message_id=str(row.get("id") or ""),
                                subject=str(row.get("subject") or ""),
                                body=body,
                                sender=str(email_addr.get("address") or mailbox_email),
                            )
                        )
                    if on_progress is not None:
                        try:
                            on_progress(len(out))
                        except Exception:
                            logger.info("graph_list_sent_progress_callback_failed")
                    next_link = data.get("@odata.nextLink")
                    url = str(next_link) if next_link else None
        except AppError:
            raise
        except httpx.HTTPError:
            logger.info("graph_list_sent_transport_failed")
            raise AppError(
                code="CONNECTOR_FAILURE",
                message="Graph Sent Items transport failed.",
                status_code=502,
                retryable=True,
            ) from None
        return [m for m in out if m.message_id]

    def _raise_calendar_status(
        self, status_code: int, *, action: str, body_text: str = ""
    ) -> None:
        if status_code in (401, 403):
            lowered = (body_text or "").lower()
            if any(
                token in lowered
                for token in ("scope", "insufficient", "not granted", "accessdenied")
            ):
                raise AppError(
                    code="BAD_SCOPES",
                    message=f"Graph calendar {action} denied — Calendars scopes insufficient.",
                    status_code=403,
                    retryable=False,
                )
            raise AppError(
                code="CONSENT_REQUIRED",
                message=f"Graph calendar {action} denied — check Calendars consent/scopes.",
                status_code=403,
                retryable=False,
            )
        raise AppError(
            code="CONNECTOR_FAILURE",
            message=f"Graph calendar {action} failed.",
            status_code=502,
            retryable=True,
        )

    def get_calendar_busy(
        self,
        *,
        user_assertion: str,
        tenant_id: str,
        mailbox_kind: MailboxKind,
        mailbox_email: str,
        graph_mailbox_id: str | None,
        start_iso: str,
        end_iso: str,
    ) -> list[BusyInterval]:
        token = self._acquire_obo_token(user_assertion=user_assertion, tenant_id=tenant_id)
        root = _mailbox_root(
            mailbox_kind=mailbox_kind,
            mailbox_email=mailbox_email,
            graph_mailbox_id=graph_mailbox_id,
        )
        headers = {"Authorization": f"Bearer {token}"}
        # Prefer getSchedule for free/busy; fall back to calendarView.
        schedule_payload = {
            "schedules": [mailbox_email],
            "startTime": {"dateTime": start_iso.replace("Z", ""), "timeZone": "Europe/Brussels"},
            "endTime": {"dateTime": end_iso.replace("Z", ""), "timeZone": "Europe/Brussels"},
            "availabilityViewInterval": 30,
        }
        try:
            with httpx.Client(timeout=30.0) as client:
                resp = client.post(
                    f"{root}/calendar/getSchedule",
                    headers=headers,
                    json=schedule_payload,
                )
                if resp.status_code in (401, 403):
                    self._raise_calendar_status(
                        resp.status_code,
                        action="getSchedule",
                        body_text=resp.text[:500],
                    )
                if resp.status_code >= 400:
                    # Fallback: calendarView of events (treat as busy), paginate.
                    busy_rows: list[dict] = []
                    url: str | None = f"{root}/calendarView"
                    params: dict[str, str] | None = {
                        "startDateTime": start_iso,
                        "endDateTime": end_iso,
                        "$select": "start,end,showAs,isAllDay",
                        "$top": "100",
                    }
                    while url:
                        resp = client.get(url, headers=headers, params=params)
                        if resp.status_code in (401, 403):
                            self._raise_calendar_status(
                                resp.status_code,
                                action="calendarView",
                                body_text=resp.text[:500],
                            )
                        if resp.status_code >= 400:
                            self._raise_calendar_status(
                                resp.status_code,
                                action="busy",
                                body_text=resp.text[:500],
                            )
                        page = resp.json()
                        busy_rows.extend(page.get("value") or [])
                        next_link = page.get("@odata.nextLink")
                        url = str(next_link) if next_link else None
                        params = None
                    return _busy_from_calendar_view({"value": busy_rows})
                return _busy_from_get_schedule(resp.json())
        except AppError:
            raise
        except httpx.HTTPError:
            logger.info("graph_calendar_busy_transport_failed")
            raise AppError(
                code="CONNECTOR_FAILURE",
                message="Graph calendar busy transport failed.",
                status_code=502,
                retryable=True,
            ) from None

    def create_calendar_event(
        self,
        *,
        user_assertion: str,
        tenant_id: str,
        mailbox_kind: MailboxKind,
        mailbox_email: str,
        graph_mailbox_id: str | None,
        subject: str,
        start_iso: str,
        end_iso: str,
        attendees: list[str],
        body: str | None = None,
    ) -> GraphEventResult:
        token = self._acquire_obo_token(user_assertion=user_assertion, tenant_id=tenant_id)
        root = _mailbox_root(
            mailbox_kind=mailbox_kind,
            mailbox_email=mailbox_email,
            graph_mailbox_id=graph_mailbox_id,
        )
        payload = {
            "subject": subject,
            "body": {
                "contentType": "Text",
                "content": body or "",
            },
            "start": {
                "dateTime": _graph_local_datetime(start_iso),
                "timeZone": "Europe/Brussels",
            },
            "end": {
                "dateTime": _graph_local_datetime(end_iso),
                "timeZone": "Europe/Brussels",
            },
            "attendees": [
                {
                    "emailAddress": {"address": a},
                    "type": "required",
                }
                for a in attendees
            ],
        }
        try:
            with httpx.Client(timeout=30.0) as client:
                resp = client.post(
                    f"{root}/events",
                    headers={"Authorization": f"Bearer {token}"},
                    json=payload,
                )
        except httpx.HTTPError:
            logger.info("graph_create_event_transport_failed")
            raise AppError(
                code="CONNECTOR_FAILURE",
                message="Graph create event transport failed.",
                status_code=502,
                retryable=True,
            ) from None
        if resp.status_code in (401, 403):
            self._raise_calendar_status(
                resp.status_code, action="create", body_text=resp.text[:500]
            )
        if resp.status_code >= 400:
            logger.info("graph_create_event_failed status=%s", resp.status_code)
            raise AppError(
                code="CONNECTOR_FAILURE",
                message="Graph create event failed.",
                status_code=502,
                retryable=True,
            )
        try:
            data = resp.json()
        except ValueError as exc:
            raise AppError(
                code="CONNECTOR_FAILURE",
                message="Graph create event returned non-JSON body.",
                status_code=502,
                retryable=True,
            ) from exc
        event_id = str(data.get("id") or "").strip()
        if not event_id:
            raise AppError(
                code="CONNECTOR_FAILURE",
                message="Graph create event omitted event id.",
                status_code=502,
                retryable=True,
            )
        return GraphEventResult(graph_event_id=event_id)


def _recipient_addresses(raw: object) -> list[str]:
    out: list[str] = []
    if not isinstance(raw, list):
        return out
    for item in raw:
        if not isinstance(item, dict):
            continue
        addr = (item.get("emailAddress") or {}) if isinstance(item.get("emailAddress"), dict) else {}
        email = str(addr.get("address") or "").strip().lower()
        if email and email not in out:
            out.append(email)
    return out


def _parse_graph_dt(value: str | None, *, time_zone: str | None = None) -> datetime | None:
    if not value:
        return None
    raw = value.strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if dt.tzinfo is None:
        tz_name = (time_zone or "Europe/Brussels").strip() or "Europe/Brussels"
        try:
            dt = dt.replace(tzinfo=ZoneInfo(tz_name))
        except Exception:
            dt = dt.replace(tzinfo=_BRUSSELS)
    return dt


def _graph_local_datetime(iso_value: str) -> str:
    """Graph dateTime without offset when paired with timeZone."""
    dt = _parse_graph_dt(iso_value)
    if dt is None:
        return iso_value.replace("Z", "")
    local = dt.astimezone(_BRUSSELS)
    return local.strftime("%Y-%m-%dT%H:%M:%S")


def _busy_from_get_schedule(data: dict) -> list[BusyInterval]:
    out: list[BusyInterval] = []
    for schedule in data.get("value") or []:
        for item in schedule.get("scheduleItems") or []:
            status = str(item.get("status") or "").lower()
            if status in {"free"}:
                continue
            start_obj = item.get("start") or {}
            end_obj = item.get("end") or {}
            start_tz = (
                start_obj.get("timeZone") if isinstance(start_obj, dict) else None
            )
            end_tz = end_obj.get("timeZone") if isinstance(end_obj, dict) else None
            start = _parse_graph_dt(
                start_obj.get("dateTime") if isinstance(start_obj, dict) else None,
                time_zone=str(start_tz) if start_tz else None,
            )
            end = _parse_graph_dt(
                end_obj.get("dateTime") if isinstance(end_obj, dict) else None,
                time_zone=str(end_tz) if end_tz else None,
            )
            if start and end and end > start:
                out.append(BusyInterval(start=start, end=end))
    return out


def _busy_from_calendar_view(data: dict) -> list[BusyInterval]:
    out: list[BusyInterval] = []
    for row in data.get("value") or []:
        show_as = str(row.get("showAs") or "busy").lower()
        if show_as in {"free"}:
            continue
        start_obj = row.get("start") or {}
        end_obj = row.get("end") or {}
        start_tz = start_obj.get("timeZone") if isinstance(start_obj, dict) else None
        end_tz = end_obj.get("timeZone") if isinstance(end_obj, dict) else None
        start = _parse_graph_dt(
            start_obj.get("dateTime") if isinstance(start_obj, dict) else None,
            time_zone=str(start_tz) if start_tz else None,
        )
        end = _parse_graph_dt(
            end_obj.get("dateTime") if isinstance(end_obj, dict) else None,
            time_zone=str(end_tz) if end_tz else None,
        )
        if start and end and end > start:
            out.append(BusyInterval(start=start, end=end))
    return out


def message_id_hash(subject: str) -> str:
    return str(abs(hash(subject)) % 10_000_000)


_client: MailGraphClient | None = None


def get_mail_graph_client() -> MailGraphClient:
    global _client
    if _client is None:
        settings = get_settings()
        if settings.graph_mode.lower() == "obo":
            _client = OboMailGraphClient(settings)
        else:
            _client = StubMailGraphClient()
    return _client


def set_mail_graph_client(client: MailGraphClient | None) -> None:
    """Test helper."""
    global _client
    _client = client
