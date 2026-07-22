# Office SSO setup (add-in → hub Bearer)

## Goal

Outlook for Mac obtains an Entra access token via Office SSO and calls the SpoqAssist hub with `Authorization: Bearer`. Sideload can still use an in-pane paste (or `localStorage.spoq_access_token`) as fallback.

## Per Entra entity

1. App registration (same tenant as users):
   - Application ID URI: `api://localhost:3000/{client-id}` (dev) or `api://{add-in-host}/{client-id}` (prod)
   - Expose scope: `access_as_user`
   - Pre-authorize Microsoft Office (`ea5a67f6-b6f3-4338-b240-c655ddc3cc8e`) and Outlook desktop
2. Hub `.env`:
   - `ENTRA_TENANT_IDS={tenant}`
   - `ENTRA_API_AUDIENCE=api://localhost:3000/{client-id}` (must match Resource)
3. Manifest `WebApplicationInfo`:
   - `Id` = Entra client ID
   - `Resource` aligned with Application ID URI / hub audience
4. Sideload / central deploy the updated manifest

## Add-in UX

- Office SSO is tried first (`Office.auth.getAccessToken`).
- On failure the taskpane shows **Sign in required** with the SSO **code** and short message (never the token).
- Use **Retry SSO**, or paste a hub access token and **Save token** (stored only in `localStorage` as `spoq_access_token`).
- **Clear stored token** removes the sideload fallback.

## Common SSO error codes

| Code | Typical meaning | What to check |
|------|-----------------|---------------|
| 13001 | User identity / sign-in required | Sign into Outlook with work account; allow prompts |
| 13002 | User aborted consent/sign-in | Retry SSO and accept consent |
| 13005 | Resource / audience issue | Manifest `Resource` == hub `ENTRA_API_AUDIENCE`; App ID URI |
| 13006 | Client / app not registered for SSO | Pre-authorize Office client; expose `access_as_user` |
| 13007 | Invalid invalid / not consented | Admin consent for the API scope |
| 50001 / 9017 | Host / capability | Outlook build supports nested app auth; update Office |
| `sso_unavailable` | `Office.auth` missing | Not running inside Outlook WebView |

## Fallback (sideload without SSO)

In the SpoqAssist pane: paste a JWT whose `aud` matches `ENTRA_API_AUDIENCE`, then Save.

Or via DevTools console:

```js
localStorage.setItem("spoq_access_token", "<access token aud=ENTRA_API_AUDIENCE>")
```

## Notes

- Tokens are never logged in the add-in or hub.
- Graph OBO still uses hub `ENTRA_CLIENT_ID` / `ENTRA_CLIENT_SECRET` (`GRAPH_MODE=obo`).
