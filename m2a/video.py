"""Repeatable streaming video access: no list of decoded frames in memory."""
import cv2
import numpy as np
from .geometry import adjusted_size


class VideoFrames:
    def __init__(self,video,start,end,rotation):
        self.video=str(video);self.start=start;self.end=end;self.rotation=rotation
        self.expected_shape=None

    def __len__(self):return self.end-self.start+1

    def convert(self,frame):
        if self.rotation:frame=np.ascontiguousarray(np.rot90(frame,-(self.rotation//90)))
        size=adjusted_size(frame)
        if (frame.shape[1],frame.shape[0])!=tuple(size):frame=cv2.resize(frame,tuple(size),interpolation=cv2.INTER_AREA)
        if self.expected_shape is None:self.expected_shape=frame.shape
        elif frame.shape!=self.expected_shape:raise ValueError('Video resolution changed during the selected range')
        return frame

    def __iter__(self):
        cap=cv2.VideoCapture(self.video)
        if not cap.isOpened():raise ValueError(f'Cannot decode video: {self.video}')
        try:
            if self.start:cap.set(cv2.CAP_PROP_POS_FRAMES,self.start)
            for i in range(len(self)):
                ok,frame=cap.read()
                if not ok:raise ValueError(f'Video decode ended before frame {self.start+i}')
                yield self.convert(frame)
        finally:cap.release()

    def __getitem__(self,index):
        if not isinstance(index,int):raise TypeError('VideoFrames only supports integer indexing')
        if index<0:index+=len(self)
        if not 0<=index<len(self):raise IndexError(index)
        cap=cv2.VideoCapture(self.video)
        try:
            cap.set(cv2.CAP_PROP_POS_FRAMES,self.start+index)
            ok,frame=cap.read()
            if not ok:raise ValueError(f'Cannot decode video frame {self.start+index}')
            return self.convert(frame)
        finally:cap.release()


def read_frames(video,start,end,rotation):
    cap=cv2.VideoCapture(str(video))
    if not cap.isOpened():raise ValueError(f'Cannot decode video: {video}')
    try:
        fps=cap.get(cv2.CAP_PROP_FPS);count=int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    finally:cap.release()
    if not np.isfinite(fps) or fps<=0:raise ValueError('Invalid video FPS')
    end=count-1 if end is None else end
    if not 0<=start<=end<count:raise ValueError(f'Frame range must be inside 0..{count-1}')
    return VideoFrames(video,start,end,rotation),fps
