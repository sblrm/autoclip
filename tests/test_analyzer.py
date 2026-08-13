"""Tests for viral moment analyzer module."""

from __future__ import annotations

import json

import pytest

from autoclip.core.analyzer import (
    _analyze_heuristic,
    _format_duration,
    _merge_overlapping,
    _parse_llm_response,
    _validate_clips,
)
from autoclip.models.clip import Clip
from autoclip.models.config import ClipConfig, OllamaConfig


# ─── LLM Response Parsing ─────────────────────────────────────────────────────


class TestParseLLMResponse:
    def test_valid_json_array(self):
        response = json.dumps([
            {
                "start_time": 10.0,
                "end_time": 55.0,
                "score": 8,
                "reason": "Great moment",
                "suggested_title": "Amazing Clip",
                "language": "id",
            }
        ])
        clips = _parse_llm_response(response)
        assert len(clips) == 1
        assert clips[0].score == 8
        assert clips[0].start_time == 10.0

    def test_json_with_markdown_code_block(self):
        response = '''```json
[{"start_time": 5.0, "end_time": 40.0, "score": 7, "reason": "test", "suggested_title": "T", "language": "en"}]
```'''
        clips = _parse_llm_response(response)
        assert len(clips) == 1

    def test_json_embedded_in_text(self):
        response = """Here are the viral moments I found:
[{"start_time": 20.0, "end_time": 60.0, "score": 9, "reason": "Viral hook", "suggested_title": "Hook", "language": "id"}]
That's my analysis!"""
        clips = _parse_llm_response(response)
        assert len(clips) == 1
        assert clips[0].score == 9

    def test_trailing_comma_handled(self):
        response = '[{"start_time": 0.0, "end_time": 30.0, "score": 6, "reason": "ok", "suggested_title": "T", "language": "en",}]'
        clips = _parse_llm_response(response)
        assert len(clips) == 1

    def test_invalid_json_raises(self):
        with pytest.raises(ValueError, match="No JSON array"):
            _parse_llm_response("This is not JSON at all")

    def test_invalid_score_skipped(self):
        """Clips with invalid data should be skipped gracefully."""
        response = json.dumps([
            {"start_time": 0.0, "end_time": 30.0, "score": 15,  # score > 10, should be clamped or skipped
             "reason": "r", "suggested_title": "T", "language": "id"},
        ])
        # The Pydantic model will reject score > 10
        clips = _parse_llm_response(response)
        assert len(clips) == 0

    def test_multiple_clips_returned(self):
        items = [
            {"start_time": float(i * 60), "end_time": float(i * 60 + 45), "score": 9 - i,
             "reason": f"reason {i}", "suggested_title": f"Clip {i}", "language": "id"}
            for i in range(5)
        ]
        clips = _parse_llm_response(json.dumps(items))
        assert len(clips) == 5


# ─── Clip Validation ──────────────────────────────────────────────────────────


class TestValidateClips:
    def test_valid_clips_pass_through(self, sample_clips, clip_config):
        valid = _validate_clips(sample_clips, video_duration=600.0, config=clip_config)
        assert len(valid) == len(sample_clips)

    def test_clip_below_min_duration_removed(self, clip_config):
        short_clip = Clip(start_time=0.0, end_time=10.0, score=8,
                          reason="Too short", suggested_title="Short", language="id")
        valid = _validate_clips([short_clip], video_duration=600.0, config=clip_config)
        assert len(valid) == 0

    def test_clip_above_max_duration_removed(self, clip_config):
        long_clip = Clip(start_time=0.0, end_time=200.0, score=8,
                         reason="Too long", suggested_title="Long", language="id")
        valid = _validate_clips([long_clip], video_duration=600.0, config=clip_config)
        assert len(valid) == 0

    def test_clip_clamped_to_video_bounds(self, clip_config):
        # Clip extends beyond video duration
        clip = Clip(start_time=570.0, end_time=650.0, score=7,
                    reason="Near end", suggested_title="End clip", language="id")
        valid = _validate_clips([clip], video_duration=600.0, config=clip_config)
        # Should be clamped or removed (duration 30s which is at min)
        if valid:
            assert valid[0].end_time <= 600.0


# ─── Overlap Merging ──────────────────────────────────────────────────────────


class TestMergeOverlapping:
    def test_non_overlapping_clips_unchanged(self):
        clips = [
            Clip(start_time=0.0, end_time=40.0, score=7, reason="r", suggested_title="A", language="id"),
            Clip(start_time=100.0, end_time=140.0, score=8, reason="r", suggested_title="B", language="id"),
        ]
        merged = _merge_overlapping(clips, tolerance=5.0)
        assert len(merged) == 2

    def test_overlapping_clips_merged(self):
        clips = [
            Clip(start_time=0.0, end_time=50.0, score=7, reason="r", suggested_title="A", language="id"),
            Clip(start_time=40.0, end_time=90.0, score=9, reason="r", suggested_title="B", language="id"),
        ]
        merged = _merge_overlapping(clips, tolerance=5.0)
        assert len(merged) == 1
        assert merged[0].start_time == 0.0
        assert merged[0].end_time == 90.0
        assert merged[0].score == 9  # Higher score kept

    def test_single_clip_unchanged(self, sample_clip):
        merged = _merge_overlapping([sample_clip])
        assert len(merged) == 1
        assert merged[0] == sample_clip

    def test_adjacent_clips_merged_with_tolerance(self):
        clips = [
            Clip(start_time=0.0, end_time=40.0, score=6, reason="r", suggested_title="A", language="id"),
            Clip(start_time=44.0, end_time=84.0, score=8, reason="r", suggested_title="B", language="id"),
        ]
        merged = _merge_overlapping(clips, tolerance=5.0)
        assert len(merged) == 1


# ─── Heuristic Fallback ───────────────────────────────────────────────────────


class TestAnalyzeHeuristic:
    def test_returns_clips(self, sample_transcript, clip_config):
        clip_config.min_score = 1  # Low threshold to ensure hits
        clips = _analyze_heuristic(sample_transcript, clip_config)
        assert isinstance(clips, list)

    def test_all_clips_within_duration_range(self, sample_transcript, clip_config):
        clip_config.min_score = 1
        clips = _analyze_heuristic(sample_transcript, clip_config)
        for clip in clips:
            assert clip.duration >= clip_config.min_duration
            assert clip.duration <= clip_config.max_duration


# ─── Format Duration ──────────────────────────────────────────────────────────


class TestFormatDuration:
    def test_under_one_hour(self):
        assert _format_duration(125.0) == "02:05"

    def test_exactly_one_hour(self):
        assert _format_duration(3600.0) == "01:00:00"

    def test_zero(self):
        assert _format_duration(0.0) == "00:00"
