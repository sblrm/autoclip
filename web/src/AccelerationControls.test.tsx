import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";
import { App } from "./App";
import type { AccelerationStatus, ProjectDetail, RuntimeHealth, StudioClient, TrackerEngine } from "./api";

const project = {
  id: "project-1",
  title: "Episode Studio",
  source_kind: "upload" as const,
  source_path: "/projects/source.mp4",
  status: "ready" as const,
};

function detail(
  status: "draft" | "preview_ready" | "approved",
  projectTracker: TrackerEngine,
  resolutionTracker: TrackerEngine | null,
  selectedTrackId: string | null,
  hasTracks: boolean,
): ProjectDetail {
  return {
    project,
    acceleration: { project_id: project.id, tracker_engine: projectTracker, encoder_mode: "auto" },
    clips: [{
      id: "clip-1",
      project_id: project.id,
      start_time: 12,
      end_time: 30,
      title: "Momen utama",
      score: 92,
      language: "id",
      status,
      subtitle_config: {},
      selected_face_track_id: selectedTrackId,
      tracking_status: "ready",
      tracking_resolution: resolutionTracker ? {
        tracker_engine: resolutionTracker,
        provider: "CUDAExecutionProvider",
        model_id: "yunet_2023mar",
      } : null,
    }],
    face_tracks: {
      "clip-1": hasTracks ? [{ id: "track-1", clip_id: "clip-1", label: "Subject 1", confidence: 0.9, samples: [] }] : [],
    },
    tracking_gaps: { "clip-1": [] },
    jobs: [],
    artifacts: [
      ...(status === "preview_ready" ? [{
        id: "preview-1",
        project_id: project.id,
        clip_id: "clip-1",
        kind: "tracking_preview",
        path: "/projects/preview.mp4",
        metadata: { encoder_mode: "h264_nvenc", tracker_engine: resolutionTracker },
      }] : []),
      {
      id: "export-1",
      project_id: project.id,
      clip_id: "clip-1",
      kind: "export",
      path: "/projects/export.mp4",
      metadata: { encoder: "h264_nvenc", tracker_engine: "yunet_cuda" },
      },
    ],
  };
}

test("tracker override requires detection and a new explicit subject lock before preview", async () => {
  const user = userEvent.setup();
  let clipStatus: "draft" | "preview_ready" | "approved" = "approved";
  let projectTracker: TrackerEngine = "auto";
  let resolutionTracker: TrackerEngine | null = "yunet_cuda";
  let selectedTrackId: string | null = "track-1";
  let hasTracks = true;
  const currentDetail = () => detail(clipStatus, projectTracker, resolutionTracker, selectedTrackId, hasTracks);
  const client: StudioClient = {
    getOnboarding: vi.fn(async () => ({} as never)),
    updatePreferences: vi.fn(async () => ({} as never)),
    repairRequiredSetup: vi.fn(async () => ({ job_id: "repair" })),
    applyPerformanceProfile: vi.fn(async () => ({} as never)),
    getHealth: vi.fn(async (): Promise<RuntimeHealth> => ({
      ffmpeg: { available: true },
      opencv: { available: true, version: "4" },
      face_tracking: { available: true, engine: "yunet_cuda", reason: "ready" },
      runtime: "gpu",
    })),
    listProjects: vi.fn(async () => [project]),
    getProject: vi.fn(async () => currentDetail()),
    importFile: vi.fn(async () => project),
    importUrl: vi.fn(async () => project),
    analyze: vi.fn(async () => ({ job_id: "analyze" })),
    patchClip: vi.fn(async (_clipId, patch) => {
      if ("selected_face_track_id" in patch) selectedTrackId = patch.selected_face_track_id ?? null;
      return currentDetail().clips[0];
    }),
    createPreview: vi.fn(async () => ({ job_id: resolutionTracker ? "preview" : "detect" })),
    approve: vi.fn(async () => {
      clipStatus = "approved";
      return currentDetail().clips[0];
    }),
    exportClip: vi.fn(async () => ({ job_id: "export" })),
    getJob: vi.fn(async () => ({
      id: "preview", project_id: project.id, kind: "preview", stage: "completed", progress: 1, message: "Ready", error: null,
    })),
    watchJob: vi.fn((jobId, onEvent) => {
      queueMicrotask(() => {
        if (jobId === "detect") {
          resolutionTracker = projectTracker;
          hasTracks = true;
          selectedTrackId = null;
          clipStatus = "draft";
        } else if (jobId === "preview") {
          clipStatus = "preview_ready";
        }
        onEvent({
          id: jobId,
          project_id: project.id,
          kind: jobId === "detect" ? "tracking_detection" : jobId === "preview" ? "tracking_preview" : jobId,
          stage: "completed",
          progress: 1,
          message: "Ready",
          error: null,
        });
      });
      return () => undefined;
    }),
    getAccelerationStatus: vi.fn(async (): Promise<AccelerationStatus> => ({
      platform: "Windows",
      engines: {
        mediapipe_cpu: { state: "ready", provider: "CPUDelegate", model_id: "face_detector" },
        yunet_cuda: { state: "ready", provider: "CUDAExecutionProvider", model_id: "yunet_2023mar" },
      },
      encoders: { h264_nvenc: { state: "ready" }, libx264: { state: "ready" } },
    })),
    listAccelerationPlans: vi.fn(async () => []),
    recheckAcceleration: vi.fn(async (): Promise<AccelerationStatus> => ({
      platform: "Windows",
      engines: { mediapipe_cpu: { state: "ready", provider: "CPUDelegate", model_id: "face_detector" } },
      encoders: { h264_nvenc: { state: "ready" } },
    })),
    installAcceleration: vi.fn(async () => ({ job_id: "install" })),
    setProjectAcceleration: vi.fn(async (projectId, patch) => {
      const nextTracker = patch.tracker_engine ?? projectTracker;
      if (nextTracker !== projectTracker) {
        resolutionTracker = null;
        selectedTrackId = null;
        hasTracks = false;
        clipStatus = "draft";
      }
      projectTracker = nextTracker;
      return { project_id: projectId, tracker_engine: projectTracker, encoder_mode: "auto" as const };
    }),
  };

  window.history.replaceState({}, "", "/projects/project-1");
  render(<App client={client} />);

  expect(await screen.findByText("Subject 1")).toBeVisible();
  await user.click(screen.getByRole("button", { name: "Kontrol engine lanjutan" }));
  expect(screen.getByRole("button", { name: "Ekspor 9:16" })).toBeEnabled();
  expect(screen.getByText("h264_nvenc")).toBeVisible();
  expect(screen.getByText("yunet_cuda")).toBeVisible();

  await user.click(await screen.findByRole("button", { name: "Gunakan CPU MediaPipe" }));

  expect(client.setProjectAcceleration).toHaveBeenCalledWith(project.id, { tracker_engine: "mediapipe_cpu" });
  await waitFor(() => expect(screen.queryByText("Subject 1")).not.toBeInTheDocument());
  expect(screen.getByRole("button", { name: "Setujui pratinjau" })).toBeDisabled();
  expect(screen.getByRole("button", { name: "Ekspor 9:16" })).toBeDisabled();

  await user.click(screen.getByRole("button", { name: "Deteksi wajah" }));
  await waitFor(() => expect(client.createPreview).toHaveBeenCalledWith("clip-1"));
  const detectedSubject = await screen.findByRole("button", { name: /Subject 1/ });
  expect(detectedSubject).not.toHaveClass("is-selected");
  expect(screen.getByRole("button", { name: "Setujui pratinjau" })).toBeDisabled();
  expect(screen.getByRole("button", { name: "Ekspor 9:16" })).toBeDisabled();

  await user.click(detectedSubject);
  await waitFor(() => expect(screen.getByRole("button", { name: "Buat pratinjau" })).toBeEnabled());

  await user.click(screen.getByRole("button", { name: "Buat pratinjau" }));
  await waitFor(() => expect(screen.getByRole("button", { name: "Setujui pratinjau" })).toBeEnabled());
  await user.click(screen.getByRole("button", { name: "Setujui pratinjau" }));
  await waitFor(() => expect(screen.getByRole("button", { name: "Ekspor 9:16" })).toBeEnabled());
});
