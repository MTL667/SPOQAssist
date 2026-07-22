import React, { useEffect, useState } from "react";
import { makeStyles, Spinner, Text } from "@fluentui/react-components";

const useStyles = makeStyles({
  root: {
    display: "flex",
    flexDirection: "column",
    gap: "12px",
    padding: "8px 0",
  },
  hint: { color: "#5B6B73" },
});

export function AnalyzingState(): React.JSX.Element {
  const styles = useStyles();
  const [slow, setSlow] = useState(false);
  const reduceMotion =
    typeof window !== "undefined" &&
    window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

  useEffect(() => {
    const t = window.setTimeout(() => setSlow(true), 4000);
    return () => window.clearTimeout(t);
  }, []);

  return (
    <div className={styles.root} aria-live="polite" aria-busy="true">
      <Spinner label="Analyzing message…" appearance={reduceMotion ? "primary" : undefined} />
      {slow ? (
        <Text className={styles.hint} block>
          Still working…
        </Text>
      ) : null}
    </div>
  );
}
