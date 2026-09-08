"""YOLOX ONNX person detection and appearance/motion-assisted assignment.

Detector tensor contract: official Megvii YOLOX ONNXRuntime demo (Apache-2.0).
Tracker is a lightweight local implementation, not ByteTrack/SAM2.
"""
from pathlib import Path
import json
import cv2
import numpy as np
from scipy.ndimage import gaussian_filter1d
from scipy.optimize import linear_sum_assignment
from .runtime import Model


class PersonDetector:
    def __init__(self, models, provider, min_height=.18):
        if not (Path(models)/'yolox_s.onnx').is_file():
            raise FileNotFoundError('Run SetupMovie2Anim.bat to install the person detector')
        self.model=Model(models,'yolox_s',provider)
        self.size=640
        self.min_height=min_height
        grids=[]; strides=[]
        for stride in [8,16,32]:
            y,x=np.mgrid[:self.size//stride,:self.size//stride]
            grids.append(np.stack([x,y],-1).reshape(-1,2))
            strides.append(np.full((x.size,1),stride))
        self.grid=np.concatenate(grids);self.stride=np.concatenate(strides)

    def __call__(self,frame):
        h,w=frame.shape[:2]; ratio=min(self.size/w,self.size/h)
        padded=np.full((self.size,self.size,3),114,np.uint8)
        resized=cv2.resize(frame,(int(w*ratio),int(h*ratio)))
        padded[:len(resized),:resized.shape[1]]=resized
        raw=self.model(padded.transpose(2,0,1)[None].astype(np.float32))[0][0]
        score=raw[:,4]*raw[:,5]  # COCO class zero: person.
        valid=score>.2
        pred=raw[valid];scores=score[valid]
        center=(pred[:,:2]+self.grid[valid])*self.stride[valid]
        extent=np.exp(np.clip(pred[:,2:4],-10,10))*self.stride[valid]
        boxes=np.concatenate([center-extent/2,center+extent/2],axis=1)/ratio
        boxes[:,0::2]=boxes[:,0::2].clip(0,w);boxes[:,1::2]=boxes[:,1::2].clip(0,h)
        order=np.argsort(-scores);keep=[]
        while len(order):
            i=order[0];keep.append(i)
            order=order[1:][box_iou(boxes[i],boxes[order[1:]])<.5]
        keep=[i for i in keep if boxes[i,3]-boxes[i,1]>h*self.min_height and boxes[i,2]-boxes[i,0]>12]
        return boxes[keep],scores[keep]


def box_iou(a,boxes):
    inter=np.maximum(0,np.minimum(a[2:],boxes[:,2:])-np.maximum(a[:2],boxes[:,:2])).prod(axis=1)
    union=np.prod(a[2:]-a[:2])+np.prod(boxes[:,2:]-boxes[:,:2],axis=1)-inter
    return inter/np.maximum(union,1e-6)


def appearance(frame,box):
    a,b,c,d=box.astype(int);w=c-a;h=d-b
    crop=frame[b+int(.15*h):b+int(.75*h),a+int(.2*w):c-int(.2*w)]
    hsv=cv2.cvtColor(crop,cv2.COLOR_BGR2HSV)
    hist=cv2.calcHist([hsv],[0,1],None,[16,8],[0,180,0,256]).ravel()
    return hist/(hist.sum()+1e-8)


def select_actor_tracks(tracks, mode='all'):
    """Select body subjects without changing the tracks used to mask the camera.

    Primary means the most frequently observed track, with median observed box
    area as a tie breaker. Selection is clip-wide: never switch IDs per frame or
    fill a long absence with a different person.
    """
    if mode not in {'all', 'primary'}:
        raise ValueError(f'Unknown actor mode: {mode}')
    if mode == 'all':
        return tracks
    if not tracks:
        raise ValueError('No tracked actor available for primary selection')

    def rank(track):
        observed = np.asarray(track['observed'], dtype=bool)
        boxes = track['boxes'][observed]
        area = np.prod(np.maximum(0, boxes[:, 2:] - boxes[:, :2]), axis=1)
        return int(observed.sum()), float(np.median(area)) if len(area) else 0.

    return [max(tracks, key=rank)]


class Tracker:
    def __init__(self,max_gap=12):
        self.tracks=[];self.max_gap=max_gap

    def update(self,frame_index,boxes,scores,looks):
        active=[t for t in self.tracks if frame_index-t['last']<=self.max_gap]
        matched=set()
        if active and len(boxes):
            cost=np.full((len(active),len(boxes)),100.)
            for i,t in enumerate(active):
                gap=frame_index-t['last']; pred=t['box']+t['velocity']*gap
                iou=box_iou(pred,boxes)
                dist=np.linalg.norm((pred[:2]+pred[2:])/2-(boxes[:,:2]+boxes[:,2:])/2,axis=1)/max(pred[3]-pred[1],1)
                color=np.array([np.sqrt(max(0,1-np.sqrt(t['appearance']*h).sum())) for h in looks])
                cost[i]=.8*(1-iou)+.8*dist+.8*color
                cost[i,dist>.8]=100
            rows,cols=linear_sum_assignment(cost)
            for i,j in zip(rows,cols):
                if cost[i,j]>1.35: continue
                t=active[i];gap=frame_index-t['last']
                t['velocity']=.7*t['velocity']+.3*(boxes[j]-t['box'])/gap
                t['appearance']=.9*t['appearance']+.1*looks[j]
                t['box']=boxes[j];t['last']=frame_index
                t['samples'][frame_index]=(boxes[j],float(scores[j]))
                matched.add(j)
        for j in range(len(boxes)):
            if j in matched or scores[j]<.45:continue
            self.tracks.append(dict(id=len(self.tracks)+1,box=boxes[j],last=frame_index,
                velocity=np.zeros(4),appearance=looks[j],samples={frame_index:(boxes[j],float(scores[j]))}))

    def stitch_fragments(self):
        """Join short, unambiguous gaps without merging overlapping tracks."""
        joins=[];removed=set()
        for a in sorted(self.tracks,key=lambda t:-len(t['samples'])):
            if a['id'] in removed or len(a['samples'])<6:continue
            while True:
                last=max(a['samples']);box=a['samples'][last][0]
                candidates=[]
                for b in self.tracks:
                    if b is a or b['id'] in removed or len(b['samples'])<6:continue
                    first=min(b['samples']);gap=first-last-1
                    if not 0<=gap<=self.max_gap:continue
                    other=b['samples'][first][0]
                    height=max(box[3]-box[1],other[3]-other[1])
                    distance=np.linalg.norm((box[:2]+box[2:]-other[:2]-other[2:])/2)/max(height,1)
                    ratio=(other[3]-other[1])/max(box[3]-box[1],1)
                    color=np.sqrt(max(0,1-np.sqrt(a['appearance']*b['appearance']).sum()))
                    if distance>1.5 or not .4<ratio<2.5 or color>.35:continue
                    candidates.append((distance+2*color+.02*gap,b))
                candidates.sort(key=lambda item:item[0])
                if not candidates or (len(candidates)>1 and candidates[1][0]-candidates[0][0]<.2):break
                _,b=candidates[0]
                rivals=[t for t in self.tracks if t is not a and t is not b and t['id'] not in removed
                        and len(t['samples'])>=6 and 0<=min(b['samples'])-max(t['samples'])-1<=self.max_gap
                        and np.sqrt(max(0,1-np.sqrt(t['appearance']*b['appearance']).sum()))<.35]
                if any(len(t['samples'])>=len(a['samples'])*.5 for t in rivals):break
                joins.append(dict(from_id=a['id'],to_id=b['id'],gap_frames=min(b['samples'])-last-1))
                a['samples'].update(b['samples']);removed.add(b['id'])
        self.tracks=[t for t in self.tracks if t['id'] not in removed]
        return joins

    def finish_partial(self,n,wh):
        result=[]
        for track in self.tracks:
            keys=np.array(sorted(track['samples']))
            if len(keys)<6:continue
            boxes=np.zeros((n,4));valid=np.zeros(n,dtype=bool)
            for part in np.split(keys,np.flatnonzero(np.diff(keys)>self.max_gap+1)+1):
                if len(part)<6 or part[-1]-part[0]+1<12:continue
                first,last=int(part[0]),int(part[-1])+1
                observed=np.array([track['samples'][int(i)][0] for i in part])
                local=np.column_stack([np.interp(np.arange(first,last),part,observed[:,k]) for k in range(4)])
                local=gaussian_filter1d(local,1,axis=0,mode='nearest')
                center=(local[:,:2]+local[:,2:])/2;extent=(local[:,2:]-local[:,:2])*1.08
                local=np.concatenate([center-extent/2,center+extent/2],axis=1)
                local[:,0::2]=local[:,0::2].clip(0,wh[0]);local[:,1::2]=local[:,1::2].clip(0,wh[1])
                boxes[first:last]=local;valid[first:last]=True
            if valid.any():result.append(dict(id=track['id'],boxes=boxes,valid=valid,
                observed=np.isin(np.arange(n),keys)&valid,coverage=float(valid.mean())))
        if not result:raise ValueError('No person interval with at least 12 frames and 6 observations')
        return result

    def finish(self,n,wh):
        significant=[t for t in self.tracks if len(t['samples'])>=max(6,n*.15)]
        if not significant:raise ValueError('No persistent person detected')
        if len(significant)>2:raise ValueError('More than two persistent IDs: multiple people or tracking fragmentation; inspect detections.json')
        significant.sort(key=lambda t:sum(t['samples'][min(t['samples'])][0][[0,2]]))
        result=[]
        for t in significant:
            frames=np.array(sorted(t['samples']))
            gaps=np.diff(np.r_[-1,frames,n])-1
            if frames[0]>2 or frames[-1]<n-3 or max(gaps)>self.max_gap or len(frames)/n<.8:
                raise ValueError(f'Person ID {t["id"]} not reliably visible over full clip; crop the time range or inspect detections.json')
            observed=np.array([t['samples'][int(f)][0] for f in frames])
            boxes=np.column_stack([np.interp(np.arange(n),frames,observed[:,k]) for k in range(4)])
            boxes=gaussian_filter1d(boxes,1,axis=0,mode='nearest')
            center=(boxes[:,:2]+boxes[:,2:])/2; extent=(boxes[:,2:]-boxes[:,:2])*1.08
            boxes=np.concatenate([center-extent/2,center+extent/2],axis=1)
            boxes[:,0::2]=boxes[:,0::2].clip(0,wh[0]);boxes[:,1::2]=boxes[:,1::2].clip(0,wh[1])
            result.append(dict(id=t['id'],boxes=boxes,observed=np.isin(np.arange(n),frames),coverage=len(frames)/n))
        return result


def detect_tracks(frames,fps,models,provider,output,log=print,allow_small_initial=False):
    output=Path(output); detector=PersonDetector(models,provider)
    tracker=Tracker(max_gap=max(3,round(fps*.4))); detections=[]
    for i,frame in enumerate(frames):
        boxes,scores=detector(frame)
        if i==0 and allow_small_initial and not np.any(scores>=.45):
            detector.min_height=.06
            boxes,scores=detector(frame)
            log("No large initial actor; allowing smaller distant people (height >= 6%)")
        tracker.update(i,boxes,scores,[appearance(frame,b) for b in boxes])
        detections.append(dict(frame=i,boxes=boxes.tolist(),scores=scores.tolist()))
        if i%12==0 or i==len(frames)-1:log(f'Person detection {i+1}/{len(frames)}')
    (output/'detections.json').write_text(json.dumps(detections),encoding='utf-8')
    if allow_small_initial:
        joins=tracker.stitch_fragments()
        (output/'track_joins.json').write_text(json.dumps(joins,indent=2),encoding='utf-8')
        if joins:log(f'Joined {len(joins)} unambiguous short tracking gaps')
    tracks=(tracker.finish_partial if allow_small_initial else tracker.finish)(len(frames),(frames[0].shape[1],frames[0].shape[0]))
    np.savez_compressed(output/'tracks.npz',boxes=np.array([t['boxes'] for t in tracks]),
                        observed=np.array([t['observed'] for t in tracks]),valid=np.array([t.get('valid',np.ones(len(frames),dtype=bool)) for t in tracks]),ids=[t['id'] for t in tracks],fps=fps)
    writer=cv2.VideoWriter(str(output/'tracking.mp4'),cv2.VideoWriter_fourcc(*'mp4v'),fps,(frames[0].shape[1],frames[0].shape[0]))
    if not writer.isOpened():raise RuntimeError('Cannot write tracking preview')
    try:
        for i,frame in enumerate(frames):
            out=frame.copy()
            for person,t in enumerate(tracks,1):
                if 'valid' in t and not t['valid'][i]:continue
                x0,y0,x1,y1=t['boxes'][i].astype(int);color=(255,160,40) if person==1 else (90,220,100)
                cv2.rectangle(out,(x0,y0),(x1,y1),color,2)
                cv2.putText(out,f'Person {person}'+(' (interpolated)' if not t['observed'][i] else ''),(x0,max(20,y0-5)),cv2.FONT_HERSHEY_SIMPLEX,.6,color,2)
            writer.write(out)
    finally:writer.release()
    log(f'Detected {len(tracks)} person(s); coverage '+str([round(t['coverage'],3) for t in tracks]))
    return tracks
