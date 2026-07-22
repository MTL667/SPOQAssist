---
story_key: 1-4-connect-mailbox-via-microsoft-graph
epic: 1
story: 4
status: review
---

# Story 1.4: Connect mailbox via Microsoft Graph

## Status

review

## Acceptance Criteria

- Connect personal + shared succeeds (stub or OBO)
- Consent / bad scopes / connector failure → clear error codes
- Graph secrets stay on hub only; client never stores them

## Dev Agent Record

### Completion Notes

- `POST /v1/mailbox_profiles/connect`
- `services/mail_graph.py`: `StubMailGraphClient` (default) + `OboMailGraphClient` (`GRAPH_MODE=obo`)
- Docs: `docs/graph-scopes.md`
- Error codes: `CONSENT_REQUIRED`, `BAD_SCOPES`, `CONNECTOR_FAILURE`

### Tests

- `tests/api/test_mailbox_connect.py`
