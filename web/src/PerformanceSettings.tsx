import { ArrowClockwise, ArrowLeft, CircleNotch, Cpu, GearSix, Lightning, Wrench } from "@phosphor-icons/react";
import { useEffect, useState } from "react";
import { AccelerationCenter } from "../ux/AccelerationCenter";
import type { AccelerationPlan, OnboardingSnapshot, PerformanceProfile, StudioClient } from "./api";

type Locale = "id" | "en";

const copy = {
  id: {
    title: "Performa lokal",
    body: "Pilih cara kerja AutoClip. GPU hanya dipakai saat tracker dan NVENC sudah lulus pemeriksaan nyata.",
    auto: "Otomatis",
    cpu: "Gunakan CPU",
    gpu: "Gunakan GPU",
    repair: "Perbaiki GPU",
    advanced: "Kontrol engine lanjutan",
    evidence: "Bukti runtime",
    gpuSetup: "Setup GPU tracking",
    gpuSetupBody: "Pasang komponen tetap ini dari AutoClip, lalu cek ulang. GPU tidak akan aktif sebelum tracker dan NVENC lolos pemeriksaan nyata.",
    install: "Pasang",
    download: "Unduh",
    ready: "Siap",
    needsSetup: "Perlu dipasang",
    nvencNeedsDriver: "NVENC belum siap. Perbarui driver NVIDIA atau pasang ulang FFmpeg dari Home, lalu cek ulang.",
    recheckGpu: "Cek ulang GPU",
    openGpuSetup: "Buka setup GPU",
    home: "Kembali ke Home",
    loading: "Memuat performa…",
  },
  en: {
    title: "Local performance",
    body: "Choose how AutoClip runs. GPU is only used after the tracker and NVENC pass live checks.",
    auto: "Auto",
    cpu: "Use CPU",
    gpu: "Use GPU",
    repair: "Repair GPU",
    advanced: "Advanced engine controls",
    evidence: "Runtime evidence",
    gpuSetup: "GPU tracking setup",
    gpuSetupBody: "Install these fixed components from AutoClip, then recheck. GPU never activates before tracker and NVENC pass live checks.",
    install: "Install",
    download: "Download",
    ready: "Ready",
    needsSetup: "Needs setup",
    nvencNeedsDriver: "NVENC is not ready. Update the NVIDIA driver or reinstall FFmpeg from Home, then recheck.",
    recheckGpu: "Recheck GPU",
    openGpuSetup: "Open GPU setup",
    home: "Back to Home",
    loading: "Loading performance…",
  },
} as const;

export function PerformanceSettings({ client, locale, onOpenHome }: { client: StudioClient; locale: Locale; onOpenHome?: () => void }) {
  const [snapshot, setSnapshot] = useState<OnboardingSnapshot | null>(null);
  const [busy, setBusy] = useState<PerformanceProfile | null>(null);
  const [issue, setIssue] = useState<string | null>(null);
  const [advanced, setAdvanced] = useState(false);
  const [plans, setPlans] = useState<AccelerationPlan[]>([]);
  const [installingPlan, setInstallingPlan] = useState<string | null>(null);
  const [showGpuSetup, setShowGpuSetup] = useState(false);
  const activeLocale = snapshot?.preferences.locale ?? locale;
  const t = copy[activeLocale];

  const refresh = async () => setSnapshot(await client.getOnboarding());

  useEffect(() => {
    refresh().catch((error: Error) => setIssue(error.message));
  }, [client]);

  useEffect(() => {
    client.listAccelerationPlans().then(setPlans).catch((error: Error) => setIssue(error.message));
  }, [client]);

  const choose = async (profile: PerformanceProfile) => {
    setBusy(profile);
    setIssue(null);
    try {
      await client.updatePreferences({ performance_profile: profile });
      await refresh();
    } catch (error) {
      setIssue(error instanceof Error ? error.message : "Performance update failed");
    } finally {
      setBusy(null);
    }
  };

  const installGpuPlan = async (planId: AccelerationPlan["id"]) => {
    setInstallingPlan(planId);
    setIssue(null);
    try {
      const job = await client.installAcceleration(planId, false);
      let completedSynchronously = false;
      let stop = () => { completedSynchronously = true; };
      const nextStop = client.watchJob(job.job_id, (event) => {
        if (["completed", "failed", "interrupted"].includes(event.stage)) {
          stop();
          setInstallingPlan(null);
          if (event.stage === "completed") refresh().catch((error: Error) => setIssue(error.message));
          else setIssue(event.error || event.message);
        }
      });
      stop = nextStop;
      if (completedSynchronously) nextStop();
    } catch (error) {
      setInstallingPlan(null);
      setIssue(error instanceof Error ? error.message : "GPU setup failed");
    }
  };

  const recheckGpu = async () => {
    setIssue(null);
    try {
      await client.recheckAcceleration();
      await refresh();
    } catch (error) {
      setIssue(error instanceof Error ? error.message : "GPU recheck failed");
    }
  };

  if (!snapshot) return <main className="grid min-h-screen place-items-center bg-[#10100f] font-mono text-xs tracking-[.2em] text-stone-500">{t.loading}</main>;
  const profile = snapshot.preferences.performance_profile;
  const cuda = snapshot.acceleration.engines.yunet_cuda;
  const nvenc = snapshot.acceleration.encoders.h264_nvenc;
  const gpuReady = cuda?.state === "ready" && nvenc?.state === "ready";
  const gpuPlans = ["pytorch_cuda_128", "onnxruntime_cuda_128", "yunet_2023mar"] as const;

  return <main className="min-h-screen bg-[#10100f] px-5 py-8 text-stone-100 md:px-10"><section className="mx-auto max-w-4xl"><header className="border-b border-white/8 pb-6"><div className="flex items-start justify-between gap-4"><div><p className="font-mono text-[10px] tracking-[.2em] text-[#f5662c]">AUTOCLIP / LOCAL STUDIO</p><h1 className="mt-4 text-4xl font-semibold tracking-[-.06em]">{t.title}</h1><p className="mt-4 max-w-2xl leading-7 text-stone-400">{t.body}</p></div>{onOpenHome ? <button className="action-secondary shrink-0" onClick={onOpenHome}><ArrowLeft size={16} />{t.home}</button> : null}</div></header><section className="mt-7 border border-white/8 bg-[#151513] p-6"><p className="font-mono text-[10px] tracking-[.15em] text-stone-500">PROFILE</p><div className="mt-4 grid gap-3 sm:grid-cols-3" role="radiogroup">{([
    ["auto", t.auto, GearSix],
    ["cpu", t.cpu, Cpu],
    ["gpu", t.gpu, Lightning],
  ] as const).map(([value, label, Icon]) => <button key={value} role="radio" aria-checked={profile === value} className={`min-h-24 border p-4 text-left ${profile === value ? "border-[#f5662c] bg-[#211a16]" : "border-white/8 bg-[#11110f]"}`} disabled={busy !== null} onClick={() => void choose(value)}><Icon size={18} className="text-[#f5662c]" /><span className="mt-5 block text-sm font-medium">{busy === value ? <CircleNotch className="animate-spin" size={15} /> : label}</span></button>)}</div></section><section className="mt-5 border border-white/8 bg-[#151513] p-6"><p className="font-mono text-[10px] tracking-[.15em] text-stone-500">{t.evidence.toUpperCase()}</p><dl className="mt-4 grid gap-3 text-sm sm:grid-cols-2"><div className="border border-white/8 p-4"><dt className="text-stone-500">YuNet CUDA</dt><dd className="mt-2">{cuda?.state === "ready" ? cuda.provider || "Ready" : cuda?.state || "Not verified"}</dd></div><div className="border border-white/8 p-4"><dt className="text-stone-500">H.264 NVENC</dt><dd className="mt-2">{nvenc?.state === "ready" ? "Ready" : nvenc?.state || "Not verified"}</dd></div></dl>{issue ? <div className="mt-5 border-l-2 border-[#f5662c] bg-[#211a16] p-4 text-sm text-stone-200"><p>{issue}</p><button className="action-export mt-4" onClick={() => setShowGpuSetup(true)}><Wrench size={16} />{t.openGpuSetup}</button></div> : null}</section>{(!gpuReady || showGpuSetup) ? <section id="gpu-setup" className="mt-5 border border-[#f5662c]/40 bg-[#1a1714] p-6" aria-label={t.gpuSetup}><p className="font-mono text-[10px] tracking-[.15em] text-[#f5662c]">GPU / WINDOWS + UBUNTU</p><h2 className="mt-3 text-xl font-semibold">{t.gpuSetup}</h2><p className="mt-3 max-w-2xl text-sm leading-6 text-stone-400">{t.gpuSetupBody}</p><div className="mt-5 grid gap-3">{gpuPlans.map((id, index) => { const plan = plans.find((item) => item.id === id); if (!plan) return null; const action = id === "yunet_2023mar" ? t.download : t.install; const done = id === "yunet_2023mar" ? cuda?.state === "ready" : id === "onnxruntime_cuda_128" ? cuda?.provider === "CUDAExecutionProvider" && cuda?.state === "ready" : snapshot.setup.components.some((component) => component.id === "torch" && component.acceleration === "gpu"); return <div className="flex flex-wrap items-center justify-between gap-3 border border-white/8 bg-[#11110f] p-4" key={id}><div><p className="font-mono text-[10px] text-stone-500">0{index + 1}</p><p className="mt-1 text-sm font-medium">{plan.label}</p><p className="mt-1 max-w-xl text-xs leading-5 text-stone-500">{plan.detail}</p><p className="mt-1 text-xs text-stone-500">{done ? t.ready : t.needsSetup}</p></div><button className="action-export" disabled={installingPlan !== null || done} onClick={() => void installGpuPlan(id)}>{installingPlan === id ? <CircleNotch className="animate-spin" size={16} /> : <Lightning size={16} />}{action} {plan.label}</button></div>; })}</div><div className="mt-4 border-t border-white/8 pt-4 text-sm"><p><strong>H.264 NVENC:</strong> {nvenc?.state === "ready" ? t.ready : t.nvencNeedsDriver}</p><button className="action-secondary mt-4" disabled={installingPlan !== null} onClick={() => void recheckGpu()}><ArrowClockwise size={16} />{t.recheckGpu}</button></div></section> : null}<section className="mt-5 border border-white/8 bg-[#151513] p-6"><button className="action-secondary" onClick={() => setAdvanced((value) => !value)}>{t.advanced}</button>{advanced ? <div className="mt-5"><AccelerationCenter client={client} locale={activeLocale} /></div> : null}</section></section></main>;
}
