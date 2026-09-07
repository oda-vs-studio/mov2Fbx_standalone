"""Shared-camera placement and initial double-support floor calibration."""
from pathlib import Path
import json
import numpy as np
from scipy.spatial.transform import Rotation
from .export import PARENTS, prepare, forward_kinematics
from .retarget import ROOT, align_vector, load_skeleton, retarget_arrays, write_fbx


def global_rotations(local,parents):
    result=local.copy()
    for i,p in enumerate(parents):
        if p>=0:result[:,i]=result[:,p] @ local[:,i]
    return result


def rest_positions(offsets,parents):
    result=offsets.copy()
    for i,p in enumerate(parents):
        if p>=0:result[i]+=result[p]
    return result


def source_soles(world,global_r,offsets):
    # Virtual sole points: remove the neutral anatomical ankle/toe height.
    # Raw ankle and toe joints are at different heights and must NOT be plane-fit directly.
    rest=rest_positions(offsets,PARENTS)
    floor=min(rest[10,1],rest[11,1])-.02
    result=[]
    for joint,ankle in [(7,7),(10,7),(8,8),(11,8)]:
        result.append(world[:,joint]+np.einsum('fij,j->fi',global_r[:,ankle],[0.,floor-rest[joint,1],0.]))
    return np.stack(result,axis=1)


def fit_initial_floor(points,initial_frames):
    sample=np.median(points[:initial_frames],axis=0)
    centered=sample-sample.mean(axis=0)
    _,singular,vh=np.linalg.svd(centered,full_matrices=False)
    normal=vh[-1]
    if normal[1]<0:normal=-normal
    tilt=float(np.rad2deg(np.arccos(np.clip(normal[1],-1,1))))
    rms=float(np.sqrt(np.mean((centered@normal)**2)))
    reliable=bool(singular[1]>.04 and singular[2]/max(singular[1],1e-9)<.4 and tilt<40)
    return normal,dict(tilt_deg=tilt,plane_rms_m=rms,spread_m=singular.tolist(),reliable=reliable)


def stabilize_scene(actors,initial_frames=6,enabled=True):
    normals=[];fit=[];soles=[]
    for actor in actors:
        gr=global_rotations(actor['local'],PARENTS)
        points=source_soles(actor['world'],gr,actor['offsets'])
        normal,report=fit_initial_floor(points,initial_frames)
        normals.append(normal);fit.append(report);soles.append(points)
    accepted=[n for n,r in zip(normals,fit) if r['reliable']]
    normal=np.mean(accepted,axis=0) if accepted and enabled else np.array([0.,1.,0.])
    normal/=np.linalg.norm(normal)
    common=align_vector(normal,np.array([0.,1.,0.]))
    centers=[np.median((s@common.T)[:initial_frames].mean(axis=1),axis=0) for s in soles]
    origin=np.mean(centers,axis=0)
    reports=[]
    for actor,n,report,points,center in zip(actors,normals,fit,soles,centers):
        residual=align_vector(common@n,np.array([0.,1.,0.])) if enabled and report['reliable'] else np.eye(3)
        total=residual@common
        # Residual subject tilt is corrected around its initial contact center;
        # this does not move either person's horizontal scene anchor.
        translation=center-residual@center-origin
        translation[1]-=center[1]-origin[1]
        world=actor['world']@total.T+translation
        root=actor['root']@total.T+translation
        local=actor['local'].copy();local[:,0]=total@local[:,0]
        corrected_soles=points@total.T+translation
        anchor=center-origin;anchor[1]=0
        actor.update(local=local,root=root,world=world,anchor=anchor,soles=corrected_soles)
        reports.append({**report,'applied':bool(enabled and np.linalg.norm(total-np.eye(3))>1e-8),
            'residual_applied':bool(enabled and report['reliable']),
            'rotation_matrix':total.tolist(),'translation_m':translation.tolist(),
            'anchor_m':anchor.tolist(),'initial_sole_height_rms_m':float(np.sqrt(np.mean(corrected_soles[:initial_frames,:,1]**2)))})
    return dict(mode='initial double support; virtual sole plane; fixed camera',enabled=enabled,
                initial_frames=initial_frames,shared_rotation=common.tolist(),shared_origin_m=origin.tolist(),people=reports)


def forward_target(t,r,parents):
    world=t.copy();global_r=r.copy()
    for i,p in enumerate(parents):
        if p>=0:
            world[:,i]=world[:,p]+np.einsum('fij,fj->fi',global_r[:,p],t[:,i])
            global_r[:,i]=global_r[:,p]@r[:,i]
    return world,global_r


def target_soles(world,global_r,target):
    names=target['names'];out=[]
    for name in ['foot_l','ball_l','foot_r','ball_r']:
        i=names.index(name)
        offset=target['rot'][i].T@np.array([0.,-target['pos'][i,1],0.])
        out.append(world[:,i]+np.einsum('fij,j->fi',global_r[:,i],offset))
    return np.stack(out,axis=1)


def target_basis(target):
    idx={n:i for i,n in enumerate(target['names'])}
    left=target['pos'][idx['thigh_l']]-target['pos'][idx['thigh_r']]
    left[1]=0;left/=np.linalg.norm(left)
    return np.column_stack([left,[0,1,0],np.cross(left,[0,1,0])])


def combine_targets(target,animations):
    # The combined FBX uses namespaces; individual FBX files keep original bone names.
    names=['Scene'];parents=[-1];pos=[np.zeros(3)];rot=[np.eye(3)]
    frames=len(animations[0][0]);ts=[np.zeros((frames,1,3))];rs=[np.tile(np.eye(3),(frames,1,1,1))]
    for actor,(t,r) in enumerate(animations,1):
        offset=len(names)
        names.extend([f'person_{actor:02d}:{n}' for n in target['names']])
        parents.extend([p+offset if p>=0 else 0 for p in target['parents']])
        pos.extend(target['local_pos']);rot.extend(target['local_rot']);ts.append(t);rs.append(r)
    combined=dict(names=names,parents=np.array(parents),local_pos=np.array(pos),local_rot=np.array(rot))
    return combined,np.concatenate(ts,axis=1),np.concatenate(rs,axis=1)


def export_scene(runs,output,correct_tilt=True,initial_seconds=.2,camera_dir=None):
    output=Path(output);target=load_skeleton(ROOT/'models/quinn_skeleton.txt')
    body=np.load(ROOT/'models/skeleton.npz');actors=[];fps=None
    for run in map(Path,runs):
        motion=np.load(run/'motion.npz');meta=json.loads((run/'metadata.json').read_text())
        rotations,root,offsets,world=prepare(motion,body,meta,center=False)
        if fps is not None and (float(motion['fps'])!=fps or len(root)!=len(actors[0]['root'])):
            raise ValueError('Scene actors must share all frame timestamps')
        fps=float(motion['fps'])
        actors.append(dict(run=run,local=rotations.as_matrix().reshape(-1,55,3,3),root=root,offsets=offsets,world=world))
    camera_report=None
    if camera_dir is not None:
        from .moving_camera import world_actors
        actors,fps,camera_report=world_actors(runs,body,camera_dir)
    initial=max(1,min(len(actors[0]['root']),round(fps*initial_seconds)))
    report=stabilize_scene(actors,initial,correct_tilt)
    idx={n:i for i,n in enumerate(target['names'])}
    leg=sum(np.linalg.norm(target['pos'][idx[b]]-target['pos'][idx[a]]) for a,b in [('thigh_l','calf_l'),('calf_l','foot_l')])
    scale=leg/np.median([np.linalg.norm(a['offsets'][4])+np.linalg.norm(a['offsets'][7]) for a in actors])
    basis=target_basis(target);animations=[];worlds=[]
    for person,a in enumerate(actors,1):
        np.savez_compressed(a['run']/'scene_source.npz',positions_m=a['world'],root_m=a['root'],
            local_rotations=a['local'],offsets=a['offsets'],sole_points_m=a['soles'],fps=fps)
        t,r,w,retarget_report=retarget_arrays(a['local'],a['root'],a['offsets'],target,translation_scale=scale,floor_mode='none')
        w,gr=forward_target(t,r,target['parents']);sole=target_soles(w,gr,target)
        contact=np.median(sole[:initial].mean(axis=1),axis=0)
        desired=(basis@a['anchor'])*scale
        # Reference-proportion correction around the fixed world contact anchor.
        # Shift the whole skeleton, including its root and IK helpers, once.
        shift=desired-contact
        t[:,0]+=shift
        w,gr=forward_target(t,r,target['parents'])
        sole=target_soles(w,gr,target)
        actual=np.median(sole[:initial].mean(axis=1),axis=0)
        if np.linalg.norm(actual-desired)>1e-6:raise RuntimeError('Shared target contact anchor mismatch')
        a['target_report']={**retarget_report,'anchor_cm':actual.tolist(),'proportion_offset_cm':shift.tolist(),
            'initial_sole_height_rms_cm':float(np.sqrt(np.mean(sole[:initial,:,1]**2)))}
        np.savez_compressed(a['run']/'quinn_motion.npz',positions_cm=w,local_translations_cm=t,
                            local_rotations=r,parents=target['parents'],names=target['names'],fps=fps)
        (a['run']/'quinn_retarget.json').write_text(json.dumps(a['target_report'],indent=2),encoding='utf-8')
        write_fbx(a['run']/'quinn.fbx',target,t,r,fps,a['run'])
        animations.append((t,r));worlds.append(w)
    combined,ts,rs=combine_targets(target,animations)
    if len(actors)==1:write_fbx(output/'scene.fbx',target,*animations[0],fps,output)
    else:write_fbx(output/'scene.fbx',combined,ts,rs,fps,output)
    report.update(people_count=len(actors),fps=fps,frames=len(ts),shared_cm_per_m=float(scale),
        target_people=[a['target_report'] for a in actors],
        placement='Shared monocular camera coordinates; common scale and initial floor; metric distance remains estimated',
        limitations=['Fixed camera only; no camera-motion reconstruction','Initial two-foot contact is assumed',
                     'Virtual sole proxies, not a fitted mesh ground-contact solver','No per-frame foot lock or inter-person collision solve'])
    if camera_report is not None:
        report['camera']=camera_report
        report['quality_warnings']=[]
        report['motion_diagnostics']=[]
        for i,a in enumerate(actors,1):
            vertical=float(np.ptp(a['root'][:,1]))
            speed=float(np.linalg.norm(np.diff(a['root'],axis=0),axis=1).max()*fps)
            report['motion_diagnostics'].append(dict(person=i,vertical_range_m=vertical,max_root_speed_mps=speed))
            if vertical>2. or speed>12.:
                report['quality_warnings'].append(f'Person {i}: inferred vertical range {vertical:.2f} m, peak root speed {speed:.2f} m/s. Review camera/body drift and scale; FBX serialization success is not motion accuracy.')
        report['placement']='DA3 shared world coordinates; common estimated body/depth scale'
        report['mode']='initial double support after moving-camera world conversion'
        report['limitations'][0]='Experimental moving-camera solve; camera and body/depth alignment are estimated'
    (output/'scene.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    # Shared viewport, rather than independent recentered viewers.
    from .preview import write_preview
    wp,_=forward_target(ts,rs,combined['parents'])
    write_preview(output/'scene_preview.html',wp/100,fps,dict(start_frame=0),
                  parents=combined['parents'].tolist(),label='Quinn / shared scene',
                  hint='Shared estimated positions. Initial double-support correction. Drag to orbit.')
    return report


def solve_auto(video,output,models,provider='dml',correct_tilt=True,log=print,moving_camera=False,camera_model='DA3-LARGE'):
    from .pipeline import read_frames,calibrate,solve
    from .tracking import detect_tracks
    output=Path(output)
    if output.exists():raise FileExistsError(f'Run exists: {output}')
    output.mkdir(parents=True)
    camera_dir=output/'camera' if moving_camera else None
    if moving_camera:
        from .moving_camera import worker
        worker('rectify',camera_dir,video,camera_model)
        video=camera_dir/'rectified.avi'
    frames,fps=read_frames(video,0,None,0)
    tracks=detect_tracks(frames,fps,models,provider,output,log,allow_small_initial=moving_camera)
    if moving_camera:
        lens=json.loads((camera_dir/'lens.json').read_text())
        camera=(lens['K'][0][0],0.,0.)
        del frames
        worker('poses',camera_dir,model=camera_model)
    else:
        camera=calibrate(frames[0],models,provider)
        del frames
    camera_status=json.loads((camera_dir/'camera_report.json').read_text()) if moving_camera else None
    if camera_status and 'segments' in camera_status:
        from .track_intervals import prepare_intervals
        camera_status,tracking_skips=prepare_intervals(camera_status,tracks,camera_dir)
        exports=[];errors=[]
        for segment in camera_status['segments']:
            first,last=segment['start'],segment['end']
            folder=output if not camera_status['partial'] else output/'segments'/f"{segment['id']:03d}"
            folder.mkdir(parents=True,exist_ok=True)
            try:
                result=solve_range(video,folder,models,provider,camera,[tracks[i] for i in segment.get('track_indices',range(len(tracks)))],first,last,
                    camera_dir/segment['camera_dir'],correct_tilt,log)
                result.update(source_start_frame=first,source_end_frame_inclusive=last-1,
                    input_frames=camera_status['input_frames'],partial=camera_status['partial'])
                (folder/'scene.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
                exports.append(dict(directory=str(folder.relative_to(output)),start=first,end=last,people_count=result['people_count']))
            except Exception as exc:
                import traceback
                (folder/'ERROR.txt').write_text(traceback.format_exc(),encoding='utf-8')
                errors.append(dict(start=first,end=last,reason=str(exc)))
                log(f'SEGMENT FAILED {first}..{last-1}: {exc}; continuing')
        manifest=dict(partial=camera_status['partial'] or bool(errors),exports=exports,
            input_frames=camera_status['input_frames'],camera_skipped_ranges=camera_status['skipped_ranges'],
            camera_failures=camera_status['failures'],tracking_skipped_ranges=tracking_skips,segment_errors=errors,
            independent_world_origins=camera_status['partial'])
        (output/'segments_manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
        if not exports:raise ValueError('No segment completed body solve/export; see segments_manifest.json')
        return manifest
    selected_frames=camera_status['frames'] if camera_status else None
    runs=[]
    for i,t in enumerate(tracks,1):
        run=output/f'person_{i:02d}'
        log(f'Capturing person {i}/{len(tracks)}')
        solve(video,run,models,provider=provider,camera=camera,track_boxes=t['boxes'][:selected_frames],end=selected_frames-1 if selected_frames else None,log=log)
        if moving_camera:
            metadata=json.loads((run/'metadata.json').read_text())
            metadata['moving_camera']='../camera/trajectory.npz; applied at shared scene export'
            metadata['limitations']=[x for x in metadata['limitations'] if x!='Camera estimated on first selected frame']
            metadata['limitations'].append('Hue zero camera angular input; explicit DA3 world conversion follows')
            (run/'metadata.json').write_text(json.dumps(metadata,indent=2),encoding='utf-8')
        runs.append(run)
    report=export_scene(runs,output,correct_tilt,camera_dir=camera_dir)
    if camera_status is not None:
        report['partial']=camera_status['partial']
        report['source_start_frame']=0
        report['source_end_frame_inclusive']=selected_frames-1
        report['input_frames']=camera_status['input_frames']
        report['camera_stop_reason']=camera_status['failure']
    report['tracking']=[dict(id=t['id'],coverage=float(t['observed'][:selected_frames].mean()),interpolated_frames=int((~t['observed'][:selected_frames]).sum())) for t in tracks]
    (output/'scene.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    for i,p in enumerate(report['people'],1):
        status='applied' if p['residual_applied'] else 'disabled or unreliable; no subject residual correction'
        log(f'Initial foot plane person {i}: {p["tilt_deg"]:.2f} degrees, {status}')
    for warning in report.get('quality_warnings',[]):log('QUALITY REVIEW: '+warning)
    log(f'Scene complete: {len(tracks)} person(s), shared positions')
    return report


def solve_range(video,output,models,provider,camera,tracks,first,last,camera_dir,correct_tilt,log):
    """All people use exactly the same source timestamps within one camera world."""
    from .pipeline import solve
    runs=[]
    for i,track in enumerate(tracks,1):
        run=output/f'person_{i:02d}'
        log(f'Segment {first}..{last-1}: person {i}/{len(tracks)}')
        solve(video,run,models,provider=provider,camera=camera,start=first,end=last-1,
            track_boxes=track['boxes'][first:last],log=log)
        metadata=json.loads((run/'metadata.json').read_text())
        metadata['moving_camera']=str(camera_dir/'trajectory.npz')
        metadata['limitations']=[x for x in metadata['limitations'] if x!='Camera estimated on first selected frame']
        metadata['limitations'].append('Hue zero camera angular input; independent segment world conversion follows')
        (run/'metadata.json').write_text(json.dumps(metadata,indent=2),encoding='utf-8')
        runs.append(run)
    report=export_scene(runs,output,correct_tilt,camera_dir=camera_dir)
    report['tracking']=[dict(id=t['id'],coverage=float(t['observed'][first:last].mean()),
        interpolated_frames=int((~t['observed'][first:last]).sum())) for t in tracks]
    for warning in report.get('quality_warnings',[]):log('QUALITY REVIEW: '+warning)
    return report
