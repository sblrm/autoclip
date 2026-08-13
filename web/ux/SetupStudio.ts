export type ComponentState = "ready" | "missing" | "installing" | "failed" | "unsupported";

export interface SetupComponent {
  id: string;
  label: string;
  required: boolean;
  state: ComponentState;
  version: string | null;
  detail: string;
  acceleration: "cpu" | "gpu" | null;
}

export interface SetupStatus {
  components: SetupComponent[];
  hardware: { adapter: string | null; driver: string | null; gpu_ready: boolean };
  is_ready: boolean;
  tutorial_steps: string[];
}

export interface SetupJob { job_id: string; stage: string; progress: number; message: string; error: string | null }

export interface SetupClient {
  getStatus(): Promise<SetupStatus>;
  recheck(): Promise<SetupStatus>;
  install(component: string): Promise<{ job_id: string }>;
  watchJob(jobId: string, onEvent: (job: SetupJob) => void): () => void;
}

export { SetupStudio, setupApi } from "./SetupStudioImpl";
