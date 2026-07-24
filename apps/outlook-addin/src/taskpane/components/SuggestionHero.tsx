import React from "react";
import { makeStyles, Text, Title3 } from "@fluentui/react-components";
import type { SuggestionViewModel } from "../state/paneState";
import { ActionsList } from "./ActionsList";
import { AttachmentSummaries } from "./AttachmentSummaries";
import { FeedbackControls } from "./FeedbackControls";
import { WhyExplanation } from "./WhyExplanation";

const useStyles = makeStyles({
  card: {
    display: "flex",
    flexDirection: "column",
    gap: "8px",
    padding: "12px 0",
  },
  meta: { color: "#5B6B73" },
  draft: {
    whiteSpace: "pre-wrap",
    marginTop: "8px",
    color: "#1A2B33",
  },
});

function primaryActionLabel(suggestion: SuggestionViewModel): string {
  // Never show "forward" as the action unless a real route exists.
  if (suggestion.suggestedRoute) return "forward";
  if (suggestion.actions?.includes("reply") || suggestion.draft) return "reply";
  if (suggestion.category === "forward") return "reply";
  return suggestion.category || "reply";
}

export function SuggestionHero({
  suggestion,
  onAccept,
  onEdit,
  onReject,
  onChangeRoute,
  onGenerateResponse,
  onSchedule,
  onDismissAction,
}: {
  suggestion: SuggestionViewModel;
  onAccept: () => void;
  onEdit: () => void;
  onReject: () => void;
  onChangeRoute: () => void;
  onGenerateResponse: () => void;
  onSchedule?: () => void;
  onDismissAction?: (actionId: string) => void;
}): React.JSX.Element {
  const styles = useStyles();
  const action = primaryActionLabel(suggestion);
  const hasDraft = Boolean(suggestion.draft);
  const canGenerate = !hasDraft && suggestion.historyStatus !== "none";
  const showSchedule =
    suggestion.category === "meeting" && (suggestion.proposedSlots?.length || 0) > 0;
  return (
    <section className={styles.card} aria-label="High confidence suggestion">
      <Title3>Suggested action</Title3>
      <Text className={styles.meta} block>
        {action} · {suggestion.priority} · High confidence
      </Text>
      {suggestion.suggestedRoute ? (
        <Text block>
          Route to {suggestion.suggestedRoute.displayName || suggestion.suggestedRoute.email} (
          {suggestion.suggestedRoute.email})
        </Text>
      ) : null}
      {suggestion.availabilityNote ? (
        <Text className={styles.meta} block>
          {suggestion.availabilityNote}
        </Text>
      ) : null}
      {hasDraft ? <Text className={styles.draft}>{suggestion.draft}</Text> : null}
      {!hasDraft && suggestion.historyStatus === "none" ? (
        <Text className={styles.meta} block>
          No grounded draft yet — mailbox history is still empty or syncing.
        </Text>
      ) : null}
      {!hasDraft && canGenerate ? (
        <Text className={styles.meta} block>
          {suggestion.draftError ||
            "No draft yet. Generate a response, or edit one yourself."}
        </Text>
      ) : null}
      {suggestion.historyStatus === "limited" ? (
        <Text className={styles.meta} block>
          Limited sent history — draft may be generic.
        </Text>
      ) : null}
      <ActionsList actions={suggestion.extractedActions} onDismiss={onDismissAction} />
      <AttachmentSummaries summaries={suggestion.attachmentSummaries} />
      <WhyExplanation items={suggestion.why} />
      <FeedbackControls
        onAccept={onAccept}
        onEdit={onEdit}
        onReject={onReject}
        onChangeRoute={onChangeRoute}
        onGenerateResponse={onGenerateResponse}
        onSchedule={onSchedule}
        showChangeRoute={Boolean(suggestion.suggestedRoute)}
        showGenerateResponse={canGenerate}
        showSchedule={showSchedule}
        hideAccept={!hasDraft && !suggestion.suggestedRoute}
      />
    </section>
  );
}
