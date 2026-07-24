import React from "react";
import { Button, makeStyles } from "@fluentui/react-components";

const useStyles = makeStyles({
  row: {
    display: "flex",
    flexWrap: "wrap",
    gap: "8px",
    marginTop: "12px",
  },
  accept: {
    backgroundColor: "#42AB9A",
    color: "#fff",
    minHeight: "40px",
  },
});

export interface FeedbackControlsProps {
  compact?: boolean;
  onAccept: () => void;
  onEdit: () => void;
  onReject: () => void;
  onChangeRoute: () => void;
  onGenerateResponse?: () => void;
  onSchedule?: () => void;
  showChangeRoute?: boolean;
  showGenerateResponse?: boolean;
  showSchedule?: boolean;
  /** When true, Accept is hidden — e.g. reply path with no draft yet. */
  hideAccept?: boolean;
}

export function FeedbackControls({
  onAccept,
  onEdit,
  onReject,
  onChangeRoute,
  onGenerateResponse,
  onSchedule,
  showChangeRoute = true,
  showGenerateResponse = false,
  showSchedule = false,
  hideAccept = false,
}: FeedbackControlsProps): React.JSX.Element {
  const styles = useStyles();
  return (
    <div className={styles.row}>
      {showGenerateResponse && onGenerateResponse ? (
        <Button className={styles.accept} onClick={onGenerateResponse}>
          Generate response
        </Button>
      ) : null}
      {showSchedule && onSchedule ? (
        <Button className={styles.accept} onClick={onSchedule}>
          Schedule
        </Button>
      ) : null}
      {!hideAccept ? (
        <Button
          className={showGenerateResponse || showSchedule ? undefined : styles.accept}
          appearance={showGenerateResponse || showSchedule ? "secondary" : undefined}
          onClick={onAccept}
        >
          Accept
        </Button>
      ) : null}
      <Button appearance="secondary" onClick={onEdit}>
        Edit
      </Button>
      {showChangeRoute ? (
        <Button appearance="secondary" onClick={onChangeRoute}>
          Change route
        </Button>
      ) : null}
      <Button appearance="outline" onClick={onReject}>
        Reject
      </Button>
    </div>
  );
}
