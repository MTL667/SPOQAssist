/**
 * Hub Bearer acquisition: Office SSO first, localStorage fallback for sideload/dev.
 * Never logs the token.
 */

const PROFILE_KEY = "spoq_mailbox_profile_id";
const PROFILE_EMAIL_KEY = "spoq_mailbox_profile_email";
const DEV_TOKEN_KEY = "spoq_access_token";

export type SsoErrorInfo = {
  code: string;
  message: string;
};

export type TokenAcquireResult =
  | { ok: true; token: string; source: "sso" | "stored" }
  | { ok: false; ssoError: SsoErrorInfo | null; hasStoredToken: boolean };

function describeSsoError(err: unknown): SsoErrorInfo {
  if (err && typeof err === "object") {
    const e = err as { code?: unknown; message?: unknown; name?: unknown };
    const code = String(e.code ?? e.name ?? "sso_error");
    const raw = String(e.message ?? "Office SSO failed");
    // Never display anything that could embed a bearer/JWT fragment.
    const looksSensitive =
      /eyJ|bearer\s+[A-Za-z0-9_-]{20,}|[A-Za-z0-9_-]{40,}\.[A-Za-z0-9_-]{10,}/i.test(raw);
    const message = looksSensitive
      ? "Office SSO failed (details omitted)."
      : raw.slice(0, 240);
    return { code, message };
  }
  return { code: "sso_error", message: "Office SSO failed" };
}

export async function acquireHubAccessTokenDetailed(): Promise<TokenAcquireResult> {
  const sso = await tryOfficeSsoDetailed();
  if (sso.token) {
    return { ok: true, token: sso.token, source: "sso" };
  }
  const stored = readDevToken();
  if (stored) {
    return { ok: true, token: stored, source: "stored" };
  }
  return { ok: false, ssoError: sso.error, hasStoredToken: false };
}

/** Convenience wrapper used by most call sites. */
export async function acquireHubAccessToken(): Promise<string | null> {
  const result = await acquireHubAccessTokenDetailed();
  return result.ok ? result.token : null;
}

async function tryOfficeSsoDetailed(): Promise<{
  token: string | null;
  error: SsoErrorInfo | null;
}> {
  try {
    const auth = Office?.auth;
    if (!auth || typeof auth.getAccessToken !== "function") {
      return {
        token: null,
        error: {
          code: "sso_unavailable",
          message: "Office.auth.getAccessToken is not available in this host.",
        },
      };
    }
    const token = await auth.getAccessToken({
      allowSignInPrompt: true,
      allowConsentPrompt: true,
      forMSGraphAccess: false,
    });
    if (!token) {
      return {
        token: null,
        error: { code: "sso_empty", message: "Office SSO returned an empty token." },
      };
    }
    return { token, error: null };
  } catch (err) {
    return { token: null, error: describeSsoError(err) };
  }
}

function readDevToken(): string | null {
  try {
    const v = window.localStorage.getItem(DEV_TOKEN_KEY);
    return v && v.trim() ? v.trim() : null;
  } catch {
    return null;
  }
}

export function hasStoredAccessToken(): boolean {
  return Boolean(readDevToken());
}

export function setStoredAccessToken(token: string): void {
  const trimmed = token.trim();
  if (!trimmed) {
    throw new Error("Token is empty.");
  }
  window.localStorage.setItem(DEV_TOKEN_KEY, trimmed);
}

export function clearStoredAccessToken(): void {
  try {
    window.localStorage.removeItem(DEV_TOKEN_KEY);
  } catch {
    /* ignore */
  }
}

export function getMailboxProfileId(): string | null {
  try {
    return window.localStorage.getItem(PROFILE_KEY);
  } catch {
    return null;
  }
}

export function getCachedMailboxEmail(): string | null {
  try {
    return window.localStorage.getItem(PROFILE_EMAIL_KEY);
  } catch {
    return null;
  }
}

export function setMailboxProfileId(id: string, email: string): void {
  try {
    window.localStorage.setItem(PROFILE_KEY, id);
    window.localStorage.setItem(PROFILE_EMAIL_KEY, email.toLowerCase());
  } catch {
    /* ignore */
  }
}

export function clearMailboxProfileCache(): void {
  try {
    window.localStorage.removeItem(PROFILE_KEY);
    window.localStorage.removeItem(PROFILE_EMAIL_KEY);
  } catch {
    /* ignore */
  }
}

export function getOfficeUserEmail(): string | null {
  try {
    return Office?.context?.mailbox?.userProfile?.emailAddress || null;
  } catch {
    return null;
  }
}
