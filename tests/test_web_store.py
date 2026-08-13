from __future__ import annotations

from pathlib import Path


def test_uploaded_video_is_copied_into_a_durable_project(tmp_path: Path) -> None:
    from autoclip.web.store import ProjectStore

    source = tmp_path / "episode.mp4"
    source.write_bytes(b"video-bytes")
    store = ProjectStore(tmp_path / "library")

    project = store.create_from_upload(source, original_name="Episode 12.mp4")

    copied_source = Path(project.source_path)
    assert project.status == "draft"
    assert copied_source.exists()
    assert copied_source.read_bytes() == b"video-bytes"
    assert copied_source.parent == tmp_path / "library" / project.id / "source"
    assert store.get_project(project.id) == project
