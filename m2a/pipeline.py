"""Editor-free ViTPose -> CHMR -> Hue inference. Explicit single-person ROI."""
from pathlib import Path
import gc
import json
import time
import cv2
import numpy as np
from .runtime import Model
from .geometry import adjusted_size, preprocess, hue_inputs, temporal_windows

PROMPT_IDS = [0,2,1,6,8,10,5,7,9,12,14,16,11,13,15,17,19,20,22]


from .video import read_frames


def calibrate(frame, models, provider):
    wh = adjusted_size(frame)
    size = (wh * (320 / wh.min())).astype(int)
    size = size // 32 * 32
    scale = wh.min()/320
    crop_size = (size*scale).astype(int)
    crop_min = (wh-crop_size)//2
    sigma = max(float(np.max((wh/size-1)/2)), .001)
    kernel = max(int(4*sigma), 3)
    kernel += 1-kernel%2
    smoothed = cv2.GaussianBlur(frame.astype(np.float32)/255, (kernel,kernel), sigma, borderType=cv2.BORDER_REPLICATE)
    data, _, _ = preprocess(smoothed, tuple(size), [*crop_min, *(wh-crop_min)], 1., False)
    model = Model(models, 'camera_calib', provider)
    result = model(data)[0].reshape(-1)
    return float(result[0]*scale), float(result[1]), float(result[2])


def solve(video, output, models, start=0, end=None, rotation=0, roi=None, provider='cpu', focal=None, height=0., seed=42, log=print, cancel=lambda:False, camera=None, track_boxes=None):
    began = time.perf_counter()
    output = Path(output)
    if output.exists():
        raise FileExistsError(f'Output directory already exists: {output}; choose a new name')
    output.mkdir(parents=True)
    def progress(message):
        if cancel():
            raise InterruptedError('Cancelled between inference calls')
        log(message)
    progress('Decoding video')
    frames, fps = read_frames(video, start, end, rotation)
    n = len(frames)
    if n < 12:
        raise ValueError('Use at least 12 frames for temporal inference')
    wh = adjusted_size(frames[0])
    box = np.array([0,0,*wh] if roi is None else roi, dtype=np.float32)
    boxes = np.repeat(box[None], n, axis=0) if track_boxes is None else np.asarray(track_boxes,dtype=np.float32)
    if boxes.shape != (n,4) or not np.isfinite(boxes).all():
        raise ValueError('Tracking boxes must contain one valid box per frame')
    if not ((boxes[:,:2]>=0).all() and (boxes[:,2:]<=wh).all() and (boxes[:,2:]>boxes[:,:2]).all()):
        raise ValueError('ROI must fit the adjusted video raster')
    pitch = roll = 0.
    if camera is not None:
        focal,pitch,roll = camera
    elif focal is None:
        progress('Estimating camera on first selected frame')
        focal, pitch, roll = calibrate(frames[0], models, provider)
        gc.collect()
    if not np.isfinite(focal) or focal <= 0:
        raise ValueError('Camera focal length must be positive')
    progress(f'Camera focal={focal:.2f}px; loading ViTPose')
    pose_model = Model(models, 'ViTPose', provider)
    post = Model(models, 'ViTPosePost', 'cpu')
    keypoints = []
    for i, frame in enumerate(frames):
        progress(f'2D pose {i+1}/{n}')
        tensor, scale, offset = preprocess(frame, (192,256), boxes[i], .5)
        points = post(pose_model(tensor)[0])[0].reshape(133,3)
        points[:, :2] = points[:, :2] * (np.array([192,256])*scale).astype(int) / [47,63] + offset
        keypoints.append(points)
    del pose_model, post
    gc.collect()
    keypoints = np.array(keypoints)
    # Save visible evidence of which person/joints the model followed.
    writer = cv2.VideoWriter(str(output/'keypoints.mp4'),cv2.VideoWriter_fourcc(*'mp4v'),fps,tuple(wh))
    if not writer.isOpened():
        raise RuntimeError('Cannot create keypoint diagnostic video')
    try:
        for frame,points,box in zip(frames,keypoints,boxes):
            overlay = frame.copy()
            cv2.rectangle(overlay,tuple(box[:2].astype(int)),tuple(box[2:].astype(int)),(255,180,0),2)
            for x,y,confidence in points[:23]:
                if confidence > .2:
                    cv2.circle(overlay,(round(float(x)),round(float(y))),3,(0,255,120),-1)
            writer.write(overlay)
    finally:
        writer.release()
    # An explicit ROI is used instead of porting Detectron2/SAM2 in this prototype.
    good = (keypoints[:, :17, 2] > .2).sum(axis=1) >= 5
    if not good.all():
        raise ValueError(f'{(~good).sum()} frames have insufficient visible body joints; tighten ROI or change range')
    progress('Loading CHMR')
    backbone = Model(models, 'chmr_backbone', provider)
    head = Model(models, 'chmr_head', provider)
    tokens = []
    for i, frame in enumerate(frames):
        progress(f'3D features {i+1}/{n}')
        tensor, scale, offset = preprocess(frame, (896,896))
        prompts = keypoints[i,PROMPT_IDS].copy()
        prompts[:,:2] = (prompts[:,:2]-offset)/scale/896
        prompts[:,2] = prompts[:,2] > .7
        prompt_box = np.r_[((boxes[i].reshape(2,2)-offset)/scale/896).reshape(-1), 1][None]
        f_inv = float(wh.max())/focal
        kinv = np.array([[f_inv,0,-.5*f_inv],[0,f_inv,-.5*f_inv],[0,0,1]])[None]
        tokens.append(head(backbone(tensor)[0], kinv, prompt_box, prompts[None])[0][0,[0,1,2,3,5]])
    del backbone, head, frames
    gc.collect()
    tokens = np.array(tokens)
    np.savez_compressed(output/'features.npz', keypoints=keypoints, tokens=tokens, boxes=boxes, focal=focal, size=wh, fps=fps)
    # UE's overlap geometry: 17 smoothing + 4 extra + 32 context frames each side.
    # Process the full sequence in bounded windows with the same retained core ranges.
    rng = np.random.default_rng(seed)
    noise = rng.standard_normal((n,331)).astype(np.float32)
    results = [[] for _ in range(4)]
    for offset,count,ml_start,ml_count,valid_start,valid_end in temporal_windows(n):
        local = slice(offset, offset+count)
        smooth, obs, cliff = hue_inputs(boxes[local], keypoints[local], focal, wh/2)
        sl = slice(ml_start, ml_start+ml_count)
        obs, cliff, smooth = obs[sl][None], cliff[sl][None], smooth[sl][None]
        img = tokens[offset+ml_start:offset+ml_start+ml_count][None]
        sample = noise[offset+ml_start:offset+ml_start+ml_count][None].copy()
        length = np.array([ml_count],dtype=np.int64)
        angular = np.zeros((1,ml_count,6),np.float32)
        heights = np.full((1,ml_count),height/100,np.float32)
        progress(f'Loading Hue for {ml_count} frames (offset {offset})')
        step = Model(models, 'hue_step_simplified', provider, ml_count)
        for index in range(49):
            progress(f'Temporal solve {index+1}/49 (offset {offset})')
            sample = step(np.array(999-index*20,dtype=np.int64), sample, length, obs, cliff, angular, img, heights)[0]
        del step
        gc.collect()
        progress('Final body solve (CPU)')
        final = Model(models, 'hue_finalStep_simplified', 'cpu', ml_count)
        k = np.array([[focal,0,wh[0]/2],[0,focal,wh[1]/2],[0,0,1]],np.float32)
        solved = final(sample,length,obs,cliff,angular,img,smooth,np.tile(k,(1,ml_count,1,1)),heights)
        keep = slice(valid_start-ml_start, valid_end-ml_start)
        for target, value, dim in zip(results,solved,[165,10,3,6]):
            target.append(value.reshape(ml_count,dim)[keep])
        del final
        gc.collect()
    pose, betas, trans, contact = [np.concatenate(x) for x in results]
    if len(pose) != n:
        raise RuntimeError(f'Output frame mismatch: {len(pose)} != {n}')
    np.savez_compressed(output/'motion.npz', poses=pose, betas=betas, translations=trans, contact_logits=contact, fps=fps)
    metadata = dict(video=str(Path(video).resolve()),start_frame=start,end_frame_inclusive=start+n-1,fps=fps,frames=n,rotation=rotation,roi=boxes[0].tolist(),roi_mode='tracked' if track_boxes is not None else 'static',focal_px=focal,camera_pitch=pitch,camera_roll=roll,provider=provider,seed=seed,body_height_cm=height,seconds=time.perf_counter()-began,coordinate_system='raw Hue output; before UE camera/ground finalize',limitations=['Tracked ROI; no mask isolation during overlap' if track_boxes is not None else 'Explicit static ROI; no Detectron2/SAM2','No UE body optimizer/foot locking','No Manny IK retargeting','Camera estimated on first selected frame','NumPy RNG and OpenCV interpolation differ from UE'])
    (output/'metadata.json').write_text(json.dumps(metadata,indent=2),encoding='utf-8')
    progress(f'Pose inference complete: {output}')
    return output


def solve_two(roi2, **kwargs):
    from .export import export_motion
    from .preview import write_pair_preview
    output = Path(kwargs.pop('output'))
    if output.exists():
        raise FileExistsError(f'Output already exists: {output}')
    if kwargs.get('roi') is None:
        raise ValueError('Two-person mode requires both --roi and --roi2')
    frames,fps = read_frames(kwargs['video'],kwargs.get('start',0),kwargs.get('start',0),kwargs.get('rotation',0))
    if kwargs.get('focal') is None:
        camera = calibrate(frames[0],kwargs['models'],kwargs.get('provider','cpu'))
    else:
        camera = (kwargs['focal'],0.,0.)
    output.mkdir(parents=True)
    people = []
    for index,box in enumerate([kwargs['roi'],roi2],1):
        run = output/f'person_{index:02d}'
        solve(**{**kwargs,'roi':box},output=run,camera=camera)
        export_motion(run,kwargs['models'])
        people.append(json.loads((run/'metadata.json').read_text(encoding='utf-8')))
    if people[0]['frames'] != people[1]['frames'] or people[0]['fps'] != people[1]['fps']:
        raise RuntimeError('Two-person frame alignment mismatch')
    (output/'pair.json').write_text(json.dumps(dict(people=people,mode='two independent static ROIs; separate skeletons, not interaction solve'),indent=2),encoding='utf-8')
    write_pair_preview(output/'preview.html',people[0]['frames'],fps)
    (output/'SUCCESS').write_text('Two independent person captures completed\n',encoding='ascii')
    return output
