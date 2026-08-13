import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { SetupStudio, type SetupClient } from "./SetupStudio";

const status = {
  components: [
    { id: "ffmpeg", label: "FFmpeg", required: true, state: "ready", version: "7", detail: "Video export.", acceleration: null },
    { id: "opencv", label: "OpenCV", required: true, state: "missing", version: null, detail: "Video frames.", acceleration: null },
    { id: "face_tracking", label: "MediaPipe Tasks", required: true, state: "missing", version: null, detail: "Face tracking.", acceleration: "cpu" },
    { id: "whisper", label: "Whisper transcription", required: true, state: "ready", version: "1", detail: "CPU mode.", acceleration: "cpu" },
  ],
  hardware: { adapter: "NVIDIA GeForce RTX 5070", driver: "610.88", gpu_ready: false },
  is_ready: false,
  tutorial_steps: ["Set up engine", "Import a video", "Analyze clips", "Lock a subject", "Approve and export"],
};

const client: SetupClient = {
  getStatus: async () => status,
  recheck: async () => status,
  install: async () => ({ job_id: "install-opencv" }),
  watchJob: () => () => undefined,
};

test("first launch explains the full clip workflow and exposes missing-tool repair", async () => {
  render(<SetupStudio client={client} />);

  expect(await screen.findByText("Mulai dari sini")).toBeVisible();
  expect(screen.getByText("1. Siapkan mesin")).toBeVisible();
  expect(screen.getByText("5. Setujui dan ekspor")).toBeVisible();
  expect(screen.getByRole("button", { name: "Pasang OpenCV" })).toBeVisible();
});

test("hardware status is named for each engine instead of a misleading global GPU mode", async () => {
  const user = userEvent.setup();
  render(<SetupStudio client={client} />);

  await screen.findByText("Mulai dari sini");
  await user.click(screen.getByRole("button", { name: "EN" }));

  expect(screen.getByText("Whisper transcription · CPU")).toBeVisible();
  expect(screen.getByText("Face tracking · CPU")).toBeVisible();
  expect(screen.getByRole("button", { name: "Enable NVIDIA GPU for Whisper" })).toBeVisible();
});
