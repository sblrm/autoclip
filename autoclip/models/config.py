"""Configuration data models for AutoClip."""

from __future__ import annotations

from typing import Any, ClassVar, Literal

from pydantic import BaseModel, Field, model_validator



class WhisperConfig(BaseModel):
    """Whisper speech-to-text configuration."""

    model: str = Field(default="base", description="Whisper model size (tiny/base/small/medium/large)")
    language: str | None = Field(default=None, description="Force language (id/en), None = auto-detect")
    device: str = Field(default="cpu", description="Computing device (cpu/cuda)")
    word_timestamps: bool = Field(default=True, description="Enable word-level timestamps for subtitle")
    fp16: bool = Field(default=False, description="Use FP16 (faster on GPU, disable on CPU)")

    VALID_MODELS: ClassVar[set[str]] = {"tiny", "base", "small", "medium", "large", "large-v2", "large-v3"}


    def model_post_init(self, __context) -> None:
        if self.model not in self.VALID_MODELS:
            raise ValueError(f"Invalid Whisper model: {self.model!r}. Choose from: {self.VALID_MODELS}")


class OllamaConfig(BaseModel):
    """Ollama LLM configuration."""

    model: str = Field(default="llama3", description="Ollama model name")
    host: str = Field(default="http://localhost:11434", description="Ollama server URL")
    timeout: int = Field(default=120, description="Request timeout in seconds")
    temperature: float = Field(default=0.3, description="Generation temperature (lower = more consistent)")
    num_ctx: int = Field(default=8192, description="Context window size")


class OutputConfig(BaseModel):
    """Output format and directory configuration."""

    format: str = Field(default="9:16", description="Aspect ratio (9:16 for vertical)")
    width: int = Field(default=1080, description="Output width in pixels")
    height: int = Field(default=1920, description="Output height in pixels")
    directory: str = Field(default="./autoclip_output", description="Output directory path")
    video_codec: str = Field(default="libx264", description="FFmpeg video codec")
    encoder_mode: Literal["auto", "h264_nvenc", "hevc_nvenc", "libx264"] = Field(
        default="auto",
        description="Acceleration encoder selection mode",
    )
    audio_codec: str = Field(default="aac", description="FFmpeg audio codec")
    crf: int = Field(default=23, description="Video quality (lower = better, 18-28 typical)")
    audio_bitrate: str = Field(default="128k", description="Audio bitrate")

    @model_validator(mode="before")
    @classmethod
    def migrate_legacy_video_codec(cls, value: Any) -> Any:
        if not isinstance(value, dict) or "encoder_mode" in value:
            return value
        migrated = dict(value)
        video_codec = migrated.get("video_codec")
        if video_codec in {"libx264", "h264_nvenc", "hevc_nvenc"}:
            migrated["encoder_mode"] = video_codec
        return migrated


class ClipConfig(BaseModel):
    """Clip detection and extraction settings."""

    min_duration: int = Field(default=30, description="Minimum clip duration in seconds", ge=5)
    max_duration: int = Field(default=90, description="Maximum clip duration in seconds", le=600)
    max_clips: int = Field(default=10, description="Maximum clips to generate", ge=1, le=50)
    min_score: int = Field(default=6, description="Minimum viral score to include (1-10)", ge=1, le=10)
    overlap_tolerance: float = Field(default=5.0, description="Seconds of overlap to merge clips")


class SubtitleConfig(BaseModel):
    """ASS/SSA subtitle styling configuration.

    Defaults are calibrated for 1080x1920 vertical video (TikTok/Reels/Shorts).
    PlayResY is fixed at 1920, so font_size is relative to that height.
    """

    enabled: bool = Field(default=True, description="Generate and burn subtitles")
    font: str = Field(default="Arial", description="Font family")
    font_size: int = Field(default=80, description="Font size (calibrated for 1080x1920; 18 = tiny, 80 = bold karaoke style)")
    primary_color: str = Field(default="&H00FFFFFF", description="Normal text color (AABBGGRR in ASS format)")
    highlight_color: str = Field(default="&H0000FFFF", description="Highlighted word color (yellow)")
    outline_color: str = Field(default="&H00000000", description="Text outline color")
    shadow_color: str = Field(default="&H80000000", description="Drop shadow color")
    bold: bool = Field(default=True, description="Bold text")
    outline_size: int = Field(default=4, description="Outline thickness (increase for readability)")
    shadow_distance: int = Field(default=3, description="Shadow distance")
    position: str = Field(default="bottom", description="Subtitle position: top/middle/bottom")
    margin_v: int = Field(default=120, description="Vertical margin from edge")
    words_per_line: int = Field(default=4, description="Max words per subtitle line (fewer = bigger text, easier to read)")
    uppercase: bool = Field(default=False, description="Convert subtitles to uppercase")


class TrackerConfig(BaseModel):
    """Face-tracking smart crop configuration."""

    enabled: bool = Field(default=False, description="Enable face-tracking smart crop")
    engine: Literal[
        "auto", "mediapipe_cpu", "mediapipe_gpu", "yunet_cpu", "yunet_cuda",
        "scrfd_cpu", "scrfd_cuda", "retinaface_cpu", "retinaface_cuda",
    ] = Field(default="auto", description="Face-tracker acceleration engine")

    @model_validator(mode="before")
    @classmethod
    def migrate_legacy_mediapipe_choice(cls, value: Any) -> Any:
        if not isinstance(value, dict) or "engine" in value or "use_mediapipe" not in value:
            return value
        migrated = dict(value)
        migrated["engine"] = "mediapipe_cpu" if migrated["use_mediapipe"] else "auto"
        return migrated
    ema_alpha: float = Field(
        default=0.04,
        description="EMA smoothing factor (0.02=very smooth/stable, 0.08=more responsive)",
        ge=0.01, le=1.0,
    )
    sample_every_n_frames: int = Field(
        default=15,
        description="Detect faces every N frames (lower=accurate but jittery, higher=smooth)",
        ge=1, le=60,
    )
    use_mediapipe: bool = Field(
        default=True,
        description="Use MediaPipe FaceDetection (falls back to OpenCV Haar if not installed)",
    )
    deadzone_fraction: float = Field(
        default=0.04,
        description=(
            "Fraction of frame size the face must move before the crop reacts. "
            "Prevents micro-jitter from detection noise. 0.04 = 4%% of frame."
        ),
        ge=0.0, le=0.3,
    )


class AutoClipConfig(BaseModel):
    """Root configuration for AutoClip."""

    whisper: WhisperConfig = Field(default_factory=WhisperConfig)
    ollama: OllamaConfig = Field(default_factory=OllamaConfig)
    output: OutputConfig = Field(default_factory=OutputConfig)
    clip: ClipConfig = Field(default_factory=ClipConfig)
    subtitle: SubtitleConfig = Field(default_factory=SubtitleConfig)
    tracker: TrackerConfig = Field(default_factory=TrackerConfig)
