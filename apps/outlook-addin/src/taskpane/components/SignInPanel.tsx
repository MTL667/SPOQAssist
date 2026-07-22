import React, { useMemo, useState } from "react";
import { Button, makeStyles, Text, Textarea, Title3 } from "@fluentui/react-components";
import type { SsoErrorInfo } from "../api/auth";
import { clearStoredAccessToken, setStoredAccessToken } from "../api/auth";

const useStyles = makeStyles({
  root: {
    display: "flex",
    flexDirection: "column",
    gap: "10px",
    marginTop: "12px",
    padding: "12px 0",
  },
  warn: { color: "#8A4B08" },
  meta: { color: "#5B6B73" },
  row: { display: "flex", gap: "8px", flexWrap: "wrap" },
  ok: { color: "#2F5D50" },
});

function looksLikeJwt(value: string): boolean {
  const parts = value.trim().split(".");
  return parts.length === 3 && parts.every((p) => p.length > 0);
}

export function SignInPanel({
  ssoError,
  onRetrySso,
  onTokenReady,
}: {
  ssoError: SsoErrorInfo | null;
  onRetrySso: () => void;
  onTokenReady: () => void;
}): React.JSX.Element {
  const styles = useStyles();
  const [draft, setDraft] = useState("");
  const [savedNote, setSavedNote] = useState<string | null>(null);
  const [localError, setLocalError] = useState<string | null>(null);
  const canSave = useMemo(() => looksLikeJwt(draft), [draft]);

  return (
    <section className={styles.root} aria-label="Sign in">
      <Title3>Sign in required</Title3>
      {ssoError ? (
        <Text className={styles.warn} block>
          Office SSO failed: {ssoError.code}
          {ssoError.message ? ` — ${ssoError.message}` : ""}
        </Text>
      ) : (
        <Text className={styles.meta} block>
          Office SSO did not return a token. Paste a hub access token for sideload, or retry SSO.
        </Text>
      )}
      <div className={styles.row}>
        <Button appearance="primary" onClick={onRetrySso}>
          Retry SSO
        </Button>
      </div>
      <Text weight="semibold">Paste hub access token (sideload)</Text>
      <Text className={styles.meta} block>
        Audience must match the hub ENTRA_API_AUDIENCE (api://localhost:3000/…). Token is stored only
        in this browser localStorage — never logged.
      </Text>
      <Textarea
        aria-label="Access token"
        value={draft}
        resize="vertical"
        onChange={(_, d) => {
          setDraft(d.value);
          setLocalError(null);
          setSavedNote(null);
        }}
        placeholder="eyJ…"
      />
      <div className={styles.row}>
        <Button
          appearance="secondary"
          disabled={!canSave}
          onClick={() => {
            try {
              setStoredAccessToken(draft);
              setDraft("");
              setSavedNote("Token saved (masked). Continuing…");
              setLocalError(null);
              onTokenReady();
            } catch (err) {
              setLocalError(err instanceof Error ? err.message : "Could not save token");
            }
          }}
        >
          Save token
        </Button>
        <Button
          appearance="subtle"
          onClick={() => {
            clearStoredAccessToken();
            setDraft("");
            setSavedNote("Stored token cleared. Retrying SSO…");
            setLocalError(null);
            onRetrySso();
          }}
        >
          Clear stored token
        </Button>
      </div>
      {localError ? (
        <Text className={styles.warn} block>
          {localError}
        </Text>
      ) : null}
      {savedNote ? (
        <Text className={styles.ok} block>
          {savedNote}
        </Text>
      ) : null}
    </section>
  );
}
