"""CUDA-only worker. File interchange keeps Torch out of the DirectML process."""
from pathlib import Path
import argparse
import gc
import hashlib
import json
import os
import time
import urllib.request
import cv2
import numpy as np
from m2a.camera_math import unproject, similarity, align_poses, validate_poses, anchor_similarity

ROOT = Path(__file__).resolve().parents[1]


def download(model_name):
    from huggingface_hub import HfApi, snapshot_download
    root = ROOT/'models/camera'; root.mkdir(parents=True, exist_ok=True)
    model = root/model_name
    manifest = root/(model_name+'.json')
    if not manifest.exists():
        revision = {'DA3-LARGE':'c54c26b16ec04d218e8d584ecf4bce082a9fcc20','DA3-GIANT':'7cd62ae9315b9dff094d2d300e4ad012640607dd'}.get(model_name) or HfApi().model_info('depth-anything/'+model_name).sha
        snapshot_download('depth-anything/'+model_name, revision=revision, local_dir=model,
                          allow_patterns=['config.json', 'model.safetensors'])
        hashes = {f.name: hashlib.file_digest(f.open('rb'), 'sha256').hexdigest()
                  for f in (model/'config.json', model/'model.safetensors')}
        manifest.write_text(json.dumps(dict(repo='depth-anything/'+model_name, revision=revision, sha256=hashes), indent=2))
    else:
        data = json.loads(manifest.read_text())
        for name, expected in data['sha256'].items():
            with (model/name).open('rb') as stream:
                if hashlib.file_digest(stream, 'sha256').hexdigest() != expected:
                    raise RuntimeError('Existing DA3 weights differ; preserved for inspection')
    weight = root/'geocalib-distorted.tar'
    provenance = root/'geocalib.json'
    url = 'https://github.com/cvg/GeoCalib/releases/download/v1.0/geocalib-distorted.tar'
    if not weight.exists():
        part = weight.with_suffix('.part')
        urllib.request.urlretrieve(url, part)
        part.replace(weight)
    with weight.open('rb') as stream: digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    if digest != '13cc505928e3ff4eb26c00bff73861ab2b11b804a546323456cf5462e1f8f447':
        raise RuntimeError('GeoCalib download does not match the verified official release')
    if provenance.exists() and json.loads(provenance.read_text())['sha256'] != digest:
        raise RuntimeError('Existing GeoCalib weights differ; preserved for inspection')
    provenance.write_text(json.dumps(dict(url=url, sha256=digest), indent=2))
    print('Camera models verified:', model, flush=True)


def rectify(video, output, crop_black_borders=False):
    import torch
    from geocalib import GeoCalib
    from m2a.video import read_frames
    if output.exists(): raise FileExistsError(output)
    output.mkdir(parents=True)
    frames, fps = read_frames(video, 0, None, 0)
    if len(frames) < 12: raise ValueError('At least 12 frames required')
    indices = np.unique(np.linspace(0, len(frames)-1, min(5, len(frames))).astype(int))
    images = np.stack([frames[int(i)][:, :, ::-1] for i in indices]).copy()
    input_h,input_w=images.shape[1:3]
    # Persistent black letterbox bars are not optical image content. Remove the
    # same border from all stages so calibration and DA3 see the active raster.
    dark=(images.max(axis=(0,3))<12)
    rows=np.where((~dark).mean(axis=1)>.005)[0]
    cols=np.where((~dark).mean(axis=0)>.005)[0]
    x0,y0,x1,y1=0,0,input_w,input_h
    if crop_black_borders and len(rows) and len(cols):
        cy0,cy1=int(rows[0]),int(rows[-1])+1;cx0,cx1=int(cols[0]),int(cols[-1])+1
        if cy0<input_h*.25 and input_h-cy1<input_h*.25 and cx0<input_w*.25 and input_w-cx1<input_w*.25:
            x0,y0=cx0,cy0;x1=x0+(cx1-x0)//2*2;y1=y0+(cy1-y0)//2*2
    images=images[:,y0:y1,x0:x1].copy()

    model = GeoCalib(str(ROOT/'models/camera/geocalib-distorted.tar')).cuda().eval()
    print('GeoCalib: one shared lens across', indices.tolist(), flush=True)
    pred = model.calibrate(torch.from_numpy(images).permute(0, 3, 1, 2).cuda().float()/255,
                           camera_model='simple_radial', shared_intrinsics=True)
    cam = pred['camera']
    f = cam.f.detach().cpu().numpy().reshape(-1, 2).mean(0)
    c = cam.c.detach().cpu().numpy().reshape(-1, 2).mean(0)
    k1 = float(cam.k1.detach().cpu().mean())
    gravity = pred['gravity'].vec3d.detach().cpu().numpy()
    h, w = images.shape[1:3]
    if not np.isfinite(np.r_[f,c,k1]).all() or min(f) < .15*max(w,h):
        raise ValueError('Unreliable lens estimate')
    kin = np.array([[f[0],0,c[0]],[0,f[1],c[1]],[0,0,1]], np.float64)
    # Centered square pixels match the current CHMR/Hue interface. Retain raster/FPS.
    focal = float(np.mean(f))
    k = np.array([[focal,0,w/2],[0,focal,h/2],[0,0,1]], np.float64)
    mx, my = cv2.initUndistortRectifyMap(kin, np.array([k1,0,0,0,0]), None, k, (w,h), cv2.CV_32FC1)
    valid = (mx>=0)&(my>=0)&(mx<w-1)&(my<h-1)
    cv2.imwrite(str(output/'valid_pixels.png'), valid.astype(np.uint8)*255)
    writer = cv2.VideoWriter(str(output/'rectified.avi'), cv2.VideoWriter_fourcc(*'FFV1'), fps, (w,h))
    if not writer.isOpened(): raise RuntimeError('Lossless FFV1 writer unavailable')
    try:
        for i, frame in enumerate(frames):
            writer.write(cv2.remap(frame[y0:y1,x0:x1],mx,my,cv2.INTER_LINEAR,borderMode=cv2.BORDER_CONSTANT))
    finally: writer.release()
    data = dict(input=str(Path(video).resolve()),frames=len(frames),fps=fps,size=[w,h],
                K=k.tolist(),original_K=kin.tolist(),k1=k1,gravity_samples=gravity.tolist(),
                input_adjusted_size=[input_w,input_h],active_crop=[x0,y0,x1,y1],sample_frames=indices.tolist(),lens='shared simple_radial; fixed lens/no zoom',
                valid_pixel_fraction=float(valid.mean()))
    (output/'lens.json').write_text(json.dumps(data,indent=2),encoding='utf-8')
    print('Rectified', len(frames), 'frames; focal', focal, 'k1', k1, flush=True)


def background_mask(shape, boxes, size, valid=None):
    h,w=shape; ow,oh=size
    mask=np.ones((h,w),np.uint8)*255 if valid is None else cv2.resize(valid,(w,h),interpolation=cv2.INTER_NEAREST)
    for box in boxes:
        x1,y1,x2,y2=np.asarray(box)*[w/ow,h/oh,w/ow,h/oh]
        pad=max(4,.08*max(x2-x1,y2-y1))
        cv2.rectangle(mask,(max(0,int(x1-pad)),max(0,int(y1-pad))),(int(x2+pad),int(y2+pad)),0,-1)
    mask[:4]=0;mask[-4:]=0;mask[:,:4]=0;mask[:,-4:]=0
    return mask


def points_world(depth,k,pose,pixels):
    ij=np.rint(pixels).astype(int)
    z=depth[ij[:,1],ij[:,0]]
    return (unproject(z,k,pixels)-pose[:,3]) @ pose[:,:3]


class CameraGeometryError(ValueError):
    """An expected geometric quality rejection, eligible for prefix recovery."""


def refine_background(images, depths, predicted_k, poses, k, masks):
    """PnP with static background tracks and fixed GeoCalib intrinsics; reject weak fits."""
    reports=[]; result=poses.copy()
    for i in range(1,len(images)):
        clahe=cv2.createCLAHE(2.,(8,8))
        gray0=clahe.apply(cv2.cvtColor(images[i-1],cv2.COLOR_RGB2GRAY))
        gray1=clahe.apply(cv2.cvtColor(images[i],cv2.COLOR_RGB2GRAY))
        p=cv2.goodFeaturesToTrack(gray0,2000,.003,3,mask=masks[i-1])
        if p is None or len(p)<30: raise CameraGeometryError('Insufficient visible background for moving-camera solve')
        q,status,_=cv2.calcOpticalFlowPyrLK(gray0,gray1,p,None,winSize=(31,31),maxLevel=4)
        back,back_status,_=cv2.calcOpticalFlowPyrLK(gray1,gray0,q,None,winSize=(31,31),maxLevel=4)
        p=p[:,0];q=q[:,0];back=back[:,0]
        h,w=gray0.shape
        good=(status[:,0]>0)&(back_status[:,0]>0)&(np.linalg.norm(back-p,axis=1)<1.5)
        good&=(q[:,0]>=1)&(q[:,0]<w-1)&(q[:,1]>=1)&(q[:,1]<h-1)
        qi=np.rint(np.clip(q,[0,0],[w-1,h-1])).astype(int)
        good &= masks[i][qi[:,1],qi[:,0]]>0
        p,q=p[good],q[good]
        # Sequential depth-guided VO: use the previously refined camera, avoiding
        # independent absolute PnP fits that can introduce frame-to-frame jumps.
        xyz=points_world(depths[i-1],k,result[i-1],p)
        finite=np.isfinite(xyz).all(1)
        xyz,q=xyz[finite],q[finite]
        if len(q)<30: raise CameraGeometryError(f'Background tracking failed at local frame {i}: {len(q)} tracks; possible cut/occlusion')
        ok,rv,tv,inliers=cv2.solvePnPRansac(xyz,q,k,None,iterationsCount=150,reprojectionError=3.,confidence=.999,flags=cv2.SOLVEPNP_EPNP)
        if not ok or inliers is None or len(inliers)<25 or len(inliers)/len(q)<.35:
            raise CameraGeometryError('Camera/background geometry inconsistent; inspect camera windows')
        ix=inliers[:,0]
        rv,tv=cv2.solvePnPRefineLM(xyz[ix],q[ix],k,None,rv,tv)
        projected,_=cv2.projectPoints(xyz[ix],rv,tv,k,None)
        err=float(np.median(np.linalg.norm(projected[:,0]-q[ix],axis=1)))
        result[i]=np.column_stack([cv2.Rodrigues(rv)[0],tv])
        old_rv=cv2.Rodrigues(poses[i,:,:3])[0]
        old_proj,_=cv2.projectPoints(xyz[ix],old_rv,poses[i,:,3],k,None)
        baseline=float(np.median(np.linalg.norm(old_proj[:,0]-q[ix],axis=1)))
        reports.append(dict(frame=i,inliers=len(ix),tracks=len(q),median_reprojection_px=err,raw_reprojection_px=baseline))
    return result,reports


def poses(output, model_name, window=24, overlap=8, resolution=336):
    import torch
    from depth_anything_3.api import DepthAnything3
    from m2a.video import read_frames
    if not 4<=overlap<window or resolution<140: raise ValueError('Invalid window/overlap/resolution')
    if (output/'trajectory.npz').exists(): raise FileExistsError(output/'trajectory.npz')
    lens=json.loads((output/'lens.json').read_text())
    frames,fps=read_frames(output/'rectified.avi',0,None,0)
    n=len(frames); ow,oh=lens['size']; k=np.array(lens['K'])
    size=np.maximum(14,(np.array([ow,oh])*resolution/max(ow,oh)).astype(int)//14*14)
    w,h=map(int,size); ks=k.copy();ks[0]*=w/ow;ks[1]*=h/oh
    tracks=np.load(output.parent/'tracks.npz')['boxes']
    detections=json.loads((output.parent/'detections.json').read_text())
    if tracks.shape[1]!=n: raise ValueError('Camera/tracking frame count mismatch')
    valid=cv2.imread(str(output/'valid_pixels.png'),cv2.IMREAD_GRAYSCALE)
    model=DepthAnything3.from_pretrained(str(ROOT/'models/camera'/model_name)).cuda().eval()
    trajectory=np.zeros((n,3,4));depth_dir=output/'depth';depth_dir.mkdir(exist_ok=True)
    reports=[];start=0;finished=0;segment_start=0;segments=[];failures=[];trial_window=window
    stream=iter(frames);tail=[]
    while start<n:
        if start==segment_start and n-start<12:
            failures.append(dict(start=start,end=n,reason='Fewer than 12 frames remain for independent body inference'))
            break
        end=min(n,start+trial_window)
        images=tail+[cv2.resize(next(stream),(w,h))[:,:,::-1].copy() for _ in range(end-max(start,finished))]
        print(f'DA3 camera frames {start}..{end-1}',flush=True)
        pred=model.inference(images,process_res=max(w,h),ref_view_strategy='first')
        ds=np.asarray(pred.depth); ik=np.asarray(pred.intrinsics); raw=validate_poses(pred.extrinsics).copy()
        if ds.shape[1:]!=(h,w): raise ValueError('Unexpected DA3 raster; intrinsics mapping would be invalid')
        masks=[background_mask((h,w),list(tracks[:,i])+[b for b,score in zip(detections[i]['boxes'],detections[i]['scores']) if score>=.45],(ow,oh),valid) for i in range(start,end)]
        # Fixed focal depth correction keeps each depth value on its original pixel ray.
        # The scene scale is still arbitrary and is aligned jointly across all actors.
        ds=ds*(ks[1,1]/ik[:,1,1])[:,None,None]
        try:
            refined,checks=refine_background(images,ds,ik,raw,ks,masks)
            join=None
            if start>segment_start:
                src=[];dst=[]
                for j in range(min(finished-start,overlap)):
                    old=np.load(depth_dir/f'{start+j:06d}.npz')['depth']
                    mask=(masks[j]>0)&(old>0)&(ds[j]>0)&np.isfinite(old)&np.isfinite(ds[j])
                    yy,xx=np.where(mask);pix=np.column_stack([xx,yy])[::max(1,len(xx)//1200)]
                    src.append(points_world(ds[j],ks,refined[j],pix))
                    dst.append(points_world(old,ks,trajectory[start+j],pix))
                x,y=np.concatenate(src),np.concatenate(dst)
                # Depth scale is robustly shared across overlap; the last common camera
                # fixes orientation/translation exactly. Point-cloud-only Sim(3) fits can
                # shift the camera when depth predictions change between windows.
                ratios=[]
                count=min(finished-start,overlap)
                for j in range(count):
                    old=np.load(depth_dir/f'{start+j:06d}.npz')['depth']
                    good=(masks[j]>0)&(old>0)&(ds[j]>0)&np.isfinite(old)&np.isfinite(ds[j])
                    ratios.extend((old[good]/ds[j][good])[::8])
                if len(ratios)<100:raise CameraGeometryError('Insufficient overlap depth to recover camera scale')
                s=float(np.median(ratios))
                if not .1<s<10:raise CameraGeometryError('Invalid overlap camera scale')
                anchor=count-1;old_pose=trajectory[start+anchor];new_pose=refined[anchor]
                r,t=anchor_similarity(old_pose,new_pose,s)
                relative=float(np.median(np.linalg.norm(s*x@r.T+t-y,axis=1))/max(np.median(np.linalg.norm(y-y.mean(0),axis=1)),1e-6))
                reprojection=[]
                for j,(xx,yy) in enumerate(zip(src,dst)):
                    pose=trajectory[start+j]
                    xc=(s*xx@r.T+t)@pose[:,:3].T+pose[:,3]
                    yc=yy@pose[:,:3].T+pose[:,3]
                    positive=(xc[:,2]>1e-5)&(yc[:,2]>1e-5)
                    if positive.mean()<.8:raise CameraGeometryError('Camera join places background behind the camera')
                    xp=xc[positive]@ks.T;yp=yc[positive]@ks.T
                    reprojection.extend(np.linalg.norm(xp[:,:2]/xp[:,2:]-yp[:,:2]/yp[:,2:],axis=1))
                join_px=float(np.median(reprojection));join_p90=float(np.quantile(reprojection,.9))
                if join_px>3 or join_p90>30 or (join_p90>10 and relative>.2):raise CameraGeometryError(f'Camera window join unreliable: reprojection median {join_px:.2f}px, p90 {join_p90:.2f}px, relative 3D error {relative:.3f}')

                refined=align_poses(refined,s,r,t);ds*=s
                join=dict(scale=float(s),relative_error=relative,reprojection_median_px=join_px,reprojection_p90_px=join_p90,depth_consistency_warning=relative>.2,reprojection_tail_warning=join_p90>10,anchor_frame=start+anchor,method='shared depth scale; exact last-overlap camera pose')
        except CameraGeometryError as exc:
            failures.append(dict(start=start,end=end,reason=str(exc)))
            if finished>segment_start:
                segments.append((segment_start,finished))
                restart=finished
                trial_window=window
            elif trial_window>12:
                restart=start
                trial_window=12
            else:
                restart=start+1
            print(f'RECOVER: {exc}; restart at frame {restart}',flush=True)
            start=segment_start=finished=restart
            if start<n:
                stream=iter(read_frames(output/'rectified.avi',start,None,0)[0])
            tail=[]
            del pred,images,ds
            gc.collect();torch.cuda.empty_cache()
            continue
        np.savez_compressed(output/f'window_{start:06d}.npz',raw_w2c=raw,refined_w2c=refined,predicted_K=ik,start=start,end=end)
        for j in range(max(0,finished-start),end-start):
            trajectory[start+j]=refined[j]
            np.savez_compressed(depth_dir/f'{start+j:06d}.npz',depth=ds[j],confidence=np.asarray(pred.conf[j]) if pred.conf is not None else np.ones((h,w)))
        reports.append(dict(start=start,end=end,background_checks=checks,join=join))
        finished=end
        trial_window=window
        tail=images[-overlap:]
        del pred,images,ds
        gc.collect();torch.cuda.empty_cache()
        if end==n:break
        start=end-overlap
    if finished>segment_start:segments.append((segment_start,finished))
    del model
    gc.collect();torch.cuda.empty_cache()
    from geocalib import GeoCalib
    from m2a.preview import write_preview
    import shutil
    gravity_model=GeoCalib(str(ROOT/'models/camera/geocalib-distorted.tar')).cuda().eval() if segments else None
    entries=[]
    full=segments==[(0,n)]
    for number,(first,last) in enumerate(segments,1):
        folder=output if full else output/'segments'/f'{number:03d}'
        folder.mkdir(parents=True,exist_ok=True)
        segment=validate_poses(trajectory[first:last])
        # Re-estimate gravity at each new world origin with the existing fixed lens.
        frame=frames[first][:,:,::-1].copy()
        gh,gw=frame.shape[:2];ratio=min(1.,896/max(gh,gw))
        frame=cv2.resize(frame,(round(gw*ratio),round(gh*ratio)))
        gp=gravity_model.calibrate(torch.from_numpy(frame).permute(2,0,1).cuda().float()/255,
            camera_model='pinhole',priors={'focal':torch.tensor(float(k[0,0]*ratio),device='cuda')})
        g=gp['gravity'].vec3d.detach().cpu().numpy().reshape(-1,3)[0]
        up=segment[0,:,:3].T@g;up/=np.linalg.norm(up)
        if not full:
            (folder/'depth').mkdir()
            for local,i in enumerate(range(first,last)):
                shutil.copyfile(depth_dir/f'{i:06d}.npz',folder/'depth'/f'{local:06d}.npz')
        np.savez_compressed(folder/'trajectory.npz',w2c=segment,K=ks,size=size,fps=fps,up_world=up,frame_indices=np.arange(first,last))
        entry=dict(id=number,camera_dir=str(folder.relative_to(output)),start=first,end=last,frames=last-first)
        entries.append(entry)
        centers=-np.einsum('fji,fj->fi',segment[:,:,:3],segment[:,:,3])
        write_preview(folder/'camera_preview.html',centers[:,None,:],fps,dict(start_frame=first),parents=[-1],
            label='DA3 camera segment',hint='Independent world origin; not connected across failed joins.')
    accepted=np.zeros(n,dtype=bool)
    for first,last in segments:accepted[first:last]=True
    changes=np.flatnonzero(np.diff(np.r_[False,~accepted,False].astype(int)))
    skipped=[dict(start=int(a),end=int(b)) for a,b in changes.reshape(-1,2)]
    report=dict(model=model_name,frames=int(accepted.sum()),input_frames=n,partial=not full,
        segments=entries,skipped_ranges=skipped,failures=failures,windows=reports,
        scale='independent camera origin and estimated body scale per segment',
        limitations=['Camera validation is internal consistency, not ground truth',
        'Failed joins create separate clips; no cross-segment world placement',
        'Search falls back to 12-frame windows with one-frame steps after geometric rejection'])
    (output/'camera_report.json').write_text(json.dumps(report,indent=2))
    if not entries:raise CameraGeometryError('No valid continuous interval of at least 12 frames')
    print('Camera search complete:',len(entries),'segments;',int(accepted.sum()),'/',n,'frames',flush=True)


def main():
    p=argparse.ArgumentParser();p.add_argument('stage',choices=['download','rectify','poses'])
    p.add_argument('--video',type=Path);p.add_argument('--output',type=Path)
    p.add_argument('--model',default='DA3-LARGE');p.add_argument('--window',type=int,default=24)
    p.add_argument('--overlap',type=int,default=8);p.add_argument('--resolution',type=int,default=336)
    p.add_argument('--crop-black-bars',action='store_true',help='Experimental active-raster crop; off by default')
    a=p.parse_args()
    cv2.setNumThreads(4)
    if a.stage=='download':download(a.model)
    elif a.stage=='rectify':rectify(a.video,a.output,a.crop_black_bars)
    else:poses(a.output,a.model,a.window,a.overlap,a.resolution)


if __name__=='__main__': main()
