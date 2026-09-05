# Movie2Anim Standalone

This repository is independent of the Unreal Movie2Anim project. Read README.md and docs/ARCHITECTURE.md before changes.

- Never start Unreal Editor as a hidden dependency of this tool.
- Keep models, third-party binaries, venvs and generated runs out of Git.
- Preserve the raw Hue output and label approximate/omitted post-processing explicitly.
- Changes to pose conversion or exporters require numeric transform tests and the FBX SDK roundtrip check.
- Changes to inference require a short real-video run; changes to two-person handling require both actors to complete on the same range.
- Do not claim Manny or robust multi-person compatibility until implemented and verified.
- Avoid overwriting existing run directories. Restrict generated files to the selected run directory.
- Setup uses local UE assets only; normal inference/export must not depend on an engine path.
