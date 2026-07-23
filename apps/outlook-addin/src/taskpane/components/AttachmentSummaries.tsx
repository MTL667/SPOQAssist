import React from "react";
import { Badge, makeStyles, Text, tokens } from "@fluentui/react-components";
import { AttachRegular, ScanRegular } from "@fluentui/react-icons";
import type { AttachmentSummaryViewModel } from "../state/paneState";

const useStyles = makeStyles({
  container: {
    display: "flex",
    flexDirection: "column",
    gap: "4px",
    marginTop: "8px",
  },
  row: {
    display: "flex",
    alignItems: "flex-start",
    gap: "6px",
    padding: "3px 0",
  },
  filename: {
    fontWeight: 600,
    fontSize: "12px",
  },
  summary: {
    fontSize: "12px",
    color: tokens.colorNeutralForeground2,
  },
  meta: {
    fontSize: "11px",
    color: tokens.colorNeutralForeground3,
  },
});

export function AttachmentSummaries({
  summaries,
}: {
  summaries: AttachmentSummaryViewModel[];
}): React.JSX.Element | null {
  if (!summaries || summaries.length === 0) return null;

  const styles = useStyles();

  return (
    <section className={styles.container} aria-label="Attachment summaries">
      {summaries.map((att, idx) => (
        <div key={idx} className={styles.row}>
          {att.isScan ? <ScanRegular fontSize={14} /> : <AttachRegular fontSize={14} />}
          <div>
            <Text className={styles.filename} block>
              {att.filename}
              {att.pageCount ? ` (${att.pageCount} pages)` : ""}
              {att.isScan ? (
                <Badge appearance="outline" size="tiny" style={{ marginLeft: 4 }}>
                  scan
                </Badge>
              ) : null}
            </Text>
            <Text className={styles.summary} block>
              {att.summary}
            </Text>
          </div>
        </div>
      ))}
    </section>
  );
}
