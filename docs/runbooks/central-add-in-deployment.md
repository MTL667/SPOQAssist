# Central Outlook add-in deployment per Entra entity (Story 1.6)

## Goal

Deploy SpoqSense to pilot users/groups via Microsoft 365 integrated apps **per Entra entity**, so users are not limited to sideload (FR27, NFR-I2).

## Prerequisites

- One Entra app registration (or linked add-in identity) **per entity/tenant** listed in `ENTRA_TENANT_IDS` / `ENTRA_ENTITIES`
- Manifest XML built for the target host URL (HTTPS) reachable by Outlook for Mac over Tailscale/VPN when needed
- Hub API healthy: `GET /health` → `{"status":"ok",...}` (no mailbox content)

## Steps (Microsoft 365 admin center)

Repeat for **each** Entra entity:

1. Sign in to [Microsoft 365 admin center](https://admin.microsoft.com) for that tenant.
2. Go to **Settings → Integrated apps** (or **Exchange → Add-ins** depending on admin UX).
3. Choose **Upload custom apps** / deploy add-in from file.
4. Upload the SpoqSense `manifest.xml` (production host URLs, not `localhost`).
5. Assign to **users or groups** in the pilot (not org-wide until ready).
6. Confirm Outlook for Mac shows **SpoqSense** on the message read surface for assigned users.
7. Record the assignment in ops notes (`PUT /v1/ops/connector_config`) — non-content only.

## Manifest checklist before upload

- Unique `<Id>` per published revision policy
- `SourceLocation` / icon URLs point to the HTTPS add-in host for that environment
- `AppDomains` includes the add-in host
- Permissions remain least-privilege for the pilot surface

## Sideload fallback

If a user is not yet in the assignment group, use [sideload-fallback.md](./sideload-fallback.md).

## Ops config without mail content (FR36)

Authorized operators (`OPS_PRINCIPAL_OIDS`) can manage **non-content** connector/auth settings:

- `GET /v1/ops/health_detail` — entity count / tenant ids / graph mode (no mail)
- `GET|PUT /v1/ops/connector_config` — scopes string + notes (rejects secret smuggling)

Client secrets stay in hub `.env` / secret store on the Mac Studio — never in the add-in or ops JSON notes.
