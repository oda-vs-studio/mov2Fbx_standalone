import cv2
import numpy as np
from scipy.ndimage import median_filter, convolve1d


def adjusted_size(frame):
    h, w = frame.shape[:2]
    return np.array([w * 896 // h, 896] if h > 896 else [w, h], dtype=np.int32)


def preprocess(frame, size, box=None, sample_offset=0., normalize=True):
    """UE BodyTrackerUtils letterbox coordinates; OpenCV bilinear sampler."""
    original = adjusted_size(frame)
    width, height = size
    crop = np.array([0, 0, *original] if box is None else box, dtype=np.float32)
    crop[:2] = np.maximum(crop[:2], 0)
    crop[2:] = np.minimum(crop[2:], original)
    extent = crop[2:] - crop[:2]
    if np.any(extent <= 0):
        raise ValueError('Person box is outside image')
    scale = float(np.max(extent / np.array(size)))
    padding = (np.array(size) - extent / scale) / 2
    offset = crop[:2] - padding * scale
    xy_scale = np.array([frame.shape[1], frame.shape[0]]) / original
    xx, yy = np.meshgrid(np.arange(width), np.arange(height))
    mx = ((xx * scale + offset[0]) * xy_scale[0] + sample_offset).astype(np.float32)
    my = ((yy * scale + offset[1]) * xy_scale[1] + sample_offset).astype(np.float32)
    rgb = cv2.remap(frame, mx, my, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)[..., ::-1].astype(np.float32)
    if frame.dtype == np.uint8:
        rgb /= 255.
    pad = padding.astype(int)
    mask = (xx >= pad[0]) & (xx < width-pad[0]) & (yy >= pad[1]) & (yy < height-pad[1])
    rgb[~mask] = 0
    if normalize:
        rgb = (rgb - [.485, .456, .406]) / [.229, .224, .225]
    return rgb.transpose(2, 0, 1)[None].astype(np.float32), scale, offset


def hue_inputs(boxes, keypoints, focal, centers):
    boxes = np.asarray(boxes, dtype=np.float64)
    xys = np.column_stack(((boxes[:, :2]+boxes[:, 2:])/2, np.maximum((boxes[:, 2]-boxes[:, 0])/.75, boxes[:, 3]-boxes[:, 1])*1.2))
    smooth = median_filter(xys, size=(11, 1), mode='constant', cval=0.)
    kernel = np.exp(-np.arange(-12, 13, dtype=np.float64)**2/18)
    smooth = convolve1d(smooth, kernel/kernel.sum(), axis=0, mode='nearest').astype(np.float32)
    if np.any(smooth[:, 2] <= 0):
        raise ValueError('Insufficient valid frames for Hue box filter (use at least 12 frames)')
    obs = np.array(keypoints[:, :17], dtype=np.float32, copy=True)
    obs[:, :, :2] = 2*(obs[:, :, :2]-smooth[:, None, :2])/smooth[:, None, 2:3]
    obs[:, :, 2] *= (np.abs(obs[:, :, :2]) < 1).all(axis=-1)
    cliff = smooth.copy()
    cliff[:, :2] -= centers
    cliff /= focal
    return smooth, obs, cliff


def temporal_windows(n):
    """Yield UE-compatible context windows and retained frame intervals."""
    first, offset = True, 0
    while offset < n:
        count = min(n-offset,277 if first else 298)
        ml_start = 0 if first else 17
        ml_count = min(260 if first else 264,count-ml_start)
        last = ml_start+ml_count == count
        valid_start = 0 if first else 53
        valid_end = ml_start+ml_count if last else min(ml_start+ml_count-32,(32 if first else 53)+192)
        yield offset,count,ml_start,ml_count,valid_start,valid_end
        if last:
            break
        offset += valid_end-53
        first = False
