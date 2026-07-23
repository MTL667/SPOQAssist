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

export interface ActionItemOut {
  id?: string | null;
  action_type: string;
  description: string;
  due_date?: string | null;
  dismissed?: boolean;
}

export interface AttachmentSummaryOut {
  filename: string;
  mime_type: string;
  summary: string;
  page_count?: number | null;
  is_scan?: boolean;
}

export interface SuggestionOut {
  suggestion_id: string;
  mailbox_profile_id: string;
  message_id: string;
  category: string;
  priority: string;
  confidence: Confidence;
  suggested_route?: { display_name?: string | null; email: string } | null;
  draft?: string | null;
  draft_error?: string | null;
  why?: { code: string; text: string }[];
  history_status: HistoryStatus;
  attachment_warnings?: { name: string; reason: string }[];
  attachment_summaries?: AttachmentSummaryOut[];
  actions?: string[];
  extracted_actions?: ActionItemOut[];
  precompute_status?: string | null;
  timings?: Record<string, number>;
}

export interface ActionItemViewModel {
  id: string | null;
  actionType: string;
  description: string;
  dueDate: string | null;
  dismissed: boolean;
}

export interface AttachmentSummaryViewModel {
  filename: string;
  summary: string;
  pageCount: number | null;
  isScan: boolean;
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
  draftError: string | null;
  why: { code: string; text: string }[];
  historyStatus: HistoryStatus;
  attachmentWarnings: { name: string; reason: string }[];
  attachmentSummaries: AttachmentSummaryViewModel[];
  actions: string[];
  extractedActions: ActionItemViewModel[];
  precomputeStatus: string | null;
  timings: Record<string, number>;
}

export interface PaneModel {
  state: PaneState;
  suggestion: SuggestionViewModel | null;
  unavailableMessage: string | null;
  errorMessage: string | null;
}
