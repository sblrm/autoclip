"""Tests for Whisper transcriber module."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from autoclip.core.transcriber import _cache_key, _get_temp_audio_path
from autoclip.models.config import WhisperConfig
from autoclip.models.transcript import Segment, Transcript, Word


# ─── Transcript.from_whisper_result ──────────────────────────────────────────


class TestTranscriptFromWhisper:
    def test_basic_parsing(self):
        raw = {
            "language": "id",
            "segments": [
                {
                    "text": "Halo dunia",
                    "start": 0.0,
                    "end": 1.5,
                    "avg_logprob": -0.2,
                    "no_speech_prob": 0.05,
                    "words": [
                        {"word": "Halo", "start": 0.0, "end": 0.6, "probability": 0.99},
                        {"word": "dunia", "start": 0.6, "end": 1.5, "probability": 0.97},
                    ],
                }
            ],
        }
        t = Transcript.from_whisper_result(raw, audio_duration=60.0)

        assert t.language == "id"
        assert len(t.segments) == 1
        assert t.segments[0].text == "Halo dunia"
        assert len(t.segments[0].words) == 2
        assert t.audio_duration == 60.0

    def test_full_text_concatenation(self):
        raw = {
            "language": "en",
            "segments": [
                {"text": "Hello", "start": 0.0, "end": 1.0, "words": [],
                 "avg_logprob": 0.0, "no_speech_prob": 0.0},
                {"text": "world", "start": 1.0, "end": 2.0, "words": [],
                 "avg_logprob": 0.0, "no_speech_prob": 0.0},
            ],
        }
        t = Transcript.from_whisper_result(raw)
        assert t.full_text == "Hello world"

    def test_empty_segments(self):
        raw = {"language": "id", "segments": []}
        t = Transcript.from_whisper_result(raw)
        assert len(t.segments) == 0
        assert t.full_text == ""

    def test_missing_language_defaults_to_unknown(self):
        raw = {"segments": []}
        t = Transcript.from_whisper_result(raw)
        assert t.language == "unknown"


# ─── Transcript utility methods ───────────────────────────────────────────────


class TestTranscriptUtils:
    def test_get_text_in_range(self, sample_transcript):
        text = sample_transcript.get_text_in_range(0.0, 5.0)
        assert "Halo" in text

    def test_get_segments_in_range_exact(self, sample_transcript):
        segs = sample_transcript.get_segments_in_range(0.0, 4.6)
        assert len(segs) >= 1
        assert segs[0].text.startswith("Halo")

    def test_get_segments_empty_range(self, sample_transcript):
        segs = sample_transcript.get_segments_in_range(1000.0, 2000.0)
        assert segs == []

    def test_to_formatted_string(self, sample_transcript):
        formatted = sample_transcript.to_formatted_string()
        assert "[00:00]" in formatted
        assert "Halo" in formatted

    def test_repr(self, sample_transcript):
        r = repr(sample_transcript)
        assert "Transcript" in r
        assert "id" in r


# ─── Segment properties ───────────────────────────────────────────────────────


class TestSegmentProperties:
    def test_is_speech_true(self, sample_segment):
        assert sample_segment.is_speech is True

    def test_is_speech_false(self):
        seg = Segment(
            id=0, text="[noise]", start=0.0, end=1.0,
            no_speech_prob=0.95, avg_logprob=-0.5
        )
        assert seg.is_speech is False

    def test_confidence_range(self, sample_segment):
        assert 0.0 <= sample_segment.confidence <= 1.0

    def test_duration(self, sample_segment):
        assert abs(sample_segment.duration - 4.5) < 0.01


# ─── Config and cache ─────────────────────────────────────────────────────────


class TestTranscriberHelpers:
    def test_cache_key_is_deterministic(self, tmp_path):
        video = tmp_path / "test.mp4"
        video.write_bytes(b"fake" * 100)
        config = WhisperConfig(model="base")

        key1 = _cache_key(video, config)
        key2 = _cache_key(video, config)
        assert key1 == key2

    def test_cache_key_differs_by_model(self, tmp_path):
        video = tmp_path / "test.mp4"
        video.write_bytes(b"fake" * 100)
        key_base = _cache_key(video, WhisperConfig(model="base"))
        key_small = _cache_key(video, WhisperConfig(model="small"))
        assert key_base != key_small

    def test_get_temp_audio_path(self, tmp_path):
        video = tmp_path / "my_video.mp4"
        audio = _get_temp_audio_path(video)
        assert audio.parent == video.parent
        assert audio.suffix == ".wav"
        assert "my_video" in audio.name


# ─── Transcribe (mocked) ─────────────────────────────────────────────────────


class TestTranscribeFunction:
    @patch("autoclip.core.transcriber.extract_audio")
    @patch("autoclip.core.transcriber._get_audio_duration", return_value=120.0)
    def test_transcribe_calls_whisper(self, mock_duration, mock_extract, tmp_path):
        """Test that transcribe() correctly calls whisper.load_model and transcribe."""
        video = tmp_path / "video.mp4"
        video.write_bytes(b"fake")

        mock_model = MagicMock()
        mock_model.transcribe.return_value = {
            "language": "id",
            "segments": [
                {"text": "Test", "start": 0.0, "end": 1.0, "words": [],
                 "avg_logprob": -0.1, "no_speech_prob": 0.02}
            ],
        }

        with patch("whisper.load_model", return_value=mock_model):
            from autoclip.core.transcriber import transcribe
            config = WhisperConfig(model="base", device="cpu")
            result = transcribe(video, config)

        assert result.language == "id"
        assert len(result.segments) == 1
        mock_model.transcribe.assert_called_once()

    def test_transcribe_raises_on_missing_file(self, tmp_path):
        from autoclip.core.transcriber import transcribe
        config = WhisperConfig()
        with pytest.raises(FileNotFoundError):
            transcribe(tmp_path / "nonexistent.mp4", config)
