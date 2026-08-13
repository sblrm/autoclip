"""Interactive setup wizard for AutoClip.

Guides the user through all processing choices step-by-step using
Rich prompts, then returns a fully configured AutoClipConfig.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.rule import Rule
from rich.table import Table
from rich.text import Text

from autoclip.models.config import (
    AutoClipConfig,
    ClipConfig,
    OllamaConfig,
    OutputConfig,
    SubtitleConfig,
    TrackerConfig,
    WhisperConfig,
)

console = Console()

# ─── Platform Detection ───────────────────────────────────────────────────────

PLATFORM_PATTERNS: list[tuple[str, str]] = [
    (r"(?:youtube\.com|youtu\.be)", "YouTube"),
    (r"tiktok\.com", "TikTok"),
    (r"instagram\.com", "Instagram"),
    (r"(?:twitter\.com|x\.com)", "X (Twitter)"),
    (r"twitch\.tv", "Twitch"),
    (r"facebook\.com|fb\.watch", "Facebook"),
    (r"vimeo\.com", "Vimeo"),
    (r"dailymotion\.com", "Dailymotion"),
    (r"reddit\.com", "Reddit"),
]


def detect_platform(url: str) -> str:
    """Detect the video platform from a URL."""
    for pattern, name in PLATFORM_PATTERNS:
        if re.search(pattern, url, re.IGNORECASE):
            return name
    return "Unknown"


# ─── Ollama Helpers ───────────────────────────────────────────────────────────


def _get_installed_ollama_models() -> list[str]:
    """Return list of locally installed Ollama models, empty if not running."""
    try:
        import ollama
        response = ollama.list()
        # Handle both old and new ollama SDK response shapes
        models = response.get("models", []) if isinstance(response, dict) else getattr(response, "models", [])
        names = []
        for m in models:
            name = m.get("name", "") if isinstance(m, dict) else getattr(m, "model", getattr(m, "name", ""))
            if name:
                names.append(name)
        return names
    except Exception:
        return []


def _is_cuda_available() -> bool:
    """Check if CUDA GPU is available for torch."""
    try:
        import torch
        return torch.cuda.is_available()
    except Exception:
        return False


# ─── Wizard Steps ─────────────────────────────────────────────────────────────


def _step_header(step: int, total: int, title: str) -> None:
    console.print()
    console.print(Rule(
        f"[bold cyan]Step {step}/{total}[/]  [white]{title}[/]",
        style="dim cyan",
    ))
    console.print()


def _ask_url() -> str:
    """Step 1: Ask for video URL and validate."""
    from autoclip.utils.validators import is_valid_url

    while True:
        url = Prompt.ask("  [cyan]Paste video URL[/]").strip()
        if not url:
            console.print("  [yellow]URL tidak boleh kosong.[/]")
            continue
        if not is_valid_url(url):
            console.print("  [red]URL tidak valid. Pastikan formatnya benar (contoh: https://youtu.be/...).[/]")
            continue

        platform = detect_platform(url)
        icon = {
            "YouTube": "[red]YouTube[/]",
            "TikTok": "[white]TikTok[/]",
            "Instagram": "[magenta]Instagram[/]",
            "X (Twitter)": "[cyan]X (Twitter)[/]",
            "Twitch": "[purple]Twitch[/]",
            "Facebook": "[blue]Facebook[/]",
            "Vimeo": "[cyan]Vimeo[/]",
        }.get(platform, f"[dim]{platform}[/]")

        console.print(f"  [green][OK][/] Platform terdeteksi: {icon}")
        return url


def _ask_analysis_mode() -> tuple[bool, Optional[str]]:
    """Step 2: AI (Ollama) or Heuristic, and which model.

    Returns (use_ai, ollama_model_name).
    """
    installed = _get_installed_ollama_models()
    ollama_running = len(installed) > 0

    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("Key", style="bold cyan", width=4)
    table.add_column("Mode", style="white")
    table.add_column("Info", style="dim")

    if ollama_running:
        table.add_row("1", "AI (Ollama)", f"Direkomendasikan — {len(installed)} model tersedia")
        table.add_row("2", "Heuristic", "Cepat, offline, tanpa LLM")
    else:
        table.add_row("1", "Heuristic", "Ollama tidak terdeteksi — mode ini otomatis aktif")
        table.add_row("2", "AI (Ollama)", "[dim]Ollama tidak running — install dari ollama.ai[/]")

    console.print(table)
    console.print()

    if not ollama_running:
        console.print("  [yellow][INFO] Ollama tidak terdeteksi. Menggunakan mode Heuristic.[/]")
        return False, None

    choice = Prompt.ask("  Pilihan", choices=["1", "2"], default="1")

    if choice == "2":
        return False, None

    # AI mode — pick model
    console.print()
    console.print("  [dim]Model Ollama yang tersedia:[/]")
    model_table = Table(show_header=False, box=None, padding=(0, 2))
    model_table.add_column("Key", style="bold cyan", width=4)
    model_table.add_column("Model", style="white")
    for i, m in enumerate(installed, 1):
        model_table.add_row(str(i), m)

    console.print(model_table)
    console.print()

    default_model = installed[0]
    model_choice = Prompt.ask(
        f"  Pilih model (Enter untuk [cyan]{default_model}[/])",
        default="1",
    )

    try:
        idx = int(model_choice) - 1
        selected = installed[idx] if 0 <= idx < len(installed) else default_model
    except ValueError:
        # User typed model name directly
        selected = model_choice if model_choice in installed else default_model

    console.print(f"  [green][OK][/] Model: [cyan]{selected}[/]")
    return True, selected


def _ask_whisper_model() -> str:
    """Step 3: Whisper model size."""
    models = [
        ("tiny",   "Paling cepat, akurasi rendah  (~75MB)"),
        ("base",   "Cepat, akurasi cukup           (~145MB)  [recommended]"),
        ("small",  "Balance antara kecepatan & akurasi (~465MB)"),
        ("medium", "Akurat, lebih lambat           (~1.5GB)"),
        ("large",  "Paling akurat, paling lambat   (~3GB)"),
    ]

    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("Key", style="bold cyan", width=4)
    table.add_column("Model", style="white", width=10)
    table.add_column("Info", style="dim")
    for i, (name, info) in enumerate(models, 1):
        table.add_row(str(i), name, info)

    console.print(table)
    console.print()

    choice = Prompt.ask("  Pilihan", choices=["1", "2", "3", "4", "5"], default="2")
    selected = models[int(choice) - 1][0]
    console.print(f"  [green][OK][/] Whisper model: [cyan]{selected}[/]")
    return selected


def _ask_device() -> tuple[str, bool]:
    """Step 4: CPU or CUDA. Auto-detects and asks only if CUDA available.

    Returns (device, fp16).
    """
    cuda_available = _is_cuda_available()

    if not cuda_available:
        console.print("  [dim]GPU (CUDA) tidak terdeteksi. Menggunakan CPU.[/]")
        return "cpu", False

    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("Key", style="bold cyan", width=4)
    table.add_column("Device", style="white", width=12)
    table.add_column("Info", style="dim")
    table.add_row("1", "GPU (CUDA)", "Lebih cepat ~3-5x, butuh NVIDIA GPU  [recommended]")
    table.add_row("2", "CPU", "Kompatibel semua hardware, lebih lambat")
    console.print(table)
    console.print()

    choice = Prompt.ask("  Pilihan", choices=["1", "2"], default="1")
    if choice == "1":
        console.print("  [green][OK][/] Device: [cyan]GPU (CUDA)[/] dengan FP16")
        return "cuda", True
    console.print("  [green][OK][/] Device: [cyan]CPU[/]")
    return "cpu", False


def _ask_output_format() -> tuple[int, int, bool]:
    """Step 5: Output format.

    Returns (width, height, keep_original).
    """
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("Key", style="bold cyan", width=4)
    table.add_column("Format", style="white", width=28)
    table.add_column("Info", style="dim")
    table.add_row("1", "9:16 Vertikal (1080 x 1920)", "TikTok / Reels / Shorts ready  [recommended]")
    table.add_row("2", "Pertahankan rasio asli", "Output sama seperti video sumber")
    console.print(table)
    console.print()

    choice = Prompt.ask("  Pilihan", choices=["1", "2"], default="1")
    if choice == "1":
        console.print("  [green][OK][/] Format: [cyan]9:16 Vertikal (1080x1920)[/]")
        return 1080, 1920, False
    console.print("  [green][OK][/] Format: [cyan]Original (pertahankan rasio)[/]")
    return 0, 0, True


def _ask_subtitle() -> bool:
    """Step 6: Enable subtitles?"""
    result = Confirm.ask("  Tambahkan subtitle karaoke otomatis?", default=True)
    status = "[green][OK][/] Subtitle aktif" if result else "[dim]Subtitle dinonaktifkan[/]"
    console.print(f"  {status}")
    return result


def _ask_clip_settings() -> tuple[int, int, int, int]:
    """Step 7: Clip count and score threshold (simple defaults shown).

    Returns (max_clips, min_score, min_duration, max_duration).
    """
    console.print("  [dim]Tekan Enter untuk menggunakan nilai default.[/]")
    console.print()

    max_clips_str = Prompt.ask("  Maksimal jumlah clip   ", default="10")
    min_score_str = Prompt.ask("  Skor viral minimum (1-10)", default="6")
    min_dur_str   = Prompt.ask("  Durasi minimum clip (detik)", default="30")
    max_dur_str   = Prompt.ask("  Durasi maksimum clip (detik)", default="90")

    def _int(val: str, default: int) -> int:
        try:
            return int(val)
        except ValueError:
            return default

    return (
        _int(max_clips_str, 10),
        _int(min_score_str, 6),
        _int(min_dur_str, 30),
        _int(max_dur_str, 90),
    )


def _ask_output_folder(video_title: str = "") -> Path:
    """Step 9: Output folder selection."""
    safe_title = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", video_title)
    safe_title = re.sub(r"\s+", "_", safe_title.strip())[:50] or "clips"
    default_path = Path("./autoclip_output") / safe_title

    console.print(f"  [dim]Default: [cyan]{default_path}[/][/]")
    console.print("  [dim]Ketik path folder lain, atau tekan Enter untuk default.[/]")
    console.print()

    raw = Prompt.ask("  Output folder", default=str(default_path)).strip()
    chosen = Path(raw)
    console.print(f"  [green][OK][/] Output: [cyan]{chosen}[/]")
    return chosen


def _is_mediapipe_available() -> bool:
    """Return True if mediapipe is importable."""
    try:
        import mediapipe  # noqa: F401
        return True
    except ImportError:
        return False


def _ask_face_tracking() -> bool:
    """Step 8: Ask whether to enable face-tracking smart crop."""
    mp_available = _is_mediapipe_available()
    cv_available = True
    try:
        import cv2  # noqa: F401
    except ImportError:
        cv_available = False

    if not cv_available:
        console.print(
            "  [dim]Face tracking membutuhkan opencv-python dan mediapipe.[/]\n"
            "  [yellow]Install dengan: pip install opencv-python mediapipe[/]"
        )
        return False

    engine = "MediaPipe (akurat)" if mp_available else "OpenCV Haar (fallback)"
    console.print(f"  [dim]Engine terdeteksi: {engine}[/]")
    console.print()

    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("Key", style="bold cyan", width=4)
    table.add_column("Mode", style="white", width=26)
    table.add_column("Info", style="dim")
    table.add_row("1", "Aktifkan face tracking", "Crop mengikuti wajah — cocok untuk podcast/talk")
    table.add_row("2", "Center crop biasa", "Crop ke tengah frame (default, lebih cepat)")
    console.print(table)
    console.print()

    choice = Prompt.ask("  Pilihan", choices=["1", "2"], default="2")
    if choice == "1":
        console.print("  [green][OK][/] Face tracking aktif — crop akan mengikuti wajah speaker")
        return True
    console.print("  [dim]Center crop digunakan[/]")
    return False


# ─── Summary & Confirm ────────────────────────────────────────────────────────


def _show_summary(choices: dict) -> None:
    """Show a summary table of all wizard choices."""
    console.print()
    console.print(Rule("[bold white]Ringkasan Pilihan[/]", style="dim"))
    console.print()

    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("Label", style="dim", width=26)
    table.add_column("Value", style="cyan bold")

    platform = detect_platform(choices["url"])
    table.add_row("URL", choices["url"][:60] + "..." if len(choices["url"]) > 60 else choices["url"])
    table.add_row("Platform", platform)
    table.add_row("Analysis", "AI (Ollama: " + choices["ollama_model"] + ")" if choices["use_ai"] else "Heuristic")
    table.add_row("Whisper model", choices["whisper_model"])
    table.add_row("Device", choices["device"].upper())
    fmt = f"{choices['width']}x{choices['height']}" if not choices["keep_original"] else "Original"
    table.add_row("Output format", fmt)
    table.add_row("Subtitle", "Ya" if choices["subtitle"] else "Tidak")
    table.add_row("Face tracking", "Aktif" if choices["face_tracking"] else "Tidak")
    table.add_row("Max clips", str(choices["max_clips"]))
    table.add_row("Min score", f"{choices['min_score']}/10")
    table.add_row("Durasi clip", f"{choices['min_duration']}s - {choices['max_duration']}s")
    table.add_row("Output folder", str(choices["output_dir"]))

    console.print(table)
    console.print()


# ─── Main Entry Point ─────────────────────────────────────────────────────────


def run_wizard() -> tuple[str, AutoClipConfig]:
    """Run the interactive wizard.

    Returns:
        (url, config) — video URL and fully configured AutoClipConfig.
    """
    from autoclip import __version__
    from autoclip.utils.console import print_banner

    print_banner()

    console.print(Panel(
        "[dim]Jawab beberapa pertanyaan berikut untuk mulai memproses video.\n"
        "Tekan [bold]Ctrl+C[/] kapan saja untuk membatalkan.[/]",
        border_style="dim cyan",
        padding=(0, 2),
    ))

    total_steps = 9

    # ── Step 1: URL ───────────────────────────────────────────────────────────
    _step_header(1, total_steps, "Video URL")
    url = _ask_url()

    # ── Step 2: Analysis Mode ─────────────────────────────────────────────────
    _step_header(2, total_steps, "Mode Analisis")
    use_ai, ollama_model = _ask_analysis_mode()

    # ── Step 3: Whisper Model ─────────────────────────────────────────────────
    _step_header(3, total_steps, "Model Transkripsi (Whisper)")
    whisper_model = _ask_whisper_model()

    # ── Step 4: Device ────────────────────────────────────────────────────────
    _step_header(4, total_steps, "Hardware (CPU / GPU)")
    device, fp16 = _ask_device()

    # ── Step 5: Output Format ─────────────────────────────────────────────────
    _step_header(5, total_steps, "Format Output Video")
    width, height, keep_original = _ask_output_format()

    # ── Step 6: Subtitle ──────────────────────────────────────────────────────
    _step_header(6, total_steps, "Subtitle")
    subtitle = _ask_subtitle()

    # ── Step 7: Clip Settings ─────────────────────────────────────────────────
    _step_header(7, total_steps, "Pengaturan Clip")
    max_clips, min_score, min_duration, max_duration = _ask_clip_settings()

    # ── Step 8: Face Tracking ─────────────────────────────────────────────────
    _step_header(8, total_steps, "Face Tracking Smart Crop")
    face_tracking = _ask_face_tracking()

    # ── Step 9: Output Folder ─────────────────────────────────────────────────
    _step_header(9, total_steps, "Folder Output")
    output_dir = _ask_output_folder()

    # ── Summary & Confirm ─────────────────────────────────────────────────────
    choices = {
        "url": url,
        "use_ai": use_ai,
        "ollama_model": ollama_model or "llama3",
        "whisper_model": whisper_model,
        "device": device,
        "fp16": fp16,
        "width": width,
        "height": height,
        "keep_original": keep_original,
        "subtitle": subtitle,
        "max_clips": max_clips,
        "min_score": min_score,
        "min_duration": min_duration,
        "max_duration": max_duration,
        "face_tracking": face_tracking,
        "output_dir": output_dir,
    }

    _show_summary(choices)

    if not Confirm.ask("  [bold]Mulai proses?[/]", default=True):
        console.print("\n  [dim]Dibatalkan.[/]\n")
        raise SystemExit(0)

    console.print()

    # ── Build config ──────────────────────────────────────────────────────────
    cfg = AutoClipConfig(
        whisper=WhisperConfig(
            model=whisper_model,
            device=device,
            fp16=fp16,
        ),
        ollama=OllamaConfig(
            model=choices["ollama_model"],
        ),
        output=OutputConfig(
            width=width if not keep_original else 0,
            height=height if not keep_original else 0,
            directory=str(output_dir.parent),
        ),
        clip=ClipConfig(
            max_clips=max_clips,
            min_score=min_score,
            min_duration=min_duration,
            max_duration=max_duration,
        ),
        subtitle=SubtitleConfig(
            enabled=subtitle,
        ),
        tracker=TrackerConfig(
            enabled=face_tracking,
        ),
    )

    # Store output dir name for use in process command
    cfg._wizard_output_dir = output_dir  # type: ignore[attr-defined]
    cfg._wizard_use_ai = use_ai         # type: ignore[attr-defined]

    return url, cfg
