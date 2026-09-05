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

The inference models, body data and SDK originate from the local installation. They are not committed to this repository. Original Epic/Autodesk assets retain their attribution; extraction manifests identify source files.

## Model extraction

The extractor supports the installed uncooked UE 5.8 NNE layout. It identifies a single ONNX FileData payload using the serialized file type, validates length, copies data in bounded chunks, and reads additional arrays. Unknown layouts and path traversal are rejected.
ViTPose has >2 GB of external data. The UE descriptor maps tensor filenames to slices of one byte array. The extracted ONNX graph references these slices directly in `OnnxExternalDataBytes`, avoiding a second 2.5 GB copy.

The skeleton extractor validates tagged array IDs and lengths for this asset version, then computes joint rest positions and the first ten shape deltas. It is intentionally version-specific and fails on incompatible assets.

## Coordinate contract

`motion.npz` is the raw Hue result. `world_motion.npz` applies the camera correction and Y/Z flip to root rotation and position, regresses the skeleton from mean shape, and normalizes first-frame X/Z plus the global minimum ankle/foot Y. Child rotations remain in SMPL-X local axes.
Positions in NPZ use metres. FBX/BVH convert positions to centimetres. BVH uses intrinsic ZXY Euler channels. FBX uses the SDK's XYZ Euler order.

The FBX helper reloads its exported file and compares all 4x4 local transforms at every sampled frame. This checks serialization, hierarchy and curve evaluation; it does not establish that the inferred pose matches the original actor or the UE pipeline.

## Two-person mode

Both people share camera calibration and frame range but are inferred independently inside explicit static ROIs. Each person gets an independent motion directory and success marker. The parent success marker is written only after both exports finish. The paired HTML preview uses `postMessage` to synchronize its two frames and works with local files.

There is no coupled interaction model, collision/occlusion solve, automatic ID association, or guaranteed common spatial scale. Each output is independently centered.

## Resource and failure behavior

Models are loaded by stage and released before later stages. Hue windows retain overlap; the final model runs on CPU. The input length is bounded to 600 frames because decoded rasters are held in memory. GPU work has CPU provider fallback inside ONNX Runtime; device selection is not a claim that every operator ran on GPU.
Existing output directories are rejected. Partial runs remain inspectable. GUI cancellation terminates only its own Python child, and completion is gated on exit code plus `SUCCESS`.
