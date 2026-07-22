import React, { useMemo, useState } from "react";
import { Button, Input, makeStyles, Text, Title3 } from "@fluentui/react-components";

const useStyles = makeStyles({
  root: { display: "flex", flexDirection: "column", gap: "10px", padding: "8px 0" },
  list: { display: "flex", flexDirection: "column", gap: "6px" },
  row: { display: "flex", gap: "8px", flexWrap: "wrap" },
});

function normalizeEmail(value: string): string {
  return value.trim().replace(/\.+$/, "").toLowerCase();
}

function isValidEmail(value: string): boolean {
  const v = normalizeEmail(value);
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(v) && !v.endsWith("@contoso.com");
}

export function RoutePicker({
  onSelect,
  onCancel,
  priorRoutes = [],
}: {
  onSelect: (email: string, name: string, teach: boolean) => void;
  onCancel: () => void;
  /** Optional remembered/learned routes from the hub — never Contoso demo defaults. */
  priorRoutes?: { email: string; name: string }[];
}): React.JSX.Element {
  const styles = useStyles();
  const [query, setQuery] = useState("");
  const [teach, setTeach] = useState(true);
  const safePriors = useMemo(
    () =>
      priorRoutes.filter((r) => {
        const email = normalizeEmail(r.email || "");
        return Boolean(email) && !email.endsWith("@contoso.com");
      }),
    [priorRoutes]
  );
  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return safePriors;
    return safePriors.filter(
      (r) => r.email.toLowerCase().includes(q) || r.name.toLowerCase().includes(q)
    );
  }, [query, safePriors]);
  const typedOk = isValidEmail(query);

  return (
    <section className={styles.root} aria-label="Change route">
      <Title3>Change route</Title3>
      <Input
        aria-label="Recipient email"
        value={query}
        onChange={(_, d) => setQuery(d.value)}
        placeholder="Type a real recipient email"
      />
      <div className={styles.list} role="listbox" aria-label="Route candidates">
        {filtered.map((r) => (
          <Button
            key={r.email}
            appearance="secondary"
            onClick={() => onSelect(r.email, r.name || r.email, teach)}
          >
            {r.name || r.email} — {r.email}
          </Button>
        ))}
        {typedOk ? (
          <Button
            appearance="primary"
            onClick={() => {
              const email = normalizeEmail(query);
              onSelect(email, email, teach);
            }}
          >
            Use {normalizeEmail(query)}
          </Button>
        ) : null}
        {!filtered.length && !typedOk ? (
          <Text>Enter a valid email address to set the route.</Text>
        ) : null}
      </div>
      <label>
        <input
          type="checkbox"
          checked={teach}
          onChange={(e) => setTeach(e.target.checked)}
        />{" "}
        <Text>Remember this correction for similar messages</Text>
      </label>
      <div className={styles.row}>
        <Button appearance="subtle" onClick={onCancel}>
          Cancel
        </Button>
      </div>
    </section>
  );
}
