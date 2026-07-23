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
  const [elapsedSec, setElapsedSec] = useState(0);
  const reduceMotion =
    typeof window !== "undefined" &&
    window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

  useEffect(() => {
    const started = performance.now();
    const id = window.setInterval(() => {
      setElapsedSec((performance.now() - started) / 1000);
    }, 250);
    return () => window.clearInterval(id);
  }, []);

  const label =
    elapsedSec < 10 ? `${elapsedSec.toFixed(1)}s` : `${Math.round(elapsedSec)}s`;

  return (
    <div className={styles.root} aria-live="polite" aria-busy="true">
      <Spinner
        label={`Analyzing message… ${label}`}
        appearance={reduceMotion ? "primary" : undefined}
      />
      {elapsedSec >= 4 ? (
        <Text className={styles.hint} block>
          Still working… {label}
        </Text>
      ) : null}
    </div>
  );
}
