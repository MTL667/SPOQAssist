import React from "react";
import { Button, makeStyles, Text, Title3 } from "@fluentui/react-components";

const useStyles = makeStyles({
  root: {
    display: "flex",
    flexDirection: "column",
    gap: "12px",
    padding: "16px",
    minHeight: "100vh",
    boxSizing: "border-box",
    backgroundColor: "#F3F7FA",
  },
  message: {
    color: "#5B6B73",
  },
  actions: {
    marginTop: "8px",
  },
});

export interface HubUnavailableProps {
  message?: string;
  onRetry: () => void;
  retrying?: boolean;
}

/**
 * UX-DR6 — clear unavailable + Retry; no stale Accept / suggestions.
 */
export function HubUnavailable({
  message,
  onRetry,
  retrying = false,
}: HubUnavailableProps): React.JSX.Element {
  const styles = useStyles();
  return (
    <main className={styles.root} aria-live="polite">
      <Title3>SpoqSense unavailable</Title3>
      <Text className={styles.message} block>
        {message ||
          "The SpoqSense hub cannot be reached. Check Tailscale/VPN and try again."}
      </Text>
      <Text className={styles.message} block>
        IT: verify hub health at GET /health (no mailbox content).
      </Text>
      <div className={styles.actions}>
        <Button appearance="primary" onClick={onRetry} disabled={retrying}>
          {retrying ? "Retrying…" : "Retry"}
        </Button>
      </div>
    </main>
  );
}
