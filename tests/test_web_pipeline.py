from __future__ import annotations

from pathlib import Path

from autoclip.models.clip import Clip


def test_analysis_pipeline_persists_editable_clip_candidates(tmp_path: Path) -> None:
    from autoclip.web.runtime_pipeline import StudioPipeline
    from autoclip.web.runtime_store import RuntimeStore

    source = tmp_path / "episode.mp4"
    source.write_bytes(b"video")
    store = RuntimeStore(tmp_path / "library")
    project = store.create_from_upload(source, original_name="Episode.mp4")
    pipeline = StudioPipeline(
        store,
        transcribe=lambda *_: object(),
        analyze=lambda *_: [
            Clip(
                start_time=12.0,
                end_time=42.0,
                score=9,
                reason="Strong hook",
                suggested_title="Big reveal",
                language="en",
            )
        ],
    )

    pipeline.analyze(project.id, lambda *_: None)

    clips = store.list_clips(project.id)
    assert store.get_project(project.id).status == "ready"
    assert [(clip.title, clip.start_time, clip.end_time, clip.score) for clip in clips] == [
        ("Big reveal", 12.0, 42.0, 9)
    ]
