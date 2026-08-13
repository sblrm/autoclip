"""ASS/SSA subtitle generator with karaoke-style word highlighting."""

from __future__ import annotations

import math
from pathlib import Path

from autoclip.models.clip import Clip
from autoclip.models.config import SubtitleConfig
from autoclip.models.transcript import Segment, Transcript, Word


# ASS color format: &HAABBGGRR (alpha, blue, green, red)
_DEFAULT_TRANSPARENT = "&H00000000"
_KARAOKE_TIMING_EXTRA_MS = 50  # Extra buffer for karaoke timing


def generate_subtitles(
    transcript: Transcript,
    clip: Clip,
    output_path: Path,
    config: SubtitleConfig,
) -> Path:
    """
    Generate an ASS subtitle file for a clip with word-level karaoke highlighting.

    Args:
        transcript: Full video transcript (will filter to clip's time range)
        clip: The clip to generate subtitles for
        output_path: Path to write the .ass file
        config: Subtitle styling configuration

    Returns:
        Path to the generated ASS file
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Get segments within clip's time range
    segments = transcript.get_segments_in_range(clip.start_time, clip.end_time)

    # Adjust timestamps to be relative to clip start
    adjusted_segments = _adjust_timestamps(segments, clip.start_time, clip.end_time)

    # Build ASS content
    ass_content = _build_ass_file(adjusted_segments, config, clip.duration)

    with open(output_path, "w", encoding="utf-8-sig") as f:  # utf-8-sig for BOM (FFmpeg compatibility)
        f.write(ass_content)

    return output_path


def _adjust_timestamps(
    segments: list[Segment], clip_start: float, clip_end: float
) -> list[Segment]:
    """Adjust all segment and word timestamps relative to clip start time."""
    adjusted = []
    for seg in segments:
        # Clamp to clip bounds
        seg_start = max(0.0, seg.start - clip_start)
        seg_end = min(clip_end - clip_start, seg.end - clip_start)

        if seg_end <= 0 or seg_start >= (clip_end - clip_start):
            continue

        adjusted_words = []
        for word in seg.words:
            w_start = max(0.0, word.start - clip_start)
            w_end = min(clip_end - clip_start, word.end - clip_start)
            if w_end > 0:
                adjusted_words.append(Word(
                    text=word.text,
                    start=round(w_start, 3),
                    end=round(w_end, 3),
                    probability=word.probability,
                ))

        adjusted.append(Segment(
            id=seg.id,
            text=seg.text,
            start=round(seg_start, 3),
            end=round(seg_end, 3),
            words=adjusted_words,
            avg_logprob=seg.avg_logprob,
            no_speech_prob=seg.no_speech_prob,
        ))

    return adjusted


def _build_ass_file(
    segments: list[Segment],
    config: SubtitleConfig,
    total_duration: float,
) -> str:
    """Build the complete ASS file content."""
    script_info = _build_script_info(config)
    styles = _build_styles(config)
    events = _build_events(segments, config)

    return "\n".join([script_info, styles, events])


def _build_script_info(config: SubtitleConfig) -> str:
    """Build the [Script Info] section."""
    return (
        "[Script Info]\n"
        "ScriptType: v4.00+\n"
        "PlayResX: 1080\n"
        "PlayResY: 1920\n"
        "ScaledBorderAndShadow: yes\n"
        "Collisions: Normal\n"
        f"Title: AutoClip Subtitles\n"
        "WrapStyle: 0\n"
    )


def _build_styles(config: SubtitleConfig) -> str:
    """Build the [V4+ Styles] section with normal and highlight styles."""
    # Alignment: 2 = bottom-center, 8 = top-center, 5 = middle-center
    alignment_map = {"bottom": 2, "top": 8, "middle": 5}
    alignment = alignment_map.get(config.position, 2)

    bold_flag = "-1" if config.bold else "0"

    # Normal style
    normal_style = (
        f"Style: Default,{config.font},{config.font_size},"
        f"{config.primary_color},{config.primary_color},"
        f"{config.outline_color},{config.shadow_color},"
        f"{bold_flag},0,0,0,"          # Bold, Italic, Underline, Strikeout
        f"100,100,0,0,"                  # ScaleX, ScaleY, Spacing, Angle
        f"1,{config.outline_size},{config.shadow_distance},"   # BorderStyle, Outline, Shadow
        f"{alignment},10,10,{config.margin_v},1"  # Alignment, MarginL, MarginR, MarginV, Encoding
    )

    # Highlight style (for active word)
    highlight_style = (
        f"Style: Highlight,{config.font},{config.font_size},"
        f"{config.highlight_color},{config.highlight_color},"
        f"{config.outline_color},{config.shadow_color},"
        f"{bold_flag},0,0,0,"
        f"100,100,0,0,"
        f"1,{config.outline_size},{config.shadow_distance},"
        f"{alignment},10,10,{config.margin_v},1"
    )

    return (
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
        "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
        "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding\n"
        f"{normal_style}\n"
        f"{highlight_style}\n"
    )


def _build_events(segments: list[Segment], config: SubtitleConfig) -> str:
    """Build the [Events] section with dialogue lines."""
    lines = [
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]

    for seg in segments:
        if not seg.is_speech:
            continue

        text = seg.text.strip()
        if not text:
            continue

        if config.uppercase:
            text = text.upper()

        if seg.words and len(seg.words) > 1:
            # Build karaoke-style word-by-word highlighting
            dialogue_lines = _build_karaoke_lines(seg, config)
        else:
            # Simple subtitle without word highlighting
            dialogue_lines = [_build_simple_line(seg.start, seg.end, text)]

        lines.extend(dialogue_lines)

    return "\n".join(lines)


def _build_karaoke_lines(seg: Segment, config: SubtitleConfig) -> list[str]:
    """Build karaoke-style dialogue lines with per-word highlighting."""
    lines = []
    words = [w for w in seg.words if w.text.strip()]
    if not words:
        return lines

    # Group words into lines of max config.words_per_line
    word_groups = _chunk_words(words, config.words_per_line)

    for group in word_groups:
        if not group:
            continue

        group_start = group[0].start
        group_end = group[-1].end

        # For each word in the group, emit one dialogue line showing the group
        # with that specific word highlighted
        for active_idx, active_word in enumerate(group):
            # Show all words: before active = muted, active = highlighted, after = muted
            text_parts = []
            for j, word in enumerate(group):
                w_text = word.text.strip()
                if config.uppercase:
                    w_text = w_text.upper()

                if j == active_idx:
                    text_parts.append(f"{{\\rHighlight}}{w_text}{{\\rDefault}}")
                else:
                    text_parts.append(w_text)

            combined_text = " ".join(text_parts)

            # Show this version during the active word's time span
            word_start = active_word.start
            word_end = active_word.end

            if word_start < word_end:
                line = (
                    f"Dialogue: 0,{_ts(word_start)},{_ts(word_end)},"
                    f"Default,,0,0,0,,{combined_text}"
                )
                lines.append(line)

    return lines


def _build_simple_line(start: float, end: float, text: str) -> str:
    """Build a simple subtitle dialogue line."""
    return f"Dialogue: 0,{_ts(start)},{_ts(end)},Default,,0,0,0,,{text}"


def _chunk_words(words: list[Word], chunk_size: int) -> list[list[Word]]:
    """Split words into groups of chunk_size."""
    return [words[i:i + chunk_size] for i in range(0, len(words), chunk_size)]


def _ts(seconds: float) -> str:
    """Convert seconds to ASS timestamp format H:MM:SS.cc"""
    total_cs = int(seconds * 100)  # centiseconds
    h = total_cs // 360000
    m = (total_cs % 360000) // 6000
    s = (total_cs % 6000) // 100
    cs = total_cs % 100
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"
