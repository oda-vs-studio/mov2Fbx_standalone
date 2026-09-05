"""Reference-axis-aware FK retargeting onto the supplied Quinn skeleton."""
from pathlib import Path
import json
import shlex
import subprocess
import warnings
import numpy as np
from scipy.spatial.transform import Rotation
from .export import NAMES, PARENTS, prepare

ROOT = Path(__file__).resolve().parents[1]


def load_skeleton(path):
    lines = Path(path).read_text(encoding='utf-8').splitlines()
    rows = [shlex.split(line) for line in lines[1:]]
    if len(rows) != int(lines[0]):
        raise ValueError('Invalid skeleton count')
    names = [r[0] for r in rows]
    parents = np.array([int(r[1]) for r in rows])
    data = np.array([[float(x) for x in r[2:]] for r in rows])
    if len(set(names)) != len(names) or not np.isfinite(data).all():
        raise ValueError('Duplicate names or invalid reference transforms')
    if not np.allclose(data[:, 7:10], 1, atol=1e-5):
        raise ValueError('Scaled skeletons are unsupported; apply scale before export')
    if parents[0] != -1 or any(p < 0 or p >= i for i, p in enumerate(parents[1:], 1)):
        raise ValueError('Expected one skeleton root in parent-first order')
    pos = data[:, :3]
    rot = Rotation.from_quat(data[:, 3:7]).as_matrix()
    local_pos, local_rot = pos.copy(), rot.copy()
    for i, p in enumerate(parents):
        if p >= 0:
            local_pos[i] = rot[p].T @ (pos[i]-pos[p])
            local_rot[i] = rot[p].T @ rot[i]
    return dict(names=names, parents=parents, pos=pos, rot=rot,
                local_pos=local_pos, local_rot=local_rot)


def align_vector(a, b):
    a, b = a/np.linalg.norm(a), b/np.linalg.norm(b)
    v, d = np.cross(a, b), np.clip(np.dot(a, b), -1, 1)
    if d < -0.999999:
        axis = np.cross(a, np.eye(3)[np.argmin(np.abs(a))])
        return Rotation.from_rotvec(axis/np.linalg.norm(axis)*np.pi).as_matrix()
    if np.linalg.norm(v) < 1e-10:
        return np.eye(3)
    return Rotation.from_rotvec(v/np.linalg.norm(v)*np.arctan2(np.linalg.norm(v), d)).as_matrix()


def mapping():
    pairs = {'pelvis':'pelvis','spine_01':'spine1','spine_02':'spine1',
             'spine_03':'spine2','spine_04':'spine3','spine_05':'spine3',
             'neck_01':'neck','neck_02':'neck','head':'head'}
    for suffix, side in [('l','left'),('r','right')]:
        for t, s in [('thigh','hip'),('calf','knee'),('foot','ankle'),('ball','foot'),
                     ('clavicle','collar'),('upperarm','shoulder'),('lowerarm','elbow'),('hand','wrist')]:
            pairs[f'{t}_{suffix}'] = f'{side}_{s}'
        for finger in ['index','middle','ring','pinky','thumb']:
            for k in range(1, 4):
                pairs[f'{finger}_{k:02d}_{suffix}'] = f'{side}_{finger}{k}'
    return pairs


def retarget_arrays(source_local, source_root, source_offsets, target, translation_scale=None, floor_mode="global_min"):
    names, parents, rest, rest_r = (target[k] for k in ['names','parents','pos','rot'])
    index = {n:i for i,n in enumerate(names)}
    pairs = {index[n]:NAMES.index(s) for n,s in mapping().items() if n in index}
    for required in ['root','pelvis','thigh_l','calf_l','foot_l','thigh_r','calf_r','foot_r','head']:
        if required not in index:
            raise ValueError(f'Missing Quinn bone: {required}')
    # Target left/right axis and vertical define its canonical facing direction.
    left = rest[index['thigh_l']] - rest[index['thigh_r']]
    left[1] = 0
    left /= np.linalg.norm(left)
    up = np.array([0.,1.,0.])
    basis = np.column_stack([left, up, np.cross(left, up)])
    sg = source_local.copy()
    for i, p in enumerate(PARENTS[1:], 1):
        sg[:, i] = sg[:, p] @ source_local[:, i]
    # A-pose to SMPL-X T-pose calibration: align each primary outgoing bone.
    next_target = {'pelvis':'spine_01','spine_01':'spine_02','spine_02':'spine_03',
                   'spine_03':'spine_04','spine_04':'spine_05','spine_05':'neck_01',
                   'neck_01':'neck_02','neck_02':'head'}
    next_source = {0:3,3:6,6:9,9:12,12:15}
    for suffix in ['l','r']:
        for a,b in [('thigh','calf'),('calf','foot'),('foot','ball'),('clavicle','upperarm'),
                    ('upperarm','lowerarm'),('lowerarm','hand'),('hand','middle_01')]:
            next_target[f'{a}_{suffix}'] = f'{b}_{suffix}'
        for finger in ['index','middle','ring','pinky','thumb']:
            for k in [1,2]: next_target[f'{finger}_{k:02d}_{suffix}'] = f'{finger}_{k+1:02d}_{suffix}'
    for a,b in [(1,4),(4,7),(7,10),(2,5),(5,8),(8,11),(13,16),(16,18),(18,20),
                (14,17),(17,19),(19,21),(20,28),(21,43)]: next_source[a]=b
    for base in range(25,55,3): next_source[base]=base+1; next_source[base+1]=base+2
    correction = {}
    direction_checks = []
    for i, si in pairs.items():
        child_name = next_target.get(names[i])
        if child_name in index and si in next_source:
            j, sj = index[child_name], next_source[si]
            # Some target paths include a metacarpal; use endpoint displacement.
            source_rest = np.zeros((55,3))
            source_rest[0] = source_offsets[0]
            for k,p in enumerate(PARENTS[1:],1): source_rest[k] = source_rest[p]+source_offsets[k]
            sv = basis @ (source_rest[sj]-source_rest[si])
            correction[i] = align_vector(rest[j]-rest[i], sv) @ rest_r[i]
            if parents[j] == i:
                direction_checks.append((i,j,si,sv/np.linalg.norm(sv)))
        else:
            # End bones retain the parent's reference-axis calibration.
            p = parents[i]
            correction[i] = correction.get(p,rest_r[p]) @ rest_r[p].T @ rest_r[i] if p >= 0 else rest_r[i]
    f, n = len(source_root), len(names)
    local_t = np.broadcast_to(target['local_pos'],(f,n,3)).copy()
    local_r = np.broadcast_to(target['local_rot'],(f,n,3,3)).copy()
    world_t, world_r = np.zeros_like(local_t), np.zeros_like(local_r)
    target_leg = sum(np.linalg.norm(rest[index[b]]-rest[index[a]]) for a,b in [('thigh_l','calf_l'),('calf_l','foot_l')])
    scale = target_leg / (np.linalg.norm(source_offsets[4])+np.linalg.norm(source_offsets[7]))
    if translation_scale is not None:
        scale = float(translation_scale)
    hip_world = (source_root @ basis.T)*scale
    for i,p in enumerate(parents):
        if i == index['root']:
            local_t[:,i] = hip_world * [1,0,1]
        if i in pairs:
            desired = basis @ sg[:,pairs[i]] @ basis.T @ correction[i]
            local_r[:,i] = np.swapaxes(world_r[:,p],-1,-2) @ desired if p>=0 else desired
        if names[i] == 'pelvis':
            local_t[:,i] = np.einsum('fij,fj->fi',np.swapaxes(world_r[:,p],-1,-2),hip_world-world_t[:,p])
        world_r[:,i] = world_r[:,p] @ local_r[:,i] if p>=0 else local_r[:,i]
        world_t[:,i] = world_t[:,p]+np.einsum('fij,fj->fi',world_r[:,p],local_t[:,i]) if p>=0 else local_t[:,i]
    # One constant floor adjustment retains jumps. No foot locking or IK solve.
    floor = world_t[:,[index[x] for x in ['foot_l','foot_r','ball_l','ball_r']],1].min() if floor_mode == 'global_min' else 0.
    pi=index['pelvis']; p=parents[pi]
    local_t[:,pi] -= np.einsum('fij,j->fi',np.swapaxes(world_r[:,p],-1,-2),[0,floor,0])
    followers={'ik_foot_l':'foot_l','ik_foot_r':'foot_r','ik_hand_gun':'hand_r',
               'ik_hand_l':'hand_l','ik_hand_r':'hand_r','center_of_mass':'pelvis'}
    for i,p in enumerate(parents):
        if names[i] in followers:
            j=index[followers[names[i]]]
            local_t[:,i]=np.einsum('fij,fj->fi',np.swapaxes(world_r[:,p],-1,-2),world_t[:,j]-world_t[:,p])
            local_r[:,i]=np.swapaxes(world_r[:,p],-1,-2) @ world_r[:,j]
        world_r[:,i]=world_r[:,p] @ local_r[:,i] if p>=0 else local_r[:,i]
        world_t[:,i]=world_t[:,p]+np.einsum('fij,fj->fi',world_r[:,p],local_t[:,i]) if p>=0 else local_t[:,i]
    if not np.isfinite(local_t).all() or not np.isfinite(local_r).all(): raise ValueError('Nonfinite retarget output')
    errors=[]
    for i,j,si,v in direction_checks:
        expected=np.einsum('fij,j->fi',basis @ sg[:,si] @ basis.T,v)
        actual=world_t[:,j]-world_t[:,i]; actual/=np.linalg.norm(actual,axis=1)[:,None]
        errors.append(float(np.max(np.linalg.norm(actual-expected,axis=1))))
    error=max(errors,default=0.)
    if error>1e-5: raise ValueError(f'Retarget direction mismatch {error}')
    return local_t,local_r,world_t,dict(mapped=len(pairs),bones=n,translation_cm_per_m=scale,
        direction_max_error=error,method='reference-axis calibrated FK; fixed twist offsets; IK helper followers; no foot locking')


def write_fbx(path,target,translations,rotations,fps,work):
    path,work=Path(path),Path(work)
    with warnings.catch_warnings():
        warnings.simplefilter('ignore',UserWarning)
        euler=Rotation.from_matrix(rotations.reshape(-1,3,3)).as_euler('xyz',degrees=False).reshape(*translations.shape)
        euler=np.rad2deg(np.unwrap(euler,axis=0))
        rest_euler=Rotation.from_matrix(target['local_rot']).as_euler('xyz',degrees=True)
    text_path=work/(path.stem+'_fbx_input.txt')
    with text_path.open('w',encoding='ascii') as stream:
        stream.write(f'{len(target["names"])} {len(translations)} {fps:.12f}\n')
        for i,name in enumerate(target['names']):
            if not name.isascii() or any(x.isspace() for x in name): raise ValueError('Unsupported bone name')
            stream.write(f'{name} {target["parents"][i]} '+ ' '.join(map(str,np.r_[target['local_pos'][i],rest_euler[i]]))+'\n')
        for t,r in zip(translations,euler): stream.write(' '.join(map(str,np.concatenate([t,r],axis=-1).ravel()))+'\n')
    result=subprocess.run([str(ROOT/'bin/fbx_retarget.exe'),str(text_path),str(path)],capture_output=True,text=True,check=True)
    (work/(path.stem+'_fbx_validation.txt')).write_text(result.stdout,encoding='utf-8')
    print(result.stdout.strip(),flush=True)


def export_retarget(run,output,skeleton=None):
    run=Path(run); skeleton=Path(skeleton or ROOT/'models/quinn_skeleton.txt')
    target=load_skeleton(skeleton)
    motion=np.load(run/'motion.npz'); body=np.load(ROOT/'models/skeleton.npz')
    metadata=json.loads((run/'metadata.json').read_text(encoding='utf-8'))
    rotations,root,offsets,_=prepare(motion,body,metadata)
    t,r,world,report=retarget_arrays(rotations.as_matrix().reshape(-1,55,3,3),root,offsets,target)
    write_fbx(output,target,t,r,float(motion['fps']),run)
    np.savez_compressed(run/'quinn_motion.npz',positions_cm=world,local_translations_cm=t,
        local_rotations=r,parents=target['parents'],names=target['names'],fps=motion['fps'])
    (run/'quinn_retarget.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    return report
