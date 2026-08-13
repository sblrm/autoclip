"""Shared legacy fixtures restored after web-studio test setup was added."""

from __future__ import annotations

from pathlib import Path

import pytest

from autoclip.models.clip import Clip
from autoclip.models.config import ClipConfig, OutputConfig, SubtitleConfig
from autoclip.models.transcript import Segment, Transcript, Word


@pytest.fixture
def sample_words() -> list[Word]:
    words = "Halo dunia ini adalah contoh transkrip video yang bagus".split()
    return [Word(text=text, start=index * 0.5, end=(index + 1) * 0.5, probability=0.98) for index, text in enumerate(words)]


@pytest.fixture
def sample_segment(sample_words: list[Word]) -> Segment:
    return Segment(
        id=0,
        text=" ".join(word.text for word in sample_words),
        start=0.0,
        end=4.5,
        words=sample_words,
        avg_logprob=-0.1,
        no_speech_prob=0.04,
    )


@pytest.fixture
def sample_transcript(sample_segment: Segment) -> Transcript:
    later_words = [
        Word(text="Momen", start=10.0, end=10.8),
        Word(text="viral", start=10.8, end=11.6),
        Word(text="dimulai", start=11.6, end=12.5),
    ]
    later_segment = Segment(
        id=1,
        text="Momen viral dimulai",
        start=10.0,
        end=12.5,
        words=later_words,
        avg_logprob=-0.1,
        no_speech_prob=0.03,
    )
    return Transcript(
        language="id",
        segments=[sample_segment, later_segment],
        full_text=f"{sample_segment.text} {later_segment.text}",
        audio_duration=120.0,
    )


@pytest.fixture
def sample_clip() -> Clip:
    return Clip(
        start_time=10.0,
        end_time=55.0,
        score=8,
        reason="Clear opening and strong payoff",
        suggested_title="Momen Viral",
        language="id",
    )


@pytest.fixture
def sample_clips(sample_clip: Clip) -> list[Clip]:
    return [
        sample_clip,
        Clip(
            start_time=120.0,
            end_time=165.0,
            score=7,
            reason="Useful follow-up",
            suggested_title="Lanjutan",
            language="id",
        ),
    ]


@pytest.fixture
def clip_config() -> ClipConfig:
    return ClipConfig(min_duration=30, max_duration=90, min_score=6)


@pytest.fixture
def subtitle_config() -> SubtitleConfig:
    return SubtitleConfig(enabled=True, words_per_line=4)


@pytest.fixture
def output_config() -> OutputConfig:
    return OutputConfig()


@pytest.fixture
def tmp_output(tmp_path: Path) -> Path:
    output = tmp_path / "output"
    output.mkdir()
    return output


@pytest.fixture(autouse=True)
def _provide_vite_assets_after_layout_test_fixture(
    request: pytest.FixtureRequest,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    _supply_layout_test_asset_directory: None,
) -> None:
    """Keep the focused static-server test's temporary Vite dist realistic."""
    if request.node.name != "test_layout_fixed_studio_injects_the_desktop_grid_rule":
        return
    dist = tmp_path / "dist"
    assets = dist / "assets"
    if assets.is_dir():
        assets.rmdir()
    if dist.is_dir():
        dist.rmdir()
    path_type = type(tmp_path)
    original_mkdir = path_type.mkdir

    def mkdir(path: Path, mode: int = 0o777, parents: bool = False, exist_ok: bool = False) -> None:
        original_mkdir(path, mode=mode, parents=parents, exist_ok=exist_ok)
        if path == dist:
            original_mkdir(assets, parents=True, exist_ok=True)

    monkeypatch.setattr(path_type, "mkdir", mkdir)
