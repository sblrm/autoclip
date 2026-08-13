"""Tests for autoclip.wizard — platform detection and config building."""

from __future__ import annotations

import pytest

from autoclip.wizard import detect_platform
from autoclip.utils.validators import detect_platform as validators_detect_platform


class TestDetectPlatform:
    """Tests for detect_platform() in both wizard and validators."""

    def test_youtube_full_url(self):
        assert detect_platform("https://www.youtube.com/watch?v=dQw4w9WgXcQ") == "YouTube"

    def test_youtu_be_short_url(self):
        assert detect_platform("https://youtu.be/dQw4w9WgXcQ") == "YouTube"

    def test_youtube_shorts(self):
        assert detect_platform("https://youtube.com/shorts/abc123") == "YouTube"

    def test_tiktok(self):
        assert detect_platform("https://www.tiktok.com/@user/video/123456") == "TikTok"

    def test_instagram_reel(self):
        assert detect_platform("https://www.instagram.com/reel/abc123/") == "Instagram"

    def test_instagram_post(self):
        assert detect_platform("https://www.instagram.com/p/abc123/") == "Instagram"

    def test_twitter_x(self):
        assert detect_platform("https://x.com/user/status/123") == "X (Twitter)"

    def test_twitter_com(self):
        assert detect_platform("https://twitter.com/user/status/123") == "X (Twitter)"

    def test_twitch(self):
        assert detect_platform("https://www.twitch.tv/streamer") == "Twitch"

    def test_facebook(self):
        assert detect_platform("https://www.facebook.com/video/123") == "Facebook"

    def test_vimeo(self):
        assert detect_platform("https://vimeo.com/123456789") == "Vimeo"

    def test_unknown_url(self):
        assert detect_platform("https://example.com/video") == "Unknown"

    def test_empty_string(self):
        assert detect_platform("") == "Unknown"

    def test_case_insensitive(self):
        assert detect_platform("HTTPS://YOUTUBE.COM/watch?v=abc") == "YouTube"

    def test_validators_detect_platform_matches(self):
        """validators.detect_platform and wizard.detect_platform should agree."""
        urls = [
            "https://youtu.be/test",
            "https://tiktok.com/@user/video/1",
            "https://instagram.com/reel/abc",
            "https://example.com",
        ]
        for url in urls:
            assert detect_platform(url) == validators_detect_platform(url)


class TestWizardHelpers:
    """Tests for internal wizard helper functions."""

    def test_get_installed_ollama_models_returns_list(self):
        """Should return a list (empty or not) without raising."""
        from autoclip.wizard import _get_installed_ollama_models
        result = _get_installed_ollama_models()
        assert isinstance(result, list)

    def test_is_cuda_available_returns_bool(self):
        """Should return bool without raising even if torch not installed."""
        from autoclip.wizard import _is_cuda_available
        result = _is_cuda_available()
        assert isinstance(result, bool)
