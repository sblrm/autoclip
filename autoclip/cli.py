"""AutoClip CLI — main command interface built with Typer + Rich."""

from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

# Force UTF-8 output on Windows to handle any unicode in titles etc.
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

app = typer.Typer(
    name="autoclip",
    help="AutoClip -- AI-powered video clipper for content creators.",
    add_completion=False,
    no_args_is_help=False,   # We handle no-args ourselves with the wizard
    rich_markup_mode="rich",
    pretty_exceptions_show_locals=False,
    invoke_without_command=True,
)

console = Console()


# ─── Version callback ─────────────────────────────────────────────────────────


def _version_callback(value: bool) -> None:
    if value:
        from autoclip import __version__
        typer.echo(f"AutoClip v{__version__}")
        raise typer.Exit()


@app.callback()
def main(
    ctx: typer.Context,
    version: bool = typer.Option(
        False,
        "--version", "-v",
        callback=_version_callback,
        is_eager=True,
        help="Show version and exit.",
    ),
) -> None:
    """AutoClip -- AI-powered video clipper for TikTok, Reels & Shorts."""
    # If no subcommand was given, launch the interactive wizard
    if ctx.invoked_subcommand is None:
        _run_wizard_mode()


def _run_wizard_mode() -> None:
    """Launch the interactive wizard, then run the full pipeline."""
    from autoclip.wizard import run_wizard

    try:
        url, cfg = run_wizard()
    except (KeyboardInterrupt, SystemExit):
        console.print("\n  [dim]Keluar.[/]\n")
        raise typer.Exit(0)

    # Resolve wizard-injected output dir
    output_dir: Path = getattr(cfg, "_wizard_output_dir", None)  # type: ignore[attr-defined]
    use_ai: bool = getattr(cfg, "_wizard_use_ai", True)          # type: ignore[attr-defined]

    # If user chose heuristic, temporarily disable Ollama by setting model to ""
    if not use_ai:
        cfg.ollama.model = ""

    _run_pipeline(
        url=url,
        cfg=cfg,
        output_dir=output_dir,
        no_subtitle=not cfg.subtitle.enabled,
        no_cache=False,
        verbose=False,
    )


# ─── process ──────────────────────────────────────────────────────────────────


@app.command()
def process(
    url: str = typer.Argument(..., help="Video URL (YouTube, TikTok, Instagram, etc.)"),
    config_path: Optional[Path] = typer.Option(
        None, "--config", "-c",
        help="Path to YAML config file (default: ~/.autoclip/config.yaml)",
    ),
    whisper_model: Optional[str] = typer.Option(
        None, "--model", "-m",
        help="Whisper model size: tiny | base | small | medium | large",
    ),
    llm_model: Optional[str] = typer.Option(
        None, "--llm",
        help="Ollama model name: llama3 | mistral | gemma",
    ),
    language: Optional[str] = typer.Option(
        None, "--language", "-l",
        help="Force transcript language: id | en (default: auto-detect)",
    ),
    min_duration: Optional[int] = typer.Option(
        None, "--min-duration",
        help="Minimum clip duration in seconds (default: 30)",
    ),
    max_duration: Optional[int] = typer.Option(
        None, "--max-duration",
        help="Maximum clip duration in seconds (default: 90)",
    ),
    max_clips: Optional[int] = typer.Option(
        None, "--max-clips",
        help="Maximum number of clips to generate (default: 10)",
    ),
    min_score: Optional[int] = typer.Option(
        None, "--min-score",
        help="Minimum viral score to include (1-10, default: 6)",
    ),
    output_dir: Optional[Path] = typer.Option(
        None, "--output", "-o",
        help="Output directory (default: ./autoclip_output/<video-title>)",
    ),
    no_subtitle: bool = typer.Option(
        False, "--no-subtitle",
        help="Skip subtitle generation",
    ),
    no_cache: bool = typer.Option(
        False, "--no-cache",
        help="Ignore cached transcription and re-transcribe",
    ),
    device: Optional[str] = typer.Option(
        None, "--device",
        help="Computing device: cpu | cuda (default: cpu)",
    ),
    face_track: bool = typer.Option(
        False, "--face-track",
        help="Enable face-tracking smart crop (requires opencv-python + mediapipe)",
    ),
    verbose: bool = typer.Option(
        False, "--verbose",
        help="Enable verbose logging",
    ),
) -> None:
    """
    Process a video URL through the full AutoClip pipeline.

    Downloads the video, transcribes it, detects viral moments,
    cuts clips, and generates subtitles -- all automatically.

    [bold cyan]Examples:[/]
      autoclip process https://youtu.be/dQw4w9WgXcQ
      autoclip process https://youtu.be/dQw4w9WgXcQ --model small --max-clips 5
      autoclip process <url> --no-subtitle --output ./my_clips
    """
    from autoclip.config import load_config
    from autoclip.utils.validators import is_valid_url
    from autoclip.utils.console import print_banner, print_error

    print_banner()

    if not is_valid_url(url):
        print_error(f"Invalid URL: [cyan]{url}[/]")
        raise typer.Exit(1)

    cfg = load_config(config_path)

    # Apply CLI overrides
    if whisper_model:
        cfg.whisper.model = whisper_model
    if llm_model:
        cfg.ollama.model = llm_model
    if language:
        cfg.whisper.language = language
    if min_duration is not None:
        cfg.clip.min_duration = min_duration
    if max_duration is not None:
        cfg.clip.max_duration = max_duration
    if max_clips is not None:
        cfg.clip.max_clips = max_clips
    if min_score is not None:
        cfg.clip.min_score = min_score
    if device:
        cfg.whisper.device = device
    if no_subtitle:
        cfg.subtitle.enabled = False
    if face_track:
        cfg.tracker.enabled = True

    _run_pipeline(
        url=url,
        cfg=cfg,
        output_dir=output_dir,
        no_subtitle=no_subtitle,
        no_cache=no_cache,
        verbose=verbose,
    )


def _run_pipeline(
    url: str,
    cfg,
    output_dir: Optional[Path],
    no_subtitle: bool,
    no_cache: bool,
    verbose: bool,
) -> None:
    """Shared pipeline: download → transcribe → analyze → subtitle → export."""
    from autoclip.core.analyzer import analyze_transcript
    from autoclip.core.clipper import create_clips as _create_clips
    from autoclip.core.downloader import download_video, _fetch_metadata
    from autoclip.core.subtitle import generate_subtitles
    from autoclip.core.transcriber import transcribe
    from autoclip.utils.console import (
        print_clips_table,
        print_error,
        print_info,
        print_step,
        print_success,
        print_summary,
        print_warning,
    )

    start_time = time.time()

    # ── Step 1: Download ──────────────────────────────────────────────────────
    print_step(1, 5, "Downloading video...", "[DL]")

    meta = None
    with console.status("[cyan]Fetching video info...[/]", spinner="dots"):
        try:
            meta = _fetch_metadata(url)
        except Exception:
            meta = None

    if meta:
        print_info(
            f"[bold]{meta.title}[/] by [cyan]{meta.uploader}[/] "
            f"({_fmt_duration(meta.duration)})"
        )

    safe_title = _safe_dirname(meta.title if meta else "video")
    final_output_dir = output_dir or Path(cfg.output.directory) / safe_title
    final_output_dir.mkdir(parents=True, exist_ok=True)
    cache_dir = final_output_dir / ".cache"

    with console.status("[cyan]Downloading...[/]", spinner="dots"):
        try:
            dl_result = download_video(url=url, output_dir=final_output_dir / "source")
        except Exception as e:
            print_error(f"Download failed: {e}")
            raise typer.Exit(1)

    if dl_result.was_cached:
        print_success("Using cached video download.")
    else:
        print_success(f"Downloaded -> [cyan]{dl_result.video_path.name}[/]")

    # ── Step 2: Transcribe ────────────────────────────────────────────────────
    print_step(2, 5, f"Transcribing with Whisper ({cfg.whisper.model})...", "[SR]")

    with console.status(
        f"[cyan]Loading Whisper '{cfg.whisper.model}' model...[/]", spinner="dots"
    ):
        try:
            transcript = transcribe(
                video_path=dl_result.video_path,
                config=cfg.whisper,
                cache_dir=None if no_cache else cache_dir,
            )
        except Exception as e:
            print_error(f"Transcription failed: {e}")
            if verbose:
                import traceback
                traceback.print_exc()
            raise typer.Exit(1)

    lang_label = transcript.language.upper()
    print_success(
        f"Transcribed [{lang_label}] -- {len(transcript.segments)} segments, "
        f"{len(transcript.full_text.split())} words"
    )
    if verbose:
        print_info(f"Preview: {transcript.full_text[:200]}...")

    # ── Step 3: Analyze ───────────────────────────────────────────────────────
    analysis_label = cfg.ollama.model if cfg.ollama.model else "heuristic"
    print_step(3, 5, f"Analyzing viral moments ({analysis_label})...", "[AI]")

    with console.status("[cyan]Analyzing transcript...[/]", spinner="dots"):
        try:
            clips = analyze_transcript(
                transcript=transcript,
                ollama_config=cfg.ollama,
                clip_config=cfg.clip,
            )
        except Exception as e:
            print_error(f"Analysis failed: {e}")
            if verbose:
                import traceback
                traceback.print_exc()
            raise typer.Exit(1)

    if not clips:
        print_warning(
            "No viral moments detected. "
            "Try lowering --min-score or adjusting --min-duration."
        )
        raise typer.Exit(0)

    print_success(f"Found [bold]{len(clips)}[/] viral moment(s)")
    print_clips_table(clips, meta.title if meta else "")

    # ── Step 4: Subtitles ─────────────────────────────────────────────────────
    subtitle_paths: dict[int, Path] = {}

    if cfg.subtitle.enabled and not no_subtitle:
        print_step(4, 5, "Generating ASS subtitles...", "[CC]")
        subs_dir = final_output_dir / "subtitles"

        with console.status("[cyan]Generating subtitles...[/]", spinner="dots"):
            for i, clip in enumerate(clips):
                sub_path = subs_dir / f"clip_{i + 1:02d}.ass"
                try:
                    generate_subtitles(
                        transcript=transcript,
                        clip=clip,
                        output_path=sub_path,
                        config=cfg.subtitle,
                    )
                    subtitle_paths[i] = sub_path
                except Exception as e:
                    print_warning(f"Subtitle generation failed for clip {i + 1}: {e}")

        print_success(f"Generated {len(subtitle_paths)} subtitle file(s)")
    else:
        print_step(4, 5, "Skipping subtitles", "[CC]")

    # ── Step 5: Export ────────────────────────────────────────────────────────
    fmt_label = (
        f"{cfg.output.width}x{cfg.output.height}" if cfg.output.width else "original ratio"
    )
    tracker_label = " + face tracking" if getattr(cfg, "tracker", None) and cfg.tracker.enabled else ""
    print_step(5, 5, f"Exporting {len(clips)} clip(s) [{fmt_label}{tracker_label}]...", "[CUT]")

    output_paths = []
    with console.status("[cyan]Exporting clips...[/]", spinner="dots") as status:
        for i, clip in enumerate(clips):
            status.update(
                f"[cyan]Exporting clip {i + 1}/{len(clips)}: "
                f"{clip.suggested_title[:40]}...[/]"
            )
            try:
                paths = _create_clips(
                    video_path=dl_result.video_path,
                    clips=[clip],
                    output_dir=final_output_dir,
                    output_config=cfg.output,
                    subtitle_paths={0: subtitle_paths[i]} if i in subtitle_paths else None,
                    tracker_config=cfg.tracker,
                )
                output_paths.extend(paths)
            except Exception as e:
                print_warning(f"Failed to export clip {i + 1}: {e}")
                if verbose:
                    import traceback
                    traceback.print_exc()

    elapsed = time.time() - start_time

    if output_paths:
        print_summary(
            clips=[clips[i] for i in range(len(output_paths))],
            output_paths=output_paths,
            output_dir=str(final_output_dir),
            elapsed_seconds=elapsed,
        )
    else:
        print_error("No clips were successfully exported.")
        raise typer.Exit(1)




# ─── init ─────────────────────────────────────────────────────────────────────


@app.command()
def init(
    force: bool = typer.Option(
        False, "--force", "-f",
        help="Overwrite existing config file.",
    ),
) -> None:
    """
    Initialize AutoClip configuration file.

    Creates ~/.autoclip/config.yaml with default settings and comments.
    """
    from autoclip.config import init_config
    from autoclip.utils.console import print_banner, print_success, print_warning

    print_banner()
    path, created = init_config(force=force)

    if created:
        print_success(f"Config initialized -> [cyan]{path}[/]")
        console.print("\n  Edit this file to customize AutoClip defaults.\n")
    else:
        print_warning(
            f"Config already exists at [cyan]{path}[/]. "
            "Use [bold]--force[/] to overwrite."
        )


# ─── check ────────────────────────────────────────────────────────────────────


@app.command()
def check() -> None:
    """
    Check all AutoClip dependencies.

    Verifies FFmpeg, Whisper, Ollama, and yt-dlp are installed and accessible.
    """
    from autoclip.utils.console import print_banner
    from autoclip.utils.validators import check_dependencies, check_yt_dlp

    print_banner()
    console.print("[bold]Checking dependencies...[/]\n")

    dep_status = check_dependencies()
    ytdlp_ok, ytdlp_ver = check_yt_dlp()

    table = Table(border_style="dim", show_header=True, header_style="bold white")
    table.add_column("Dependency", style="white", width=20)
    table.add_column("Status", width=12)
    table.add_column("Details", style="dim")

    def status_cell(ok: bool) -> Text:
        return Text("[OK]", style="bold green") if ok else Text("[MISSING]", style="bold red")

    table.add_row(
        "FFmpeg",
        status_cell(dep_status.ffmpeg_available),
        f"v{dep_status.ffmpeg_version}" if dep_status.ffmpeg_version else "Not found",
    )
    table.add_row(
        "FFprobe",
        status_cell(dep_status.ffprobe_available),
        "Bundled with FFmpeg" if dep_status.ffprobe_available else "Not found",
    )
    table.add_row(
        "yt-dlp",
        status_cell(ytdlp_ok),
        f"v{ytdlp_ver}" if ytdlp_ok else "Not found -- run: pip install yt-dlp",
    )
    table.add_row(
        "OpenAI Whisper",
        status_cell(dep_status.whisper_available),
        "Installed" if dep_status.whisper_available
        else "Not found -- run: pip install openai-whisper",
    )
    table.add_row(
        "Ollama",
        status_cell(dep_status.ollama_available),
        f"{len(dep_status.ollama_models)} model(s): "
        f"{', '.join(dep_status.ollama_models[:3]) or 'none'}"
        if dep_status.ollama_available
        else "Server not running -- install from ollama.ai",
    )

    console.print(table)
    console.print()

    if dep_status.errors:
        console.print("[bold red]Issues found:[/]")
        for err in dep_status.errors:
            console.print(f"  [red]*[/] {err}")
        console.print()

    if dep_status.all_ok and ytdlp_ok:
        console.print("[bold green]All dependencies satisfied. AutoClip is ready![/]\n")
    elif dep_status.minimum_ok:
        console.print(
            "[bold yellow]Minimum requirements met, but some features may be limited.[/]\n"
        )
    else:
        console.print(
            "[bold red]Missing required dependencies. Please install them and run again.[/]\n"
        )
        raise typer.Exit(1)


# ─── config ───────────────────────────────────────────────────────────────────


@app.command(name="config")
def show_config(
    config_path: Optional[Path] = typer.Option(
        None, "--config", "-c",
        help="Path to config file (default: ~/.autoclip/config.yaml)",
    ),
) -> None:
    """
    Show current AutoClip configuration.
    """
    from autoclip.config import CONFIG_FILE, load_config
    from autoclip.utils.console import print_banner

    print_banner()
    cfg = load_config(config_path)
    path = config_path or CONFIG_FILE

    exists_label = "[green]exists[/]" if path.exists() else "[yellow]using defaults[/]"
    console.print(
        Panel(
            f"[dim]Config file:[/] [cyan]{path}[/] ({exists_label})",
            border_style="dim cyan",
        )
    )
    console.print()

    cfg_dict = cfg.model_dump()
    console.print_json(data=cfg_dict)


# ─── Helpers ──────────────────────────────────────────────────────────────────


def _fmt_duration(seconds: float) -> str:
    total = int(seconds)
    h = total // 3600
    m = (total % 3600) // 60
    s = total % 60
    if h:
        return f"{h}h {m:02d}m {s:02d}s"
    return f"{m}m {s:02d}s"


def _safe_dirname(title: str, max_len: int = 60) -> str:
    import re
    safe = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", title)
    safe = re.sub(r"\s+", "_", safe.strip())
    return safe[:max_len].rstrip("_. ") or "video"


if __name__ == "__main__":
    app()
