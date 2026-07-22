import "core-js/stable";
import "regenerator-runtime/runtime";
import React from "react";
import { createRoot } from "react-dom/client";
import { FluentProvider } from "@fluentui/react-components";
import { App } from "./App";
import { spoqTheme } from "./theme/spoqTokens";

Office.onReady(() => {
  const el = document.getElementById("root");
  if (!el) return;
  createRoot(el).render(
    <FluentProvider theme={spoqTheme}>
      <App />
    </FluentProvider>
  );
});
