# Sideload fallback (Outlook for Mac)

Temporary path when centralized deployment (Story 1.6) has not yet assigned the user.

## Steps

```bash
# Terminal 1 — hub
docker compose -f docker/docker-compose.yml up --build

# Terminal 2 — add-in
cd apps/outlook-addin
npx office-addin-dev-certs install   # once
export HUB_BASE_URL=http://localhost:8000
npm run dev-server
```

1. In Outlook for Mac: **Get Add-ins → My Add-ins → Add from file** (or org sideload path).
2. Select `apps/outlook-addin/manifest.xml` (or `dist/manifest.xml` after build).
3. Open a message → **SpoqAssist** task pane.
4. If the hub is down, the pane shows **SpoqAssist unavailable** with **Retry** (no Accept/suggestions).

## Notes

- Sideload is for developers and early pilot only.
- Prefer central assignment per Entra entity once ready — see [central-add-in-deployment.md](./central-add-in-deployment.md).
