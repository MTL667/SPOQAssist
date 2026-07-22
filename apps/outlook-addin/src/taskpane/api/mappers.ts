import type { SuggestionOut, SuggestionViewModel } from "../state/paneState";

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
    why: (api.why || []).map((w) => ({ code: w.code, text: w.text })),
    historyStatus: api.history_status,
    attachmentWarnings: (api.attachment_warnings || []).map((w) => ({
      name: w.name,
      reason: w.reason,
    })),
    actions: api.actions || [],
  };
}
