"""Camera geometry, in OpenCV coordinates unless explicitly converted to Y-up."""
import numpy as np


def validate_poses(w2c):
    w2c = np.asarray(w2c, dtype=np.float64)
    if w2c.ndim != 3 or w2c.shape[1:] != (3, 4) or not np.isfinite(w2c).all():
        raise ValueError('Camera poses must be finite N x 3 x 4 world-to-camera matrices')
    r = w2c[:, :, :3]
    if not np.allclose(r @ r.transpose(0, 2, 1), np.eye(3), atol=2e-3) or np.any(np.linalg.det(r) < .99):
        raise ValueError('Camera rotation is not a proper orthonormal matrix')
    # Float32 network rotations can be slightly non-orthogonal. Project to SO(3).
    u,_,vh=np.linalg.svd(r)
    w2c=w2c.copy();w2c[:,:,:3]=u@vh
    return w2c


def camera_to_world(points, w2c):
    w2c = validate_poses(w2c)
    return np.einsum('fji,f...j->f...i', w2c[:, :, :3], points - w2c[:, None, :, 3])


def unproject(depth, k, pixels):
    pixels = np.asarray(pixels)
    rays = np.column_stack([pixels, np.ones(len(pixels))]) @ np.linalg.inv(k).T
    return rays * np.asarray(depth)[:, None]


def similarity(source, target):
    """Least squares target = scale * source @ rotation.T + translation."""
    x, y = np.asarray(source), np.asarray(target)
    xm, ym = x.mean(0), y.mean(0)
    a, b = x-xm, y-ym
    if len(x) < 6 or np.linalg.matrix_rank(a) < 2:
        raise ValueError('Insufficient background geometry to join camera windows')
    u, d, vh = np.linalg.svd(b.T @ a / len(x))
    sign = np.ones(3); sign[-1] = np.linalg.det(u @ vh)
    r = (u * sign) @ vh
    s = np.sum(d*sign) / np.mean(np.sum(a*a, axis=1))
    t = ym-s*r@xm
    if not np.isfinite(s) or not .1 < s < 10:
        raise ValueError('Unreliable camera-window scale')
    return s, r, t


def align_poses(w2c, scale, rotation, translation):
    w2c = validate_poses(w2c)
    r = w2c[:, :, :3] @ rotation.T
    t = scale*w2c[:, :, 3] - np.einsum('fij,j->fi', r, translation)
    return np.concatenate([r, t[:, :, None]], axis=2)


def transform_body(local, root, w2c, camera_scale, up_rotation):
    """Raw Hue camera basis -> DA3 world -> Y-up, with one scene-wide scale."""
    w2c = validate_poses(w2c)
    if len(root) != len(w2c) or not np.isfinite(camera_scale) or camera_scale <= 0:
        raise ValueError('Body/camera frame count or scale mismatch')
    # Current raw Hue root uses OpenCV camera axes; child-local axes are untouched.
    rcw = w2c[:, :, :3].transpose(0, 2, 1)
    centers = -np.einsum('fij,fj->fi', rcw, w2c[:, :, 3]) * camera_scale
    world_root = np.einsum('fij,fj->fi', rcw, root) + centers
    result = local.copy()
    result[:, 0] = up_rotation @ rcw @ local[:, 0]
    return result, world_root @ up_rotation.T


def anchor_similarity(old_pose, new_pose, scale):
    old_pose=validate_poses(np.asarray(old_pose)[None])[0]
    new_pose=validate_poses(np.asarray(new_pose)[None])[0]
    if not np.isfinite(scale) or scale<=0:raise ValueError('Positive camera scale required')
    r=old_pose[:,:3].T@new_pose[:,:3]
    old_center=-old_pose[:,:3].T@old_pose[:,3]
    new_center=-new_pose[:,:3].T@new_pose[:,3]
    return r,old_center-scale*r@new_center
