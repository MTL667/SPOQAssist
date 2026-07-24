import type {
  ActionItemViewModel,
  AttachmentSummaryViewModel,
  SuggestionOut,
  SuggestionViewModel,
} from "../state/paneState";

/** snake_case API → camelCase UI view model */
export function mapSuggestion(api: SuggestionOut): SuggestionViewModel {
  return {
    suggestionId: api.suggestion_id,
    mailboxProfileId: api.mailbox_profile_id,
    messageId: api.message_id,
    category: api.category,
    priority: api.priority,
    confidence: api.confidence,
    suggestedRoute: api.suggested_route
      ? {
          displayName: api.suggested_route.display_name,
          email: api.suggested_route.email,
        }
      : null,
    draft: api.draft,
    draftError: api.draft_error ?? null,
    why: (api.why || []).map((w) => ({ code: w.code, text: w.text })),
    historyStatus: api.history_status,
    attachmentWarnings: (api.attachment_warnings || []).map((w) => ({
      name: w.name,
      reason: w.reason,
    })),
    attachmentSummaries: (api.attachment_summaries || []).map(
      (a): AttachmentSummaryViewModel => ({
        filename: a.filename,
        summary: a.summary,
        pageCount: a.page_count ?? null,
        isScan: a.is_scan ?? false,
      })
    ),
    actions: api.actions || [],
    extractedActions: (api.extracted_actions || []).map(
      (a): ActionItemViewModel => ({
        id: a.id ?? null,
        actionType: a.action_type,
        description: a.description,
        dueDate: a.due_date ?? null,
        dismissed: a.dismissed ?? false,
      })
    ),
    proposedSlots: (api.proposed_slots || []).map((s) => ({
      start: s.start,
      end: s.end,
      label: s.label,
    })),
    availabilityNote: api.availability_note ?? null,
    precomputeStatus: api.precompute_status ?? null,
    timings: api.timings ?? {},
  };
}
