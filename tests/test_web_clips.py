from __future__ import annotations

from pathlib import Path

import pytest


def test_clip_requires_preview_before_it_can_be_approved(tmp_path: Path) -> None:
    from autoclip.web.studio_store import StudioStore

    source = tmp_path / "episode.mp4"
    source.write_bytes(b"video-bytes")
    store = StudioStore(tmp_path / "library")
    project = store.create_from_upload(source, original_name="Episode 12.mp4")
    clip = store.create_clip(
        project.id,
        start_time=12.0,
        end_time=45.0,
        title="Big reveal",
        score=8,
        language="en",
    )

    with pytest.raises(ValueError, match="preview"):
        store.approve_clip(clip.id)

    previewed = store.mark_preview_ready(clip.id)
    approved = store.approve_clip(clip.id)
    assert previewed.status == "preview_ready"
    assert approved.status == "approved"
