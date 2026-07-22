import React, { useEffect, useRef } from "react";
import { Button, makeStyles, Text, Title3 } from "@fluentui/react-components";

const useStyles = makeStyles({
  overlay: {
    position: "fixed",
    inset: 0,
    backgroundColor: "rgba(26, 43, 51, 0.45)",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    padding: "16px",
    zIndex: 1000,
  },
  dialog: {
    backgroundColor: "#F8FBFC",
    padding: "20px",
    maxWidth: "420px",
    width: "100%",
    display: "flex",
    flexDirection: "column",
    gap: "10px",
    outline: "2px solid #135067",
  },
  confirm: {
    backgroundColor: "#135067",
    color: "#fff",
    minHeight: "40px",
  },
  actions: {
    display: "flex",
    gap: "8px",
    marginTop: "8px",
  },
  disclosure: {
    color: "#1A2B33",
    fontWeight: 600,
  },
});

export interface ConfirmOutboundDialogProps {
  action: "send" | "forward";
  recipients: string[];
  draftExcerpt: string;
  aiAssisted: boolean;
  onConfirm: () => void;
  onCancel: () => void;
  busy?: boolean;
}

export function ConfirmOutboundDialog({
  action,
  recipients,
  draftExcerpt,
  aiAssisted,
  onConfirm,
  onCancel,
  busy,
}: ConfirmOutboundDialogProps): React.JSX.Element {
  const styles = useStyles();
  const dialogRef = useRef<HTMLDivElement>(null);
  const cancelRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    cancelRef.current?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        onCancel();
        return;
      }
      if (e.key !== "Tab" || !dialogRef.current) return;
      const focusable = dialogRef.current.querySelectorAll<HTMLElement>(
        'button:not([disabled]), [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
      );
      if (!focusable.length) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onCancel]);

  return (
    <div className={styles.overlay} role="presentation">
      <div
        ref={dialogRef}
        className={styles.dialog}
        role="dialog"
        aria-modal="true"
        aria-labelledby="confirm-outbound-title"
      >
        <Title3 id="confirm-outbound-title">Confirm {action}</Title3>
        <Text block>Recipients: {recipients.join(", ")}</Text>
        <Text block>Excerpt: {draftExcerpt.slice(0, 180) || "(empty)"}</Text>
        {aiAssisted ? (
          <Text className={styles.disclosure} block>
            AI disclosure: this outbound message was prepared with SpoqSense assistance and will
            include a disclosure footer.
          </Text>
        ) : null}
        <div className={styles.actions}>
          <Button className={styles.confirm} onClick={onConfirm} disabled={busy}>
            Confirm
          </Button>
          <Button appearance="subtle" ref={cancelRef} onClick={onCancel} disabled={busy}>
            Cancel
          </Button>
        </div>
      </div>
    </div>
  );
}
