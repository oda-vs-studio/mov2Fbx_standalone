import tempfile
import unittest
from pathlib import Path
import struct
import numpy as np
from scipy.spatial.transform import Rotation
from m2a.geometry import preprocess, hue_inputs, temporal_windows
from m2a.export import PARENTS, NAMES, forward_kinematics, write_bvh
from tools.extract_models import extract


class GeometryTests(unittest.TestCase):
    def test_temporal_boundaries_have_no_missing_or_duplicate_frames(self):
        for n in [12,16,124,259,260,261,276,277,278,298,299,416,417,600,619,1200,10000]:
            retained = []
            for offset,count,ml_start,ml_count,start,end in temporal_windows(n):
                self.assertGreater(ml_count,0)
                self.assertLessEqual(ml_count,264)
                self.assertGreaterEqual(start,ml_start)
                self.assertLessEqual(end,ml_start+ml_count)
                retained.extend(range(offset+start,offset+end))
            self.assertEqual(retained,list(range(n)))
    def test_letterbox_coordinates_and_black_padding(self):
        frame = np.full((100,200,3),255,np.uint8)
        image,scale,offset = preprocess(frame,(200,200),normalize=False)
        np.testing.assert_allclose(offset,[0,-50])
        self.assertEqual(scale,1)
        np.testing.assert_allclose(image[:,:,0],0)
        np.testing.assert_allclose(image[:,:,100],1)

    def test_hue_observations_and_intrinsics(self):
        boxes = np.tile([0,0,150,200],(40,1))
        points = np.tile([75,100,1],(40,133,1)).astype(np.float32)
        smooth,obs,cliff = hue_inputs(boxes,points,500,np.array([75,100]))
        np.testing.assert_allclose(smooth[20],[75,100,240],atol=1e-5)
        np.testing.assert_allclose(obs[20,:,0:2],0,atol=1e-6)
        np.testing.assert_allclose(cliff[20],[0,0,.48],atol=1e-5)

    def test_forward_kinematics_rotates_child_offset(self):
        angles = np.zeros((1,55,3))
        angles[0,0,2] = np.pi/2
        offsets = np.zeros((55,3))
        offsets[1] = [1,0,0]
        world = forward_kinematics(Rotation.from_rotvec(angles.reshape(-1,3)),np.array([[2,3,4.]]),offsets)
        np.testing.assert_allclose(world[0,1],[2,4,4],atol=1e-7)

    def test_bvh_reconstructs_all_local_rotations(self):
        rng = np.random.default_rng(71)
        rotations = Rotation.from_rotvec(rng.normal(size=(4*55,3))*.3)
        root = rng.normal(size=(4,3))
        offsets = rng.normal(size=(55,3))*.1
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'motion.bvh'
            write_bvh(path,rotations,root,offsets,29.97)
            content = path.read_text().splitlines()
            names = [line.split()[1] for line in content if line.strip().startswith(('ROOT ','JOINT '))]
            self.assertEqual(set(names),set(NAMES))
            motion = content.index('MOTION')
            self.assertEqual(content[motion+1],'Frames: 4')
            keys = np.array([[float(v) for v in line.split()] for line in content[motion+3:]])
            np.testing.assert_allclose(keys[:,:3]/100,root,atol=1e-9)
            recovered = Rotation.from_euler('ZXY',keys[:,3:].reshape(-1,3),degrees=True).as_matrix().reshape(4,55,3,3)
            expected = rotations.as_matrix().reshape(4,55,3,3)[:,[NAMES.index(name) for name in names]]
            np.testing.assert_allclose(recovered,expected,atol=1e-9)


class ExtractorTests(unittest.TestCase):
    def test_rejects_missing_payload_and_unsafe_additional_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            asset = root/'invalid.uasset'
            asset.write_bytes(b'not a model')
            with self.assertRaises(ValueError):
                extract(asset,root/'models')
            name = b'../escape\0'
            asset.write_bytes(b'\x05\0\0\0onnx\0'+struct.pack('<q',2)+b'\x08\x08'+struct.pack('<ii',1,len(name))+name+struct.pack('<q',1)+b'x')
            with self.assertRaises(ValueError):
                extract(asset,root/'models')
            self.assertFalse((root/'escape').exists())


if __name__ == '__main__':
    unittest.main()
