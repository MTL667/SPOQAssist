/**
 * Hub Bearer acquisition: Office SSO first, localStorage fallback for sideload/dev.
 * Never logs the token.
 */

const PROFILE_KEY = "spoq_mailbox_profile_id";
const PROFILE_EMAIL_KEY = "spoq_mailbox_profile_email";

export async function acquireHubAccessToken(): Promise<string | null> {
  const officeToken = await tryOfficeSso();
  if (officeToken) return officeToken;
  return readDevToken();
}

async function tryOfficeSso(): Promise<string | null> {
  try {
    const auth = Office?.auth;
    if (!auth || typeof auth.getAccessToken !== "function") return null;
    const token = await auth.getAccessToken({
      allowSignInPrompt: true,
      allowConsentPrompt: true,
      forMSGraphAccess: false,
    });
    return token || null;
  } catch {
    return null;
  }
}

function readDevToken(): string | null {
  try {
    return window.localStorage.getItem("spoq_access_token");
  } catch {
    return null;
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
