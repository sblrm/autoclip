import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { App } from "./App";
import type { StudioClient } from "./api";

const project = {
  id: "project-1",
  title: "Episode Studio",
  source_kind: "upload",
  source_path: "/projects/source.mp4",
  status: "ready",
};

const client: StudioClient = {
  getHealth: async () => ({
    ffmpeg: { available: true },
    opencv: { available: true, version: "4" },
    face_tracking: { available: true, engine: "mediapipe_tasks", reason: "ready" },
    runtime: "cpu",
  }),
  listProjects: async () => [project],
  getProject: async () => ({
    project,
    clips: [
      {
        id: "clip-1",
        project_id: project.id,
        start_time: 12,
        end_time: 30,
        title: "Momen utama",
        score: 92,
        language: "id",
        status: "draft",
        subtitle_config: {},
        selected_face_track_id: null,
        tracking_status: "needs_subject",
      },
    ],
    face_tracks: {
      "clip-1": [{ id: "track-1", clip_id: "clip-1", label: "Subject 1", confidence: 0.9, samples: [] }],
    },
    tracking_gaps: { "clip-1": [] },
    jobs: [],
    artifacts: [],
  }),
  importFile: async () => project,
  importUrl: async () => project,
  analyze: async () => ({ job_id: "job" }),
  patchClip: async () => ({}) as never,
  createPreview: async () => ({ job_id: "job" }),
  approve: async () => ({}) as never,
  exportClip: async () => ({ job_id: "job" }),
};

test("starts in Indonesian and makes face selection visible before approval", async () => {
  const user = userEvent.setup();
  render(<App client={client} />);

  expect(await screen.findByText("Perpustakaan proyek")).toBeInTheDocument();
  expect(screen.getByText("Pilih subjek")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Setujui pratinjau" })).toBeDisabled();

  await user.click(screen.getByRole("button", { name: "EN" }));
  expect(screen.getByText("Project library")).toBeInTheDocument();
});
