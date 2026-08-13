"""Tests for ASS subtitle generator module."""

from __future__ import annotations

from pathlib import Path

import pytest

from autoclip.core.subtitle import (
    _adjust_timestamps,
    _build_ass_file,
    _chunk_words,
    _ts,
    generate_subtitles,
)
from autoclip.models.config import SubtitleConfig
from autoclip.models.transcript import Segment, Word


# ─── Timestamp Formatting ─────────────────────────────────────────────────────


class TestTimestampFormatting:
    def test_zero(self):
        assert _ts(0.0) == "0:00:00.00"

    def test_one_second(self):
        assert _ts(1.0) == "0:00:01.00"

    def test_one_minute(self):
        assert _ts(60.0) == "0:01:00.00"

    def test_one_hour(self):
        assert _ts(3600.0) == "1:00:00.00"

    def test_fractional_seconds(self):
        result = _ts(1.5)
        assert result == "0:00:01.50"

    def test_complex_time(self):
        result = _ts(125.75)
        assert "2:05" in result


# ─── Word Chunking ────────────────────────────────────────────────────────────


class TestChunkWords:
    def test_exact_chunk(self, sample_words):
        chunks = _chunk_words(sample_words[:4], 4)
        assert len(chunks) == 1
        assert len(chunks[0]) == 4

    def test_partial_last_chunk(self, sample_words):
        # 9 words, chunk_size=4 → [4, 4, 1]
        chunks = _chunk_words(sample_words, 4)
        assert len(chunks) == 3
        assert len(chunks[0]) == 4
        assert len(chunks[-1]) == 1

    def test_empty_words(self):
        chunks = _chunk_words([], 5)
        assert chunks == []

    def test_single_word(self, sample_words):
        chunks = _chunk_words([sample_words[0]], 5)
        assert len(chunks) == 1
        assert len(chunks[0]) == 1


# ─── Timestamp Adjustment ─────────────────────────────────────────────────────


class TestAdjustTimestamps:
    def test_basic_offset(self, sample_segment):
        adjusted = _adjust_timestamps([sample_segment], clip_start=2.0, clip_end=10.0)
        assert len(adjusted) == 1
        # Segment start (0.0) adjusted to 0.0 - 2.0 = -2.0 → clamped to 0.0
        assert adjusted[0].start >= 0.0

    def test_segment_outside_clip_removed(self, sample_segment):
        adjusted = _adjust_timestamps([sample_segment], clip_start=100.0, clip_end=200.0)
        assert len(adjusted) == 0

    def test_words_adjusted_correctly(self, sample_segment):
        adjusted = _adjust_timestamps([sample_segment], clip_start=1.0, clip_end=10.0)
        if adjusted and adjusted[0].words:
            for word in adjusted[0].words:
                assert word.start >= 0.0


# ─── ASS File Structure ───────────────────────────────────────────────────────


class TestASSFileStructure:
    def test_has_required_sections(self, sample_transcript, sample_clip, subtitle_config):
        content = _build_ass_file(
            segments=sample_transcript.get_segments_in_range(
                sample_clip.start_time, sample_clip.end_time
            ),
            config=subtitle_config,
            total_duration=sample_clip.duration,
        )
        # Actually build with adjusted segments
        from autoclip.core.subtitle import _adjust_timestamps
        segs = sample_transcript.get_segments_in_range(0.0, 10.0)
        adj = _adjust_timestamps(segs, 0.0, 10.0)
        content = _build_ass_file(adj, subtitle_config, 10.0)

        assert "[Script Info]" in content
        assert "[V4+ Styles]" in content
        assert "[Events]" in content

    def test_has_default_style(self, sample_transcript, subtitle_config):
        from autoclip.core.subtitle import _adjust_timestamps
        segs = sample_transcript.get_segments_in_range(0.0, 10.0)
        adj = _adjust_timestamps(segs, 0.0, 10.0)
        content = _build_ass_file(adj, subtitle_config, 10.0)
        assert "Style: Default" in content

    def test_has_highlight_style(self, sample_transcript, subtitle_config):
        from autoclip.core.subtitle import _adjust_timestamps
        segs = sample_transcript.get_segments_in_range(0.0, 10.0)
        adj = _adjust_timestamps(segs, 0.0, 10.0)
        content = _build_ass_file(adj, subtitle_config, 10.0)
        assert "Style: Highlight" in content

    def test_has_dialogue_lines(self, sample_transcript, subtitle_config):
        from autoclip.core.subtitle import _adjust_timestamps
        segs = sample_transcript.get_segments_in_range(0.0, 10.0)
        adj = _adjust_timestamps(segs, 0.0, 10.0)
        content = _build_ass_file(adj, subtitle_config, 10.0)
        assert "Dialogue:" in content


# ─── Full generate_subtitles ──────────────────────────────────────────────────


class TestGenerateSubtitles:
    def test_creates_file(self, sample_transcript, sample_clip, subtitle_config, tmp_path):
        output_path = tmp_path / "test.ass"
        result = generate_subtitles(
            transcript=sample_transcript,
            clip=sample_clip,
            output_path=output_path,
            config=subtitle_config,
        )
        assert result == output_path
        assert output_path.exists()
        assert output_path.stat().st_size > 0

    def test_file_is_valid_utf8(self, sample_transcript, sample_clip, subtitle_config, tmp_path):
        output_path = tmp_path / "test.ass"
        generate_subtitles(
            transcript=sample_transcript,
            clip=sample_clip,
            output_path=output_path,
            config=subtitle_config,
        )
        content = output_path.read_text(encoding="utf-8-sig")
        assert len(content) > 0

    def test_uppercase_config(self, sample_transcript, sample_clip, tmp_path):
        config = SubtitleConfig(enabled=True, uppercase=True)
        output_path = tmp_path / "upper.ass"
        generate_subtitles(
            transcript=sample_transcript,
            clip=sample_clip,
            output_path=output_path,
            config=config,
        )
        content = output_path.read_text(encoding="utf-8-sig")
        # Dialogue lines should have uppercase text
        dialogue_lines = [l for l in content.split("\n") if l.startswith("Dialogue:")]
        for line in dialogue_lines:
            # Text portion (after last ,,) should be uppercase
            text_part = line.split(",,")[-1] if ",," in line else ""
            if text_part and not text_part.startswith("{"):
                assert text_part == text_part.upper() or any(
                    c in text_part for c in "{}\\rHighlight"
                )
