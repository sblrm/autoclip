"""Local dependency probes and explicit, allow-listed repair plans."""

from __future__ import annotations

import importlib
import platform as platform_module
import subprocess
import sys
from dataclasses import asdict, dataclass
from types import MappingProxyType
from typing import Callable, Mapping, Protocol, Sequence

from autoclip.web.acceleration import AccelerationStatus, EncoderProbe, EngineProbe


CUDA_INDEX = "https://download.pytorch.org/whl/cu128"
CPU_INDEX = "https://download.pytorch.org/whl/cpu"


@dataclass(frozen=True)
class ComponentStatus:
    id: str
    label: str
    required: bool
    state: str
    version: str | None
    detail: str
    acceleration: str | None = None
    provider: str | None = None
    model_id: str | None = None
    probe_detail: str | None = None
    error_code: str | None = None


@dataclass(frozen=True)
class HardwareStatus:
    adapter: str | None
    driver: str | None
    gpu_ready: bool


@dataclass(frozen=True)
class SetupStatus:
    components: tuple[ComponentStatus, ...]
    hardware: HardwareStatus
    is_ready: bool
    tutorial_steps: tuple[str, ...] = (
        "Set up engine",
        "Import a video",
        "Analyze clips",
        "Lock a subject",
        "Approve and export",
    )

    def payload(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class InstallPlan:
    component: str
    label: str
    command: list[str]
    requires_restart: bool
    detail: str

    def payload(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    output: str


class RuntimeProbe(Protocol):
    def executable_version(self, name: str) -> str | None: ...

    def package_version(self, name: str) -> str | None: ...

    def cuda_available(self) -> bool: ...

    def nvidia_adapter(self) -> tuple[str | None, str | None]: ...

    def onnxruntime_providers(self) -> tuple[str, ...]: ...


class AccelerationStatusProvider(Protocol):
    def status(self) -> AccelerationStatus: ...


class SystemProbe:
    """Probe only local programs and modules; network access is never needed."""

    def executable_version(self, name: str) -> str | None:
        try:
            result = subprocess.run(
                [name, "-version"], check=False, capture_output=True, text=True, timeout=8
            )
        except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
            return None
        if result.returncode != 0:
            return None
        return (result.stdout or result.stderr).splitlines()[0].strip() or "installed"

    def package_version(self, name: str) -> str | None:
        try:
            module = importlib.import_module(name)
        except ImportError:
            return None
        return str(getattr(module, "__version__", "installed"))

    def cuda_available(self) -> bool:
        try:
            torch = importlib.import_module("torch")
            return bool(torch.cuda.is_available())
        except (ImportError, AttributeError):
            return False

    def nvidia_adapter(self) -> tuple[str | None, str | None]:
        command = ["nvidia-smi", "--query-gpu=name,driver_version", "--format=csv,noheader"]
        try:
            result = subprocess.run(command, check=False, capture_output=True, text=True, timeout=8)
        except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
            return None, None
        if result.returncode != 0 or not result.stdout.strip():
            return None, None
        name, _, driver = result.stdout.splitlines()[0].partition(",")
        return name.strip() or None, driver.strip() or None

    def onnxruntime_providers(self) -> tuple[str, ...]:
        try:
            onnxruntime = importlib.import_module("onnxruntime")
            onnxruntime.preload_dlls()
            return tuple(str(provider) for provider in onnxruntime.get_available_providers())
        except Exception:
            return ()


Reporter = Callable[[str, float, str], None]
CommandRunner = Callable[[Sequence[str]], CommandResult]


def _run_command(command: Sequence[str]) -> CommandResult:
    try:
        result = subprocess.run(command, check=False, capture_output=True, text=True)
    except FileNotFoundError as error:
        return CommandResult(127, str(error))
    return CommandResult(result.returncode, (result.stdout + "\n" + result.stderr).strip())


class SetupManager:
    """Describe and repair local prerequisites without accepting arbitrary commands."""

    def __init__(
        self,
        *,
        probe: RuntimeProbe | None = None,
        runner: CommandRunner = _run_command,
        python_executable: str | None = None,
        acceleration_manager: AccelerationStatusProvider | None = None,
        platform_name: str | None = None,
    ) -> None:
        self.probe = probe or SystemProbe()
        self.runner = runner
        self.python_executable = python_executable or sys.executable
        self.acceleration_manager = acceleration_manager
        self.platform_name = platform_name or platform_module.system()

    def status(self) -> SetupStatus:
        ffmpeg = self.probe.executable_version("ffmpeg")
        opencv = self.probe.package_version("cv2")
        mediapipe = self.probe.package_version("mediapipe")
        whisper = self.probe.package_version("whisper")
        ollama = self.probe.executable_version("ollama")
        torch = self.probe.package_version("torch")
        onnxruntime = self.probe.package_version("onnxruntime")
        onnxruntime_providers = self._onnxruntime_providers()
        adapter, driver = self.probe.nvidia_adapter()
        gpu_ready = self.probe.cuda_available()
        acceleration_status = self._acceleration_status()
        verified_face_ready = any(
            probe.state == "ready" for probe in acceleration_status.engines.values()
        )
        face_ready = bool(opencv and (mediapipe or verified_face_ready))
        components = [
            self._component("ffmpeg", "FFmpeg", True, ffmpeg, "Video import and export."),
            self._component("opencv", "OpenCV", True, opencv, "Video frames for face tracking."),
            ComponentStatus(
                "face_tracking",
                "MediaPipe Tasks",
                True,
                "ready" if face_ready else "missing",
                mediapipe,
                "Subject detection stays CPU until a GPU delegate is verified.",
                "cpu",
                probe_detail="Legacy summary; inspect the engine rows below.",
            ),
            ComponentStatus(
                "whisper",
                "Whisper transcription",
                True,
                "ready" if whisper else "missing",
                whisper,
                "NVIDIA GPU available." if gpu_ready else "CPU mode. Install NVIDIA acceleration if offered below.",
                "gpu" if gpu_ready else "cpu",
                "PyTorch CUDA" if gpu_ready else "PyTorch CPU",
            ),
            self._component("ollama", "Ollama analysis", False, ollama, "Optional local AI ranking."),
            ComponentStatus(
                "torch",
                "PyTorch runtime",
                True,
                "ready" if torch else "missing",
                torch,
                "CUDA is active." if gpu_ready else "CPU-only runtime.",
                "gpu" if gpu_ready else "cpu",
                "CUDA" if gpu_ready else "CPU",
            ),
        ]
        components.extend(
            self._acceleration_components(
                acceleration_status,
                onnxruntime=onnxruntime,
                onnxruntime_providers=onnxruntime_providers,
            ),
        )
        required_ready = all(component.state == "ready" for component in components if component.required)
        return SetupStatus(tuple(components), HardwareStatus(adapter, driver, gpu_ready), required_ready)

    def install_plan(self, component: str) -> InstallPlan:
        pip = [self.python_executable, "-m", "pip", "install", "--upgrade"]
        if component == "ffmpeg":
            return self._ffmpeg_install_plan()
        plans: dict[str, InstallPlan] = {
            "torch": InstallPlan(
                "torch",
                "PyTorch CPU runtime",
                [*pip, "torch", "torchaudio", "--index-url", CPU_INDEX],
                False,
                "Installs the fixed CPU runtime needed by Whisper and local setup checks.",
            ),
            "opencv": InstallPlan("opencv", "OpenCV", [*pip, "opencv-python"], False, "Installs video frame support."),
            "face_tracking": InstallPlan(
                "face_tracking",
                "Face tracking",
                [*pip, "opencv-python", "mediapipe"],
                False,
                "Installs OpenCV and MediaPipe Tasks for subject selection.",
            ),
            "whisper": InstallPlan(
                "whisper", "Whisper transcription", [*pip, "openai-whisper"], False, "Installs local transcription.",
            ),
            "ollama": InstallPlan(
                "ollama",
                "Ollama analysis",
                [
                    "winget",
                    "install",
                    "--id",
                    "Ollama.Ollama",
                    "--exact",
                    "--source",
                    "winget",
                    "--accept-package-agreements",
                    "--accept-source-agreements",
                    "--disable-interactivity",
                ],
                True,
                "Installs optional local AI analysis. Restart AutoClip, then choose a model.",
            ),
            **acceleration_runtime_plans(self.python_executable),
        }
        if component == "pytorch_cuda_128":
            adapter, _ = self.probe.nvidia_adapter()
            torch = self.probe.package_version("torch")
            if not adapter:
                raise ValueError("NVIDIA GPU not detected. CPU mode remains available.")
            if self.probe.cuda_available() and torch and "+cu128" in torch.casefold():
                raise ValueError(f"CUDA 12.8 PyTorch is already active ({torch}); no reinstall needed.")
            return acceleration_runtime_plans(self.python_executable)[component]
        if component == "whisper_gpu":
            adapter, _ = self.probe.nvidia_adapter()
            torch = self.probe.package_version("torch")
            if not adapter:
                raise ValueError("NVIDIA GPU not detected. CPU mode remains available.")
            if not torch:
                raise ValueError("Install Whisper before enabling NVIDIA acceleration.")
            if self.probe.cuda_available() and "+cu128" in torch.casefold():
                raise ValueError(f"CUDA 12.8 PyTorch is already active ({torch}); no reinstall needed.")
            version = torch.split("+", maxsplit=1)[0]
            return InstallPlan(
                "whisper_gpu",
                "NVIDIA GPU for Whisper",
                [
                    self.python_executable,
                    "-m",
                    "pip",
                    "install",
                    "--upgrade",
                    "--force-reinstall",
                    f"torch=={version}",
                    f"torchaudio=={version}",
                    "--index-url",
                    CUDA_INDEX,
                ],
                True,
                "Installs the official CUDA-enabled PyTorch wheels. Restart AutoClip, then recheck Whisper.",
            )
        try:
            return plans[component]
        except KeyError as error:
            raise ValueError(f"Unsupported setup component: {component}") from error

    def _ffmpeg_install_plan(self) -> InstallPlan:
        if self.platform_name.casefold() == "windows":
            return InstallPlan(
                "ffmpeg",
                "FFmpeg",
                [
                    "winget",
                    "install",
                    "--id",
                    "Gyan.FFmpeg.Shared",
                    "--exact",
                    "--source",
                    "winget",
                    "--accept-package-agreements",
                    "--accept-source-agreements",
                    "--disable-interactivity",
                ],
                True,
                "Windows Package Manager downloads FFmpeg. Restart AutoClip after install.",
            )
        if self._is_ubuntu():
            return InstallPlan(
                "ffmpeg",
                "FFmpeg",
                ["pkexec", "apt-get", "install", "-y", "ffmpeg"],
                False,
                "Ubuntu authorization installs FFmpeg. Recheck setup after install.",
            )
        raise ValueError(f"unsupported_platform: automated FFmpeg install is unavailable on {self.platform_name}")

    def _is_ubuntu(self) -> bool:
        if self.platform_name.casefold() == "ubuntu":
            return True
        if self.platform_name.casefold() != "linux":
            return False
        try:
            return platform_module.freedesktop_os_release().get("ID", "").casefold() == "ubuntu"
        except OSError:
            return False

    def install(self, component: str, report: Reporter) -> InstallPlan:
        plan = self.install_plan(component)
        report("installing", 0.1, f"Installing {plan.label}")
        result = self.runner(plan.command)
        if result.returncode != 0:
            detail = result.output[-4000:] or "Installer exited without output."
            report("failed", 1.0, detail)
            raise RuntimeError(detail)
        report("completed", 1.0, f"{plan.label} installed. {'Restart AutoClip, then recheck.' if plan.requires_restart else 'Recheck setup.'}")
        return plan

    @staticmethod
    def _component(
        component_id: str, label: str, required: bool, version: str | None, detail: str
    ) -> ComponentStatus:
        return ComponentStatus(
            component_id,
            label,
            required,
            "ready" if version else "missing",
            version,
            detail,
        )

    def _acceleration_status(self) -> AccelerationStatus:
        if self.acceleration_manager is None:
            return AccelerationStatus.for_test()
        try:
            return self.acceleration_manager.status()
        except Exception:
            return AccelerationStatus.for_test()

    def _onnxruntime_providers(self) -> tuple[str, ...]:
        providers = getattr(self.probe, "onnxruntime_providers", None)
        if providers is None:
            return ()
        try:
            return tuple(str(provider) for provider in providers())
        except Exception:
            return ()

    @staticmethod
    def _acceleration_components(
        status: AccelerationStatus,
        *,
        onnxruntime: str | None,
        onnxruntime_providers: tuple[str, ...],
    ) -> tuple[ComponentStatus, ...]:
        cuda_probes = tuple(
            status.engines.get(name, EngineProbe())
            for name in ("yunet_cuda", "scrfd_cuda", "retinaface_cuda")
        )
        ort_provider_seen = "CUDAExecutionProvider" in onnxruntime_providers
        ort_probe_detail = next(
            (probe.reason for probe in cuda_probes if probe.reason),
            None,
        )
        components = [
            ComponentStatus(
                "onnxruntime_cuda_128",
                "ONNX Runtime CUDA 12.8",
                False,
                "ready" if onnxruntime and ort_provider_seen else "missing" if not onnxruntime else "unsupported",
                onnxruntime,
                "Uses PyTorch CUDA/cuDNN runtime libraries; CUDA Toolkit is not required.",
                "gpu",
                "CUDAExecutionProvider",
                probe_detail=(
                    ort_probe_detail
                    if ort_provider_seen
                    else "CUDAExecutionProvider is unavailable after ONNX Runtime DLL preload."
                ),
                error_code="tracker_error" if onnxruntime and not ort_provider_seen else None,
            ),
        ]
        for engine_id, label in (
            ("mediapipe_cpu", "MediaPipe CPU"),
            ("mediapipe_gpu", "MediaPipe GPU"),
            ("yunet_cpu", "YuNet CPU"),
            ("yunet_cuda", "YuNet CUDA"),
        ):
            components.append(
                SetupManager._engine_component(
                    engine_id,
                    label,
                    status.engines.get(engine_id, EngineProbe()),
                ),
            )
        for encoder_id, label in (
            ("libx264", "FFmpeg libx264 encoder"),
            ("h264_nvenc", "FFmpeg H.264 NVENC encoder"),
            ("hevc_nvenc", "FFmpeg HEVC NVENC encoder"),
        ):
            components.append(
                SetupManager._encoder_component(
                    f"ffmpeg_{encoder_id}",
                    label,
                    encoder_id,
                    status.encoders.get(encoder_id, EncoderProbe()),
                ),
            )
        return tuple(components)

    @staticmethod
    def _engine_component(component_id: str, label: str, probe: EngineProbe) -> ComponentStatus:
        return ComponentStatus(
            component_id,
            label,
            False,
            probe.state,
            None,
            "Verified by live detector inference.",
            "gpu" if "gpu" in component_id or "cuda" in component_id else "cpu",
            probe.provider or None,
            probe.model_id,
            probe.reason,
            "tracker_error" if probe.state == "failed" else None,
        )

    @staticmethod
    def _encoder_component(
        component_id: str,
        label: str,
        encoder_id: str,
        probe: EncoderProbe,
    ) -> ComponentStatus:
        return ComponentStatus(
            component_id,
            label,
            False,
            probe.state,
            None,
            "Verified from the local FFmpeg encoder list.",
            "gpu" if "nvenc" in encoder_id else "cpu",
            encoder_id,
            probe_detail=probe.reason,
            error_code="nvenc_error" if "nvenc" in encoder_id and probe.state != "ready" else None,
        )


def acceleration_runtime_plans(python_executable: str) -> Mapping[str, InstallPlan]:
    """Return the fixed command-backed acceleration registry owned by the server."""
    return MappingProxyType(
        {
            "pytorch_cuda_128": InstallPlan(
                component="pytorch_cuda_128",
                label="PyTorch CUDA 12.8",
                command=[
                    python_executable,
                    "-m",
                    "pip",
                    "install",
                    "--upgrade",
                    "--force-reinstall",
                    "torch",
                    "torchaudio",
                    "--index-url",
                    CUDA_INDEX,
                ],
                requires_restart=True,
                detail=(
                    "Installs the official CUDA 12.8 PyTorch runtime used to verify GPU tracking. "
                    "Restart AutoClip, then recheck."
                ),
            ),
            "onnxruntime_cuda_128": InstallPlan(
                component="onnxruntime_cuda_128",
                label="ONNX Runtime CUDA 12.8",
                command=[
                    python_executable,
                    "-m",
                    "pip",
                    "install",
                    "--upgrade",
                    "onnxruntime-gpu[cuda,cudnn]==1.26.0",
                ],
                requires_restart=False,
                detail=(
                    "Installs CUDA 12.8 ONNX Runtime. AutoClip requires a successful "
                    "YuNet CUDA inference."
                ),
            ),
        },
    )
