from pathlib import Path
import json
import subprocess
import numpy as np
from scipy.spatial.transform import Rotation

PARENTS = [-1,0,0,0,1,2,3,4,5,6,7,8,9,9,9,12,13,14,16,17,18,19,15,15,15,20,25,26,20,28,29,20,31,32,20,34,35,20,37,38,21,40,41,21,43,44,21,46,47,21,49,50,21,52,53]
NAMES = ['pelvis','left_hip','right_hip','spine1','left_knee','right_knee','spine2','left_ankle','right_ankle','spine3','left_foot','right_foot','neck','left_collar','right_collar','head','left_shoulder','right_shoulder','left_elbow','right_elbow','left_wrist','right_wrist','jaw','left_eye','right_eye'] + [f'{side}_{finger}{i}' for side in ['left','right'] for finger in ['index','middle','pinky','ring','thumb'] for i in [1,2,3]]


def forward_kinematics(rotations, root, offsets):
    n = len(root)
    world = np.zeros((n,55,3),dtype=np.float64)
    matrices = rotations.as_matrix().reshape(n,55,3,3)
    global_rot = matrices.copy()
    world[:,0] = root
    for i, parent in enumerate(PARENTS[1:],1):
        global_rot[:,i] = global_rot[:,parent] @ matrices[:,i]
        world[:,i] = world[:,parent] + np.einsum('nij,j->ni',global_rot[:,parent],offsets[i])
    return world


def prepare(motion, skeleton, metadata, center=True):
    pose = motion['poses'].reshape(-1,55,3).copy()
    betas = motion['betas'].mean(axis=0)
    joints = skeleton['joints'] + np.einsum('jck,k->jc',skeleton['shape_deltas'],betas)
    offsets = joints.copy()
    offsets[1:] -= joints[np.array(PARENTS[1:])]
    # Same camera orientation/axis flip as UE ApplyHps. Floor uses joints, not skinned vertices.
    camera = Rotation.from_rotvec([-metadata['camera_pitch'],0,0]) * Rotation.from_rotvec([0,metadata['camera_roll'],0])
    conversion = Rotation.from_matrix(np.diag([1.,-1.,-1.])) * camera
    pose[:,0] = (conversion * Rotation.from_rotvec(pose[:,0])).as_rotvec()
    root = conversion.apply(motion['translations'] + joints[0])
    rotations = Rotation.from_rotvec(pose.reshape(-1,3))
    world = forward_kinematics(rotations,root,offsets)
    # Keep jumps and translation; place lowest foot/ankle joint on floor globally.
    if not center:
        return rotations, root, offsets, world
    floor = float(world[:,[7,8,10,11],1].min())
    origin = np.array([root[0,0],floor,root[0,2]])
    root -= origin
    world -= origin
    return rotations, root, offsets, world


def write_bvh(path, rotations, root, offsets, fps):
    order, lines = [], ['HIERARCHY']
    def node(i,depth):
        indent = '  '*depth
        lines.extend([indent+('ROOT ' if i == 0 else 'JOINT ')+NAMES[i],indent+'{'])
        offset = np.zeros(3) if i == 0 else offsets[i]*100
        lines.append(indent+'  OFFSET '+' '.join(f'{v:.9f}' for v in offset))
        lines.append(indent+('  CHANNELS 6 Xposition Yposition Zposition Zrotation Xrotation Yrotation' if i == 0 else '  CHANNELS 3 Zrotation Xrotation Yrotation'))
        order.append(i)
        children = [j for j,p in enumerate(PARENTS) if p == i]
        for child in children:
            node(child,depth+1)
        if not children:
            lines.extend([indent+'  End Site',indent+'  {',indent+'    OFFSET 0 0 0',indent+'  }'])
        lines.append(indent+'}')
    node(0,0)
    euler = rotations.as_euler('ZXY',degrees=True).reshape(len(root),55,3)
    lines += ['MOTION',f'Frames: {len(root)}',f'Frame Time: {1/fps:.12f}']
    for frame in range(len(root)):
        values = np.r_[root[frame]*100,euler[frame,order].reshape(-1)]
        lines.append(' '.join(f'{v:.9f}' for v in values))
    path.write_text('\n'.join(lines)+'\n',encoding='ascii')


def export_motion(output, models):
    output, models = Path(output), Path(models)
    motion = np.load(output/'motion.npz')
    skeleton = np.load(models/'skeleton.npz')
    metadata = json.loads((output/'metadata.json').read_text(encoding='utf-8'))
    rotations, root, offsets, world = prepare(motion,skeleton,metadata)
    fps = float(motion['fps'])
    write_bvh(output/'motion.bvh',rotations,root,offsets,fps)
    np.savez_compressed(output/'world_motion.npz',joints=world,root=root,offsets=offsets,quaternions_xyzw=rotations.as_quat().reshape(-1,55,4),fps=fps)
    helper = Path(__file__).resolve().parent.parent/'bin/fbx_export.exe'
    if helper.exists():
        intermediate = output/'fbx_input.txt'
        euler = rotations.as_euler('xyz',degrees=True).reshape(len(root),55,3)
        with intermediate.open('w',encoding='ascii') as f:
            f.write(f'55 {len(root)} {fps:.12f}\n')
            for i in range(55):
                f.write(f'{NAMES[i]} {PARENTS[i]} '+' '.join(map(str,offsets[i]*100))+'\n')
            for frame in range(len(root)):
                f.write(' '.join(map(str,np.r_[root[frame]*100,euler[frame].reshape(-1)]))+'\n')
        result = subprocess.run([str(helper),str(intermediate.resolve()),str((output/'motion.fbx').resolve())],capture_output=True,text=True,check=True)
        (output/'fbx_validation.txt').write_text(result.stdout,encoding='utf-8')
    from .preview import write_preview
    write_preview(output/'preview.html',world,fps,metadata)
    metadata['export'] = dict(skeleton='SMPL-X 55 joints (not Manny)',up_axis='Y',unit='cm in BVH/FBX; metres in NPZ',floor='global minimum ankle/foot joint; not mesh contact',fbx=helper.exists())
    (output/'metadata.json').write_text(json.dumps(metadata,indent=2),encoding='utf-8')
    (output/'SUCCESS').write_text('Standalone inference and export completed\n',encoding='ascii')
    print('Exported',output,flush=True)
