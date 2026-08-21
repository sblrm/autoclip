import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, test, vi } from "vitest";
import type { AccelerationClient, AccelerationPlan, AccelerationStatus } from "../src/api";
import { AccelerationCenter } from "./AccelerationCenter";

const windowsStatus: AccelerationStatus = {
  platform: "Windows",
  engines: {
    mediapipe_cpu: { state: "ready", provider: "CPUDelegate", model_id: "face_detector" },
    mediapipe_gpu: { state: "unsupported", provider: "GPUDelegate", reason: "Ubuntu only" },
    yunet_cpu: { state: "ready", provider: "CPUExecutionProvider", model_id: "yunet_2023mar" },
    yunet_cuda: { state: "ready", provider: "CUDAExecutionProvider", model_id: "yunet_2023mar" },
    scrfd_cpu: { state: "missing", provider: "CPUExecutionProvider", model_id: "insightface_antelopev2_scrfd" },
    scrfd_cuda: { state: "missing", provider: "CUDAExecutionProvider", model_id: "insightface_antelopev2_scrfd" },
    retinaface_cpu: { state: "missing", provider: "CPUExecutionProvider", model_id: "insightface_buffalo_m_retinaface" },
    retinaface_cuda: { state: "missing", provider: "CUDAExecutionProvider", model_id: "insightface_buffalo_m_retinaface" },
  },
  encoders: {
    libx264: { state: "ready" },
    h264_nvenc: { state: "ready" },
    hevc_nvenc: { state: "ready" },
  },
};

const plans: AccelerationPlan[] = [
  {
    id: "yunet_2023mar",
    label: "YuNet 2023mar",
    kind: "model",
    requires_restart: false,
    detail: "Pinned YuNet model.",
    license: "MIT",
    research_only: false,
    bytes: 232589,
  },
  {
    id: "insightface_antelopev2_scrfd",
    label: "InsightFace antelopev2 SCRFD detector",
    kind: "model",
    requires_restart: false,
    detail: "Pinned SCRFD model pack.",
    license: "Non-commercial research only (InsightFace pretrained asset)",
    research_only: true,
    bytes: 360662982,
  },
];

function accelerationClient(status = windowsStatus): AccelerationClient {
  return {
    getAccelerationStatus: vi.fn(async () => status),
    listAccelerationPlans: vi.fn(async () => plans),
    recheckAcceleration: vi.fn(async () => status),
    installAcceleration: vi.fn(async () => ({ job_id: "job-1" })),
    setProjectAcceleration: vi.fn(async (projectId, patch) => ({
      project_id: projectId,
      tracker_engine: patch.tracker_engine ?? "auto",
      encoder_mode: patch.encoder_mode ?? "auto",
    })),
    watchJob: vi.fn(() => () => undefined),
  };
}

describe("AccelerationCenter", () => {
  test("shows Windows YuNet CUDA recommendation and saves MediaPipe CPU override", async () => {
    const user = userEvent.setup();
    const client = accelerationClient();

    render(<AccelerationCenter client={client} locale="id" projectId="project-1" />);

    expect(await screen.findByText("Rekomendasi: YuNet CUDA")).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Gunakan CPU MediaPipe" }));
    expect(client.setProjectAcceleration).toHaveBeenCalledWith("project-1", {
      tracker_engine: "mediapipe_cpu",
    });
  });

  test("requires research acknowledgement before SCRFD download", async () => {
    const user = userEvent.setup();

    render(<AccelerationCenter client={accelerationClient()} locale="en" />);

    await screen.findByText("Recommended: YuNet CUDA");
    await user.click(screen.getByRole("button", { name: "Install SCRFD" }));
    expect(screen.getByText("Model assets are for non-commercial research only.")).toBeVisible();
    expect(screen.getByRole("button", { name: "Download model" })).toBeDisabled();
  });
});
