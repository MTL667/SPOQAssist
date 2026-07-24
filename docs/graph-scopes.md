# Microsoft Graph scopes (per Entra entity)

Documented during Story 1.4. Configure the same scopes on each Entra app registration that the hub uses for OBO.

## Pilot scopes

| Scope | Purpose |
|-------|---------|
| `Mail.Read` | Read message content for analysis (personal) |
| `Mail.Read.Shared` | Read shared-mailbox content for delegates |
| `Mail.Send` | Send/forward only after confirm-outbound (FR37) — used in later stories |
| `Calendars.Read` | Free/busy consult for meeting-intent drafts (owner calendar only) |
| `Calendars.ReadWrite` | Create Outlook events after explicit Schedule confirm |

Authority: `https://login.microsoftonline.com/{tenant_id}`  
Resource: Microsoft Graph (`https://graph.microsoft.com`)

## Hub configuration

- `GRAPH_MODE=stub` — local/dev without live Graph (default)
- `GRAPH_MODE=obo` — confidential client OBO on the Mac Studio hub
- `ENTRA_CLIENT_ID` / `ENTRA_CLIENT_SECRET` — **hub only**; never ship to the Outlook add-in
- `GRAPH_SCOPES` — comma-separated list matching admin consent
- Ops may record non-secret scope notes via `PUT /v1/ops/connector_config` (FR36)

## Rules

1. The add-in sends only the hub API Bearer token — never Graph refresh tokens.
2. OBO exchange and Graph calls happen only on the hub.
3. Missing consent → API error code `CONSENT_REQUIRED`.
4. Insufficient scopes → `BAD_SCOPES`.
5. Transient Graph failures → `CONNECTOR_FAILURE` (retryable).
