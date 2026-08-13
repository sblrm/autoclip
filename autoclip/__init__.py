"""
AutoClip — AI-powered video clipper for content creators.

Automatically clips long videos into viral short-form content
for TikTok, Instagram Reels, and YouTube Shorts.
"""

__version__ = "0.1.0"
__author__ = "AutoClip Contributors"
__license__ = "MIT"

from autoclip.models.clip import Clip
from autoclip.models.transcript import Transcript

__all__ = ["Clip", "Transcript", "__version__"]
