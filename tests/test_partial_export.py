import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, Mock
import numpy as np
from m2a import drop_video, scene


class PartialExportTests(unittest.TestCase):
    def test_drop_labels_range_and_preserves_full_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); (root/'models').mkdir()
            (root/'models/quinn_skeleton.txt').touch()
            video=root/'clip.mp4';video.touch()
            full=video.with_suffix('.fbx');full.write_bytes(b'existing')
            def solve(video,run,*args,**kwargs):
                run.mkdir(parents=True)
                report=dict(partial=True,source_start_frame=0,source_end_frame_inclusive=23,people_count=2)
                (run/'scene.fbx').write_bytes(b'scene')
                (run/'scene.json').write_text(json.dumps(report))
                for i in [1,2]:
                    (run/f'person_{i:02d}').mkdir()
                    (run/f'person_{i:02d}/quinn.fbx').write_bytes(b'actor')
                return report
            cap=Mock();cap.get.return_value=328
            with patch.object(drop_video,'ROOT',root),patch.object(drop_video,'solve_auto',solve),patch.object(drop_video.cv2,'VideoCapture',return_value=cap),patch('sys.argv',['drop',str(video),'--moving-camera']):
                self.assertEqual(drop_video.main(),0)
            self.assertEqual(full.read_bytes(),b'existing')
            out=root/'clip_frames_000000-000023_partial.fbx'
            self.assertEqual(out.read_bytes(),b'scene')
            self.assertTrue(out.with_suffix('.json').exists())
            self.assertTrue(root.joinpath('clip_frames_000000-000023_partial_person_02.fbx').exists())

    def test_body_actors_use_same_accepted_range(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)/'run';calls=[]
            def worker(stage,folder,*args,**kwargs):
                if stage=='rectify':
                    folder.mkdir()
                    (folder/'lens.json').write_text(json.dumps(dict(K=np.eye(3).tolist())))
                else:
                    (folder/'camera_report.json').write_text(json.dumps(dict(frames=24,partial=True,input_frames=328,failure={'reason':'join'})))
            def solve(video,run,models,**kwargs):
                calls.append(kwargs)
                run.mkdir()
                (run/'metadata.json').write_text(json.dumps(dict(limitations=[])))
            tracks=[dict(id=i,boxes=np.ones((328,4)),observed=np.ones(328,dtype=bool),coverage=1.) for i in [1,2]]
            report=dict(people=[],people_count=2)
            with patch('m2a.moving_camera.worker',worker),patch('m2a.pipeline.read_frames',return_value=([np.zeros((2,2,3))],24)),patch('m2a.tracking.detect_tracks',return_value=tracks),patch('m2a.pipeline.solve',solve),patch.object(scene,'export_scene',return_value=report):
                result=scene.solve_auto('clip.mp4',out,Path(tmp),moving_camera=True,log=lambda _:None)
            self.assertEqual(len(calls),2)
            for call in calls:
                self.assertEqual(call['end'],23)
                self.assertEqual(call['track_boxes'].shape,(24,4))
            self.assertTrue(result['partial'])
            self.assertEqual(result['source_end_frame_inclusive'],23)


if __name__=='__main__':unittest.main()
