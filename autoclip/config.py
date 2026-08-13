"""AutoClip configuration loader and manager."""

from __future__ import annotations

import os
from pathlib import Path

import yaml

from autoclip.models.config import AutoClipConfig

# Default config directory and file
CONFIG_DIR = Path.home() / ".autoclip"
CONFIG_FILE = CONFIG_DIR / "config.yaml"


def get_default_config_dict() -> dict:
    """Return the default configuration as a plain dict."""
    return {
        "whisper": {
            "model": "base",
            "language": None,
            "device": "cpu",
            "word_timestamps": True,
            "fp16": False,
        },
        "ollama": {
            "model": "llama3",
            "host": "http://localhost:11434",
            "timeout": 120,
            "temperature": 0.3,
            "num_ctx": 8192,
        },
        "output": {
            "format": "9:16",
            "width": 1080,
            "height": 1920,
            "directory": "./autoclip_output",
            "video_codec": "libx264",
            "audio_codec": "aac",
            "crf": 23,
            "audio_bitrate": "128k",
        },
        "clip": {
            "min_duration": 30,
            "max_duration": 90,
            "max_clips": 10,
            "min_score": 6,
            "overlap_tolerance": 5.0,
        },
        "subtitle": {
            "enabled": True,
            "font": "Arial",
            "font_size": 18,
            "primary_color": "&H00FFFFFF",
            "highlight_color": "&H0000FFFF",
            "outline_color": "&H00000000",
            "shadow_color": "&H80000000",
            "bold": True,
            "outline_size": 2,
            "shadow_distance": 2,
            "position": "bottom",
            "margin_v": 60,
            "words_per_line": 5,
            "uppercase": False,
        },
    }


def load_config(config_path: Path | None = None) -> AutoClipConfig:
    """
    Load AutoClip configuration from YAML file.

    Priority (highest to lowest):
    1. Explicitly provided config_path
    2. AUTOCLIP_CONFIG environment variable
    3. ~/.autoclip/config.yaml
    4. Built-in defaults
    """
    path = config_path or _resolve_config_path()

    if path and path.exists():
        with open(path, encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
        # Merge with defaults so partial configs still work
        merged = _deep_merge(get_default_config_dict(), raw)
        return AutoClipConfig(**merged)

    return AutoClipConfig()


def save_config(config: AutoClipConfig, config_path: Path | None = None) -> Path:
    """Save configuration to YAML file."""
    path = config_path or CONFIG_FILE
    path.parent.mkdir(parents=True, exist_ok=True)

    data = config.model_dump()
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

    return path


def init_config(force: bool = False) -> tuple[Path, bool]:
    """
    Initialize the default config file.

    Returns:
        (path, created): path to config file, and whether it was newly created
    """
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    if CONFIG_FILE.exists() and not force:
        return CONFIG_FILE, False

    defaults = get_default_config_dict()
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        # Write with helpful comments
        f.write(_config_with_comments(defaults))

    return CONFIG_FILE, True


def _resolve_config_path() -> Path | None:
    """Resolve config file path from env var or default location."""
    env_path = os.environ.get("AUTOCLIP_CONFIG")
    if env_path:
        return Path(env_path)
    if CONFIG_FILE.exists():
        return CONFIG_FILE
    return None


def _deep_merge(base: dict, override: dict) -> dict:
    """Deep merge override into base dict, returning new dict."""
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _config_with_comments(defaults: dict) -> str:
    """Generate YAML config string with helpful comments."""
    return """\
# AutoClip Configuration
# Documentation: https://github.com/your-org/autoclip
# Edit this file to set your defaults. CLI flags always override these values.

# ─── Whisper (Speech-to-Text) ────────────────────────────────────────────────
whisper:
  # Model size: tiny | base | small | medium | large | large-v2 | large-v3
  # Larger = more accurate but slower. Recommended: base (fast) or small (balanced)
  model: base

  # Language: null = auto-detect, "id" = Indonesian, "en" = English
  language: null

  # Device: cpu | cuda (GPU). Use cuda if you have an NVIDIA GPU for 10x speedup
  device: cpu

  # Word timestamps: required for karaoke-style subtitle highlight
  word_timestamps: true

  # FP16: faster on GPU but may cause issues on CPU. Set true only if device=cuda
  fp16: false

# ─── Ollama (Local LLM for Viral Moment Analysis) ────────────────────────────
ollama:
  # Model to use. Run `ollama pull llama3` first.
  # Options: llama3, mistral, gemma, phi3, llama2
  model: llama3

  # Ollama server URL (default if running locally)
  host: http://localhost:11434

  # Request timeout in seconds
  timeout: 120

  # Temperature: lower = more consistent output, higher = more creative
  temperature: 0.3

  # Context window size
  num_ctx: 8192

# ─── Output Settings ─────────────────────────────────────────────────────────
output:
  # Aspect ratio (currently only 9:16 supported in v0.1.0)
  format: "9:16"
  width: 1080
  height: 1920

  # Output directory (relative to CWD or absolute path)
  directory: ./autoclip_output

  video_codec: libx264
  audio_codec: aac

  # CRF: quality factor (18=high quality, 23=good, 28=smaller file)
  crf: 23
  audio_bitrate: "128k"

# ─── Clip Detection ──────────────────────────────────────────────────────────
clip:
  # Duration range for each clip (in seconds)
  min_duration: 30
  max_duration: 90

  # Maximum number of clips to generate per video
  max_clips: 10

  # Minimum viral score (1-10) to include a clip. Lower = more clips
  min_score: 6

  # Seconds of overlap between clips before merging them
  overlap_tolerance: 5.0

# ─── Subtitle Settings ───────────────────────────────────────────────────────
subtitle:
  # Set false to disable subtitle generation
  enabled: true

  font: Arial
  font_size: 18

  # Colors in ASS format (&HAABBGGRR)
  primary_color: "&H00FFFFFF"   # White text
  highlight_color: "&H0000FFFF"  # Yellow for active word
  outline_color: "&H00000000"   # Black outline
  shadow_color: "&H80000000"    # Semi-transparent shadow

  bold: true
  outline_size: 2
  shadow_distance: 2

  # Position: top | middle | bottom
  position: bottom
  margin_v: 60

  # Words to show per subtitle line
  words_per_line: 5

  # Convert subtitles to uppercase (popular TikTok style)
  uppercase: false
"""
