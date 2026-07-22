---
story_key: 1-6-central-outlook-add-in-deployment-per-entra-entity
epic: 1
story: 6
status: review
---

# Story 1.6: Central Outlook add-in deployment per Entra entity

## Status

review

## Acceptance Criteria

- Documented centralized deploy steps per Entra entity (FR27)
- Sideload documented as temporary fallback
- Non-content connector/auth ops config (FR36)

## Dev Agent Record

### Completion Notes

- `docs/runbooks/central-add-in-deployment.md`
- `docs/runbooks/sideload-fallback.md`
- Ops API: `GET /v1/ops/health_detail`, `GET|PUT /v1/ops/connector_config` (ops OID gate; rejects secret notes)

### Tests

- `tests/api/test_admin_ops.py`
