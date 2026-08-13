"""Indonesian language prompt template for viral moment analysis."""

from __future__ import annotations

ANALYZE_PROMPT_ID = """\
Kamu adalah seorang ahli content creator dan video editor yang berpengalaman dalam membuat konten viral di TikTok, Instagram Reels, dan YouTube Shorts.

Tugasmu adalah menganalisis transkrip video berikut dan menemukan momen-momen terbaik yang berpotensi viral jika dijadikan short video.

## Transkrip Video
Durasi total: {total_duration_formatted}
{transcript}

## Kriteria Momen Viral
Cari momen yang memiliki satu atau lebih karakteristik berikut:
1. **Emosional** — momen mengharukan, mengejutkan, atau menyentuh hati
2. **Lucu/Menghibur** — jokes, cerita lucu, atau situasi tidak terduga
3. **Insight Mendalam** — tips berharga, fakta mengejutkan, atau perspektif unik
4. **Kontroversial** — pendapat yang menantang norma atau memancing diskusi
5. **Storytelling Kuat** — narasi yang menarik dengan conflict dan resolution
6. **Hook Kuat** — pembukaan yang langsung menarik perhatian di detik pertama
7. **Call-to-Action** — momen yang memotivasi penonton untuk mengambil tindakan
8. **Cliffhanger** — momen yang membuat penonton penasaran

## Batasan Durasi
- Minimum: {min_duration} detik
- Maksimum: {max_duration} detik
- Setiap clip harus berdiri sendiri dan dapat dipahami tanpa konteks video sebelumnya

## Format Output
Berikan response HANYA dalam format JSON array berikut (tanpa text lain, tanpa markdown):
[
  {{
    "start_time": <detik sebagai angka desimal>,
    "end_time": <detik sebagai angka desimal>,
    "score": <angka 1-10, seberapa viral potensinya>,
    "reason": "<alasan singkat dalam Bahasa Indonesia mengapa momen ini viral>",
    "suggested_title": "<judul pendek yang menarik untuk short video ini, dalam Bahasa Indonesia>",
    "language": "id"
  }}
]

Temukan maksimal {max_clips} clip terbaik, diurutkan dari skor tertinggi. Hanya sertakan momen dengan skor minimal {min_score}.
"""


def format_prompt_id(
    transcript: str,
    total_duration_formatted: str,
    min_duration: int = 30,
    max_duration: int = 90,
    max_clips: int = 10,
    min_score: int = 6,
) -> str:
    """Format the Indonesian analysis prompt with video data."""
    return ANALYZE_PROMPT_ID.format(
        transcript=transcript,
        total_duration_formatted=total_duration_formatted,
        min_duration=min_duration,
        max_duration=max_duration,
        max_clips=max_clips,
        min_score=min_score,
    )
