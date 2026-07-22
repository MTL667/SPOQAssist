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
  const fromEnv =
    typeof process !== "undefined" && process.env && process.env.HUB_BASE_URL
      ? process.env.HUB_BASE_URL
      : "";
  return (fromEnv || "http://localhost:8000").replace(/\/$/, "");
}

async function parseError(response: Response): Promise<string> {
  try {
    const data = (await response.json()) as { error?: { message?: string; code?: string } };
    if (data.error?.message) return data.error.message;
  } catch {
    /* ignore */
  }
  return `HTTP ${response.status}`;
}

export async function fetchHealth(signal?: AbortSignal): Promise<HealthResponse> {
  const response = await fetch(`${hubBaseUrl()}/health`, {
    method: "GET",
    signal,
    headers: { Accept: "application/json" },
  });
  if (!response.ok) throw new Error(`Hub health HTTP ${response.status}`);
  return (await response.json()) as HealthResponse;
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
    `${hubBaseUrl()}/v1/mailbox_profiles/${params.mailboxProfileId}/messages/${encodeURIComponent(params.messageId)}/analyze`,
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${params.token}`,
        "Content-Type": "application/json",
        Accept: "application/json",
      },
      body: JSON.stringify({
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

export function getHubBaseUrl(): string {
  return hubBaseUrl();
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
