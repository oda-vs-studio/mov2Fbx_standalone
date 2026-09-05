# Auto scene and streaming validation

Validated on this PC with DirectML pose inference and CPU final Hue stage.

| Input | Frames | People | Observed tracking coverage | Initial tilt estimates (degrees) |
| --- | ---: | ---: | --- | --- |
| MiniMax_H3_00025_.mp4 | 124 | 2 | 1.0, 1.0 | 14.93, 22.84 |
| MiniMax_H3_00023_.mp4 | 124 | 2 | 1.0, 1.0 | 29.09, 35.33 |
| MiniMax_H3_00024_.mp4 | 124 | 2 | 1.0, 1.0 | 14.26, 21.74 |
| MiniMax_H3_00011_.mp4 | 124 | 1 | 1.0 | 11.63 |
| validation619.mp4 | 619 | 1 | 1.0 | 4.37 |

The 619-frame integration clip is a derived test clip: each frame of the supplied 00016 video was repeated five times, ending at frame 619. It is not a claim that the user's unidentified 619-frame input has been tested.

All combined and individual FBX files passed SDK re-import with maximum local-matrix error 0. Paired files contain 179 bones including the shared Scene root; individuals contain the original 89 Quinn bones. The 619-frame FBX contains all 619 samples at 24 fps.

The three two-person clips retained both IDs in every frame, without interpolation. Fourteen tests pass: known floor tilt removal while preserving later bends, 1.6-metre inter-person anchor separation, common-scale transforms, two-person FBX serialization, crossing synthetic tracks, rejection of long disappearance, streaming 619-frame decode, repeated/ranged/rotated decode and the prior core/retarget tests. Temporal-window coverage also passes 1200 and 10000 frames (geometry tests, not full inference).

The first 00025 pose was visually compared before/after correction and against the input video. The backward pitch was reduced, and the two-person front-view layout was retained. Initial target virtual-sole RMS heights for that clip were approximately 1.59 and 1.81 cm. These are proxy errors, not measured mesh/physical floor errors.

No ground-truth camera/scene measurement, UE import, skinned-mesh validation, moving-camera reconstruction or difficult real occlusion/re-identification evaluation has been performed. Shared positions remain monocular estimates.

Run folders:
- runs/drop/20260905_180919_8adcad50
- runs/drop/20260905_181221_eb4c2308
- runs/drop/20260905_181325_33b0e4cf
- runs/drop/20260905_181427_4d3a22b8
- runs/drop/20260905_181735_63fa51d6
