"""Shared moving-camera preparation and explicit pre-retarget world conversion."""
from pathlib import Path
import json
import subprocess
import os
import numpy as np
from scipy.spatial.transform import Rotation
from .camera_math import transform_body, validate_poses
from .export import PARENTS, forward_kinematics
from .retarget import ROOT, align_vector


def worker(stage, output, video=None, model='DA3-LARGE'):
    python=ROOT/'.venv-camera/Scripts/python.exe'
    if not python.exists(): raise FileNotFoundError('Run SetupMovie2Anim.bat first')
    args=[str(python),'-u','-m','tools.camera_worker',stage,'--output',str(output),'--model',model]
    if video is not None:args+=['--video',str(video)]
    env=os.environ.copy();env.update(PYTHONUTF8='1',OMP_NUM_THREADS='8',OPENBLAS_NUM_THREADS='8',MKL_NUM_THREADS='8')
    subprocess.run(args,cwd=ROOT,check=True,env=env)


def world_actors(runs,body,camera_dir):
    camera_dir=Path(camera_dir)
    camera=np.load(camera_dir/'trajectory.npz')
    w2c=validate_poses(camera['w2c']);k=camera['K'];cw,ch=camera['size']
    actors=[];ratios=[]
    for run in map(Path,runs):
        motion=np.load(run/'motion.npz');feat=np.load(run/'features.npz')
        if len(motion['poses'])!=len(w2c) or not np.isclose(float(motion['fps']),float(camera['fps'])):
            raise ValueError('Body and camera must have identical frame range and FPS')
        joints=body['joints']+np.einsum('jck,k->jc',body['shape_deltas'],motion['betas'].mean(0))
        offsets=joints.copy();offsets[1:]-=joints[np.array(PARENTS[1:])]
        root=motion['translations']+joints[0]
        local=Rotation.from_rotvec(motion['poses'].reshape(-1,3)).as_matrix().reshape(-1,55,3,3)
        ow,oh=feat['size']
        for i in np.unique(np.linspace(0,len(root)-1,min(40,len(root))).astype(int)):
            points=feat['keypoints'][i,[5,6,11,12]]
            if np.min(points[:,2])<.5 or root[i,2]<=0:continue
            uv=points[:,:2].mean(0)*[cw/ow,ch/oh]
            x,y=np.rint(uv).astype(int)
            depth=np.load(camera_dir/'depth'/f'{i:06d}.npz')['depth']
            patch=depth[max(0,y-2):min(ch,y+3),max(0,x-2):min(cw,x+3)]
            good=patch[np.isfinite(patch)&(patch>0)]
            if len(good)>=4:ratios.append(float(root[i,2]/np.median(good)))
        actors.append(dict(run=run,local=local,root=root,offsets=offsets))
    if len(ratios)<4:raise ValueError('Insufficient torso depth evidence to align camera/body scale')
    scale=float(np.median(ratios));spread=float(np.median(np.abs(np.array(ratios)-scale))/scale)
    if spread>.5:raise ValueError('Camera/body scale inconsistent; cannot place actors reliably')
    up=align_vector(camera['up_world'],np.array([0.,1.,0.]))
    for a in actors:
        a['local'],a['root']=transform_body(a['local'],a['root'],w2c,scale,up)
        a['world']=forward_kinematics(Rotation.from_matrix(a['local'].reshape(-1,3,3)),a['root'],a['offsets'])
    report=dict(mode='DA3 moving camera; fixed shared GeoCalib lens',camera_units_to_body_m=scale,
                scale_relative_mad=spread,scale_samples=len(ratios),up_rotation=up.tolist(),
                limitations=['Hue runs with zero CamAngvel; its output is treated as camera-relative before explicit world conversion',
                'Body/depth scale uses torso surface as pelvis-depth proxy; absolute metres remain approximate',
                'No joint body-camera optimization or foot locking'])
    (camera_dir/'body_alignment.json').write_text(json.dumps(report,indent=2))
    return actors,float(camera['fps']),report
