---
title: 'Hub health check timeout (stop infinite Checking…)'
type: 'bugfix'
created: '2026-07-22'
status: 'done'
route: 'one-shot'
---

# Hub health check timeout (stop infinite Checking…)

## Intent

**Problem:** When the LAN hub/proxy is slow or briefly unreachable, `fetchHealth` had no timeout, so the Outlook taskpane stayed on “Checking SpoqAssist hub…” indefinitely.

**Approach:** Abort the health `fetch` after 5 seconds with `AbortController`, so the pane shows the unavailable/retry UI instead of spinning forever.

## Suggested Review Order

- Bound health fetch with AbortController + 5s timer
  [`client.ts:41`](../../apps/outlook-addin/src/taskpane/api/client.ts#L41)
