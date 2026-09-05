# Standalone architecture

Runtime: Python -> OpenCV -> ONNX Runtime -> SMPL-X pose -> NumPy/SciPy skeleton -> FBX SDK executable.
No `unreal` import, Editor process, UE DLL, Capture Manager or Unreal asset load is used during inference/export.

## Local source references

The port follows the installed Epic implementation under:

`D:\UE\UE_5.8\Engine\Plugins\Marketplace\MetaHumanBodyTracker_5.8\Source`

- `BodyTracker/Private/OfflineBodyTracker.cpp`: ViTPose/CHMR inputs, Hue schedule, temporal windows.
- `BodyTracker/Public/OfflineBodyTracker.h`: tensor dimensions and window sizes.
- `BodyTracker/Public/BodyTrackerUtils.h`: image mapping and letterbox normalization.
- `BodyTracker/Private/CameraCalibration.cpp`: camera model preprocessing and outputs.
- `MetaHumanBodyTracker/Private/MetaHumanSMPLX.cpp`: 55-bone hierarchy and joint regression layout.
- `MetaHumanBodyTracker/Private/Nodes/OfflineBodyTrackerNode.cpp`: camera orientation and Y-up conversion.
- `Engine/Source/Runtime/NNE/Private/NNEModelData.cpp`: uncooked FileData / AdditionalFileData serialization.

The inference models, body data and SDK originate from the local installation. Large inference models and SDK binaries are not committed. The small Quinn reference FBX, skeleton text and provenance manifest are bundled. Original Epic/Autodesk assets retain their attribution; extraction manifests identify source files.

## Model extraction

The extractor supports the installed uncooked UE 5.8 NNE layout. It identifies a single ONNX FileData payload using the serialized file type, validates length, copies data in bounded chunks, and reads additional arrays. Unknown layouts and path traversal are rejected.
ViTPose has >2 GB of external data. The UE descriptor maps tensor filenames to slices of one byte array. The extracted ONNX graph references these slices directly in `OnnxExternalDataBytes`, avoiding a second 2.5 GB copy.

The skeleton extractor validates tagged array IDs and lengths for this asset version, then computes joint rest positions and the first ten shape deltas. It is intentionally version-specific and fails on incompatible assets.

## Coordinate contract

`motion.npz` is the raw Hue result. `world_motion.npz` applies the camera correction and Y/Z flip to root rotation and position, regresses the skeleton from mean shape, and normalizes first-frame X/Z plus the global minimum ankle/foot Y. Child rotations remain in SMPL-X local axes.
Positions in NPZ use metres. FBX/BVH convert positions to centimetres. BVH uses intrinsic ZXY Euler channels. FBX uses the SDK's XYZ Euler order.

The FBX helper reloads its exported file and compares all 4x4 local transforms at every sampled frame. This checks serialization, hierarchy and curve evaluation; it does not establish that the inferred pose matches the original actor or the UE pipeline.

## Legacy manual two-person mode

Both people share camera calibration and frame range but are inferred independently inside explicit static ROIs. Each person gets an independent motion directory and success marker. The parent success marker is written only after both exports finish. The paired HTML preview uses `postMessage` to synchronize its two frames and works with local files.

There is no coupled interaction model, collision/occlusion solve, automatic ID association, or guaranteed common spatial scale. Each output is independently centered.

## Resource and failure behavior

Models are loaded by stage and released before later stages. Hue windows retain overlap; the final model runs on CPU. VideoFrames streams each stage from the original video rather than retaining decoded rasters. The old 600-frame limit is removed; temporal inference uses bounded 260/264-frame windows. Features, poses and FBX data still scale with duration. GPU work has CPU provider fallback inside ONNX Runtime; device selection is not a claim that every operator ran on GPU.
Existing output directories are rejected. Partial runs remain inspectable. GUI cancellation terminates only its own Python child, and completion is gated on exit code plus `SUCCESS`.

## Quinn export

`fbx_skeleton.exe` reads only skeleton nodes, collapsing non-skeleton ancestors into global reference transforms, and converts the supplied FBX to Y-up centimetres. The extracted default reference pose is saved in models; no original mesh or UE dependency is needed during runtime. Scaled and multi-root skeletons are rejected.

`m2a.retarget` uses explicit SMPL-X / Quinn bone correspondence. Reference outgoing bone directions calibrate the A-pose to T-pose difference while preserving target local axes and segment lengths. The world-space source rotations drive calibrated target frames, then parent inverse transforms recover FBX local rotations. Target leg length scales pelvis translation. Additional spine/neck bones share the corresponding source rotation. Twist bones retain reference local offsets; IK markers follow hands and feet. This is FK transfer, not a foot-contact IK solver or a reproduction of UE's corrective rig.

`fbx_retarget.exe` writes skeleton-only FBX, a reference bind pose, and per-frame local translations/rotations; it reimports and compares every local matrix. Tests independently re-extract reference global transforms, check animated bone lengths, outgoing directions, root travel and IK marker positions. Raw Hue output is retained.

The drop BAT explicitly writes the final FBX beside the selected video (the user-requested exception to run-directory-only output). Exclusive creation prevents overwriting an existing FBX. All intermediates stay in a unique runs/drop directory. Videos shorter than 12 frames fail. The old 600-frame cap is removed; all selected frames are exported.

## Automatic shared scene mode

DropVideoToQuinnFBX.bat now runs `scene.solve_auto`. `tracking.PersonDetector` uses the official YOLOX-S ONNX (pinned URL / SHA256 in tools/setup_detection.py and models/yolox_manifest.json). BGR uint8 letterboxing and grid/stride decoding follow the official model contract. The custom tracker assigns detections using Hungarian matching with predicted motion, overlap, and torso HSV appearance. IDs are initially ordered left-to-right, not resorted each frame. Only short gaps are interpolated and flagged. Long absence, low full-clip coverage or more than two significant tracks fail instead of inventing a complete motion. This is not a re-identification neural network, ByteTrack or SAM2.

Each actor receives its own per-frame ROI in ViTPose, CHMR and Hue, with one shared camera calibration and frame range. `prepare(center=False)` retains camera-space inter-person displacement. No actor is separately centered before scene placement. One scene origin and one translation scale are used. Target anatomy offsets are corrected around each actor's shared initial contact anchor, rather than scaling the camera distance differently for each actor.

Initial tilt assumes double support during the first 0.2 seconds. The SMPL-X reference ankle/toe height is subtracted in the animated foot frame to construct virtual sole points; fitting raw joint heights would incorrectly treat the natural ankle/toe height difference as a tilted floor. A robust-in-time median provides four initial contact proxies per actor. SVD estimates the plane normal. A shared rotation aligns the mean accepted normal with +Y; a fixed residual actor rotation is applied about that actor's initial contact center. The horizontal center stays fixed. Initial vertical offsets are aligned to a common floor. Child-local joint rotations are unchanged, so later bending and jumping are retained.

When virtual sole points are degenerate/nonplanar or the suggested correction exceeds 40 degrees, the actor's residual correction is skipped and reported. `--no-tilt-correction` disables both shared and residual rotation; initial placement still uses contact anchors. Moving cameras, changing terrain, initial airborne poses and accurate metric relative depth are outside this prototype's guarantees.

Combined FBX: one Scene root and namespaced `person_01:*`, `person_02:*` skeletons. Individual FBX: original Quinn bone names, identical shared-space transforms. All are skeleton-only, Y-up cm, full clip timing. Raw Hue motion.npz is retained. scene_source.npz stores corrected pre-retarget data. scene.json records transforms, source/target contact errors, common scale and tracking coverage. scene_preview.html uses a single common viewport.

Detector provenance: https://github.com/Megvii-BaseDetection/YOLOX/tree/main/demo/ONNXRuntime
YOLOX license: Apache-2.0, https://github.com/Megvii-BaseDetection/YOLOX/blob/main/LICENSE

## Streaming / long clips

`video.VideoFrames` is a repeatable iterable with integer frame access. Each sequential pass opens and releases its own decoder and reads frames in order. It applies the same resize/rotation contract as before. Detector, ViTPose, diagnostics and CHMR make separate passes; no full list of RGB rasters is retained. Hue keeps its existing context-window schedule, tested for complete/nonduplicated retained indices at 619, 1200 and 10000 frames. The FBX helper still has a 100000-frame sanity limit. Long clips cost proportionally more time and store proportional feature/pose/output data; there is no promise of constant total memory for arbitrarily long input.

HTML skeleton previews retain up to approximately 600 sampled frames and adjust playback FPS/source-frame labels. FBX, NPZ and diagnostic MP4 retain the full input frame range. Variable-FPS timestamps and camera motion remain unsupported.

## Reproducible setup

SetupStandalone.bat invokes the standard-library tools/bootstrap_setup.py under Python 3.13 x64. Interactive setup selects the UE folder with tkinter; the bundled Quinn skeleton removes the need for another FBX selection. The setup detects MSVC using vswhere, creates/reuses .venv, installs pinned requirements, stages and validates UE model extraction, builds all three helpers, downloads the pinned YOLOX model, then runs tests and doctor. Existing complete models are hash-checked and reused; differing existing model files are not silently overwritten. Extraction staging and explicit Quinn replacement backups stay under ignored work/. See README for prerequisites, exact source/destination paths and noninteractive flags.
