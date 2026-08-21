import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { App } from "./App";
import type { Project, StudioClient } from "./api";

const project: Project = {
  id: "project-1",
  title: "Episode Studio",
  source_kind: "upload",
  source_path: "/projects/source.mp4",
  status: "ready",
};

const client: StudioClient = {
  getOnboarding: async () => ({
    preferences: { locale: "id", last_project_id: null, onboarding_complete: false, performance_profile: "auto", updated_at: "" },
    setup: { components: [], is_ready: true, tutorial_steps: [] },
    acceleration: { platform: "Windows", engines: {}, encoders: { libx264: { state: "ready" } } },
    recommended_action: { id: "start_project", title: "Start a project" },
    tutorial_steps: [],
  }),
  updatePreferences: async () => ({} as never),
  repairRequiredSetup: async () => ({ job_id: "repair" }),
  applyPerformanceProfile: async () => ({} as never),
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
  getJob: async () => ({ id: "job", project_id: project.id, kind: "test", stage: "completed", progress: 1, message: "done", error: null }),
  watchJob: () => () => undefined,
  getAccelerationStatus: async () => ({ platform: "Windows", engines: { mediapipe_cpu: { state: "ready", provider: "CPUDelegate" } }, encoders: { libx264: { state: "ready" } } }),
  listAccelerationPlans: async () => [],
  recheckAcceleration: async () => ({ platform: "Windows", engines: { mediapipe_cpu: { state: "ready", provider: "CPUDelegate" } }, encoders: { libx264: { state: "ready" } } }),
  installAcceleration: async () => ({ job_id: "install" }),
  setProjectAcceleration: async (projectId) => ({ project_id: projectId, tracker_engine: "auto", encoder_mode: "auto" }),
};

test("uses Home as the root route and loads durable onboarding", async () => {
  window.history.replaceState({}, "", "/");
  render(<App client={client} />);

  expect(await screen.findByRole("button", { name: "Buka detail performa" })).toBeVisible();
  expect(screen.getByRole("button", { name: "Lanjutkan proyek" })).toBeVisible();
});

test("opens performance settings without selecting a project", async () => {
  window.history.replaceState({}, "", "/settings");
  render(<App client={client} />);

  expect(await screen.findByRole("radio", { name: "Gunakan GPU" })).toBeVisible();
});

test("returns from performance setup to Home", async () => {
  const user = userEvent.setup();
  window.history.replaceState({}, "", "/settings");
  render(<App client={client} />);

  await user.click(await screen.findByRole("button", { name: "Kembali ke Home" }));

  expect(await screen.findByRole("button", { name: "Buka detail performa" })).toBeVisible();
});

test("starts in Indonesian and makes face selection visible before approval", async () => {
  const user = userEvent.setup();
  window.history.replaceState({}, "", "/projects/project-1");
  render(<App client={client} />);

  expect(await screen.findByText("PERPUSTAKAAN PROYEK")).toBeInTheDocument();
  expect(await screen.findByRole("button", { name: "Pilih subjek" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Setujui pratinjau" })).toBeDisabled();

  await user.click(screen.getByRole("button", { name: "EN" }));
  expect(screen.getByText("PROJECT LIBRARY")).toBeInTheDocument();
});
