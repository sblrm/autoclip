import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";
import { PerformanceSettings } from "./PerformanceSettings";
import type { AccelerationPlan, OnboardingSnapshot, StudioClient } from "./api";

const gpuMissingSnapshot: OnboardingSnapshot = {
  preferences: { locale: "id", last_project_id: null, onboarding_complete: false, performance_profile: "auto", updated_at: "" },
  setup: { components: [], is_ready: true, tutorial_steps: [] },
  acceleration: {
    platform: "Windows",
    engines: { yunet_cuda: { state: "missing", provider: "CUDAExecutionProvider", reason: "Inferensi YuNet CUDA belum terverifikasi" }, yunet_cpu: { state: "ready", provider: "CPUExecutionProvider" } },
    encoders: { libx264: { state: "ready" }, h264_nvenc: { state: "missing", reason: "NVENC belum terverifikasi" } },
  },
  recommended_action: { id: "start_project", title: "Start a project" },
  tutorial_steps: [],
};

function clientFor(snapshot: OnboardingSnapshot, updatePreferences = vi.fn(async () => snapshot.preferences)): StudioClient {
  return {
    getOnboarding: vi.fn(async () => snapshot),
    updatePreferences,
    repairRequiredSetup: vi.fn(async () => ({ job_id: "repair" })),
    applyPerformanceProfile: vi.fn(async () => ({} as never)),
    getAccelerationStatus: vi.fn(async () => snapshot.acceleration),
    listAccelerationPlans: vi.fn(async () => [{ id: "insightface_antelopev2_scrfd", label: "InsightFace SCRFD", kind: "model", requires_restart: false, detail: "research", license: "research", research_only: true }]),
    recheckAcceleration: vi.fn(async () => snapshot.acceleration),
    installAcceleration: vi.fn(async () => ({ job_id: "install" })),
    setProjectAcceleration: vi.fn(async () => ({} as never)),
    watchJob: vi.fn(() => () => undefined),
  } as unknown as StudioClient;
}

test("GPU profile explains missing live evidence and opens fixed setup without claiming ready", async () => {
  const user = userEvent.setup();
  const client = clientFor(gpuMissingSnapshot, vi.fn(async () => { throw new Error("Inferensi YuNet CUDA belum terverifikasi"); }));
  render(<PerformanceSettings client={client} locale="id" />);

  await user.click(await screen.findByRole("radio", { name: "Gunakan GPU" }));

  expect(await screen.findByText("Inferensi YuNet CUDA belum terverifikasi")).toBeVisible();
  expect(screen.getByRole("button", { name: "Buka setup GPU" })).toBeVisible();
});

test("research model still needs acknowledgement in advanced settings", async () => {
  const user = userEvent.setup();
  const client = clientFor({ ...gpuMissingSnapshot, preferences: { ...gpuMissingSnapshot.preferences, locale: "en" } });
  render(<PerformanceSettings client={client} locale="en" />);

  await user.click(await screen.findByRole("button", { name: "Advanced engine controls" }));
  await user.click(await screen.findByRole("button", { name: "Install SCRFD" }));

  expect(screen.getByRole("button", { name: "Download model" })).toBeDisabled();
});

test("GPU setup exposes fixed runtime and YuNet downloads from the main performance page", async () => {
  const user = userEvent.setup();
  const installAcceleration = vi.fn(async () => ({ job_id: "install-yunet" }));
  const client = clientFor(gpuMissingSnapshot);
  const gpuPlans: AccelerationPlan[] = [
    { id: "pytorch_cuda_128", label: "PyTorch CUDA 12.8", kind: "package", requires_restart: true, detail: "fixed", license: null, research_only: false },
    { id: "onnxruntime_cuda_128", label: "ONNX Runtime CUDA 12.8", kind: "package", requires_restart: false, detail: "fixed", license: null, research_only: false },
    { id: "yunet_2023mar", label: "YuNet", kind: "model", requires_restart: false, detail: "fixed", license: "MIT", research_only: false },
  ];
  client.listAccelerationPlans = vi.fn(async () => gpuPlans);
  client.installAcceleration = installAcceleration;
  render(<PerformanceSettings client={client} locale="id" />);

  expect(await screen.findByRole("button", { name: "Pasang PyTorch CUDA 12.8" })).toBeVisible();
  expect(screen.getByRole("button", { name: "Pasang ONNX Runtime CUDA 12.8" })).toBeVisible();
  await user.click(screen.getByRole("button", { name: "Unduh YuNet" }));

  expect(installAcceleration).toHaveBeenCalledWith("yunet_2023mar", false);
});
