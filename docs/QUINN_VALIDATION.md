# Quinn retarget validation

Input skeleton: C:\temp\SKM_Quinn_Simple.FBX (SHA256 in models/quinn_manifest.json).
Extracted 89 skeleton nodes; geometry is not exported. Reference global positions and rotations survive extraction and FBX serialization within 1e-6 cm / 1e-7 matrix element tolerance. Original bone names and parent indices match.

Nine unit/integration tests pass, including synthetic animated bone lengths, reference-axis direction transfer, horizontal root travel, IK helper positions, reference FBX re-extraction, and animated FBX SDK roundtrip at 29.97 fps.

The actual DropVideoToQuinnFBX.bat completed MiniMax_H3_00016_.mp4: 124 frames, 24 fps, 89 bones. The generated MiniMax_H3_00016_.fbx is beside the original video. FBX SDK roundtrip maximum local matrix error: 0. The existing-file guard returns failure and leaves the existing FBX SHA256 unchanged.

Four sampled source/target skeleton poses were visually compared (frames 0, 40, 80, 123). Main limb motion follows the source with Quinn proportions. This is a skeleton/transform check; no skinned character or Unreal import was validated. FK retargeting retains fixed twist offsets and does not provide contact foot locking.

Run: runs/drop/20260905_161022_6511940e
