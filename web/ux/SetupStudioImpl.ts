import { createElement, useEffect, useState } from "react";
import { SetupStudio as SetupStudioScreen, setupApi } from "./SetupStudioImpl.tsx";
import type { SetupClient, SetupStatus } from "./SetupStudio";

export { setupApi };

export function SetupStudio({ client = setupApi, onEnterStudio }: { client?: SetupClient; onEnterStudio?: () => void }) {
  const [status, setStatus] = useState<SetupStatus | null>(null);

  useEffect(() => {
    client.getStatus().then(setStatus).catch(() => setStatus(null));
  }, [client]);

  const whisper = status?.components.find((component) => component.id === "whisper");
  const tracking = status?.components.find((component) => component.id === "face_tracking");
  const factStyle = {
    position: "fixed" as const,
    right: "16px",
    bottom: "16px",
    zIndex: 100,
    display: "flex",
    gap: "10px",
    padding: "9px 12px",
    border: "1px solid rgba(245,102,44,.38)",
    background: "#1b1815",
    color: "#d6cec4",
    fontFamily: "ui-monospace, monospace",
    fontSize: "11px",
  };

  return createElement(
    "div",
    null,
    status ? createElement(
      "div",
      { style: factStyle, "aria-label": "Per-engine runtime status" },
      createElement("span", null, `Whisper transcription · ${(whisper?.acceleration ?? "cpu").toUpperCase()}`),
      createElement("span", null, `Face tracking · ${(tracking?.acceleration ?? "cpu").toUpperCase()}`),
    ) : null,
    createElement(SetupStudioScreen, { client, onEnterStudio }),
  );
}
