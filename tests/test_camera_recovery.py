import json
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import MagicMock, patch
import cv2
import numpy as np
from tools import camera_worker as worker


class CameraRecoveryTests(unittest.TestCase):
    def run_camera(self, geometric=True):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);out=root/'camera';out.mkdir()
            k=np.array([[100.,0,70],[0,100.,70],[0,0,1]])
            (out/'lens.json').write_text(json.dumps(dict(size=[140,140],K=k.tolist())))
            cv2.imwrite(str(out/'valid_pixels.png'),np.full((140,140),255,np.uint8))
            np.savez(root/'tracks.npz',boxes=np.empty((0,80,4)))
            (root/'detections.json').write_text(json.dumps([dict(boxes=[],scores=[]) for _ in range(80)]))
            frames=[np.full((140,140,3),i,np.uint8) for i in range(80)]
            def read(video,start,end,rotation):return frames[start:None if end is None else end+1],24
            model=MagicMock();model.cuda.return_value.eval.return_value=model
            def inference(images,**kwargs):
                n=len(images)
                return types.SimpleNamespace(depth=np.ones((n,140,140)),intrinsics=np.tile(k,(n,1,1)),
                    extrinsics=np.tile(np.c_[np.eye(3),np.zeros(3)],(n,1,1)),conf=None)
            model.inference.side_effect=inference
            api=types.ModuleType('depth_anything_3.api');api.DepthAnything3=MagicMock()
            api.DepthAnything3.from_pretrained.return_value=model
            geo=types.ModuleType('geocalib');geo.GeoCalib=MagicMock()
            gravity=MagicMock();gravity.detach.return_value.cpu.return_value.numpy.return_value=np.array([[0.,-1.,0.]])
            geo.GeoCalib.return_value.cuda.return_value.eval.return_value.calibrate.return_value={'gravity':types.SimpleNamespace(vec3d=gravity)}
            def refine(images,depths,ik,poses,k,masks):
                if any(int(im[0,0,0])==40 for im in images):
                    if geometric:raise worker.CameraGeometryError('synthetic bad frame 40')
                    raise ValueError('unexpected implementation error')
                return poses,[]
            modules={'torch':MagicMock(),'depth_anything_3':types.ModuleType('depth_anything_3'),'depth_anything_3.api':api,'geocalib':geo}
            with patch.dict('sys.modules',modules),patch('m2a.video.read_frames',read),patch.object(worker,'refine_background',refine),patch('m2a.preview.write_preview'),patch('builtins.print'):
                worker.poses(out,'synthetic',resolution=140)
            report=json.loads((out/'camera_report.json').read_text())
            indices=[np.load(out/s['camera_dir']/'trajectory.npz')['frame_indices'].tolist() for s in report['segments']]
            return report,indices

    def test_search_resumes_after_bad_frame_without_overlap_or_missing_good_tail(self):
        report,indices=self.run_camera()
        self.assertEqual(indices,[list(range(40)),list(range(41,80))])
        self.assertEqual(report['skipped_ranges'],[dict(start=40,end=41)])
        self.assertEqual(report['frames'],79)

    def test_unexpected_errors_are_not_treated_as_geometric_rejections(self):
        with self.assertRaisesRegex(ValueError,'unexpected implementation error'):
            self.run_camera(False)


if __name__=='__main__':unittest.main()
