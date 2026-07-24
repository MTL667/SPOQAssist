import type { SuggestionOut } from "../state/paneState";

export interface HealthResponse {
  status: string;
  service?: string;
}

export interface OpsHealthDetail {
  status: string;
  graph_mode?: string;
  inference?: { status?: string; mode?: string };
  configured_tenant_ids?: string[];
  register_doc?: string;
}

function hubBaseUrl(): string {
  // webpack DefinePlugin injects a string literal for process.env.HUB_BASE_URL.
  // Do not gate on `process` existing — Office WebViews often have no Node `process`,
  // which previously fell through to http://localhost:8000 (mixed-content blocked).
  const injected = process.env.HUB_BASE_URL;
  if (typeof injected === "string") {
    return injected.replace(/\/$/, "");
  }
  return "http://localhost:8000";
}

async function parseError(response: Response): Promise<string> {
  try {
    const data = (await response.json()) as {
      error?: { message?: string; code?: string };
      detail?: string | { msg?: string }[];
    };
    if (data.error?.message) return data.error.message;
    if (typeof data.detail === "string") return data.detail;
  } catch {
    /* ignore */
  }
  return `HTTP ${response.status}`;
}

export async function fetchHealth(signal?: AbortSignal): Promise<HealthResponse> {
  // Office WebView + webpack proxy can hang past AbortSignal when the LAN hub stalls.
  // Race a hard timeout so the pane always leaves "Checking…".
  const controller = new AbortController();
  const onCallerAbort = () => controller.abort();
  if (signal) {
    if (signal.aborted) controller.abort();
    else signal.addEventListener("abort", onCallerAbort, { once: true });
  }
  const timeoutMs = 8000;
  let timer: number | undefined;
  const timeoutReject = new Promise<never>((_, reject) => {
    timer = window.setTimeout(() => {
      controller.abort();
      reject(new Error("Hub health timed out"));
    }, timeoutMs);
  });
  try {
    const response = await Promise.race([
      fetch(`${hubBaseUrl()}/health`, {
        method: "GET",
        signal: controller.signal,
        headers: { Accept: "application/json" },
      }),
      timeoutReject,
    ]);
    if (!response.ok) throw new Error(`Hub health HTTP ${response.status}`);
    return (await response.json()) as HealthResponse;
  } finally {
    if (timer != null) window.clearTimeout(timer);
    if (signal) signal.removeEventListener("abort", onCallerAbort);
  }
}

export async function fetchOpsHealth(): Promise<OpsHealthDetail> {
  const response = await fetch(`${hubBaseUrl()}/v1/ops/health_detail`, {
    headers: { Accept: "application/json" },
  });
  if (!response.ok) throw new Error(await parseError(response));
  return (await response.json()) as OpsHealthDetail;
}

export async function analyzeMessage(params: {
  token: string;
  mailboxProfileId: string;
  messageId: string;
  subject: string;
  body: string;
  sender: string;
  attachmentNames: string[];
  includeDraft?: boolean;
}): Promise<SuggestionOut> {
  const response = await fetch(
    `${hubBaseUrl()}/v1/mailbox_profiles/${params.mailboxProfileId}/analyze`,
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${params.token}`,
        "Content-Type": "application/json",
        Accept: "application/json",
      },
      body: JSON.stringify({
        message_id: params.messageId,
        include_draft: params.includeDraft !== false,
        subject: params.subject,
        body: params.body,
        sender: params.sender,
        attachment_names: params.attachmentNames,
      }),
    }
  );
  if (!response.ok) throw new Error(await parseError(response));
  return (await response.json()) as SuggestionOut;
}

export async function submitFeedback(params: {
  token: string;
  mailboxProfileId: string;
  suggestionId: string;
  outcome: "accept" | "edit" | "reject" | "reroute";
  editedDraft?: string;
  correctedRouteEmail?: string;
  correctedRouteName?: string;
  teach?: boolean;
}): Promise<void> {
  const response = await fetch(
    `${hubBaseUrl()}/v1/mailbox_profiles/${params.mailboxProfileId}/feedback`,
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${params.token}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        suggestion_id: params.suggestionId,
        outcome: params.outcome,
        edited_draft: params.editedDraft,
        corrected_route_email: params.correctedRouteEmail,
        corrected_route_name: params.correctedRouteName,
        teach: params.teach || false,
      }),
    }
  );
  if (!response.ok) throw new Error(await parseError(response));
}

export async function confirmOutbound(params: {
  token: string;
  mailboxProfileId: string;
  suggestionId: string;
  idempotencyKey: string;
  action: "send" | "forward";
  recipients: string[];
  subject?: string;
  body?: string;
  aiAssisted: boolean;
}): Promise<{ idempotent_replay: boolean; ai_disclosure_applied: boolean }> {
  const response = await fetch(
    `${hubBaseUrl()}/v1/mailbox_profiles/${params.mailboxProfileId}/confirm-outbound`,
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${params.token}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        suggestion_id: params.suggestionId,
        idempotency_key: params.idempotencyKey,
        action: params.action,
        recipients: params.recipients,
        subject: params.subject,
        body: params.body,
        ai_assisted: params.aiAssisted,
      }),
    }
  );
  if (!response.ok) throw new Error(await parseError(response));
  return (await response.json()) as {
    idempotent_replay: boolean;
    ai_disclosure_applied: boolean;
  };
}

export async function confirmSchedule(params: {
  token: string;
  mailboxProfileId: string;
  suggestionId: string;
  idempotencyKey: string;
  slotStart: string;
  slotEnd: string;
  attendees?: string[];
}): Promise<{ status: string; graph_event_id: string | null; idempotent_replay: boolean }> {
  const response = await fetch(
    `${hubBaseUrl()}/v1/mailbox_profiles/${params.mailboxProfileId}/confirm-schedule`,
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${params.token}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        suggestion_id: params.suggestionId,
        idempotency_key: params.idempotencyKey,
        slot_start: params.slotStart,
        slot_end: params.slotEnd,
        attendees: params.attendees,
      }),
    }
  );
  if (!response.ok) throw new Error(await parseError(response));
  return (await response.json()) as {
    status: string;
    graph_event_id: string | null;
    idempotent_replay: boolean;
  };
}

export function getHubBaseUrl(): string {
  return hubBaseUrl();
}

export type HistoryProfileStatus = "not_started" | "syncing" | "ready" | "failed";
export type HistorySyncPhase =
  | "not_started"
  | "fetching"
  | "indexing"
  | "ready"
  | "failed";

export interface HistorySyncProgress {
  history_status: HistoryProfileStatus;
  history_sync_error: string | null;
  history_chunk_count: number | null;
  history_sync_phase: HistorySyncPhase;
  history_messages_fetched: number;
  history_messages_target: number;
  history_sync_started_at?: string | null;
}

export async function syncMailboxIndex(params: {
  token: string;
  mailboxProfileId: string;
  maxMessages?: number;
  /** false = hub starts sync in background (Outlook open path). */
  wait?: boolean;
}): Promise<
  HistorySyncProgress & {
    indexed_count: number;
    total_chunks: number | null;
    started: boolean;
  }
> {
  const response = await fetch(
    `${hubBaseUrl()}/v1/mailbox_profiles/${params.mailboxProfileId}/index/sync`,
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${params.token}`,
        "Content-Type": "application/json",
        Accept: "application/json",
      },
      body: JSON.stringify({
        max_messages: params.maxMessages ?? 3000,
        wait: params.wait ?? true,
      }),
    }
  );
  if (!response.ok) throw new Error(await parseError(response));
  const data = (await response.json()) as {
    indexed_count: number;
    total_chunks?: number | null;
    history_status?: HistoryProfileStatus;
    history_sync_error?: string | null;
    started?: boolean;
    history_sync_phase?: HistorySyncPhase;
    history_messages_fetched?: number;
    history_messages_target?: number;
    history_chunk_count?: number | null;
    history_sync_started_at?: string | null;
  };
  return {
    indexed_count: data.indexed_count,
    total_chunks: data.total_chunks ?? null,
    history_status: data.history_status ?? "not_started",
    history_sync_error: data.history_sync_error ?? null,
    started: data.started ?? true,
    history_chunk_count: data.history_chunk_count ?? data.total_chunks ?? null,
    history_sync_phase: data.history_sync_phase ?? "not_started",
    history_messages_fetched: data.history_messages_fetched ?? 0,
    history_messages_target: data.history_messages_target ?? 0,
    history_sync_started_at: data.history_sync_started_at ?? null,
  };
}

export async function fetchMailboxProfile(params: {
  token: string;
  mailboxProfileId: string;
}): Promise<HistorySyncProgress> {
  const response = await fetch(
    `${hubBaseUrl()}/v1/mailbox_profiles/${params.mailboxProfileId}`,
    {
      headers: {
        Authorization: `Bearer ${params.token}`,
        Accept: "application/json",
      },
    }
  );
  if (!response.ok) throw new Error(await parseError(response));
  const data = (await response.json()) as {
    history_status?: HistoryProfileStatus;
    history_sync_error?: string | null;
    history_chunk_count?: number | null;
    history_sync_phase?: HistorySyncPhase;
    history_messages_fetched?: number;
    history_messages_target?: number;
    history_sync_started_at?: string | null;
  };
  return {
    history_status: data.history_status ?? "not_started",
    history_sync_error: data.history_sync_error ?? null,
    history_chunk_count: data.history_chunk_count ?? null,
    history_sync_phase: data.history_sync_phase ?? "not_started",
    history_messages_fetched: data.history_messages_fetched ?? 0,
    history_messages_target: data.history_messages_target ?? 0,
    history_sync_started_at: data.history_sync_started_at ?? null,
  };
}

export interface ProfileInspect {
  id: string;
  email: string;
  kind: string;
  connection_status: string;
  connection_error: string | null;
  history_status: HistoryProfileStatus;
  last_history_sync_at: string | null;
  history_sync_error: string | null;
  history_chunk_count: number;
  indexed_message_count: number;
  history_sync_phase?: HistorySyncPhase;
  history_messages_fetched?: number;
  history_messages_target?: number;
  routes: Array<{
    pattern_key: string;
    route_email: string;
    route_name: string | null;
    weight: number;
  }>;
  behavior_summary: {
    text: string | null;
    status: string;
    error: string | null;
  };
}

export async function inspectMailboxProfile(params: {
  token: string;
  mailboxProfileId: string;
  includeSummary?: boolean;
}): Promise<ProfileInspect> {
  const qs =
    params.includeSummary === false ? "?include_summary=false" : "?include_summary=true";
  const response = await fetch(
    `${hubBaseUrl()}/v1/mailbox_profiles/${params.mailboxProfileId}/inspect${qs}`,
    {
      headers: {
        Authorization: `Bearer ${params.token}`,
        Accept: "application/json",
      },
    }
  );
  if (!response.ok) {
    const err = new Error(await parseError(response)) as Error & { status?: number };
    err.status = response.status;
    throw err;
  }
  return (await response.json()) as ProfileInspect;
}

export async function connectMailbox(params: {
  token: string;
  email: string;
  kind: "personal" | "shared";
}): Promise<{ id: string }> {
  const response = await fetch(`${hubBaseUrl()}/v1/mailbox_profiles/connect`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${params.token}`,
      "Content-Type": "application/json",
      Accept: "application/json",
    },
    body: JSON.stringify({ email: params.email, kind: params.kind }),
  });
  if (!response.ok) throw new Error(await parseError(response));
  const data = (await response.json()) as { mailbox_profile: { id: string } };
  return { id: data.mailbox_profile.id };
}
