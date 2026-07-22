export type PaneState =
  | "checking"
  | "idle"
  | "unavailable"
  | "analyzing"
  | "ready_hero"
  | "ready_review"
  | "confirming"
  | "editing"
  | "error";

export type Confidence = "high" | "medium" | "low";
export type HistoryStatus = "sufficient" | "limited" | "none";

export interface SuggestionOut {
  suggestion_id: string;
  mailbox_profile_id: string;
  message_id: string;
  category: string;
  priority: string;
  confidence: Confidence;
  suggested_route?: { display_name?: string | null; email: string } | null;
  draft?: string | null;
  why?: { code: string; text: string }[];
  history_status: HistoryStatus;
  attachment_warnings?: { name: string; reason: string }[];
  actions?: string[];
}

export interface SuggestionViewModel {
  suggestionId: string;
  mailboxProfileId: string;
  messageId: string;
  category: string;
  priority: string;
  confidence: Confidence;
  suggestedRoute: { displayName?: string | null; email: string } | null;
  draft: string | null | undefined;
  why: { code: string; text: string }[];
  historyStatus: HistoryStatus;
  attachmentWarnings: { name: string; reason: string }[];
  actions: string[];
}

export interface PaneModel {
  state: PaneState;
  suggestion: SuggestionViewModel | null;
  unavailableMessage: string | null;
  errorMessage: string | null;
}
