"""Viral moment analyzer using Ollama LLM with heuristic fallback."""

from __future__ import annotations

import json
import re

from autoclip.models.clip import Clip
from autoclip.models.config import ClipConfig, OllamaConfig
from autoclip.models.transcript import Transcript


def analyze_transcript(
    transcript: Transcript,
    ollama_config: OllamaConfig,
    clip_config: ClipConfig,
    progress_callback=None,
) -> list[Clip]:
    """
    Analyze a transcript to find viral moment candidates using Ollama LLM.

    Falls back to heuristic analysis if Ollama is unavailable.

    Args:
        transcript: Full video transcript with timestamps
        ollama_config: Ollama LLM configuration
        clip_config: Clip detection settings (duration, score thresholds)
        progress_callback: Optional callable(message: str) for status updates

    Returns:
        List of Clip objects sorted by viral score (descending)
    """
    if progress_callback:
        progress_callback("Preparing transcript for analysis...")

    # Check if Ollama is accessible
    ollama_available = _check_ollama(ollama_config)

    if ollama_available:
        if progress_callback:
            progress_callback(f"Analyzing with Ollama ({ollama_config.model})...")
        clips = _analyze_with_llm(transcript, ollama_config, clip_config)
    else:
        if progress_callback:
            progress_callback("Ollama unavailable, using heuristic analysis...")
        clips = _analyze_heuristic(transcript, clip_config)

    # Post-process: validate, merge overlapping, sort
    clips = _validate_clips(clips, transcript.audio_duration, clip_config)
    clips = _merge_overlapping(clips, clip_config.overlap_tolerance)
    clips.sort(key=lambda c: c.score, reverse=True)

    # Limit to max_clips
    clips = clips[: clip_config.max_clips]

    return clips


def _check_ollama(config: OllamaConfig) -> bool:
    """Check if Ollama server is running and model is available."""
    try:
        import ollama
        client = ollama.Client(host=config.host)
        models = client.list()
        available_names = [m["name"] for m in models.get("models", [])]
        # Check if configured model (or its base) is available
        model_base = config.model.split(":")[0]
        return any(model_base in name for name in available_names)
    except Exception:
        return False


def _analyze_with_llm(
    transcript: Transcript,
    ollama_config: OllamaConfig,
    clip_config: ClipConfig,
) -> list[Clip]:
    """Run LLM analysis via Ollama."""
    import ollama

    # Format transcript for LLM
    transcript_text = transcript.to_formatted_string()
    duration_fmt = _format_duration(transcript.audio_duration)

    # Select prompt language based on transcript language
    if transcript.language.startswith("id"):
        from autoclip.prompts.analyze_id import format_prompt_id
        prompt = format_prompt_id(
            transcript=transcript_text,
            total_duration_formatted=duration_fmt,
            min_duration=clip_config.min_duration,
            max_duration=clip_config.max_duration,
            max_clips=clip_config.max_clips,
            min_score=clip_config.min_score,
        )
        lang = "id"
    else:
        from autoclip.prompts.analyze_en import format_prompt_en
        prompt = format_prompt_en(
            transcript=transcript_text,
            total_duration_formatted=duration_fmt,
            min_duration=clip_config.min_duration,
            max_duration=clip_config.max_duration,
            max_clips=clip_config.max_clips,
            min_score=clip_config.min_score,
        )
        lang = "en"

    # Call Ollama
    client = ollama.Client(host=ollama_config.host)
    response = client.generate(
        model=ollama_config.model,
        prompt=prompt,
        options={
            "temperature": ollama_config.temperature,
            "num_ctx": ollama_config.num_ctx,
        },
    )

    raw_response = response.get("response", "")
    return _parse_llm_response(raw_response, lang)


def _parse_llm_response(response: str, default_lang: str = "id") -> list[Clip]:
    """
    Parse the LLM JSON response into Clip objects.

    Handles common LLM formatting issues (markdown code blocks, trailing commas).
    """
    # Strip markdown code blocks if present
    response = response.strip()
    response = re.sub(r"^```(?:json)?\s*", "", response)
    response = re.sub(r"\s*```$", "", response)

    # Find JSON array in response
    json_match = re.search(r"\[.*?\]", response, re.DOTALL)
    if not json_match:
        raise ValueError(f"No JSON array found in LLM response: {response[:200]}")

    json_str = json_match.group(0)

    # Fix trailing commas (common LLM mistake)
    json_str = re.sub(r",\s*([}\]])", r"\1", json_str)

    try:
        data = json.loads(json_str)
    except json.JSONDecodeError as e:
        raise ValueError(f"Failed to parse LLM JSON response: {e}\nResponse: {json_str[:300]}") from e

    clips = []
    for item in data:
        if not isinstance(item, dict):
            continue
        try:
            clip = Clip(
                start_time=float(item.get("start_time", 0)),
                end_time=float(item.get("end_time", 0)),
                score=int(item.get("score", 5)),
                reason=str(item.get("reason", "AI-detected viral moment")),
                suggested_title=str(item.get("suggested_title", "Untitled Clip")),
                language=str(item.get("language", default_lang)),
            )
            clips.append(clip)
        except Exception:
            continue  # Skip invalid entries

    return clips


def _analyze_heuristic(transcript: Transcript, clip_config: ClipConfig) -> list[Clip]:
    """
    Fallback heuristic analysis when Ollama is unavailable.

    Strategy:
    - Split transcript into windows of target duration
    - Score each window based on:
      * Speech density (words per second)
      * Sentence count
      * Presence of high-energy keywords
      * Low silence/pause ratio
    """
    VIRAL_KEYWORDS_ID = {
        "rahasia", "tips", "cara", "jangan", "harus", "ternyata", "shock",
        "viral", "gila", "wow", "luar biasa", "tidak percaya", "fakta",
        "penting", "kesalahan", "belajar", "sukses", "gagal", "uang",
        "jutaan", "gratis", "mudah", "cepat", "berhasil",
    }
    VIRAL_KEYWORDS_EN = {
        "secret", "tips", "how to", "never", "always", "shocking", "viral",
        "incredible", "amazing", "unbelievable", "fact", "important", "mistake",
        "learn", "success", "fail", "money", "million", "free", "easy",
        "fast", "hack", "truth", "revealed", "why",
    }
    keywords = VIRAL_KEYWORDS_ID if transcript.language.startswith("id") else VIRAL_KEYWORDS_EN

    clips = []
    segments = [s for s in transcript.segments if s.is_speech]
    if not segments:
        return clips

    # Slide a window across segments
    window = clip_config.min_duration
    step = window // 2

    start = segments[0].start
    end_limit = segments[-1].end

    while start + window <= end_limit:
        end = start + window
        window_segs = transcript.get_segments_in_range(start, end)

        if not window_segs:
            start += step
            continue

        # Score based on keywords and density
        text = " ".join(s.text for s in window_segs).lower()
        words = text.split()
        word_count = len(words)
        density = word_count / window if window > 0 else 0

        keyword_hits = sum(1 for kw in keywords if kw in text)

        # Raw score (0-10)
        raw_score = min(10, int(
            (keyword_hits * 2)
            + (density * 1.5)
            + (len(window_segs) * 0.3)
        ))
        score = max(1, raw_score)

        if score >= clip_config.min_score:
            lang = "id" if transcript.language.startswith("id") else "en"
            clip = Clip(
                start_time=round(start, 2),
                end_time=round(end, 2),
                score=score,
                reason="Heuristic: high keyword density and speech activity" if lang == "en"
                       else "Heuristik: kepadatan kata kunci tinggi dan aktivitas bicara",
                suggested_title=f"Clip {int(start // 60):02d}:{int(start % 60):02d}",
                language=lang,
            )
            clips.append(clip)

        start += step

    return clips


def _validate_clips(
    clips: list[Clip], video_duration: float, config: ClipConfig
) -> list[Clip]:
    """Validate and clean up clip list."""
    valid = []
    for clip in clips:
        # Clamp to video bounds
        start = max(0.0, clip.start_time)
        end = min(video_duration, clip.end_time) if video_duration > 0 else clip.end_time
        duration = end - start

        # Skip if out of duration range
        if duration < config.min_duration or duration > config.max_duration:
            continue
        if start >= end:
            continue

        valid.append(Clip(
            start_time=round(start, 2),
            end_time=round(end, 2),
            score=clip.score,
            reason=clip.reason,
            suggested_title=clip.suggested_title,
            language=clip.language,
        ))

    return valid


def _merge_overlapping(clips: list[Clip], tolerance: float = 5.0) -> list[Clip]:
    """Merge clips that overlap within tolerance seconds."""
    if len(clips) <= 1:
        return clips

    sorted_clips = sorted(clips, key=lambda c: c.start_time)
    merged = [sorted_clips[0]]

    for clip in sorted_clips[1:]:
        if merged[-1].overlaps(clip, tolerance):
            merged[-1] = merged[-1].merge(clip)
        else:
            merged.append(clip)

    return merged


def _format_duration(seconds: float) -> str:
    """Format seconds as MM:SS or HH:MM:SS."""
    total = int(seconds)
    h = total // 3600
    m = (total % 3600) // 60
    s = total % 60
    if h > 0:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"
