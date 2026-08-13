import {
  ArrowClockwise,
  CheckCircle,
  CircleNotch,
  Cpu,
  FilmReel,
  FolderOpen,
  GearSix,
  Lightning,
  LockSimple,
  Play,
  ShieldCheck,
  Sparkle,
  TerminalWindow,
  WarningCircle,
} from "@phosphor-icons/react";
import { useCallback, useEffect, useMemo, useState } from "react";

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

interface SetupJob { job_id: string; stage: string; progress: number; message: string; error: string | null }

export interface SetupClient {
  getStatus(): Promise<SetupStatus>;
  recheck(): Promise<SetupStatus>;
  install(component: string): Promise<{ job_id: string }>;
  watchJob(jobId: string, onEvent: (job: SetupJob) => void): () => void;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, init);
  if (!response.ok) {
    const body = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(body.detail || "Local setup request failed");
  }
  return response.json() as Promise<T>;
}

export const setupApi: SetupClient = {
  getStatus: () => request<SetupStatus>("/api/setup/status"),
  recheck: () => request<SetupStatus>("/api/setup/recheck", { method: "POST" }),
  install: (component) => request<{ job_id: string }>("/api/setup/install", {
    method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ component }),
  }),
  watchJob: (jobId, onEvent) => {
    const url = new URL(`/api/jobs/${jobId}`, window.location.href);
    url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
    const socket = new WebSocket(url);
    socket.onmessage = (event) => onEvent(JSON.parse(event.data) as SetupJob);
    socket.onerror = () => socket.close();
    return () => socket.close();
  },
};

type Locale = "id" | "en";

const copy = {
  id: {
    setup: "Pusat setup", welcome: "Mulai dari sini", title: "Potong video pertama, tanpa menebak setup.",
    body: "AutoClip bekerja sepenuhnya di perangkat Anda. Cek mesin, pasang kebutuhan, lalu mulai edit.",
    ready: "Mesin siap", needs: "Perlu setup", openStudio: "Buka studio", recheck: "Cek ulang",
    local: "100% lokal", installed: "Terpasang", missing: "Belum ada", installing: "Memasang", failed: "Gagal",
    install: "Pasang", installGpu: "Aktifkan NVIDIA GPU untuk Whisper", hardware: "Perangkat keras",
    detected: "Terdeteksi", notDetected: "GPU NVIDIA tidak terdeteksi", cpu: "CPU", gpu: "GPU",
    tutorialTitle: "Alur kerja jelas", tutorialBody: "Satu video. Satu subjek terkunci. Satu ekspor yang Anda setujui.",
    safeTitle: "Instalasi terkendali", safeBody: "Tidak ada perintah tersembunyi. Setup hanya menjalankan pemasang lokal yang diizinkan.",
    details: "Apa yang akan dilakukan?", component: "Komponen", engine: "Mesin", action: "Tindakan",
    steps: ["Siapkan mesin", "Impor video", "Analisis klip", "Kunci subjek", "Setujui dan ekspor"],
    progress: "Proses setup", enterBlocked: "Selesaikan kebutuhan wajib untuk membuka studio.",
  },
  en: {
    setup: "Setup Center", welcome: "Start here", title: "Make your first cut without guessing the setup.",
    body: "AutoClip runs entirely on your device. Check your machine, repair what is missing, then start editing.",
    ready: "Engine ready", needs: "Setup needed", openStudio: "Enter studio", recheck: "Recheck",
    local: "100% local", installed: "Ready", missing: "Missing", installing: "Installing", failed: "Failed",
    install: "Install", installGpu: "Enable NVIDIA GPU for Whisper", hardware: "Hardware",
    detected: "Detected", notDetected: "No NVIDIA GPU detected", cpu: "CPU", gpu: "GPU",
    tutorialTitle: "Clear workflow", tutorialBody: "One video. One locked subject. One export you approve.",
    safeTitle: "Controlled installation", safeBody: "No hidden commands. Setup runs only approved local installers.",
    details: "What will happen?", component: "Component", engine: "Engine", action: "Action",
    steps: ["Set up engine", "Import a video", "Analyze clips", "Lock a subject", "Approve and export"],
    progress: "Setup progress", enterBlocked: "Finish required setup before entering the studio.",
  },
} as const;

const installable = new Set(["ffmpeg", "opencv", "face_tracking", "whisper", "ollama"]);

export function SetupStudio({ client = setupApi, onEnterStudio }: { client?: SetupClient; onEnterStudio?: () => void }) {
  const [locale, setLocale] = useState<Locale>("id");
  const [status, setStatus] = useState<SetupStatus | null>(null);
  const [job, setJob] = useState<SetupJob | null>(null);
  const [busyComponent, setBusyComponent] = useState<string | null>(null);
  const [issue, setIssue] = useState<string | null>(null);
  const t = copy[locale];

  const refresh = useCallback(async () => {
    setIssue(null);
    try { setStatus(await client.recheck()); }
    catch (error) { setIssue(error instanceof Error ? error.message : "Setup check failed"); }
  }, [client]);

  useEffect(() => { refresh(); }, [refresh]);

  const beginInstall = useCallback(async (component: string) => {
    setBusyComponent(component); setIssue(null); setJob(null);
    try {
      const queued = await client.install(component);
      const close = client.watchJob(queued.job_id, (event) => {
        setJob(event);
        if (["completed", "failed", "interrupted"].includes(event.stage)) {
          close(); setBusyComponent(null); refresh();
          if (event.error) setIssue(event.error);
        }
      });
    } catch (error) {
      setBusyComponent(null);
      setIssue(error instanceof Error ? error.message : "Installer could not start");
    }
  }, [client, refresh]);

  const missingRequired = useMemo(
    () => status?.components.filter((component) => component.required && component.state !== "ready") ?? [],
    [status],
  );

  return <main className="setup-shell">
    <header className="setup-topbar">
      <div className="brand"><span className="brand-mark"><FilmReel size={20} weight="fill" /></span><span><strong>AUTOCLIP</strong><small>LOCAL STUDIO</small></span></div>
      <div className="top-actions"><span className="local-badge"><LockSimple size={13} />{t.local}</span><button className="language-button" onClick={() => setLocale((value) => value === "id" ? "en" : "id")} aria-label={locale === "id" ? "EN" : "ID"}>{locale === "id" ? "EN" : "ID"}</button></div>
    </header>

    <div className="setup-layout">
      <section className="setup-main">
        <div className="eyebrow"><Sparkle size={15} />{t.setup}</div>
        <h1>{t.title}</h1>
        <p className="setup-lede">{t.body}</p>
        <div className={`readiness ${status?.is_ready ? "is-ready" : ""}`}>
          <span className="readiness-icon">{status?.is_ready ? <CheckCircle size={22} weight="fill" /> : <GearSix size={22} weight="fill" />}</span>
          <div><strong>{status?.is_ready ? t.ready : t.needs}</strong><p>{status?.is_ready ? "Semua kebutuhan wajib telah diperiksa." : `${missingRequired.length} kebutuhan wajib perlu perhatian.`}</p></div>
          <button className="quiet-button" onClick={refresh} disabled={busyComponent !== null}><ArrowClockwise size={16} />{t.recheck}</button>
        </div>

        <section className="tutorial-card" aria-labelledby="tutorial-heading">
          <div><p className="section-kicker">{t.welcome}</p><h2 id="tutorial-heading">{t.tutorialTitle}</h2><p>{t.tutorialBody}</p></div>
          <ol className="step-list">{t.steps.map((step, index) => <li key={step}><span>{index + 1}</span>{step}</li>)}</ol>
        </section>

        <section aria-label={t.component} className="components-section">
          <div className="section-heading"><div><p className="section-kicker">{t.engine}</p><h2>Local engine check</h2></div><span>{status?.components.length ?? 0} checks</span></div>
          <div className="component-grid">
            {status?.components.map((component) => <ComponentCard key={component.id} component={component} locale={locale} t={t} busy={busyComponent === component.id} onInstall={beginInstall} />)}
            {status?.hardware.adapter && !status.hardware.gpu_ready ? <GpuCard hardware={status.hardware} locale={locale} t={t} busy={busyComponent === "whisper_gpu"} onInstall={beginInstall} /> : null}
          </div>
        </section>
      </section>

      <aside className="setup-aside">
        <section className="hardware-card"><div className="panel-heading"><Cpu size={19} /><span>{t.hardware}</span></div><p className="adapter">{status?.hardware.adapter ?? t.notDetected}</p><dl><div><dt>{t.detected}</dt><dd>{status?.hardware.driver ? `Driver ${status.hardware.driver}` : "—"}</dd></div><div><dt>Whisper</dt><dd>{status?.hardware.gpu_ready ? t.gpu : t.cpu}</dd></div><div><dt>Face tracking</dt><dd>{t.cpu}</dd></div></dl></section>
        <section className="safety-card"><ShieldCheck size={20} /><div><h2>{t.safeTitle}</h2><p>{t.safeBody}</p></div></section>
        {job ? <section className="job-card"><div className="job-title"><CircleNotch className={job.stage === "completed" ? "" : "spin"} size={17} /><span>{t.progress}</span></div><p>{job.message}</p><div className="job-meter"><span style={{ width: `${Math.round(job.progress * 100)}%` }} /></div></section> : null}
        <button className="enter-button" onClick={onEnterStudio} disabled={!status?.is_ready || busyComponent !== null}><Play size={17} weight="fill" />{t.openStudio}</button>
        {!status?.is_ready ? <p className="enter-help"><WarningCircle size={15} />{t.enterBlocked}</p> : null}
      </aside>
    </div>
    {issue ? <div role="alert" className="setup-alert"><WarningCircle size={18} />{issue}</div> : null}
  </main>;
}

function ComponentCard({ component, locale, t, busy, onInstall }: { component: SetupComponent; locale: Locale; t: typeof copy.id; busy: boolean; onInstall: (component: string) => void }) {
  const label = component.state === "ready" ? t.installed : component.state === "installing" ? t.installing : component.state === "failed" ? t.failed : t.missing;
  const button = locale === "id" ? `Pasang ${component.label}` : `${t.install} ${component.label}`;
  return <article className={`component-card is-${component.state}`}><div className="component-top"><span className="component-icon">{component.state === "ready" ? <CheckCircle size={20} weight="fill" /> : <WarningCircle size={20} weight="fill" />}</span><span className="status-word">{label}</span></div><h3>{component.label}{component.acceleration ? <span> · {component.acceleration.toUpperCase()}</span> : null}</h3><p>{component.detail}</p><div className="component-footer"><small>{component.version ?? "—"}</small>{component.state !== "ready" && installable.has(component.id) ? <button onClick={() => onInstall(component.id)} disabled={busy}><TerminalWindow size={15} />{busy ? t.installing : button}</button> : null}</div></article>;
}

function GpuCard({ hardware, locale, t, busy, onInstall }: { hardware: SetupStatus["hardware"]; locale: Locale; t: typeof copy.id; busy: boolean; onInstall: (component: string) => void }) {
  return <article className="component-card gpu-card"><div className="component-top"><span className="component-icon"><Lightning size={20} weight="fill" /></span><span className="status-word">{t.detected}</span></div><h3>Whisper transcription · CPU</h3><p>{hardware.adapter} detected. GPU activation affects Whisper only; tracking and render remain CPU until verified.</p><div className="component-footer"><small>CUDA opt-in</small><button onClick={() => onInstall("whisper_gpu")} disabled={busy}><Lightning size={15} weight="fill" />{busy ? t.installing : t.installGpu}</button></div></article>;
}
