"""Whisper-based speech-to-text transcriber."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from autoclip.models.config import WhisperConfig
from autoclip.models.transcript import Transcript
from autoclip.utils.ffmpeg import extract_audio


def transcribe(
    video_path: Path,
    config: WhisperConfig,
    cache_dir: Path | None = None,
    progress_callback=None,
) -> Transcript:
    """
    Transcribe the audio from a video file using OpenAI Whisper.

    Args:
        video_path: Path to the video (or audio) file
        config: Whisper configuration (model, language, device)
        cache_dir: Optional directory to cache transcription results
        progress_callback: Optional callable() for progress updates

    Returns:
        Transcript with segments and word-level timestamps

    Raises:
        FileNotFoundError: If video file doesn't exist
        RuntimeError: If transcription fails
    """
    if not video_path.exists():
        raise FileNotFoundError(f"Video file not found: {video_path}")

    # Check cache
    if cache_dir:
        cached = _load_cached_transcript(video_path, config, cache_dir)
        if cached:
            return cached

    # Extract audio to WAV (Whisper needs audio)
    audio_path = video_path.with_suffix(".wav")
    if not audio_path.exists():
        audio_path = _get_temp_audio_path(video_path)
        extract_audio(video_path, audio_path)

    # Get audio duration for Transcript metadata
    audio_duration = _get_audio_duration(audio_path)

    # Load model and transcribe
    try:
        import whisper
    except ImportError:
        raise RuntimeError(
            "openai-whisper is not installed. Run: pip install openai-whisper"
        )

    if progress_callback:
        progress_callback("Loading Whisper model...")

    model = whisper.load_model(config.model, device=config.device)

    if progress_callback:
        progress_callback("Transcribing audio...")

    transcribe_opts: dict = {
        "word_timestamps": config.word_timestamps,
        "fp16": config.fp16 and config.device == "cuda",
        "verbose": False,
        "condition_on_previous_text": True,
        "temperature": 0,  # Greedy decoding for more consistent output
    }

    # Only set language if specified; otherwise auto-detect
    if config.language:
        transcribe_opts["language"] = config.language

    result = model.transcribe(str(audio_path), **transcribe_opts)

    # Clean up temp audio if we created it
    if audio_path != video_path.with_suffix(".wav") and audio_path.exists():
        try:
            audio_path.unlink()
        except OSError:
            pass

    transcript = Transcript.from_whisper_result(result, audio_duration=audio_duration)

    # Cache the result
    if cache_dir:
        _save_cached_transcript(video_path, config, cache_dir, transcript)

    return transcript


def _get_temp_audio_path(video_path: Path) -> Path:
    """Get a temp audio path in the same directory as the video."""
    return video_path.parent / f"_autoclip_{video_path.stem}_audio.wav"


def _get_audio_duration(audio_path: Path) -> float:
    """Get audio duration in seconds via FFprobe."""
    try:
        from autoclip.utils.ffmpeg import get_video_info
        info = get_video_info(audio_path)
        return info.duration
    except Exception:
        return 0.0


def _cache_key(video_path: Path, config: WhisperConfig) -> str:
    """Generate a cache key based on file content hash + config."""
    # Use file size + mtime for quick cache key (avoid reading whole file)
    stat = video_path.stat()
    key_source = f"{video_path}:{stat.st_size}:{stat.st_mtime}:{config.model}:{config.language}"
    return hashlib.md5(key_source.encode()).hexdigest()


def _load_cached_transcript(
    video_path: Path, config: WhisperConfig, cache_dir: Path
) -> Transcript | None:
    """Load a cached transcript if available and valid."""
    key = _cache_key(video_path, config)
    cache_file = cache_dir / f"transcript_{key}.json"

    if cache_file.exists():
        try:
            with open(cache_file, encoding="utf-8") as f:
                data = json.load(f)
            return Transcript(**data)
        except Exception:
            # Invalid cache — ignore and re-transcribe
            try:
                cache_file.unlink()
            except OSError:
                pass

    return None


def _save_cached_transcript(
    video_path: Path, config: WhisperConfig, cache_dir: Path, transcript: Transcript
) -> None:
    """Save transcript to cache."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    key = _cache_key(video_path, config)
    cache_file = cache_dir / f"transcript_{key}.json"

    try:
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(transcript.model_dump(), f, ensure_ascii=False, indent=2)
    except OSError:
        pass  # Cache failure is non-fatal
