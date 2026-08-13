"""Tests for config loading and management."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from autoclip.config import (
    _deep_merge,
    get_default_config_dict,
    init_config,
    load_config,
    save_config,
)
from autoclip.models.config import AutoClipConfig, OutputConfig, TrackerConfig, WhisperConfig

def test_legacy_mediapipe_yaml_remains_readable() -> None:
    assert TrackerConfig.model_validate({"use_mediapipe": True}).engine == "mediapipe_cpu"
    assert TrackerConfig.model_validate({"use_mediapipe": False}).engine == "auto"
    assert TrackerConfig().engine == "auto"
    assert OutputConfig().encoder_mode == "auto"


@pytest.mark.parametrize("video_codec", ["libx264", "h264_nvenc", "hevc_nvenc"])
def test_legacy_video_codec_populates_encoder_mode(video_codec: str) -> None:
    assert OutputConfig.model_validate({"video_codec": video_codec}).encoder_mode == video_codec


def test_explicit_encoder_mode_takes_precedence_over_legacy_video_codec() -> None:
    config = OutputConfig.model_validate(
        {"video_codec": "libx264", "encoder_mode": "h264_nvenc"},
    )
    assert config.encoder_mode == "h264_nvenc"
    assert config.video_codec == "libx264"

def test_load_config_migrates_persisted_legacy_video_codec(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text("output:\n  video_codec: hevc_nvenc\n", encoding="utf-8")

    config = load_config(config_path)

    assert config.output.video_codec == "hevc_nvenc"


# ─── Default Config ───────────────────────────────────────────────────────────


class TestDefaultConfig:
    def test_default_whisper_model(self):
        cfg = AutoClipConfig()
        assert cfg.whisper.model == "base"

    def test_default_ollama_model(self):
        cfg = AutoClipConfig()
        assert cfg.ollama.model == "llama3"

    def test_default_clip_duration(self):
        cfg = AutoClipConfig()
        assert cfg.clip.min_duration == 30
        assert cfg.clip.max_duration == 90

    def test_default_output_resolution(self):
        cfg = AutoClipConfig()
        assert cfg.output.width == 1080
        assert cfg.output.height == 1920

    def test_default_subtitle_enabled(self):
        cfg = AutoClipConfig()
        assert cfg.subtitle.enabled is True

    def test_invalid_whisper_model_raises(self):
        with pytest.raises(ValueError):
            WhisperConfig(model="nonexistent_model")


# ─── Deep Merge ───────────────────────────────────────────────────────────────


class TestDeepMerge:
    def test_simple_override(self):
        base = {"a": 1, "b": 2}
        override = {"b": 99}
        result = _deep_merge(base, override)
        assert result["a"] == 1
        assert result["b"] == 99

    def test_nested_merge(self):
        base = {"whisper": {"model": "base", "language": None}}
        override = {"whisper": {"model": "small"}}
        result = _deep_merge(base, override)
        assert result["whisper"]["model"] == "small"
        assert result["whisper"]["language"] is None  # Preserved

    def test_base_not_mutated(self):
        base = {"a": 1, "nested": {"x": 10}}
        override = {"nested": {"x": 99}}
        _deep_merge(base, override)
        assert base["nested"]["x"] == 10  # Original unchanged

    def test_new_keys_added(self):
        base = {"existing": 1}
        override = {"new_key": "value"}
        result = _deep_merge(base, override)
        assert result["new_key"] == "value"
        assert result["existing"] == 1


# ─── Load Config from File ────────────────────────────────────────────────────


class TestLoadConfig:
    def test_load_defaults_when_no_file(self, tmp_path):
        nonexistent = tmp_path / "does_not_exist.yaml"
        cfg = load_config(nonexistent)
        # Should return defaults
        assert cfg.whisper.model == "base"

    def test_load_partial_config(self, tmp_path):
        config_file = tmp_path / "config.yaml"
        config_file.write_text("whisper:\n  model: large-v3\n")

        cfg = load_config(config_file)
        assert cfg.whisper.model == "large-v3"
        # Other defaults preserved
        assert cfg.ollama.model == "llama3"

    def test_load_full_config(self, tmp_path):
        defaults = get_default_config_dict()
        defaults["whisper"]["model"] = "medium"
        defaults["clip"]["max_clips"] = 5

        config_file = tmp_path / "config.yaml"
        with open(config_file, "w") as f:
            yaml.dump(defaults, f)

        cfg = load_config(config_file)
        assert cfg.whisper.model == "medium"
        assert cfg.clip.max_clips == 5

    def test_empty_yaml_returns_defaults(self, tmp_path):
        config_file = tmp_path / "empty.yaml"
        config_file.write_text("")
        cfg = load_config(config_file)
        assert cfg.whisper.model == "base"


# ─── Save Config ──────────────────────────────────────────────────────────────


class TestSaveConfig:
    def test_save_creates_file(self, tmp_path):
        cfg = AutoClipConfig()
        path = save_config(cfg, tmp_path / "output.yaml")
        assert path.exists()

    def test_save_and_reload(self, tmp_path):
        cfg = AutoClipConfig()
        cfg.whisper.model = "small"
        cfg.clip.max_clips = 3

        path = tmp_path / "test_config.yaml"
        save_config(cfg, path)

        loaded = load_config(path)
        assert loaded.whisper.model == "small"
        assert loaded.clip.max_clips == 3

    def test_save_creates_parent_dirs(self, tmp_path):
        deep_path = tmp_path / "a" / "b" / "c" / "config.yaml"
        cfg = AutoClipConfig()
        save_config(cfg, deep_path)
        assert deep_path.exists()


# ─── Init Config ──────────────────────────────────────────────────────────────


class TestInitConfig:
    def test_init_creates_file(self, tmp_path, monkeypatch):
        # Monkeypatch CONFIG_FILE to use tmp_path
        import autoclip.config as cfg_module
        monkeypatch.setattr(cfg_module, "CONFIG_DIR", tmp_path / ".autoclip")
        monkeypatch.setattr(cfg_module, "CONFIG_FILE", tmp_path / ".autoclip" / "config.yaml")

        path, created = init_config()
        assert created is True
        assert path.exists()

    def test_init_does_not_overwrite_existing(self, tmp_path, monkeypatch):
        import autoclip.config as cfg_module
        config_dir = tmp_path / ".autoclip"
        config_file = config_dir / "config.yaml"
        config_dir.mkdir()
        config_file.write_text("existing: content\n")

        monkeypatch.setattr(cfg_module, "CONFIG_DIR", config_dir)
        monkeypatch.setattr(cfg_module, "CONFIG_FILE", config_file)

        _, created = init_config(force=False)
        assert created is False
        assert config_file.read_text() == "existing: content\n"  # Unchanged

    def test_init_with_force_overwrites(self, tmp_path, monkeypatch):
        import autoclip.config as cfg_module
        config_dir = tmp_path / ".autoclip"
        config_file = config_dir / "config.yaml"
        config_dir.mkdir()
        config_file.write_text("old: content\n")

        monkeypatch.setattr(cfg_module, "CONFIG_DIR", config_dir)
        monkeypatch.setattr(cfg_module, "CONFIG_FILE", config_file)

        _, created = init_config(force=True)
        assert created is True
        new_content = config_file.read_text()
        assert "old: content" not in new_content
        assert "AutoClip" in new_content
