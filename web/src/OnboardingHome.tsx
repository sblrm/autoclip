import { CheckCircle, CircleNotch, FolderOpen, GearSix, GlobeSimple, UploadSimple, Wrench } from "@phosphor-icons/react";
import { useEffect, useRef, useState } from "react";
import type { Job, OnboardingSnapshot, Project, StudioClient } from "./api";

type Locale = "id" | "en";

const copy = {
  id: {
    eyebrow: "AUTOCLIP / STUDIO LOKAL",
    title: "Mulai, periksa, lalu potong dengan yakin.",
    body: "Semua video, model, dan hasil tetap tersimpan di komputer ini.",
    repair: "Perbaiki setup wajib",
    ready: "Setup siap",
    performance: "Performa",
    performanceBody: "Pilih Otomatis, CPU, atau GPU. GPU hanya aktif setelah inferensi dan NVENC terverifikasi.",
    performanceLink: "Buka detail performa",
    tutorial: "Alur kerja",
    tutorialCount: "4 langkah review",
    import: "Impor video",
    analyze: "Analisis klip",
    subject: "Pilih subjek",
    export: "Setujui dan ekspor",
    start: "Mulai proyek",
    resume: "Lanjutkan proyek",
    localVideo: "Video lokal",
    useUrl: "Gunakan tautan",
    urlPlaceholder: "https://…",
    importing: "Mengimpor video…",
    setupFirst: "Selesaikan setup wajib sebelum mengimpor video.",
  },
  en: {
    eyebrow: "AUTOCLIP / LOCAL STUDIO",
    title: "Start, verify, then cut with confidence.",
    body: "Every video, model, and result stays on this computer.",
    repair: "Repair required setup",
    ready: "Setup ready",
    performance: "Performance",
    performanceBody: "Choose Auto, CPU, or GPU. GPU only activates after live inference and NVENC are verified.",
    performanceLink: "Open performance details",
    tutorial: "Workflow",
    tutorialCount: "4 review steps",
    import: "Import video",
    analyze: "Analyze clips",
    subject: "Select subject",
    export: "Approve and export",
    start: "Start project",
    resume: "Resume project",
    localVideo: "Local video",
    useUrl: "Use link",
    urlPlaceholder: "https://…",
    importing: "Importing video…",
    setupFirst: "Finish required setup before importing a video.",
  },
} as const;

interface Props {
  client: StudioClient;
  locale: Locale;
  projects: Project[];
  snapshot: OnboardingSnapshot;
  onOpenProject: (projectId: string) => void;
  onStartProject: () => void;
  onOpenSettings: () => void;
}

export function OnboardingHome({ client, locale, projects, snapshot, onOpenProject, onStartProject, onOpenSettings }: Props) {
  const [current, setCurrent] = useState(snapshot);
  const [activeLocale, setActiveLocale] = useState<Locale>(locale);
  const [job, setJob] = useState<Job | null>(null);
  const [busy, setBusy] = useState(false);
  const [issue, setIssue] = useState<string | null>(null);
  const [url, setUrl] = useState("");
  const fileInput = useRef<HTMLInputElement>(null);
  const t = copy[activeLocale];

  useEffect(() => {
    setCurrent(snapshot);
    setActiveLocale(locale);
  }, [locale, snapshot]);

  const refresh = async () => {
    const next = await client.getOnboarding();
    setCurrent(next);
  };

  const runRepair = async () => {
    setBusy(true);
    setIssue(null);
    try {
      const created = await client.repairRequiredSetup();
      let stopped = false;
      const stop = client.watchJob(created.job_id, (event) => {
        setJob(event);
        if (!stopped && ["completed", "failed", "interrupted"].includes(event.stage)) {
          stopped = true;
          if (event.stage === "completed") {
            refresh().catch((error: Error) => setIssue(error.message)).finally(() => setBusy(false));
          } else {
            setIssue(event.error || event.message);
            setBusy(false);
          }
          stop();
        }
      });
    } catch (error) {
      setIssue(error instanceof Error ? error.message : "Repair failed");
      setBusy(false);
    }
  };

  const importSource = async (source: File | string) => {
    setBusy(true);
    setIssue(null);
    try {
      const project = typeof source === "string" ? await client.importUrl(source) : await client.importFile(source);
      onOpenProject(project.id);
    } catch (error) {
      setIssue(error instanceof Error ? error.message : "Import failed");
      setBusy(false);
    }
  };

  const switchLanguage = async () => {
    setIssue(null);
    try {
      const preferences = await client.updatePreferences({ locale: activeLocale === "id" ? "en" : "id" });
      setActiveLocale(preferences.locale);
    } catch (error) {
      setIssue(error instanceof Error ? error.message : "Language update failed");
    }
  };

  const steps = [t.import, t.analyze, t.subject, t.export];
  const needsRepair = current.recommended_action.id === "repair_required";

  return <main className="min-h-screen bg-[#10100f] px-5 py-6 text-stone-100 md:px-10 md:py-10">
    <header className="mx-auto flex max-w-6xl items-center justify-between border-b border-white/8 pb-5"><div className="flex items-center gap-3"><span className="grid size-9 place-items-center bg-[#f5662c] text-black">✂</span><div><p className="font-mono text-[11px] font-bold tracking-[.16em]">AUTOCLIP</p><p className="font-mono text-[9px] tracking-[.18em] text-stone-500">LOCAL STUDIO</p></div></div><div className="flex items-center gap-2"><button className="action-secondary" aria-label={activeLocale === "id" ? "English" : "Bahasa Indonesia"} onClick={() => void switchLanguage()}><GlobeSimple size={16} />{activeLocale === "id" ? "EN" : "ID"}</button><button className="action-secondary" onClick={onOpenSettings}><GearSix size={16} />{t.performance}</button></div></header>
    <section className="mx-auto grid max-w-6xl gap-6 py-12 lg:grid-cols-[1.35fr_.65fr]"><div><p className="font-mono text-[10px] tracking-[.2em] text-[#f5662c]">{t.eyebrow}</p><h1 className="mt-5 max-w-3xl text-balance text-5xl font-semibold tracking-[-.07em] md:text-7xl">{t.title}</h1><p className="mt-6 max-w-xl text-lg leading-8 text-stone-400">{t.body}</p>{needsRepair ? <p className="mt-5 text-sm text-[#f5662c]">{t.setupFirst}</p> : null}<div className="mt-9 flex flex-wrap gap-3"><button className="action-export" disabled={busy || needsRepair} onClick={() => { onStartProject(); fileInput.current?.click(); }}><UploadSimple size={17} />{t.start}</button>{projects[0] ? <button className="action-secondary" onClick={() => onOpenProject(projects[0].id)}><FolderOpen size={17} />{t.resume}</button> : null}</div><input ref={fileInput} className="hidden" type="file" accept="video/*,.mkv" onChange={(event) => { const file = event.target.files?.[0]; if (file) void importSource(file); }} /></div>
      <aside className="border border-white/8 bg-[#151513] p-6"><div className="flex items-center gap-3"><span className={`grid size-9 place-items-center ${needsRepair ? "bg-[#f5662c] text-black" : "bg-emerald-400 text-black"}`}>{needsRepair ? <Wrench size={18} /> : <CheckCircle size={18} />}</span><div><p className="font-mono text-[10px] tracking-[.15em] text-stone-500">LOCAL ENGINE</p><p className="mt-1 text-sm font-medium">{needsRepair ? current.recommended_action.title : t.ready}</p></div></div><p className="mt-5 text-sm leading-6 text-stone-400">{needsRepair ? current.setup.components.filter((component) => component.required && component.state !== "ready").map((component) => component.label).join(", ") : t.performanceBody}</p>{needsRepair ? <button className="action-export mt-6 w-full justify-center" disabled={busy} onClick={() => void runRepair()}>{busy ? <CircleNotch className="animate-spin" size={16} /> : <Wrench size={16} />}{t.repair}</button> : null}{job ? <p className="mt-4 font-mono text-[10px] text-stone-500">{job.message} {Math.round(job.progress * 100)}%</p> : null}</aside>
    </section>
    <section className="mx-auto grid max-w-6xl gap-5 lg:grid-cols-[1.1fr_.9fr]"><div className="border border-white/8 bg-[#151513] p-6"><div className="flex items-center justify-between"><div><p className="font-mono text-[10px] tracking-[.15em] text-stone-500">{t.tutorial.toUpperCase()}</p><p className="mt-2 text-lg">{t.tutorialCount}</p></div><span className="font-mono text-sm text-[#f5662c]">01—04</span></div><ol className="mt-6 grid gap-3 sm:grid-cols-2">{steps.map((step, index) => <li className="border border-white/8 px-4 py-3 text-sm text-stone-300" key={step}><span className="mr-3 font-mono text-[10px] text-[#f5662c]">0{index + 1}</span>{step}</li>)}</ol></div><div className="border border-white/8 bg-[#151513] p-6"><p className="font-mono text-[10px] tracking-[.15em] text-stone-500">{t.localVideo.toUpperCase()}</p><label className="mt-4 block text-sm text-stone-300">URL</label><input className="studio-input mt-2" value={url} placeholder={t.urlPlaceholder} onChange={(event) => setUrl(event.target.value)} /><button className="mt-3 text-sm text-[#f5662c] disabled:text-stone-600" disabled={busy || needsRepair || !url.trim()} onClick={() => void importSource(url.trim())}><GlobeSimple className="mr-2 inline" size={15} />{t.useUrl}</button>{busy ? <p className="mt-4 text-sm text-stone-400">{t.importing}</p> : null}{issue ? <p className="mt-4 text-sm text-red-300">{issue}</p> : null}</div></section>
    <section className="mx-auto mt-5 max-w-6xl border border-white/8 bg-[#151513] p-6"><div className="flex items-center justify-between gap-4"><div><p className="font-mono text-[10px] tracking-[.15em] text-stone-500">{t.performance.toUpperCase()}</p><p className="mt-2 text-sm text-stone-400">{t.performanceBody}</p></div><button className="action-secondary shrink-0" onClick={onOpenSettings}>{t.performanceLink}</button></div></section>
  </main>;
}
