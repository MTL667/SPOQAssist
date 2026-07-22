import React, { useEffect, useState } from "react";
import { makeStyles, Text, Title3 } from "@fluentui/react-components";
import { fetchOpsHealth, type OpsHealthDetail } from "../api/client";

const useStyles = makeStyles({
  root: {
    marginTop: "24px",
    paddingTop: "12px",
    borderTop: "1px solid #CDEFE0",
    display: "flex",
    flexDirection: "column",
    gap: "4px",
  },
  meta: { color: "#5B6B73", fontSize: "12px" },
});

/** UX-DR15 — optional non-mail ops surface */
export function OpsHealthStatus(): React.JSX.Element {
  const styles = useStyles();
  const [detail, setDetail] = useState<OpsHealthDetail | null>(null);

  useEffect(() => {
    void fetchOpsHealth()
      .then(setDetail)
      .catch(() => setDetail({ status: "down" }));
  }, []);

  return (
    <aside className={styles.root} aria-label="Ops health">
      <Title3>Ops health</Title3>
      <Text className={styles.meta} block>
        Hub: {detail?.status || "…"} · Graph: {detail?.graph_mode || "—"} · Inference:{" "}
        {detail?.inference?.status || "—"} ({detail?.inference?.mode || "—"})
      </Text>
      <Text className={styles.meta} block>
        No mailbox content is shown here. Register: {detail?.register_doc || "docs/…"}
      </Text>
    </aside>
  );
}
