"""Tests for video clipper module."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from autoclip.core.clipper import _build_output_path, _sanitize_title
from autoclip.models.clip import Clip
from autoclip.models.config import OutputConfig


# ─── Title Sanitization ───────────────────────────────────────────────────────


class TestSanitizeTitle:
    def test_basic_title(self):
        result = _sanitize_title("My Awesome Clip")
        assert result == "My_Awesome_Clip"

    def test_special_characters_removed(self):
        result = _sanitize_title('Clip: "Best" <viral>')
        assert '"' not in result
        assert "<" not in result
        assert ">" not in result
        assert ":" not in result

    def test_max_length(self):
        long = "A" * 100
        result = _sanitize_title(long, max_len=40)
        assert len(result) <= 40

    def test_empty_title_returns_fallback(self):
        result = _sanitize_title("")
        assert result == "clip"

    def test_unicode_title(self):
        result = _sanitize_title("Momen Viral Terbaik 2024")
        assert len(result) > 0


# ─── Output Path Building ─────────────────────────────────────────────────────


class TestBuildOutputPath:
    def test_output_path_format(self, tmp_output, sample_clip):
        path = _build_output_path(tmp_output, 1, sample_clip)
        assert path.parent == tmp_output
        assert path.suffix == ".mp4"
        assert "clip_01" in path.name
        assert "score8" in path.name

    def test_clip_number_padded(self, tmp_output, sample_clip):
        path = _build_output_path(tmp_output, 5, sample_clip)
        assert "clip_05" in path.name

    def test_high_clip_number(self, tmp_output, sample_clip):
        path = _build_output_path(tmp_output, 15, sample_clip)
        assert "clip_15" in path.name


# ─── Clip Model ───────────────────────────────────────────────────────────────


class TestClipModel:
    def test_duration_calculation(self, sample_clip):
        assert abs(sample_clip.duration - 45.0) < 0.01

    def test_duration_formatted(self, sample_clip):
        assert sample_clip.duration_formatted == "00:45"

    def test_start_formatted(self, sample_clip):
        assert sample_clip.start_formatted == "00:10"

    def test_end_formatted(self, sample_clip):
        assert sample_clip.end_formatted == "00:55"

    def test_overlap_detection_true(self):
        clip_a = Clip(start_time=0.0, end_time=50.0, score=7, reason="r", suggested_title="A", language="id")
        clip_b = Clip(start_time=40.0, end_time=80.0, score=8, reason="r", suggested_title="B", language="id")
        assert clip_a.overlaps(clip_b)

    def test_overlap_detection_false(self):
        clip_a = Clip(start_time=0.0, end_time=40.0, score=7, reason="r", suggested_title="A", language="id")
        clip_b = Clip(start_time=100.0, end_time=140.0, score=8, reason="r", suggested_title="B", language="id")
        assert not clip_a.overlaps(clip_b)

    def test_merge_keeps_broader_range(self):
        clip_a = Clip(start_time=0.0, end_time=50.0, score=7, reason="r", suggested_title="A", language="id")
        clip_b = Clip(start_time=30.0, end_time=90.0, score=9, reason="r", suggested_title="B", language="id")
        merged = clip_a.merge(clip_b)
        assert merged.start_time == 0.0
        assert merged.end_time == 90.0
        assert merged.score == 9

    def test_end_time_must_be_after_start_time(self):
        with pytest.raises(ValueError):
            Clip(start_time=60.0, end_time=30.0, score=5, reason="r", suggested_title="T", language="id")

    def test_score_bounds(self):
        with pytest.raises(Exception):
            Clip(start_time=0.0, end_time=30.0, score=11, reason="r", suggested_title="T", language="id")
        with pytest.raises(Exception):
            Clip(start_time=0.0, end_time=30.0, score=0, reason="r", suggested_title="T", language="id")


# ─── Create Clips (mocked FFmpeg) ─────────────────────────────────────────────


class TestCreateClips:
    def test_missing_video_raises_error(self, tmp_output, sample_clips, output_config):
        from autoclip.core.clipper import create_clips
        with pytest.raises(FileNotFoundError):
            create_clips(
                video_path=tmp_output / "nonexistent.mp4",
                clips=sample_clips,
                output_dir=tmp_output,
                output_config=output_config,
            )

    @patch("autoclip.core.clipper.run_ffmpeg")
    @patch("autoclip.core.clipper.get_video_info")
    def test_creates_one_file_per_clip(self, mock_info, mock_ffmpeg, tmp_path, sample_clips, output_config):
        from autoclip.utils.ffmpeg import VideoInfo
        from autoclip.core.clipper import create_clips

        # Create fake source video
        video = tmp_path / "video.mp4"
        video.write_bytes(b"fake")

        mock_info.return_value = VideoInfo(
            path=video, width=1920, height=1080, duration=600.0,
            fps=30.0, video_codec="h264", audio_codec="aac", size_bytes=1000000
        )

        # Simulate FFmpeg creating output files
        def side_effect(args, **kwargs):
            # Find the output path (last arg without dash prefix)
            output = next((a for a in reversed(args) if not a.startswith("-")), None)
            if output:
                Path(output).touch()
            return MagicMock()

        mock_ffmpeg.side_effect = side_effect

        output_dir = tmp_path / "output"
        paths = create_clips(
            video_path=video,
            clips=sample_clips,
            output_dir=output_dir,
            output_config=output_config,
        )

        assert mock_ffmpeg.call_count == len(sample_clips)
