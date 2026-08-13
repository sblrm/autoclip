"""English language prompt template for viral moment analysis."""

from __future__ import annotations

ANALYZE_PROMPT_EN = """\
You are an expert content creator and video editor with deep expertise in creating viral content for TikTok, Instagram Reels, and YouTube Shorts.

Your task is to analyze the following video transcript and identify the best moments that could go viral as short-form vertical videos.

## Video Transcript
Total duration: {total_duration_formatted}
{transcript}

## Viral Moment Criteria
Look for moments with one or more of these characteristics:
1. **Emotional** — touching, surprising, or deeply moving moments
2. **Entertaining** — jokes, funny stories, or unexpected situations
3. **Valuable Insight** — actionable tips, surprising facts, or unique perspectives
4. **Controversial** — opinions that challenge norms or spark discussion
5. **Strong Storytelling** — compelling narrative with conflict and resolution
6. **Strong Hook** — opening that immediately grabs attention in the first second
7. **Call-to-Action** — moments that motivate viewers to take action
8. **Cliffhanger** — moments that leave viewers wanting more

## Duration Constraints
- Minimum: {min_duration} seconds
- Maximum: {max_duration} seconds
- Each clip must stand alone and be understandable without prior video context

## Output Format
Respond ONLY with a JSON array in the following format (no other text, no markdown):
[
  {{
    "start_time": <seconds as decimal number>,
    "end_time": <seconds as decimal number>,
    "score": <number 1-10, viral potential>,
    "reason": "<brief English explanation of why this moment is viral>",
    "suggested_title": "<short, catchy title for this short video in English>",
    "language": "en"
  }}
]

Find at most {max_clips} best clips, sorted by score (highest first). Only include moments with a score of at least {min_score}.
"""


def format_prompt_en(
    transcript: str,
    total_duration_formatted: str,
    min_duration: int = 30,
    max_duration: int = 90,
    max_clips: int = 10,
    min_score: int = 6,
) -> str:
    """Format the English analysis prompt with video data."""
    return ANALYZE_PROMPT_EN.format(
        transcript=transcript,
        total_duration_formatted=total_duration_formatted,
        min_duration=min_duration,
        max_duration=max_duration,
        max_clips=max_clips,
        min_score=min_score,
    )
