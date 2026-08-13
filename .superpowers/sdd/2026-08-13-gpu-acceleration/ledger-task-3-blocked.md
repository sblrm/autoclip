# Task 3 blocked addendum

Task 3: BLOCKED — `autoclip/web/tracking.py` must accept optional MediaPipe delegate/metadata and pass delegate into `BaseOptions`. Required existing-file patch is denied by `windows sandbox helper_unknown_error: setup refresh had errors`.

Current implementation evidence: detector adapters, live probe manager, tests added; focused suite result reported by implementer: 15 passed, 1 failed. Failing test is only legacy `MediaPipeTasksDetector` delegate support.

Task 4 does not require blocked `tracking.py` method change. User instructed to skip blocker and continue.
