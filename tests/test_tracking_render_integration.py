from __future__ import annotations

import json
from pathlib import Path

import pytest


def test_preview_and_export_share_one_saved_face_trajectory(tmp_path: Path) -> None:
    pytest.importorskip("cv2")
    from autoclip.web.full_store import FullStudioStore
    from autoclip.web.rendering import TrackingService

    fixture = Path(__file__).parent / "fixtures" / "two_people_pixabay.mp4"
    store = FullStudioStore(tmp_path / "projects")
    project = store.create_from_upload(fixture, original_name="two_people.mp4")
    clip = store.create_clip(project.id, start_time=0, end_time=1.5, title="Two people", score=90, language="en")
    service = TrackingService(store)

    tracks = service.detect_tracks(clip.id, lambda *_: None)
    assert tracks
    store.select_face_track(clip.id, tracks[0].id)
    preview = service.render_preview(clip.id, lambda *_: None)
    assert preview is not None and Path(preview.path).is_file()
    store.approve_clip(clip.id)
    exported = service.export_approved(clip.id, lambda *_: None)

    trajectory_artifacts = [item for item in store.list_artifacts(project.id) if item.kind == "tracking_trajectory"]
    trajectory = json.loads(Path(trajectory_artifacts[-1].path).read_text(encoding="utf-8"))
    assert Path(exported.path).is_file()
    assert trajectory["selected_face_track_id"] == tracks[0].id
    assert len(trajectory["centers"]) > 0
