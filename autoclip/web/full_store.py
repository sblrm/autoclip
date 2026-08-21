"""Persistence additions for the complete local studio workflow."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from autoclip.web.runtime_store import RuntimeStore
from autoclip.web.studio_store import StudioClip


@dataclass(frozen=True)
class TrackingGap:
    """A sampled interval where the locked subject was not detected."""

    id: str
    clip_id: str
    start_sample: int
    end_sample: int


class FullStudioStore(RuntimeStore):
    """Runtime store with saved tracking gaps and safe clip-state helpers."""

    def _initialize(self) -> None:
        super()._initialize()
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS tracking_gaps (
                    id TEXT PRIMARY KEY,
                    clip_id TEXT NOT NULL,
                    start_sample INTEGER NOT NULL,
                    end_sample INTEGER NOT NULL
                )
                """
            )

    def clear_tracking_data(self, clip_id: str) -> None:
        """Clear stale candidates before a fresh, deterministic detection pass."""
        self.get_clip(clip_id)
        with self._connect() as connection:
            connection.execute("DELETE FROM face_tracks WHERE clip_id = ?", (clip_id,))
            connection.execute("DELETE FROM tracking_gaps WHERE clip_id = ?", (clip_id,))
            connection.execute(
                "DELETE FROM artifacts WHERE clip_id = ? AND kind IN ('tracking_trajectory', 'tracking_preview')",
                (clip_id,),
            )
            connection.execute("DELETE FROM clip_tracking_resolutions WHERE clip_id = ?", (clip_id,))
            connection.execute(
                """
                UPDATE clips
                SET status = 'draft', selected_face_track_id = NULL, tracking_status = 'detecting'
                WHERE id = ?
                """,
                (clip_id,),
            )

    def clear_tracking_preview(self, clip_id: str) -> None:
        """Invalidate an encoded preview without discarding detection or its subject lock."""
        self.get_clip(clip_id)
        with self._connect() as connection:
            connection.execute(
                "DELETE FROM artifacts WHERE clip_id = ? AND kind = 'tracking_preview'",
                (clip_id,),
            )
            connection.execute(
                "UPDATE clips SET status = 'draft', tracking_status = 'needs_preview' WHERE id = ?",
                (clip_id,),
            )

    def save_tracking_gap(self, clip_id: str, start_sample: int, end_sample: int) -> TrackingGap:
        self.get_clip(clip_id)
        if start_sample < 0 or end_sample < start_sample:
            raise ValueError("Tracking gap bounds are invalid")
        gap = TrackingGap(uuid.uuid4().hex, clip_id, start_sample, end_sample)
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO tracking_gaps (id, clip_id, start_sample, end_sample) VALUES (?, ?, ?, ?)",
                (gap.id, gap.clip_id, gap.start_sample, gap.end_sample),
            )
        return gap

    def list_tracking_gaps(self, clip_id: str) -> list[TrackingGap]:
        self.get_clip(clip_id)
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, clip_id, start_sample, end_sample
                FROM tracking_gaps WHERE clip_id = ? ORDER BY start_sample
                """,
                (clip_id,),
            ).fetchall()
        return [TrackingGap(**dict(row)) for row in rows]

    def select_face_track(self, clip_id: str, track_id: str | None) -> StudioClip:
        """Only allow a clip to lock a subject candidate that belongs to it."""
        if track_id is not None and not any(track.id == track_id for track in self.list_face_tracks(clip_id)):
            raise ValueError("Selected face track does not belong to this clip")
        return self.update_clip(clip_id, selected_face_track_id=track_id)

    def set_clip_status(self, clip_id: str, status: str) -> StudioClip:
        return self._set_clip_status(clip_id, status)
