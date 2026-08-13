# Graph Report - .  (2026-08-01)

## Corpus Check
- Corpus is ~19,086 words - fits in a single context window. You may not need a graph.

## Summary
- 589 nodes · 1245 edges · 34 communities (28 shown, 6 thin omitted)
- Extraction: 91% EXTRACTED · 9% INFERRED · 0% AMBIGUOUS · INFERRED: 113 edges (avg confidence: 0.5)
- Token cost: 1,500 input · 400 output

## Community Hubs (Navigation)
- Face Tracking & Smart Crop
- CLI Entrypoint & Commands
- Video Downloading Engine
- System Configuration Manager
- Subtitle Generator & Styling
- Interactive CLI Wizard
- Video Clip Data Model
- LLM & Heuristic Viral Analyzer
- Audio Caching & Extraction
- Platform URL Validator Tests
- Whisper Transcription & FFmpeg
- Pytest Test Fixtures
- Video Clipper & Renderer
- Transcript Segment Data Model
- Ollama & CUDA Hardware Detector
- LLM JSON Response Parser
- AutoClip Core Package Init
- Bilingual English Analysis Prompt
- FFprobe Video Metadata Model
- Data Models Package Init
- Clip Output Path Builder
- Clip Title Sanitizer
- Overlapping Clip Merger
- Clip Validation & Filtering
- Whisper Transcript Converter
- Project Documentation & Config Spec
- Duration Formatter Utility
- System Dependency Status Checker
- Transcript Utility Unit Tests
- Whisper Transcriber Unit Tests
- Shell Setup Script
- Tests Package Init
- AutoClip Executable Launcher
- Auto Extraction Specification

## God Nodes (most connected - your core abstractions)
1. `Clip` - 55 edges
2. `AutoClipConfig` - 35 edges
3. `WhisperConfig` - 31 edges
4. `Segment` - 31 edges
5. `Transcript` - 28 edges
6. `Word` - 25 edges
7. `run_wizard()` - 23 edges
8. `SubtitleConfig` - 22 edges
9. `_run_pipeline()` - 20 edges
10. `FacePosition` - 20 edges

## Surprising Connections (you probably didn't know these)
- `TestAnalyzeHeuristic` --uses--> `Clip`  [INFERRED]
  tests/test_analyzer.py → autoclip/models/clip.py
- `TestFormatDuration` --uses--> `Clip`  [INFERRED]
  tests/test_analyzer.py → autoclip/models/clip.py
- `TestMergeOverlapping` --uses--> `Clip`  [INFERRED]
  tests/test_analyzer.py → autoclip/models/clip.py
- `TestParseLLMResponse` --uses--> `Clip`  [INFERRED]
  tests/test_analyzer.py → autoclip/models/clip.py
- `TestValidateClips` --uses--> `Clip`  [INFERRED]
  tests/test_analyzer.py → autoclip/models/clip.py

## Import Cycles
- None detected.

## Communities (34 total, 6 thin omitted)

### Community 0 - "Face Tracking & Smart Crop"
Cohesion: 0.07
Nodes (42): apply_face_crop(), build_crop_trajectory(), CropTrajectory, detect_faces(), _detect_faces_mediapipe(), _detect_faces_opencv(), dominant_face(), FacePosition (+34 more)

### Community 1 - "CLI Entrypoint & Commands"
Cohesion: 0.06
Nodes (52): check(), _fmt_duration(), init(), main(), process(), Path, AutoClip CLI — main command interface built with Typer + Rich., Process a video URL through the full AutoClip pipeline. Downloads the video,… (+44 more)

### Community 2 - "Video Downloading Engine"
Cohesion: 0.07
Nodes (34): download_video(), DownloadResult, _fetch_metadata(), _make_progress_hook(), Path, Video downloader using yt-dlp., Fetch video metadata without downloading., Metadata extracted from a downloaded video. (+26 more)

### Community 3 - "System Configuration Manager"
Cohesion: 0.08
Nodes (28): _config_with_comments(), _deep_merge(), get_default_config_dict(), init_config(), load_config(), Path, AutoClip configuration loader and manager., Initialize the default config file. Returns: (path, created): path to config… (+20 more)

### Community 4 - "Subtitle Generator & Styling"
Cohesion: 0.08
Nodes (30): _adjust_timestamps(), _build_ass_file(), _build_events(), _build_karaoke_lines(), _build_script_info(), _build_simple_line(), _build_styles(), _chunk_words() (+22 more)

### Community 5 - "Interactive CLI Wizard"
Cohesion: 0.10
Nodes (29): _ask_analysis_mode(), _ask_clip_settings(), _ask_device(), _ask_face_tracking(), _ask_output_folder(), _ask_output_format(), _ask_subtitle(), _ask_url() (+21 more)

### Community 6 - "Video Clip Data Model"
Cohesion: 0.08
Nodes (11): Clip, BaseModel, Duration of the clip in seconds., Human-readable duration (MM:SS)., Human-readable start time (MM:SS)., Human-readable end time (MM:SS)., Check if this clip overlaps with another clip (with tolerance in seconds)., Merge two overlapping clips, keeping the higher score and broader range. (+3 more)

### Community 7 - "LLM & Heuristic Viral Analyzer"
Cohesion: 0.19
Nodes (15): _analyze_heuristic(), analyze_transcript(), _analyze_with_llm(), _check_ollama(), Viral moment analyzer using Ollama LLM with heuristic fallback., Fallback heuristic analysis when Ollama is unavailable. Strategy: - Split…, Analyze a transcript to find viral moment candidates using Ollama LLM. Falls…, Check if Ollama server is running and model is available. (+7 more)

### Community 8 - "Audio Caching & Extraction"
Cohesion: 0.17
Nodes (15): _cache_key(), _get_audio_duration(), _get_temp_audio_path(), _load_cached_transcript(), Path, Get a temp audio path in the same directory as the video., Get audio duration in seconds via FFprobe., Generate a cache key based on file content hash + config. (+7 more)

### Community 9 - "Platform URL Validator Tests"
Cohesion: 0.11
Nodes (3): Tests for detect_platform() in both wizard and validators., validators.detect_platform and wizard.detect_platform should agree., TestDetectPlatform

### Community 10 - "Whisper Transcription & FFmpeg"
Cohesion: 0.18
Nodes (13): Whisper-based speech-to-text transcriber., check_ffmpeg(), extract_audio(), get_video_info(), Path, FFmpeg helper utilities., Run an FFmpeg command with optional progress tracking. Args: args: FFmpeg…, Extract audio from video as WAV (16kHz mono — optimal for Whisper). Args:… (+5 more)

### Community 11 - "Pytest Test Fixtures"
Cohesion: 0.22
Nodes (15): fixture, clip_config(), default_config(), ollama_config(), output_config(), Path, Shared pytest fixtures for AutoClip tests., sample_clip() (+7 more)

### Community 12 - "Video Clipper & Renderer"
Cohesion: 0.24
Nodes (13): create_clips(), _export_clip(), _export_clip_tracked(), Path, Video clipper — cuts and exports clips as 9:16 vertical video via FFmpeg., Export a single clip using face-tracking smart crop., Export a single clip with FFmpeg., Cut and export video clips as 9:16 vertical videos. Args: video_path: Source… (+5 more)

### Community 13 - "Transcript Segment Data Model"
Cohesion: 0.17
Nodes (5): A transcribed segment (sentence/phrase) with timing and words., True if this segment is likely actual speech (not silence/noise)., Overall confidence of this segment (0-1)., Segment, TestSegmentProperties

### Community 14 - "Ollama & CUDA Hardware Detector"
Cohesion: 0.20
Nodes (9): _get_installed_ollama_models(), _is_cuda_available(), Return list of locally installed Ollama models, empty if not running., Check if CUDA GPU is available for torch., Tests for autoclip.wizard — platform detection and config building., Tests for internal wizard helper functions., Should return a list (empty or not) without raising., Should return bool without raising even if torch not installed. (+1 more)

### Community 15 - "LLM JSON Response Parser"
Cohesion: 0.29
Nodes (4): _parse_llm_response(), Parse the LLM JSON response into Clip objects. Handles common LLM formatting…, Clips with invalid data should be skipped gracefully., TestParseLLMResponse

### Community 16 - "AutoClip Core Package Init"
Cohesion: 0.18
Nodes (6): AutoClip — AI-powered video clipper for content creators. Automatically clips…, Get all segments (including partial) within a time range., Format transcript with timestamps for LLM context., Full transcript from Whisper with language and all segments., Get all text within a time range., Transcript

### Community 17 - "Bilingual English Analysis Prompt"
Cohesion: 0.24
Nodes (7): format_prompt_en(), English language prompt template for viral moment analysis., Format the English analysis prompt with video data., format_prompt_id(), Indonesian language prompt template for viral moment analysis., Format the Indonesian analysis prompt with video data., Prompt templates for viral moment analysis.

### Community 18 - "FFprobe Video Metadata Model"
Cohesion: 0.22
Nodes (4): Basic video metadata from FFprobe., VideoInfo, patch, TestCreateClips

### Community 19 - "Data Models Package Init"
Cohesion: 0.25
Nodes (5): Data models for AutoClip., BaseModel, Transcript data models for Whisper output., A single word with timing information from Whisper., Word

### Community 20 - "Clip Output Path Builder"
Cohesion: 0.36
Nodes (4): _build_output_path(), Build the output file path for a clip., Tests for video clipper module., TestBuildOutputPath

### Community 21 - "Clip Title Sanitizer"
Cohesion: 0.39
Nodes (3): Convert a clip title to a safe filename component., _sanitize_title(), TestSanitizeTitle

### Community 22 - "Overlapping Clip Merger"
Cohesion: 0.43
Nodes (3): _merge_overlapping(), Merge clips that overlap within tolerance seconds., TestMergeOverlapping

### Community 23 - "Clip Validation & Filtering"
Cohesion: 0.43
Nodes (3): Validate and clean up clip list., _validate_clips(), TestValidateClips

### Community 25 - "Project Documentation & Config Spec"
Cohesion: 0.29
Nodes (7): AutoClip Example Configuration, AutoClip Overview, Face Tracking Smart Crop, Ollama LLM Analysis, Smart Karaoke Subtitles, Viral Moment Scoring, AutoClip Dependencies Specification

### Community 26 - "Duration Formatter Utility"
Cohesion: 0.47
Nodes (3): _format_duration(), Format seconds as MM:SS or HH:MM:SS., TestFormatDuration

### Community 27 - "System Dependency Status Checker"
Cohesion: 0.33
Nodes (3): DependencyStatus, Minimum requirements: FFmpeg + Whisper (can run without Ollama with heuristics)., Holds status of all AutoClip external dependencies.

### Community 29 - "Whisper Transcriber Unit Tests"
Cohesion: 0.40
Nodes (3): patch, Test that transcribe() correctly calls whisper.load_model and transcribe., TestTranscribeFunction

## Knowledge Gaps
- **9 isolated node(s):** `autoclip`, `setup.sh script`, `Auto Extraction Feature`, `Ollama LLM Analysis`, `Viral Moment Scoring` (+4 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **6 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Clip` connect `Video Clip Data Model` to `CLI Entrypoint & Commands`, `Subtitle Generator & Styling`, `LLM & Heuristic Viral Analyzer`, `Pytest Test Fixtures`, `Video Clipper & Renderer`, `LLM JSON Response Parser`, `AutoClip Core Package Init`, `FFprobe Video Metadata Model`, `Data Models Package Init`, `Clip Output Path Builder`, `Clip Title Sanitizer`, `Overlapping Clip Merger`, `Clip Validation & Filtering`, `Duration Formatter Utility`?**
  _High betweenness centrality (0.170) - this node is a cross-community bridge._
- **Why does `AutoClipConfig` connect `System Configuration Manager` to `Pytest Test Fixtures`, `Face Tracking & Smart Crop`, `Data Models Package Init`, `Interactive CLI Wizard`?**
  _High betweenness centrality (0.142) - this node is a cross-community bridge._
- **Why does `WhisperConfig` connect `System Configuration Manager` to `Interactive CLI Wizard`, `Audio Caching & Extraction`, `Whisper Transcription & FFmpeg`, `Pytest Test Fixtures`, `Transcript Segment Data Model`, `Data Models Package Init`, `Whisper Transcript Converter`, `Transcript Utility Unit Tests`, `Whisper Transcriber Unit Tests`?**
  _High betweenness centrality (0.080) - this node is a cross-community bridge._
- **Are the 9 inferred relationships involving `Clip` (e.g. with `TestAnalyzeHeuristic` and `TestFormatDuration`) actually correct?**
  _`Clip` has 9 INFERRED edges - model-reasoned connections that need verification._
- **Are the 13 inferred relationships involving `AutoClipConfig` (e.g. with `TestDeepMerge` and `TestDefaultConfig`) actually correct?**
  _`AutoClipConfig` has 13 INFERRED edges - model-reasoned connections that need verification._
- **Are the 10 inferred relationships involving `WhisperConfig` (e.g. with `TestDeepMerge` and `TestDefaultConfig`) actually correct?**
  _`WhisperConfig` has 10 INFERRED edges - model-reasoned connections that need verification._
- **Are the 10 inferred relationships involving `Segment` (e.g. with `TestAdjustTimestamps` and `TestASSFileStructure`) actually correct?**
  _`Segment` has 10 INFERRED edges - model-reasoned connections that need verification._