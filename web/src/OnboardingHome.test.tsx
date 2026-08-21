import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";
import { OnboardingHome } from "./OnboardingHome";
import type { OnboardingSnapshot, StudioClient } from "./api";

const project = {
  id: "p-1",
  title: "Episode Studio",
  source_kind: "upload" as const,
  source_path: "/projects/source.mp4",
  status: "ready" as const,
};

const missingRuntimeSnapshot: OnboardingSnapshot = {
  preferences: {
    locale: "id",
    last_project_id: "p-1",
    onboarding_complete: false,
    performance_profile: "auto",
    updated_at: "2026-08-21T00:00:00Z",
  },
  setup: {
    components: [{ id: "ffmpeg", label: "FFmpeg", required: true, state: "missing", version: null, detail: "Video export" }],
    is_ready: false,
    tutorial_steps: ["Import video", "Analyze clips", "Lock a subject", "Approve and export"],
  },
  acceleration: { platform: "Windows", engines: {}, encoders: { libx264: { state: "ready" } } },
  recommended_action: { id: "repair_required", title: "Repair required setup" },
  tutorial_steps: ["Import video", "Analyze clips", "Lock a subject", "Approve and export"],
};

const readyRuntimeSnapshot: OnboardingSnapshot = {
  ...missingRuntimeSnapshot,
  setup: { ...missingRuntimeSnapshot.setup, components: [{ ...missingRuntimeSnapshot.setup.components[0], state: "ready" }], is_ready: true },
  recommended_action: { id: "start_project", title: "Start a project" },
};

function clientFor(snapshot: OnboardingSnapshot): StudioClient {
  return {
    getOnboarding: vi.fn(async () => readyRuntimeSnapshot),
    updatePreferences: vi.fn(async (patch) => ({ ...snapshot.preferences, ...patch })),
    repairRequiredSetup: vi.fn(async () => ({ job_id: "repair-1" })),
    applyPerformanceProfile: vi.fn(async () => ({} as never)),
    importFile: vi.fn(async () => project),
    importUrl: vi.fn(async () => project),
    watchJob: vi.fn((_id, onEvent) => {
      queueMicrotask(() => onEvent({ id: "repair-1", project_id: "__setup__", kind: "setup:repair_required", stage: "completed", progress: 1, message: "Done", error: null }));
      return () => undefined;
    }),
  } as unknown as StudioClient;
}

test("Home shows one repair action, Indonesian tutorial, and settings escape hatch", async () => {
  render(<OnboardingHome client={clientFor(missingRuntimeSnapshot)} locale="id" projects={[]} snapshot={missingRuntimeSnapshot}
    onOpenProject={vi.fn()} onStartProject={vi.fn()} onOpenSettings={vi.fn()} />);

  expect(await screen.findByRole("button", { name: "Perbaiki setup wajib" })).toBeVisible();
  expect(screen.getByText("Impor video")).toBeVisible();
  expect(screen.getByRole("button", { name: "Buka detail performa" })).toBeVisible();
  expect(screen.getByRole("button", { name: "Mulai proyek" })).toBeDisabled();
});

test("repair completion refreshes readiness and keeps project resume available", async () => {
  const user = userEvent.setup();
  const client = clientFor(missingRuntimeSnapshot);
  render(<OnboardingHome client={client} locale="id" projects={[project]} snapshot={missingRuntimeSnapshot}
    onOpenProject={vi.fn()} onStartProject={vi.fn()} onOpenSettings={vi.fn()} />);

  await user.click(screen.getByRole("button", { name: "Perbaiki setup wajib" }));

  await waitFor(() => expect(client.getOnboarding).toHaveBeenCalled());
  expect(screen.getByRole("button", { name: "Lanjutkan proyek" })).toBeVisible();
  expect(screen.getByText("Setup siap")).toBeVisible();
});

test("Home imports a local video and opens its durable project", async () => {
  const user = userEvent.setup();
  const client = clientFor(readyRuntimeSnapshot);
  const openProject = vi.fn();
  render(<OnboardingHome client={client} locale="en" projects={[]} snapshot={readyRuntimeSnapshot}
    onOpenProject={openProject} onStartProject={vi.fn()} onOpenSettings={vi.fn()} />);

  await user.click(screen.getByRole("button", { name: "Start project" }));
  const input = document.querySelector('input[type="file"]') as HTMLInputElement;
  await user.upload(input, new File(["video"], "source.mp4", { type: "video/mp4" }));

  await waitFor(() => expect(openProject).toHaveBeenCalledWith("p-1"));
});

test("Home persists a language switch before changing its copy", async () => {
  const user = userEvent.setup();
  const client = clientFor(readyRuntimeSnapshot);
  render(<OnboardingHome client={client} locale="id" projects={[]} snapshot={readyRuntimeSnapshot}
    onOpenProject={vi.fn()} onStartProject={vi.fn()} onOpenSettings={vi.fn()} />);

  await user.click(screen.getByRole("button", { name: "English" }));

  expect(client.updatePreferences).toHaveBeenCalledWith({ locale: "en" });
  expect(await screen.findByText("Start, verify, then cut with confidence.")).toBeVisible();
  expect(screen.getByText("4 review steps")).toBeVisible();
});
