import * as Dialog from "@radix-ui/react-dialog";
import {
  ArrowClockwise,
  CaretDown,
  CheckCircle,
  CircleNotch,
  FilmReel,
  FolderOpen,
  FrameCorners,
  GearSix,
  GlobeSimple,
  HardDrives,
  Lightning,
  MagicWand,
  Play,
  Plus,
  Scissors,
  ShareFat,
  UploadSimple,
  UserFocus,
  WarningCircle,
  X,
} from "@phosphor-icons/react";
import { startTransition, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, type Artifact, type Clip, type FaceTrack, type Job, type Project, type ProjectDetail, type RuntimeHealth, type StudioClient } from "./api";

type Locale = "id" | "en";

const copy = {
  id: {
    library: "Perpustakaan proyek",
    newProject: "Proyek baru",
    importVideo: "Impor video",
    url: "Tautan video",
    analyze: "Analisis klip",
    editor: "Ruang edit",
    candidates: "Kandidat klip",
    inspector: "Inspektur crop",
    selectSubject: "Pilih subjek",
    makePreview: "Buat pratinjau",
    approve: "Setujui pratinjau",
    export: "Ekspor 9:16",
    source: "Sumber",
    health: "Kesehatan runtime",
    noProject: "Mulai dengan satu video",
    noProjectBody: "AutoClip menyimpan salinan lokal, lalu mengubahnya menjadi ruang review yang bisa dilanjutkan kapan saja.",
    drop: "Pilih video lokal",
    urlPlaceholder: "https://…",
    useUrl: "Gunakan tautan",
    safeArea: "Safe area 9:16",
    tracking: "Pelacakan wajah",
    subtitle: "Subjudul",
    title: "Judul klip",
    in: "Masuk",
    out: "Keluar",
    noTracks: "Jalankan deteksi untuk memilih subjek. Sistem tidak akan berpindah wajah otomatis.",
    selected: "Terkunci",
    gaps: "Gap pelacakan",
    exportHistory: "Riwayat ekspor",
    ready: "siap review",
  },
  en: {
    library: "Project library",
    newProject: "New project",
    importVideo: "Import video",
    url: "Video link",
    analyze: "Analyze clips",
    editor: "Edit room",
    candidates: "Clip candidates",
    inspector: "Crop inspector",
    selectSubject: "Select subject",
    makePreview: "Make preview",
    approve: "Approve preview",
    export: "Export 9:16",
    source: "Source",
    health: "Runtime health",
    noProject: "Start with one video",
    noProjectBody: "AutoClip keeps a local copy, then turns it into a review room you can safely resume later.",
    drop: "Choose a local video",
    urlPlaceholder: "https://…",
    useUrl: "Use link",
    safeArea: "9:16 safe area",
    tracking: "Face tracking",
    subtitle: "Subtitles",
    title: "Clip title",
    in: "In",
    out: "Out",
    noTracks: "Run detection to select a subject. The system will never switch faces automatically.",
    selected: "Locked",
    gaps: "Tracking gaps",
    exportHistory: "Export history",
    ready: "ready to review",
  },
} as const;

interface AppProps {
  client?: StudioClient;
}

export function App({ client = api }: AppProps) {
  const [locale, setLocale] = useState<Locale>("id");
  const [projects, setProjects] = useState<Project[]>([]);
  const [activeProjectId, setActiveProjectId] = useState<string | null>(null);
  const [detail, setDetail] = useState<ProjectDetail | null>(null);
  const [activeClipId, setActiveClipId] = useState<string | null>(null);
  const [health, setHealth] = useState<RuntimeHealth | null>(null);
  const [job, setJob] = useState<Job | null>(null);
  const [issue, setIssue] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const t = copy[locale];

  const refreshLibrary = useCallback(async () => {
    const [runtime, items] = await Promise.all([client.getHealth(), client.listProjects()]);
    setHealth(runtime);
    setProjects(items);
    setActiveProjectId((current) => current ?? items[0]?.id ?? null);
  }, [client]);

  const refreshDetail = useCallback(async (projectId: string) => {
    const next = await client.getProject(projectId);
    startTransition(() => {
      setDetail(next);
      setActiveClipId((current) => current && next.clips.some((clip) => clip.id === current) ? current : next.clips[0]?.id ?? null);
    });
  }, [client]);

  useEffect(() => {
    refreshLibrary().catch((error: Error) => setIssue(error.message));
  }, [refreshLibrary]);

  useEffect(() => {
    if (activeProjectId) {
      refreshDetail(activeProjectId).catch((error: Error) => setIssue(error.message));
    } else {
      setDetail(null);
    }
  }, [activeProjectId, refreshDetail]);

  const activeClip = useMemo(
    () => detail?.clips.find((clip) => clip.id === activeClipId) ?? null,
    [activeClipId, detail],
  );

  const runJob = useCallback(async (start: () => Promise<{ job_id: string }>) => {
    setBusy(true);
    setIssue(null);
    try {
      const created = await start();
      const cancel = client.watchJob(created.job_id, (event) => {
        setJob(event);
        if (["completed", "failed", "interrupted"].includes(event.stage)) {
          cancel();
          if (activeProjectId) refreshDetail(activeProjectId).catch((error: Error) => setIssue(error.message));
          refreshLibrary().catch((error: Error) => setIssue(error.message));
          setBusy(false);
        }
      });
    } catch (error) {
      setIssue(error instanceof Error ? error.message : "Request failed");
      setBusy(false);
    }
  }, [activeProjectId, client, refreshDetail, refreshLibrary]);

  const updateClip = useCallback(async (patch: Parameters<StudioClient["patchClip"]>[1]) => {
    if (!activeClip || !activeProjectId) return;
    try {
      await client.patchClip(activeClip.id, patch);
      await refreshDetail(activeProjectId);
    } catch (error) {
      setIssue(error instanceof Error ? error.message : "Unable to save clip");
    }
  }, [activeClip, activeProjectId, client, refreshDetail]);

  const importSource = useCallback(async (source: File | string) => {
    setBusy(true);
    setIssue(null);
    try {
      const project = typeof source === "string" ? await client.importUrl(source) : await client.importFile(source);
      await refreshLibrary();
      setActiveProjectId(project.id);
    } catch (error) {
      setIssue(error instanceof Error ? error.message : "Import failed");
    } finally {
      setBusy(false);
    }
  }, [client, refreshLibrary]);

  return (
    <main className="min-h-screen bg-[#10100f] text-stone-100 selection:bg-[#f5662c] selection:text-black">
      <div className="studio-grid min-h-screen">
        <Sidebar projects={projects} activeProjectId={activeProjectId} health={health} t={t} locale={locale} onLocale={() => setLocale((value) => value === "id" ? "en" : "id")} onSelect={setActiveProjectId} />
        <section className="min-w-0 border-x border-white/8 bg-[#151513]">
          <Topbar detail={detail} health={health} t={t} onAnalyze={() => activeProjectId && runJob(() => client.analyze(activeProjectId))} />
          {detail ? (
            <Editor detail={detail} clip={activeClip} job={job} busy={busy} t={t} onSelectClip={setActiveClipId} onPatch={updateClip} onPreview={() => activeClip && runJob(() => client.createPreview(activeClip.id))} onApprove={async () => { if (activeClip && activeProjectId) { await client.approve(activeClip.id); await refreshDetail(activeProjectId); } }} onExport={() => activeClip && runJob(() => client.exportClip(activeClip.id))} />
          ) : (
            <ImportScreen t={t} busy={busy} onImport={importSource} />
          )}
        </section>
        <Inspector detail={detail} clip={activeClip} health={health} job={job} busy={busy} t={t} onPatch={updateClip} onPreview={() => activeClip && runJob(() => client.createPreview(activeClip.id))} onApprove={async () => { if (activeClip && activeProjectId) { await client.approve(activeClip.id); await refreshDetail(activeProjectId); } }} onExport={() => activeClip && runJob(() => client.exportClip(activeClip.id))} />
      </div>
      {issue ? <div className="fixed bottom-5 left-1/2 z-50 flex -translate-x-1/2 items-center gap-3 border border-[#f5662c]/50 bg-[#29231f] px-4 py-3 text-sm shadow-2xl"><WarningCircle size={20} className="text-[#f5662c]" />{issue}<button onClick={() => setIssue(null)} aria-label="Dismiss"><X size={16} /></button></div> : null}
    </main>
  );
}

function Sidebar({ projects, activeProjectId, health, t, locale, onLocale, onSelect }: { projects: Project[]; activeProjectId: string | null; health: RuntimeHealth | null; t: typeof copy.id; locale: Locale; onLocale: () => void; onSelect: (id: string) => void }) {
  return <aside className="hidden min-h-screen flex-col bg-[#10100f] lg:flex">
    <div className="flex items-center justify-between border-b border-white/8 px-5 py-5"><div className="flex items-center gap-3"><span className="grid size-8 place-items-center bg-[#f5662c] text-black"><Scissors size={18} weight="bold" /></span><div><p className="font-mono text-[11px] font-bold tracking-[.16em] text-white">AUTOCLIP</p><p className="font-mono text-[9px] tracking-[.18em] text-stone-500">LOCAL STUDIO</p></div></div><button className="font-mono text-[10px] text-stone-400 hover:text-white" aria-label={locale === "id" ? "EN" : "ID"} onClick={onLocale}>{locale === "id" ? "EN" : "ID"}</button></div>
    <nav className="p-3"><p className="px-2 pb-2 font-mono text-[10px] tracking-[.15em] text-stone-600">{t.library.toUpperCase()}</p><div className="space-y-1">{projects.map((project) => <button key={project.id} onClick={() => onSelect(project.id)} className={`group flex w-full items-center gap-3 px-3 py-3 text-left transition ${project.id === activeProjectId ? "bg-[#24231f] text-white" : "text-stone-500 hover:bg-white/4 hover:text-stone-200"}`}><FilmReel size={18} weight={project.id === activeProjectId ? "fill" : "regular"} /><span className="min-w-0"><span className="block truncate text-sm">{project.title}</span><span className="block font-mono text-[10px] uppercase tracking-[.12em] text-stone-600">{project.status}</span></span></button>)}</div></nav>
    <div className="mt-auto border-t border-white/8 p-4"><div className="flex items-center justify-between font-mono text-[10px] text-stone-500"><span>LOCAL ENGINE</span><span className={health?.face_tracking.available ? "text-[#f5662c]" : "text-red-400"}>{health?.face_tracking.available ? "ONLINE" : "CHECK"}</span></div><div className="mt-3 h-px bg-stone-800"><div className="h-px w-2/3 bg-[#f5662c]" /></div></div>
  </aside>;
}

function Topbar({ detail, health, t, onAnalyze }: { detail: ProjectDetail | null; health: RuntimeHealth | null; t: typeof copy.id; onAnalyze: () => void }) {
  return <header className="flex min-h-17 items-center justify-between border-b border-white/8 px-5 md:px-7"><div className="flex min-w-0 items-center gap-3"><HardDrives size={17} className="text-[#f5662c]" /><div className="min-w-0"><p className="truncate text-sm font-semibold">{detail?.project.title ?? t.newProject}</p><p className="font-mono text-[10px] uppercase tracking-[.14em] text-stone-500">{detail ? `${detail.clips.length} ${t.candidates}` : "LOCAL-ONLY / 9:16"}</p></div></div><div className="flex items-center gap-2"><span className="hidden items-center gap-2 border border-white/8 px-3 py-2 font-mono text-[10px] text-stone-400 sm:flex"><span className={`size-1.5 rounded-full ${health?.face_tracking.available ? "bg-[#f5662c]" : "bg-red-400"}`} />{health?.runtime?.toUpperCase() ?? "CHECK"}</span>{detail ? <button onClick={onAnalyze} className="action-secondary"><MagicWand size={16} />{t.analyze}</button> : null}</div></header>;
}

function ImportScreen({ t, busy, onImport }: { t: typeof copy.id; busy: boolean; onImport: (source: File | string) => Promise<void> }) {
  const fileInput = useRef<HTMLInputElement>(null);
  const [url, setUrl] = useState("");
  return <div className="mx-auto flex min-h-[calc(100vh-69px)] max-w-3xl flex-col justify-center px-6 py-16"><div className="max-w-xl"><p className="mb-5 font-mono text-[11px] tracking-[.2em] text-[#f5662c]">01 / {t.source.toUpperCase()}</p><h1 className="text-balance text-5xl font-semibold tracking-[-.06em] text-stone-100 md:text-7xl">{t.noProject}</h1><p className="mt-6 max-w-md text-lg leading-8 text-stone-400">{t.noProjectBody}</p></div><div className="mt-12 grid gap-4 md:grid-cols-[1.2fr_.8fr]"><button className="import-tile text-left" onClick={() => fileInput.current?.click()} disabled={busy}><UploadSimple size={27} className="text-[#f5662c]" /><span className="mt-12 block text-lg">{t.drop}</span><span className="mt-1 block font-mono text-[10px] uppercase tracking-[.15em] text-stone-500">MP4 · MOV · M4V · WEBM</span></button><div className="import-tile"><GlobeSimple size={27} className="text-[#f5662c]" /><label className="mt-10 block font-mono text-[10px] uppercase tracking-[.15em] text-stone-500">{t.url}</label><input className="studio-input mt-2" value={url} placeholder={t.urlPlaceholder} onChange={(event) => setUrl(event.target.value)} /><button className="mt-3 text-sm text-[#f5662c] disabled:text-stone-600" disabled={busy || !url.trim()} onClick={() => onImport(url.trim())}>{t.useUrl} →</button></div></div><input ref={fileInput} className="hidden" type="file" accept="video/*,.mkv" onChange={(event) => { const file = event.target.files?.[0]; if (file) onImport(file); }} /></div>;
}

function Editor({ detail, clip, job, busy, t, onSelectClip, onPatch, onPreview, onApprove, onExport }: { detail: ProjectDetail; clip: Clip | null; job: Job | null; busy: boolean; t: typeof copy.id; onSelectClip: (id: string) => void; onPatch: (patch: Parameters<StudioClient["patchClip"]>[1]) => Promise<void>; onPreview: () => void; onApprove: () => void; onExport: () => void }) {
  const preview = clip ? latestArtifact(detail.artifacts, clip.id, "tracking_preview") : undefined;
  const tracks = clip ? detail.face_tracks[clip.id] ?? [] : [];
  const gaps = clip ? detail.tracking_gaps[clip.id] ?? [] : [];
  return <div className="editor-shell"><section className="editor-preview"><div className="mb-4 flex items-center justify-between"><span className="font-mono text-[10px] uppercase tracking-[.16em] text-stone-500">{t.editor}</span><span className="font-mono text-[10px] text-[#f5662c]">9:16 / MP4</span></div><div className="preview-frame">{preview ? <video className="h-full w-full object-cover" src={`/api/artifacts/${preview.id}`} controls /> : <div className="preview-placeholder"><FrameCorners size={36} weight="thin" /><p>{t.safeArea}</p><span>{clip ? clip.title : "—"}</span></div>}<div className="safe-guide" /></div>{job ? <div className="job-strip"><CircleNotch size={15} className={job.stage === "completed" ? "text-[#f5662c]" : "animate-spin text-[#f5662c]"} /><span>{job.message}</span><span className="ml-auto font-mono">{Math.round(job.progress * 100)}%</span></div> : null}</section><section className="timeline-panel"><div className="mb-3 flex items-center justify-between"><span className="font-mono text-[10px] uppercase tracking-[.16em] text-stone-500">{t.candidates}</span><span className="font-mono text-[10px] text-stone-600">{detail.clips.length} CUTS</span></div><div className="clip-rail">{detail.clips.map((item) => <button key={item.id} onClick={() => onSelectClip(item.id)} className={`clip-card ${clip?.id === item.id ? "is-active" : ""}`} style={{ width: `${Math.max(16, Math.min(55, (item.end_time - item.start_time) * 3))}%` }}><span className="clip-score">{item.score}</span><span className="truncate">{item.title}</span></button>)}</div>{clip ? <div className="mt-5 flex flex-wrap items-center gap-3"><span className="font-mono text-[10px] text-stone-500">{formatTime(clip.start_time)} — {formatTime(clip.end_time)}</span><div className="flex min-w-28 flex-1 overflow-hidden border border-white/8">{Array.from({ length: 14 }, (_, index) => <span key={index} className={`h-1 flex-1 ${gaps.some((gap) => index >= gap.start_sample && index <= gap.end_sample) ? "bg-[#f5662c]" : "bg-stone-700"}`} />)}</div><span className="font-mono text-[10px] uppercase text-stone-500">{tracks.length} subjects</span></div> : null}</section></div>;
}

function Inspector({ detail, clip, health, job, busy, t, onPatch, onPreview, onApprove, onExport }: { detail: ProjectDetail | null; clip: Clip | null; health: RuntimeHealth | null; job: Job | null; busy: boolean; t: typeof copy.id; onPatch: (patch: Parameters<StudioClient["patchClip"]>[1]) => Promise<void>; onPreview: () => void; onApprove: () => void; onExport: () => void }) {
  const tracks = clip && detail ? detail.face_tracks[clip.id] ?? [] : [];
  const gaps = clip && detail ? detail.tracking_gaps[clip.id] ?? [] : [];
  const exports = detail?.artifacts.filter((artifact) => artifact.kind === "export") ?? [];
  return <aside className="inspector-panel"><div className="flex items-center justify-between border-b border-white/8 px-5 py-5"><div><p className="font-mono text-[10px] uppercase tracking-[.15em] text-stone-500">{t.inspector}</p><p className="mt-1 text-sm text-stone-200">{clip?.tracking_status ?? "—"}</p></div><HealthDialog health={health} t={t} /></div>{clip ? <div className="space-y-7 p-5"><div><label className="studio-label">{t.title}</label><input className="studio-input" defaultValue={clip.title} onBlur={(event) => onPatch({ title: event.currentTarget.value })} /></div><div className="grid grid-cols-2 gap-3"><NumberField label={t.in} value={clip.start_time} onCommit={(start_time) => onPatch({ start_time })} /><NumberField label={t.out} value={clip.end_time} onCommit={(end_time) => onPatch({ end_time })} /></div><div><div className="mb-3 flex items-center justify-between"><label className="studio-label">{t.selectSubject}</label><UserFocus size={17} className="text-[#f5662c]" /></div>{tracks.length ? <div className="space-y-2">{tracks.map((track) => <button key={track.id} onClick={() => onPatch({ selected_face_track_id: track.id })} className={`track-option ${clip.selected_face_track_id === track.id ? "is-selected" : ""}`}><span><span className="block text-sm">{track.label}</span><span className="font-mono text-[10px] text-stone-500">{Math.round(track.confidence * 100)}% CONF.</span></span>{clip.selected_face_track_id === track.id ? <CheckCircle size={18} className="text-[#f5662c]" /> : <CaretDown size={15} className="-rotate-90 text-stone-600" />}</button>)}</div> : <p className="border-l border-[#f5662c] pl-3 text-sm leading-6 text-stone-500">{t.noTracks}</p>}</div><div className="border-y border-white/8 py-5"><div className="mb-3 flex items-center justify-between"><label className="studio-label">{t.gaps}</label><span className="font-mono text-[10px] text-stone-600">{gaps.length}</span></div><p className="text-sm leading-6 text-stone-500">{gaps.length ? "Hold, then ease toward center at marked intervals." : "No persisted subject loss."}</p></div><div className="space-y-2"><button className="action-primary w-full" disabled={busy || !health?.face_tracking.available} onClick={onPreview}><Play size={17} weight="fill" />{tracks.length && !clip.selected_face_track_id ? t.selectSubject : t.makePreview}</button><button className="action-secondary w-full justify-center" disabled={busy || clip.status !== "preview_ready"} onClick={onApprove}><CheckCircle size={17} />{t.approve}</button><button className="action-export w-full" disabled={busy || clip.status !== "approved"} onClick={onExport}><ShareFat size={17} weight="fill" />{t.export}</button></div>{job?.error ? <p className="text-xs text-red-300">{job.error}</p> : null}<div><p className="studio-label">{t.exportHistory}</p>{exports.length ? exports.slice(-3).reverse().map((artifact) => <a className="mt-2 flex items-center gap-2 text-sm text-stone-300 hover:text-[#f5662c]" key={artifact.id} href={`/api/artifacts/${artifact.id}`}><FolderOpen size={16} />MP4 export</a>) : <p className="text-sm text-stone-600">—</p>}</div></div> : <div className="p-5 text-sm leading-6 text-stone-500">{t.noProjectBody}</div>}</aside>;
}

function HealthDialog({ health, t }: { health: RuntimeHealth | null; t: typeof copy.id }) {
  return <Dialog.Root><Dialog.Trigger asChild><button className="grid size-8 place-items-center border border-white/8 text-stone-400 hover:text-[#f5662c]" aria-label={t.health}><GearSix size={17} /></button></Dialog.Trigger><Dialog.Portal><Dialog.Overlay className="fixed inset-0 z-50 bg-black/70" /><Dialog.Content className="fixed left-1/2 top-1/2 z-50 w-[min(92vw,420px)] -translate-x-1/2 -translate-y-1/2 border border-white/10 bg-[#191917] p-6 shadow-2xl"><Dialog.Title className="text-lg">{t.health}</Dialog.Title><Dialog.Description className="mt-1 text-sm text-stone-500">Local prerequisites, never cloud processing.</Dialog.Description><div className="mt-6 space-y-3">{[["FFmpeg", health?.ffmpeg.available], ["OpenCV", health?.opencv.available], ["MediaPipe Tasks", health?.face_tracking.available]].map(([name, available]) => <div className="flex items-center justify-between border-b border-white/7 pb-3 text-sm" key={String(name)}><span>{name}</span><span className={available ? "text-[#f5662c]" : "text-red-400"}>{available ? "READY" : "MISSING"}</span></div>)}<div className="flex items-center justify-between text-sm"><span>Runtime</span><span className="font-mono text-stone-400">{health?.runtime?.toUpperCase() ?? "—"}</span></div></div><Dialog.Close className="absolute right-4 top-4 text-stone-500 hover:text-white" aria-label="Close"><X size={17} /></Dialog.Close></Dialog.Content></Dialog.Portal></Dialog.Root>;
}

function NumberField({ label, value, onCommit }: { label: string; value: number; onCommit: (value: number) => Promise<void> }) { return <div><label className="studio-label">{label}</label><input className="studio-input" type="number" min="0" step="0.1" defaultValue={value} onBlur={(event) => { const next = Number(event.currentTarget.value); if (Number.isFinite(next)) onCommit(next); }} /></div>; }

function latestArtifact(artifacts: Artifact[], clipId: string, kind: string) { return [...artifacts].reverse().find((artifact) => artifact.clip_id === clipId && artifact.kind === kind); }
function formatTime(value: number) { const minutes = Math.floor(value / 60); return `${String(minutes).padStart(2, "0")}:${(value % 60).toFixed(1).padStart(4, "0")}`; }
