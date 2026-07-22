import React, { useState } from "react";
import { Button, makeStyles, Text } from "@fluentui/react-components";

const useStyles = makeStyles({
  list: {
    marginTop: "8px",
    paddingLeft: "16px",
    color: "#5B6B73",
  },
});

export function WhyExplanation({
  items,
}: {
  items: { code: string; text: string }[];
}): React.JSX.Element {
  const styles = useStyles();
  const [open, setOpen] = useState(false);
  if (!items.length) return <></>;
  return (
    <div>
      <Button appearance="transparent" size="small" onClick={() => setOpen((v) => !v)}>
        {open ? "Hide why" : "Why this suggestion?"}
      </Button>
      {open ? (
        <ul className={styles.list}>
          {items.map((item) => (
            <li key={`${item.code}-${item.text}`}>
              <Text>{item.text}</Text>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
