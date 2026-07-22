# SpoqAssist Outlook add-in

Outlook for Mac task pane (React + Fluent UI v9).

## Dev

```bash
export HUB_BASE_URL=http://localhost:8000
npm install
npx office-addin-dev-certs install   # once
npm run dev-server
```

Sideload `manifest.xml` — see `docs/runbooks/sideload-fallback.md`.

On open, the pane probes `GET {HUB_BASE_URL}/health`. If unreachable → `HubUnavailable` + Retry (no suggestions).

## Build

```bash
npm run build
```
