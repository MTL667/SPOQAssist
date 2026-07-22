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
  showChangeRoute?: boolean;
}

export function FeedbackControls({
  onAccept,
  onEdit,
  onReject,
  onChangeRoute,
  showChangeRoute = true,
}: FeedbackControlsProps): React.JSX.Element {
  const styles = useStyles();
  return (
    <div className={styles.row}>
      <Button className={styles.accept} onClick={onAccept}>
        Accept
      </Button>
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
