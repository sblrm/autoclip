"""Tests for video downloader module."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from autoclip.core.downloader import (
    DownloadResult,
    VideoMetadata,
    _sanitize_filename,
    _fetch_metadata,
    download_video,
)
from autoclip.utils.validators import is_valid_url


# ─── URL Validation ───────────────────────────────────────────────────────────


class TestUrlValidation:
    def test_valid_youtube_url(self):
        assert is_valid_url("https://www.youtube.com/watch?v=dQw4w9WgXcQ")

    def test_valid_youtu_be_url(self):
        assert is_valid_url("https://youtu.be/dQw4w9WgXcQ")

    def test_valid_tiktok_url(self):
        assert is_valid_url("https://www.tiktok.com/@user/video/123456")

    def test_valid_instagram_url(self):
        assert is_valid_url("https://www.instagram.com/reel/ABC123/")

    def test_invalid_no_scheme(self):
        assert not is_valid_url("youtube.com/watch?v=abc")

    def test_invalid_empty(self):
        assert not is_valid_url("")

    def test_invalid_random_string(self):
        assert not is_valid_url("not a url at all")


# ─── Filename Sanitization ────────────────────────────────────────────────────


class TestSanitizeFilename:
    def test_basic_title(self):
        result = _sanitize_filename("Hello World")
        assert result == "Hello_World"

    def test_special_characters(self):
        result = _sanitize_filename('Video: "Best Tips" & Tricks <2024>')
        assert "/" not in result
        assert ":" not in result
        assert "<" not in result
        assert ">" not in result

    def test_max_length(self):
        long_title = "A" * 200
        result = _sanitize_filename(long_title, max_len=80)
        assert len(result) <= 80

    def test_empty_title(self):
        result = _sanitize_filename("")
        assert result == "video"

    def test_unicode_title(self):
        result = _sanitize_filename("Cara Mudah Belajar Python — Tutorial Lengkap")
        assert len(result) > 0
        # Unicode characters without special meaning should be kept
        assert "Cara" in result


# ─── VideoMetadata ────────────────────────────────────────────────────────────


class TestVideoMetadata:
    def test_create_metadata(self):
        meta = VideoMetadata(
            title="Test Video",
            uploader="Test Channel",
            duration=300.0,
            platform="youtube",
            url="https://youtu.be/test",
        )
        assert meta.title == "Test Video"
        assert meta.duration == 300.0
        assert meta.platform == "youtube"

    def test_metadata_defaults(self):
        meta = VideoMetadata(
            title="Test",
            uploader="Channel",
            duration=0.0,
            platform="unknown",
            url="https://example.com",
        )
        assert meta.description == ""
        assert meta.tags == []
        assert meta.view_count == 0


# ─── Download (mocked) ────────────────────────────────────────────────────────


class TestDownloadVideo:
    def test_invalid_url_raises_valueerror(self, tmp_path):
        with pytest.raises(ValueError, match="Invalid URL"):
            download_video("not-a-url", tmp_path)

    def test_uses_cached_file(self, tmp_path):
        """Should return cached video if file already exists."""
        # Create a fake cached video file
        fake_video = tmp_path / "Test_Video.mp4"
        fake_video.write_bytes(b"fake video data" * 100)

        mock_meta = VideoMetadata(
            title="Test Video",
            uploader="Channel",
            duration=60.0,
            platform="youtube",
            url="https://youtu.be/test",
        )

        with patch("autoclip.core.downloader._fetch_metadata", return_value=mock_meta):
            result = download_video("https://youtu.be/test", tmp_path)

        assert result.was_cached is True
        assert result.video_path == fake_video

    def test_download_result_structure(self, tmp_path):
        """Test that DownloadResult has correct structure."""
        fake_path = tmp_path / "video.mp4"
        meta = VideoMetadata(
            title="Test", uploader="C", duration=30.0,
            platform="youtube", url="https://youtu.be/x"
        )
        result = DownloadResult(
            video_path=fake_path,
            audio_path=None,
            metadata=meta,
            was_cached=False,
        )
        assert result.video_path == fake_path
        assert result.audio_path is None
        assert result.was_cached is False

    @patch("yt_dlp.YoutubeDL")
    def test_download_creates_output(self, mock_ytdl_class, tmp_path):
        """Test successful download creates file."""
        mock_meta = VideoMetadata(
            title="New Video", uploader="Chan", duration=120.0,
            platform="youtube", url="https://youtu.be/new",
        )

        # Simulate yt-dlp creating the file
        fake_video = tmp_path / "New_Video.mp4"
        fake_video.write_bytes(b"fake content" * 100)

        mock_ydl = MagicMock()
        mock_ydl.__enter__ = MagicMock(return_value=mock_ydl)
        mock_ydl.__exit__ = MagicMock(return_value=False)
        mock_ytdl_class.return_value = mock_ydl

        with patch("autoclip.core.downloader._fetch_metadata", return_value=mock_meta):
            result = download_video("https://youtu.be/new", tmp_path)

        assert result.video_path.exists()
