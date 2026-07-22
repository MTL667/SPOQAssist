import React, { useMemo, useState } from "react";
import { Button, Input, makeStyles, Text, Title3 } from "@fluentui/react-components";

const useStyles = makeStyles({
  root: { display: "flex", flexDirection: "column", gap: "10px", padding: "8px 0" },
  list: { display: "flex", flexDirection: "column", gap: "6px" },
  row: { display: "flex", gap: "8px", flexWrap: "wrap" },
});

const DEFAULT_ROUTES = [
  { email: "desk@contoso.com", name: "Service Desk" },
  { email: "finance@contoso.com", name: "Finance" },
  { email: "hr@contoso.com", name: "HR" },
];

export function RoutePicker({
  onSelect,
  onCancel,
}: {
  onSelect: (email: string, name: string, teach: boolean) => void;
  onCancel: () => void;
}): React.JSX.Element {
  const styles = useStyles();
  const [query, setQuery] = useState("");
  const [teach, setTeach] = useState(true);
  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return DEFAULT_ROUTES;
    return DEFAULT_ROUTES.filter(
      (r) => r.email.includes(q) || r.name.toLowerCase().includes(q)
    );
  }, [query]);

  return (
    <section className={styles.root} aria-label="Change route">
      <Title3>Change route</Title3>
      <Input
        aria-label="Search recipients"
        value={query}
        onChange={(_, d) => setQuery(d.value)}
        placeholder="Search name or email"
      />
      <div className={styles.list} role="listbox" aria-label="Route candidates">
        {filtered.map((r) => (
          <Button
            key={r.email}
            appearance="secondary"
            onClick={() => onSelect(r.email, r.name, teach)}
          >
            {r.name} — {r.email}
          </Button>
        ))}
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
