"""Local dependency probes and explicit, allow-listed repair plans."""

from __future__ import annotations

import importlib
import subprocess
import sys
from dataclasses import asdict, dataclass
from typing import Callable, Protocol, Sequence


CUDA_INDEX = "https://download.pytorch.org/whl/cu130"


@dataclass(frozen=True)
class ComponentStatus:
    id: str
    label: str
    required: bool
    state: str
    version: str | None
    detail: str
    acceleration: str | None = None


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
    ) -> None:
        self.probe = probe or SystemProbe()
        self.runner = runner
        self.python_executable = python_executable or sys.executable

    def status(self) -> SetupStatus:
        ffmpeg = self.probe.executable_version("ffmpeg")
        opencv = self.probe.package_version("cv2")
        mediapipe = self.probe.package_version("mediapipe")
        whisper = self.probe.package_version("whisper")
        ollama = self.probe.executable_version("ollama")
        torch = self.probe.package_version("torch")
        adapter, driver = self.probe.nvidia_adapter()
        gpu_ready = self.probe.cuda_available()
        face_ready = bool(opencv and mediapipe)
        components = (
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
            ),
            ComponentStatus(
                "whisper",
                "Whisper transcription",
                True,
                "ready" if whisper else "missing",
                whisper,
                "NVIDIA GPU available." if gpu_ready else "CPU mode. Install NVIDIA acceleration if offered below.",
                "gpu" if gpu_ready else "cpu",
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
            ),
        )
        required_ready = all(component.state == "ready" for component in components if component.required)
        return SetupStatus(components, HardwareStatus(adapter, driver, gpu_ready), required_ready)

    def install_plan(self, component: str) -> InstallPlan:
        pip = [self.python_executable, "-m", "pip", "install", "--upgrade"]
        plans: dict[str, InstallPlan] = {
            "ffmpeg": InstallPlan(
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
        }
        if component == "whisper_gpu":
            adapter, _ = self.probe.nvidia_adapter()
            torch = self.probe.package_version("torch")
            if not adapter:
                raise ValueError("NVIDIA GPU not detected. CPU mode remains available.")
            if not torch:
                raise ValueError("Install Whisper before enabling NVIDIA acceleration.")
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
