# Replay bundles

`cases.json`: 24 real, labelled triage cases (8 bug, 7 noise, 3 flaky, 6 test_issue), recorded by
the spike (`spike/triage_capture.py`) from the reference suite under each catalogue variant, plus
model-written specs that failed on the clean app. Each case holds the failing step, error,
attempts, console/network signals and the aria snapshot at the failure.

`testomation bench --replay` scores the analyzer on these without running the app (minutes, not
hours). Re-record when the app, the catalogue or the reference suite changes.
