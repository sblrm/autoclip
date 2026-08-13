"""Clip data model."""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class Clip(BaseModel):
    """Represents a detected viral moment / clip candidate."""

    start_time: float = Field(..., description="Start time in seconds", ge=0)
    end_time: float = Field(..., description="End time in seconds", gt=0)
    score: int = Field(..., description="Viral potential score (1-10)", ge=1, le=10)
    reason: str = Field(..., description="AI reasoning for selecting this moment")
    suggested_title: str = Field(..., description="AI-suggested title for the clip")
    language: str = Field(default="id", description="Primary language of the clip (id/en)")

    @field_validator("end_time")
    @classmethod
    def end_must_be_after_start(cls, v: float, info) -> float:
        if "start_time" in info.data and v <= info.data["start_time"]:
            raise ValueError("end_time must be greater than start_time")
        return v

    @property
    def duration(self) -> float:
        """Duration of the clip in seconds."""
        return self.end_time - self.start_time

    @property
    def duration_formatted(self) -> str:
        """Human-readable duration (MM:SS)."""
        total = int(self.duration)
        return f"{total // 60:02d}:{total % 60:02d}"

    @property
    def start_formatted(self) -> str:
        """Human-readable start time (MM:SS)."""
        total = int(self.start_time)
        return f"{total // 60:02d}:{total % 60:02d}"

    @property
    def end_formatted(self) -> str:
        """Human-readable end time (MM:SS)."""
        total = int(self.end_time)
        return f"{total // 60:02d}:{total % 60:02d}"

    def overlaps(self, other: "Clip", tolerance: float = 5.0) -> bool:
        """Check if this clip overlaps with another clip (with tolerance in seconds)."""
        return not (self.end_time + tolerance < other.start_time or other.end_time + tolerance < self.start_time)

    def merge(self, other: "Clip") -> "Clip":
        """Merge two overlapping clips, keeping the higher score and broader range."""
        return Clip(
            start_time=min(self.start_time, other.start_time),
            end_time=max(self.end_time, other.end_time),
            score=max(self.score, other.score),
            reason=self.reason if self.score >= other.score else other.reason,
            suggested_title=self.suggested_title if self.score >= other.score else other.suggested_title,
            language=self.language,
        )

    def __repr__(self) -> str:
        return (
            f"Clip(start={self.start_formatted}, end={self.end_formatted}, "
            f"duration={self.duration_formatted}, score={self.score}/10)"
        )
