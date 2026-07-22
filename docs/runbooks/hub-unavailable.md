# Hub unavailable

## Symptoms

- Outlook pane shows **SpoqSense unavailable** + **Retry**
- Monitoring: `GET /health` fails or times out over Tailscale/TLS

## Checks (no mailbox content)

```bash
curl -sS http://localhost:8000/health
curl -sS http://localhost:8000/v1/ops/health_detail
```

1. Is Compose `api` / uvicorn running on the Mac Studio?
2. Is Postgres healthy (`db` service)?
3. Can the MacBook reach the Studio over Tailscale?
4. Is `HUB_BASE_URL` in the add-in build correct?

## User impact

While unavailable, the add-in must not show stale Accept or suggestion actions.
