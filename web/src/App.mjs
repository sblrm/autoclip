import { createElement, useLayoutEffect } from "react";
import { App as StudioEditor } from "./App.tsx";

function clarifySubjectLabel(root = document) {
  for (const label of root.querySelectorAll("label.studio-label")) {
    if (label.textContent === "Pilih subjek") label.textContent = "Subjek terkunci";
    if (label.textContent === "Select subject") label.textContent = "Locked subject";
  }
}

export function App({ client }) {
  useLayoutEffect(() => {
    clarifySubjectLabel();
    const observer = new MutationObserver(() => clarifySubjectLabel());
    observer.observe(document.body, { childList: true, subtree: true });
    return () => observer.disconnect();
  }, []);

  return createElement(StudioEditor, { client });
}
