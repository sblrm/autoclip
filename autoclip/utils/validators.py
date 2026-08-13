"""URL validation and dependency checking."""

from __future__ import annotations

import re
import shutil
import urllib.parse


# Supported platform URL patterns
_SUPPORTED_PATTERNS = [
    r"(https?://)?(www\.)?youtube\.com/watch\?v=",
    r"(https?://)?youtu\.be/",
    r"(https?://)?(www\.)?youtube\.com/shorts/",
    r"(https?://)?(www\.)?tiktok\.com/",
    r"(https?://)?(www\.)?instagram\.com/(reel|p)/",
    r"(https?://)?(www\.)?twitter\.com/.+/status/",
    r"(https?://)?(www\.)?x\.com/.+/status/",
    r"(https?://)?(www\.)?twitch\.tv/",
    r"(https?://)?(www\.)?facebook\.com/",
    r"(https?://)?(www\.)?vimeo\.com/",
    r"(https?://)?(www\.)?dailymotion\.com/",
    r"(https?://)?(www\.)?reddit\.com/",
    r"(https?://)?(www\.)?bilibili\.com/",
]

_SUPPORTED_REGEX = re.compile("|".join(_SUPPORTED_PATTERNS), re.IGNORECASE)


def is_valid_url(url: str) -> bool:
    """Check if a string is a valid URL (basic check)."""
    try:
        result = urllib.parse.urlparse(url)
        return all([result.scheme in ("http", "https"), result.netloc])
    except ValueError:
        return False


def is_supported_platform(url: str) -> bool:
    """Check if URL is from a supported platform."""
    return bool(_SUPPORTED_REGEX.search(url))


def get_platform(url: str) -> str:
    """Identify the platform from a URL (returns lowercase key)."""
    url_lower = url.lower()
    platforms = {
        "youtube": ["youtube.com", "youtu.be"],
        "tiktok": ["tiktok.com"],
        "instagram": ["instagram.com"],
        "twitter": ["twitter.com", "x.com"],
        "twitch": ["twitch.tv"],
        "facebook": ["facebook.com"],
        "vimeo": ["vimeo.com"],
        "dailymotion": ["dailymotion.com"],
        "reddit": ["reddit.com"],
        "bilibili": ["bilibili.com"],
    }
    for platform, domains in platforms.items():
        if any(domain in url_lower for domain in domains):
            return platform
    return "unknown"


def detect_platform(url: str) -> str:
    """Identify the platform from a URL (returns human-readable display name)."""
    _display = {
        "youtube": "YouTube",
        "tiktok": "TikTok",
        "instagram": "Instagram",
        "twitter": "X (Twitter)",
        "twitch": "Twitch",
        "facebook": "Facebook",
        "vimeo": "Vimeo",
        "dailymotion": "Dailymotion",
        "reddit": "Reddit",
        "bilibili": "Bilibili",
    }
    key = get_platform(url)
    return _display.get(key, "Unknown")



class DependencyStatus:
    """Holds status of all AutoClip external dependencies."""

    def __init__(self):
        self.ffmpeg_available: bool = False
        self.ffmpeg_version: str = ""
        self.ffprobe_available: bool = False
        self.ollama_available: bool = False
        self.ollama_models: list[str] = []
        self.whisper_available: bool = False
        self.errors: list[str] = []

    @property
    def all_ok(self) -> bool:
        return (
            self.ffmpeg_available
            and self.ffprobe_available
            and self.ollama_available
            and self.whisper_available
        )

    @property
    def minimum_ok(self) -> bool:
        """Minimum requirements: FFmpeg + Whisper (can run without Ollama with heuristics)."""
        return self.ffmpeg_available and self.ffprobe_available and self.whisper_available


def check_dependencies() -> DependencyStatus:
    """Check all required AutoClip dependencies."""
    status = DependencyStatus()

    # Check FFmpeg
    from autoclip.utils.ffmpeg import check_ffmpeg, check_ffprobe
    status.ffmpeg_available, status.ffmpeg_version = check_ffmpeg()
    status.ffprobe_available = check_ffprobe()
    if not status.ffmpeg_available:
        status.errors.append("FFmpeg not found. Install from: https://ffmpeg.org/download.html")
    if not status.ffprobe_available:
        status.errors.append("FFprobe not found (usually bundled with FFmpeg)")

    # Check Whisper
    try:
        import whisper  # noqa: F401
        status.whisper_available = True
    except ImportError:
        status.whisper_available = False
        status.errors.append("openai-whisper not installed. Run: pip install openai-whisper")

    # Check Ollama
    try:
        import ollama  # noqa: F401
        # Try to actually connect to Ollama server
        client = ollama.Client()
        models_response = client.list()
        status.ollama_available = True
        status.ollama_models = [m["name"] for m in models_response.get("models", [])]
    except ImportError:
        status.ollama_available = False
        status.errors.append("ollama Python package not installed. Run: pip install ollama")
    except Exception as e:
        status.ollama_available = False
        status.errors.append(
            f"Ollama server not running: {e}. "
            "Install from: https://ollama.ai and run: ollama serve"
        )

    return status


def check_yt_dlp() -> tuple[bool, str]:
    """Check yt-dlp availability."""
    ytdlp_path = shutil.which("yt-dlp")
    if ytdlp_path:
        try:
            import subprocess
            result = subprocess.run(
                ["yt-dlp", "--version"], capture_output=True, text=True, timeout=10
            )
            return True, result.stdout.strip()
        except Exception:
            pass

    # Also check as Python package
    try:
        import yt_dlp  # noqa: F401
        return True, "installed"
    except ImportError:
        return False, ""
