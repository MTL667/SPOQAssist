import React from "react";
import { makeStyles, Text, Title3 } from "@fluentui/react-components";
import type { SuggestionViewModel } from "../state/paneState";
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
}: {
  suggestion: SuggestionViewModel;
  onAccept: () => void;
  onEdit: () => void;
  onReject: () => void;
  onChangeRoute: () => void;
}): React.JSX.Element {
  const styles = useStyles();
  const action = primaryActionLabel(suggestion);
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
      {suggestion.draft ? <Text className={styles.draft}>{suggestion.draft}</Text> : null}
      {suggestion.historyStatus === "none" || suggestion.historyStatus === "limited" ? (
        <Text className={styles.meta} block>
          Limited sent history — draft may be generic.
        </Text>
      ) : null}
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
