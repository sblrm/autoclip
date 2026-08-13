import { StrictMode, useState } from "react";
import { createRoot } from "react-dom/client";
import { App } from "../src/App";
import "../src/styles.css";
import "./setup.css";
import { SetupStudio } from "./SetupStudio";

function StudioShell() {
  const [showEditor, setShowEditor] = useState(false);
  return showEditor ? <App /> : <SetupStudio onEnterStudio={() => setShowEditor(true)} />;
}

createRoot(document.getElementById("root")!).render(
  <StrictMode><StudioShell /></StrictMode>,
);
