"""Rich console output helpers for AutoClip."""

from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)
from rich.table import Table
from rich.text import Text
from rich.theme import Theme

from autoclip import __version__
from autoclip.models.clip import Clip

# ─── Custom Theme ──────────────────────────────────────────────────────────────
THEME = Theme(
    {
        "autoclip.accent": "bold cyan",
        "autoclip.success": "bold green",
        "autoclip.warning": "bold yellow",
        "autoclip.error": "bold red",
        "autoclip.muted": "dim white",
        "autoclip.score.high": "bold green",
        "autoclip.score.mid": "bold yellow",
        "autoclip.score.low": "bold red",
        "autoclip.step": "bold blue",
    }
)

console = Console(theme=THEME, highlight=False)


ASCII_BANNER = r"""
   ___         __       ________      
  / _ | __ __/ /____  / ___/ (_)____ 
 / __ |/ // / __/ _ \/ /__/ / / __/ 
/_/ |_|\_,_/\__/\___/\___/_/_/\__/  
"""


def print_banner() -> None:
    """Print the AutoClip ASCII banner with version info."""
    banner_text = Text(ASCII_BANNER, style="bold cyan")
    subtitle = Text(
        f"  v{__version__} - AI-Powered Video Clipper for Content Creators\n",
        style="dim cyan"
    )
    console.print(banner_text)
    console.print(subtitle)


def print_step(step_num: int, total_steps: int, message: str, emoji: str = "▶") -> None:
    """Print a styled pipeline step indicator."""
    step_label = Text(f"  {emoji} Step {step_num}/{total_steps}", style="autoclip.step")
    msg = Text(f" — {message}", style="white")
    console.print(step_label + msg)


def print_success(message: str) -> None:
    """Print a success message."""
    console.print(f"  [autoclip.success][OK][/] {message}")


def print_warning(message: str) -> None:
    """Print a warning message."""
    console.print(f"  [autoclip.warning][WARN][/] {message}")


def print_error(message: str) -> None:
    """Print an error message."""
    console.print(f"  [autoclip.error][ERR][/] {message}")


def print_info(message: str) -> None:
    """Print an info message."""
    console.print(f"  [autoclip.muted][i][/] {message}")


def get_score_style(score: int) -> str:
    """Return Rich style name based on viral score."""
    if score >= 8:
        return "autoclip.score.high"
    elif score >= 6:
        return "autoclip.score.mid"
    return "autoclip.score.low"


def get_score_bar(score: int, width: int = 10) -> str:
    """Return a visual score bar like [####......] 8/10."""
    filled = int((score / 10) * width)
    bar = "#" * filled + "." * (width - filled)
    return f"[{bar}] {score}/10"


def print_clips_table(clips: list[Clip], video_title: str = "") -> None:
    """Print a Rich table showing all detected clips."""
    title = f"Detected Clips{' - ' + video_title if video_title else ''}"
    table = Table(
        title=title,
        title_style="bold cyan",
        border_style="dim cyan",
        show_header=True,
        header_style="bold white",
        expand=False,
        padding=(0, 1),
    )

    table.add_column("#", style="dim", width=3, justify="right")
    table.add_column("Time Range", style="white", width=14)
    table.add_column("Duration", style="dim", width=8)
    table.add_column("Viral Score", width=18)
    table.add_column("Suggested Title", style="cyan", max_width=35)
    table.add_column("Reason", style="dim white", max_width=40)

    for i, clip in enumerate(clips, 1):
        score_style = get_score_style(clip.score)
        score_bar = get_score_bar(clip.score)

        table.add_row(
            str(i),
            f"{clip.start_formatted} -> {clip.end_formatted}",
            clip.duration_formatted,
            Text(score_bar, style=score_style),
            clip.suggested_title,
            clip.reason[:80] + "..." if len(clip.reason) > 80 else clip.reason,
        )

    console.print()
    console.print(table)
    console.print()


def print_summary(
    clips: list[Clip],
    output_paths: list,
    output_dir: str,
    elapsed_seconds: float,
) -> None:
    """Print processing summary panel."""
    total_duration = sum(c.duration for c in clips)
    avg_score = sum(c.score for c in clips) / len(clips) if clips else 0
    elapsed_fmt = f"{int(elapsed_seconds // 60)}m {int(elapsed_seconds % 60)}s"

    lines = [
        f"  [autoclip.success][DONE][/] Generated [bold]{len(output_paths)}[/] clips",
        f"  [autoclip.muted]Total duration:[/] {int(total_duration // 60)}m {int(total_duration % 60)}s",
        f"  [autoclip.muted]Avg viral score:[/] {avg_score:.1f}/10",
        f"  [autoclip.muted]Processing time:[/] {elapsed_fmt}",
        f"  [autoclip.muted]Output directory:[/] [cyan]{output_dir}[/]",
    ]

    panel = Panel(
        "\n".join(lines),
        title="[bold green]AutoClip Complete![/]",
        border_style="green",
        padding=(1, 2),
    )
    console.print()
    console.print(panel)


def make_progress(*args, **kwargs) -> Progress:
    """Create a styled Rich progress bar."""
    return Progress(
        SpinnerColumn(style="cyan"),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(bar_width=30, style="cyan", complete_style="bold cyan"),
        TaskProgressColumn(),
        TimeElapsedColumn(),
        TimeRemainingColumn(),
        console=console,
        **kwargs,
    )


def make_spinner(description: str) -> Progress:
    """Create a simple spinner progress."""
    return Progress(
        SpinnerColumn(style="cyan"),
        TextColumn(f"[cyan]{description}[/]"),
        TimeElapsedColumn(),
        console=console,
        transient=True,
    )
