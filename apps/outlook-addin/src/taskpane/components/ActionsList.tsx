import React from "react";
import {
  Badge,
  Button,
  makeStyles,
  Text,
  tokens,
} from "@fluentui/react-components";
import { DismissRegular } from "@fluentui/react-icons";
import type { ActionItemViewModel } from "../state/paneState";

const useStyles = makeStyles({
  container: {
    display: "flex",
    flexDirection: "column",
    gap: "6px",
    marginTop: "8px",
  },
  actionRow: {
    display: "flex",
    alignItems: "center",
    gap: "8px",
    padding: "4px 0",
  },
  description: {
    flex: 1,
    fontSize: "12px",
  },
  dueDate: {
    fontSize: "11px",
    color: tokens.colorNeutralForeground3,
  },
  urgent: {
    fontWeight: 600,
    color: tokens.colorPaletteRedForeground1,
  },
});

function actionBadgeColor(
  actionType: string
): "brand" | "danger" | "important" | "informative" {
  switch (actionType) {
    case "deadline":
      return "danger";
    case "todo":
      return "brand";
    case "meeting":
      return "important";
    case "question":
      return "informative";
    default:
      return "informative";
  }
}

function actionLabel(actionType: string): string {
  switch (actionType) {
    case "deadline":
      return "Deadline";
    case "todo":
      return "To-do";
    case "meeting":
      return "Meeting";
    case "question":
      return "Question";
    default:
      return actionType;
  }
}

function isUrgent(action: ActionItemViewModel): boolean {
  if (action.actionType !== "deadline" || !action.dueDate) return false;
  const due = new Date(action.dueDate);
  const now = new Date();
  const diffDays = (due.getTime() - now.getTime()) / (1000 * 60 * 60 * 24);
  return diffDays <= 2 && diffDays >= 0;
}

export function ActionsList({
  actions,
  onDismiss,
}: {
  actions: ActionItemViewModel[];
  onDismiss?: (actionId: string) => void;
}): React.JSX.Element | null {
  const styles = useStyles();
  const visible = actions.filter((a) => !a.dismissed);

  if (visible.length === 0) return null;

  return (
    <section className={styles.container} aria-label="Extracted actions">
      {visible.map((action, idx) => (
        <div key={action.id || idx} className={styles.actionRow}>
          <Badge
            appearance="filled"
            color={actionBadgeColor(action.actionType)}
            size="small"
          >
            {actionLabel(action.actionType)}
          </Badge>
          <Text
            className={`${styles.description} ${isUrgent(action) ? styles.urgent : ""}`}
          >
            {action.description}
          </Text>
          {action.dueDate ? (
            <Text className={styles.dueDate}>{action.dueDate}</Text>
          ) : null}
          {onDismiss && action.id ? (
            <Button
              appearance="subtle"
              size="small"
              icon={<DismissRegular />}
              aria-label={`Dismiss action: ${action.description}`}
              onClick={() => onDismiss(action.id!)}
            />
          ) : null}
        </div>
      ))}
    </section>
  );
}
