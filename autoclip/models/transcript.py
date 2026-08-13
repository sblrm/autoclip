"""Transcript data models for Whisper output."""

from __future__ import annotations

from pydantic import BaseModel, Field


class Word(BaseModel):
    """A single word with timing information from Whisper."""

    text: str = Field(..., description="The word text")
    start: float = Field(..., description="Word start time in seconds", ge=0)
    end: float = Field(..., description="Word end time in seconds", ge=0)
    probability: float = Field(default=1.0, description="Confidence probability (0-1)", ge=0, le=1)

    @property
    def duration(self) -> float:
        return self.end - self.start

    def __repr__(self) -> str:
        return f"Word(text={self.text!r}, start={self.start:.2f}, end={self.end:.2f})"


class Segment(BaseModel):
    """A transcribed segment (sentence/phrase) with timing and words."""

    id: int = Field(..., description="Segment index")
    text: str = Field(..., description="Full segment text")
    start: float = Field(..., description="Segment start time in seconds", ge=0)
    end: float = Field(..., description="Segment end time in seconds", ge=0)
    words: list[Word] = Field(default_factory=list, description="Word-level timestamps")
    avg_logprob: float = Field(default=0.0, description="Average log probability (confidence)")
    no_speech_prob: float = Field(default=0.0, description="Probability segment is silence")

    @property
    def duration(self) -> float:
        return self.end - self.start

    @property
    def is_speech(self) -> bool:
        """True if this segment is likely actual speech (not silence/noise)."""
        return self.no_speech_prob < 0.5

    @property
    def confidence(self) -> float:
        """Overall confidence of this segment (0-1)."""
        import math
        return min(1.0, max(0.0, math.exp(self.avg_logprob)))

    def __repr__(self) -> str:
        return f"Segment(id={self.id}, start={self.start:.2f}, end={self.end:.2f}, text={self.text[:40]!r})"


class Transcript(BaseModel):
    """Full transcript from Whisper with language and all segments."""

    language: str = Field(..., description="Detected or specified language code (e.g. 'id', 'en')")
    segments: list[Segment] = Field(default_factory=list, description="All transcript segments")
    full_text: str = Field(default="", description="Complete concatenated transcript text")
    audio_duration: float = Field(default=0.0, description="Total audio duration in seconds")

    @classmethod
    def from_whisper_result(cls, result: dict, audio_duration: float = 0.0) -> "Transcript":
        """Build Transcript from raw Whisper output dict."""
        segments = []
        full_texts = []

        for i, seg in enumerate(result.get("segments", [])):
            words = [
                Word(
                    text=w.get("word", "").strip(),
                    start=w.get("start", seg["start"]),
                    end=w.get("end", seg["end"]),
                    probability=w.get("probability", 1.0),
                )
                for w in seg.get("words", [])
            ]
            segment = Segment(
                id=i,
                text=seg.get("text", "").strip(),
                start=seg.get("start", 0.0),
                end=seg.get("end", 0.0),
                words=words,
                avg_logprob=seg.get("avg_logprob", 0.0),
                no_speech_prob=seg.get("no_speech_prob", 0.0),
            )
            segments.append(segment)
            full_texts.append(segment.text)

        return cls(
            language=result.get("language", "unknown"),
            segments=segments,
            full_text=" ".join(full_texts),
            audio_duration=audio_duration,
        )

    def get_text_in_range(self, start: float, end: float) -> str:
        """Get all text within a time range."""
        texts = []
        for seg in self.segments:
            if seg.start >= start and seg.end <= end:
                texts.append(seg.text)
            elif seg.start < end and seg.end > start:
                # Partial overlap
                texts.append(seg.text)
        return " ".join(texts).strip()

    def get_segments_in_range(self, start: float, end: float) -> list[Segment]:
        """Get all segments (including partial) within a time range."""
        return [
            seg for seg in self.segments
            if not (seg.end <= start or seg.start >= end)
        ]

    def to_formatted_string(self, max_chars_per_line: int = 80) -> str:
        """Format transcript with timestamps for LLM context."""
        lines = []
        for seg in self.segments:
            if seg.is_speech:
                timestamp = f"[{int(seg.start // 60):02d}:{int(seg.start % 60):02d}]"
                lines.append(f"{timestamp} {seg.text}")
        return "\n".join(lines)

    def __repr__(self) -> str:
        return (
            f"Transcript(language={self.language!r}, "
            f"segments={len(self.segments)}, "
            f"duration={self.audio_duration:.1f}s)"
        )
