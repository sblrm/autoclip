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
}

export interface ProjectDetail {
  project: Project;
  clips: Clip[];
  face_tracks: Record<string, FaceTrack[]>;
  tracking_gaps: Record<string, TrackingGap[]>;
  jobs: Job[];
  artifacts: Artifact[];
}

export interface JobCreated {
  job_id: string;
}

export interface StudioClient {
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
    const body = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(body.detail || "Local studio request failed");
  }
  return response.json() as Promise<T>;
}

export const api: StudioClient = {
  getHealth: () => request<RuntimeHealth>("/api/runtime-health"),
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
