import { createElement, useLayoutEffect } from "react";
import { App as StudioEditor } from "./App.tsx";
import type { StudioClient } from "./api";

export function App({ client }: { client?: StudioClient }) {
  useLayoutEffect(() => {
    for (const label of document.querySelectorAll("label.studio-label")) {
      if (label.textContent === "Pilih subjek") label.textContent = "Subjek terkunci";
    }
  }, []);
  return createElement(StudioEditor, { client });
}
