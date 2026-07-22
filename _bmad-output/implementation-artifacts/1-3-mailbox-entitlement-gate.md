---
story_key: 1-3-mailbox-entitlement-gate
epic: 1
story: 3
status: review
---

# Story 1.3: Mailbox entitlement gate

## Status

review

## Acceptance Criteria

- Unentitled caller → 403 FORBIDDEN on data/AI endpoints
- Personal mailbox: non-owner including admin denied on content endpoints (FR6)
- Checks in hub `domain/policies.py` + `api/deps.py`

## Dev Agent Record

### Completion Notes

- Tables: `mailbox_profiles`, `mailbox_entitlements`
- `require_mailbox_content_access` dependency; content stub at `GET /v1/mailbox_profiles/{id}/content_stub`
- Personal: owner only; shared: owner / shared_delegate / admin

### Tests

- `tests/api/test_mailbox_entitlement.py`
