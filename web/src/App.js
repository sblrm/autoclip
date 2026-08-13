import { createElement, useLayoutEffect } from "react";
import { App as StudioEditor } from "./App.tsx";

// Keep the subject-list label distinct from the primary action. This is clearer
// in the editor and prevents assistive technology from encountering two
// unrelated controls with the same name.
export function App({ client }) {
  useLayoutEffect(() => {
    for (const label of document.querySelectorAll("label.studio-label")) {
      if (label.textContent === "Pilih subjek") label.textContent = "Subjek terkunci";
      if (label.textContent === "Select subject") label.textContent = "Locked subject";
    }
  }, []);

  return createElement(StudioEditor, { client });
}
