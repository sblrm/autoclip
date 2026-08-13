"""Adapters that reuse AutoClip's core pipeline for local web projects."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from autoclip.web.runtime_store import RuntimeStore

ProgressReporter = Callable[[str, float, str], None]


class StudioPipeline:
    """Run source resolution, transcription, and clip analysis for one project."""

    def __init__(
        self,
        store: RuntimeStore,
        *,
        transcribe: Callable[..., Any] | None = None,
        analyze: Callable[..., list[Any]] | None = None,
        download: Callable[..., Any] | None = None,
    ) -> None:
        self.store = store
        self._transcribe = transcribe or _transcribe
        self._analyze = analyze or _analyze
        self._download = download or _download

    def analyze(self, project_id: str, report: ProgressReporter) -> None:
        """Persist AI clip candidates while retaining the original local source."""
        from autoclip.config import load_config

        project = self.store.get_project(project_id)
        config = load_config()
        project_root = self.store.root / project.id
        cache_dir = project_root / ".cache"

        self.store.set_project_status(project.id, "transcribing")
        report("transcribing", 0.15, "Transcribing video locally")
        video_path = self._resolve_source(project.id, project.source_kind, project.source_path, project_root)
        transcript = self._transcribe(video_path, config.whisper, cache_dir)
        self._save_transcript(project.id, transcript, project_root)

        self.store.set_project_status(project.id, "analyzing")
        report("analyzing", 0.65, "Finding high-potential clips")
        candidates = self._analyze(transcript, config.ollama, config.clip)
        for candidate in candidates:
            self.store.create_clip(
                project.id,
                start_time=candidate.start_time,
                end_time=candidate.end_time,
                title=candidate.suggested_title,
                score=candidate.score,
                language=candidate.language,
            )
        self.store.set_project_status(project.id, "ready")
        report("ready", 0.95, f"{len(candidates)} clip candidates ready for review")

    def _resolve_source(
        self,
        project_id: str,
        source_kind: str,
        source_path: str,
        project_root: Path,
    ) -> Path:
        if source_kind == "upload":
            path = Path(source_path)
            if not path.is_file():
                raise FileNotFoundError("Project source video is missing")
            return path
        result = self._download(url=source_path, output_dir=project_root / "source")
        return result.video_path

    def _save_transcript(self, project_id: str, transcript: Any, project_root: Path) -> None:
        transcript_path = project_root / "transcript.json"
        if hasattr(transcript, "model_dump"):
            data = transcript.model_dump(mode="json")
        else:
            data = {"status": "available"}
        transcript_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        self.store.save_artifact(project_id, "transcript", transcript_path)


def _transcribe(video_path: Path, whisper_config: Any, cache_dir: Path) -> Any:
    from autoclip.core.transcriber import transcribe

    return transcribe(video_path=video_path, config=whisper_config, cache_dir=cache_dir)


def _analyze(transcript: Any, ollama_config: Any, clip_config: Any) -> list[Any]:
    from autoclip.core.analyzer import analyze_transcript

    return analyze_transcript(
        transcript=transcript,
        ollama_config=ollama_config,
        clip_config=clip_config,
    )


def _download(url: str, output_dir: Path) -> Any:
    from autoclip.core.downloader import download_video

    return download_video(url=url, output_dir=output_dir)
