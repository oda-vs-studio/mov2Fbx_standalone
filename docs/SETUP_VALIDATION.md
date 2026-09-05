# Setup validation

A fresh copy containing only source/configuration/docs and the three bundled Quinn assets was created without .venv, bin, inference models or run outputs. SetupStandalone.bat --engine <UE 5.8.2> --noninteractive completed:

- Created a Python 3.13 x64 virtual environment and installed requirements.lock.txt.
- Extracted all seven UE ONNX models, external data, and SMPL-X joint data.
- Built all three native FBX helpers using automatically detected Visual Studio C++ tools.
- Downloaded the official YOLOX-S model and verified its pinned SHA256.
- Passed all 14 tests, including FBX SDK roundtrips, and the runtime doctor check.
- Used that fresh environment to process a 16-frame video through the actual drop BAT, producing an 89-bone Quinn FBX at 24 fps with SDK roundtrip matrix error 0.
- Re-running setup reused the existing hash-verified inference models and completed successfully.

The original working repository's inference model hashes still match its extraction manifest. Its models, virtual environment, binaries and run outputs were not removed. At audit time no large model/intermediate files were tracked in the standalone Git repository; .gitignore was broadened to cover stray generated files as well. Small exceptions intentionally include QuinnSkeleton.fbx, models/quinn_skeleton.txt and models/quinn_manifest.json.

Interactive folder/file selection uses standard tkinter dialogs. The automated validation supplied --engine rather than interacting with those dialogs. Python, Visual Studio, UE and the installed body-tracker plugin remain external prerequisites; setup does not install Unreal Engine itself.
