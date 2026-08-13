"""Video downloader using yt-dlp."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import yt_dlp

from autoclip.utils.validators import is_valid_url


@dataclass
class VideoMetadata:
    """Metadata extracted from a downloaded video."""

    title: str
    uploader: str
    duration: float  # seconds
    platform: str
    url: str
    description: str = ""
    upload_date: str = ""
    view_count: int = 0
    like_count: int = 0
    tags: list[str] = field(default_factory=list)


@dataclass
class DownloadResult:
    """Result of a video download operation."""

    video_path: Path
    audio_path: Path | None
    metadata: VideoMetadata
    was_cached: bool = False


def _sanitize_filename(title: str, max_len: int = 80) -> str:
    """Convert video title to a safe filesystem name."""
    safe = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", title)
    safe = re.sub(r"\s+", "_", safe.strip())
    safe = safe[:max_len].rstrip("_. ")
    return safe or "video"


def download_video(
    url: str,
    output_dir: Path,
    progress_callback=None,
    max_height: int = 1080,
) -> DownloadResult:
    """
    Download a video from a supported URL using yt-dlp.

    Args:
        url: Video URL (YouTube, TikTok, Instagram, etc.)
        output_dir: Directory to save the downloaded video
        progress_callback: Optional callable(percent: float, speed: str, eta: str)
        max_height: Maximum vertical resolution (default 1080p)

    Returns:
        DownloadResult with paths and metadata

    Raises:
        ValueError: If URL is invalid
        RuntimeError: If download fails
    """
    if not is_valid_url(url):
        raise ValueError(f"Invalid URL: {url!r}")

    output_dir.mkdir(parents=True, exist_ok=True)

    # Probe metadata first (no download)
    metadata = _fetch_metadata(url)
    safe_title = _sanitize_filename(metadata.title)
    video_filename = f"{safe_title}.%(ext)s"
    video_output_template = str(output_dir / video_filename)

    # Check if already downloaded
    existing = list(output_dir.glob(f"{safe_title}.*"))
    video_exts = {".mp4", ".mkv", ".webm", ".mov"}
    cached_video = next((p for p in existing if p.suffix in video_exts), None)
    if cached_video and cached_video.stat().st_size > 0:
        return DownloadResult(
            video_path=cached_video,
            audio_path=None,
            metadata=metadata,
            was_cached=True,
        )

    # Build yt-dlp options
    ydl_opts = {
        "outtmpl": video_output_template,
        "format": f"bestvideo[height<={max_height}][ext=mp4]+bestaudio[ext=m4a]/best[height<={max_height}][ext=mp4]/best",
        "merge_output_format": "mp4",
        "writesubtitles": False,
        "quiet": True,
        "no_warnings": True,
        "progress_hooks": [_make_progress_hook(progress_callback)] if progress_callback else [],
        "postprocessors": [{
            "key": "FFmpegVideoConvertor",
            "preferedformat": "mp4",
        }],
        "retries": 3,
        "fragment_retries": 3,
        "http_chunk_size": 10485760,  # 10MB chunks
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
    except yt_dlp.utils.DownloadError as e:
        raise RuntimeError(f"Download failed: {e}") from e

    # Find downloaded file
    downloaded = list(output_dir.glob(f"{safe_title}.*"))
    video_file = next((p for p in downloaded if p.suffix in video_exts), None)

    if not video_file or not video_file.exists():
        raise RuntimeError(f"Download appeared to succeed but file not found in {output_dir}")

    return DownloadResult(
        video_path=video_file,
        audio_path=None,
        metadata=metadata,
        was_cached=False,
    )


def _fetch_metadata(url: str) -> VideoMetadata:
    """Fetch video metadata without downloading."""
    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": False,
        "skip_download": True,
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False) or {}
    except Exception as e:
        # Return minimal metadata on failure
        return VideoMetadata(
            title="Unknown Video",
            uploader="Unknown",
            duration=0.0,
            platform="unknown",
            url=url,
        )

    return VideoMetadata(
        title=info.get("title", "Unknown Video"),
        uploader=info.get("uploader", "Unknown"),
        duration=float(info.get("duration", 0)),
        platform=info.get("extractor_key", "unknown").lower(),
        url=url,
        description=info.get("description", "")[:500],  # truncate
        upload_date=info.get("upload_date", ""),
        view_count=info.get("view_count") or 0,
        like_count=info.get("like_count") or 0,
        tags=info.get("tags", []) or [],
    )


def _make_progress_hook(callback):
    """Create a yt-dlp progress hook that calls our callback."""
    def hook(d: dict) -> None:
        if d.get("status") == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 1
            downloaded = d.get("downloaded_bytes", 0)
            percent = (downloaded / total) * 100 if total else 0
            speed = d.get("speed_str", "")
            eta = d.get("eta_str", "")
            callback(percent, speed, eta)
        elif d.get("status") == "finished":
            callback(100.0, "", "")
    return hook
