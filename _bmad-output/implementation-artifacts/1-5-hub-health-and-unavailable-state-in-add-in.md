---
story_key: 1-5-hub-health-and-unavailable-state-in-add-in
epic: 1
story: 5
status: review
---

# Story 1.5: Hub health and unavailable state in add-in

## Status

review

## Acceptance Criteria

- `GET /health` non-content (existing)
- Pane shows HubUnavailable + Retry when hub unreachable
- No stale Accept/suggestion actions while unavailable

## Dev Agent Record

### Completion Notes

- Add-in: `HubUnavailable.tsx`, `api/client.ts` health probe, pane states `checking|idle|unavailable`
- `HUB_BASE_URL` via webpack DefinePlugin
- Runbook: `docs/runbooks/hub-unavailable.md`
