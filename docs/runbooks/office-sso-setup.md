# Office SSO setup (add-in → hub Bearer)

## Goal

Outlook for Mac obtains an Entra access token via Office SSO and calls the SpoqAssist hub with `Authorization: Bearer`. Sideload can still use `localStorage.spoq_access_token` as fallback.

## Per Entra entity

1. App registration (same tenant as users):
   - Application ID URI: `api://localhost:3000/{client-id}` (dev) or `api://{add-in-host}/{client-id}` (prod)
   - Expose scope: `access_as_user`
   - Pre-authorize Microsoft Office (`ea5a67f6-b6f3-4338-b240-c655ddc3cc8e`) and Outlook desktop
2. Hub `.env`:
   - `ENTRA_TENANT_IDS={tenant}`
   - `ENTRA_API_AUDIENCE=api://localhost:3000/{client-id}` (must match Resource)
3. Manifest `WebApplicationInfo`:
   - Replace `REPLACE_ENTRA_CLIENT_ID` with the client ID
   - Align `Resource` with Application ID URI
4. Sideload / central deploy the updated manifest

## Fallback (sideload without SSO)

```js
localStorage.setItem("spoq_access_token", "<access token aud=ENTRA_API_AUDIENCE>")
// mailbox profile is auto-created on first analyze via connect
```

## Notes

- Tokens are never logged in the add-in or hub.
- Graph OBO still uses hub `ENTRA_CLIENT_ID` / `ENTRA_CLIENT_SECRET` (`GRAPH_MODE=obo`).
