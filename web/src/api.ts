export type ProjectStatus =
  | "draft"
  | "importing"
  | "transcribing"
  | "analyzing"
  | "ready"
  | "previewing"
  | "exporting"
  | "completed"
  | "failed"
  | "interrupted";

export interface Project {
  id: string;
  title: string;
  source_kind: "upload" | "url";
  source_path: string;
  status: ProjectStatus;
}

export interface Clip {
  id: string;
  project_id: string;
  start_time: number;
  end_time: number;
  title: string;
  score: number;
  language: string;
  status: "draft" | "preview_ready" | "approved" | "exported";
  subtitle_config: Record<string, unknown>;
  selected_face_track_id: string | null;
  tracking_status: string;
  tracking_resolution?: TrackingResolution | null;
}

export type TrackerEngine =
  | "auto"
  | "mediapipe_cpu"
  | "mediapipe_gpu"
  | "yunet_cpu"
  | "yunet_cuda"
  | "scrfd_cpu"
  | "scrfd_cuda"
  | "retinaface_cpu"
  | "retinaface_cuda";

export type EncoderMode = "auto" | "h264_nvenc" | "hevc_nvenc" | "libx264";
export type RuntimeState = "ready" | "missing" | "unsupported" | "failed" | "requires_acknowledgement";

export interface EngineCapability {
  state: RuntimeState;
  provider?: string;
  model_id?: string | null;
  reason?: string | null;
  probe_detail?: string | null;
  error_code?: string | null;
  error?: string | null;
}

export interface EncoderCapability {
  state: RuntimeState;
  reason?: string | null;
  probe_detail?: string | null;
  error_code?: string | null;
  error?: string | null;
}

export interface AccelerationStatus {
  platform: string;
  engines: Partial<Record<TrackerEngine, EngineCapability>>;
  encoders: Partial<Record<EncoderMode, EncoderCapability>>;
}

export type AccelerationPlanId =
  | "pytorch_cuda_128"
  | "onnxruntime_cuda_128"
  | "yunet_2023mar"
  | "insightface_buffalo_m_retinaface"
  | "insightface_antelopev2_scrfd";

export interface AccelerationPlan {
  id: AccelerationPlanId;
  label: string;
  kind: "package" | "model";
  requires_restart: boolean;
  detail: string;
  license: string | null;
  research_only: boolean;
  bytes?: number;
}

export interface ProjectAcceleration {
  project_id: string;
  tracker_engine: TrackerEngine;
  encoder_mode: EncoderMode;
}

export interface TrackingResolution {
  tracker_engine: TrackerEngine;
  provider: string;
  model_id: string | null;
}

export interface FaceTrack {
  id: string;
  clip_id: string;
  label: string;
  confidence: number;
  samples: Array<{ cx: number; cy: number; confidence: number } | null>;
}

export interface TrackingGap {
  id: string;
  clip_id: string;
  start_sample: number;
  end_sample: number;
}

export interface Artifact {
  id: string;
  project_id: string;
  clip_id: string | null;
  kind: string;
  path: string;
  metadata?: Record<string, unknown> | null;
}

export interface Job {
  id: string;
  project_id: string;
  kind: string;
  stage: string;
  progress: number;
  message: string;
  error: string | null;
}

export interface RuntimeHealth {
  ffmpeg: { available: boolean };
  opencv: { available: boolean; version: string | null };
  face_tracking: { available: boolean; engine: string; reason: string };
  runtime: "cpu" | "gpu";
  acceleration?: AccelerationStatus;
}

export type PerformanceProfile = "auto" | "cpu" | "gpu";

export interface AppPreferences {
  locale: "id" | "en";
  last_project_id: string | null;
  onboarding_complete: boolean;
  performance_profile: PerformanceProfile;
  updated_at: string;
}

export interface SetupComponent {
  id: string;
  label: string;
  required: boolean;
  state: RuntimeState;
  version: string | null;
  detail: string;
  acceleration?: string | null;
  provider?: string | null;
  model_id?: string | null;
  probe_detail?: string | null;
  error_code?: string | null;
}

export interface OnboardingSnapshot {
  preferences: AppPreferences;
  setup: { components: SetupComponent[]; is_ready: boolean; tutorial_steps: string[] };
  acceleration: AccelerationStatus;
  recommended_action: { id: "repair_required" | "start_project"; title: string };
  tutorial_steps: string[];
}

export interface StructuredError {
  code: string;
  title: string;
  recovery_action: string;
  retryable: boolean;
}

export interface ProjectDetail {
  project: Project;
  acceleration?: ProjectAcceleration;
  clips: Clip[];
  face_tracks: Record<string, FaceTrack[]>;
  tracking_gaps: Record<string, TrackingGap[]>;
  jobs: Job[];
  artifacts: Artifact[];
}

export interface JobCreated {
  job_id: string;
}

export interface AccelerationClient {
  getAccelerationStatus(): Promise<AccelerationStatus>;
  listAccelerationPlans(): Promise<AccelerationPlan[]>;
  recheckAcceleration(): Promise<AccelerationStatus>;
  installAcceleration(planId: AccelerationPlanId, acknowledgeResearchLicense?: boolean): Promise<JobCreated>;
  setProjectAcceleration(projectId: string, patch: Partial<Pick<ProjectAcceleration, "tracker_engine" | "encoder_mode">>): Promise<ProjectAcceleration>;
  watchJob(id: string, onEvent: (job: Job) => void): () => void;
}

export interface StudioClient extends AccelerationClient {
  getOnboarding(): Promise<OnboardingSnapshot>;
  updatePreferences(patch: Partial<Pick<AppPreferences, "locale" | "onboarding_complete" | "performance_profile">>): Promise<AppPreferences>;
  repairRequiredSetup(): Promise<JobCreated>;
  applyPerformanceProfile(projectId: string): Promise<ProjectAcceleration>;
  getHealth(): Promise<RuntimeHealth>;
  listProjects(): Promise<Project[]>;
  getProject(id: string): Promise<ProjectDetail>;
  importFile(file: File): Promise<Project>;
  importUrl(url: string): Promise<Project>;
  analyze(projectId: string): Promise<JobCreated>;
  patchClip(id: string, patch: Partial<Pick<Clip, "start_time" | "end_time" | "title" | "subtitle_config" | "selected_face_track_id">>): Promise<Clip>;
  createPreview(clipId: string): Promise<JobCreated>;
  approve(clipId: string): Promise<Clip>;
  exportClip(clipId: string): Promise<JobCreated>;
  getJob(id: string): Promise<Job>;
  watchJob(id: string, onEvent: (job: Job) => void): () => void;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, init);
  if (!response.ok) {
    const body = await response.json().catch(() => ({ detail: response.statusText })) as Partial<StructuredError> & { detail?: string };
    const message = body.title
      ? `${body.title}${body.recovery_action ? ` ${body.recovery_action}` : ""}`
      : body.detail || "Local studio request failed";
    throw new Error(message);
  }
  return response.json() as Promise<T>;
}

export const api: StudioClient = {
  getOnboarding: () => request<OnboardingSnapshot>("/api/onboarding"),
  updatePreferences: (patch) => request<AppPreferences>("/api/preferences", {
    method: "PATCH",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(patch),
  }),
  repairRequiredSetup: () => request<JobCreated>("/api/onboarding/repair", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: "{}",
  }),
  applyPerformanceProfile: (projectId) => request<ProjectAcceleration>(`/api/projects/${projectId}/apply-performance-profile`, { method: "POST" }),
  getHealth: () => request<RuntimeHealth>("/api/runtime-health"),
  getAccelerationStatus: () => request<AccelerationStatus>("/api/acceleration/status"),
  listAccelerationPlans: () => request<AccelerationPlan[]>("/api/acceleration/plans"),
  recheckAcceleration: () => request<AccelerationStatus>("/api/acceleration/recheck", { method: "POST" }),
  installAcceleration: (planId, acknowledgeResearchLicense = false) => request<JobCreated>("/api/acceleration/install", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      plan_id: planId,
      ...(acknowledgeResearchLicense ? { acknowledge_research_license: true } : {}),
    }),
  }),
  setProjectAcceleration: (projectId, patch) => request<ProjectAcceleration>(`/api/projects/${projectId}/acceleration`, {
    method: "PATCH",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(patch),
  }),
  listProjects: () => request<Project[]>("/api/projects"),
  getProject: (id) => request<ProjectDetail>(`/api/projects/${id}`),
  importFile: (file) => {
    const form = new FormData();
    form.set("file", file);
    return request<Project>("/api/projects/import", { method: "POST", body: form });
  },
  importUrl: (url) => request<Project>("/api/projects/from-url", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ url }),
  }),
  analyze: (projectId) => request<JobCreated>(`/api/projects/${projectId}/analyze`, { method: "POST" }),
  patchClip: (id, patch) => request<Clip>(`/api/clips/${id}`, {
    method: "PATCH",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(patch),
  }),
  createPreview: (clipId) => request<JobCreated>(`/api/clips/${clipId}/tracking-preview`, { method: "POST" }),
  approve: (clipId) => request<Clip>(`/api/clips/${clipId}/approve`, { method: "POST" }),
  exportClip: (clipId) => request<JobCreated>(`/api/clips/${clipId}/export`, { method: "POST" }),
  getJob: (id) => request<Job>(`/api/jobs/${id}`),
  watchJob: (id, onEvent) => {
    const url = new URL(`/api/jobs/${id}`, window.location.href);
    url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
    const socket = new WebSocket(url);
    socket.onmessage = (event) => onEvent(JSON.parse(event.data) as Job);
    socket.onerror = () => socket.close();
    return () => socket.close();
  },
};
