import * as Dialog from "@radix-ui/react-dialog";
import { ArrowClockwise, CheckCircle, CircleNotch, DownloadSimple, Lightning, WarningCircle, X } from "@phosphor-icons/react";
import { useCallback, useEffect, useRef, useState } from "react";
import type {
  AccelerationClient,
  AccelerationPlan,
  AccelerationStatus,
  EncoderMode,
  EngineCapability,
  ProjectAcceleration,
  RuntimeState,
  TrackerEngine,
} from "../src/api";

export type AccelerationLocale = "id" | "en";

export interface AccelerationCenterProps {
  client: AccelerationClient;
  locale: AccelerationLocale;
  projectId?: string;
  currentSelection?: ProjectAcceleration;
  compact?: boolean;
  onSelectionChanged?: (selection: ProjectAcceleration) => void | Promise<void>;
}

const trackerOrder: TrackerEngine[] = [
  "auto",
  "mediapipe_cpu",
  "mediapipe_gpu",
  "yunet_cpu",
  "yunet_cuda",
  "scrfd_cpu",
  "scrfd_cuda",
  "retinaface_cpu",
  "retinaface_cuda",
];

const encoderOrder: EncoderMode[] = ["auto", "h264_nvenc", "hevc_nvenc", "libx264"];

const trackerLabels: Record<TrackerEngine, string> = {
  auto: "Auto",
  mediapipe_cpu: "MediaPipe CPU",
  mediapipe_gpu: "MediaPipe GPU",
  yunet_cpu: "YuNet CPU",
  yunet_cuda: "YuNet CUDA",
  scrfd_cpu: "SCRFD CPU",
  scrfd_cuda: "SCRFD CUDA",
  retinaface_cpu: "RetinaFace CPU",
  retinaface_cuda: "RetinaFace CUDA",
};

const encoderLabels: Record<EncoderMode, string> = {
  auto: "Auto",
  h264_nvenc: "H.264 NVENC",
  hevc_nvenc: "HEVC NVENC",
  libx264: "libx264 CPU",
};

const text = {
  id: {
    title: "Akselerasi lokal",
    auto: "Otomatis",
    recommended: "Rekomendasi",
    verified: "Terverifikasi dengan inferensi nyata",
    notVerified: "Belum terverifikasi",
    tracker: "Face tracking",
    encoder: "Encoder video",
    models: "Model dan runtime",
    recheck: "Cek ulang akselerasi",
    useAuto: "Gunakan Otomatis",
    useTracker: "Gunakan",
    chooseTracker: "Pilih engine face tracking",
    chooseEncoder: "Pilih encoder video",
    researchOnly: "Aset model hanya untuk riset non-komersial.",
    acknowledge: "Saya memahami batas lisensi model ini.",
    download: "Unduh model",
    cancel: "Batal",
    installing: "Memasang",
    noReady: "Tidak ada engine face tracking yang terverifikasi.",
    provider: "Provider",
    model: "Model",
    platform: "Platform",
    retry: "Coba lagi",
  },
  en: {
    title: "Local acceleration",
    auto: "Auto",
    recommended: "Recommended",
    verified: "Verified by live inference",
    notVerified: "Not verified",
    tracker: "Face tracking",
    encoder: "Video encoder",
    models: "Models and runtime",
    recheck: "Recheck acceleration",
    useAuto: "Use Auto",
    useTracker: "Use",
    chooseTracker: "Choose face tracking engine",
    chooseEncoder: "Choose video encoder",
    researchOnly: "Model assets are for non-commercial research only.",
    acknowledge: "I understand this model's license restriction.",
    download: "Download model",
    cancel: "Cancel",
    installing: "Installing",
    noReady: "No face tracking engine has passed live verification.",
    provider: "Provider",
    model: "Model",
    platform: "Platform",
    retry: "Retry",
  },
} as const;

function readyAutoTracker(status: AccelerationStatus): TrackerEngine | null {
  const order: TrackerEngine[] = status.platform.toLowerCase() === "ubuntu"
    ? ["mediapipe_gpu", "yunet_cuda", "mediapipe_cpu", "yunet_cpu"]
    : ["yunet_cuda", "mediapipe_cpu", "yunet_cpu"];
  return order.find((engine) => status.engines[engine]?.state === "ready") ?? null;
}

function readyAutoEncoder(status: AccelerationStatus): EncoderMode {
  return status.encoders.h264_nvenc?.state === "ready" ? "h264_nvenc" : "libx264";
}

function stateText(state: RuntimeState | undefined, locale: AccelerationLocale) {
  return state === "ready" ? text[locale].verified : text[locale].notVerified;
}

function detailText(capability: EngineCapability | undefined) {
  return capability?.reason ?? capability?.probe_detail ?? capability?.error ?? capability?.error_code ?? "—";
}

function installLabel(plan: AccelerationPlan, locale: AccelerationLocale) {
  const action = locale === "id" ? "Pasang" : "Install";
  if (plan.id === "pytorch_cuda_128") return `${action} PyTorch CUDA 12.8`;
  if (plan.id === "insightface_antelopev2_scrfd") return `${action} SCRFD`;
  if (plan.id === "insightface_buffalo_m_retinaface") return `${action} RetinaFace`;
  if (plan.id === "yunet_2023mar") return `${action} YuNet`;
  return `${action} ONNX Runtime CUDA`;
}

function bytesLabel(bytes?: number) {
  if (!bytes) return null;
  return `${(bytes / 1024 / 1024).toFixed(bytes < 1024 * 1024 ? 2 : 1)} MB`;
}

export function AccelerationCenter({
  client,
  locale,
  projectId,
  currentSelection,
  compact = false,
  onSelectionChanged,
}: AccelerationCenterProps) {
  const [status, setStatus] = useState<AccelerationStatus | null>(null);
  const [plans, setPlans] = useState<AccelerationPlan[]>([]);
  const [issue, setIssue] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [researchPlan, setResearchPlan] = useState<AccelerationPlan | null>(null);
  const [acknowledged, setAcknowledged] = useState(false);
  const [jobMessage, setJobMessage] = useState<string | null>(null);
  const stopWatching = useRef<(() => void) | null>(null);
  const t = text[locale];

  useEffect(() => {
    let active = true;
    Promise.all([client.getAccelerationStatus(), client.listAccelerationPlans()])
      .then(([nextStatus, nextPlans]) => {
        if (!active) return;
        setStatus(nextStatus);
        setPlans(nextPlans);
      })
      .catch((error: unknown) => {
        if (active) setIssue(error instanceof Error ? error.message : "Acceleration check failed");
      });
    return () => {
      active = false;
      stopWatching.current?.();
      stopWatching.current = null;
    };
  }, [client]);

  const recheck = useCallback(async () => {
    setIssue(null);
    setBusy("recheck");
    try {
      setStatus(await client.recheckAcceleration());
    } catch (error) {
      setIssue(error instanceof Error ? error.message : "Acceleration check failed");
    } finally {
      setBusy(null);
    }
  }, [client]);

  const select = useCallback(async (patch: Partial<Pick<ProjectAcceleration, "tracker_engine" | "encoder_mode">>) => {
    if (!projectId) return;
    setIssue(null);
    setBusy(Object.keys(patch)[0] ?? "selection");
    try {
      const saved = await client.setProjectAcceleration(projectId, patch);
      await onSelectionChanged?.(saved);
    } catch (error) {
      setIssue(error instanceof Error ? error.message : "Acceleration selection failed");
    } finally {
      setBusy(null);
    }
  }, [client, onSelectionChanged, projectId]);

  const install = useCallback(async (plan: AccelerationPlan, acknowledgement = false) => {
    setResearchPlan(null);
    setAcknowledged(false);
    setIssue(null);
    setBusy(plan.id);
    try {
      const created = await client.installAcceleration(plan.id, acknowledgement);
      let finishedSynchronously = false;
      let stop = () => { finishedSynchronously = true; };
      const nextStop = client.watchJob(created.job_id, (event) => {
        setJobMessage(event.message);
        if (["completed", "failed", "interrupted"].includes(event.stage)) {
          stop();
          stopWatching.current = null;
          setBusy(null);
          if (event.error) setIssue(event.error);
          client.recheckAcceleration().then(setStatus).catch((error: unknown) => {
            setIssue(error instanceof Error ? error.message : "Acceleration check failed");
          });
        }
      });
      stop = nextStop;
      stopWatching.current = nextStop;
      if (finishedSynchronously) nextStop();
    } catch (error) {
      setBusy(null);
      setIssue(error instanceof Error ? error.message : "Acceleration install failed");
    }
  }, [client]);

  if (!status) {
    return <section className={`acceleration-center ${compact ? "is-compact" : ""}`} aria-label={t.title}>
      <p className="acceleration-loading"><CircleNotch className="spin" size={16} />{t.title}</p>
      {issue ? <p role="alert" className="acceleration-issue">{issue}</p> : null}
    </section>;
  }

  const recommendation = readyAutoTracker(status);
  const encoderRecommendation = readyAutoEncoder(status);
  const recommendationProbe = recommendation ? status.engines[recommendation] : undefined;

  return <section className={`acceleration-center ${compact ? "is-compact" : ""}`} aria-label={t.title}>
    <div className="acceleration-heading">
      <div><p className="section-kicker">{t.platform}: {status.platform}</p><h2>{t.title}</h2></div>
      <button className="acceleration-recheck" onClick={recheck} disabled={busy !== null} aria-label={t.recheck}>
        <ArrowClockwise className={busy === "recheck" ? "spin" : ""} size={16} />
      </button>
    </div>

    <article className="acceleration-auto">
      <div>
        <span className="acceleration-state is-ready"><Lightning size={14} weight="fill" />{t.auto}</span>
        <h3>{recommendation ? `${t.recommended}: ${trackerLabels[recommendation]}` : t.noReady}</h3>
        {recommendation ? <p>{recommendationProbe?.provider ?? "—"} · {recommendationProbe?.model_id ?? "—"} · {encoderLabels[encoderRecommendation]}</p> : null}
        {recommendationProbe?.reason ? <small>{recommendationProbe.reason}</small> : null}
      </div>
      {projectId && !compact ? <div className="acceleration-auto-actions"><button className="acceleration-action" onClick={() => select({ tracker_engine: "auto", encoder_mode: "auto" })} disabled={busy !== null}>{t.useAuto}</button><button className="acceleration-action" onClick={() => select({ tracker_engine: "mediapipe_cpu" })} disabled={busy !== null || status.engines.mediapipe_cpu?.state !== "ready"}>{locale === "id" ? "Gunakan CPU MediaPipe" : "Use MediaPipe CPU"}</button></div> : null}
    </article>

    {compact ? <CompactControls status={status} locale={locale} busy={busy !== null} currentSelection={currentSelection} onSelect={select} /> : <>
      <div className="acceleration-section-heading"><h3>{t.tracker}</h3><span>{trackerOrder.length - 1} engines</span></div>
      <div className="acceleration-engine-grid">
        {trackerOrder.slice(1).map((engine) => <EngineCard key={engine} engine={engine} capability={status.engines[engine]} locale={locale} projectId={projectId} selected={currentSelection?.tracker_engine === engine} busy={busy !== null} onSelect={select} />)}
      </div>

      <div className="acceleration-section-heading"><h3>{t.encoder}</h3><span>{encoderOrder.length - 1} modes</span></div>
      <div className="acceleration-encoder-list">
        {encoderOrder.slice(1).map((encoder) => {
          const capability = status.encoders[encoder];
          return <button key={encoder} className={`acceleration-encoder ${currentSelection?.encoder_mode === encoder ? "is-selected" : ""}`} disabled={!projectId || busy !== null || capability?.state !== "ready"} onClick={() => select({ encoder_mode: encoder })}>
            <span><strong>{encoderLabels[encoder]}</strong><small>{capability?.reason ?? stateText(capability?.state, locale)}</small></span>
            <span className={`acceleration-state ${capability?.state === "ready" ? "is-ready" : ""}`}>{stateText(capability?.state, locale)}</span>
          </button>;
        })}
      </div>

      <div className="acceleration-section-heading"><h3>{t.models}</h3><span>{plans.length} plans</span></div>
      <div className="acceleration-plan-list">
        {plans.map((plan) => <article key={plan.id} className="acceleration-plan">
          <div><strong>{plan.label}</strong><p>{plan.detail}</p><small>{[plan.license, bytesLabel(plan.bytes)].filter(Boolean).join(" · ")}</small></div>
          <button className="acceleration-action" disabled={busy !== null} onClick={() => plan.research_only ? setResearchPlan(plan) : install(plan)}><DownloadSimple size={15} />{busy === plan.id ? t.installing : installLabel(plan, locale)}</button>
        </article>)}
      </div>
    </>}

    {jobMessage ? <p className="acceleration-job"><CircleNotch className={busy ? "spin" : ""} size={15} />{jobMessage}</p> : null}
    {issue ? <p role="alert" className="acceleration-issue"><WarningCircle size={16} />{issue}<button onClick={recheck}>{t.retry}</button></p> : null}

    <Dialog.Root open={researchPlan !== null} onOpenChange={(open) => { if (!open) { setResearchPlan(null); setAcknowledged(false); } }}>
      <Dialog.Portal>
        <Dialog.Overlay className="acceleration-dialog-overlay" />
        <Dialog.Content className="acceleration-dialog">
          <Dialog.Title>{researchPlan?.label}</Dialog.Title>
          <Dialog.Description>{t.researchOnly}</Dialog.Description>
          <p className="acceleration-license">{researchPlan?.license}</p>
          <label className="acceleration-ack"><input type="checkbox" checked={acknowledged} onChange={(event) => setAcknowledged(event.target.checked)} />{t.acknowledge}</label>
          <div className="acceleration-dialog-actions"><Dialog.Close asChild><button className="acceleration-cancel">{t.cancel}</button></Dialog.Close><button className="acceleration-action" disabled={!acknowledged || !researchPlan} onClick={() => researchPlan && install(researchPlan, true)}>{t.download}</button></div>
          <Dialog.Close className="acceleration-dialog-close" aria-label="Close"><X size={17} /></Dialog.Close>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  </section>;
}

function CompactControls({ status, locale, busy, currentSelection, onSelect }: {
  status: AccelerationStatus;
  locale: AccelerationLocale;
  busy: boolean;
  currentSelection?: ProjectAcceleration;
  onSelect: (patch: Partial<Pick<ProjectAcceleration, "tracker_engine" | "encoder_mode">>) => Promise<void>;
}) {
  const t = text[locale];
  return <div className="acceleration-compact-controls">
    <button className="acceleration-action" disabled={busy || status.engines.mediapipe_cpu?.state !== "ready"} onClick={() => onSelect({ tracker_engine: "mediapipe_cpu" })}>{locale === "id" ? "Gunakan CPU MediaPipe" : "Use MediaPipe CPU"}</button>
    <label><span>{t.chooseTracker}</span><select value={currentSelection?.tracker_engine ?? "auto"} disabled={busy} onChange={(event) => onSelect({ tracker_engine: event.target.value as TrackerEngine })}>{trackerOrder.map((engine) => <option key={engine} value={engine} disabled={engine !== "auto" && status.engines[engine]?.state !== "ready"}>{engine === "auto" ? t.auto : trackerLabels[engine]}</option>)}</select></label>
    <label><span>{t.chooseEncoder}</span><select value={currentSelection?.encoder_mode ?? "auto"} disabled={busy} onChange={(event) => onSelect({ encoder_mode: event.target.value as EncoderMode })}>{encoderOrder.map((encoder) => <option key={encoder} value={encoder} disabled={encoder !== "auto" && status.encoders[encoder]?.state !== "ready"}>{encoder === "auto" ? t.auto : encoderLabels[encoder]}</option>)}</select></label>
  </div>;
}

function EngineCard({ engine, capability, locale, projectId, selected, busy, onSelect }: {
  engine: TrackerEngine;
  capability?: EngineCapability;
  locale: AccelerationLocale;
  projectId?: string;
  selected: boolean;
  busy: boolean;
  onSelect: (patch: Partial<Pick<ProjectAcceleration, "tracker_engine" | "encoder_mode">>) => Promise<void>;
}) {
  const t = text[locale];
  return <article className={`acceleration-engine ${selected ? "is-selected" : ""}`}>
    <div className="acceleration-engine-top"><strong>{trackerLabels[engine]}</strong><span className={`acceleration-state ${capability?.state === "ready" ? "is-ready" : ""}`}>{stateText(capability?.state, locale)}</span></div>
    <dl><div><dt>{t.provider}</dt><dd>{capability?.provider || "—"}</dd></div><div><dt>{t.model}</dt><dd>{capability?.model_id || "—"}</dd></div></dl>
    <p>{detailText(capability)}</p>
    {projectId ? <button className="acceleration-action" disabled={busy || capability?.state !== "ready"} onClick={() => onSelect({ tracker_engine: engine })}>{t.useTracker} {trackerLabels[engine]}</button> : null}
  </article>;
}
