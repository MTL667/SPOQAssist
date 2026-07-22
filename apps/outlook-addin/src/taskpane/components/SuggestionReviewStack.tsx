import React from "react";
import { makeStyles, Text, Title3 } from "@fluentui/react-components";
import type { SuggestionViewModel } from "../state/paneState";
import { FeedbackControls } from "./FeedbackControls";
import { WhyExplanation } from "./WhyExplanation";

const useStyles = makeStyles({
  stack: {
    display: "flex",
    flexDirection: "column",
    gap: "12px",
    padding: "12px 0",
  },
  block: {
    display: "flex",
    flexDirection: "column",
    gap: "4px",
  },
  meta: { color: "#5B6B73" },
  draft: { whiteSpace: "pre-wrap" },
});

export function SuggestionReviewStack({
  suggestion,
  onAccept,
  onEdit,
  onReject,
  onChangeRoute,
}: {
  suggestion: SuggestionViewModel;
  onAccept: () => void;
  onEdit: () => void;
  onReject: () => void;
  onChangeRoute: () => void;
}): React.JSX.Element {
  const styles = useStyles();
  return (
    <section className={styles.stack} aria-label="Review suggestions">
      <Title3>Review suggestions</Title3>
      <Text className={styles.meta} block>
        Confidence: {suggestion.confidence} (not color-only — label shown)
      </Text>
      <div className={styles.block}>
        <Text weight="semibold">Category</Text>
        <Text>{suggestion.category}</Text>
      </div>
      <div className={styles.block}>
        <Text weight="semibold">Priority</Text>
        <Text>{suggestion.priority}</Text>
      </div>
      {suggestion.suggestedRoute ? (
        <div className={styles.block}>
          <Text weight="semibold">Suggested route</Text>
          <Text>{suggestion.suggestedRoute.email}</Text>
        </div>
      ) : null}
      {suggestion.draft ? (
        <div className={styles.block}>
          <Text weight="semibold">Draft</Text>
          <Text className={styles.draft}>{suggestion.draft}</Text>
        </div>
      ) : (
        <Text className={styles.meta}>
          {suggestion.historyStatus === "none"
            ? "No grounded draft yet — mailbox history is still empty or syncing."
            : "No draft generated for this message. Try Analyze again."}
        </Text>
      )}
      <WhyExplanation items={suggestion.why} />
      <FeedbackControls
        onAccept={onAccept}
        onEdit={onEdit}
        onReject={onReject}
        onChangeRoute={onChangeRoute}
        showChangeRoute={Boolean(suggestion.suggestedRoute)}
      />
    </section>
  );
}
