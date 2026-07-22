import React from "react";
import { Button, makeStyles, Spinner, Text, Title3 } from "@fluentui/react-components";
import type { ProfileInspect } from "../api/client";

const useStyles = makeStyles({
  panel: {
    display: "flex",
    flexDirection: "column",
    gap: "10px",
    marginTop: "16px",
    paddingTop: "12px",
    borderTop: "1px solid #D5DEE3",
  },
  meta: { color: "#5B6B73" },
  block: {
    display: "flex",
    flexDirection: "column",
    gap: "2px",
  },
  mono: {
    fontFamily: "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace",
    fontSize: "12px",
    wordBreak: "break-all",
  },
  summary: {
    whiteSpace: "pre-wrap",
    color: "#1A2B33",
  },
  row: {
    display: "flex",
    flexWrap: "wrap",
    gap: "8px",
    marginTop: "4px",
  },
});

function shortId(id: string): string {
  return id.length > 12 ? `${id.slice(0, 8)}…${id.slice(-4)}` : id;
}

export function CheckProfilePanel({
  data,
  loading,
  error,
  onClose,
  onRetrySummary,
}: {
  data: ProfileInspect | null;
  loading: boolean;
  error: string | null;
  onClose: () => void;
  onRetrySummary: () => void;
}): React.JSX.Element {
  const styles = useStyles();
  return (
    <section className={styles.panel} aria-label="Check mailbox profile">
      <Title3>Mailbox-profiel</Title3>
      {loading && !data ? (
        <div className={styles.row}>
          <Spinner size="tiny" />
          <Text className={styles.meta}>Profiel laden…</Text>
        </div>
      ) : null}
      {error ? (
        <Text className={styles.meta} block>
          {error}
        </Text>
      ) : null}
      {data ? (
        <>
          <div className={styles.block}>
            <Text weight="semibold">Profiel-id</Text>
            <Text className={styles.mono} title={data.id}>
              {shortId(data.id)}
            </Text>
          </div>
          <div className={styles.block}>
            <Text weight="semibold">Mailbox</Text>
            <Text>
              {data.email} · {data.kind}
            </Text>
          </div>
          <div className={styles.block}>
            <Text weight="semibold">Connectie</Text>
            <Text>
              {data.connection_status}
              {data.connection_error ? ` — ${data.connection_error}` : ""}
            </Text>
          </div>
          <div className={styles.block}>
            <Text weight="semibold">History</Text>
            <Text>
              {data.history_status} · {data.history_chunk_count} chunks ·{" "}
              {data.indexed_message_count} Sent berichten
            </Text>
            <Text className={styles.meta} block>
              Laatste sync: {data.last_history_sync_at || "—"}
            </Text>
            {data.history_sync_error ? (
              <Text className={styles.meta} block>
                Syncfout: {data.history_sync_error}
              </Text>
            ) : null}
          </div>
          <div className={styles.block}>
            <Text weight="semibold">Geleerde routes</Text>
            {data.routes.length === 0 ? (
              <Text className={styles.meta}>Nog geen geleerde doorstuurroutes.</Text>
            ) : (
              data.routes.map((r, idx) => (
                <Text key={`${r.pattern_key}-${r.route_email}-${idx}`} block>
                  {r.pattern_key} → {r.route_email}
                  {r.route_name ? ` (${r.route_name})` : ""} · gewicht {r.weight}
                </Text>
              ))
            )}
          </div>
          <div className={styles.block}>
            <Text weight="semibold">Gedragssamenvatting</Text>
            {loading ? (
              <div className={styles.row}>
                <Spinner size="tiny" />
                <Text className={styles.meta}>Samenvatting vernieuwen…</Text>
              </div>
            ) : null}
            {data.behavior_summary.status === "error" ? (
              <>
                <Text className={styles.meta} block>
                  {data.behavior_summary.error || "Samenvatting mislukt."}
                </Text>
                <Button appearance="secondary" onClick={onRetrySummary} disabled={loading}>
                  Opnieuw samenvatten
                </Button>
              </>
            ) : (
              <Text className={styles.summary} block>
                {data.behavior_summary.text || "Geen samenvatting."}
              </Text>
            )}
          </div>
        </>
      ) : null}
      <div className={styles.row}>
        <Button appearance="secondary" onClick={onClose}>
          Sluiten
        </Button>
      </div>
    </section>
  );
}
